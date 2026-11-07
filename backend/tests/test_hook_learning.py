"""Which hook shapes earn views and interaction, and the hint the writers get because of it (Wan, 7 Nov 2026). In-memory store."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fakestore import FakeStore

from semasa import db, hook_bank, hook_learning, motion

NOW = datetime(2026, 11, 7, 6, 0, tzinfo=UTC)


def metric(post, views, acts=0, days_ago=5, **over):
    return {"post_id": post, "sent_at": (NOW - timedelta(days=days_ago)).isoformat(), "views": views, "reach": None,
            "impressions": None, "reactions": acts, "comments": 0, "shares": 0, "saves": 0, "reposts": 0, "quotes": 0,
            "clicks": 0, **over}


def world(specs, extra=None, settings=None):
    """specs: [(post id, shape, style, views, interactions)] -> a store with posts, ideas and metrics."""
    posts, ideas, mets = [], [], []
    for pid, shape, style, views, acts in specs:
        posts.append({"id": pid, "idea_id": f"i-{pid}", "media_ids": []})
        brief = {"hook_shape": shape, **({"hook_style": style} if style else {})}
        ideas.append({"id": f"i-{pid}", "brief": brief})
        mets.append(metric(pid, views, acts))
    t = {"semasa_post_metrics": mets, db.POSTS: posts, db.IDEAS: ideas, db.MEDIA: [], "semasa_motions": []}
    if settings:
        t[db.SETTINGS] = settings
    t.update(extra or {})
    return FakeStore(**t)


def test_a_shape_needs_three_results_before_it_is_ranked_and_the_best_scores_highest():
    specs = [(f"a{i}", 17, "", 1000, 50) for i in range(3)] + [(f"b{i}", 21, "", 200, 4) for i in range(3)] \
        + [("c1", 5, "", 9000, 900), ("c2", 5, "", 9000, 900)]                       # two results only: not ranked
    ranked = hook_learning.rank(hook_learning.collect(world(specs), NOW))
    assert [r["shape"] for r in ranked] == [17, 21] and ranked[0]["n"] == 3 and ranked[0]["score"] == 1.0
    assert ranked[1]["score"] < ranked[0]["score"]
    assert ranked[0]["views"] == 1000.0 and ranked[0]["rate"] == 0.05


def test_results_older_than_the_window_and_posts_without_a_base_are_left_out():
    s = world([("a", 17, "", 1000, 10)])
    s.tables["semasa_post_metrics"] += [metric("a", 500, 5, days_ago=90), metric("a", 0, 5)]
    got = hook_learning.per_post(s.tables["semasa_post_metrics"], NOW - timedelta(days=hook_learning.WINDOW_DAYS))
    assert got == {"a": {"views": 1000, "interactions": 10}}
    assert hook_learning.per_post([metric("z", 0, 9)], NOW - timedelta(days=60)) == {}, "nothing to divide by"


def test_the_channels_of_one_post_add_up_and_reach_stands_in_for_views():
    rows = [metric("a", 400, 20), metric("a", None, 10, reach=600), metric("b", None, 5, impressions=50)]
    got = hook_learning.per_post(rows, NOW - timedelta(days=60))
    assert got["a"] == {"views": 1000, "interactions": 30} and got["b"] == {"views": 50, "interactions": 5}


def test_a_film_post_is_joined_to_the_shape_its_film_was_written_on():
    s = world([("f1", 0, "", 800, 40), ("f2", 0, "", 800, 40), ("f3", 0, "", 800, 40)])
    for i in (1, 2, 3):
        s.tables[db.IDEAS][i - 1]["brief"] = {}                                   # no shape on the idea: it is a film
        s.tables[db.POSTS][i - 1]["media_ids"] = [f"g{i}"]
        s.tables[db.MEDIA].append({"id": f"g{i}", "meta": {"motion_id": f"m{i}"}})
        s.tables["semasa_motions"].append({"id": f"m{i}", "check_report": {"hook": {"shape": 24}}})
    got = hook_learning.collect(s, NOW)
    assert [(r["shape"], r["kind"]) for r in got] == [(24, "film")] * 3
    assert hook_learning.rank(got)[0]["films"] == 3


def test_styles_are_ranked_apart_from_the_built_in_shapes():
    specs = [(f"a{i}", 3, "st1", 900, 45) for i in range(3)] + [(f"b{i}", 1, "st1", 100, 2) for i in range(3)] \
        + [(f"c{i}", 17, "", 500, 25) for i in range(3)] + [(f"d{i}", 21, "", 400, 8) for i in range(3)]
    s = world(specs)
    hook_learning.learn(s, NOW)
    st1 = hook_bank.Bank(id="st1", name="Berani")
    assert "shapes 3, 1 earned" in hook_learning.hint(s, st1)
    assert "shapes 17, 21 earned" in hook_learning.hint(s, None)
    assert "shapes 17, 21 earned" in hook_learning.hint(s, hook_bank.Bank())


def test_learn_writes_the_setting_and_says_nothing_until_two_shapes_are_ranked():
    s = world([("a", 17, "", 1000, 50)])
    value = hook_learning.learn(s, NOW)
    assert value["ranking"] == [] and value["measured"] == 1 and value["min_posts"] == 3
    saved = next(r["value"] for r in s.tables[db.SETTINGS] if r["key"] == hook_learning.KEY)
    assert saved["at"] == NOW.isoformat()
    assert hook_learning.hint(s, None) == "", "nothing to say yet"
    only_one = world([(f"a{i}", 17, "", 1000, 50) for i in range(3)])
    hook_learning.learn(only_one, NOW)
    assert hook_learning.hint(only_one, None) == "", "one ranked shape is not a pattern"


def test_the_hint_is_a_hint_with_room_to_explore_and_quotes_nothing():
    specs = [(f"a{i}", 17, "", 900, 45) for i in range(3)] + [(f"b{i}", 21, "", 100, 2) for i in range(3)] \
        + [(f"c{i}", 9, "", 500, 20) for i in range(3)] + [(f"d{i}", 4, "", 50, 1) for i in range(3)]
    s = world(specs)
    hook_learning.learn(s, NOW)
    text = hook_learning.hint(s, None)
    assert text.startswith("WHAT HAS WORKED FOR THIS ACCOUNT") and "only a hint" in text
    assert "every rule above still outranks it" in text
    assert "shapes 17, 9, 21 earned" in text, "the top three, best first"
    assert "when it fits the story" in text and "fewer than 3 results" in text
    assert "Never reuse an earlier hook's words" in text


def test_wans_switch_turns_the_hint_off_and_a_missing_table_leaves_it_on():
    specs = [(f"a{i}", 17, "", 900, 45) for i in range(3)] + [(f"b{i}", 21, "", 100, 2) for i in range(3)]
    s = world(specs, settings=[{"key": hook_learning.SWITCH_KEY, "value": {"enabled": False}}])
    hook_learning.learn(s, NOW)
    assert hook_learning.enabled(s) is False and hook_learning.hint(s, None) == ""
    s2 = world(specs)
    hook_learning.learn(s2, NOW)
    assert hook_learning.enabled(s2) is True and hook_learning.hint(s2, None) != ""
    assert hook_learning.hint(None, None) == ""
    assert hook_learning.collect(FakeStore(), NOW) == [], "no tables: no results, no error"


def test_the_hint_rides_in_both_writers_prompts_after_the_rules_and_before_the_shapes():
    hint = "WHAT HAS WORKED FOR THIS ACCOUNT (x): shapes 17, 9 earned the most."
    post = hook_bank.block(None, "regulab", None, hint)
    film = hook_bank.film_block("regulab", None, hint)
    for text in (post, film):
        assert text.index("HOOK") < text.index(hint) < text.index("Shapes you may use:")
    assert hint not in hook_bank.block(None, "regulab") and hint not in hook_bank.film_block("regulab")
    assert hint in motion.build_script_system({"voice": "off", "language": "bm", "stream": "regulab"}, "", 4, None, hint)
