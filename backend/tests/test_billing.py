"""Bil: the worker's rules on a fake store: claiming the outbox, sending once, failing visibly, reminders and expiry."""
from datetime import UTC, datetime

from fakestore import FakeStore

from semasa import billing, db
from semasa.senders import SendError

NOW = datetime(2026, 10, 7, 2, 0, tzinfo=UTC)            # 10:00 MYT
SETTINGS = {"company": {"name": "WS Regulab Solutions", "email": "info@kkmhalalconsultant.com", "signatory": "Wan"},
            "bank": {"name": "Public Bank Berhad", "account_name": "WS Regulab Solutions", "account_no": "3246551604"},
            "email": {"auto_reminders": True, "reminder_days": [-3, 1, 7, 14], "cc_self": True}}
CLIENT = {"name": "Marosia Maison Enterprise", "attention": "Puan Aisyah", "email": "hello@marosia.my"}


def _doc(**kw):
    base = {"id": "d1", "kind": "invoice", "number": "INV-2026-015", "status": "issued", "token": "a" * 32, "client": CLIENT,
            "items": [{"description": "Notification", "qty": 3, "rate": 280}], "total": 840, "currency": "MYR",
            "issue_date": "2026-10-07", "due_date": "2026-11-06", "lang": "bm", "reminders": {"sent": []},
            "updated_at": "2026-10-07T01:00:00+00:00"}
    base.update(kw)
    return base


class FakeSender:
    def __init__(self, fail=None):
        self.sent, self.fail = [], fail

    def upload_pdf(self, url, name):
        return {"name": name, "mimetype": "application/pdf", "s3key": "k/" + name}

    def send(self, **kw):
        if self.fail:
            raise self.fail
        self.sent.append(kw)
        return {"id": "m1", "threadId": "t1"}


def _render(store, doc, settings, now):
    return "https://x/billing/a/INV.pdf", "billing/a/INV.pdf"


def _store(**tables):
    s = FakeStore(**tables)
    s.tables.setdefault(db.SETTINGS, [{"key": "billing", "value": SETTINGS}])
    s.tables.setdefault(db.BILLING_EVENTS, [])
    s.tables.setdefault(db.LOG, [])
    return s


def test_a_send_goes_once_marks_the_document_sent_and_copies_the_company():
    row = {"id": "o1", "doc_id": "d1", "action": "send", "to_email": "hello@marosia.my", "cc": [], "subject": "", "body": "",
           "status": "pending", "attempts": 0, "meta": {}}
    store = _store(**{db.BILLING_DOCS: [_doc()], db.BILLING_OUTBOX: [row]})
    sender = FakeSender()
    counts = billing.process_outbox(store, SETTINGS, sender, NOW, render=_render)
    assert counts == {"sent": 1, "error": 0}
    assert len(sender.sent) == 1
    mail = sender.sent[0]
    assert mail["to"] == "hello@marosia.my" and mail["cc"] == ["info@kkmhalalconsultant.com"]
    assert mail["attachment"]["s3key"].endswith(".pdf")
    assert mail["subject"].startswith("Invois INV-2026-015 daripada")
    assert "3246551604" in mail["html"] and "#bil/" + "a" * 32 in mail["html"]
    doc = store.tables[db.BILLING_DOCS][0]
    assert doc["status"] == "sent" and doc["sent_at"]
    out = store.tables[db.BILLING_OUTBOX][0]
    assert out["status"] == "sent" and out["result"] == {"id": "m1", "threadId": "t1"}
    assert [e["kind"] for e in store.tables[db.BILLING_EVENTS]] == ["send"]
    # a second run finds nothing pending: the mail is never sent twice
    assert billing.process_outbox(store, SETTINGS, sender, NOW, render=_render) == {"sent": 0, "error": 0}
    assert len(sender.sent) == 1


def test_wans_own_subject_and_body_win_and_a_reminder_marks_its_offset():
    row = {"id": "o1", "doc_id": "d1", "action": "reminder", "to_email": "hello@marosia.my", "cc": ["boss@marosia.my"],
           "subject": "Peringatan mesra", "body": "Salam,\nmohon jelaskan.", "status": "pending", "attempts": 0,
           "meta": {"offset": 7}}
    store = _store(**{db.BILLING_DOCS: [_doc(status="sent")], db.BILLING_OUTBOX: [row]})
    sender = FakeSender()
    billing.process_outbox(store, SETTINGS, sender, NOW, render=_render)
    mail = sender.sent[0]
    assert mail["subject"] == "Peringatan mesra" and mail["html"] == "<p>Salam,<br>mohon jelaskan.</p>"
    assert mail["cc"] == ["boss@marosia.my", "info@kkmhalalconsultant.com"]
    assert store.tables[db.BILLING_DOCS][0]["reminders"]["sent"] == [-3, 1, 7]
    assert store.tables[db.BILLING_DOCS][0]["status"] == "sent"               # a reminder never changes the status


