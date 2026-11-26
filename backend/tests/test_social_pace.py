"""A rest between browser reads of Instagram and Threads (Wan, 26 Nov 2026: "add limit")."""

from datetime import UTC, datetime, timedelta

from fakestore import FakeStore

from semasa import intake, social_pace, social_web

NOW = datetime(2026, 11, 26, 6, 0, tzinfo=UTC)


def _store(**tables):
    return FakeStore(semasa_settings=[], **tables)


def test_defaults_and_the_settings_override():
    assert social_pace.hours_of({}, "instagram") == 11 and social_pace.hours_of({}, "threads") == 5
    assert social_pace.hours_of({"pace": {"instagram": 20}}, "instagram") == 20
    assert social_pace.hours_of({"pace": {"instagram": 0}}, "instagram") == 0            # 0 = no limit
    assert social_pace.hours_of({"pace": {"instagram": "x"}}, "instagram") == 11
    assert social_pace.hours_of({"pace": {"instagram": 999}}, "instagram") == 72         # never a rest of weeks
    assert social_pace.hours_of({}, "facebook") == 0                                     # only Instagram and Threads rest


def test_a_platform_rests_until_its_gap_has_passed_and_sweep_now_waives_it():
    store = _store()
    assert social_pace.next_read(store, {}, "instagram", NOW) is None                     # never read: go
    social_pace.mark(store, "instagram", NOW - timedelta(hours=3))
    until = social_pace.next_read(store, {}, "instagram", NOW)
    assert until == NOW - timedelta(hours=3) + timedelta(hours=11)
    assert social_pace.next_read(store, {}, "instagram", NOW, forced=True) is None        # "Sweep now"
    assert social_pace.next_read(store, {}, "threads", NOW) is None                       # each platform has its own clock
    assert social_pace.next_read(store, {}, "instagram", NOW + timedelta(hours=9)) is None
    assert "resting" in social_pace.rest_note("instagram", until) and "Instagram" in social_pace.rest_note("instagram", until)


def test_a_missing_settings_table_never_stops_a_read():
    class NoTable:
        def table(self, name):
            raise RuntimeError("no table")
    assert social_pace.next_read(NoTable(), {}, "instagram", NOW) is None
    social_pace.mark(NoTable(), "instagram", NOW)                                          # does not raise
    assert social_pace.carried_read(NoTable(), "instagram") == 0


def test_a_resting_platform_keeps_its_last_read_count():
    store = FakeStore(semasa_settings=[{"key": "sources", "value": {"report": {"community": {"read": {"instagram": 5}}}}}])
    assert social_pace.carried_read(store, "instagram") == 5


def test_the_instagram_caps_are_small_and_the_pause_is_random(monkeypatch):
    assert (social_web.PER_TAG_IG, social_web.PER_ACCOUNT_IG, social_web.MAX_TAGS, social_web.MAX_ACCOUNTS) == (2, 3, 5, 6)
    waits = []

    class Page:
        def wait_for_timeout(self, ms):
            waits.append(ms)
    for _ in range(12):
        social_web.pace(Page(), 2500, 6500)
    assert all(2500 <= w <= 6500 for w in waits) and len(set(waits)) > 1


def test_community_skips_a_resting_instagram_and_marks_a_real_read(monkeypatch):
    calls = []
    monkeypatch.setattr(social_web, "fetch", lambda platform, cfg, now: (calls.append(platform) or ([], "")))
    monkeypatch.setattr(intake.threads_web, "fetch", lambda cfg, now: (calls.append("threads") or ([], "")))
    monkeypatch.setattr(intake.reddit_web, "fetch", lambda cfg, now: ([], ""))
    monkeypatch.setattr(intake.threads_api, "fetch", lambda store, cfg, now: ([], ""))
    monkeypatch.setattr(intake.community, "fetch", lambda client, cfg, reddit=True: {"posts": [], "videos": [], "threads": []})
    monkeypatch.setattr(intake.community, "annotate", lambda llm, batch: ([], []))
    monkeypatch.setattr(intake, "write", lambda store, rows, dry: None)
    cfg = intake.merged(intake.DEFAULTS, {})["community"]
    store = _store(semasa_watch=[], semasa_ideas=[])
    social_pace.mark(store, "instagram", NOW - timedelta(hours=2))
    social_pace.mark(store, "threads", NOW - timedelta(hours=9))
    rep = intake.do_community(store, None, None, dict(cfg), NOW, False)
    assert "instagram" not in calls and "facebook" in calls and "threads" in calls          # instagram rests; the rest read
    assert "instagram" in rep["resting"] and "Instagram" in rep["instagram_stats"] and rep["instagram_error"] is None
    assert social_pace.last_read(store, "threads") == NOW                                   # the real read was marked
    calls.clear()
    intake.do_community(store, None, None, {**cfg, "_forced": True}, NOW, False)
    assert "instagram" in calls                                                              # "Sweep now" waives the rest
