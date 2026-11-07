"""The 25 hook shapes are REQUIRED in every post (Wan, 6 Nov 2026: "make sure 25 hook tu wajib dalam ayat").

Each test names a behaviour: the writer is always given the shapes its stream may use, a post without a valid shape is asked for
again once and then fails with a reason, the company account never gets the first-person family, and the standing rules still
outrank the shapes.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fakestore import FakeStore  # noqa: E402

from semasa import hook_bank, ideas  # noqa: E402
from semasa.config import LLMSettings  # noqa: E402
from semasa.llm import LLM  # noqa: E402


def _request(stream="regulab", family=None, writer=None):
    idea = {"id": "i", "stream": stream, "source_title": "T", "hook_family": family}
    source = {"ok": False, "why": "no link", "image": None}
    return ideas.build_request(idea, source, {}, writer=writer)


def test_all_twenty_five_shapes_are_kept_and_numbered_in_series_order():
    assert sum(len(v) for v in ideas.HOOK_FAMILIES.values()) == 25
    assert set(ideas.HOOK_FAMILIES) == {"curiosity", "transform", "vulnerable", "bold", "relatable"}
    rows = hook_bank.numbered()
    assert [r[0] for r in rows] == list(range(1, 26))
    assert rows[0][1:] == ("curiosity", "Takde sapa cakap pasal ___ tapi ni sebab aku ___")
    assert rows[10][1] == "vulnerable" and rows[15][1] == "bold"
    assert rows[24][1:] == ("relatable", "Org lain: ___. Aku: masih figuring out ___")


def test_every_post_is_given_the_shapes_even_when_no_family_is_named():
    for family in (None, "", "zzz"):
        system, _ = _request(family=family)
        assert "HOOK SHAPE (REQUIRED" in system and "MUST be built on exactly one" in system
        assert "RELATABLE:" in system and "Semua org ckp ___ tapi realitinya ___" in system


def test_a_named_family_narrows_the_shapes_but_stays_required():
    system, _ = _request(family="bold")
    assert "HOOK SHAPE (REQUIRED" in system and "BOLD:" in system and "RELATABLE:" not in system
    assert "16. Semua org ckp ___ tapi realitinya ___" in system


def test_the_company_account_never_gets_the_first_person_family():
    for family in (None, "vulnerable"):
        system, _ = _request(family=family)
        assert "Takde sapa nampak part mana aku" not in system and "VULNERABLE:" not in system
    assert {r[1] for r in hook_bank.allowed("regulab")} == {"curiosity", "transform", "bold", "relatable"}
    assert len(hook_bank.allowed("regulab")) == 20 and len(hook_bank.allowed("linkedin")) == 25


def test_the_first_person_family_does_reach_the_linkedin_stream():
    system, _ = _request(stream="linkedin", family="vulnerable")
    assert "14. Takde sapa nampak part mana aku ___" in system
    assert "faithful translation" in system                          # an English post translates the shape, never copies it


def test_the_shapes_never_lift_the_standing_rules():
    system, _ = _request(family="transform")
    # the rule that forbids an invented figure must still be present, and must be stated before the block that offers the shapes
    assert system.index("no fee, duration, circular") < system.index("HOOK SHAPE")
    assert "Never fill a blank with a figure" in system and "never keep the underscores" in system
    assert "RELATABLE or CURIOSITY shape" in system                   # a way out when a shape cannot be filled honestly


def test_house_style_still_cannot_lift_a_rule():
    writer = {"regulab": {"voice": "tenang", "never": ["halal-friendly"]}}
    system, _ = _request(family="relatable", writer=writer)
    assert "HOUSE STYLE" in system
    assert system.index("HOUSE STYLE") < system.index("HOOK SHAPE")
    assert "It adds to the rules above and never lifts one" in system


def test_both_writers_ask_for_the_shape_number_in_their_answer():
    assert '"hook_shape"' in ideas.REGULAB_SYSTEM and '"hook_shape"' in ideas.LINKEDIN_SYSTEM


def test_declared_accepts_only_a_usable_shape():
    ok = {"hook": "Ni apa sebenarnya jadi bila kau tukar label", "hook_shape": 4}
    assert hook_bank.declared(ok, "regulab") == 4 and hook_bank.declared({**ok, "hook_shape": "4"}, "regulab") == 4
    assert hook_bank.declared({**ok, "hook_shape": 0}, "regulab") is None
    assert hook_bank.declared({**ok, "hook_shape": 26}, "regulab") is None
    assert hook_bank.declared({**ok, "hook_shape": None}, "regulab") is None
    assert hook_bank.declared({**ok, "hook_shape": "abc"}, "regulab") is None
    assert hook_bank.declared({"hook": "x"}, "regulab") is None and hook_bank.declared(None, "regulab") is None
    assert hook_bank.declared({**ok, "hook": ""}, "regulab") is None
    assert hook_bank.declared({**ok, "hook": "Stop buat ___ kalau kau nak ___"}, "regulab") is None, "blanks left in the hook"
    assert hook_bank.declared({**ok, "hook_shape": 12}, "regulab") is None, "a confession on the company account"
    assert hook_bank.declared({**ok, "hook_shape": 12}, "linkedin") == 12
    assert hook_bank.declared({**ok, "hook_shape": 4}, "regulab", family="bold") is None, "outside the family the idea named"


def test_lead_matches_ignores_case_spacing_and_punctuation():
    assert hook_bank.lead_matches("Stop buat ini, kalau kau nak sihat!", "stop buat ini kalau kau nak sihat. Lagi satu perkara.")
    assert not hook_bank.lead_matches("Stop buat ini kalau kau nak sihat", "Perkara lain sepenuhnya di sini")
    assert not hook_bank.lead_matches("", "anything")


# ---- the writer is held to it ----------------------------------------------------------------------------------------------

class Seq(LLM):
    """Answers in turn, remembering what it was asked."""

    def __init__(self, *answers):
        super().__init__(LLMSettings(provider="openai", api_key="k", base_url="https://x/v1", model="m", timeout=5))
        self.answers, self.seen = list(answers), []

    def chat_json(self, system, user, **kw):
        self.seen.append((system, user))
        return self.answers.pop(0) if self.answers else None


CAP = "Notifikasi kosmetik bukan kelulusan produk."
GOOD = {"fit": True, "hook": "Ni apa sebenarnya jadi bila kau hantar notifikasi", "hook_shape": 4, "domain": "kosmetik",
        "citation": "NPRA", "text": {"bm": {"instagram": "Ni apa sebenarnya jadi bila kau hantar notifikasi. " + CAP}}}


def _store():
    return FakeStore(semasa_settings=[{"key": "brand", "value": {}}, {"key": "publishing", "value": {"enabled": False}}],
                     semasa_posts=[], media_generations=[], semasa_ideas=[])


def _write(llm, monkeypatch):
    monkeypatch.setattr(ideas, "read_source", lambda url: {"ok": False, "why": "no link", "image": None})
    store = _store()
    idea = {"id": "i1", "stream": "regulab", "source_title": "T", "created_by": "u", "make_media": "none"}
    store.tables["semasa_ideas"].append({**idea, "status": "working"})
    return store, ideas.process_idea(store, llm, idea, ideas.load_settings(store))


def test_a_post_with_a_valid_shape_is_written_and_the_shape_is_kept_on_the_idea(monkeypatch):
    llm = Seq(GOOD)
    store, pid = _write(llm, monkeypatch)
    brief = store.tables["semasa_ideas"][0]["brief"]
    assert brief["hook_shape"] == 4 and brief["hook_in_caption"] is True and len(llm.seen) == 1
    assert store.tables["semasa_posts"][0]["id"] == pid


def test_a_missing_shape_is_asked_for_once_more_and_the_second_answer_is_used(monkeypatch):
    llm = Seq({**GOOD, "hook_shape": None}, GOOD)
    store, _ = _write(llm, monkeypatch)
    assert len(llm.seen) == 2 and "DID NOT USE A HOOK SHAPE" in llm.seen[1][1] and "DID NOT USE" not in llm.seen[0][1]
    assert store.tables["semasa_ideas"][0]["brief"]["hook_shape"] == 4


def test_two_answers_without_a_shape_fail_the_idea_with_a_reason_and_write_no_post(monkeypatch):
    llm = Seq({**GOOD, "hook_shape": 99}, {**GOOD, "hook": "Stop buat ___ kalau kau nak ___"})
    monkeypatch.setattr(ideas, "read_source", lambda url: {"ok": False, "why": "no link", "image": None})
    store = _store()
    with pytest.raises(ideas.IdeaError, match="25 hook shapes"):
        ideas.process_idea(store, llm, {"id": "i1", "stream": "regulab", "source_title": "T", "make_media": "none"}, {})
    assert store.tables["semasa_posts"] == [] and len(llm.seen) == 2


def test_a_revision_is_held_to_it_too_and_an_unfit_answer_is_never_asked_again(monkeypatch):
    post = {"id": "p1", "stream": "regulab", "lang": "bm", "status": "draft", "domain": "kosmetik", "hook": "Lama",
            "citation": "NPRA", "text": {"bm": {"instagram": "Lama."}}, "revise_note": "pendekkan", "revise_state": "working"}
    store = _store()
    store.tables["semasa_posts"] = [post]
    llm = Seq({"fit": True, "hook": "Baru", "text": {"bm": {"instagram": "Baru."}}})
    with pytest.raises(ideas.IdeaError, match="25 hook shapes"):
        ideas.revise_one(store, llm, post, ideas.load_settings(store))
    assert store.tables["semasa_posts"][0]["hook"] == "Lama" and len(llm.seen) == 2
    assert "HOOK SHAPE (REQUIRED" in llm.seen[0][0]
    again = Seq({"fit": True, "hook": "Baru", "text": {"bm": {"instagram": "Baru."}}},
                {"fit": True, "hook": "Cuba nak jelaskan notifikasi sambil minum kopi be like", "hook_shape": 24,
                 "text": {"bm": {"instagram": "Cuba nak jelaskan notifikasi sambil minum kopi be like."}}})
    ideas.revise_one(store, again, post, ideas.load_settings(store))
    assert store.tables["semasa_posts"][0]["hook"].startswith("Cuba nak jelaskan")


# ---- the cover slide and the poster wear the hook (7 Nov 2026) --------------------------------------------------------------

def test_a_cover_that_already_opens_with_the_hook_is_kept_and_one_that_does_not_is_set_to_it():
    hook = "Stop buat label sendiri kalau nak produk selamat"
    kept = [{"title": "Stop buat *label* sendiri kalau nak produk selamat", "points": []}, {"title": "Fakta", "points": ["a"]}]
    assert hook_bank.cover(kept, hook) == (kept, "kept")
    other = [{"title": "Tentang label", "points": ["x"]}, {"title": "Fakta", "points": ["a"]}]
    got, state = hook_bank.cover(other, hook)
    assert state == "set" and got[0] == {"title": hook, "points": ["x"]} and got[1] == other[1], "the rest is untouched"
    assert other[0]["title"] == "Tentang label", "the input is not changed"


def test_a_hook_too_long_for_a_headline_or_with_blanks_left_leaves_the_cover_alone():
    items = [{"title": "Tentang label", "points": []}]
    long_hook = " ".join(["perkataan"] * 14)
    assert hook_bank.cover(items, long_hook) == (items, "too_long")
    assert hook_bank.cover(items, "Stop buat ___ kalau nak ___") == (items, "")
    assert hook_bank.cover(items, "") == (items, "") and hook_bank.cover([], "Hook") == ([], "")


def test_the_slide_and_poster_rules_ask_for_the_hook_on_the_cover():
    for stream in ("regulab", "linkedin"):
        assert "headline IS the hook" in ideas.SLIDES_RULES[stream]
        assert "same hook shape you filled" in ideas.POSTER_RULES[stream]
