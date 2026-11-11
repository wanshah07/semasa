from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from test_telegram_tools import LINK, team_store  # noqa: E402

from semasa import telegram_catalogue as cat  # noqa: E402


def test_home_has_only_the_five_new_english_buttons():
    text, buttons = cat.home_reply(LINK)
    assert "Semasa here" in text
    assert [row[0]["callback_data"] for row in buttons] == ["c:model", "c:repo", "c:idea", "c:style", "c:post"]


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
