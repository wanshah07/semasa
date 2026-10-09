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
    assert counts == {"sent": 1, "error": 0, "skipped": 0, "left": 0}
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
