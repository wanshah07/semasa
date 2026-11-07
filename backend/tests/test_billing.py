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


def test_a_bucket_that_refuses_pdfs_says_which_sql_to_run(monkeypatch):
    """17 Oct 2026: Storage answered 415 invalid_mime_type; the timeline showed a raw StorageApiError and no way out."""
    monkeypatch.setattr(billing, "render_pdf", lambda *a, **k: b"%PDF-1.4 x")

    def refuse(*a, **k):
        raise Exception("StorageApiError: {'statusCode': 415, 'error': 'invalid_mime_type', "
                        "'message': 'mime type application/pdf is not supported'}")
    monkeypatch.setattr(db, "upload_generated", refuse)
    store = _store(**{db.BILLING_DOCS: [_doc()]})
    try:
        billing.ensure_pdf(store, _doc(), SETTINGS, NOW)
    except SendError as exc:
        assert exc.kind == "refused" and "039_generated_pdf.sql" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("a refused upload must not pass")
    assert store.tables[db.BILLING_DOCS][0].get("pdf_url") is None


# ---- businesses (supabase/066): each document is worded and sent under its own business ------------------------------------

def test_a_valorith_document_is_worded_with_valorith_and_never_claims_a_from_the_gmail_cannot_send_as():
    company = {**SETTINGS["company"], "name": "Valorith", "email": "hello@valorith.my", "signatory": "Wan"}
    valorith = {**SETTINGS, "company": company,
                "email": {**(SETTINGS.get("email") or {}), "cc_self": True}}
    row = {"id": "o1", "doc_id": "d1", "action": "send", "to_email": "buyer@shop.my", "cc": [], "subject": "", "body": "",
           "status": "pending", "attempts": 0, "meta": {}}
    store = _store(**{db.BILLING_DOCS: [_doc(business_id="valorith")], db.BILLING_OUTBOX: [row]})
    sender = FakeSender()
    sender.expect = "info@kkmhalalconsultant.com"          # the one Gmail connection
    seen = []

    def render(st, d, cfg, now):
        seen.append(cfg["company"]["name"])
        return "https://x/a.pdf", "a.pdf"
    counts = billing.process_outbox(store, SETTINGS, sender, NOW, businesses={"valorith": valorith}, render=render)
    assert counts == {"sent": 1, "error": 0}
    mail = sender.sent[0]
    assert seen == ["Valorith"], "the PDF is drawn with Valorith's letterhead"
    assert "Valorith" in mail["subject"]
    assert mail["from_email"] == "", "Gmail cannot send as hello@valorith.my, so no From is claimed"
    assert mail["cc"] == ["hello@valorith.my"], "the copy goes to the business's own address"


def test_a_document_with_no_business_settings_falls_back_to_the_shared_settings():
    assert billing.settings_for({"business_id": "new"}, {"new": {}}, SETTINGS) is SETTINGS
    assert billing.settings_for({}, {}, SETTINGS) is SETTINGS
    own = {"company": {"name": "V"}}
    assert billing.settings_for({"business_id": "valorith"}, {"valorith": own}, SETTINGS) == own


def test_each_business_keeps_its_own_reminder_rules():
    docs = [_doc(id="ws", status="sent", due_date="2026-09-30"),
            _doc(id="val", status="sent", due_date="2026-09-30", business_id="valorith")]
    store = _store(**{db.BILLING_DOCS: docs, db.BILLING_OUTBOX: []})
    off = {**SETTINGS, "email": {"auto_reminders": False}}
    counts = billing.sweep(store, SETTINGS, NOW, businesses={"valorith": off})
    assert counts == {"reminders": 1, "expired": 0}
    assert [o["doc_id"] for o in store.tables[db.BILLING_OUTBOX]] == ["ws"]


def test_only_ws_regulab_papers_carry_the_ws_regulab_logo():
    assert billing.logo_for({}, SETTINGS).endswith("/cards/logo-ink.png")
    assert billing.logo_for({"business_id": "wsregulab"}, SETTINGS).endswith("/cards/logo-ink.png")
    assert billing.logo_for({"business_id": "valorith"}, SETTINGS) == "", "no logo set: the company name is written instead"
    own = {"company": {"logo_url": "https://cdn.example/valorith.png"}}
    assert billing.logo_for({"business_id": "valorith"}, own) == "https://cdn.example/valorith.png"
    assert billing.logo_for({"business_id": "valorith"}, {"company": {"logo_url": "javascript:alert(1)"}}) == ""


