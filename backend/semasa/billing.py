"""Bil (Wan, 7 Oct 2026): the worker's half of quotations, invoices and receipts.

The page (web/src/pages/BillingTab.jsx) writes the documents and queues e-mails in semasa_billing_outbox; the database wakes
this run (repository_dispatch 'billing_pending', supabase/028_billing.sql) and it
  1. renders the A4 PDF in Chrome from the SAME template the page shows (web/src/lib/billingDoc.js, served as a module
     next to billing.js the way studio_cards.py serves studio.js), keeps it in semasa-generated and on the document;
  2. sends the e-mail from Wan's own Gmail through Composio For You (the LinkedIn publisher's road: a workbench cell
     fetches the PDF and uploads it for an s3key, then ONE run_composio_tool(GMAIL_SEND_EMAIL), never retried);
  3. once a day queues reminders for invoices past due (settings.billing.email.reminder_days) and marks quotations past
     their validity as expired.
Rules it never breaks: a numbered document's words are never rewritten here; an e-mail that may have gone is never sent
twice (the outbox row is 'working' before the call and 'sent'/'error' after, and a second run finds no 'pending' row);
every outcome is a row in semasa_billing_events and a line in semasa_log (area 'billing')."""
from __future__ import annotations

import base64
import io
import os
import re
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import requests

from . import db
from .log import get_logger
from .senders import _MARK, _POST_CELL, ComposioMCP, SendError, _b64
from .studio_cards import ASSETS, LIB, ORIGIN, _launch, _serve

log = get_logger("semasa.billing")

SETTINGS_KEY = "billing"
MODULES = ("/billing.js", "/billingDoc.js")
DEFAULT_OFFSETS = [-3, 1, 7, 14]
OPEN = ("issued", "sent", "viewed")
SITE_URL = os.environ.get("SEMASA_SITE_URL", "https://socialmedia.kkmhalalconsultant.com")
MAX_ATTEMPTS = 3

PAGE = """<!doctype html><html><head><meta charset="utf-8"></head><body>
<script type="module">
import * as B from "/billingDoc.js"; import * as L from "/billing.js";
window.__bill = {...B, ...L}; window.__ready = true;
</script>
</body></html>"""


# ---- settings and small helpers ------------------------------------------------------------------------------------------
def load_settings(store: Any) -> dict[str, Any]:
    try:
        rows = store.table(db.SETTINGS).select("key,value").eq("key", SETTINGS_KEY).execute().data or []
    except Exception as exc:  # noqa: BLE001
        log.warning("billing settings could not be read: %s", str(exc)[:160])
        return {}
    return (rows[0].get("value") if rows else None) or {}


def today_myt(now: datetime | None = None) -> date:
    now = now or datetime.now(UTC)
    return (now + timedelta(hours=8)).date()


def add_days(iso: str, n: int) -> str:
    return (date.fromisoformat(str(iso)[:10]) + timedelta(days=int(n))).isoformat()


def _ints(xs: Any) -> list[int]:
    return [int(x) for x in (xs or []) if str(x).lstrip("-").isdigit()]


def next_reminder(doc: dict[str, Any], offsets: list[int], today: date) -> int | None:
    """Mirror of billing.js nextReminder: the latest offset that is due and not yet sent, for an invoice that was e-mailed."""
    if doc.get("kind") != "invoice" or not doc.get("due_date") or doc.get("status") not in ("sent", "viewed"):
        return None
    sent = set(_ints((doc.get("reminders") or {}).get("sent")))
    due = [o for o in sorted(set(_ints(offsets))) if o not in sent and today.isoformat() >= add_days(doc["due_date"], o)]
    return due[-1] if due else None


def after_reminder(doc: dict[str, Any], offset: int, offsets: list[int], now: datetime) -> dict[str, Any]:
    sent = set(_ints((doc.get("reminders") or {}).get("sent")))
    sent.update(o for o in _ints(offsets) if o <= offset)
    return {**(doc.get("reminders") or {}), "sent": sorted(sent), "last_at": now.isoformat()}


