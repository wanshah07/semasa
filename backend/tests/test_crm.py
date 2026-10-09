"""CRM: the worker's rules on a fake store: consent gate, the footer and unsubscribe link, caps, send once, tallies."""
from datetime import UTC, datetime

from fakestore import FakeStore

from semasa import crm, db
from semasa.senders import SendError

NOW = datetime(2026, 10, 9, 2, 0, tzinfo=UTC)            # 10:00 MYT
SETTINGS = {"daily_cap": 3, "per_run": 2, "footer_bm": "Anda bersetuju.", "footer_en": "You agreed."}


def _contact(i, **kw):
    base = {"id": f"k{i}", "name": f"Orang {i}", "company": "Syarikat", "email": f"k{i}@x.my", "lang": "bm", "consent": True,
            "unsubscribed_at": None, "unsub_token": f"tok{i}" * 8}
    base.update(kw)
    return base


def _camp(**kw):
    base = {"id": "c1", "name": "Promo Oktober", "kind": "broadcast", "status": "sending", "send_at": "2026-10-09T01:00:00+00:00",
            "sent_count": 0, "error_count": 0}
    base.update(kw)
    return base


def _row(i, **kw):
    base = {"id": f"o{i}", "campaign_id": "c1", "contact_id": f"k{i}", "to_email": f"k{i}@x.my", "subject": "Hai Orang",
            "body": "Baris satu\n\nBaris dua", "status": "pending", "attempts": 0, "is_test": False}
    base.update(kw)
    return base


class FakeSender:
    def __init__(self, fail=None):
        self.sent, self.fail = [], fail

    def send(self, **kw):
        if self.fail:
            raise self.fail
        self.sent.append(kw)
        return {"id": "m1", "threadId": "t1"}


def _store(**tables):
    s = FakeStore(**tables)
    s.tables.setdefault(db.SETTINGS, [{"key": "crm", "value": SETTINGS},
                                      {"key": "billing", "value": {"company": {"email": "info@x.my"}}}])
    s.tables.setdefault(db.CRM_ACTIVITIES, [])
    s.tables.setdefault(db.LOG, [])
    return s


def test_sends_once_with_footer_and_unsubscribe_link_and_records_the_activity():
    store = _store(**{db.CRM_CONTACTS: [_contact(1)], db.CRM_CAMPAIGNS: [_camp()], db.CRM_OUTBOX: [_row(1)]})
    sender = FakeSender()
    counts = crm.process_outbox(store, SETTINGS, sender, NOW, site="https://s.my")
    assert counts == {"sent": 1, "error": 0, "skipped": 0, "left": 0, "manual": 0}
    mail = sender.sent[0]
    assert mail["to"] == "k1@x.my" and mail["from_email"] == "info@x.my" and mail["subject"] == "Hai Orang"
    assert "<p>Baris satu</p><p>Baris dua</p>" in mail["html"]
    assert "Anda bersetuju." in mail["html"] and "https://s.my/#crm/unsub/" + "tok1" * 8 in mail["html"]
    row = store.tables[db.CRM_OUTBOX][0]
    assert row["status"] == "sent" and row["result"] == {"id": "m1", "threadId": "t1"} and row["sent_at"]
    assert store.tables[db.CRM_CONTACTS][0]["last_contact_at"] == NOW.isoformat()
    assert [a["kind"] for a in store.tables[db.CRM_ACTIVITIES]] == ["campaign"]
    camp = store.tables[db.CRM_CAMPAIGNS][0]
    assert camp["status"] == "sent" and camp["sent_count"] == 1
    # a second run finds nothing pending and sends nothing
    assert crm.process_outbox(store, SETTINGS, sender, NOW)["sent"] == 0 and len(sender.sent) == 1


def test_consent_withdrawn_after_queueing_is_checked_again_at_send_time():
    store = _store(**{db.CRM_CONTACTS: [_contact(1, consent=False), _contact(2, unsubscribed_at="2026-10-09T01:30:00+00:00")],
                      db.CRM_CAMPAIGNS: [_camp()], db.CRM_OUTBOX: [_row(1), _row(2)]})
    sender = FakeSender()
    counts = crm.process_outbox(store, SETTINGS, sender, NOW)
    assert counts["sent"] == 0 and counts["skipped"] == 2 and not sender.sent
    assert all(r["status"] == "skipped" and r["error"] == "no consent" for r in store.tables[db.CRM_OUTBOX])


