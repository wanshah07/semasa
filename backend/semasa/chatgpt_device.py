"""Log in to ChatGPT from the Motion tab with a link and a one-time code (Wan, 6 Nov 2026: "can we implement this, and the
code can refresh, link can click in semasa to link with motion"). `python -m semasa.chatgpt_device`, started by .github/workflows/
chatgpt-login.yml when the page asks (supabase/059: semasa_chatgpt_device_start wakes it with repository_dispatch).

The device-code login the Codex CLI itself offers (`codex login --device-auth`). A browser page cannot call auth.openai.com, so
the worker does it, and the page only ever sees the code and the link:

  1. POST /api/accounts/deviceauth/usercode  -> a one-time code and a private device id (the code lives 15 minutes)
  2. the page shows the code beside https://auth.openai.com/codex/device; Wan signs in there and types it
  3. POST /api/accounts/deviceauth/token every few seconds -> 403 `deviceauth_authorization_pending` until he approves, then an
     authorization code and its PKCE verifier
  4. POST /oauth/token (authorization_code) -> the tokens, saved exactly where 058's paste puts them (semasa_chatgpt_auth)

Steps 1 and 3 were probed from a runner-like environment on 6 Nov 2026 (a real code came back; polling it answered 403 pending).
Step 4 needs a real approval, so it is covered by tests with fake replies and proved by Wan's first login.

A new request (the "new code" button) overwrites the row, and the next poll sees it and stops this run; the workflow also cancels
an older run. A run ends when the code is approved, expires, is cancelled or superseded, or fails. Nothing is logged but states:
never a token, never the device id.
"""

from __future__ import annotations

import sys
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import requests

from . import chatgpt_login, db
from .log import get_logger

log = get_logger("semasa.chatgpt_device")

TABLE = "semasa_chatgpt_device"
API = f"{chatgpt_login.ISSUER}/api/accounts/deviceauth"
USERCODE = f"{API}/usercode"
POLL = f"{API}/token"
EXCHANGE = f"{chatgpt_login.ISSUER}/oauth/token"
REDIRECT = f"{chatgpt_login.ISSUER}/deviceauth/callback"
VERIFY_URL = f"{chatgpt_login.ISSUER}/codex/device"
LIFETIME = timedelta(minutes=15)
MIN_INTERVAL = 3
MAX_FAILS = 6                       # consecutive polls that could not reach OpenAI before the run gives up


class DeviceError(RuntimeError):
    pass


def _body(resp: Any) -> dict[str, Any]:
    try:
        data = resp.json()
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001 - an answer that is not JSON is just an answer with no fields
        return {}


def _err_code(resp: Any) -> str:
    err = _body(resp).get("error")
    return str((err.get("code") or err.get("type") or "") if isinstance(err, dict) else err or "").lower()


def _said(resp: Any) -> str:
    return chatgpt_login._clip(getattr(resp, "text", ""), 160)