def public_link(token: str, site: str = SITE_URL) -> str:
    return f"{site.rstrip('/')}/#bil/{token}"


def qr_data_url(text: str) -> str:
    """The QR on the paper opens the public view. segno writes the PNG itself; no Pillow in the path."""
    import segno
    buf = io.BytesIO()
    segno.make(text, error="m").save(buf, kind="png", scale=8, border=1, dark="#0B4D3C")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def events(store: Any, doc_id: str, kind: str, detail: dict[str, Any] | None = None) -> None:
    try:
        store.table(db.BILLING_EVENTS).insert({"doc_id": doc_id, "kind": kind, "detail": detail or {}}).execute()
    except Exception as exc:  # noqa: BLE001
        log.info("event %s not written: %s", kind, str(exc)[:120])


def fmt_date(iso: Any) -> str:
    s = str(iso or "")[:10]
    return f"{s[8:10]}/{s[5:7]}/{s[0:4]}" if len(s) == 10 and s[4] == "-" else s


def file_name(doc: dict[str, Any]) -> str:
    who = re.sub(r"[^\w]+", "-", str((doc.get("client") or {}).get("name") or ""), flags=re.UNICODE).strip("-")[:40]
    return f"{doc.get('number') or 'draft'}{'-' + who if who else ''}.pdf"


# ---- the PDF ---------------------------------------------------------------------------------------------------------------
def _serve_bill(route: Any) -> None:
    path = route.request.url[len(ORIGIN):].split("?", 1)[0]
    if path in ("/", "/index.html"):
        return route.fulfill(status=200, content_type="text/html", body=PAGE)
    if path in MODULES:
        body = (LIB / path[1:]).read_text("utf-8")
        return route.fulfill(status=200, content_type="application/javascript", body=body)
    return _serve(route)                       # /cards/* (fonts, logo), anything else 404


def render_pdf(doc: dict[str, Any], settings: dict[str, Any], *, link: str = "", lang: str | None = None) -> bytes:
    """A4 PDF bytes of the document, drawn by the page's own template in headless Chrome."""
    if not all((LIB / m[1:]).is_file() for m in MODULES) or not (ASSETS / "fonts.css").is_file():
        raise SendError("refused", "the billing template files are missing from this checkout (web/src/lib/billing*.js)")
    from playwright.sync_api import sync_playwright
    opts = {"lang": lang or doc.get("lang") or "en", "logoUrl": f"{ORIGIN}/cards/logo-ink.png",
            "fontsCss": f"{ORIGIN}/cards/fonts.css"}
    if link:
        opts["qr"] = qr_data_url(link)
    with sync_playwright() as p:
        browser = _launch(p)
        try:
            page = browser.new_page()
            page.route(f"{ORIGIN}/**", _serve_bill)
            page.goto(f"{ORIGIN}/index.html")
            page.wait_for_function("window.__ready === true", timeout=30_000)
            html = page.evaluate("([d, s, o]) => window.__bill.documentHtml(d, s, o)", [doc, settings, opts])
            paper = browser.new_page()
            paper.route(f"{ORIGIN}/**", _serve_bill)
            paper.goto(f"{ORIGIN}/index.html")
            paper.set_content(html, wait_until="load")
            paper.evaluate("document.fonts.ready.then(() => true)")
            pdf = paper.pdf(format="A4", print_background=True, prefer_css_page_size=True,
                            margin={"top": "0", "right": "0", "bottom": "0", "left": "0"})
        finally:
            browser.close()
    if not pdf or pdf[:4] != b"%PDF":
        raise SendError("transient", "Chrome did not hand back a PDF")
    return pdf