# ---- each business from its own Gmail (Wan, 7 Nov 2026: "for valorith change to muhammad.ridzuan22222@gmail.com") ----------

VALORITH_MAIL = "muhammad.ridzuan22222@gmail.com"


def _acct(id_, email, default=False):
    return {"id": id_, "status": "active", "is_default": default, "user_info": {"email": email}}


def _gmail(accounts, **kw):
    g = billing.GmailMCP("ck", **kw)
    g._tool = lambda name, args: {"data": {"results": {"gmail": {"accounts": accounts}}}}
    return g


# what Composio held on 7 Nov 2026: the Valorith inbox (the default) and info@ connected twice
LIVE = [_acct("gmail_snag-ulling", VALORITH_MAIL, default=True), _acct("gmail_smock-upgang", "info@kkmhalalconsultant.com"),
        _acct("gmail_prissy-stingo", "info@kkmhalalconsultant.com")]


def test_one_inbox_connected_twice_is_still_one_inbox_and_the_same_link_is_taken_every_run():
    g = _gmail(LIVE, expect="info@kkmhalalconsultant.com")
    assert g.account() == "gmail_prissy-stingo", "the lowest id when neither duplicate is the default"
    assert g.mailbox() == "info@kkmhalalconsultant.com"
    dup_default = [_acct("b", "info@kkmhalalconsultant.com"), _acct("a", "INFO@kkmhalalconsultant.com", default=True)]
    assert _gmail(dup_default, expect="info@kkmhalalconsultant.com").account() == "a", "Composio's default first"


def test_a_business_sends_from_its_own_inbox_and_from_ws_regulabs_until_its_own_is_connected():
    own = _gmail(LIVE, expect=VALORITH_MAIL, fallback="info@kkmhalalconsultant.com")
    assert own.account() == "gmail_snag-ulling" and own.mailbox() == VALORITH_MAIL
    without = [a for a in LIVE if a["id"] != "gmail_snag-ulling"]
    fb = _gmail(without, expect=VALORITH_MAIL, fallback="info@kkmhalalconsultant.com")
    assert fb.mailbox() == "info@kkmhalalconsultant.com", "never an arbitrary inbox: the named fallback"
    stranger = [_acct("x", "a@b.my"), _acct("y", "c@d.my")]
    try:
        _gmail(stranger, expect=VALORITH_MAIL, fallback="info@kkmhalalconsultant.com").account()
        raise AssertionError("two unknown inboxes must be refused, not guessed")
    except SendError as exc:
        assert VALORITH_MAIL in exc.message and "found 2" in exc.message
    assert _gmail([_acct("z", "only@one.my")]).account() == "z", "no address named and one inbox: as before"


class MailboxSender(FakeSender):
    def __init__(self, address):
        super().__init__()
        self.address = address

    def mailbox(self):
        return self.address


def test_the_outbox_sends_each_business_through_its_own_sender_with_its_own_from():
    valorith = {**SETTINGS, "company": {**SETTINGS["company"], "name": "Valorith", "email": VALORITH_MAIL},
                "email": {**SETTINGS["email"], "cc_self": True}}
    rows = [{"id": f"o{i}", "doc_id": d, "action": "send", "to_email": "buyer@shop.my", "cc": [], "subject": "", "body": "",
             "status": "pending", "attempts": 0, "meta": {}} for i, d in enumerate(["ws", "val", "val2"])]
    docs = [_doc(id="ws"), _doc(id="val", business_id="valorith"), _doc(id="val2", business_id="valorith")]
    store = _store(**{db.BILLING_DOCS: docs, db.BILLING_OUTBOX: rows})
    ws, val = MailboxSender("info@kkmhalalconsultant.com"), MailboxSender(VALORITH_MAIL)
    asked = []

    def sender_for(email):
        asked.append(email)
        return ws if email == "info@kkmhalalconsultant.com" else val
    counts = billing.process_outbox(store, SETTINGS, ws, NOW, businesses={"valorith": valorith}, render=_render,
                                    sender_for=sender_for)
    assert counts == {"sent": 3, "error": 0}
    assert len(ws.sent) == 1 and ws.sent[0]["from_email"] == "info@kkmhalalconsultant.com"
    assert len(val.sent) == 2 and all(m["from_email"] == VALORITH_MAIL for m in val.sent), "From is the inbox sending"
    assert all(m["cc"] == [VALORITH_MAIL] for m in val.sent), "cc_self as before: a copy in Valorith's own inbox"
    assert asked == ["info@kkmhalalconsultant.com", VALORITH_MAIL, VALORITH_MAIL]
