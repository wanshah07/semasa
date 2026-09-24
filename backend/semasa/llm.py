"""One chat call, two dialects, one contract.

`chat_json()` returns a dict on success and **None** on any failure — timeout, 4xx,
5xx, unparsable JSON, silent endpoint. The caller must record which of the two it
got. A dead endpoint that quietly degrades to a keyword rulebook fills the store with
verdicts that read like reviewed ones (`kkm-complaints` learned this the hard way), so
`summary_source` is a column, not a hope.

Dialects:
  openai     — POST {base}/chat/completions. Covers OpenAI, Mireld, Groq, OpenRouter,
               and Anthropic's own OpenAI-compatible endpoint. `response_format`
               json_object is requested; a server that ignores it is handled by the
               fence-stripping parser.
  anthropic  — POST {base}/v1/messages with the native schema.

`probe()` asks the endpoint who it is, before a run spends anything on it.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

import requests

from .config import LLMSettings
from .log import get_logger

log = get_logger("semasa.llm")

_FENCE = re.compile(r"^\s*```(?:json|python)?\s*|\s*```\s*$", re.S)
_THINK = re.compile(r"<think>.*?</think>", re.S | re.I)
_PY_LITERALS = {"True": "true", "False": "false", "None": "null"}
_PY_LITERAL_AT = re.compile(r"(True|False|None)(?![A-Za-z0-9_])")


class LLM:
    def __init__(self, settings: LLMSettings | None = None):
        self.s = settings or LLMSettings.load()
        self.calls = 0
        self.failures = 0

    @property
    def configured(self) -> bool:
        return bool(self.s.api_key)

    # --- public -----------------------------------------------------------------

    def probe(self) -> bool:
        """True when the endpoint answers a trivial request with parsable JSON."""
        if not self.configured:
            log.warning("LLM: no API key — summaries will be rules-only")
            return False
        out = self.chat_json("Reply with JSON only.", 'Return {"ok": true}.', max_tokens=20)
        ok = bool(out) and out.get("ok") is True
        log.info("LLM probe %s: provider=%s model=%s base=%s", "OK" if ok else "FAILED",
                 self.s.provider, self.s.model, self.s.base_url)
        return ok

    def chat_json(self, system: str, user: str, *, max_tokens: int = 1500, retries: int = 2) -> dict[str, Any] | None:
        if not self.configured:
            return None
        for attempt in range(retries + 1):
            self.calls += 1
            try:
                text = self._call(system, user, max_tokens)
                try:
                    data = _parse_json(text)
                except ValueError as exc:
                    # say WHAT came back, or a parse failure is undiagnosable from the log
                    log.warning("LLM answer not parsable (%s); it starts: %r", exc, (text or "")[:200])
                    data = None
                if isinstance(data, dict):
                    return data
                if data is not None:
                    log.warning("LLM answered non-object JSON (%s): %r", type(data).__name__, (text or "")[:200])
            except requests.Timeout:
                log.warning("LLM timeout after %ss (attempt %d)", self.s.timeout, attempt + 1)
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else "?"
                body = (exc.response.text[:300] if exc.response is not None else "")
                log.warning("LLM HTTP %s: %s", status, body)
                if status in (400, 401, 403, 404):
                    break  # not going to change on retry
            except (requests.RequestException, ValueError, KeyError) as exc:
                log.warning("LLM error: %s", exc)
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
        self.failures += 1
        return None

    # --- dialects ---------------------------------------------------------------

    def _call(self, system: str, user: str, max_tokens: int) -> str:
        if self.s.provider == "anthropic":
            return self._anthropic(system, user, max_tokens)
        return self._openai(system, user, max_tokens)

    def _openai(self, system: str, user: str, max_tokens: int) -> str:
        r = requests.post(
            f"{self.s.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.s.api_key}", "Content-Type": "application/json"},
            json={
                "model": self.s.model,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "temperature": 0.2,
                "max_tokens": max_tokens,
                "response_format": {"type": "json_object"},
            },
            timeout=self.s.timeout,
        )
        if r.status_code == 400 and "response_format" in r.text:
            # endpoint does not know json_object mode: ask again without it
            r = requests.post(
                f"{self.s.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.s.api_key}", "Content-Type": "application/json"},
                json={
                    "model": self.s.model,
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                    "temperature": 0.2,
                    "max_tokens": max_tokens,
                },
                timeout=self.s.timeout,
            )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    def _anthropic(self, system: str, user: str, max_tokens: int) -> str:
        r = requests.post(
            f"{self.s.base_url}/v1/messages",
            headers={
                "x-api-key": self.s.api_key or "",
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": self.s.model,
                "system": system,
                "messages": [{"role": "user", "content": user}],
                "max_tokens": max_tokens,
                "temperature": 0.2,
            },
            timeout=self.s.timeout,
        )
        r.raise_for_status()
        blocks = r.json().get("content") or []
        return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")


def _pythonish_to_json(s: str) -> str:
    """Rewrite a Python-literal answer as JSON: True/False/None outside strings become
    true/false/null, and single-quoted strings become double-quoted. Some gateways'
    models answer `{"ok": True}` or `{'ok': True}` even when asked for JSON (run
    36026074962: "Expecting value: line 1 column 7 (char 6)" on all three probes).
    Text inside strings is never touched, so a summary saying "True" survives."""
    out: list[str] = []
    i, n, quote_char = 0, len(s), ""
    while i < n:
        c = s[i]
        if quote_char:
            if c == "\\" and i + 1 < n:
                nxt = s[i + 1]
                out.append("'" if (quote_char == "'" and nxt == "'") else c + nxt)
                i += 2
                continue
            if c == quote_char:
                out.append('"')
                quote_char = ""
            elif c == '"':            # a bare " inside a single-quoted string
                out.append('\\"')
            else:
                out.append(c)
            i += 1
            continue
        if c in "\"'":
            quote_char = c
            out.append('"')
            i += 1
            continue
        m = _PY_LITERAL_AT.match(s, i)
        if m and (i == 0 or not (s[i - 1].isalnum() or s[i - 1] == "_")):
            out.append(_PY_LITERALS[m.group(1)])
            i = m.end()
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _parse_json(text: str) -> Any:
    """Tolerates code fences, <think> blocks, prose around the object and Python-style
    literals; raises ValueError otherwise."""
    if not text or not text.strip():
        raise ValueError("empty answer")
    cleaned = _FENCE.sub("", _THINK.sub("", text).strip())
    candidates = [cleaned]
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end > start:
        candidates.append(cleaned[start : end + 1])
    last: Exception | None = None
    for candidate in candidates:
        for attempt in (candidate, _pythonish_to_json(candidate)):
            try:
                return json.loads(attempt)
            except json.JSONDecodeError as exc:
                last = exc
    raise ValueError(f"not a JSON object ({last})")