def with_names(store: Any, doc: dict[str, Any]) -> dict[str, Any]:
    """The paper names its project and, for a receipt, the invoice it settles: both are other rows, read here."""
    out = dict(doc)
    try:
        if doc.get("project_id") and not doc.get("project"):
            rows = store.table(db.PROJECTS).select("name").eq("id", doc["project_id"]).execute().data or []
            if rows:
                out["project"] = rows[0].get("name") or ""
        if doc.get("parent_id") and not doc.get("parent_number"):
            rows = store.table(db.BILLING_DOCS).select("number").eq("id", doc["parent_id"]).execute().data or []
            if rows:
                out["parent_number"] = rows[0].get("number") or ""
    except Exception as exc:  # noqa: BLE001 - a missing name never stops the paper
        log.info("names for %s not read: %s", doc.get("number"), str(exc)[:120])
    return out


def ensure_pdf(store: Any, doc: dict[str, Any], settings: dict[str, Any], now: datetime) -> tuple[str, str]:
    """The document's PDF, rendered now if it is missing or older than the document's last change. Returns (url, path)."""
    fresh = doc.get("pdf_url") and doc.get("pdf_at") and str(doc.get("pdf_at")) >= str(doc.get("updated_at") or "")
    if fresh:
        return doc["pdf_url"], doc["pdf_path"]
    pdf = render_pdf(with_names(store, doc), settings, link=public_link(doc["token"]))
    path = f"billing/{doc['token']}/{file_name(doc)}"
    url = db.upload_generated(store, path, pdf, "application/pdf")
    stamp = now.isoformat()
    store.table(db.BILLING_DOCS).update({"pdf_url": url, "pdf_path": path, "pdf_at": stamp}).eq("id", doc["id"]).execute()
    doc.update(pdf_url=url, pdf_path=path, pdf_at=stamp)
    events(store, doc["id"], "pdf", {"path": path})
    return url, path


# ---- Gmail through Composio For You ----------------------------------------------------------------------------------------
_PDF_CELL = """
import json, base64, os, requests
def _semasa():
    u, name = json.loads(base64.b64decode("{spec}").decode())
    os.makedirs("/home/user/semasa", exist_ok=True)
    r = requests.get(u, timeout=60)
    ct = (r.headers.get("content-type") or "").split(";")[0].strip()
    if r.status_code != 200 or not r.content[:4] == b"%PDF":
        return {{"ok": False, "kind": "refused", "message": f"the PDF answered {{r.status_code}} {{ct or 'no type'}}: {{u}}"}}
    path = "/home/user/semasa/" + name
    with open(path, "wb") as fh:
        fh.write(r.content)
    res, err = upload_local_file(path)
    if err:
        return {{"ok": False, "kind": "transient", "message": f"PDF upload failed: {{err}}"}}
    key = (res or {{}}).get("s3key") or ((res or {{}}).get("data") or {{}}).get("s3key")
    if not key:
        return {{"ok": False, "kind": "transient", "message": f"PDF upload gave no s3key: {{str(res)[:200]}}"}}
    return {{"ok": True, "file": {{"name": name, "mimetype": "application/pdf", "s3key": key}}}}
try:
    _r = _semasa()
except Exception as _e:
    _r = {{"ok": False, "kind": "transient", "message": f"{{type(_e).__name__}}: {{_e}}"}}
print("{mark}" + json.dumps(_r))
"""


def _dig(obj: Any, key: str) -> Any:
    """The first value under `key` anywhere in the answer (Composio nests id/threadId differently per tool version)."""
    if isinstance(obj, dict):
        if key in obj and isinstance(obj[key], (str, int)):
            return obj[key]
        for v in obj.values():
            found = _dig(v, key)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = _dig(v, key)
            if found is not None:
                return found
    return None


