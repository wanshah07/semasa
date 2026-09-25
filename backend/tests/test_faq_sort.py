"""The bot's own categories: names that mean the same are one category, the list never grows past its caps or
back into what Wan deleted, a new category needs a group, and Wan's own placement is never moved."""

from datetime import UTC, datetime, timedelta

from fakestore import FakeStore

from semasa import faq, faq_sort
from semasa.config import LLMSettings


class FakeLLM:
    def __init__(self, *outs, key="k"):
        self.outs, self.seen = list(outs), []
        self.s = LLMSettings(provider="openai", api_key=key, base_url="https://x/v1", model="m", timeout=5)

    @property
    def configured(self):
        return bool(self.s.api_key)

    def chat_json(self, system, user, max_tokens=0, **_):
        self.seen.append((system, user))
        return self.outs.pop(0) if self.outs else None


def _faq(i, cat="lain", by="bot", sorted_at=None, **k):
    return {"id": i, "status": "ready", "question_bm": f"soalan {i}", "answer_bm": f"jawapan {i}", "category": cat,
            "subcategory": "", "category_by": by, "sorted_at": sorted_at, "created_at": f"2026-09-25T00:0{i}:00+00:00",
            **k}


def _row(store, i):
    return next(r for r in store.tables["semasa_faqs"] if r["id"] == i)


def _saved(store):
    return next(r for r in store.tables["semasa_settings"] if r["key"] == "faq")["value"]


# --- names ----------------------------------------------------------------------------------------------

def test_names_that_mean_the_same_are_the_same():
    assert faq_sort.same_name("Label & Penandaan", "label dan penandaan")
    assert faq_sort.same_name("Penandaan label", "Label & penandaan")
    assert faq_sort.same_name("Import", "Import & eksport")
    assert not faq_sort.same_name("Halal", "Farmaseutikal")
    assert not faq_sort.same_name("Kos", "Kosmetik")                   # a short word is not "inside" a longer one


def test_a_new_sub_is_added_once_and_capped():
    cats = faq.categories({})
    assert faq_sort.add_sub(cats, "halal", "Tarikh luput") == "Tarikh luput"
    halal = next(c for c in cats if c["key"] == "halal")
    assert "Tarikh luput" in halal["subs"] and halal["auto_subs"] == ["Tarikh luput"]
    assert faq_sort.add_sub(cats, "halal", "tarikh  luput.") == "Tarikh luput" and halal["subs"].count("Tarikh luput") == 1
    assert faq_sort.add_sub(cats, "halal", "Logo dan sijil") == "Logo & sijil"          # an existing sub
    assert faq_sort.add_sub(cats, "lain", "Apa-apa") == ""                               # Lain-lain has no subs
    assert faq_sort.add_sub(cats, "halal", "Kemasan produk") == ""                      # Indonesian: refused
    assert faq_sort.add_sub(cats, "halal", "Premis runcit", declined=["premis runcit"]) == ""
    while len(halal["subs"]) < faq_sort.MAX_SUBS:
        faq_sort.add_sub(cats, "halal", f"Topik {len(halal['subs'])} baharu")
    assert faq_sort.add_sub(cats, "halal", "Satu lagi") == ""


def test_a_new_category_goes_before_lain_and_is_marked():
    cats = faq.categories({})
    key = faq_sort.add_category(cats, {"key": "Label!", "bm": "Label & penandaan", "en": "Labelling", "subs": ["Label", "label"]})
    assert key == "label" and cats[-1]["key"] == "lain" and cats[-2]["key"] == "label"
    assert cats[-2]["auto"] is True and cats[-2]["subs"] == ["Label"]
    assert faq_sort.add_category(cats, {"bm": "Penandaan label", "en": "Labels"}) == "label"         # the same one
    assert faq_sort.add_category(cats, {"bm": "Halal"}) == "halal"
    assert faq_sort.add_category(cats, {"bm": "Import & eksport"}, declined=["Import dan eksport"]) == "lain"
    while len(cats) < faq_sort.MAX_CATEGORIES:
        faq_sort.add_category(cats, {"bm": f"Tajuk nombor {len(cats)}"})
    assert faq_sort.add_category(cats, {"bm": "Satu lagi"}) == "lain"


