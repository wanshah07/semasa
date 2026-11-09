"""Wan, 9 Nov 2026: (1) LinkedIn is English all the way down, (2) one event is one idea whatever the headline, (3) a news story
needs no rule, (4) a hook too long for the cover is shortened once."""

import pytest
from fakestore import FakeStore

from semasa import autofill, hook_bank, ideas, language
from semasa.config import LLMSettings
from semasa.llm import LLM

BRAND = {"regulab": {"slots": ["08:00"], "schedule": {str(d): ["kosmetik"] for d in range(7)}},
         "linkedin": {"slots": ["06:00", "19:00"], "angles": {"A": "Regulatory change"}}}


class Seq(LLM):
    """Answers each ask with the next answer in the list (the last one repeats), and remembers what it was asked."""

    def __init__(self, *answers):
        super().__init__(LLMSettings(provider="openai", api_key="k", base_url="https://x/v1", model="m", timeout=5))
        self.answers, self.seen = list(answers), []

    def chat_json(self, system, user, **kw):
        self.seen.append((system, user))
        return self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]


def _store():
    return FakeStore(semasa_settings=[{"key": "brand", "value": BRAND}, {"key": "publishing", "value": {"enabled": False}}],
                     semasa_posts=[], media_generations=[], semasa_ideas=[])


def _li(hook="The thing nobody tells you: KKM acts before the report.", slides=None, **kw):
    cap = hook + "\n\nKKM can sample a product on one complaint.\n\nFollow me for more like this."
    out = {"fit": True, "hook": hook, "hook_shape": 3, "angle": "A", "citation": "Food Act 1983",
           "text": {"en": {"linkedin": cap}}, "visual_prompt": "a lab", "alt": "a lab"}
    if slides is not None:
        out["slides"] = slides
    return {**out, **kw}


EN_SLIDES = [{"title": "The thing nobody tells you: KKM acts before the report.", "points": []}] + [
    {"title": "What is *confirmed*", "lead": "KKM is investigating one complaint.", "points": ["One bread product."]},
    {"title": "The takeaway", "lead": "The clock starts at the complaint.", "points": ["Not at the report."]}]
MY_SLIDES = [{"title": "Benda pasal siasatan aduan makanan yg takde sapa bagitau kau", "points": []}] + EN_SLIDES[1:]


def _idea(**brief):
    return {"id": "i1", "stream": "linkedin", "source_title": "KKM siasat aduan", "created_by": "u", "make_media": "none",
            "brief": {"format": "carousel", **brief}}


@pytest.fixture(autouse=True)
def _no_net(monkeypatch):
    monkeypatch.setattr(ideas, "read_source", lambda url: {"ok": False, "why": "x", "image": None})


# --- 1. English only ---------------------------------------------------------------------------------------------------

def test_malay_is_found_in_short_text_and_english_is_left_alone():
    assert language.is_malay("Benda pasal siasatan aduan makanan yg takde sapa bagitau kau")       # casual markers
    assert language.is_malay("Aduan bukan pembuka perbualan. Aduan adalah *pencetus*.")
    assert language.is_malay("Semua produk ini dan itu")                                          # two function words
    assert not language.is_malay("KKM acts on one complaint, before any report")
    assert not language.is_malay("Read the x-ray report at example.org")                          # letters of a URL or a word
    assert not language.is_malay("Halal certificates must match import permits.")
    assert language.malay_fields({"hook": "ok hook", "slides": MY_SLIDES}) == ["slide 1"]
    assert language.malay_fields(_li(slides=EN_SLIDES)) == []


def test_a_malay_hook_and_cover_on_linkedin_are_asked_again_in_english():
    store = _store()
    bad = _li(hook="Benda pasal siasatan aduan makanan yg takde sapa bagitau kau: KKM terus ambil sampel", slides=MY_SLIDES)
    llm = Seq(bad, _li(slides=EN_SLIDES))
    pid = ideas.process_idea(store, llm, _idea(), ideas.load_settings(store))
    post = store.tables["semasa_posts"][0]
    assert post["id"] == pid and post["hook"].startswith("The thing nobody tells you")
    assert not language.malay_fields({"hook": post["hook"], "slides": post["slides"]})
    assert len(llm.seen) == 2 and "MUST BE ENGLISH" in llm.seen[1][1] and "hook, slide 1" in llm.seen[1][1]


def test_a_linkedin_answer_that_stays_malay_fails_with_a_reason_and_writes_no_draft():
    store = _store()
    bad = _li(hook="Benda pasal siasatan aduan makanan yg takde sapa bagitau kau: KKM ambil sampel", slides=MY_SLIDES)
    with pytest.raises(ideas.IdeaError, match="Malay on a LinkedIn post"):
        ideas.process_idea(store, Seq(bad), _idea(), ideas.load_settings(store))
    assert store.tables["semasa_posts"] == []


