"""The Semasa Google Sheet (apps-script/Code.gs): one sheet for Semasa, holding the FAQ tabs and the Log tab.

Calls go to the Apps Script web app with a shared token. The database is the source of truth, and the sheet is
a mirror: the FAQ is REPLACED whenever it changes (semasa.faq.sync_sheet), and the log is APPENDED, only the rows
not sent before, tracked by the log's own increasing id on both sides (the script ignores an id it already has,
so two runs sending the same rows cannot duplicate them).

SEMASA_SHEET_URL / SEMASA_SHEET_TOKEN (FAQ_SHEET_URL / FAQ_SHEET_TOKEN, their first names, still work).
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from typing import Any

import requests

from . import db
from .log import get_logger

log = get_logger("semasa.sheet")

LOG_BATCH = 2000
# A row's id is taken when it is written but seen only when its transaction commits, so a row can appear after a
# higher id was already copied. Copying only rows this old closes that gap (every write here commits in well under
# a second); the newest rows simply go with the next run.
SETTLE = timedelta(minutes=2)
LOG_FIELDS = ["id", "at_myt", "level", "area", "event", "title", "actor", "ref_table", "ref_id", "detail"]
MYT = timedelta(hours=8)


class SheetError(RuntimeError):
    """The sheet refused or could not be reached; the message is safe to show (no token in it)."""


def config() -> tuple[str, str]:
    url = (os.environ.get("SEMASA_SHEET_URL") or os.environ.get("FAQ_SHEET_URL") or "").strip()
    token = (os.environ.get("SEMASA_SHEET_TOKEN") or os.environ.get("FAQ_SHEET_TOKEN") or "").strip()
    return url, token


def configured() -> bool:
    return all(config())


def call(action: str, payload: dict[str, Any], *, timeout: int = 90) -> dict[str, Any]:
    url, token = config()
    if not url or not token:
        raise SheetError("not configured (SEMASA_SHEET_URL / SEMASA_SHEET_TOKEN)")
    body = json.dumps({"token": token, "action": action, **payload}, ensure_ascii=False).encode("utf-8")
    try:
        r = requests.post(url, data=body, headers={"Content-Type": "application/json"}, timeout=timeout,
                          allow_redirects=True)
    except requests.RequestException as exc:
        raise SheetError(f"{type(exc).__name__}: cannot reach the sheet") from exc
    try:
        out = r.json()
    except ValueError as exc:
        raise SheetError(f"HTTP {r.status_code}: the sheet did not answer with JSON") from exc
    if not out.get("ok"):
        raise SheetError(str(out.get("error") or "refused"))
    return out


def myt(iso: str | None) -> str:
    try:
        t = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        return (t.astimezone(UTC) + MYT).strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return str(iso or "")


def log_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"id": r["id"], "at_myt": myt(r.get("at")), "level": r.get("level") or "", "area": r.get("area") or "",
             "event": r.get("event") or "", "title": r.get("title") or "", "actor": "Wan" if r.get("actor") else "Bot",
             "ref_table": r.get("ref_table") or "", "ref_id": r.get("ref_id") or "",
             "detail": json.dumps(r.get("detail") or {}, ensure_ascii=False)} for r in rows]


def sync_log(store: Any) -> str:
    """Append the log rows the sheet has not had yet. Never raises; a failure is logged at most every 6 hours
    (a failure logged on every run would itself become an endless stream of rows to send)."""
    if not configured():
        return "log sheet: not configured"
    try:
        got = store.table(db.SETTINGS).select("key,value").eq("key", "log_sheet").limit(1).execute().data or []
        state = dict(got[0]["value"]) if got and isinstance(got[0].get("value"), dict) else {}
        last = int(state.get("last_id") or 0)
        settled = (datetime.now(UTC) - SETTLE).isoformat()
        rows = (store.table(db.LOG).select("*").gt("id", last).lt("at", settled).order("id").limit(LOG_BATCH)
                .execute().data or [])
        if not rows:
            return "log sheet: nothing new"
        out = call("append_log", {"fields": LOG_FIELDS, "rows": log_rows(rows)})
        state.update(last_id=max(int(r["id"]) for r in rows), at=datetime.now(UTC).isoformat(),
                     appended=int(out.get("appended") or 0))
        if got:
            store.table(db.SETTINGS).update({"value": state}).eq("key", "log_sheet").execute()
        else:
            store.table(db.SETTINGS).insert({"key": "log_sheet", "value": state}).execute()
        return f"log sheet: {state['appended']} rows appended"
    except Exception as exc:  # noqa: BLE001 - the sheet is a mirror; it never stops a run
        why = str(exc)[:160] if isinstance(exc, SheetError) else type(exc).__name__
        log.warning("log sheet sync failed: %s", why)
        note_failure(store, "system", "system.sheet_failed", f"Log gagal disalin ke Google Sheet: {why}")
        return f"log sheet: FAILED ({why})"


def note_failure(store: Any, area: str, event: str, title: str, *, hours: int = 6) -> None:
    """Log a sheet failure at most once every `hours` for the same event. The worker runs every 10 minutes when
    work waits; one error row per run would bury the log (and the Log tab mirror) in copies of one fault."""
    try:
        cutoff = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
        recent = (store.table(db.LOG).select("id").eq("event", event).gt("at", cutoff).limit(1).execute().data or [])
        if not recent:
            db.log_event(store, "error", area, event, title)
    except Exception:  # noqa: BLE001
        pass