class GmailMCP(ComposioMCP):
    """Wan's Gmail (info@kkmhalalconsultant.com) through Composio For You: attach the PDF, send once."""

    def __init__(self, consumer_key: str, session: Any = None, account_id: str | None = None, expect: str = ""):
        super().__init__(consumer_key, session=session)
        self.account_id = account_id
        self.expect = expect          # the address the connection must be, when the settings name one

    def account(self) -> str:
        if self.account_id:
            return self.account_id
        body = self._twice(lambda: self._tool("COMPOSIO_MANAGE_CONNECTIONS",
                                              {"toolkits": [{"name": "gmail", "action": "list"}]}))
        accts = (((body.get("data") or {}).get("results") or {}).get("gmail") or {}).get("accounts") or []
        live = [a for a in accts if str(a.get("status", "")).lower() == "active"]
        if self.expect:
            mine = [a for a in live if str((a.get("user_info") or {}).get("email", "")).lower() == self.expect.lower()]
            live = mine or live
        if len(live) != 1:
            raise SendError("refused", f"Composio For You: expected exactly 1 active Gmail connection, found {len(live)}")
        self.account_id = live[0]["id"]
        return self.account_id

    def upload_pdf(self, url: str, name: str) -> dict[str, str]:
        r = self._cell(_PDF_CELL.format(spec=_b64([url, name]), mark=_MARK), "Semasa: attach the billing PDF")
        if not r.get("ok"):
            raise SendError(r.get("kind") or "transient", str(r.get("message") or "PDF upload failed"))
        return r["file"]

    def trash(self, message_id: str) -> None:
        """Move one sent mail to Gmail's Trash (recoverable there for 30 days). Used by the CRM's delete (crm.py)."""
        account = f', account="{self.account()}"'
        r = self._cell(_POST_CELL.format(args=_b64({"message_id": message_id, "user_id": "me"}), tool="GMAIL_MOVE_TO_TRASH",
                                         account=account, mark=_MARK), "Semasa: move a sent e-mail to Trash")
        if r.get("err"):
            raise SendError("refused", f"GMAIL_MOVE_TO_TRASH: {str(r['err'])[:300]}")
        res = r.get("res") or {}
        if isinstance(res, dict) and res.get("successful") is False:
            msg = str(res.get("error") or res)
            # a mail already gone from the mailbox is the outcome asked for, not a failure
            if "404" in msg or "not found" in msg.lower():
                return
            raise SendError("refused", f"GMAIL_MOVE_TO_TRASH: {msg[:300]}")

    def send(self, *, to: str, cc: list[str], subject: str, html: str, attachment: dict[str, str] | None,
             from_email: str = "") -> dict[str, Any]:
        """ONE call, never retried: a timeout here may already have sent the mail."""
        args: dict[str, Any] = {"recipient_email": to, "subject": subject, "body": html, "is_html": True, "user_id": "me"}
        if cc:
            args["cc"] = cc
        if attachment:
            args["attachment"] = attachment
        if from_email:
            args["from_email"] = from_email
        account = f', account="{self.account()}"'
        r = self._cell(_POST_CELL.format(args=_b64(args), tool="GMAIL_SEND_EMAIL", account=account, mark=_MARK),
                       "Semasa: send the billing e-mail")
        if r.get("err"):
            raise SendError("refused", f"GMAIL_SEND_EMAIL: {str(r['err'])[:300]}")
        res = r.get("res") or {}
        if isinstance(res, dict) and res.get("successful") is False:
            raise SendError("refused", f"GMAIL_SEND_EMAIL: {str(res.get('error') or res)[:300]}")
        return {"id": _dig(res, "id"), "threadId": _dig(res, "threadId")}


# ---- the e-mail's words (mirror of billing.js emailFor; the page's copy is the one Wan reads and may edit) ------------------
KIND_WORDS = {"quotation": ("Sebut harga", "Quotation"), "invoice": ("Invois", "Invoice"), "receipt": ("Resit", "Receipt")}