def test_the_auto_marks_survive_a_round_trip_through_settings():
    cats = faq.categories({})
    faq_sort.add_category(cats, {"bm": "Label & penandaan", "en": "Labelling"})
    faq_sort.add_sub(cats, "halal", "Tarikh luput")
    again = faq.categories({"faq": {"categories": cats}})
    assert next(c for c in again if c["key"] == "labelling")["auto"] is True
    assert next(c for c in again if c["key"] == "halal")["auto_subs"] == ["Tarikh luput"]
    # Wan renamed the sub in Tetapan: it is no longer the bot's
    edited = [dict(c, subs=["Logo & sijil", "Luput"]) if c["key"] == "halal" else c for c in cats]
    assert "auto_subs" not in next(c for c in faq.categories({"faq": {"categories": edited}}) if c["key"] == "halal")


# --- the writer's subcategory ------------------------------------------------------------------------------

GOOD = {"question_bm": "Berapa lama sijil halal sah?", "answer_bm": "Sijil halal sah selama dua tahun.",
        "question_en": "How long is a halal certificate valid?", "answer_en": "It is valid for two years.",
        "category": "halal", "subcategory": "", "new_subcategory": "Tempoh sah sijil", "tags": [],
        "instrument": "", "answer_source": "given", "needs_check": False, "check_note": ""}


def test_the_writer_adds_a_subcategory_and_the_run_saves_it():
    store = FakeStore(semasa_faqs=[{"id": "a", "status": "new", "created_at": "1", "attempts": 0, "raw_question": "Q",
                                    "raw_answer": "A", "source_kind": "paste", "category": "lain", "category_by": "bot"}],
                      semasa_settings=[{"key": "faq", "value": {}}], semasa_log=[])
    llm = FakeLLM(GOOD, {"items": []})
    note = faq.run(store, llm)
    got = _row(store, "a")
    assert (got["category"], got["subcategory"], got["category_by"]) == ("halal", "Tempoh sah sijil", "bot")
    saved = _saved(store)
    halal = next(c for c in saved["categories"] if c["key"] == "halal")
    assert "Tempoh sah sijil" in halal["subs"] and halal["auto_subs"] == ["Tempoh sah sijil"] and saved["changed_at"]
    assert any(r["event"] == "faq.subcategory" for r in store.tables["semasa_log"])
    assert "sort: nothing to sort" in note


def test_a_sub_is_not_invented_when_one_fits():
    row = {"id": "a", "source_kind": "paste", "raw_question": "Q", "raw_answer": "A", "category": "lain", "category_by": "bot"}
    store = FakeStore(semasa_faqs=[row])
    cats, grown = faq.categories({}), []
    faq.process(store, FakeLLM({**GOOD, "subcategory": "Logo & sijil"}), row, cats, None, grown)
    assert _row(store, "a")["subcategory"] == "Logo & sijil" and grown == []


def test_the_save_keeps_what_wan_changed_meanwhile():
    mine = [{"key": "halal", "bm": "Halal (JAKIM)", "en": "Halal", "subs": ["Logo"]}]
    store = FakeStore(semasa_settings=[{"key": "faq", "value": {"categories": mine, "declined": ["x"]}}])
    faq_sort.save_growth(store, [{"bm": "Label & penandaan", "en": "Labelling", "auto_at": "t"}], [("halal", "Luput")])
    saved = _saved(store)
    assert [c["key"] for c in saved["categories"]] == ["halal", "labelling", "lain"]
    assert saved["categories"][0]["bm"] == "Halal (JAKIM)" and saved["categories"][0]["subs"] == ["Logo", "Luput"]
    assert saved["declined"] == ["x"]


# --- sorting -----------------------------------------------------------------------------------------------

def test_what_the_sorter_looks_at():
    cats = faq.categories({})
    changed = "2026-09-25T10:00:00Z"
    rows = [_faq(1), _faq(2, sorted_at="2026-09-25T09:00:00+00:00"), _faq(3, sorted_at="2026-09-25T11:00:00+00:00"),
            _faq(4, by="wan"), _faq(5, cat="halal"), _faq(6, cat="deleted", by="wan")]
    assert [r["id"] for r in faq_sort.to_sort(rows, cats, changed)] == [1, 2, 6]
    assert [r["id"] for r in faq_sort.to_sort(rows, cats, None)] == [1, 6]


