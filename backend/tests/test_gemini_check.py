"""Is each Gemini key live, and which model does it call? (Wan, 7 Nov 2026). The check asks every switched-on key, writes the
answer on its row, and keeps the list of models and the pick that answered for the card's menus and for every worker. A stand-in
for Live answers; nothing here reaches Google."""
from __future__ import annotations

from datetime import UTC, datetime

from fakestore import FakeStore

from semasa import db, gemini_check, gemini_keys

NOW = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)
GONE = ('404 [{ "error": { "code": 404, "message": "This model models/gemini-2.5-flash is no longer available to new users. '
        'Please update your code to use models/gemini-3-flash for the latest version.", "status": "NOT_FOUND" } }]')


def key(i, **over):
    return {"id": f"k{i}", "label": f"Key {i}", "hint": f"…{i}{i}{i}{i}", "api_key": f"AIza-secret-{i}", "enabled": True,
            "status": "new", "cooldown_until": None, "last_ok_at": None, "last_used_at": None, "calls": 0, "failures": 0,
            "checked_at": None, "check_note": None, **over}


def native(*names, methods=("generateContent",)):
    return [{"name": n, "methods": list(methods)} for n in names]


class Live:
    """Per key: native (the model list), models (the OpenAI-style list) and chat {model: (ok, ms, error)} with "*" for the rest.
    `asked` records (key, model) of every question."""
    def __init__(self, **per_key):
        self.per_key, self.asked, self.timeouts = per_key, [], []

    def native_models(self, c, timeout=0):
        return self.per_key.get(c["key"], {}).get("native", [])

    def models(self, c, timeout=0):
        return self.per_key.get(c["key"], {}).get("models", [])

    def chat(self, c, model, timeout=0):
        self.asked.append((c["key"], model))
        self.timeouts.append(timeout)
        got = self.per_key.get(c["key"], {}).get("chat", {})
        return got.get(model) or got.get("*") or (True, 400, "")


def store(*keys, settings=None, models=None):
    t = {gemini_keys.TABLE: list(keys)}
    rows = []
    if settings is not None:
        rows.append({"key": "gemini", "value": settings})
    if models is not None:
        rows.append({"key": gemini_keys.MODELS_KEY, "value": models})
    if rows:
        t[db.SETTINGS] = rows
    return FakeStore(**t)


def row(s, i):
    return next(r for r in s.tables[gemini_keys.TABLE] if r["id"] == f"k{i}")


def saved_models(s):
    return next(r["value"] for r in s.tables[db.SETTINGS] if r["key"] == gemini_keys.MODELS_KEY)


LISTED_NEW = native("gemini-2.5-flash", "gemini-3.5-flash", "gemini-3.7-flash", "gemini-3.8-flash", "gemini-flash-latest",
                    "gemini-3.1-flash-image")
LISTED = native("gemini-2.5-flash", "gemini-3-flash", "gemini-flash-latest", "gemini-2.5-pro", "gemini-2.5-flash-image",
                "gemini-embedding-001", "imagen-4.0-generate-001", "gemma-3-27b-it")


# ---- ranking ----------------------------------------------------------------------------------------------------------------

def test_text_models_are_ranked_stable_first_newest_first_flash_before_pro_and_never_a_picture_or_embedding_model():
    names = ["gemini-2.5-flash", "gemini-3-flash", "gemini-3-flash-preview", "gemini-2.5-pro", "gemini-2.5-flash-lite",
             "gemini-2.5-flash-image", "gemini-embedding-001", "gemma-3-27b-it", "imagen-4.0-generate-001",
             "gemini-2.5-flash-preview-tts", "gemini-live-2.5-flash", "gemini-flash-latest"]
    order = [n for _, n in sorted((gemini_check.text_rank(n), n) for n in names if gemini_check.text_rank(n) is not None)]
    assert order == ["gemini-3-flash", "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro", "gemini-3-flash-preview",
                     "gemini-flash-latest"]


def test_the_candidates_start_with_googles_own_suggestion_then_the_always_current_alias():
    listed = ["gemini-2.5-flash", "gemini-3-flash", "gemini-flash-latest"]
    got = gemini_check.text_candidates(listed, wanted_gone="gemini-2.5-flash", suggestion="gemini-3-flash")
    assert got == ["gemini-3-flash", "gemini-flash-latest"]
    assert gemini_check.text_candidates(listed, wanted_gone="gemini-2.5-flash")[0] == "gemini-flash-latest"
    assert gemini_check.text_candidates([])[0] == "gemini-flash-latest", "nothing listed: the alias is still worth asking"


