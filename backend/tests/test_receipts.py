"""Resit: the worker's parsing and its run on a fake store: read, file, match, and the three outcomes."""
from datetime import UTC, datetime

from fakestore import FakeStore

from semasa import db, receipts
from semasa.senders import SendError

NOW = datetime(2026, 10, 9, 2, 0, tzinfo=UTC)
SETTINGS = {"drive_root": "Semasa/Resit", "drive_account": "info@x.my", "per_run": 20}
SUBS = [{"id": "s1", "vendor": "TIME dotCom", "name": "Home fibre", "status": "active"},
        {"id": "s2", "vendor": "Unifi", "name": "Mobile postpaid", "status": "active"},
        {"id": "s3", "vendor": "Unifi", "name": "Home 100Mbps Pro", "status": "ended"}]


def test_parse_read_checks_every_field_and_never_guesses():
    raw = {"vendor": "  Petronas Kajang ", "date": "09/10/2026", "total": "RM 45.00", "currency": "RM", "tax": None,
           "items": [{"name": "Primax 95", "qty": "1", "price": "45.00"}, {"name": "", "price": 1}, "junk"],
           "payment_method": "Card", "category": "fuel", "summary": "Isi minyak", "confidence": 1.4}
    r = receipts.parse_read(raw)
    assert r["vendor"] == "Petronas Kajang" and r["doc_date"] == "2026-10-09" and r["total"] == 45.0 and r["currency"] == "MYR"
    assert r["items"] == [{"name": "Primax 95", "qty": 1.0, "price": 45.0}]
    assert r["payment_method"] == "card" and r["category"] == "pengangkutan" and r["confidence"] == 1.0
    assert receipts.parse_read(None)["vendor"] == "" and receipts.parse_read({"total": "n/a"})["total"] is None
    assert receipts.iso_date("2026-10-09T10:00") == "2026-10-09" and receipts.iso_date("31/02/2026") is None
    assert receipts.iso_date("9-10-26") == "2026-10-09"
    assert receipts.category_of("ZUS Coffee", "nonsense") == "makan" and receipts.category_of("Acme", None) == "lain"
    assert receipts.category_of("Acme", "klien") == "klien"


def test_subscription_match_prefers_the_longest_and_skips_ended():
    assert receipts.match_subscription("TIME dotCom Berhad", SUBS) == "s1"
    assert receipts.match_subscription("unifi", SUBS) == "s2"
    assert receipts.match_subscription("Mobile postpaid bill", SUBS) == "s2"
    assert receipts.match_subscription("ZUS", SUBS) is None
    assert receipts.match_subscription("", SUBS) is None


def test_file_name_and_drive_segments():
    read = {"vendor": "Petronas / Kajang", "total": 45, "currency": "MYR", "doc_date": "2026-10-09"}
    assert receipts.file_name(read, "abcdef12") == "2026-10-09 Petronas Kajang RM45.00 abcdef.jpg"
    assert receipts.file_name({"vendor": "", "total": None}, "abcdef12") == "tarikh-tiada resit abcdef.jpg"
    assert receipts.drive_segments("Semasa/Resit", "2026-10-09", "x") == ["Semasa", "Resit", "2026", "10"]
    # no date read: the month it was snapped, in Malaysia time (23:30 UTC on 30 Sep is 1 Oct MYT)
    assert receipts.drive_segments("Semasa/Resit", None, "2026-09-30T23:30:00+00:00") == ["Semasa", "Resit", "2026", "10"]


class FakeLLM:
    def __init__(self, answer):
        self.answer, self.asked = answer, 0

    def describe_image(self, system, prompt, data, mime, max_tokens=900):
        self.asked += 1
        return self.answer


class FakeDrive:
    def __init__(self, fail=None):
        self.filed, self.fail = [], fail

    def file(self, *, url, name, segments):
        if self.fail:
            raise self.fail
        self.filed.append((url, name, segments))
        return {"file_id": "f1", "url": "https://drive.google.com/file/d/f1/view", "folder_id": "p"}