def _send_words(doc: dict[str, Any], lang: str, total: str, due: str, bank_line: str, company: str) -> tuple[str, str, str]:
    number = doc.get("number") or ""
    kind = KIND_WORDS[doc["kind"]][1 if lang == "en" else 0]
    if lang == "en":
        subject = f"{kind} {number} from {company}"
        lead = {
            "quotation": f"Please find attached our quotation <b>{number}</b> for <b>{total}</b>, valid until <b>{due}</b>.",
            "invoice": f"Please find attached invoice <b>{number}</b> for <b>{total}</b>, due on <b>{due}</b>.",
            "receipt": f"Thank you for your payment. Receipt <b>{number}</b> for <b>{total}</b> is attached.",
        }[doc["kind"]]
        extra = {
            "quotation": "Reply to this e-mail to accept, or let us know if anything should change.",
            "invoice": f"Payment by bank transfer to {bank_line}, quoting the invoice number." if bank_line else "",
            "receipt": "",
        }[doc["kind"]]
    else:
        subject = f"{kind} {number} daripada {company}"
        lead = {
            "quotation": f"Dilampirkan sebut harga <b>{number}</b> berjumlah <b>{total}</b>, sah sehingga <b>{due}</b>.",
            "invoice": f"Dilampirkan invois <b>{number}</b> berjumlah <b>{total}</b>, perlu dijelaskan sebelum <b>{due}</b>.",
            "receipt": f"Terima kasih atas bayaran anda. Resit <b>{number}</b> berjumlah <b>{total}</b> dilampirkan.",
        }[doc["kind"]]
        extra = {
            "quotation": "Balas e-mel ini untuk menerima, atau maklumkan jika ada yang perlu diubah.",
            "invoice": (f"Bayaran melalui pindahan bank ke {bank_line}, dengan nombor invois sebagai rujukan."
                        if bank_line else ""),
            "receipt": "",
        }[doc["kind"]]
    return subject, lead, extra


def _reminder_words(doc: dict[str, Any], lang: str, total: str, due: str, bank_line: str) -> tuple[str, str, str]:
    number = doc.get("number") or ""
    late = (today_myt() - date.fromisoformat(str(doc["due_date"])[:10])).days if doc.get("due_date") else 0
    if lang == "en":
        days = f"{late} day{'s' if late != 1 else ''}"
        subject = f"Reminder: invoice {number} is {days} overdue" if late > 0 else f"Reminder: invoice {number} is due on {due}"
        lead = (f"A gentle reminder that invoice <b>{number}</b> for <b>{total}</b> was due on <b>{due}</b> and remains unpaid."
                if late > 0 else f"A gentle reminder that invoice <b>{number}</b> for <b>{total}</b> is due on <b>{due}</b>.")
        extra = ((f"Bank transfer: {bank_line}. " if bank_line else "")
                 + "If payment has already been made, please ignore this message.")
    else:
        subject = (f"Peringatan: invois {number} lewat {late} hari" if late > 0
                   else f"Peringatan: invois {number} perlu dijelaskan sebelum {due}")
        lead = (f"Peringatan mesra bahawa invois <b>{number}</b> berjumlah <b>{total}</b> sepatutnya dijelaskan pada "
                f"<b>{due}</b> dan masih belum diterima." if late > 0
                else f"Peringatan mesra bahawa invois <b>{number}</b> berjumlah <b>{total}</b> perlu dijelaskan sebelum "
                     f"<b>{due}</b>.")
        extra = ((f"Pindahan bank: {bank_line}. " if bank_line else "")
                 + "Jika bayaran sudah dibuat, abaikan mesej ini.")
    return subject, lead, extra


def email_words(doc: dict[str, Any], action: str, settings: dict[str, Any], link: str) -> tuple[str, str]:
    """Subject and HTML body in the document's language."""
    lang = "en" if doc.get("lang") == "en" else "bm"
    co, bank = settings.get("company") or {}, settings.get("bank") or {}
    c = doc.get("client") or {}
    who = c.get("attention") or c.get("name") or ""
    total = f"{doc.get('currency') or 'MYR'} {float(doc.get('total') or 0):,.2f}"
    due = fmt_date(doc.get("due_date"))
    company = co.get("name") or "WS Regulab Solutions"
    bank_line = ""
    if bank.get("account_no"):
        bank_line = f"{bank.get('name', '')} · {bank.get('account_name', '')} · <b>{bank.get('account_no', '')}</b>"
    if action == "reminder":
        subject, lead, extra = _reminder_words(doc, lang, total, due, bank_line)
    else:
        subject, lead, extra = _send_words(doc, lang, total, due, bank_line, company)
    hi = f"Dear {who}," if lang == "en" else f"Salam sejahtera {who},"
    view = "View online" if lang == "en" else "Lihat dalam talian"
    regards = "Kind regards," if lang == "en" else "Sekian, terima kasih."
    reg = f" · {co['reg_no']}" if co.get("reg_no") else ""
    phone = f" · {co['phone']}" if co.get("phone") else ""
    sign = f"<b>{co.get('signatory', '')}</b><br>{company}{reg}<br>{co.get('email', '')}{phone}"
    paras = [p for p in (hi, lead, extra, f'<a href="{link}">{view}</a>' if link else "", regards, sign) if p]
    html = ('<div style="font:14px/1.5 -apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#10222f">'
            + "".join(f"<p>{p}</p>" for p in paras) + "</div>")
    return subject, html