def test_picture_models_need_image_in_the_name_and_are_ranked_newest_stable_first():
    assert gemini_check.image_rank("gemini-2.5-flash-image") is not None
    assert gemini_check.image_rank("imagen-4.0-generate-001") is None and gemini_check.image_rank("gemini-2.5-flash") is None
    names = ["gemini-2.5-flash-image", "gemini-3-pro-image-preview", "gemini-3-flash-image"]
    assert sorted(names, key=gemini_check.image_rank) == ["gemini-3-flash-image", "gemini-2.5-flash-image",
                                                          "gemini-3-pro-image-preview"]


def test_googles_own_words_name_the_replacement():
    assert gemini_keys.suggested_model(GONE) == "gemini-3-flash"
    assert gemini_keys.suggested_model("500 Internal error") == ""


def test_a_model_that_is_gone_is_not_the_keys_fault():
    assert gemini_keys.classify(GONE) == "model"
    assert gemini_keys.classify("404 models/x is not found for API version v1beta") == "model"
    assert gemini_keys.classify("429 RESOURCE_EXHAUSTED") == "limited" and gemini_keys.classify("403 API key not valid") == "bad"


# ---- the check --------------------------------------------------------------------------------------------------------------

def test_a_working_key_is_marked_ok_with_what_was_found_and_the_lists_are_saved():
    s = store(key(1))
    live = Live(**{"AIza-secret-1": {"native": LISTED}})
    out = gemini_check.run(s, live, NOW)
    r = row(s, 1)
    assert out.startswith("1 of 1 Gemini keys answered with gemini-flash-latest") and r["status"] == "ok" and r["checked_at"]
    assert "answered in 400 ms (gemini-flash-latest)" in r["check_note"]
    assert "gemini-2.5-flash-image is in this key's list" in r["check_note"]
    m = saved_models(s)
    assert m["text_pick"] == "gemini-flash-latest" and m["image_pick"] == "gemini-2.5-flash-image" and m["from"] == "Key 1"
    assert "gemini-3-flash" in m["text"] and "gemini-embedding-001" not in m["text"]
    assert "imagen-4.0-generate-001" not in m["image"]


def test_a_retired_model_is_replaced_by_one_that_answers_and_the_key_is_not_rested():
    s = store(key(1), settings={"model": "gemini-2.5-flash"})
    live = Live(**{"AIza-secret-1": {"native": LISTED, "chat": {"gemini-2.5-flash": (False, 80, GONE)}}})
    out = gemini_check.run(s, live, NOW)
    r = row(s, 1)
    assert "with gemini-3-flash" in out and r["status"] == "ok" and r["cooldown_until"] is None
    assert "gemini-2.5-flash did not answer, so gemini-3-flash is used automatically" in r["check_note"]
    assert saved_models(s)["text_pick"] == "gemini-3-flash"
    assert gemini_keys.load_settings(s)["model"] == "gemini-3-flash", "every worker now calls the working model"


def test_the_screenshot_case_two_keys_a_gone_model_and_no_resting_label():
    s = store(key(1), key(2))
    both = {"native": LISTED, "chat": {"gemini-flash-latest": (False, 60, GONE), "*": (True, 300, "")}}
    live = Live(**{"AIza-secret-1": both, "AIza-secret-2": both})
    gemini_check.run(s, live, NOW)
    assert row(s, 1)["status"] == "ok" and row(s, 2)["status"] == "ok"
    assert row(s, 1)["cooldown_until"] is None and row(s, 2)["cooldown_until"] is None
    second = [m for k, m in live.asked if k == "AIza-secret-2"]
    assert second[0] == "gemini-3-flash", "the second key starts from the working model"


def test_wans_own_choice_is_kept_while_the_keys_list_it_and_it_answers():
    s = store(key(1), settings={"model": "gemini-2.5-pro"}, models={"text": [], "text_pick": "gemini-3-flash"})
    live = Live(**{"AIza-secret-1": {"native": LISTED}})
    gemini_check.run(s, live, NOW)
    assert ("AIza-secret-1", "gemini-2.5-pro") in live.asked
    assert gemini_keys.load_settings(s)["model"] == "gemini-2.5-pro"
    assert saved_models(s)["text_pick"] == "gemini-3-flash", "auto's pick is not overwritten by his choice"