def test_a_test_send_ignores_consent_and_is_not_an_activity():
    store = _store(**{db.CRM_CONTACTS: [_contact(1, consent=False)], db.CRM_CAMPAIGNS: [_camp()],
                      db.CRM_OUTBOX: [_row(1, is_test=True, to_email="info@x.my")]})
    sender = FakeSender()
    assert crm.process_outbox(store, SETTINGS, sender, NOW)["sent"] == 1
    assert sender.sent[0]["to"] == "info@x.my" and not store.tables[db.CRM_ACTIVITIES]
    assert store.tables[db.CRM_CAMPAIGNS][0]["sent_count"] == 0       # a test is never counted


def test_caps_per_run_and_per_day_leave_the_rest_pending_and_say_so():
    contacts = [_contact(i) for i in range(1, 6)]
    store = _store(**{db.CRM_CONTACTS: contacts, db.CRM_CAMPAIGNS: [_camp()], db.CRM_OUTBOX: [_row(i) for i in range(1, 6)]})
    sender = FakeSender()
    c1 = crm.process_outbox(store, SETTINGS, sender, NOW)
    assert c1["sent"] == 2 and c1["left"] == 3                         # per_run 2
    assert store.tables[db.CRM_CAMPAIGNS][0]["status"] == "sending"
    c2 = crm.process_outbox(store, SETTINGS, sender, NOW)
    assert c2["sent"] == 1 and c2["left"] == 2                         # daily_cap 3 reached
    c3 = crm.process_outbox(store, SETTINGS, sender, NOW)
    assert c3["sent"] == 0 and c3["left"] == 2 and any(x["event"] == "crm.cap" for x in store.tables[db.LOG])
    assert len(sender.sent) == 3


def test_not_yet_due_campaign_is_left_alone_and_a_transient_failure_retries_then_fails():
    later = _camp(status="scheduled", send_at="2026-10-09T09:00:00+00:00")
    store = _store(**{db.CRM_CONTACTS: [_contact(1)], db.CRM_CAMPAIGNS: [later], db.CRM_OUTBOX: [_row(1)]})
    assert crm.process_outbox(store, SETTINGS, FakeSender(), NOW)["sent"] == 0
    assert store.tables[db.CRM_OUTBOX][0]["status"] == "pending"
    store = _store(**{db.CRM_CONTACTS: [_contact(1)], db.CRM_CAMPAIGNS: [_camp()], db.CRM_OUTBOX: [_row(1)]})
    bad = FakeSender(fail=SendError("transient", "gateway 502"))
    assert crm.process_outbox(store, SETTINGS, bad, NOW)["error"] == 1
    assert store.tables[db.CRM_OUTBOX][0]["status"] == "pending" and store.tables[db.CRM_OUTBOX][0]["attempts"] == 1
    store.tables[db.CRM_OUTBOX][0]["attempts"] = crm.MAX_ATTEMPTS - 1
    crm.process_outbox(store, SETTINGS, bad, NOW)
    assert store.tables[db.CRM_OUTBOX][0]["status"] == "error" and store.tables[db.CRM_CAMPAIGNS][0]["error_count"] == 1
    store = _store(**{db.CRM_CONTACTS: [_contact(1)], db.CRM_CAMPAIGNS: [_camp()], db.CRM_OUTBOX: [_row(1)]})
    assert crm.process_outbox(store, SETTINGS, None, NOW)["error"] == 1
    assert "COMPOSIO_CONSUMER_KEY" in store.tables[db.CRM_OUTBOX][0]["error"]


def test_body_html_is_kept_and_english_footer_follows_the_contact():
    assert crm.as_html("<p>Sudah HTML</p>") == "<p>Sudah HTML</p>"
    assert crm.as_html("a <b\n\nc") == "<p>a &lt;b</p><p>c</p>"
    out = crm.with_footer("<p>x</p>", "en", "t" * 32, SETTINGS, site="https://s.my/")
    assert "You agreed." in out and ">Unsubscribe<" in out and "https://s.my/#crm/unsub/" + "t" * 32 in out


def test_welcome_sweep_calls_the_queue_function_for_live_welcome_campaigns():
    camps = [_camp(id="w1", kind="welcome", status="scheduled"), _camp(id="w2", kind="welcome", status="draft"), _camp()]
    store = _store(**{db.CRM_CAMPAIGNS: camps})
    calls = []

    class R:
        def __init__(self, name, params):
            calls.append((name, params))

        def execute(self):
            from types import SimpleNamespace
            return SimpleNamespace(data={"queued": 2})

    store.rpc = lambda name, params: R(name, params)
    assert crm.welcome_sweep(store) == {"welcome_queued": 2}
    assert calls == [("semasa_crm_queue", {"p_campaign": "w1"})]