# ---- the outbox ------------------------------------------------------------------------------------------------------------
def claim(store: Any, limit: int = 20) -> list[dict[str, Any]]:
    q = store.table(db.BILLING_OUTBOX).select("*").eq("status", "pending").order("created_at").limit(limit)
    rows = q.execute().data or []
    out = []
    for r in rows:
        attempts = int(r.get("attempts") or 0) + 1
        got = store.table(db.BILLING_OUTBOX).update({"status": "working", "attempts": attempts}) \
            .eq("id", r["id"]).eq("status", "pending").execute().data
        if got:
            out.append({**r, "status": "working", "attempts": attempts})
    return out


def _fail(store: Any, row: dict[str, Any], doc: dict[str, Any] | None, exc: Exception, back: str, level: str) -> None:
    msg = str(exc) if isinstance(exc, SendError) else f"{type(exc).__name__}: {str(exc)[:400]}"
    store.table(db.BILLING_OUTBOX).update({"status": back, "error": msg[:500]}).eq("id", row["id"]).execute()
    if doc:
        events(store, doc["id"], "email_failed", {"action": row["action"], "to": row["to_email"], "error": msg[:300]})
    db.log_event(store, level, "billing", "billing.email_failed", f"{(doc or {}).get('number') or row['doc_id']}: {msg[:200]}",
                 ref_table=db.BILLING_DOCS, ref_id=row["doc_id"])


def process_outbox(store: Any, settings: dict[str, Any], sender: GmailMCP | None, now: datetime,
                   render: Any = ensure_pdf) -> dict[str, int]:
    counts = {"sent": 0, "error": 0}
    co = settings.get("company") or {}
    email = settings.get("email") or {}
    offsets = _ints(email.get("reminder_days")) or DEFAULT_OFFSETS
    for row in claim(store):
        doc_rows = store.table(db.BILLING_DOCS).select("*").eq("id", row["doc_id"]).execute().data or []
        doc = doc_rows[0] if doc_rows else None
        try:
            if not doc:
                raise SendError("refused", "the document no longer exists")
            if doc.get("status") in ("draft", "void"):
                raise SendError("refused", f"{doc.get('number') or 'this draft'} is {doc.get('status')}: nothing is sent for it")
            if sender is None:
                raise SendError("refused", "no Gmail sender: the COMPOSIO_CONSUMER_KEY secret is not set")
            link = public_link(doc["token"])
            url, _path = render(store, doc, settings, now)
            attachment = sender.upload_pdf(url, file_name(doc))
            subject, html = email_words(doc, row["action"], settings, link)
            subject = row.get("subject") or subject
            if row.get("body"):
                html = row["body"] if "<" in row["body"] else "<p>" + row["body"].replace("\n", "<br>") + "</p>"
            cc = list(row.get("cc") or [])
            me = str(co.get("email") or "")
            if email.get("cc_self") and me and me not in cc and me.lower() != str(row["to_email"]).lower():
                cc.append(me)
            result = sender.send(to=row["to_email"], cc=cc, subject=subject, html=html, attachment=attachment, from_email=me)
            patch: dict[str, Any] = {}
            if row["action"] == "send":
                patch["sent_at"] = now.isoformat()
                if doc.get("status") == "issued":
                    patch["status"] = "sent"
            else:
                offset = (row.get("meta") or {}).get("offset")
                if offset is not None:
                    patch["reminders"] = after_reminder(doc, int(offset), offsets, now)
            if patch:
                store.table(db.BILLING_DOCS).update(patch).eq("id", doc["id"]).execute()
            store.table(db.BILLING_OUTBOX).update({"status": "sent", "error": "", "result": result}).eq("id", row["id"]).execute()
            detail = {"to": row["to_email"], "cc": cc, "subject": subject, "gmail": result}
            if row["action"] == "reminder":
                detail["offset"] = (row.get("meta") or {}).get("offset")
            events(store, doc["id"], row["action"], detail)
            db.log_event(store, "info", "billing", f"billing.{row['action']}", f"{doc.get('number')}: e-mel ke {row['to_email']}",
                         ref_table=db.BILLING_DOCS, ref_id=doc["id"], detail={"subject": subject})
            counts["sent"] += 1
        except SendError as exc:
            # a transient refusal BEFORE the send call may try again on the next run; the send itself is never retried
            # (the row is 'working' through the call, so a timeout there ends as 'error' and Wan decides)
            back = "pending" if exc.kind == "transient" and int(row.get("attempts") or 1) < MAX_ATTEMPTS else "error"
            _fail(store, row, doc, exc, back, "warn")
            counts["error"] += 1
        except Exception as exc:  # noqa: BLE001 - one bad row never stops the others
            _fail(store, row, doc, exc, "error", "error")
            counts["error"] += 1
    return counts