def test_a_choice_that_is_no_longer_listed_falls_back_to_the_pick_without_forgetting_it():
    s = store(key(1), settings={"model": "gemini-1.5-flash"}, models={"text": ["gemini-3-flash"], "text_pick": "gemini-3-flash"})
    assert gemini_keys.load_settings(s)["model"] == "gemini-3-flash"
    assert gemini_keys.load_settings(s)["model_setting"] == "gemini-1.5-flash", "the card still shows what he chose"


def test_a_key_whose_list_lacks_the_picture_model_says_so_without_failing():
    s = store(key(1))
    gemini_check.run(s, Live(**{"AIza-secret-1": {"native": native("gemini-3-flash")}}), NOW)
    assert row(s, 1)["status"] == "ok"
    assert "no picture model is in this key's list" in row(s, 1)["check_note"]
    other = store(key(1))
    gemini_check.run(other, Live(**{"AIza-secret-1": {"native": native("gemini-3-flash", "gemini-3-flash-image")}}), NOW)
    assert "gemini-3-flash-image is in this key's list" in row(other, 1)["check_note"]
    gone_pick = store(key(1), settings={"image_model": "gemini-2.0-flash-image"})
    listing = native("gemini-3-flash", "gemini-3-flash-image")
    gemini_check.run(gone_pick, Live(**{"AIza-secret-1": {"native": listing}}), NOW)
    note = row(gone_pick, 1)["check_note"]
    assert "gemini-3-flash-image is in this key's list" in note, "a choice nobody lists is not drawn with"


def test_a_refused_key_is_marked_bad_and_the_note_says_what_to_check():
    s = store(key(1))
    bad = (False, 90, '400 {"error": {"message": "API key not valid. Please pass a valid API key."}}')
    out = gemini_check.run(s, Live(**{"AIza-secret-1": {"native": LISTED, "chat": {"*": bad}}}), NOW)
    r = row(s, 1)
    assert r["status"] == "bad" and "API key not valid" in r["last_error"] and "refused this key" in r["check_note"]
    assert out == "0 of 1 Gemini keys answered; 1 refused, 0 limited"


def test_a_rate_limited_key_rests_and_is_not_called_bad():
    s = store(key(1))
    limited = {"native": LISTED, "chat": {"*": (False, 50, "429 RESOURCE_EXHAUSTED: quota")}}
    gemini_check.run(s, Live(**{"AIza-secret-1": limited}), NOW)
    r = row(s, 1)
    assert r["status"] == "limited" and r["cooldown_until"] and "rests" in r["check_note"]


def test_every_switched_on_key_is_asked_and_a_switched_off_one_is_not():
    s = store(key(1), key(2), key(3, enabled=False))
    live = Live(**{"AIza-secret-2": {"chat": {"*": (False, 70, "429 quota")}}})
    out = gemini_check.run(s, live, NOW)
    assert {k for k, _ in live.asked} == {"AIza-secret-1", "AIza-secret-2"}
    assert row(s, 1)["status"] == "ok" and row(s, 2)["status"] == "limited" and row(s, 3)["status"] == "new"
    assert out.endswith("; 0 refused, 1 limited")


def test_an_explicit_check_lets_a_key_that_was_refused_recover():
    s = store(key(1, status="bad", last_error="400 API key not valid"))
    gemini_check.run(s, Live(), NOW)
    assert row(s, 1)["status"] == "ok" and row(s, 1)["last_error"] is None


def test_no_key_switched_on_says_so_and_a_missing_table_is_not_an_error():
    assert gemini_check.run(store(key(1, enabled=False)), Live(), NOW) == "no Gemini key is switched on"
    assert gemini_check.run(FakeStore(), Live(), NOW) == "no Gemini key is switched on"


def test_nothing_that_answers_says_so_in_the_note_and_keeps_the_key_untouched():
    s = store(key(1))
    gone = {"native": native("gemini-2.5-flash"), "chat": {"*": (False, 60, GONE)}}
    gemini_check.run(s, Live(**{"AIza-secret-1": gone}), NOW)
    r = row(s, 1)
    assert r["status"] == "new" and r["cooldown_until"] is None and "no text model this key lists answered" in r["check_note"]


