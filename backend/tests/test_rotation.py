"""Hooks and poster looks take their TURN and never repeat (Wan, 20 Nov 2026: "make sure hook sentiasa berubah, tak berulang dan
ikut turutan", and for the posters "follow turn not repeat")."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fakestore import FakeStore

sys.path.insert(0, str(Path(__file__).parent))
from test_hook_bank import CAP, GOOD, Seq  # noqa: E402

from semasa import hook_bank, ideas, rotation  # noqa: E402


def _store(briefs=(), hooks=()):
    """Ideas written for `regulab`, newest first, each with a brief; posts with these hooks, newest first."""
    n = len(briefs)
    rows = [{"id": f"i{k}", "stream": "regulab", "status": "drafted", "brief": b, "updated_at": f"2026-11-{20 - k:02d}T00:00:00Z"}
            for k, b in enumerate(briefs)]
    posts = [{"id": f"p{k}", "stream": "regulab", "hook": h, "created_at": f"2026-11-{20 - k:02d}T00:00:00Z"}
             for k, h in enumerate(hooks)]
    assert n == len(rows)
    return FakeStore(semasa_ideas=rows, semasa_posts=posts, semasa_settings=[{"key": "brand", "value": {}}])


def test_the_turn_goes_round_the_families_so_two_in_a_row_never_share_one():
    order = rotation.shape_order("regulab")
    assert len(order) == 20 and sorted(order) == sorted(r[0] for r in hook_bank.allowed("regulab"))
    fam = {n: f for n, f, _ in hook_bank.numbered()}
    assert order[:4] == [1, 6, 16, 21], "one from each family the company account may use, in turn"
    assert all(fam[a] != fam[b] for a, b in zip(order, order[1:], strict=False))
    assert len(rotation.shape_order("linkedin")) == 25 and rotation.shape_order("linkedin")[:5] == [1, 6, 11, 16, 21]


def test_the_first_post_takes_the_first_shape_and_the_next_takes_the_next_never_the_same():
    assert rotation.turn_for(_store(), "regulab").assigned == 1
    t = rotation.turn_for(_store([{"hook_shape": 1}]), "regulab")
    assert t.assigned == 6 and t.fallbacks == [16, 21]
    t = rotation.turn_for(_store([{"hook_shape": 16}, {"hook_shape": 6}, {"hook_shape": 1}]), "regulab")
    assert t.assigned == 21, "after 16 comes 21, and 16 is not asked for again"


def test_the_turn_never_repeats_inside_its_window_and_goes_all_the_way_round():
    briefs: list[dict] = []
    seen: list[int] = []
    for _ in range(40):
        n = rotation.turn_for(_store(briefs), "regulab").assigned
        assert n not in seen[:8], f"{n} came back after {seen[:8]}"
        seen.insert(0, n)
        briefs.insert(0, {"hook_shape": n})
    assert set(seen) == {r[0] for r in hook_bank.allowed("regulab")}, "every shape gets its turn"


def test_a_shape_from_another_hook_style_does_not_move_the_turn():
    t = rotation.turn_for(_store([{"hook_shape": 16, "hook_style": "other"}]), "regulab")
    assert t.assigned == 1, "the built-in turn starts again: 16 means another shape in another style"


def test_the_writer_is_told_the_shape_the_fallbacks_and_the_latest_hooks():
    t = rotation.turn_for(_store([{"hook_shape": 1}], ["Semua orang cakap A, tapi realitinya B", "Soalan yang takde sapa tanya"]),
                          "regulab")
    hint = t.hint()
    assert "NUMBER 6" in hint and "use shape 16, then 21" in hint
    assert "Semua orang cakap A, tapi realitinya B" in hint and "never echo" in hint
    assert "NOT THIS POST'S TURN" in t.ask_again() and "shape 6" in t.ask_again()
    assert rotation.Turn().hint() == "" and rotation.Turn().permitted == []


def test_the_turn_survives_a_store_that_cannot_answer():
    class Broken:
        def table(self, name):
            raise RuntimeError("down")
    t = rotation.turn_for(Broken(), "regulab")
    assert t.assigned == 1 and t.recent == []
    assert rotation.next_look(Broken(), "regulab") == "hand"


# --- the poster looks ------------------------------------------------------------------------------------------------------


def test_the_looks_follow_the_turn_and_never_repeat():
    looks: list[str] = []
    briefs: list[dict] = []
    for _ in range(33):
        look = rotation.next_look(_store(briefs), "regulab")
        assert look not in looks[:4]
        looks.insert(0, look)
        briefs.insert(0, {"look": look})
    assert looks[-1] == "hand" and looks[-2] == "marker" and looks[-3] == "torn", "in the order of the picker"
    assert set(looks) == set(rotation.LOOK_TURN)


def test_a_hidden_look_is_skipped_and_a_look_off_the_turn_starts_it_again():
    assert rotation.next_look(_store([{"look": "hand"}]), "regulab", ["marker"]) == "torn"
    assert rotation.next_look(_store([{"look": "image"}]), "regulab") == "hand", "image is chosen by hand, not part of the turn"
    every = list(rotation.LOOK_TURN)
    assert rotation.next_look(_store(), "regulab", every) in rotation.LOOK_TURN, "hiding all of them never leaves nothing"


# --- the writer ------------------------------------------------------------------------------------------------------------


def _write(llm, store, **idea):
    idea = {"id": "i9", "stream": "regulab", "source_title": "T", "created_by": "u", "make_media": "none", **idea}
    store.tables["semasa_ideas"].append({**idea, "status": "working", "brief": idea.get("brief", {})})
    return ideas.process_idea(store, llm, idea, ideas.load_settings(store))


@pytest.fixture
def offline(monkeypatch):
    monkeypatch.setattr(ideas, "read_source", lambda url: {"ok": False, "why": "no link", "image": None})


def test_the_writer_is_given_this_posts_shape(offline):
    llm = Seq({**GOOD, "hook": "Takde sapa cakap pasal notifikasi tapi ni sebab aku hantar", "hook_shape": 1,
               "text": {"bm": {"instagram": "Takde sapa cakap pasal notifikasi tapi ni sebab aku hantar. " + CAP}}})
    store = _store([{"hook_shape": 25}], ["Orang lain: sijil dah ada. Aku: masih pikir label"])
    _write(llm, store)
    system = llm.seen[0][0]
    assert "THIS POST'S HOOK SHAPE IS NUMBER 1" in system and "Orang lain: sijil dah ada" in system
    brief = store.tables["semasa_ideas"][-1]["brief"]
    assert brief["hook_shape"] == 1 and len(llm.seen) == 1


def test_a_shape_that_is_not_its_turn_is_asked_for_once_more_and_the_turn_answer_is_used(offline):
    turn = {**GOOD, "hook": "Takde sapa cakap pasal notifikasi tapi ni sebab aku hantar", "hook_shape": 1,
            "text": {"bm": {"instagram": "Takde sapa cakap pasal notifikasi tapi ni sebab aku hantar. " + CAP}}}
    llm = Seq(GOOD, turn)                      # GOOD is built on shape 4: not the turn (1)
    store = _store([{"hook_shape": 25}])
    _write(llm, store)
    assert len(llm.seen) == 2 and "NOT THIS POST'S TURN" in llm.seen[1][1]
    assert store.tables["semasa_ideas"][-1]["brief"]["hook_shape"] == 1


def test_a_writer_that_will_not_take_its_turn_still_gets_the_post_written(offline):
    llm = Seq(GOOD, GOOD)
    store = _store([{"hook_shape": 25}])
    pid = _write(llm, store)
    assert len(llm.seen) == 2 and store.tables["semasa_ideas"][-1]["brief"]["hook_shape"] == 4
    assert any(p["id"] == pid for p in store.tables["semasa_posts"]), "rotation never costs a post"


def test_a_poster_with_no_look_takes_the_next_look_in_the_turn_and_a_chosen_look_is_kept(offline):
    llm = Seq({**GOOD, "hook_shape": 4, "poster": {"title": "Notifikasi", "points": ["Satu"]}})
    store = _store([{"hook_shape": 4, "look": "hand"}])
    _write(llm, store, make_media="image", brief={"format": "poster"})
    assert store.tables["semasa_ideas"][-1]["brief"]["look"] == "marker"
    job = next(m for m in store.tables["media_generations"] if (m.get("meta") or {}).get("design") == "poster")
    assert job["meta"]["look"] == "marker"
    llm = Seq({**GOOD, "hook_shape": 4, "poster": {"title": "Notifikasi", "points": ["Satu"]}})
    store = _store([{"hook_shape": 4, "look": "hand"}])
    _write(llm, store, make_media="image", brief={"format": "poster", "look": "neon"})
    assert store.tables["semasa_ideas"][-1]["brief"]["look"] == "neon", "Wan's own choice wins"


def test_the_linkedin_writer_wants_numbered_facts_and_no_follow_line_or_self_label():
    p = ideas.LINKEDIN_SYSTEM
    assert "NUMBERED LIST" in p and "5 to 8 points" in p and "250 to 380 words" in p
    assert "no \"follow me\"" in p and "as a chemist" in p and "never address the reader by job title" in p
    assert "invitation to follow him" not in p and "Follow me for more like this" not in p
