"""Wan, 9 Nov 2026: a name-weighted duplicate match, and the writer asked whether a new auto-fill story is an event the stream has
already written up (words cannot link two reports of one incident that share no name)."""

import pytest
from fakestore import FakeStore

from semasa import autofill, ideas
from semasa.config import LLMSettings
from semasa.llm import LLM

P = autofill.story_profile

RECALL = P("Gardenia tarik balik roti gandum", "Gardenia Bakeries menarik balik roti gandum selepas aduan pengguna.")
STOP_SALE = P("KKM arah Gardenia henti jual roti gandum",
              "Roti gandum Gardenia dihentikan jualan selepas aduan pengguna di Selangor.")
LAUNCH = P("Gardenia lancar roti baharu perisa pandan", "Gardenia Bakeries melancarkan roti perisa pandan edisi terhad.")
FACTORY = P("KKM akan periksa kilang Gardenia susulan dakwaan keracunan makanan",
            "KKM akan memeriksa kilang Gardenia Bakeries bagi mengesahkan pematuhan Akta Makanan 1983 susulan dakwaan keracunan "
            "makanan, sementara menunggu keputusan analisis makmal.")
ROTI = P("KKM siasat aduan keracunan makanan membabitkan produk roti | Sinar Harian",
         "KKM menyiasat aduan keracunan makanan yang membabitkan produk roti.")


# --- the name-weighted match -------------------------------------------------------------------------------------------------

def test_names_are_found_from_the_original_case_and_a_repeated_opening_company_counts():
    assert "gardenia" in RECALL[2] and "bakeries" in RECALL[2]          # opens both sentences, so it is a name
    assert "gardenia" in STOP_SALE[2] and "roti" not in STOP_SALE[2]    # an ordinary word that merely opens a sentence is not
    assert "rm413728" in P("AKPS sita daging bernilai RM413,728")[2]    # an amount identifies an event
    assert not (P("Kesan sijil halal meragukan")[2])                    # "Kesan" opens the headline once: a word, not a name


def test_a_shared_name_plus_three_more_shared_words_is_the_same_event_even_when_the_headlines_differ():
    assert autofill.same_story_profile(RECALL, STOP_SALE)


def test_a_company_in_two_different_stories_is_not_one_story():
    assert not autofill.same_story_profile(RECALL, LAUNCH)              # recall vs a new flavour
    assert not autofill.same_story_profile(LAUNCH, FACTORY)
    assert not autofill.same_story_profile(RECALL, FACTORY)             # a recall vs a factory inspection


def test_reports_that_share_no_name_are_left_to_the_writer_check():
    """The roti complaint and the Gardenia factory check are one incident, and no word links them (the roti report never names
    the company). Words stop here on purpose; same_event_written is what asks."""
    assert not autofill.same_story_profile(ROTI, FACTORY)


def test_one_per_story_uses_summaries_and_names_for_the_pool_and_for_what_was_already_written():
    rows = [{"title": "Gardenia tarik balik roti gandum", "summary": "Gardenia Bakeries menarik balik roti gandum selepas aduan.",
             "url": "https://a/1"},
            {"title": "KKM arah Gardenia henti jual roti gandum",
             "summary": "Roti gandum Gardenia dihentikan jualan selepas aduan.",
             "url": "https://b/2"},
            {"title": "Gardenia lancar roti baharu perisa pandan", "summary": "Gardenia Bakeries melancarkan roti perisa pandan.",
             "url": "https://c/3"}]
    assert [r["url"] for r in autofill.one_per_story(rows)] == ["https://a/1", "https://c/3"]
    assert [r["url"] for r in autofill.one_per_story(rows, set(), [RECALL])] == ["https://c/3"]


def test_used_profiles_reads_the_ideas_made_lately_and_never_raises():
    store = FakeStore(semasa_ideas=[{"id": "i1", "source_title": "Gardenia tarik balik roti gandum",
                                     "source_summary": "Gardenia Bakeries menarik balik roti.",
                                     "created_at": "2026-11-09T10:00:00+00:00"}])
    got = autofill.used_profiles(store)
    assert isinstance(got, list)

    class Broken:
        def table(self, *_):
            raise RuntimeError("down")
    assert autofill.used_profiles(Broken()) == []


