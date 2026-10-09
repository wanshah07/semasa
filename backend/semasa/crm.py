"""CRM (Wan, 9 Oct 2026): the worker's half of marketing e-mail.

The page (web/src/pages/CrmTab.jsx) keeps contacts and campaigns; semasa_crm_queue (supabase/031_crm.sql) turns a campaign
into one outbox row per consenting contact with the words frozen; the database wakes this run (repository_dispatch
'crm_pending') and it
  1. sends every pending outbox row whose campaign is due (send_at <= now and status sending/scheduled), from Wan's own
     Gmail through Composio For You (the Bil sender, backend/semasa/billing.py GmailMCP: ONE call per mail, never retried),
     with the PDPA footer and the unsubscribe link added under the words;
  2. stops at the day's cap (settings.crm.daily_cap, counted from rows sent today) and the run's cap (per_run), and says so;
  3. once an hour, queues the WELCOME campaign for any consenting contact who has not had it yet, and marks a broadcast
     'sent' when nothing of it is left pending.
Rules it never breaks: a contact without consent, or unsubscribed, is never mailed (the queue function skips them and this
run checks again before sending, because consent can be withdrawn between the click and the send); an outbox row is
'working' before the call and 'sent'/'error' after, so a second run finds no 'pending' row for it; every outcome is a
line in semasa_crm_activities and in semasa_log (area 'crm')."""
from __future__ import annotations

import html as html_mod
import os
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import requests

from . import db
from .billing import GmailMCP
from .log import get_logger
from .senders import SendError

log = get_logger("semasa.crm")

SETTINGS_KEY = "crm"
SITE_URL = os.environ.get("SEMASA_SITE_URL", "https://socialmedia.kkmhalalconsultant.com")
MAX_ATTEMPTS = 3
DEFAULTS = {"daily_cap": 200, "per_run": 60, "from_name": "WS Regulab Solutions", "reply_to": "",
            "footer_bm": "Anda menerima e-mel ini kerana anda bersetuju menerima makluman daripada WS Regulab Solutions.",
            "footer_en": "You receive this e-mail because you agreed to hear from WS Regulab Solutions.", "test_to": ""}
MYT = timedelta(hours=8)


def load_settings(store: Any) -> dict[str, Any]:
    rows = store.table(db.SETTINGS).select("key,value").eq("key", SETTINGS_KEY).execute().data or []
    raw = rows[0]["value"] if rows and isinstance(rows[0].get("value"), dict) else {}
    return {**DEFAULTS, **raw}


def company_email(store: Any) -> str:
    rows = store.table(db.SETTINGS).select("key,value").eq("key", "billing").execute().data or []
    v = rows[0]["value"] if rows and isinstance(rows[0].get("value"), dict) else {}
    return str((v.get("company") or {}).get("email") or "")


def unsubscribe_link(token: str, site: str = SITE_URL) -> str:
    return f"{site.rstrip('/')}/#crm/unsub/{token}"


def as_html(body: str) -> str:
    """The campaign body as HTML: left as it is when it already carries tags, otherwise paragraphs from the lines."""
    if re.search(r"<[a-z][^>]*>", body, re.I):
        return body
    paras = [p.strip() for p in re.split(r"\n\s*\n", body.strip()) if p.strip()]
    return "".join("<p>" + html_mod.escape(p).replace("\n", "<br>") + "</p>" for p in paras)


def with_footer(body_html: str, lang: str, token: str, settings: dict[str, Any], site: str = SITE_URL) -> str:
    """The PDPA line and the way out, under every marketing mail. Never on a test send to Wan himself? Also there: the test
    is for seeing exactly what a person gets."""
    words = settings.get("footer_en" if lang == "en" else "footer_bm") or DEFAULTS["footer_en" if lang == "en" else "footer_bm"]
    out = "Unsubscribe" if lang == "en" else "Berhenti melanggan"
    link = unsubscribe_link(token, site)
    return (f"{body_html}<hr style=\"border:0;border-top:1px solid #e2ecf6;margin:24px 0 12px\">"
            f"<p style=\"font-size:12px;color:#64748b\">{html_mod.escape(words)} "
            f"<a href=\"{html_mod.escape(link)}\" style=\"color:#64748b\">{out}</a></p>")