def _parse(stamp: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return None


def _row(store: Any) -> dict[str, Any] | None:
    rows = store.table(TABLE).select("*").eq("id", "main").execute().data or []
    return rows[0] if rows else None


def _set(store: Any, **patch: Any) -> None:
    store.table(TABLE).update({**patch, "updated_at": datetime.now(UTC).isoformat()}).eq("id", "main").execute()


def request_code(http: Any) -> dict[str, Any]:
    """One new device code: {device_auth_id, user_code, interval, expires_at}."""
    try:
        resp = http.post(USERCODE, json={"client_id": chatgpt_login.CLIENT_ID}, timeout=30)
    except requests.RequestException as exc:
        raise DeviceError(f"OpenAI could not be reached: {chatgpt_login._clip(exc, 160)}") from exc
    data = _body(resp)
    if resp.status_code != 200 or not data.get("device_auth_id") or not data.get("user_code"):
        raise DeviceError(f"OpenAI would not give a login code ({resp.status_code}): {_said(resp)}")
    return data


def exchange(http: Any, approved: dict[str, Any]) -> dict[str, Any]:
    """The tokens for an approved device login."""
    try:
        resp = http.post(EXCHANGE, data={
            "grant_type": "authorization_code", "code": approved.get("authorization_code"), "redirect_uri": REDIRECT,
            "client_id": chatgpt_login.CLIENT_ID, "code_verifier": approved.get("code_verifier")},
            headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30)
    except requests.RequestException as exc:
        raise DeviceError(f"OpenAI could not be reached to finish the login: {chatgpt_login._clip(exc, 160)}") from exc
    data = _body(resp)
    if resp.status_code != 200 or not data.get("access_token") or not data.get("refresh_token"):
        raise DeviceError(f"OpenAI would not finish the login ({resp.status_code}): {_said(resp)}")
    return data


def save_login(store: Any, tokens: dict[str, Any], now: datetime) -> None:
    """The same row 058's paste writes, so Motion cannot tell the two ways in apart. The switch, model and count stay as set."""
    keep = {k: tokens[k] for k in ("id_token", "access_token", "refresh_token") if tokens.get(k)}
    acct = chatgpt_login.account_of(keep)
    if acct:
        keep["account_id"] = acct
    ends = chatgpt_login.expiry(str(keep.get("access_token") or ""))
    email = str(chatgpt_login.claims(str(keep.get("id_token") or "")).get("email") or "")[:120] or None
    stamp = now.isoformat()
    store.table(chatgpt_login.TABLE).upsert({
        "id": "main", "auth": {"tokens": keep}, "account": email, "access_expires_at": ends.isoformat() if ends else None,
        "connected_at": stamp, "checked_at": None, "last_ok_at": None, "last_error": None, "last_error_at": None,
        "updated_at": stamp}, on_conflict="id").execute()


def run(store: Any, *, http: Any = None, sleep: Any = None, now: Any = None) -> str:
    """Get a code, show it, wait for the approval, save the login. Returns a one-line outcome (also printed by the workflow)."""
    http = http or requests
    sleep = sleep or time.sleep
    clock = now or (lambda: datetime.now(UTC))
    row = _row(store)
    if not row or row.get("state") != "requested":
        return "no ChatGPT login was asked for"
    mine = row.get("requested_at")
    try:
        code = request_code(http)
    except DeviceError as exc:
        _set(store, state="error", error=str(exc), device_auth_id=None)
        return f"error: {exc}"
    interval = max(MIN_INTERVAL, int(float(code.get("interval") or 5)))
    ends = _parse(code.get("expires_at")) or (clock() + LIFETIME)
    _set(store, state="waiting", user_code=str(code["user_code"]), verification_url=VERIFY_URL, expires_at=ends.isoformat(),
         device_auth_id=str(code["device_auth_id"]), interval_s=interval, error=None)
    fails = 0
    while True:
        sleep(interval)
        cur = _row(store)
        if not cur or cur.get("requested_at") != mine or cur.get("state") != "waiting":
            return "stopped: a newer request or a cancel replaced this code"
        if clock() >= ends:
            _set(store, state="expired", device_auth_id=None)
            return "expired: the code was not approved in time"
        try:
            resp = http.post(POLL, json={"device_auth_id": code["device_auth_id"], "user_code": code["user_code"]}, timeout=30)
        except requests.RequestException as exc:
            fails += 1
            if fails >= MAX_FAILS:
                _set(store, state="error", device_auth_id=None,
                     error=f"OpenAI could not be reached: {chatgpt_login._clip(exc, 120)}")
                return "error: OpenAI could not be reached while waiting"
            continue
        fails = 0
        if resp.status_code == 200:
            break
        why = _err_code(resp)
        if "slow_down" in why or resp.status_code == 429:
            interval += 5
            continue
        if resp.status_code in (403, 404) or "pending" in why:
            continue                                         # not approved yet: the normal answer for most of the 15 minutes
        msg = f"OpenAI answered {resp.status_code} while waiting: {_said(resp)}"
        _set(store, state="error", error=msg, device_auth_id=None)
        return f"error: {msg}"
    try:
        tokens = exchange(http, _body(resp))
    except DeviceError as exc:
        _set(store, state="error", error=str(exc), device_auth_id=None)
        return f"error: {exc}"
    save_login(store, tokens, clock())
    _set(store, state="done", user_code=None, device_auth_id=None, error=None)
    return "done: ChatGPT is connected"


def main() -> int:
    outcome = run(db.client())
    print(f"ChatGPT login: {outcome}")
    return 1 if outcome.startswith("error") else 0


if __name__ == "__main__":
    sys.exit(main())
