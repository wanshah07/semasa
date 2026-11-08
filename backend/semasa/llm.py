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

A CHAIN of writers (feature C, 8 Nov 2026): the AI team's full ranked list (`LLMSettings.chain`, from ai_team.chain through
ai_config.llm_for), or, without one, rootsys (LLM_*) and the backup LLM_FALLBACK_API_KEY switches on (Mireld by default).
A call walks the chain until a link answers: a timeout, a 5xx, a 429, a model the gateway does not serve or an empty answer
moves to the next link; a refusal that is the request's own fault stops. Each key goes only to its own host.
"""

from __future__ import annotations

import base64
import json
import re
import time
from collections.abc import Callable
from typing import Any

import requests

from .config import LLMSettings
from .log import get_logger

log = get_logger("semasa.llm")

_FENCE = re.compile(r"^\s*```(?:json|python)?\s*|\s*```\s*$", re.S)
_THINK = re.compile(r"<think>.*?</think>", re.S | re.I)
_PY_LITERALS = {"True": "true", "False": "false", "None": "null"}
_PY_LITERAL_AT = re.compile(r"(True|False|None)(?![A-Za-z0-9_])")


# Token usage (Wan, 9 Oct 2026: "track status of token from mireld and afiq API"): every call records what the gateway's
# `usage` said, where it went and how long it took, through a sink a runner attaches (api_status.attach). No sink: nothing
# is recorded, and a sink that throws never fails a call.
_USAGE_SINK: Callable[[dict[str, Any]], None] | None = None
_LAST_USAGE: dict[str, int] = {}


def set_usage_sink(fn: Callable[[dict[str, Any]], None] | None) -> None:
    global _USAGE_SINK
    _USAGE_SINK = fn


def _record_usage(rec: dict[str, Any]) -> None:
    if _USAGE_SINK is None:
        return
    try:
        _USAGE_SINK(rec)
    except Exception as exc:  # noqa: BLE001
        log.info("usage sink: %s", str(exc)[:120])


def _usage_from(j: Any) -> dict[str, int]:
    u = j.get("usage") if isinstance(j, dict) else None
    if not isinstance(u, dict):
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    p = int(u.get("prompt_tokens") or u.get("input_tokens") or 0)
    c = int(u.get("completion_tokens") or u.get("output_tokens") or 0)
    return {"prompt_tokens": p, "completion_tokens": c, "total_tokens": int(u.get("total_tokens") or (p + c))}


# How a refused call is read (feature C, 8 Nov 2026: "when the chosen model/robot is not live, EVERY backend AI call falls
# over to another live one"). A gateway that times out, answers 5xx or 429, or gives nothing parsable is one link's problem:
# the next link is asked. A 400 that is the REQUEST's own fault (the content, a context too long) would get the same answer
# from every gateway, so the chain stops there; a 400 that is about the MODEL ("not supported", "does not exist") is this
# link's problem and the next one is asked. A 400 nobody can read gets exactly one more link, not the whole chain.
MODEL_FAULT_RE = re.compile(r"model|not supported|unsupported|does not exist|not found|deprecated|no longer|unknown engine|"
                            r"response_format|reasoning", re.I)
REQUEST_FAULT_RE = re.compile(r"context[_ ]length|too long|maximum context|max(imum)? tokens|token limit|content[_ ]?policy|"
                              r"content management|safety|moderation|violat|prompt is too|invalid image|image too", re.I)
_OK, _MISS, _STOP, _UNSURE = "ok", "miss", "stop", "unsure"


def classify_http(status: int | str, body: str) -> str:
    """What a refused HTTP answer means for the CHAIN: _MISS (ask the next link), _STOP (every link would say the same) or
    _UNSURE (a 400 nobody can read: one more link, then stop)."""
    try:
        code = int(status)
    except (TypeError, ValueError):
        return _MISS
    if code == 400:
        if MODEL_FAULT_RE.search(body or ""):
            return _MISS
        if REQUEST_FAULT_RE.search(body or ""):
            return _STOP
        return _UNSURE
    if code == 413 or (code == 422 and REQUEST_FAULT_RE.search(body or "")):
        return _STOP
    return _MISS


class LLM:
    """One writer over a CHAIN of gateways. `settings.chain` (from ai_team.chain through ai_config.llm_for) is the AI team's
    full ranked list; without it the primary and the backup in the settings are a two-link chain, exactly as before. A call
    walks the chain, healthy links first, at most MAX_LINKS links and inside a time budget, and records which link
    answered (`last_model`, `last_gateway`) and every miss (per label, and through the usage sink for api_usage)."""

    PRIMARY_DOWN_AFTER = 2       # misses in a row that put a link to the back of the order for the rest of the run
    MAX_LINKS = 4                # links one call may ask
    TRIAL_MISS_LIMIT = 3
    prefer_backup = False        # class defaults: a stand-in built with __new__ (tests) still has them
    budget_s: float | None = None

    def __init__(self, settings: LLMSettings | None = None, chain: list[dict[str, Any]] | None = None):
        self.s = settings or LLMSettings.load()
        self.calls = 0
        self.failures = 0
        self.backup_answers = 0        # answers that came from a link other than the first ("the backup writer")
        self.last_model = ""           # the model behind the last answer, for the record on the draft
        self.last_gateway = ""         # the gateway (base URL) behind the last answer
        # A one-run trial (semasa.trial, the page's "Try Mireld" button): the backup is asked FIRST and rootsys only
        # when it gives nothing, so the run shows what Mireld can do while still finishing its work.
        self.prefer_backup = False
        self.answers = {"primary": 0, "backup": 0}         # usable answers, per link label
        self.misses = {"primary": 0, "backup": 0}          # asked and got nothing usable, per link label
        self.vision = {"primary": 0, "backup": 0, "backup_missed": 0}
        self.trial_stopped = ""                             # why the trial stopped asking the backup first, if it did
        self._backup_run = 0                                # consecutive misses of the backup while it goes first
        # rootsys down for the run (2 Oct 2026, run 48): every batch spent 3 x 60s on rootsys before the backup answered,
        # four batches ate the 25-minute job limit and the run was cancelled with 90 new items unsummarised. After
        # PRIMARY_DOWN_AFTER calls in a row where a link gave nothing it goes to the BACK of the order for the rest of
        # the run (a per-link cool-off) and is asked once, as a last resort, only when every other link gave nothing too.
        self._miss_run: dict[str, int] = {}
        self.links = self._links(chain)
        # the whole chain may take this long for one answer; the first link is always asked, a later one is skipped when
        # the budget is spent (a 4-link chain of 60 s timeouts must not hold a batch for ten minutes)
        self.budget_s = float(self.s.timeout) * 5

    # --- the chain ---------------------------------------------------------------------

    def _links(self, chain: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        """[{label, slug, provider, base_url, key, model, vision_model}] in the AI team's order. Labels: the settings'
        primary is "primary", its backup "backup" (trial.py and the scrape summary count by those), the rest by slug."""
        given = list(chain if chain is not None else (getattr(self.s, "chain", ()) or ()))
        out: list[dict[str, Any]] = []
        if given:
            for c in given:
                if not c.get("base_url") or not c.get("key") or c.get("blocked"):
                    continue
                base = str(c["base_url"]).rstrip("/")
                if base == (self.s.base_url or "").rstrip("/") and not any(x["label"] == "primary" for x in out):
                    label, vision = "primary", (self.s.vision_model or c.get("model") or "")
                elif base == (self.s.fallback_base_url or "").rstrip("/") and not any(x["label"] == "backup" for x in out):
                    label, vision = "backup", c.get("vision_model") or ""
                else:
                    label, vision = str(c.get("slug") or base), c.get("vision_model") or ""
                out.append({"label": label, "slug": c.get("slug") or label, "provider": c.get("provider") or "openai",
                            "base_url": base, "key": c["key"], "model": c.get("model") or "", "vision_model": vision})
            if out:
                return out
        if self.primary_ok:
            out.append({"label": "primary", "slug": "primary", "provider": self.s.provider, "base_url": self.s.base_url,
                        "key": self.s.api_key or "", "model": self.s.model,
                        "vision_model": self.s.vision_model or self.s.model})
        if self.backup_ok:
            # nothing says the backup's model can see, and a text model would describe a picture it never saw
            out.append({"label": "backup", "slug": "backup", "provider": "openai", "base_url": self.s.fallback_base_url,
                        "key": self.s.fallback_key or "", "model": self.s.fallback_model, "vision_model": ""})
        return out

    def _down(self, label: str) -> bool:
        """This link has missed PRIMARY_DOWN_AFTER times in a row AND another link is still standing: with nobody else to
        ask, a link is never written off (a run without a backup keeps asking rootsys, as before)."""
        runs = getattr(self, "_miss_run", {})
        if runs.get(label, 0) < self.PRIMARY_DOWN_AFTER:
            return False
        return any(runs.get(x["label"], 0) < self.PRIMARY_DOWN_AFTER for x in getattr(self, "links", ()) if x["label"] != label)

    @property
    def primary_down(self) -> bool:
        """The first link has given nothing for PRIMARY_DOWN_AFTER calls in a row and another link carries the run."""
        return self._down("primary")

    @property
    def primary_ok(self) -> bool:
        return bool(self.s.api_key) and not getattr(self.s, "blocked", "")

    @property
    def backup_ok(self) -> bool:
        return bool(getattr(self.s, "fallback_key", None)) and not getattr(self.s, "fallback_blocked", "")

    @property
    def configured(self) -> bool:
        """Read from the SETTINGS, so a caller that swaps `llm.s` (tests do) gets the answer for what it swapped in."""
        return self.primary_ok or self.backup_ok or bool(getattr(self.s, "chain", ()))

    @property
    def can_see(self) -> bool:
        """Something can READ a picture: a link with a vision model, or a picture reader of its own set in the page (which
        works even when the writer is off)."""
        own = bool(getattr(self.s, "vision_key", None) and getattr(self.s, "vision_base_url", "")
                   and getattr(self.s, "vision_reader_model", ""))
        return own or any(x.get("vision_model") for x in getattr(self, "links", ()))

    def why_off(self) -> str:
        """For the page: why the writer did not run."""
        if getattr(self.s, "blocked", ""):
            return self.s.blocked
        if getattr(self.s, "fallback_key", None) and getattr(self.s, "fallback_blocked", ""):
            return f"no LLM_API_KEY, and the backup is off: {self.s.fallback_blocked}"
        return "no LLM key: set the LLM_API_KEY secret (the writer needs it)"

    def _ordered(self, backup: bool) -> list[dict[str, Any]]:
        """The links in the order this call asks them: standing links first (the chain's own order), links in cool-off
        last; in a trial the backup first. `backup=False`: the first link only."""
        links = list(getattr(self, "links", ()))
        if not backup:
            links = links[:1]
        up = [x for x in links if not self._down(x["label"])]
        down = [x for x in links if self._down(x["label"])]
        order = up + down
        if getattr(self, "prefer_backup", False):
            # the trial asks the backup first whatever its run so far: its third miss in a row is what ENDS the trial
            b = next((x for x in order if x["label"] == "backup"), None)
            if b is not None:
                order.remove(b)
                order.insert(0, b)
        return order

    def _writers(self, model: str | None, backup: bool) -> list[tuple[str, str, str, str, str]]:
        """(label, provider, base_url, key, model) in the order they are asked. Each key goes only to its own host. An
        explicit `model` names a model on the FIRST link (the settings' primary); the other links use their own."""
        return [(x["label"], x["provider"], x["base_url"], x["key"],
                 (model or x["model"]) if x["label"] == "primary" else x["model"]) for x in self._ordered(backup)]

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
                 self.last_model or self.s.model, self.last_gateway or self.s.base_url)
        return ok

    def chat_json(self, system: str, user: str | list[dict[str, Any]], *, max_tokens: int = 1500, retries: int = 2,
                  model: str | None = None, backup: bool = True) -> dict[str, Any] | None:
        """`user` is a string, or a list of content parts (see `image_parts`). The chain is walked in order: the first
        link with `retries` retries, every later link with one, a link in cool-off asked once as a last resort."""
        return self._walk(system, user, max_tokens, retries, model, backup, _parse_object)

    def chat_text(self, system: str, user: str | list[dict[str, Any]], *, max_tokens: int = 1500, model: str | None = None,
                  backup: bool = True) -> str | None:
        """The answer as plain text, one try per link; None when none gave any. For answers that are not JSON, such as a
        whole HTML file, where wrapping the file in a JSON string is what breaks it."""
        return self._walk(system, user, max_tokens, 0, model, backup, _parse_text)

    def _walk(self, system: str, user: str | list[dict[str, Any]], max_tokens: int, retries: int, model: str | None,
              backup: bool, parse: Callable[[str], Any]) -> Any:
        writers = self._writers(model, backup)
        if not writers:
            return None
        t0 = time.monotonic()
        budget = getattr(self, "budget_s", None)
        unsure_used = False
        for n, (label, provider, base, key, use_model) in enumerate(writers[: self.MAX_LINKS]):
            if n > 0:
                if budget is not None and time.monotonic() - t0 >= budget:
                    log.warning("LLM: %d link(s) gave nothing and the %.0fs budget is spent; %s is not asked", n, budget, label)
                    break
                log.warning("LLM: %s gave no usable answer; asking %s (%s, %s)", writers[n - 1][0], label, base, use_model)
            last_resort = n > 0 and self._down(label)
            tries = 0 if last_resort else (retries if label == "primary" else min(retries, 1))
            data, verdict = self._ask(system, user, max_tokens, tries, provider, base, key, use_model, parse)
            if data is not None:
                self._note_answer(label, use_model, base)
                return data
            self._note_miss(label, n == 0)
            if verdict == _STOP:
                log.warning("LLM: the request itself was refused (%s); no other link is asked", label)
                break
            if verdict == _UNSURE:
                if unsure_used:
                    break
                unsure_used = True                 # a 400 nobody can read: one more link, then stop
        self.failures += 1
        return None

    def _note_answer(self, label: str, model: str, base: str) -> None:
        self.last_model = model
        self.last_gateway = base
        self.answers[label] = self.answers.get(label, 0) + 1
        runs = self.__dict__.setdefault("_miss_run", {})
        runs[label] = 0
        if label != "primary":
            self.backup_answers = getattr(self, "backup_answers", 0) + 1
            if label == "backup":
                self._backup_run = 0

    def _note_miss(self, label: str, first: bool) -> None:
        self.misses[label] = self.misses.get(label, 0) + 1
        runs = self.__dict__.setdefault("_miss_run", {})
        runs[label] = runs.get(label, 0) + 1
        if runs[label] == self.PRIMARY_DOWN_AFTER and self._down(label):
            log.warning("LLM: %s has given nothing %d calls in a row; it goes to the back of the chain for the rest of the run",
                        label, runs[label])
        if label == "backup" and first:
            self._trial_miss()

    def _ask(self, system: str, user: str | list[dict[str, Any]], max_tokens: int, retries: int, provider: str,
             base: str, key: str, model: str, parse: Callable[[str], Any] | None = None) -> tuple[Any, str]:
        """(answer, verdict): the parsed answer and _OK, or None and why the chain should go on (_MISS), stop (_STOP) or
        allow one more link (_UNSURE)."""
        parse = parse or _parse_object
        verdict = _MISS
        for attempt in range(retries + 1):
            self.calls += 1
            try:
                text = self._call(system, user, max_tokens, model, provider=provider, base=base, key=key)
                try:
                    data = parse(text)
                except ValueError as exc:
                    # say WHAT came back, or a parse failure is undiagnosable from the log
                    log.warning("LLM answer not parsable (%s); it starts: %r", exc, (text or "")[:200])
                    data = None
                if data is not None:
                    return data, _OK
            except requests.Timeout:
                log.warning("LLM timeout after %ss (attempt %d)", self.s.timeout, attempt + 1)
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else "?"
                body = (exc.response.text[:300] if exc.response is not None else "")
                log.warning("LLM HTTP %s: %s", status, body)
                if status in (400, 401, 403, 404, 413, 422):
                    verdict = classify_http(status, body)
                    break  # not going to change on retry
            except (requests.RequestException, ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
                # IndexError / TypeError: a 200 whose "choices" is empty or null (a content filter's usual answer) is
                # "no answer", so the next link is asked, never a crash of the whole run
                log.warning("LLM error: %s", exc)
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
        return None, verdict

    # --- dialects ---------------------------------------------------------------

    def describe_image(self, system: str, prompt: str, data: bytes, mime: str, *,
                       max_tokens: int = 900) -> dict[str, Any] | None:
        """The READ step: one picture and a question. None when no key, gateway or model will take a picture — the caller
        records that the reference was not read rather than pretending it was.

        A picture reader set in the page (its own endpoint, key and model) is asked first; then every link of the chain
        that has a vision model (the first link's VISION_MODEL; another robot's own model when that robot reads pictures),
        in the chain's order. A link with no vision model is never sent a picture: a text model would describe a picture
        it never saw."""
        if getattr(self.s, "vision_key", None) and getattr(self.s, "vision_base_url", "") and \
                getattr(self.s, "vision_reader_model", ""):
            provider = self.s.vision_provider or "openai"
            out, _ = self._ask(system, image_parts(provider, prompt, data, mime), max_tokens, 1, provider,
                               self.s.vision_base_url, self.s.vision_key or "", self.s.vision_reader_model)
            if out is not None:
                self.last_model = self.s.vision_reader_model
                self.last_gateway = self.s.vision_base_url
                self.vision["reader"] = self.vision.get("reader", 0) + 1
                return out
            log.warning("the picture reader set in the page gave nothing; the writer's chain reads it instead")
        order = self._ordered(True)
        if getattr(self, "prefer_backup", False):
            # the trial: can the backup's model SEE? Asked once, with its own key, before the rest of the chain.
            b = next((x for x in order if x["label"] == "backup"), None)
            if b is not None and not b.get("vision_model"):
                order = [{**b, "vision_model": b["model"], "_trial": True}] + [x for x in order if x is not b]
        t0 = time.monotonic()
        budget = getattr(self, "budget_s", None)
        asked = 0
        for x in order:
            vm = x.get("vision_model")
            if not vm:
                continue
            if asked and budget is not None and time.monotonic() - t0 >= budget:
                log.warning("LLM: the picture read budget is spent; %s is not asked", x["label"])
                break
            if asked >= self.MAX_LINKS:
                break
            asked += 1
            out, verdict = self._ask(system, image_parts(x["provider"], prompt, data, mime), max_tokens, 1, x["provider"],
                                     x["base_url"], x["key"], vm)
            if out is not None:
                self._note_answer(x["label"], vm, x["base_url"])
                self.vision[x["label"]] = self.vision.get(x["label"], 0) + 1
                return out
            if x.get("_trial"):
                self.vision["backup_missed"] += 1
                log.warning("LLM trial: the backup did not read the picture; the chain reads it instead")
                self._trial_miss()
            else:
                log.warning("LLM: %s (%s) did not read the picture; the next link with a vision model is asked", x["label"], vm)
            if verdict == _STOP:
                break
        return None

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
        t0 = time.monotonic()
        _LAST_USAGE.clear()
        try:
            if provider == "anthropic":
                out = self._anthropic(system, user, max_tokens, model, base, key or "")
            else:
                out = self._openai(system, user, max_tokens, model, base, key or "")
        except Exception as exc:
            ms = int((time.monotonic() - t0) * 1000)
            _record_usage({"base": base, "model": model, "ok": False, "ms": ms, "error": str(exc)[:200]})
            raise
        _record_usage({"base": base, "model": model, "ok": True, "ms": int((time.monotonic() - t0) * 1000), **_LAST_USAGE})
        return out

    def _openai(self, system: str, user: str | list[dict[str, Any]], max_tokens: int, model: str, base: str,
                key: str) -> str:
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        body: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": with_instructions(system, user)}],
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
        j = r.json()
        _LAST_USAGE.update(_usage_from(j))
        choice = (j.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        content = msg.get("content") or ""
        # a thinking model (deepseek-v4.1-flash, kimi-k3, glm-5.x) spends its budget on reasoning FIRST; when that eats the
        # whole max_tokens the answer is empty and finish_reason is "length". Say so, or the log reads as a dead gateway
        # (24 Oct 2026: three motion calls, 7000 of 7000 tokens each, content "")
        if not content.strip() and (choice.get("finish_reason") == "length" or msg.get("reasoning_content")):
            log.warning("LLM %s: no answer text; the model spent its %d tokens thinking (finish_reason=%s). Raise max_tokens "
                        "or pick a non-thinking model", model, max_tokens, choice.get("finish_reason"))
        return content

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
        j = r.json()
        _LAST_USAGE.update(_usage_from(j))
        blocks = j.get("content") or []
        return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")


def with_instructions(system: str, user: str | list[dict[str, Any]]) -> str | list[dict[str, Any]]:
    """The instructions again, at the top of the user turn (OpenAI dialect only). From 28 Sep 2026 the rootsys gateway
    stopped passing the system message on: every scrape batch came back as "you haven't included a question or
    request — what would you like me to do?", 0/12 answered, and six runs in a row hit the 25-minute limit (scrape
    runs 36497165283 to 36589007283). A model that does get the system message loses nothing by reading them twice."""
    if not system:
        return user
    head = f"INSTRUCTIONS (follow them exactly):\n{system}\n\nINPUT:\n"
    if isinstance(user, str):
        return head + user
    return [{"type": "text", "text": head.rstrip()}, *user]


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
    # The object followed by prose that has a brace of its own ("Note: each {i} is the index"): the first-to-last-brace
    # cut above then ends in the note and fails. Read exactly one object from the first brace and ignore what follows.
    if start != -1:
        for attempt in (cleaned[start:], _pythonish_to_json(cleaned[start:])):
            try:
                return json.JSONDecoder().raw_decode(attempt)[0]
            except json.JSONDecodeError as exc:
                last = exc
    raise ValueError(f"not a JSON object ({last})")


def _parse_object(text: str) -> dict[str, Any] | None:
    """A JSON OBJECT, or None for JSON of another shape (logged); ValueError for no JSON at all."""
    data = _parse_json(text)
    if isinstance(data, dict):
        return data
    log.warning("LLM answered non-object JSON (%s): %r", type(data).__name__, (text or "")[:200])
    return None


def _parse_text(text: str) -> str:
    if not text or not text.strip():
        raise ValueError("empty answer")
    return text
