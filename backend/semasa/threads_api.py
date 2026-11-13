"""Wan's own Threads app (supabase/080): read public posts by keyword straight from Meta, for the viral-post feed.

Composio's shared Threads app answers "Application does not have permission for this action" to a keyword search, so the sweep
(intake.do_community) asks this module when Composio returns nothing. Meta's own documentation (read 13 Nov 2026):
  GET https://graph.threads.com/v1.0/keyword_search?q=&search_type=TOP&since=&limit=&fields=&access_token=
  threads_keyword_search is required; WITHOUT its approval "the search is performed only on posts owned by the authenticated
  user", after approval public posts are searchable. So a result made only of the connected account's own posts is NOT a viral
  feed: it is reported as "not approved yet" and no row is made from it.
  Long-lived token: 60 days; GET /refresh_access_token?grant_type=th_refresh_token&access_token= works when the token is at least
  24 hours old and not expired. A query with no results does not count toward the 2,200 a day.

The page can never read the app secret or the token back (no policy on semasa_threads_auth); this is the only reader.
Nothing here posts, approves or drafts a thing.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import requests

from .log import get_logger

log = get_logger("semasa.threads_api")

TABLE = "semasa_threads_auth"
BASE = "https://graph.threads.com"
FIELDS = "id,text,username,permalink,timestamp,media_type"
REFRESH_WITHIN = timedelta(days=14)        # a token is renewed once it has this long or less left
TIMEOUT = 20


def _parse(v: Any) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None


def _reason(resp: requests.Response) -> str:
    """What Meta said, short, with no token in it."""
    try:
        err = (resp.json() or {}).get("error") or {}
        text = f"{err.get('message') or resp.reason} (code {err.get('code')}, subcode {err.get('error_subcode')})"
    except ValueError:
        text = f"HTTP {resp.status_code} {resp.reason}"
    return text[:240]


def load(store: Any) -> dict[str, Any] | None:
    """The saved connection, or None when there is none or Wan switched it off."""
    try:
        rows = store.table(TABLE).select("*").eq("id", "main").limit(1).execute().data or []
    except Exception as exc:  # noqa: BLE001 - 080 not applied yet is normal, not an error
        log.info("threads connection not read (%s)", str(exc)[:120])
        return None
    return rows[0] if rows and rows[0].get("enabled") is not False else None


def _note(store: Any, **fields: Any) -> None:
    try:
        store.table(TABLE).update({**fields, "updated_at": datetime.now(UTC).isoformat()}).eq("id", "main").execute()
    except Exception as exc:  # noqa: BLE001 - a status that cannot be written must not stop the sweep
        log.warning("threads status not written: %s", str(exc)[:120])


def refresh_if_due(store: Any, row: dict[str, Any], now: datetime | None = None, http: Any = requests) -> dict[str, Any]:
    """Renew the long-lived token when it has two weeks or less left. Meta refuses a token younger than 24 hours; that refusal is
    written as the last error and the old token is kept."""
    now = now or datetime.now(UTC)
    ends = _parse(row.get("expires_at"))
    if not ends or ends - now > REFRESH_WITHIN or ends <= now:
        return row
    try:
        resp = http.get(f"{BASE}/refresh_access_token",
                        params={"grant_type": "th_refresh_token", "access_token": row["access_token"]}, timeout=TIMEOUT)
        if resp.status_code != 200:
            _note(store, last_error=f"token refresh refused: {_reason(resp)}", last_error_at=now.isoformat())
            return row
        data = resp.json()
        token = str(data.get("access_token") or "")
        if not token:
            return row
        ends = now + timedelta(seconds=int(data.get("expires_in") or 60 * 86400))
        _note(store, access_token=token, expires_at=ends.isoformat())
        return {**row, "access_token": token, "expires_at": ends.isoformat()}
    except Exception as exc:  # noqa: BLE001
        _note(store, last_error=f"token refresh failed: {str(exc)[:160]}", last_error_at=now.isoformat())
        return row


def account(store: Any, row: dict[str, Any], http: Any = requests) -> tuple[str, str]:
    """(username, error). Reads the account the token belongs to once, then keeps it."""
    if row.get("username"):
        return str(row["username"]), ""
    try:
        resp = http.get(f"{BASE}/v1.0/me", params={"fields": "id,username", "access_token": row["access_token"]},
                        timeout=TIMEOUT)
        if resp.status_code != 200:
            err = f"Threads refused the token: {_reason(resp)}"
            _note(store, last_error=err, last_error_at=datetime.now(UTC).isoformat())
            return "", err
        data = resp.json()
        _note(store, username=data.get("username"), user_id=str(data.get("id") or ""),
              checked_at=datetime.now(UTC).isoformat(), last_error=None, last_error_at=None)
        return str(data.get("username") or ""), ""
    except Exception as exc:  # noqa: BLE001
        return "", f"Threads could not be reached: {str(exc)[:160]}"


def search(row: dict[str, Any], query: str, since: int, limit: int, http: Any = requests) -> tuple[list[dict[str, Any]], str]:
    """One keyword, top posts since a Unix time. (posts, error)."""
    try:
        resp = http.get(f"{BASE}/v1.0/keyword_search",
                        params={"q": query, "search_type": "TOP", "since": since, "limit": max(1, min(100, limit)),
                                "fields": FIELDS, "access_token": row["access_token"]}, timeout=TIMEOUT)
    except Exception as exc:  # noqa: BLE001
        return [], f"Threads could not be reached: {str(exc)[:160]}"
    if resp.status_code != 200:
        return [], f"Threads search refused: {_reason(resp)}"
    return list((resp.json() or {}).get("data") or []), ""


def fetch(store: Any, cfg: dict[str, Any], now: datetime | None = None, http: Any = requests) -> tuple[list[dict[str, Any]], str]:
    """Public Threads posts for the sweep's keywords, in the shape community.thread_candidates reads. (posts, error).
    ([], "") when no connection is saved. The connected account's own posts are never returned as viral posts."""
    row = load(store)
    if not row:
        return [], ""
    now = now or datetime.now(UTC)
    row = refresh_if_due(store, row, now, http)
    me, err = account(store, row, http)
    if err:
        return [], err
    th = cfg.get("threads") or {}
    queries = [q for q in (th.get("queries") or []) if str(q).strip()][:8]
    hours = max(6, min(14 * 24, int(th.get("hours") or 72)))
    limit = max(1, min(25, int(th.get("max_results") or 8)))
    since = int((now - timedelta(hours=hours)).timestamp())
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    own = 0
    for q in queries:
        posts, err = search(row, str(q), since, limit, http)
        if err:
            _note(store, last_error=err, last_error_at=now.isoformat())
            return out, err
        for p in posts:
            pid = str(p.get("id") or "")
            if not pid or pid in seen:
                continue
            seen.add(pid)
            if me and str(p.get("username") or "").lower() == me.lower():
                own += 1
                continue
            out.append({"id": pid, "text": str(p.get("text") or "")[:500], "permalink": p.get("permalink"),
                        "timestamp": p.get("timestamp"), "username": p.get("username")})
    if own and not out:
        err = ("Threads searched only this account's own posts: threads_keyword_search is not approved for the app yet "
               "(Meta App Review), so there is no public search")
        _note(store, last_error=err, last_error_at=now.isoformat())
        return [], err
    if out:
        _note(store, last_ok_at=now.isoformat(), last_error=None, last_error_at=None)
    return out, ""
