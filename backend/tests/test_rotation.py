"""Hooks and poster looks take their TURN and never repeat (Wan, 20 Nov 2026: "make sure hook sentiasa berubah, tak berulang dan
ikut turutan", and for the posters "follow turn not repeat")."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fakestore import FakeStore

sys.path.insert(0, str(Path(__file__).parent))
from test_hook_bank import CAP, GOOD, Seq  # noqa: E402

from semasa import compliance, hook_bank, ideas, rotation  # noqa: E402


def _store(briefs=(), hooks=(), stream="regulab"):
    """Ideas written for `regulab`, newest first, each with a brief; posts with these hooks, newest first."""
    n = len(briefs)
    rows = [{"id": f"i{k}", "stream": stream, "status": "drafted", "brief": b, "updated_at": f"2026-11-{20 - k:02d}T00:00:00Z"}
            for k, b in enumerate(briefs)]
    posts = [{"id": f"p{k}", "stream": stream, "hook": h, "created_at": f"2026-11-{20 - k:02d}T00:00:00Z"}
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
    assert rotation.next_look(Broken(), "regulab") == "classic"


# --- the poster looks ------------------------------------------------------------------------------------------------------


def test_the_looks_follow_the_turn_and_never_repeat():
    looks: list[str] = []
    briefs: list[dict] = []
    for _ in range(33):
        look = rotation.next_look(_store(briefs), "regulab")
        assert look not in looks[:4]
        looks.insert(0, look)
        briefs.insert(0, {"look": look})
    assert looks[-4:][::-1] == ["classic", "hand", "marker", "torn"], "in the order of the picker, Semasa's own first"
    assert set(looks) == set(rotation.LOOK_TURN)


def test_linkedin_and_ws_regulab_each_take_their_own_turn_through_the_posters():
    # Wan, 21 Nov 2026: "check if linkedn and ws regulab post will auto use these posters, ikut turn, bukan repeat"
    for stream in ("linkedin", "regulab"):
        briefs: list[dict] = []
        looks: list[str] = []
        for _ in range(len(rotation.LOOK_TURN)):
            look = rotation.next_look(_store(briefs, stream=stream), stream)
            looks.append(look)
            briefs.insert(0, {"look": look})
        assert looks == list(rotation.LOOK_TURN), stream
        assert len(set(looks[:4])) == 4, "no look repeats within a few posts"


def test_a_hidden_look_is_skipped_and_a_look_off_the_turn_starts_it_again():
    assert rotation.next_look(_store([{"look": "hand"}]), "regulab", ["marker"]) == "torn"
    assert rotation.next_look(_store([{"look": "chalk"}]), "regulab") == "metro", "where the live queue stands after chalk"
    assert rotation.next_look(_store([{"look": "photo"}]), "regulab") == "classic", "photo needs a picture: not in the turn"
    assert rotation.next_look(_store([{"look": "image"}]), "regulab") == "journal", "Diari follows Image (Wan, 23 Nov 2026)"
    assert rotation.next_look(_store([{"look": "journal"}]), "regulab") == "classic", "the turn closes on Diari, then restarts"
    assert rotation.LOOK_TURN == ("classic", "hand", "marker", "torn", "block", "neon", "deck", "chalk", "metro", "strip",
                                  "grid", "image", "journal")
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
    assert "NUMBERED LIST" in p and "6 to 10 points" in p and "350 to 500 words" in p and "1500 characters" in p
    assert "no \"follow me\"" in p and "as a chemist" in p and "never address the reader by job title" in p
    assert "invitation to follow him" not in p and "Follow me for more like this" not in p


def test_a_linkedin_poster_is_drawn_on_plain_paper_even_when_the_post_has_a_picture(offline):
    assert ideas.slide_ground("linkedin", True) == "none" and ideas.slide_ground("linkedin", False) == "none"
    assert ideas.slide_ground("regulab", True) == "post_image" and ideas.slide_ground("regulab", False) == "none"
    english = {"fit": True, "hook": "Here is what a notification does and does not do", "hook_shape": 4, "angle": "A",
               "citation": "NPRA",
               "text": {"en": {"linkedin": "Here is what a notification does and does not do. It is not approval."}},
               "poster": {"title": "Notification", "points": ["One"]}}
    llm = Seq(english)
    store = _store([{"hook_shape": 4, "look": "hand"}], stream="linkedin")
    _write(llm, store, stream="linkedin", make_media="image", brief={"format": "poster"})
    job = next(m for m in store.tables["media_generations"] if (m.get("meta") or {}).get("design") == "poster")
    assert job["meta"]["look"] == "marker", "LinkedIn takes its turn through the posters: marker follows hand"
    assert job["meta"]["bg"] == "none"


# --- no single picture card (Wan, 21 Nov 2026: "for ws regulab and linkend no more image single card, because too ugly") ---


def test_an_idea_with_no_format_is_a_poster_never_a_single_picture():
    assert ideas.format_of({"stream": "regulab"}) == "poster" and ideas.format_of({"stream": "linkedin"}) == "poster"
    assert ideas.format_of({"stream": "regulab", "make_slides": True}) == "carousel"
    assert ideas.format_of({"brief": {"format": "comic"}}) == "comic"
    assert ideas.format_of({"brief": {"format": "carousel"}}) == "carousel"


def _modes(store):
    return sorted(str(m.get("mode")) for m in store.tables["media_generations"])


def test_a_poster_and_a_carousel_are_written_with_no_ai_picture_beside_them(offline):
    poster = {**GOOD, "hook_shape": 4, "poster": {"title": "Notifikasi", "points": ["Satu"]}}
    store = _store([{"hook_shape": 4, "look": "hand"}])
    _write(Seq(poster), store, make_media="image", brief={"format": "poster"})
    assert _modes(store) == ["slides"], "one poster job and no 'recreate' or 'prompt' picture"
    carousel = {**GOOD, "hook_shape": 4, "slides": [{"title": "Satu", "points": ["a"]}, {"title": "Dua", "points": ["b"]}]}
    store = _store([{"hook_shape": 4, "look": "hand"}])
    _write(Seq(carousel), store, make_media="image", make_slides=True)
    assert _modes(store) == ["slides"], "one slides job and no picture"


def test_a_post_the_writer_gave_no_poster_for_still_gets_a_poster_never_an_ai_picture_alone(offline):
    store = _store([{"hook_shape": 4, "look": "hand"}])
    answer = {**GOOD, "hook_shape": 4, "visual_prompt": "a bottle on a table"}
    _write(Seq(answer), store, make_media="image", brief={"format": "poster"})
    # no poster came back: the poster is asked for from the caption, or built from it, and drawn (Wan, 23 Nov 2026: "make
    # sure its poster not only generated image"); an AI picture is never the post's artwork on its own
    assert _modes(store) == ["slides"]
    assert [j["mode"] for j in store.tables["media_generations"]].count("prompt") == 0


def test_a_crowded_slide_is_drawn_as_two_when_no_look_can_fit_it():
    from semasa import carousel
    slide = {"title": "Trial", "points": ["a one", "b two", "c three", "d four", "e five"]}
    out = carousel.split_full([slide])
    assert [s["title"] for s in out] == ["Trial (1/2)", "Trial (2/2)"]
    assert [p for s in out for p in s["points"]] == slide["points"]      # every word kept
    assert carousel.split_full([{"title": "T", "points": ["a", "b", "c"]}]) == [{"title": "T", "points": ["a", "b", "c"]}]
    verse = {"title": "V", "points": list("abcde"), "ayat": {"surah": 1}}
    assert carousel.split_full([verse]) == [verse]                        # a verse is never split


@pytest.mark.caption_floor
def test_a_caption_under_its_floor_is_asked_again_for_more_facts():
    short = "Notifikasi bukan kelulusan. NPRA menyemak selepas produk dipasarkan."
    longer = "Notifikasi bukan kelulusan.\n" + "\n".join(f"{n}. NPRA menyemak fakta {n} selepas produk." for n in range(1, 30))
    assert ideas.caption_short({"bm": {"instagram": short}}, "regulab", "bm") == (len(short), ideas.CAPTION_FLOOR["regulab"][1])
    assert ideas.caption_short({"bm": {"instagram": longer}}, "regulab", "bm") is None
    assert ideas.caption_short({"en": {"linkedin": "x" * 1499}}, "linkedin", "en") is not None
    assert ideas.caption_short({"en": {"linkedin": "x" * 1500}}, "linkedin", "en") is None
    assert "TOO SHORT" in ideas.ask_longer(10, 900, "regulab") and "MORE FACTS" in ideas.ask_longer(10, 900, "regulab")


@pytest.mark.caption_floor
def test_a_short_caption_is_written_again_longer_and_the_longer_one_is_stored(offline):
    first = {**GOOD, "hook": "Takde sapa cakap pasal notifikasi tapi ni sebab aku hantar", "hook_shape": 1,
             "text": {"bm": {"instagram": "Takde sapa cakap pasal notifikasi tapi ni sebab aku hantar. Pendek."}}}
    long_cap = "Takde sapa cakap pasal notifikasi tapi ni sebab aku hantar.\n" + "\n".join(
        f"{n}. NPRA menyemak fakta nombor {n} selepas produk dipasarkan di pasaran." for n in range(1, 30))
    llm = Seq(first, {**first, "text": {"bm": {"instagram": long_cap}}})
    store = _store([{"hook_shape": 25}])
    pid = _write(llm, store)
    assert len(llm.seen) == 2 and "TOO SHORT" in llm.seen[1][1]
    post = next(p for p in store.tables["semasa_posts"] if p["id"] == pid)
    assert post["text"]["bm"]["instagram"].startswith("Takde sapa") and "19. NPRA" in post["text"]["bm"]["instagram"]


@pytest.mark.caption_floor
def test_a_caption_that_stays_short_still_makes_the_post(offline):
    first = {**GOOD, "hook": "Takde sapa cakap pasal notifikasi tapi ni sebab aku hantar", "hook_shape": 1,
             "text": {"bm": {"instagram": "Takde sapa cakap pasal notifikasi tapi ni sebab aku hantar. Pendek."}}}
    llm = Seq(first, first)
    store = _store([{"hook_shape": 25}])
    pid = _write(llm, store)
    assert len(llm.seen) == 2 and any(p["id"] == pid for p in store.tables["semasa_posts"])


def test_a_caption_over_the_platform_limit_is_trimmed_by_whole_paragraphs_keeping_hook_follow_and_tags():
    body = "\n\n".join(f"{n}. Fakta nombor {n} " + "x" * 300 for n in range(1, 12))
    cap = "Hook di sini.\n\n" + body + "\n\nFollow untuk tip regulatori yang senang faham.\n\n#halal #npra"
    out = ideas.fit_caption(cap, 2200)
    assert len(out) <= 2200 and out.startswith("Hook di sini.") and out.endswith("#halal #npra") and "Follow untuk" in out
    assert all(p in cap for p in out.split("\n\n")), "no paragraph is cut in the middle"
    assert ideas.fit_caption("pendek", 2200) == "pendek"
    fitted = ideas.fit_captions({"bm": {"instagram": cap, "threads": cap}}, "regulab")
    assert len(fitted["bm"]["instagram"]) <= 2200
    chain = compliance.thread_parts(fitted["bm"]["threads"])
    assert 1 < len(chain) <= 5 and all(len(x) <= 500 for x in chain), "a thread is fitted to its own rule: 5 posts of 500"
