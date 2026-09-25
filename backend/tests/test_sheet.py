"""The Semasa sheet: the log is appended once per row, a failure never stops a run and is logged once, not per run."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from fakestore import FakeStore

from semasa import sheet


class Resp:
    status_code = 200
    text = ""

    def __init__(self, body):
        self.body = body

    def json(self):
        return self.body


def _log(i, **k):
    return {"id": i, "at": f"2026-09-25T0{i}:00:00+00:00", "level": "info", "area": "scrape", "event": "scrape.done",
            "title": f"row {i}", "actor": None, "ref_table": None, "ref_id": None, "detail": {"n": i}, **k}


def _env(monkeypatch, name="SEMASA"):
    for n in ("SEMASA_SHEET_URL", "SEMASA_SHEET_TOKEN", "FAQ_SHEET_URL", "FAQ_SHEET_TOKEN"):
        monkeypatch.delenv(n, raising=False)
    monkeypatch.setenv(f"{name}_SHEET_URL", "https://script/exec")
    monkeypatch.setenv(f"{name}_SHEET_TOKEN", "tok")


def test_not_configured_does_nothing(monkeypatch):
    for n in ("SEMASA_SHEET_URL", "SEMASA_SHEET_TOKEN", "FAQ_SHEET_URL", "FAQ_SHEET_TOKEN"):
        monkeypatch.delenv(n, raising=False)
    store = FakeStore(semasa_log=[_log(1)])
    assert sheet.sync_log(store) == "log sheet: not configured"


def test_the_old_faq_secret_names_still_work(monkeypatch):
    _env(monkeypatch, "FAQ")
    assert sheet.configured() and sheet.config() == ("https://script/exec", "tok")


def test_log_rows_are_sent_once_in_order_with_malaysia_time(monkeypatch):
    _env(monkeypatch)
    sent = []
    monkeypatch.setattr(sheet.requests, "post",
                        lambda url, data, **k: sent.append(json.loads(data)) or Resp({"ok": True, "appended": 2}))
    store = FakeStore(semasa_log=[_log(2), _log(1, actor="u1")], semasa_settings=[])
    assert sheet.sync_log(store) == "log sheet: 2 rows appended"
    body = sent[0]
    assert body["action"] == "append_log" and body["token"] == "tok" and body["fields"] == sheet.LOG_FIELDS
    assert [r["id"] for r in body["rows"]] == [1, 2]
    assert body["rows"][0]["at_myt"] == "2026-09-25 09:00:00" and body["rows"][0]["actor"] == "Wan"
    assert body["rows"][1]["actor"] == "Bot" and json.loads(body["rows"][1]["detail"]) == {"n": 2}
    # the next run sends only what is new
    assert sheet.sync_log(store) == "log sheet: nothing new" and len(sent) == 1
    store.tables["semasa_log"].append(_log(3))
    sheet.sync_log(store)
    assert [r["id"] for r in sent[1]["rows"]] == [3]


def test_ids_compare_as_numbers_not_text(monkeypatch):
    _env(monkeypatch)
    sent = []
    monkeypatch.setattr(sheet.requests, "post",
                        lambda url, data, **k: sent.append(json.loads(data)) or Resp({"ok": True, "appended": 1}))
    store = FakeStore(semasa_log=[_log(9), _log(10)],
                      semasa_settings=[{"key": "log_sheet", "value": {"last_id": 9}}])
    sheet.sync_log(store)
    assert [r["id"] for r in sent[0]["rows"]] == [10]


def test_rows_younger_than_two_minutes_wait_for_the_next_run(monkeypatch):
    _env(monkeypatch)
    sent = []
    monkeypatch.setattr(sheet.requests, "post",
                        lambda url, data, **k: sent.append(json.loads(data)) or Resp({"ok": True, "appended": 1}))
    fresh = _log(2, at=datetime.now(UTC).isoformat())
    store = FakeStore(semasa_log=[_log(1), fresh], semasa_settings=[])
    sheet.sync_log(store)
    assert [r["id"] for r in sent[0]["rows"]] == [1]
    store.tables["semasa_log"][1]["at"] = (datetime.now(UTC) - timedelta(minutes=3)).isoformat()   # the store holds a copy
    sheet.sync_log(store)
    assert [r["id"] for r in sent[1]["rows"]] == [2]


def test_a_refusal_keeps_the_mark_and_is_logged_once_per_six_hours(monkeypatch):
    _env(monkeypatch)
    monkeypatch.setattr(sheet.requests, "post", lambda *a, **k: Resp({"ok": False, "error": "Unauthorised"}))
    store = FakeStore(semasa_log=[_log(1)], semasa_settings=[])
    assert sheet.sync_log(store) == "log sheet: FAILED (Unauthorised)"
    assert store.tables["semasa_settings"] == []                      # nothing marked as sent
    failed = [r for r in store.tables["semasa_log"] if r["event"] == "system.sheet_failed"]
    assert len(failed) == 1 and failed[0]["level"] == "error" and "Unauthorised" in failed[0]["title"]
    failed[0]["at"] = datetime.now(UTC).isoformat()                    # the database stamps it
    sheet.sync_log(store)
    sheet.sync_log(store)
    assert len([r for r in store.tables["semasa_log"] if r["event"] == "system.sheet_failed"]) == 1
    failed[0]["at"] = (datetime.now(UTC) - timedelta(hours=7)).isoformat()
    sheet.sync_log(store)
    assert len([r for r in store.tables["semasa_log"] if r["event"] == "system.sheet_failed"]) == 2


def test_an_unreachable_sheet_never_raises_and_hides_the_token(monkeypatch):
    _env(monkeypatch)

    def boom(*a, **k):
        raise sheet.requests.ConnectionError("https://script/exec?token=tok refused")
    monkeypatch.setattr(sheet.requests, "post", boom)
    store = FakeStore(semasa_log=[_log(1)], semasa_settings=[])
    out = sheet.sync_log(store)
    assert out.startswith("log sheet: FAILED") and "tok" not in out
    assert all("tok" not in r["title"] for r in store.tables["semasa_log"])


def test_a_non_json_answer_is_a_clear_failure(monkeypatch):
    _env(monkeypatch)

    class Html(Resp):
        status_code = 302

        def json(self):
            raise ValueError("no json")
    monkeypatch.setattr(sheet.requests, "post", lambda *a, **k: Html(None))
    assert "did not answer with JSON" in sheet.sync_log(FakeStore(semasa_log=[_log(1)], semasa_settings=[]))


def test_a_missing_log_table_says_which_file_to_run(monkeypatch):
    _env(monkeypatch)

    class NoTable:
        def table(self, name):
            if name == "semasa_log":
                raise RuntimeError("Could not find the table 'public.semasa_log' in the schema cache")
            return FakeStore(semasa_settings=[]).table(name)
    assert sheet.sync_log(NoTable()) == "log sheet: skipped (the semasa_log table is missing: run supabase/008_log.sql)"