def sent_today(store: Any, now: datetime) -> int:
    """Marketing mails sent since midnight Malaysia time (test sends included: they leave the same mailbox)."""
    midnight = (now + MYT).replace(hour=0, minute=0, second=0, microsecond=0) - MYT
    q = store.table(db.CRM_OUTBOX).select("id").eq("status", "sent").gte("sent_at", midnight.isoformat())
    return len(q.execute().data or [])


def due_campaigns(store: Any, now: datetime) -> dict[str, dict[str, Any]]:
    rows = store.table(db.CRM_CAMPAIGNS).select("*").in_("status", ["scheduled", "sending"]).execute().data or []
    return {c["id"]: c for c in rows if not c.get("send_at") or str(c["send_at"]) <= now.isoformat()}


def claim(store: Any, campaign_ids: list[str], limit: int) -> list[dict[str, Any]]:
    if limit <= 0 or not campaign_ids:
        return []
    q = store.table(db.CRM_OUTBOX).select("*").eq("status", "pending").in_("campaign_id", campaign_ids)
    out = []
    for r in q.order("created_at").limit(limit).execute().data or []:
        attempts = int(r.get("attempts") or 0) + 1
        got = store.table(db.CRM_OUTBOX).update({"status": "working", "attempts": attempts}) \
            .eq("id", r["id"]).eq("status", "pending").execute().data
        if got:
            out.append({**r, "status": "working", "attempts": attempts})
    return out


def activity(store: Any, contact_id: str, kind: str, title: str, detail: dict[str, Any] | None = None) -> None:
    try:
        store.table(db.CRM_ACTIVITIES).insert({"contact_id": contact_id, "kind": kind, "title": title[:300],
                                               "detail": detail or {}}).execute()
    except Exception as exc:                          # the activity line is a record, never the reason a send fails
        log.info("activity not written: %s", str(exc)[:120])


def _fail(store: Any, row: dict[str, Any], exc: Exception, back: str) -> None:
    msg = str(exc) if isinstance(exc, SendError) else f"{type(exc).__name__}: {str(exc)[:400]}"
    store.table(db.CRM_OUTBOX).update({"status": back, "error": msg[:500]}).eq("id", row["id"]).execute()
    db.log_event(store, "warn" if back == "pending" else "error", "crm", "crm.email_failed", f"{row['to_email']}: {msg[:200]}",
                 ref_table=db.CRM_OUTBOX, ref_id=row["id"])


