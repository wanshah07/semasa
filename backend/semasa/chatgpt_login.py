"""Wan's ChatGPT login, used by Motion to draw its scene pictures (Wan, 5 Nov 2026: "for motion - add codex or chatgpt login
Oauth, so image motion can generate based on story board and styles apply").

How it works. Wan runs `codex login` (the ChatGPT option) on his own computer and pastes the contents of ~/.codex/auth.json into
the Motion tab. supabase/058 keeps the tokens in `semasa_chatgpt_auth`, which no page policy can read. This module, running on the
GitHub runner with the service role, does two things with them:

  * keeps the access token fresh: a Codex access token lasts days, and a refresh token is single-use, so every refresh writes the
    new pair back at once. Two runs refreshing together would both present the same refresh token; the loser reloads the row
    and uses what the winner saved.
  * draws a picture: one call to the Codex backend's Responses endpoint (the one the Codex CLI itself uses) with the hosted
    `image_generation` tool, streamed, and the finished picture read off the stream as base64.

This is OpenAI's own first-party login, not an app registered by Semasa, and it is NOT an API: OpenAI can change or limit it
without notice. So nothing here is allowed to stop a film. Every failure is an exception the caller turns into a note, and the
latest outcome is written on the row (`last_ok_at` / `last_error`) for the card in the page to show.
"""

from __future__ import annotations

import base64
import json
import re
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import requests

from .log import get_logger

log = get_logger("semasa.chatgpt")

TABLE = "semasa_chatgpt_auth"
ISSUER = "https://auth.openai.com"
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"          # the Codex CLI's public client: the login Wan made with `codex login`
RESPONSES = "https://chatgpt.com/backend-api/codex/responses"
SKEW = timedelta(minutes=5)                          # refresh when the access token has less than this left
DEFAULT_MODEL = "gpt-5.5"               # "gpt-5" is refused for a ChatGPT account (Codex); FALLBACK_MODELS[0]
INSTRUCTIONS = ("You are an image generator. Call the image_generation tool exactly once, using the user's message as the "
                "picture request, then stop. Never answer with text.")
SIZES = {"portrait": "1024x1536", "landscape": "1536x1024", "square": "1024x1024"}
MODELS = RESPONSES.rsplit("/", 1)[0] + "/models"   # the models this ChatGPT account may use with Codex (the CLI asks the same)
CLIENT_VERSION = "0.99.0"
# The model list is filtered by the Codex client version asked for: a newer model is hidden from an older client. 8 Nov 2026: a
# fresh login listed only "codex-auto-review" at 0.99.0 while every gpt-* writer was refused. When the first list has no
# writer, the same GET is repeated with newer versions (a plain GET, nothing is spent) and the first list with a writer wins.
CLIENT_VERSIONS = (CLIENT_VERSION, "1.0.0", "1.5.0", "2.0.0", "5.0.0")
# Tried in this order when the saved model is refused and the account's own list cannot be read (7 Nov 2026: "The 'gpt-5' model is
# not supported when using Codex with a ChatGPT account"). The account's list, when it answers, always comes first.
FALLBACK_MODELS = ("gpt-5.5", "gpt-5.4", "gpt-5.3-codex", "gpt-5.2-codex", "gpt-5.2", "gpt-5.1-codex", "gpt-5.1", "gpt-5-codex")
MODEL_TRIES = 4
# ChatGPT's own list carries entries that are not writing models (7 Nov 2026: the first live pick was "codex-auto-review", a code
# reviewer, and it was then saved as the model for storyboards and chat). Only a gpt-* slug is a candidate, and never a reviewer.
NOT_A_WRITER = re.compile(r"review|embed|moderation|realtime|audio|tts|transcribe|image|search", re.I)


def writer_candidates(listed: list[str]) -> list[str]:
    """The models worth asking, best first: the known fallbacks the account lists, then its other gpt-* writers, then the rest of
    the fallbacks (the list may be stale or unreadable). A slug that is not a writer is never asked."""
    ok = [m for m in listed if isinstance(m, str) and m.startswith("gpt-") and not NOT_A_WRITER.search(m)]
    out = [m for m in FALLBACK_MODELS if m in ok] + [m for m in ok if m not in FALLBACK_MODELS] + list(FALLBACK_MODELS)
    return list(dict.fromkeys(out))