# --- the writer check --------------------------------------------------------------------------------------------------------

class Seq(LLM):
    def __init__(self, *answers):
        super().__init__(LLMSettings(provider="openai", api_key="k", base_url="https://x/v1", model="m", timeout=5))
        self.answers, self.seen = list(answers), []

    def chat_json(self, system, user, **kw):
        self.seen.append((system, user))
        a = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(a, Exception):
            raise a
        return a


def _store(*earlier):
    rows = [{"id": f"e{i}", "stream": s, "status": st, "source_title": t, "source_summary": "",
             "created_at": "2099-01-01T00:00:00+00:00"}
            for i, (s, st, t) in enumerate(earlier)]
    return FakeStore(semasa_ideas=rows)


def _idea(**kw):
    return {"id": "new", "stream": "linkedin", "source_title": "KKM akan periksa kilang Gardenia",
            "source_summary": "KKM akan memeriksa kilang Gardenia Bakeries.", "brief": {"auto": True}, **kw}


def test_the_writer_is_asked_and_a_match_names_the_earlier_story():
    store = _store(("linkedin", "drafted", "KKM siasat aduan keracunan makanan membabitkan produk roti"),
                   ("linkedin", "drafted", "Sijil halal tiruan: JAKIM siasat"))
    llm = Seq({"same_as": 1, "why": "the same complaint"})
    assert ideas.same_event_written(store, llm, _idea()).startswith("KKM siasat aduan keracunan makanan")
    system, user = llm.seen[0]
    assert "SAME event" in system and "1. KKM siasat" in user and "NEW: KKM akan periksa kilang Gardenia" in user


def test_no_match_a_wrong_number_or_a_broken_answer_writes_the_post():
    store = _store(("linkedin", "drafted", "KKM siasat aduan keracunan makanan membabitkan produk roti"))
    for answer in ({"same_as": 0}, {"same_as": 7}, {"same_as": "abc"}, None, {"fit": True}, RuntimeError("down")):
        assert ideas.same_event_written(store, Seq(answer), _idea()) == ""


def test_only_the_same_stream_and_only_written_ideas_are_compared():
    store = _store(("regulab", "drafted", "KKM siasat aduan keracunan makanan membabitkan produk roti"),
                   ("linkedin", "error", "KKM siasat aduan roti"))
    llm = Seq({"same_as": 1})
    assert ideas.same_event_written(store, llm, _idea()) == ""
    assert llm.seen == []                                       # nothing to compare, so the writer is never asked


def test_wans_own_clicks_and_noted_retries_are_never_judged():
    store = _store(("linkedin", "drafted", "KKM siasat aduan keracunan makanan membabitkan produk roti"))
    for kw in ({"brief": {"format": "carousel"}}, {"brief": {"auto": True}, "note": "a follow-up on the factory check"}):
        llm = Seq({"same_as": 1})
        assert ideas.same_event_written(store, llm, _idea(**kw)) == "" and llm.seen == []


def test_process_idea_refuses_a_same_event_idea_with_a_reason_and_writes_no_draft(monkeypatch):
    monkeypatch.setattr(ideas, "read_source", lambda url: {"ok": False, "why": "x", "image": None})
    store = FakeStore(semasa_settings=[{"key": "brand", "value": {}}], semasa_posts=[], media_generations=[],
                      semasa_ideas=[{"id": "e1", "stream": "linkedin", "status": "drafted",
                                     "created_at": "2099-01-01T00:00:00+00:00",
                                     "source_title": "KKM siasat aduan keracunan makanan membabitkan produk roti",
                                     "source_summary": ""}])
    with pytest.raises(ideas.IdeaError, match="same event is already written up"):
        ideas.process_idea(store, Seq({"same_as": 1}), _idea(), {})
    assert store.tables["semasa_posts"] == []