def _row(**kw):
    base = {"id": "r1", "status": "pending", "image_path": "u/r.jpg", "image_url": "https://x/r.jpg",
            "taken_at": "2026-10-09T01:00:00+00:00", "attempts": 0, "drive_file_id": ""}
    base.update(kw)
    return base


def _store(rows):
    s = FakeStore(**{db.RECEIPTS: rows, db.SUBSCRIPTIONS: SUBS, db.LOG: []})
    return s


def _fetch(url):
    return b"\xff\xd8jpeg", "image/jpeg"


def test_a_receipt_is_read_filed_matched_and_done():
    store = _store([_row()])
    llm = FakeLLM({"vendor": "TIME dotCom", "date": "2026-10-05", "total": 104.95, "currency": "MYR", "items": [],
                   "category": "utiliti", "summary": "Bil fibre Oktober", "confidence": 0.9})
    drive = FakeDrive()
    counts = receipts.process(store, SETTINGS, llm, drive, NOW, fetch=_fetch)
    assert counts == {"read": 1, "filed": 1, "error": 0, "matched": 1}
    r = store.tables[db.RECEIPTS][0]
    assert r["status"] == "done" and r["vendor"] == "TIME dotCom" and r["total"] == 104.95 and r["subscription_id"] == "s1"
    assert r["drive_file_id"] == "f1" and r["drive_path"] == "Semasa/Resit/2026/10" and r["error"] == ""
    assert drive.filed[0][1] == "2026-10-05 TIME dotCom RM104.95 r1.jpg"
    assert drive.filed[0][2] == ["Semasa", "Resit", "2026", "10"]
    assert store.tables[db.LOG][0]["event"] == "receipt.filed"
    # a second run finds nothing pending
    assert receipts.process(store, SETTINGS, llm, drive, NOW, fetch=_fetch)["read"] == 0 and llm.asked == 1


def test_read_but_not_filed_stays_pending_then_errors_after_the_attempts_and_keeps_what_was_read():
    store = _store([_row()])
    llm = FakeLLM({"vendor": "ZUS Coffee", "date": "2026-10-09", "total": 12.9, "currency": "MYR"})
    bad = FakeDrive(fail=SendError("transient", "workbench 502"))
    receipts.process(store, SETTINGS, llm, bad, NOW, fetch=_fetch)
    r = store.tables[db.RECEIPTS][0]
    assert r["status"] == "pending" and r["vendor"] == "ZUS Coffee" and "drive:" in r["error"] and r["category"] == "makan"
    store.tables[db.RECEIPTS][0]["attempts"] = receipts.MAX_ATTEMPTS - 1
    receipts.process(store, SETTINGS, llm, bad, NOW, fetch=_fetch)
    assert store.tables[db.RECEIPTS][0]["status"] == "error"
    assert store.tables[db.LOG][-1]["event"] == "receipt.failed"


def test_no_reader_and_no_drive_are_said_in_words_and_a_bad_picture_is_refused():
    store = _store([_row()])
    receipts.process(store, SETTINGS, None, None, NOW, fetch=_fetch)
    r = store.tables[db.RECEIPTS][0]
    assert r["status"] == "pending" and "reader gave nothing" in r["error"] and "not filed" in r["error"]

    def bad_fetch(url):
        raise SendError("refused", "the picture answered 404 text/html")

    store = _store([_row(attempts=receipts.MAX_ATTEMPTS - 1)])
    receipts.process(store, SETTINGS, FakeLLM({}), FakeDrive(), NOW, fetch=bad_fetch)
    assert store.tables[db.RECEIPTS][0]["status"] == "error" and "404" in store.tables[db.RECEIPTS][0]["error"]


def test_already_filed_row_is_not_uploaded_again():
    store = _store([_row(drive_file_id="old", drive_path="Semasa/Resit/2026/10")])
    drive = FakeDrive()
    receipts.process(store, SETTINGS, FakeLLM({"vendor": "Acme", "total": 1}), drive, NOW, fetch=_fetch)
    assert not drive.filed and store.tables[db.RECEIPTS][0]["status"] == "done"