def process_outbox(store: Any, settings: dict[str, Any], sender: GmailMCP | None, now: datetime,
                   site: str = SITE_URL) -> dict[str, int]:
    counts = {"sent": 0, "error": 0, "skipped": 0, "left": 0}
    campaigns = due_campaigns(store, now)
    cap_day = int(settings.get("daily_cap") or DEFAULTS["daily_cap"])
    cap_run = int(settings.get("per_run") or DEFAULTS["per_run"])
    room = min(cap_run, cap_day - sent_today(store, now))
    if room <= 0:
        q = store.table(db.CRM_OUTBOX).select("id").eq("status", "pending").in_("campaign_id", list(campaigns))
        pending = q.execute().data or []
        counts["left"] = len(pending)
        if pending:
            db.log_event(store, "info", "crm", "crm.cap", f"Had harian {cap_day} e-mel dicapai; {len(pending)} menunggu esok")
        return counts
    me = company_email(store)
    for row in claim(store, list(campaigns), room):
        camp = campaigns.get(row["campaign_id"]) or {}
        try:
            if sender is None:
                raise SendError("refused", "no Gmail sender: the COMPOSIO_CONSUMER_KEY secret is not set")
            k_rows = store.table(db.CRM_CONTACTS).select("*").eq("id", row["contact_id"]).execute().data or []
            k = k_rows[0] if k_rows else None
            if not k:
                raise SendError("refused", "the contact no longer exists")
            if not row.get("is_test") and (not k.get("consent") or k.get("unsubscribed_at")):
                store.table(db.CRM_OUTBOX).update({"status": "skipped", "error": "no consent"}).eq("id", row["id"]).execute()
                counts["skipped"] += 1
                continue
            lang = k.get("lang") or camp.get("lang") or "bm"
            body = with_footer(as_html(row["body"]), lang, k["unsub_token"], settings, site)
            result = sender.send(to=row["to_email"], cc=[], subject=row["subject"], html=body, attachment=None, from_email=me)
            store.table(db.CRM_OUTBOX).update({"status": "sent", "sent_at": now.isoformat(), "result": result, "error": ""}) \
                .eq("id", row["id"]).execute()
            counts["sent"] += 1
            if not row.get("is_test"):
                store.table(db.CRM_CONTACTS).update({"last_contact_at": now.isoformat()}).eq("id", k["id"]).execute()
                activity(store, k["id"], "campaign", f"E-mel kempen: {camp.get('name') or row['subject']}",
                         {"campaign_id": row["campaign_id"], "outbox_id": row["id"]})
        except SendError as exc:
            back = "pending" if exc.kind == "transient" and row["attempts"] < MAX_ATTEMPTS else "error"
            _fail(store, row, exc, back)
            counts["error"] += 1
        except Exception as exc:                      # noqa: BLE001 - a crash must leave the row readable, never 'working' for ever
            _fail(store, row, exc, "error")
            counts["error"] += 1
    # tallies on the campaigns, and 'sent' once nothing of a broadcast is left
    for cid, camp in campaigns.items():
        rows = store.table(db.CRM_OUTBOX).select("status,is_test").eq("campaign_id", cid).execute().data or []
        real = [r for r in rows if not r.get("is_test")]
        patch = {"sent_count": sum(1 for r in real if r["status"] == "sent"),
                 "error_count": sum(1 for r in real if r["status"] == "error"), "status": camp["status"]}
        pending = sum(1 for r in real if r["status"] in ("pending", "working"))
        counts["left"] += pending
        if camp.get("kind") == "broadcast":
            patch["status"] = "sending" if pending else "sent"
        store.table(db.CRM_CAMPAIGNS).update(patch).eq("id", cid).execute()
    return counts


def welcome_sweep(store: Any) -> dict[str, int]:
    """A 'welcome' campaign goes, automatically, to every consenting contact who has not had it: the queue function does
    the matching and the freezing, this only calls it for each welcome campaign that is live."""
    counts = {"welcome_queued": 0}
    q = store.table(db.CRM_CAMPAIGNS).select("id").eq("kind", "welcome").in_("status", ["scheduled", "sending"])
    for c in q.execute().data or []:
        try:
            res = store.rpc("semasa_crm_queue", {"p_campaign": c["id"]}).execute().data or {}
            counts["welcome_queued"] += int((res or {}).get("queued") or 0)
        except Exception as exc:                      # noqa: BLE001
            db.log_event(store, "warn", "crm", "crm.welcome_failed", f"{c['id']}: {str(exc)[:200]}")
    return counts


def make_sender(store: Any) -> GmailMCP | None:
    key = os.environ.get("COMPOSIO_CONSUMER_KEY", "").strip()
    if not key:
        return None
    return GmailMCP(key, session=requests.Session(), expect=company_email(store))


def run(store: Any, now: datetime | None = None, sender: GmailMCP | None = None, sweep_too: bool = True) -> dict[str, int]:
    now = now or datetime.now(UTC)
    settings = load_settings(store)
    counts: dict[str, int] = {}
    if sweep_too:
        counts.update(welcome_sweep(store))
    counts.update(process_outbox(store, settings, sender if sender is not None else make_sender(store), now))
    return counts


def main() -> int:
    store = db.client()
    counts = run(store)
    log.info("crm: %s", counts)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as fh:
            fh.write("## CRM\n" + "\n".join(f"- {k}: {v}" for k, v in counts.items()) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
