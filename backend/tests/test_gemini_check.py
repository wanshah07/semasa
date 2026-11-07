"""Is each Gemini key live? (Wan, 7 Nov 2026). The check asks every switched-on key and writes the answer on its row. A stand-in
for Live answers; nothing here reaches Google."""
from __future__ import annotations

from datetime import UTC, datetime

from fakestore import FakeStore

from semasa import db, gemini_check, gemini_keys

NOW = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)


def key(i, **over):
    return {"id": f"k{i}", "label": f"Key {i}", "hint": f"…{i}{i}{i}{i}", "api_key": f"AIza-secret-{i}", "enabled": True,
            "status": "new", "cooldown_until": None, "last_ok_at": None, "last_used_at": None, "calls": 0, "failures": 0,
            "checked_at": None, "check_note": None, **over}


class Live:
    """Answers per key: models (a list) and chat (ok, ms, error). `asked` records (key, model) of every question."""
    def __init__(self, **per_key):
        self.per_key, self.asked = per_key, []

    def models(self, c, timeout=0):
        return self.per_key.get(c["key"], {}).get("models", [])

    def chat(self, c, model, timeout=0):
        self.asked.append((c["key"], model))
        got = self.per_key.get(c["key"], {}).get("chat", {})
        return got.get(model) or got.get("*") or (True, 400, "")


def store(*keys, settings=None):
    t = {gemini_keys.TABLE: list(keys)}
    if settings is not None:
        t[db.SETTINGS] = [{"key": "gemini", "value": settings}]
    return FakeStore(**t)


def row(s, i):
    return next(r for r in s.tables[gemini_keys.TABLE] if r["id"] == f"k{i}")


def test_a_working_key_is_marked_ok_with_what_was_found():
    s = store(key(1))
    live = Live(**{"AIza-secret-1": {"models": ["gemini-2.5-flash", "gemini-2.5-flash-image"]}})
    out = gemini_check.run(s, live, NOW)
    r = row(s, 1)
    assert out == "1 of 1 Gemini keys answered" and r["status"] == "ok" and r["last_ok_at"] and r["checked_at"]
    assert "answered in 400 ms (gemini-2.5-flash)" in r["check_note"]
    assert "gemini-2.5-flash-image is in this key's list" in r["check_note"]


def test_a_key_whose_list_lacks_the_picture_model_says_so_without_failing():
    s = store(key(1))
    gemini_check.run(s, Live(**{"AIza-secret-1": {"models": ["gemini-2.5-flash"]}}), NOW)
    assert row(s, 1)["status"] == "ok"
    assert "is NOT in this key's list" in row(s, 1)["check_note"]


def test_a_refused_key_is_marked_bad_and_the_note_says_what_to_check():
    s = store(key(1))
    bad = (False, 90, '400 {"error": {"message": "API key not valid. Please pass a valid API key."}}')
    out = gemini_check.run(s, Live(**{"AIza-secret-1": {"chat": {"*": bad}}}), NOW)
    r = row(s, 1)
    assert r["status"] == "bad" and "API key not valid" in r["last_error"] and "refused this key" in r["check_note"]
    assert out == "0 of 1 Gemini keys answered; 1 refused, 0 limited"


def test_a_rate_limited_key_rests_and_is_not_called_bad():
    s = store(key(1))
    gemini_check.run(s, Live(**{"AIza-secret-1": {"chat": {"*": (False, 50, "429 RESOURCE_EXHAUSTED: quota exceeded")}}}), NOW)
    r = row(s, 1)
    assert r["status"] == "limited" and r["cooldown_until"] and "rests" in r["check_note"]


def test_a_wrong_model_name_does_not_condemn_a_good_key():
    s = store(key(1), settings={"model": "gemini-9-flash"})
    live = Live(**{"AIza-secret-1": {"models": ["gemini-2.5-flash", "gemini-2.5-pro"],
                                      "chat": {"gemini-9-flash": (False, 80, "404 models/gemini-9-flash is not found")}}})
    gemini_check.run(s, live, NOW)
    r = row(s, 1)
    assert r["status"] == "ok" and "gemini-9-flash was not found, gemini-2.5-flash answered" in r["check_note"]
    assert ("AIza-secret-1", "gemini-2.5-flash") in live.asked


def test_every_switched_on_key_is_asked_and_a_switched_off_one_is_not():
    s = store(key(1), key(2), key(3, enabled=False))
    live = Live(**{"AIza-secret-2": {"chat": {"*": (False, 70, "429 quota")}}})
    out = gemini_check.run(s, live, NOW)
    assert {k for k, _ in live.asked} == {"AIza-secret-1", "AIza-secret-2"}
    assert row(s, 1)["status"] == "ok" and row(s, 2)["status"] == "limited" and row(s, 3)["status"] == "new"
    assert out == "1 of 2 Gemini keys answered; 0 refused, 1 limited"


def test_an_explicit_check_lets_a_key_that_was_refused_recover():
    s = store(key(1, status="bad", last_error="400 API key not valid"))
    gemini_check.run(s, Live(), NOW)
    assert row(s, 1)["status"] == "ok" and row(s, 1)["last_error"] is None


def test_no_key_switched_on_says_so_and_a_missing_table_is_not_an_error():
    assert gemini_check.run(store(key(1, enabled=False)), Live(), NOW) == "no Gemini key is switched on"
    assert gemini_check.run(FakeStore(), Live(), NOW) == "no Gemini key is switched on"


def test_the_key_goes_only_into_the_asked_call_never_into_the_note():
    s = store(key(1))
    gemini_check.run(s, Live(), NOW)
    assert "AIza-secret-1" not in str(row(s, 1)["check_note"]) and "AIza-secret-1" not in str(row(s, 1)["last_error"])