def test_a_new_category_needs_a_group_and_moves_are_logged_once():
    store = FakeStore(semasa_faqs=[_faq(1), _faq(2), _faq(3), _faq(4), _faq(5, by="wan")],
                      semasa_settings=[{"key": "faq", "value": {}}], semasa_log=[])
    out = {"items": [{"id": 1, "category": "label", "subcategory": ""}, {"id": 2, "category": "label", "subcategory": ""},
                     {"id": 3, "category": "eksport", "subcategory": ""},
                     {"id": 4, "category": "halal", "subcategory": "logo & sijil"}],
           "new_categories": [{"key": "label", "bm": "Label & penandaan", "en": "Labelling", "subs": []},
                              {"key": "eksport", "bm": "Eksport", "en": "Export", "subs": []}]}
    llm = FakeLLM(out)
    settings = {"faq": {}}
    note = faq_sort.run_sort(store, llm, settings, faq.categories(settings))
    assert note == "sort: 4 looked at, 3 moved, 1 new category"
    assert _row(store, 1)["category"] == _row(store, 2)["category"] == "label"
    assert _row(store, 3)["category"] == "lain" and _row(store, 3)["sorted_at"]           # a group of one waits
    assert (_row(store, 4)["category"], _row(store, 4)["subcategory"]) == ("halal", "Logo & sijil")
    assert _row(store, 5)["category"] == "lain" and not _row(store, 5)["sorted_at"]       # Wan's, untouched
    assert "5" not in llm.seen[0][1].split("ENTRIES:")[1].replace("soalan 5", "")
    saved = _saved(store)
    assert any(c["key"] == "label" and c["auto"] for c in saved["categories"])
    logged = [r for r in store.tables["semasa_log"] if r["event"] == "faq.sorted"]
    assert len(logged) == 1 and "kategori baharu: Label & penandaan" in logged[0]["title"]
    # nothing left to look at: no second call to the writer
    assert faq_sort.run_sort(store, llm, _saved_settings(store), faq.categories(_saved_settings(store))) == \
        "sort: nothing to sort" and len(llm.seen) == 1


def _saved_settings(store):
    return {"faq": _saved(store)}


def test_a_deleted_category_is_never_made_again():
    store = FakeStore(semasa_faqs=[_faq(1), _faq(2)],
                      semasa_settings=[{"key": "faq", "value": {"declined": ["Label & penandaan"]}}])
    out = {"items": [{"id": 1, "category": "lbl"}, {"id": 2, "category": "lbl"}],
           "new_categories": [{"key": "lbl", "bm": "Label dan penandaan", "en": "Labels"}]}
    settings = {"faq": {"declined": ["Label & penandaan"]}}
    faq_sort.run_sort(store, FakeLLM(out), settings, faq.categories(settings))
    assert _row(store, 1)["category"] == "lain" and not any(c.get("auto") for c in faq.categories(settings))


def test_without_a_writer_only_orphans_move():
    store = FakeStore(semasa_faqs=[_faq(1), _faq(2, cat="gone", by="wan")], semasa_settings=[])
    note = faq_sort.run_sort(store, FakeLLM(key=""), {}, faq.categories({}))
    assert "1 entry from deleted categories" in note
    assert (_row(store, 2)["category"], _row(store, 2)["category_by"]) == ("lain", "bot")
    assert _row(store, 1)["sorted_at"] is None                                            # still waiting for a writer


def test_a_silent_writer_marks_nothing_so_the_next_run_tries_again():
    store = FakeStore(semasa_faqs=[_faq(1)], semasa_settings=[])
    assert "did not answer" in faq_sort.run_sort(store, FakeLLM(None), {}, faq.categories({}))
    assert _row(store, 1)["sorted_at"] is None


def test_a_changed_list_is_looked_at_again():
    earlier = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    store = FakeStore(semasa_faqs=[_faq(1, sorted_at=earlier)], semasa_settings=[])
    settings = {"faq": {"changed_at": datetime.now(UTC).isoformat()}}
    llm = FakeLLM({"items": [{"id": 1, "category": "halal"}]})
    assert "1 moved" in faq_sort.run_sort(store, llm, settings, faq.categories(settings))


def test_the_sorter_never_raises():
    class Broken:
        def table(self, name):
            raise RuntimeError("boom")
    assert faq_sort.run_sort(Broken(), FakeLLM(), {}, faq.categories({})).startswith("sort: skipped")