class FakeWA:
    def __init__(self, fail=None):
        self.sent, self.fail = [], fail

    def send_text(self, **kw):
        if self.fail:
            raise self.fail
        self.sent.append(kw)
        return {"id": "wamid.1", "raw": None}


def test_whatsapp_row_goes_through_the_whatsapp_sender_as_plain_text_with_the_way_out():
    camp = _camp(channel="whatsapp", name="Promo WA")
    row = _row(1, channel="whatsapp", to_phone="60123456789", subject="Promo WA",
               body="<p>Hai <b>Orang</b></p><p>Baris dua</p>")
    store = _store(**{db.CRM_CONTACTS: [_contact(1, phone="012-345 6789")], db.CRM_CAMPAIGNS: [camp], db.CRM_OUTBOX: [row]})
    gmail, wa = FakeSender(), FakeWA()
    counts = crm.process_outbox(store, SETTINGS, gmail, NOW, site="https://s.my", wa=wa)
    assert counts["sent"] == 1 and not gmail.sent
    msg = wa.sent[0]
    assert msg["to_number"] == "60123456789"
    assert msg["text"].startswith("Hai Orang\n\nBaris dua") and "Balas STOP" in msg["text"] and "/#crm/unsub/" in msg["text"]
    assert store.tables[db.CRM_ACTIVITIES][0]["title"].startswith("WhatsApp kempen")


def test_whatsapp_without_an_api_sender_is_the_blast_board_rows_stay_pending_and_are_counted_manual():
    camp = _camp(channel="whatsapp")
    rows = [_row(1, channel="whatsapp", to_phone="60123456789"), _row(2, channel="whatsapp", to_phone="60123456788")]
    store = _store(**{db.CRM_CONTACTS: [_contact(1), _contact(2)], db.CRM_CAMPAIGNS: [camp], db.CRM_OUTBOX: rows})
    counts = crm.process_outbox(store, SETTINGS, FakeSender(), NOW, wa=None)
    assert counts["sent"] == 0 and counts["manual"] == 2 and counts["left"] == 0
    assert all(r["status"] == "pending" for r in store.tables[db.CRM_OUTBOX])
    assert store.tables[db.CRM_CAMPAIGNS][0]["status"] == "sending"


def test_trash_requested_rows_are_moved_to_gmail_trash_then_deleted_and_a_deleting_campaign_goes_last():
    class Trashing(FakeSender):
        def __init__(self):
            super().__init__()
            self.trashed = []

        def trash(self, mid):
            if mid == "bad":
                raise SendError("transient", "502")
            self.trashed.append(mid)

    camp = _camp(status="deleting")
    rows = [_row(1, status="sent", result={"id": "m1"}, trash_requested=True),
            _row(2, status="sent", result={"id": "bad"}, trash_requested=True),
            _row(3, status="sent", channel="whatsapp", to_phone="60123456789", result={"id": "wamid.3"}, trash_requested=True)]
    store = _store(**{db.CRM_CONTACTS: [_contact(1), _contact(2), _contact(3)], db.CRM_CAMPAIGNS: [camp], db.CRM_OUTBOX: rows})
    g = Trashing()
    counts = crm.process_trash(store, g)
    assert counts == {"trashed": 2, "trash_error": 1}
    assert g.trashed == ["m1"]                                        # the WhatsApp row is deleted without a Gmail call
    assert [r["id"] for r in store.tables[db.CRM_OUTBOX]] == ["o2"]    # the failed one stays flagged for the next run
    assert len(store.tables[db.CRM_CAMPAIGNS]) == 1                   # still deleting: one row left
    g2 = Trashing()
    store.tables[db.CRM_OUTBOX][0]["result"] = {"id": "m2"}
    assert crm.process_trash(store, g2) == {"trashed": 1, "trash_error": 0}
    assert store.tables[db.CRM_CAMPAIGNS] == []
    assert crm.process_trash(store, None) == {"trashed": 0, "trash_error": 0}


def test_whatsapp_text_strips_tags_and_keeps_paragraphs():
    out = crm.whatsapp_text("Baris satu\nBaris 1b\n\nBaris dua", "en", "t" * 32, SETTINGS, site="https://s.my")
    tail = "Reply STOP to stop receiving these messages. https://s.my/#crm/unsub/" + "t" * 32
    assert out == "Baris satu\nBaris 1b\n\nBaris dua\n\n" + tail
