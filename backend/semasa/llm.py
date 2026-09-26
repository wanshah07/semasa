"""One chat call, two dialects, one contract.

`chat_json()` returns a dict on success and **None** on any failure — timeout, 4xx,
5xx, unparsable JSON, silent endpoint. The caller must record which of the two it
got. A dead endpoint that quietly degrades to a keyword rulebook fills the store with
verdicts that read like reviewed ones (`kkm-complaints` learned this the hard way), so
`summary_source` is a column, not a hope.

Dialects:
  openai     — POST {base}/chat/completions. Covers OpenAI, rootsys, Mireld, Groq, OpenRouter,
               and Anthropic's own OpenAI-compatible endpoint. `response_format`
               json_object is requested; a server that ignores it is handled by the
               fence-stripping parser.
  anthropic  — POST {base}/v1/messages with the native schema.

`probe()` asks the endpoint who it is, before a run spends anything on it.

Two writers: rootsys (LLM_*) and, when LLM_FALLBACK_API_KEY is set, a backup (Mireld by default) asked only when
rootsys gives no usable answer. Each key goes only to its own host.
"""

from __future__ import annotations

import base64
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
        self.backup_answers = 0        # answers that came from the backup writer
        self.last_model = ""           # the model behind the last answer, for the record on the draft
        # A one-run trial (semasa.trial, the page's "Try Mireld" button): the backup is asked FIRST and rootsys only
        # when it gives nothing, so the run shows what Mireld can do while still finishing its work.
        self.prefer_backup = False
        self.answers = {"primary": 0, "backup": 0}         # usable answers, per writer
        self.misses = {"primary": 0, "backup": 0}          # asked and got nothing usable, per writer
        self.vision = {"primary": 0, "backup": 0, "backup_missed": 0}
        self.trial_stopped = ""                             # why the trial stopped asking the backup first, if it did
        self._backup_run = 0                                # consecutive misses of the backup while it goes first

    # --- which writer ---------------------------------------------------------------

    @property
    def primary_ok(self) -> bool:
        return bool(self.s.api_key) and not getattr(self.s, "blocked", "")

    @property
    def backup_ok(self) -> bool:
        return bool(getattr(self.s, "fallback_key", None)) and not getattr(self.s, "fallback_blocked", "")

    @property
    def configured(self) -> bool:
        return self.primary_ok or self.backup_ok

    def why_off(self) -> str:
        """For the page: why the writer did not run."""
        if getattr(self.s, "blocked", ""):
            return self.s.blocked
        if getattr(self.s, "fallback_key", None) and getattr(self.s, "fallback_blocked", ""):
            return f"no LLM_API_KEY, and the backup is off: {self.s.fallback_blocked}"
        return "no LLM key: set the LLM_API_KEY secret (the writer needs it)"

    def _writers(self, model: str | None, backup: bool) -> list[tuple[str, str, str, str, str]]:
        """(label, provider, base_url, key, model) in the order they are asked. The backup speaks the OpenAI dialect
        and gets its own key only: the rootsys key never leaves for Mireld, nor Mireld's for rootsys."""
        out = []
        if self.primary_ok:
            out.append(("primary", self.s.provider, self.s.base_url, self.s.api_key or "", model or self.s.model))
        if backup and self.backup_ok:
            b = ("backup", "openai", self.s.fallback_base_url, self.s.fallback_key or "", self.s.fallback_model)
            if self.prefer_backup:
                out.insert(0, b)
            else:
                out.append(b)
        return out

    # --- public -----------------------------------------------------------------

    def probe(self) -> bool:
        """True when a writer answers a small REAL question with parsable JSON (rootsys first, then the backup).

        It used to ask for {"ok": true}. The rootsys gateway filled that literal with junk on three
        runs in a row (`<<true>>`, `<%= data.ok %>`, `##DISABLED## true`; runs 36041027392 and
        36071479022) while real summaries worked, so the probe switched the LLM off for nothing.
        A classification with a quoted string answer is the shape the real work has."""
        if not self.configured:
            log.warning("LLM: no API key — summaries will be rules-only")
            return False
        out = self.chat_json(
            "You classify Malaysian news headlines. Reply with one JSON object only.",
            'Headline: "Harga minyak sawit naik minggu ini". Answer in the form {"category": "<one lowercase word>"}.',
            max_tokens=40)
        cat = out.get("category") if isinstance(out, dict) else None
        ok = isinstance(cat, str) and bool(cat.strip())
        backup = ok and self.backup_answers > 0
        log.info("LLM probe %s: %s model=%s base=%s", "OK" if ok else "FAILED",
                 "the BACKUP answered" if backup else f"provider={self.s.provider}",
                 self.last_model or self.s.model, self.s.fallback_base_url if backup else self.s.base_url)
        return ok

    def chat_json(self, system: str, user: str | list[dict[str, Any]], *, max_tokens: int = 1500, retries: int = 2,
                  model: str | None = None, backup: bool = True) -> dict[str, Any] | None:
        """`user` is a string, or a list of content parts (see `image_parts`). rootsys first; the backup only when
        rootsys gave nothing usable, with one retry of its own."""
        writers = self._writers(model, backup)
        if not writers:
            return None
        for n, (label, provider, base, key, use_model) in enumerate(writers):
            if label == "backup" and n > 0:
                log.warning("LLM: rootsys gave no usable answer; asking the backup (%s, %s)", base, use_model)
            elif label == "primary" and n > 0:
                log.warning("LLM trial: the backup gave no usable answer; rootsys answers instead")
            data = self._ask(system, user, max_tokens, retries if label == "primary" else 1, provider, base, key, use_model)
            if data is not None:
                self.last_model = use_model
                self.answers[label] += 1
                if label == "backup":
                    self.backup_answers += 1
                    self._backup_run = 0
                return data
            self.misses[label] += 1
            if label == "backup" and n == 0:
                self._trial_miss()
        self.failures += 1
        return None

    def _ask(self, system: str, user: str | list[dict[str, Any]], max_tokens: int, retries: int, provider: str,
             base: str, key: str, model: str) -> dict[str, Any] | None:
        for attempt in range(retries + 1):
            self.calls += 1
            try:
                text = self._call(system, user, max_tokens, model, provider=provider, base=base, key=key)
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
        return None

    # --- dialects ---------------------------------------------------------------

    def describe_image(self, system: str, prompt: str, data: bytes, mime: str, *,
                       max_tokens: int = 900) -> dict[str, Any] | None:
        """The READ step: one picture and a question to VISION_MODEL. None when the key,
        the gateway or the model will not take a picture — the caller records that the
        reference was not read rather than pretending it was. rootsys only: nothing says the
        backup's model can see, and a text model would describe a picture it never saw."""
        if self.prefer_backup and self.backup_ok:
            # the trial: can the backup's model SEE? Asked once, with its own key; rootsys reads it if not.
            out = self._ask(system, image_parts("openai", prompt, data, mime), max_tokens, 1, "openai",
                            self.s.fallback_base_url, self.s.fallback_key or "", self.s.fallback_model)
            if out is not None:
                self.last_model = self.s.fallback_model
                self.vision["backup"] += 1
                self.answers["backup"] += 1
                self.backup_answers += 1
                return out
            self.vision["backup_missed"] += 1
            log.warning("LLM trial: the backup did not read the picture; rootsys reads it instead")
            self._trial_miss()
        if not self.primary_ok:
            return None
        parts = image_parts(self.s.provider, prompt, data, mime)
        out = self.chat_json(system, parts, max_tokens=max_tokens, retries=1,
                             model=self.s.vision_model or self.s.model, backup=False)
        if out is not None:
            self.vision["primary"] += 1
        return out

    TRIAL_MISS_LIMIT = 3

    def _trial_miss(self) -> None:
        """A backup that keeps failing while it goes first would cost every call a timeout. After three in a row the
        trial stops asking it first (rootsys leads again), and the report says so."""
        if not self.prefer_backup:
            return
        self._backup_run += 1
        if self._backup_run >= self.TRIAL_MISS_LIMIT:
            self.prefer_backup = False
            self.trial_stopped = f"the backup missed {self._backup_run} times in a row, so rootsys led for the rest of the run"
            log.warning("LLM trial stopped: %s", self.trial_stopped)

    def backup_models(self) -> list[str]:
        """The backup's own model list (GET /models with its key), for the trial report. [] when it will not say."""
        if not self.backup_ok:
            return []
        try:
            r = requests.get(f"{self.s.fallback_base_url}/models", headers={"Authorization": f"Bearer {self.s.fallback_key}"},
                             timeout=min(self.s.timeout, 30))
            r.raise_for_status()
            data = r.json()
            items = data.get("data") if isinstance(data, dict) else data
            return sorted({str(m.get("id") if isinstance(m, dict) else m) for m in (items or [])})[:200]
        except (requests.RequestException, ValueError, AttributeError) as exc:
            log.warning("could not list the backup's models: %s", str(exc)[:200])
            return []

    def _call(self, system: str, user: str | list[dict[str, Any]], max_tokens: int, model: str, *,
              provider: str | None = None, base: str | None = None, key: str | None = None) -> str:
        provider = provider or self.s.provider
        base = base or self.s.base_url
        key = self.s.api_key if key is None else key
        if provider == "anthropic":
            return self._anthropic(system, user, max_tokens, model, base, key or "")
        return self._openai(system, user, max_tokens, model, base, key or "")

    def _openai(self, system: str, user: str | list[dict[str, Any]], max_tokens: int, model: str, base: str,
                key: str) -> str:
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        body: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0.2,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        r = requests.post(f"{base}/chat/completions", headers=headers, json=body, timeout=self.s.timeout)
        if r.status_code == 400 and "response_format" in r.text:
            # endpoint does not know json_object mode: ask again without it
            body.pop("response_format")
            r = requests.post(f"{base}/chat/completions", headers=headers, json=body, timeout=self.s.timeout)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    def _anthropic(self, system: str, user: str | list[dict[str, Any]], max_tokens: int, model: str, base: str,
                   key: str) -> str:
        r = requests.post(
            f"{base}/v1/messages",
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
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


def image_parts(provider: str, prompt: str, data: bytes, mime: str) -> list[dict[str, Any]]:
    """A picture plus words, in the shape each dialect wants. The picture goes inline as
    base64: a gateway is not guaranteed to fetch a URL (kkm-complaints sends data URIs to
    rootsys for the same reason)."""
    b64 = base64.b64encode(data).decode("ascii")
    if provider == "anthropic":
        return [{"type": "image", "source": {"type": "base64", "media_type": mime, "data": b64}},
                {"type": "text", "text": prompt}]
    return [{"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}]


def _pythonish_to_json(s: str) -> str:
    """Rewrite a Python-literal answer as JSON: True/False/None outside strings become
    true/false/null, and single-quoted strings become double-quoted. Some gateways'
    models answer `{"ok": True}` or `{'ok': True}` even when asked for JSON (run
    36026074962: "Expecting value: line 1 column 7 (char 6)" on all three probes).
    Text inside strings is never touched, so a summary saying "True" survives.
    Also unwraps a gateway's <<value>> template markers found outside strings."""
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
        if s.startswith("<<", i):
            # rootsys gateway, scrape run 36027449389: the first probe answer was
            # {"ok":<<true>>}. Unwrap <<value>> outside strings; inside a string it is text.
            close = s.find(">>", i + 2)
            if close != -1:
                out.append(_pythonish_to_json(s[i + 2 : close]))
                i = close + 2
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
