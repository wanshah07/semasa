"""The watchdog light of each scrape source (14 Nov 2026): green live, orange standby, red unlive."""

from datetime import UTC, datetime, timedelta

from fakestore import FakeStore

from semasa import source_lights as sl

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
CFG = {"enabled": True, "community": {"enabled": True, "hours": 72, "facebook": {"enabled": True}, "instagram": {"enabled": True},
                                      "threads": {"enabled": True}, "youtube": {"enabled": True}},
       "folders": {"enabled": True}, "myra": {"enabled": True}}


def stored(community=None, ago=2, folders=None, myra=None):
    rep = {"community": {"ok": True, "read": {}, **(community or {})}, "folders": folders or {"ok": True},
           "myra": myra or {"ok": True}}
    return {"last_run": (NOW - timedelta(hours=ago)).isoformat(), "report": rep}


def lights(st, latest=None, prev=None, watch=None, from_sweep=False, cfg=CFG):
    return sl.evaluate(cfg, st, watch or {}, latest or {}, prev or {}, NOW, from_sweep)


def test_a_source_that_read_posts_is_green_and_says_how_many():
    got = lights(stored({"read": {"threads": 24}}))["threads"]
    assert got["light"] == "green" and "24 read" in got["why"]


def test_instagram_waiting_for_its_saved_login_is_orange_and_asks_for_it_by_name():
    got = lights(stored({"instagram_error": "Instagram needs a saved login (the secret PW_STORAGE_STATE_B64)"}))["instagram"]
    assert got["light"] == "orange" and got["act"] and "PW_STORAGE_STATE_B64" in got["why"]


def test_a_login_the_platform_refused_and_a_source_error_are_red():
    refused = lights(stored({"instagram_error": "Instagram asked for a login (save one as the secret PW_STORAGE_STATE_B64)"}))
    assert refused["instagram"]["light"] == "red" and "refused or has expired" in refused["instagram"]["why"]
    yt = lights(stored({"youtube_error": "HTTP request failed: 403 Client Error: Forbidden"}))["youtube"]
    assert yt["light"] == "red" and "403" in yt["why"]
    quota = lights(stored({"youtube_error": "quota"}))["youtube"]
    assert quota["light"] == "orange" and not quota.get("act")          # it mends itself tomorrow: a light, never an e-mail


def test_a_source_that_answers_with_nothing_is_orange_then_red_after_three_sweeps_in_a_row():
    st = stored({"read": {"facebook": 0}})
    first = lights(st, from_sweep=True)["facebook"]
    assert first["light"] == "orange" and first["zero_streak"] == 1
    two = lights(st, prev={"facebook": {"zero_streak": 2}}, from_sweep=True)["facebook"]
    assert two["light"] == "red" and two["zero_streak"] == 3 and "3 sweeps in a row" in two["why"]
    again = lights(st, prev={"facebook": {"zero_streak": 2}}, from_sweep=False)["facebook"]   # health never counts twice
    assert again["zero_streak"] == 2 and again["light"] == "orange"
    mended = lights(stored({"read": {"facebook": 3}}), prev={"facebook": {"zero_streak": 2}}, from_sweep=True)["facebook"]
    assert mended["light"] == "green" and mended["zero_streak"] == 0


def test_rows_still_on_show_keep_a_quiet_source_green():
    latest = {"reddit": NOW - timedelta(hours=20)}
    assert lights(stored({"read": {"reddit": 0}}), latest)["reddit"]["light"] == "green"
    assert lights(stored({"read": {"reddit": 0}}), {"reddit": NOW - timedelta(hours=90)})["reddit"]["light"] == "orange"


def test_a_sweep_that_stopped_running_turns_every_source_red_and_a_switched_off_one_is_orange_not_a_problem():
    got = lights(stored({"read": {"threads": 5}}, ago=20))
    assert got["threads"]["light"] == "red" and "no sweep for 20 h" in got["threads"]["why"] and got["myra"]["light"] == "red"
    off = {**CFG, "community": {**CFG["community"], "instagram": {"enabled": False}}}
    ig = lights(stored(), cfg=off)["instagram"]
    assert ig["light"] == "orange" and ig["off"]
    assert not any("Instagram" in p["area"] for p in sl.problems({"instagram": ig}))


def test_folders_and_myra_follow_their_own_part_of_the_report():
    st = stored(folders={"ok": False, "error": "OneDrive refused"}, myra={"ok": True, "new": 2})
    got = lights(st)
    assert got["folder"]["light"] == "red" and "OneDrive refused" in got["folder"]["why"] and got["myra"]["light"] == "green"


def test_regulatory_and_publication_follow_the_daily_watch_sweep():
    ok = {"last_run": (NOW - timedelta(hours=5)).isoformat(),
          "result": {"sources": [{"name": "NPRA", "ok": True}, {"name": "EU", "ok": True}]}}
    assert lights(stored(), watch=ok)["regulatory"]["light"] == "green"
    part = {**ok, "result": {"sources": [{"name": "NPRA", "ok": True}, {"name": "EU", "ok": False, "error": "x"}]}}
    got = lights(stored(), watch=part)["publication"]
    assert got["light"] == "orange" and got["act"] and "EU" in got["why"]
    allbad = {**ok, "result": {"sources": [{"name": "NPRA", "ok": False, "error": "x"}]}}
    assert lights(stored(), watch=allbad)["regulatory"]["light"] == "red"
    old = {**ok, "last_run": (NOW - timedelta(hours=40)).isoformat()}
    assert lights(stored(), watch=old)["regulatory"]["light"] == "red"


def test_the_watchdog_lines_are_reds_and_oranges_that_need_someone_and_name_the_source():
    got = lights(stored({"instagram_error": "Instagram needs a saved login", "youtube_error": "403 Forbidden",
                         "read": {"threads": 3, "facebook": 0}}))
    lines = sl.problems(got)
    areas = {p["area"]: p["what"] for p in lines}
    assert areas["Scrape · YouTube"].startswith("UNLIVE") and areas["Scrape · Instagram"].startswith("STANDBY")
    assert areas["Scrape · Facebook"].startswith("STANDBY") and "Scrape · Threads" not in areas


def test_update_saves_the_lights_and_never_raises():
    store = FakeStore(semasa_settings=[{"key": "sources", "value": stored({"read": {"threads": 7}}, ago=1)}], semasa_watch=[])
    lights_now = sl.update(store, NOW, from_sweep=True)
    saved = next(r for r in store.tables["semasa_settings"] if r["key"] == "source_lights")["value"]
    assert saved["lights"]["threads"]["light"] == lights_now["threads"]["light"] == "green" and saved["at"]
    assert sl.update(object(), NOW) == {}                      # a store that cannot be read is a quiet failure, not a crash