def test_the_key_goes_only_into_the_asked_call_never_into_the_note():
    s = store(key(1))
    gemini_check.run(s, Live(), NOW)
    assert "AIza-secret-1" not in str(row(s, 1)["check_note"]) and "AIza-secret-1" not in str(row(s, 1)["last_error"])
    assert "AIza-secret-1" not in str(saved_models(s))


# ---- a worker that meets "model gone" -----------------------------------------------------------------------------------------

def test_a_worker_that_meets_a_gone_model_asks_for_the_models_once_and_retries_with_the_working_one():
    s = store(key(1), settings={"model": "gemini-2.5-flash"})
    live = Live(**{"AIza-secret-1": {"native": LISTED, "chat": {"gemini-2.5-flash": (False, 80, GONE)}}})
    cand, _seed = gemini_keys.candidate(s, "motion", live, NOW)
    assert cand and cand["model"] == "gemini-3-flash" and cand["gemini_key"] == "k1"
    assert row(s, 1)["status"] in ("ok", "new") and row(s, 1)["cooldown_until"] is None


def test_refreshing_never_raises_and_says_false_when_nothing_changed():
    class Broken(Live):
        def native_models(self, c, timeout=0):
            raise RuntimeError("down")
    s = store(key(1))
    assert gemini_check.refresh_models(s, Broken(), NOW) in (True, False)
    assert gemini_check.refresh_models(FakeStore(), Live(), NOW) is False


HUNG = (False, None, "HTTPSConnectionPool(host='generativelanguage.googleapis.com'): Read timed out. (read timeout=45)")


def test_the_check_waits_long_enough_for_a_slow_model_and_a_timeout_is_not_a_rate_limit():
    s = store(key(1))
    live = Live(**{"AIza-secret-1": {"native": LISTED, "chat": {"*": HUNG}}})
    out = gemini_check.run(s, live, NOW)
    r = row(s, 1)
    assert live.timeouts[0] == gemini_check.CHECK_TIMEOUT >= 30
    assert set(live.timeouts[1:]) == {gemini_check.NEXT_TIMEOUT}, "each further model gets a shorter wait"
    assert r["status"] == "new", "Google being slow says nothing about the key: it is not marked limited or refused"
    assert r["cooldown_until"] is not None and "no model answered in time" in r["check_note"]
    assert "Tried: gemini-flash-latest gave no answer in time" in r["check_note"]
    assert out.startswith("0 of 1")
    assert gemini_keys.classify(r["last_error"]) == "retry"


def test_a_model_that_hangs_does_not_stop_the_next_one_from_being_asked():
    s = store(key(1))
    chat = {"gemini-flash-latest": HUNG, "gemini-3.8-flash": HUNG, "*": (True, 900, "")}
    live = Live(**{"AIza-secret-1": {"native": LISTED_NEW, "chat": chat}})
    out = gemini_check.run(s, live, NOW)
    r = row(s, 1)
    assert r["status"] == "ok" and "with gemini-3.7-flash" in out
    assert [m for _, m in live.asked][:3] == ["gemini-flash-latest", "gemini-3.8-flash", "gemini-3.7-flash"]
    assert ("Tried: gemini-flash-latest gave no answer in time; gemini-3.8-flash gave no answer in time; "
            "gemini-3.7-flash answered in 900 ms") in r["check_note"]
    assert saved_models(s)["text_pick"] == "gemini-3.7-flash"
    assert gemini_keys.load_settings(s)["model"] == "gemini-3.7-flash", "every worker now calls the model that answered"


def test_a_refusal_or_a_quota_answer_stops_the_walk_because_it_is_the_keys_own():
    s = store(key(1))
    chat = {"gemini-flash-latest": HUNG, "gemini-3.8-flash": (False, 40, "429 RESOURCE_EXHAUSTED: quota"), "*": (True, 1, "")}
    live = Live(**{"AIza-secret-1": {"native": LISTED_NEW, "chat": chat}})
    gemini_check.run(s, live, NOW)
    assert [m for _, m in live.asked] == ["gemini-flash-latest", "gemini-3.8-flash"]
    assert row(s, 1)["status"] == "limited"