# ---- the daily sweep: reminders and expiry -----------------------------------------------------------------------------
def sweep(store: Any, settings: dict[str, Any], now: datetime) -> dict[str, int]:
    counts = {"reminders": 0, "expired": 0}
    today = today_myt(now)
    email = settings.get("email") or {}
    offsets = _ints(email.get("reminder_days")) or DEFAULT_OFFSETS
    docs = store.table(db.BILLING_DOCS).select("*").in_("status", list(OPEN)).execute().data or []
    pending = store.table(db.BILLING_OUTBOX).select("doc_id,action").in_("status", ["pending", "working"]).execute().data or []
    queued = {(p["doc_id"], p["action"]) for p in pending}
    for d in docs:
        if d.get("kind") == "quotation" and d.get("due_date") and str(d["due_date"])[:10] < today.isoformat():
            store.table(db.BILLING_DOCS).update({"status": "expired"}).eq("id", d["id"]).execute()
            events(store, d["id"], "expired", {"valid_until": d["due_date"]})
            counts["expired"] += 1
            continue
        if not email.get("auto_reminders", True):
            continue
        offset = next_reminder(d, offsets, today)
        to = str((d.get("client") or {}).get("email") or "").strip()
        if offset is None or "@" not in to or (d["id"], "reminder") in queued:
            continue
        store.table(db.BILLING_OUTBOX).insert({"doc_id": d["id"], "action": "reminder", "to_email": to, "status": "pending",
                                               "lang": d.get("lang") or "en", "meta": {"offset": offset, "auto": True}}).execute()
        counts["reminders"] += 1
    return counts


def make_sender(settings: dict[str, Any]) -> GmailMCP | None:
    key = os.environ.get("COMPOSIO_CONSUMER_KEY", "").strip()
    if not key:
        return None
    return GmailMCP(key, session=requests.Session(), expect=str((settings.get("company") or {}).get("email") or ""))


def run(store: Any, now: datetime | None = None, sender: GmailMCP | None = None, sweep_too: bool = True) -> dict[str, int]:
    now = now or datetime.now(UTC)
    settings = load_settings(store)
    counts: dict[str, int] = {}
    if sweep_too:
        counts.update(sweep(store, settings, now))
    counts.update(process_outbox(store, settings, sender if sender is not None else make_sender(settings), now))
    return counts


def main() -> int:
    store = db.client()
    counts = run(store)
    log.info("billing: %s", counts)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as fh:
            fh.write("## Bil\n" + "\n".join(f"- {k}: {v}" for k, v in counts.items()) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