# The image tool refuses a setting it does not offer for the image model behind the chosen model (8 Nov 2026, gpt-6.1-sol:
# "Complexity 'medium' is not supported for this image model."). The default is refused, so the other levels are asked in turn.
COMPLEXITY_REFUSED = re.compile(r"complexity '([\w-]+)' is not supported", re.I)
COMPLEXITIES = ("low", "high", "medium")

MODEL_REFUSED = re.compile(r"model_not_found|model is not supported|not supported when using codex|unknown model|"
                           r"does not exist|invalid model", re.I)


class ChatGPTError(RuntimeError):
    """A ChatGPT call that did not give a picture. `limit`: the plan's allowance is used up (stop asking for this film).
    `auth`: the login itself is refused (Wan has to log in again)."""

    def __init__(self, message: str, *, limit: bool = False, auth: bool = False, model: bool = False):
        super().__init__(message)
        self.limit, self.auth, self.model = limit, auth, model


def claims(token: str) -> dict[str, Any]:
    """The payload of a JWT, unverified (the server is what verifies it; this only reads when it ends and whose it is)."""
    try:
        body = str(token).split(".")[1]
        return json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    except Exception:  # noqa: BLE001 - an unreadable token is just a token with no known expiry
        return {}


def expiry(token: str) -> datetime | None:
    exp = claims(token).get("exp")
    return datetime.fromtimestamp(exp, UTC) if isinstance(exp, (int, float)) else None


def account_of(tokens: dict[str, Any]) -> str:
    """The ChatGPT account id the Codex backend wants in `chatgpt-account-id`: saved with the login, else read off the tokens."""
    if tokens.get("account_id"):
        return str(tokens["account_id"])
    for key in ("id_token", "access_token"):
        info = claims(str(tokens.get(key) or "")).get("https://api.openai.com/auth") or {}
        if isinstance(info, dict) and info.get("chatgpt_account_id"):
            return str(info["chatgpt_account_id"])
    return ""


def _clip(text: Any, n: int = 300) -> str:
    return " ".join(str(text or "").split())[:n]


def _event_error(ev: dict[str, Any]) -> str:
    err = (ev.get("response") or {}).get("error") or ev.get("error") or {}
    if isinstance(err, dict):
        return _clip(err.get("message") or err.get("code") or ev.get("message") or "the ChatGPT call failed")
    return _clip(err or ev.get("message") or "the ChatGPT call failed")


def read_stream(lines: Any) -> bytes:
    """The finished picture from a Responses event stream: the `image_generation_call` item's base64 `result`, from the item's own
    `done` event or, failing that, from the final `response.completed` output. An error event, or a stream with no picture,
    raises."""
    found = ""
    said = []
    for raw in lines:
        line = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw or "")
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            continue
        try:
            ev = json.loads(data)
        except ValueError:
            continue
        kind = str(ev.get("type") or "")
        if kind in ("response.failed", "error"):
            msg = _event_error(ev)
            raise ChatGPTError(msg, limit=_is_limit(msg))
        item = ev.get("item") or {}
        if kind == "response.output_item.done" and item.get("type") == "image_generation_call" and item.get("result"):
            found = str(item["result"])
        elif kind == "response.output_text.delta":
            said.append(str(ev.get("delta") or ""))
        elif kind == "response.completed" and not found:
            for out in (ev.get("response") or {}).get("output") or []:
                if out.get("type") == "image_generation_call" and out.get("result"):
                    found = str(out["result"])
    if not found:
        raise ChatGPTError("ChatGPT answered without a picture" + (f": {_clip(''.join(said), 160)}" if said else ""))
    try:
        data = base64.b64decode(found, validate=False)
    except ValueError as exc:
        raise ChatGPTError("the picture ChatGPT sent could not be decoded") from exc
    if len(data) < 2000:
        raise ChatGPTError("the picture ChatGPT sent was empty")
    return data


def read_text_stream(lines: Any) -> str:
    """The words of a Responses event stream: the text deltas, or failing that the final `response.completed` message. An error
    event, or a stream with no words, raises."""
    deltas: list[str] = []
    final = ""
    for raw in lines:
        line = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw or "")
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            continue
        try:
            ev = json.loads(data)
        except ValueError:
            continue
        kind = str(ev.get("type") or "")
        if kind in ("response.failed", "error"):
            msg = _event_error(ev)
            raise ChatGPTError(msg, limit=_is_limit(msg))
        if kind == "response.output_text.delta":
            deltas.append(str(ev.get("delta") or ""))
        elif kind == "response.completed":
            for out in (ev.get("response") or {}).get("output") or []:
                for part in out.get("content") or []:
                    if part.get("type") == "output_text" and part.get("text"):
                        final += str(part["text"])
    text = ("".join(deltas) or final).strip()
    if not text:
        raise ChatGPTError("ChatGPT answered without words")
    return text