def test_ws_regulab_keeps_its_malay_hook_and_is_never_asked_to_translate():
    store = _store()
    cap = "Benda pasal sunscreen yg takde sapa bagitau kau: ya, masuk darah.\n\nFollow untuk tip regulatori."
    out = {"fit": True, "hook": "Benda pasal sunscreen yg takde sapa bagitau kau: ya, masuk darah", "hook_shape": 3,
           "domain": "kosmetik", "citation": "NPRA", "text": {"bm": {"instagram": cap, "facebook": cap, "threads": cap}},
           "visual_prompt": "x", "alt": "x"}
    llm = Seq(out)
    idea = {"id": "i1", "stream": "regulab", "source_title": "T", "created_by": "u", "make_media": "none"}
    ideas.process_idea(store, llm, idea, ideas.load_settings(store))
    assert len(llm.seen) == 1 and store.tables["semasa_posts"][0]["hook"].startswith("Benda pasal")


def test_the_linkedin_prompt_says_english_only():
    system, _ = ideas.build_request({"stream": "linkedin", "source_title": "t"}, {"ok": False}, BRAND)
    assert "ENGLISH ONLY" in system and "never print the" in system


# --- 4. a hook too long for the cover ----------------------------------------------------------------------------------------

LONG = "The thing nobody tells you about a food complaint investigation is that KKM acts before the full report lands"


def test_a_hook_too_long_for_the_cover_is_shortened_once_and_the_cover_wears_it():
    store = _store()
    slides = [{"title": "Something else the writer put on the cover", "points": []}] + EN_SLIDES[1:]
    llm = Seq(_li(hook=LONG, slides=slides), {"hook": "KKM acts before the full report lands"})
    ideas.process_idea(store, llm, _idea(), ideas.load_settings(store))
    post = store.tables["semasa_posts"][0]
    assert post["slides"][0]["title"] == "KKM acts before the full report lands"
    assert post["hook"] == LONG                                                  # the caption keeps its own first line
    assert len(llm.seen) == 2


def test_a_shortening_that_is_still_too_long_or_malay_leaves_the_cover_as_the_writer_drew_it():
    for bad in ({"hook": LONG}, {"hook": "Benda pasal aduan yg takde sapa bagitau kau"}, None, {"hook": ""}):
        store = _store()
        slides = [{"title": "Writer's own cover", "points": []}] + EN_SLIDES[1:]
        llm = Seq(_li(hook=LONG, slides=slides), bad)
        ideas.process_idea(store, llm, _idea(), ideas.load_settings(store))
        assert store.tables["semasa_posts"][0]["slides"][0]["title"] == "Writer's own cover"
        assert len(llm.seen) == 2                                                # one try, never a loop


def test_a_cover_that_already_wears_the_hook_costs_no_extra_ask():
    store = _store()
    slides = [{"title": LONG, "points": []}] + EN_SLIDES[1:]
    llm = Seq(_li(hook=LONG, slides=slides))
    ideas.process_idea(store, llm, _idea(), ideas.load_settings(store))
    assert len(llm.seen) == 1
    assert hook_bank.cover([{"title": "x", "points": []}], LONG)[1] == "too_long"


# --- 2. the same event under another headline --------------------------------------------------------------------------------

H1 = "Sijil halal meragukan, AKPS Pelabuhan Klang sita daging kerbau bernilai RM413,728"
H2 = "Kesan sijil halal meragukan, AKPS sita daging kerbau bernilai RM413,728"
H3 = "Sijil halal tidak sepadan dengan permit, daging kerbau dari India disita"


def _rows(*titles):
    return [{"title": t, "url": f"https://x/{i}"} for i, t in enumerate(titles)]


def test_three_headlines_for_one_seizure_are_one_story():
    keys = [autofill.story_tokens(autofill.story_key(t)) for t in (H1, H2, H3)]
    assert autofill.same_event(keys[0], keys[1]) and autofill.same_event(keys[0], keys[2])
    assert [r["title"] for r in autofill.one_per_story(_rows(H1, H2, H3))] == [H1]


def test_a_story_a_rejected_or_written_idea_already_used_is_dropped_even_reworded():
    spent = {autofill.story_key(H1)}
    assert autofill.one_per_story(_rows(H2, H3), spent) == []
    assert [r["title"] for r in autofill.one_per_story(_rows(H2, "NPRA batalkan notifikasi tiga krim"), spent)] == [
        "NPRA batalkan notifikasi tiga krim"]


def test_two_different_stories_that_share_a_regulator_and_a_food_are_kept_apart():
    a = "KKM siasat aduan keracunan makanan membabitkan produk roti"
    b = "KKM tarik balik produk roti tertentu"
    c = "Sijil halal tiruan: JAKIM siasat dua syarikat makanan"
    assert len(autofill.one_per_story(_rows(a, b, c))) == 3


def test_the_papers_own_link_still_beats_a_google_news_link_for_a_reworded_twin():
    rows = [{"title": H1, "url": "https://news.google.com/rss/articles/abc"}, {"title": H3, "url": "https://bernama.com/a"}]
    assert autofill.one_per_story(rows)[0]["url"] == "https://bernama.com/a"