def test_a_refusal_is_an_error_row_with_the_reason_and_a_transient_one_tries_again_later():
    rows = [{"id": "o1", "doc_id": "d1", "action": "send", "to_email": "hello@marosia.my", "cc": [], "status": "pending",
             "attempts": 0, "meta": {}}]
    store = _store(**{db.BILLING_DOCS: [_doc()], db.BILLING_OUTBOX: rows})
    refused = FakeSender(fail=SendError("refused", "GMAIL_SEND_EMAIL: bad address"))
    billing.process_outbox(store, SETTINGS, refused, NOW, render=_render)
    out = store.tables[db.BILLING_OUTBOX][0]
    assert out["status"] == "error" and "bad address" in out["error"]
    assert store.tables[db.BILLING_DOCS][0]["status"] == "issued"              # nothing claims it was sent
    assert [e["kind"] for e in store.tables[db.BILLING_EVENTS]] == ["email_failed"]

    class Flaky(FakeSender):
        def upload_pdf(self, url, name):
            raise SendError("transient", "Composio MCP answered 502")
    store2 = _store(**{db.BILLING_DOCS: [_doc()], db.BILLING_OUTBOX: [dict(rows[0])]})
    billing.process_outbox(store2, SETTINGS, Flaky(), NOW, render=_render)
    assert store2.tables[db.BILLING_OUTBOX][0]["status"] == "pending"          # before the send: safe to try again
    assert store2.tables[db.BILLING_OUTBOX][0]["attempts"] == 1


def test_nothing_is_sent_for_a_draft_or_a_void_document_or_without_a_sender():
    row = {"id": "o1", "doc_id": "d1", "action": "send", "to_email": "x@y.my", "cc": [], "status": "pending", "attempts": 0,
           "meta": {}}
    store = _store(**{db.BILLING_DOCS: [_doc(status="void")], db.BILLING_OUTBOX: [dict(row)]})
    sender = FakeSender()
    billing.process_outbox(store, SETTINGS, sender, NOW, render=_render)
    assert not sender.sent and "void" in store.tables[db.BILLING_OUTBOX][0]["error"]
    store = _store(**{db.BILLING_DOCS: [_doc()], db.BILLING_OUTBOX: [dict(row)]})
    billing.process_outbox(store, SETTINGS, None, NOW, render=_render)
    assert "COMPOSIO_CONSUMER_KEY" in store.tables[db.BILLING_OUTBOX][0]["error"]


def test_the_sweep_queues_one_reminder_per_due_invoice_and_expires_old_quotations():
    docs = [_doc(id="late", status="sent", due_date="2026-09-30"),                       # 7 days late: offset 7 due
            _doc(id="fresh", status="sent", due_date="2026-12-01"),                      # nothing due
            _doc(id="never", status="issued", due_date="2026-09-01"),                    # never e-mailed: no reminder
            _doc(id="done", status="sent", due_date="2026-09-30", reminders={"sent": [-3, 1, 7]}),   # 7 sent, 14 not yet due
            _doc(id="noemail", status="sent", due_date="2026-09-30", client={"name": "X"}),
            _doc(id="q", kind="quotation", status="viewed", due_date="2026-10-01", number="QT-2026-009"),
            _doc(id="q2", kind="quotation", status="sent", due_date="2026-10-20", number="QT-2026-010")]
    store = _store(**{db.BILLING_DOCS: docs, db.BILLING_OUTBOX: []})
    counts = billing.sweep(store, SETTINGS, NOW)
    assert counts == {"reminders": 1, "expired": 1}
    out = store.tables[db.BILLING_OUTBOX]
    assert len(out) == 1 and out[0]["doc_id"] == "late" and out[0]["meta"] == {"offset": 7, "auto": True}
    assert {d["id"]: d["status"] for d in store.tables[db.BILLING_DOCS]}["q"] == "expired"
    assert {d["id"]: d["status"] for d in store.tables[db.BILLING_DOCS]}["q2"] == "sent"
    # run again: the queued reminder is not queued twice
    assert billing.sweep(store, SETTINGS, NOW) == {"reminders": 0, "expired": 0}
    # switched off: nothing queued, expiry still happens
    store2 = _store(**{db.BILLING_DOCS: [_doc(id="late", status="sent", due_date="2026-09-30")], db.BILLING_OUTBOX: []})
    off = {**SETTINGS, "email": {"auto_reminders": False}}
    assert billing.sweep(store2, off, NOW) == {"reminders": 0, "expired": 0}


def test_reminder_arithmetic_matches_the_page():
    d = _doc(status="sent", due_date="2026-09-30")
    today = billing.today_myt(NOW)
    assert today.isoformat() == "2026-10-07"
    assert billing.next_reminder(d, [-3, 1, 7, 14], today) == 7
    assert billing.next_reminder(_doc(status="issued", due_date="2026-09-30"), [-3, 1, 7, 14], today) is None
    assert billing.after_reminder(d, 7, [-3, 1, 7, 14], NOW)["sent"] == [-3, 1, 7]
    assert billing.file_name(_doc()) == "INV-2026-015-Marosia-Maison-Enterprise.pdf"
    assert billing.public_link("abc", "https://site.my/") == "https://site.my/#bil/abc"
    assert billing.qr_data_url("https://site.my/#bil/abc").startswith("data:image/png;base64,")


def test_email_words_in_both_languages():
    s, html = billing.email_words(_doc(lang="en"), "send", SETTINGS, "https://x/#bil/a")
    assert s == "Invoice INV-2026-015 from WS Regulab Solutions" and "Dear Puan Aisyah" in html and "3246551604" in html
    s, html = billing.email_words(_doc(kind="quotation", number="QT-2026-010"), "send", SETTINGS, "")
    assert s.startswith("Sebut harga QT-2026-010 daripada") and "sah sehingga" in html and "href" not in html
    s, html = billing.email_words(_doc(lang="en", due_date="2026-09-30", status="sent"), "reminder", SETTINGS, "")
    assert "overdue" in s and "remains unpaid" in html