_LIMIT_WORDS = ("usage limit", "rate limit", "rate_limit", "too many", "quota", "limit reached", "try again in")


def _is_limit(text: str) -> bool:
    low = text.lower()
    return any(w in low for w in _LIMIT_WORDS)


class Login:
    """The saved login and the calls made with it. `http` is `requests` (a test passes its own); `sleep` is `time.sleep`."""

    def __init__(self, store: Any, *, http: Any = None, sleep: Any = None, now: Any = None):
        self.store = store
        self.http = http or requests
        self.sleep = sleep or time.sleep
        self.now = now or (lambda: datetime.now(UTC))
        self._row: dict[str, Any] | None = None

    # ---- the row
    def row(self, fresh: bool = False) -> dict[str, Any] | None:
        if self._row is None or fresh:
            try:
                rows = self.store.table(TABLE).select("*").eq("id", "main").execute().data or []
            except Exception as exc:  # noqa: BLE001 - 058 not applied yet, or the table cannot be read: no login
                log.info("ChatGPT login not read (%s)", str(exc)[:120])
                rows = []
            self._row = rows[0] if rows else None
        return self._row

    def connected(self) -> bool:
        r = self.row()
        return bool(r and ((r.get("auth") or {}).get("tokens") or {}).get("refresh_token"))

    def settings(self) -> dict[str, Any] | None:
        """{enabled, model, max_images} when a login is saved, else None."""
        r = self.row()
        if not r or not self.connected():
            return None
        return {"enabled": bool(r.get("enabled", True)), "model": str(r.get("model") or DEFAULT_MODEL),
                "max_images": max(1, min(8, int(r.get("max_images") or 6)))}

    def _save(self, patch: dict[str, Any]) -> None:
        try:
            self.store.table(TABLE).update({**patch, "updated_at": self.now().isoformat()}).eq("id", "main").execute()
        except Exception as exc:  # noqa: BLE001 - losing a status line must never lose a film
            log.warning("ChatGPT login status not saved: %s", str(exc)[:120])

    def ok(self) -> None:
        """A picture was drawn: the login is proven."""
        stamp = self.now().isoformat()
        self._save({"last_ok_at": stamp, "checked_at": stamp, "last_error": None, "last_error_at": None})

    def failed(self, message: str) -> None:
        self._save({"last_error": _clip(message, 400), "last_error_at": self.now().isoformat()})

    # ---- the tokens
    def refresh(self, force: bool = False) -> tuple[str, str]:
        """(access_token, account_id), refreshed first when it ends within SKEW (or `force`). The new pair is saved at once."""
        r = self.row(fresh=force) or {}
        tokens = dict((r.get("auth") or {}).get("tokens") or {})
        if not tokens.get("refresh_token"):
            raise ChatGPTError("ChatGPT is not connected: log in on Technology → API", auth=True)
        end = expiry(str(tokens.get("access_token") or ""))
        if not end and r.get("access_expires_at"):
            try:
                end = datetime.fromisoformat(str(r["access_expires_at"]).replace("Z", "+00:00"))
            except ValueError:
                end = None
        if tokens.get("access_token") and end and end - self.now() > SKEW and not force:
            return str(tokens["access_token"]), account_of(tokens)
        used = str(tokens["refresh_token"])
        try:
            resp = self.http.post(f"{ISSUER}/oauth/token", json={
                "client_id": CLIENT_ID, "grant_type": "refresh_token", "refresh_token": used,
                "scope": "openid profile email"}, headers={"Content-Type": "application/json"}, timeout=30)
        except requests.RequestException as exc:
            raise ChatGPTError(f"ChatGPT login could not be refreshed: {_clip(exc, 160)}") from exc
        if resp.status_code != 200:
            # a refresh token is single-use: another run may have refreshed it a moment ago, and what it saved is good
            now_row = self.row(fresh=True) or {}
            newer = dict((now_row.get("auth") or {}).get("tokens") or {})
            if newer.get("refresh_token") and newer["refresh_token"] != used:
                return str(newer.get("access_token") or ""), account_of(newer)
            raise ChatGPTError(f"ChatGPT refused the saved login ({resp.status_code}): log in again with `codex login` and paste "
                               f"auth.json again. {_clip(getattr(resp, 'text', ''), 160)}", auth=True)
        body = resp.json()
        access = str(body.get("access_token") or "")
        if not access:
            raise ChatGPTError("ChatGPT's refresh answer had no access token", auth=True)
        tokens.update({k: body[k] for k in ("access_token", "id_token") if body.get(k)})
        tokens["refresh_token"] = str(body.get("refresh_token") or used)
        ends = expiry(access)
        self._save({"auth": {"tokens": tokens}, "access_expires_at": ends.isoformat() if ends else None})
        self._row = {**(self._row or {}), "auth": {"tokens": tokens}}
        return access, account_of(tokens)

    def check(self) -> str:
        """Refresh the login now and say whether ChatGPT accepts it (the 6-hourly API check and a new login call this). A refresh
        is the cheapest real proof there is, and it draws nothing: `last_ok_at` still waits for a real picture."""
        try:
            self.refresh(force=True)
        except ChatGPTError as exc:
            self.failed(str(exc))
            return f"ChatGPT login: {exc}"
        self._save({"checked_at": self.now().isoformat(), "last_error": None, "last_error_at": None})
        return "ChatGPT login: accepted"

    # ---- a picture
    def _body(self, prompt: str, model: str, size: str, variant: int, complexity: str | None = None) -> dict[str, Any]:
        tool: dict[str, Any] = {"type": "image_generation"}
        if variant == 0:
            tool["size"] = size
        if complexity:
            tool["complexity"] = complexity
        body = {"model": model, "instructions": INSTRUCTIONS, "store": False, "stream": True,
                "input": [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": prompt}]}],
                "tools": [tool], "parallel_tool_calls": False}
        if variant < 2:
            body["tool_choice"] = {"type": "image_generation"}
        return body

    def _run(self, body_for: Any, read: Any, timeout: int, last_variant: int) -> Any:
        """One streamed call to the Codex backend, with the refresh-once on 401, one retry on a server error and the body variants
        after a 400 that names what it did not accept. `body_for(variant)` makes the request body, `read(lines)` the answer."""
        variant, renewed, retried = 0, False, False
        while True:
            access, account = self.refresh()
            headers = {"Authorization": f"Bearer {access}", "chatgpt-account-id": account,
                       "OpenAI-Beta": "responses=experimental", "originator": "codex_cli_rs",
                       "User-Agent": "codex_cli_rs/0.0 (semasa)", "Accept": "text/event-stream",
                       "Content-Type": "application/json", "session_id": str(uuid.uuid4())}
            try:
                resp = self.http.post(RESPONSES, headers=headers, json=body_for(variant), stream=True, timeout=(20, timeout))
            except requests.RequestException as exc:
                if retried:
                    raise ChatGPTError(f"ChatGPT could not be reached: {_clip(exc, 160)}") from exc
                retried = True
                self.sleep(3)
                continue
            code = resp.status_code
            if code == 200:
                return read(resp.iter_lines(decode_unicode=True))
            text = _clip(getattr(resp, "text", ""))
            if code in (400, 404) and MODEL_REFUSED.search(text):
                raise ChatGPTError(f"ChatGPT refused the model ({code}): {text}", model=True)
            if code == 401 and not renewed:
                renewed = True
                self.refresh(force=True)
                continue
            if code == 400 and variant < last_variant:
                variant += 1
                continue
            if code in (500, 502, 503, 504) and not retried:
                retried = True
                self.sleep(3)
                continue
            if code in (401, 403):
                raise ChatGPTError(f"ChatGPT refused the login ({code}): {text}", auth=True)
            raise ChatGPTError(f"ChatGPT answered {code}: {text}", limit=(code == 429 or _is_limit(text)))

    # ---- which model this account may use
    def models(self) -> list[str]:
        """The models the account may use with Codex, as ChatGPT lists them ([] when the list cannot be read). When the list
        has no writing model, newer client versions are asked too (CLIENT_VERSIONS): the first list with a writer is the answer,
        else the first list that came back."""
        first: list[str] = []
        for version in CLIENT_VERSIONS:
            got = self._models_for(version)
            if got and not first:
                first = got
            if any(m.startswith("gpt-") and not NOT_A_WRITER.search(m) for m in got):
                self.client_version = version
                return got
            if not got and not first and version == CLIENT_VERSIONS[0]:
                return []                       # the list cannot be read at all: asking again with another version will not help
        return first

    def _models_for(self, version: str) -> list[str]:
        try:
            access, account = self.refresh()
            resp = self.http.get(MODELS, params={"client_version": version}, timeout=20, headers={
                "Authorization": f"Bearer {access}", "chatgpt-account-id": account, "originator": "codex_cli_rs",
                "User-Agent": "codex_cli_rs/0.0 (semasa)", "Accept": "application/json"})
            if resp.status_code != 200:
                return []
            body = resp.json()
        except Exception as exc:  # noqa: BLE001 - the fallback list still applies
            log.info("ChatGPT models not listed (%s)", _clip(exc, 120))
            return []
        items = body.get("models") if isinstance(body, dict) else body
        out: list[str] = []
        for m in items or []:
            slug = m.get("slug") or m.get("id") if isinstance(m, dict) else m
            if isinstance(slug, str) and slug and slug not in out:
                out.append(slug)
        return out

    def _with_model(self, call: Any, model: str) -> Any:
        """`call(model)`, and when ChatGPT refuses that model, the next ones the account allows (its own list first, then
        FALLBACK_MODELS), at most MODEL_TRIES. The first that answers is saved as the model, so the next call starts there."""
        try:
            return call(model)
        except ChatGPTError as exc:
            if not exc.model:
                raise
            first = exc
        listed = self.models()
        tried = [model]
        for m in writer_candidates(listed):
            if m in tried or len(tried) > MODEL_TRIES:
                continue
            tried.append(m)
            try:
                out = call(m)
            except ChatGPTError as exc:
                if exc.model:
                    continue
                raise
            self._save({"model": m})
            if self._row is not None:
                self._row["model"] = m
            log.info("ChatGPT: %s is refused for this account; %s answered and is saved", model, m)
            return out
        lists = f"; the account lists {', '.join(listed[:8])}" if listed else ""
        raise ChatGPTError(f"{first} Tried {', '.join(tried)}{lists}", model=True)

    def draw(self, prompt: str, *, size: str = "1024x1024", model: str = DEFAULT_MODEL, timeout: int = 300) -> bytes:
        """One picture's bytes (PNG or JPEG, whatever ChatGPT sends). Variants run only after a 400 that names what it did not
        accept: the sized forced-tool call first, then without a forced tool, then with the bare tool. A refused model is
        replaced by one the account allows (_with_model). When the image tool refuses a complexity level ("Complexity 'medium' is
        not supported for this image model"), the other levels are asked in turn, and the one that works is remembered for this
        login; when none works the model is treated as refused so the account's next model is tried."""
        def one(m: str, complexity: str | None) -> bytes:
            return self._run(lambda v: self._body(prompt, m, size, v, complexity), read_stream, timeout, 2)

        def call(m: str) -> bytes:
            first = getattr(self, "complexity", None)
            try:
                return one(m, first)
            except ChatGPTError as exc:
                seen = COMPLEXITY_REFUSED.search(str(exc))
                if not seen:
                    raise
                refused, err = {seen.group(1).lower()}, exc
            for level in COMPLEXITIES:
                if level in refused:
                    continue
                try:
                    out = one(m, level)
                except ChatGPTError as exc2:
                    again = COMPLEXITY_REFUSED.search(str(exc2))
                    if not again:
                        raise
                    refused.add(again.group(1).lower())
                    err = exc2
                    continue
                self.complexity = level
                return out
            raise ChatGPTError(f"{err} Tried complexity {', '.join(sorted(refused))}.", model=True)
        return self._with_model(call, model)

    def write(self, system: str, user: str, *, model: str = DEFAULT_MODEL, timeout: int = 180) -> str:
        """Words from ChatGPT through the same login (Wan, 7 Nov 2026: the storyboard "from chatgpt and gemini"): the same
        streamed Responses call with no tools, the answer read off the text events. Raises ChatGPTError, like draw()."""
        def call(m: str) -> str:
            body = {"model": m, "instructions": system, "store": False, "stream": True,
                    "input": [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": user}]}]}
            return self._run(lambda _v: body, read_text_stream, timeout, 0)
        return self._with_model(call, model)

    def read_image(self, system: str, prompt: str, data: bytes, mime: str = "image/jpeg", *, model: str = DEFAULT_MODEL,
                   timeout: int = 180) -> str:
        """What ChatGPT says about one picture (Wan, 8 Nov 2026: "ChatGPT also can read ... read image"): the same streamed
        Responses call as write(), with the picture inline as an `input_image` data URI beside the question."""
        uri = f"data:{mime or 'image/jpeg'};base64,{base64.b64encode(data).decode('ascii')}"

        def call(m: str) -> str:
            body = {"model": m, "instructions": system, "store": False, "stream": True,
                    "input": [{"type": "message", "role": "user", "content": [
                        {"type": "input_text", "text": prompt}, {"type": "input_image", "image_url": uri}]}]}
            return self._run(lambda _v: body, read_text_stream, timeout, 0)
        return self._with_model(call, model)

    def probe_row(self) -> dict[str, Any]:
        """ChatGPT as a robot on the API page (Wanshah 5): the login refreshed, the account's model list, and one short real
        answer from the saved model (or the first one the account allows, which is then saved)."""
        s = self.settings() or {}
        row: dict[str, Any] = {"slug": "chatgpt", "name": "ChatGPT (Wanshah 5)", "role": "primary",
                               "base_url": RESPONSES.rsplit("/", 1)[0],
                               "key_set": self.connected(), "key_last4": "", "model": s.get("model") or DEFAULT_MODEL,
                               "checked_at": self.now().isoformat(), "models": [], "balance": {}, "error": "", "reachable": False,
                               "key_ok": None, "chat_ok": False}
        if not self.connected():
            row["error"] = "not connected: paste auth.json on the API page"
            return row
        started = time.monotonic()
        try:
            self.refresh()
            row.update(key_ok=True, reachable=True)
        except ChatGPTError as exc:
            row.update(key_ok=False if exc.auth else None, error=_clip(exc, 300))
            return row
        row["models"] = self.models()
        row["latency_ms"] = int((time.monotonic() - started) * 1000)
        t0 = time.monotonic()
        try:
            got = self.write("Answer with the single word OK.", "Say OK.", model=row["model"], timeout=60)
            row.update(chat_ok=bool(str(got).strip()), chat_ms=int((time.monotonic() - t0) * 1000),
                       model=str((self._row or {}).get("model") or row["model"]))
        except ChatGPTError as exc:
            row["error"] = _clip(exc, 300)
        row["model_listed"] = (row["model"] in row["models"]) if row["models"] else None
        return row


# --- ChatGPT as a robot of the AI team (Wan, 8 Nov 2026: "make the chatgpt also can read, writing, read and generate image") ---
# the worker jobs it may serve; chat and Telegram reach it through the edge functions
TEAM_JOBS = ("reader", "ideas", "motion")
# a refusal seen this recently keeps it out of the chain (the next probe re-opens it)
REFUSED_STALE = timedelta(hours=13)


def candidate(store: Any, job: str, now: datetime | None = None) -> dict[str, Any] | None:
    """The AI-team candidate for Wan's ChatGPT login, or None: not connected, switched off, not a job it serves, or its last
    check (semasa_api_status) says the account refuses its model. Its `key` IS the Login: llm.py asks ChatGPT through it, so
    the tokens never leave this module."""
    if job not in TEAM_JOBS:
        return None
    try:
        login = Login(store)
        if not login.connected():
            return None
        s = login.settings() or {}
        if not s.get("enabled", True):
            return None
        from . import db
        rows = store.table(db.API_STATUS).select("chat_ok,checked_at,error").eq("slug", "chatgpt").execute().data or []
    except Exception as exc:  # noqa: BLE001 - ChatGPT is an extra: the team without it is the team as it was
        log.info("ChatGPT not considered (%s)", _clip(exc, 120))
        return None
    if rows and rows[0].get("chat_ok") is False and MODEL_REFUSED.search(str(rows[0].get("error") or "")):
        at = rows[0].get("checked_at")
        try:
            when = datetime.fromisoformat(str(at).replace("Z", "+00:00")) if at else None
        except ValueError:
            when = None
        if when is not None and ((now or datetime.now(UTC)) - when) < REFUSED_STALE:
            return None
    model = str(s.get("model") or DEFAULT_MODEL)
    return {"source": "chatgpt", "slug": "chatgpt", "provider": "chatgpt", "base_url": RESPONSES.rsplit("/", 1)[0], "key": login,
            "model": model, "blocked": "", "robot": "W5", "name": "Wanshah 5", "tone": "guest",
            "does": ["read", "write", "read_image", "make_image"]}
