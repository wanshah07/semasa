from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from test_telegram_tools import LINK, team_store  # noqa: E402

from semasa import telegram_catalogue as cat  # noqa: E402


def test_home_is_the_menu_of_every_segment_and_keeps_the_five_tasks_within_reach():
    """The five tasks of 9 Nov 2026 (model, repo, idea, style, post) are still buttons: each sits in its page's own menu now."""
    from semasa import telegram_menu as menu
    text, buttons = cat.home_reply(LINK, "en", "https://semasa.example")
    assert "Semasa here" in text
    datas = [b.get("callback_data") for row in buttons for b in row]
    assert datas[:2] == ["a:draf", "a:idea_r"] and "m:s:content" in datas and "m:s:technology" in datas
    assert {"model", "repo", "idea_r", "style", "draf_r"} <= set(menu.acts())


def test_idea_repo_and_style_are_queued_without_execution():
    st = team_store(**{"semasa_repo_library": [], "semasa_writing_styles": []})
    reply, done = cat.add_idea(st, LINK, "https://example.com/source a useful topic")
    assert done and st.tables["semasa_ideas"][0]["status"] == "new"
    assert st.tables["semasa_ideas"][0]["brief"]["hook_required"]
    reply, done = cat.add_repo(st, LINK, "https://github.com/example/project")
    assert done and st.tables["semasa_repo_library"][0]["status"] == "pending"
    reply, done = cat.add_style(st, LINK, "A" * 90)
    assert done and st.tables["semasa_writing_styles"][0]["status"] == "new"


def test_pending_menu_state_is_namespaced():
    st = team_store()
    cat.ask(st, "idea")
    assert cat.waiting(st, "a topic") == ("idea", "")
    cat.clear_pending(st)
    assert cat.waiting(st, "a topic") is None


def test_carousel_and_single_card_expose_design_and_picture_choices():
    _, carousel = cat.carousel_options("p1")
    assert any("c:pcpick:p1:threads" == b["callback_data"] for row in carousel for b in row)
    _, picture = cat.picture_options("p1", "grid")
    assert any("c:pcgo:p1:grid:post" == b["callback_data"] for row in picture for b in row)
    _, single = cat.single_options("p1")
    assert any("c:scpick:p1:image" == b["callback_data"] for row in single for b in row)


def test_a_linkedin_post_is_never_made_into_a_film_from_telegram():
    from fakestore import FakeStore

    from semasa import telegram_catalogue as cat
    store = FakeStore(semasa_motions=[])
    reply, buttons = cat.make_motion(store, {}, {"id": "p1", "stream": "linkedin", "status": "draft",
                                                 "text": {"en": {"linkedin": "Words"}}, "lang": "en"})
    assert "never a film" in reply and buttons == [] and store.tables["semasa_motions"] == []


# ---- the design buttons under a draft: the page's own looks, Diari first (Wan, 23 Nov 2026) -----------------------------------

def _datas(rows):
    return [b["callback_data"] for row in rows for b in row]


def _labels(rows):
    return [b["text"] for row in rows for b in row]


def test_a_drafts_carousel_buttons_offer_every_look_the_page_offers_with_diari_first():
    from semasa import ideas
    from semasa import telegram_menu as menu
    text, rows = cat.carousel_options("p1", "en")
    first = rows[0][0]
    assert first == {"text": "✨ Journal", "callback_data": "c:pcpick:p1:journal"} and len(rows[0]) == 1, "Diari leads, alone"
    looks = [d.rsplit(":", 1)[1] for d in _datas(rows) if d.startswith("c:pcpick:")]
    assert looks[:2] == ["journal", "threads"], "Diari and Threads on top (Wan, 23 Nov 2026)"
    assert menu.LOOKS["carousel"][:2] == ["journal", "threads"], "and in the carousel-from-a-topic menu"
    assert looks == menu.LOOKS["post_carousel"]
    assert set(looks) <= set(ideas.LOOKS) and len(looks) == len(set(looks))
    assert {"classic", "hand", "marker", "torn", "block", "neon", "deck", "chalk", "metro", "strip", "grid", "photo", "image",
            "threads", "journal"} <= set(looks)
    assert "Diari" in cat.carousel_options("p1", "bm")[1][0][0]["text"] and "gambar AI" in cat.carousel_options("p1", "bm")[0]
    assert "one AI picture per slide" in text
    assert all(len(d.encode()) <= menu.CALLBACK_MAX for d in _datas(rows)), "Telegram's 64-byte limit"
    long_id = "0123456789abcdef0123456789abcdef0123"
    assert all(len(d.encode()) <= menu.CALLBACK_MAX for d in _datas(cat.carousel_options(long_id)[1]) + _datas(
        cat.picture_options(long_id, "journal")[1]) + [f"c:pcgo:{long_id}:journal:none", f"c:scgo:{long_id}:metro:none"])
    assert _datas(rows)[-1] == "c:post", "and a way back"


def test_a_drafts_single_card_buttons_never_offer_diari_or_threads():
    from semasa import telegram_menu as menu
    _, rows = cat.single_options("p1", "en")
    looks = [d.rsplit(":", 1)[1] for d in _datas(rows) if d.startswith("c:scpick:")]
    assert looks == menu.LOOKS["post_card"] and "journal" not in looks and "threads" not in looks
    assert {"hand", "marker", "torn", "block", "neon", "deck", "chalk", "metro", "strip", "classic", "grid", "photo",
            "image"} <= set(looks)
    assert "Torn strips" in _labels(rows) and "Lukisan tangan" in _labels(cat.single_options("p1", "bm")[1])


def test_choosing_diari_under_a_draft_makes_the_carousel_at_once_with_no_picture_question():
    from fakestore import FakeStore
    store = FakeStore(semasa_ideas=[])
    post = {"id": "p1", "status": "draft", "stream": "regulab", "domain": "kosmetik", "hook": "Hook", "lang": "bm",
            "text": {"bm": {"instagram": "Caption."}}, "idea_id": None}
    out = cat.make_carousel(store, {"user_id": "u"}, post, "journal", "none")
    row = store.tables["semasa_ideas"][0]
    assert "sent to the writer" in out and row["brief"]["look"] == "journal" and row["make_slides"] is True
    import inspect

    from semasa import telegram_bot
    src = inspect.getsource(telegram_bot)
    assert 'if look == "journal":' in src and 'cat.make_carousel(store, link, posts[0], look, "none")' in src, \
        "the handler skips the picture-source step for Diari"
