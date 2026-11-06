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
DEFAULT_MODEL = "gpt-5"
INSTRUCTIONS = ("You are an image generator. Call the image_generation tool exactly once, using the user's message as the "
                "picture request, then stop. Never answer with text.")
SIZES = {"portrait": "1024x1536", "landscape": "1536x1024", "square": "1024x1024"}


class ChatGPTError(RuntimeError):
    """A ChatGPT call that did not give a picture. `limit`: the plan's allowance is used up (stop asking for this film).
    `auth`: the login itself is refused (Wan has to log in again)."""

    def __init__(self, message: str, *, limit: bool = False, auth: bool = False):
        super().__init__(message)
        self.limit, self.auth = limit, auth


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
            raise ChatGPTError("ChatGPT is not connected: paste auth.json in the Motion tab", auth=True)
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
    def _body(self, prompt: str, model: str, size: str, variant: int) -> dict[str, Any]:
        tool: dict[str, Any] = {"type": "image_generation"}
        if variant == 0:
            tool["size"] = size
        body = {"model": model, "instructions": INSTRUCTIONS, "store": False, "stream": True,
                "input": [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": prompt}]}],
                "tools": [tool], "parallel_tool_calls": False}
        if variant < 2:
            body["tool_choice"] = {"type": "image_generation"}
        return body

    def draw(self, prompt: str, *, size: str = "1024x1024", model: str = DEFAULT_MODEL, timeout: int = 300) -> bytes:
        """One picture's bytes (PNG or JPEG, whatever ChatGPT sends). Variants run only after a 400 that names what it did not
        accept: the sized forced-tool call first, then without a forced tool, then with the bare tool."""
        variant, renewed, retried = 0, False, False
        while True:
            access, account = self.refresh()
            headers = {"Authorization": f"Bearer {access}", "chatgpt-account-id": account,
                       "OpenAI-Beta": "responses=experimental", "originator": "codex_cli_rs",
                       "User-Agent": "codex_cli_rs/0.0 (semasa)", "Accept": "text/event-stream",
                       "Content-Type": "application/json", "session_id": str(uuid.uuid4())}
            try:
                resp = self.http.post(RESPONSES, headers=headers, json=self._body(prompt, model, size, variant),
                                      stream=True, timeout=(20, timeout))
            except requests.RequestException as exc:
                if retried:
                    raise ChatGPTError(f"ChatGPT could not be reached: {_clip(exc, 160)}") from exc
                retried = True
                self.sleep(3)
                continue
            code = resp.status_code
            if code == 200:
                return read_stream(resp.iter_lines(decode_unicode=True))
            text = _clip(getattr(resp, "text", ""))
            if code == 401 and not renewed:
                renewed = True
                self.refresh(force=True)
                continue
            if code == 400 and variant < 2:
                variant += 1
                continue
            if code in (500, 502, 503, 504) and not retried:
                retried = True
                self.sleep(3)
                continue
            if code in (401, 403):
                raise ChatGPTError(f"ChatGPT refused the login ({code}): {text}", auth=True)
            raise ChatGPTError(f"ChatGPT answered {code}: {text}", limit=(code == 429 or _is_limit(text)))
