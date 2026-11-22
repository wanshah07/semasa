"""Housekeeping (Wan, 22 Nov 2026: "make do routine cleaning to make sure supabase or egress/db is not tight")."""

from datetime import UTC, datetime, timedelta

from fakestore import FakeStore

from semasa import archive, housekeeping

NOW = datetime(2026, 11, 22, 19, 47, tzinfo=UTC)
BASE = "https://x.supabase.co/storage/v1/object/public/semasa-generated/"


def ago(days=0, hours=0):
    return (NOW - timedelta(days=days, hours=hours)).isoformat()


def _file(name, size):
    return {"name": name, "id": name, "created_at": ago(30), "metadata": {"size": size}}


def _pic(mid, idea, days, **extra):
    path = f"2026/11/{mid}.png"
    row = {"id": mid, "idea_id": idea, "post_id": None, "type": "image", "status": "done", "updated_at": ago(days),
           "generated_media_url": BASE + path, "reference_url": None, "meta": {"generated_path": path}}
    row.update(extra)
    return row


def _store(media=None, posts=None, ideas=None, motions=None, settings=None, files=None, **tables):
    store = FakeStore(
        media_generations=media or [], semasa_posts=posts or [], semasa_ideas=ideas or [], semasa_motions=motions or [],
        semasa_settings=settings or [], semasa_log=tables.pop("semasa_log", []), **tables)
    store.listing[""] = files if files is not None else [_file(f"2026/11/{m['id']}.png", 1000) for m in (media or [])]
    return store


# --- rows --------------------------------------------------------------------------------------------------------------------

def test_old_pulse_lines_usage_and_handled_telegram_updates_go_and_everything_else_stays():
    store = _store(
        semasa_log=[{"id": "l1", "event": "api_pulse.down", "at": ago(20)},
                    {"id": "l2", "event": "api_pulse.down", "at": ago(2)},
                    {"id": "l3", "event": "post.posted", "at": ago(60)}],
        semasa_api_usage=[{"id": "u1", "area": "pulse", "created_at": ago(15)},
                          {"id": "u2", "area": "pulse", "created_at": ago(1)},
                          {"id": "u3", "area": "media", "created_at": ago(60)}],
        semasa_telegram_inbox=[{"id": 1, "status": "done", "created_at": ago(40)},
                               {"id": 2, "status": "new", "created_at": ago(40)},
                               {"id": 3, "status": "error", "created_at": ago(40)},
                               {"id": 4, "status": "done", "created_at": ago(3)}])
    report = housekeeping.run(store, NOW, dry=False)
    assert report["pulse_log"] == {"found": 1, "deleted": 1, "days": 14}
    assert [r["id"] for r in store.tables["semasa_log"] if r.get("event") != "housekeeping"] == ["l2", "l3"]   # 90 days elsewhere
    assert [r["id"] for r in store.tables["semasa_api_usage"]] == ["u2", "u3"]          # a worker's AI call keeps its 90 days
    assert [r["id"] for r in store.tables["semasa_telegram_inbox"]] == [2, 4]           # one not handled yet is never touched


def test_a_dry_run_counts_and_changes_nothing():
    store = _store(semasa_log=[{"id": "l1", "event": "api_pulse.down", "at": ago(20)}],
                   media=[_pic("m1", "i1", 10)], ideas=[{"id": "i1", "status": "drafted"}])
    report = housekeeping.run(store, NOW, dry=True)
    assert report["pulse_log"]["found"] == 1 and report["pulse_log"]["deleted"] == 0
    assert report["deleted_posts"]["found"] == 1 and report["deleted_posts"]["bytes"] == 1000
    assert len(store.tables["semasa_log"]) == 1 and len(store.tables["media_generations"]) == 1 and store.removed == []
    assert "would delete" in housekeeping.summary(report)


def test_report_mode_in_settings_holds_every_step():
    store = _store(semasa_log=[{"id": "l1", "event": "api_pulse.down", "at": ago(20)}],
                   settings=[{"key": "housekeeping", "value": {"mode": "report"}}])
    assert housekeeping.run(store, NOW)["dry"] is True and len(store.tables["semasa_log"]) == 1


def test_a_window_below_the_floor_is_raised_to_it():
    store = _store(settings=[{"key": "housekeeping", "value": {"pulse_log_days": 0, "deleted_post_media_days": "x"}}])
    cfg = housekeeping.load_settings(store)
    assert cfg["pulse_log_days"] == housekeeping.FLOOR_DAYS and cfg["deleted_post_media_days"] == 7


class _Rpc(FakeStore):
    def __init__(self, error=None, **kw):
        super().__init__(**kw)
        self.error, self.calls = error, []

    def rpc(self, name, args):
        store = self

        class _Q:
            def execute(self):
                if store.error:
                    raise store.error
                store.calls.append((name, dict(args)))
                return type("R", (), {"data": 12})()
        return _Q()


def test_cron_history_goes_through_the_function_and_says_so_when_089_is_not_run():
    store = _Rpc()
    cfg = housekeeping.load_settings(store)
    assert housekeeping.sweep_cron(store, cfg, dry=False) == {"found": 12, "deleted": 12, "days": 14}
    assert [c[1]["p_dry"] for c in store.calls] == [True, False]
    missing = _Rpc(error=RuntimeError("Could not find the function public.semasa_housekeeping_cron (PGRST202)"))
    assert housekeeping.sweep_cron(missing, cfg, dry=False)["skipped"].startswith("run supabase/089")


# --- pictures of deleted posts ----------------------------------------------------------------------------------------------

def test_pictures_of_a_post_deleted_a_week_ago_go_row_and_files():
    slides = _pic("m2", "i1", 9, mode="slides", generated_media_url=None,
                  meta={"slide_paths": ["2026/11/s1.jpg", "2026/11/s2.jpg"], "slide_urls": []})
    store = _store(media=[_pic("m1", "i1", 8), slides], ideas=[{"id": "i1", "status": "drafted"}],
                   files=[_file("2026/11/m1.png", 2_000_000), _file("2026/11/s1.jpg", 300), _file("2026/11/s2.jpg", 300)])
    out = housekeeping.run(store, NOW, dry=False)["deleted_posts"]
    assert out["found"] == 2 and out["deleted"] == 2 and out["files"] == 3 and out["bytes"] == 2_000_600
    assert store.tables["media_generations"] == []
    assert sorted(p for _, ps in store.removed for p in ps) == ["2026/11/m1.png", "2026/11/s1.jpg", "2026/11/s2.jpg"]
    assert [r["event"] for r in store.tables["semasa_log"]] == ["housekeeping"]


def test_what_is_kept():
    media = [
        _pic("young", "i1", 2),                                            # deleted under 7 days ago
        _pic("haspost", "i2", 30),                                         # its idea still has a post (any status)
        _pic("attached", "i3", 30),                                        # another post holds it
        _pic("design", "i3", 30, meta={"generated_path": "2026/11/design.png", "design": {"name": "x"}}),
        _pic("designid", "i3", 30, meta={"generated_path": "2026/11/designid.png", "design_id": "d1"}),
        _pic("comic", "i3", 30, meta={"generated_path": "2026/11/comic.png", "comic": {"series": "a"}}),
        _pic("library", None, 30),                                         # made in the Image tab: the library
        _pic("owned", "i3", 30, post_id="p9"),                             # still its post's
        _pic("pending", "i3", 30, status="pending"),
        _pic("newidea", "i4", 30),                                         # its idea is still being worked on
        _pic("film", "i3", 30, type="video"),                              # films are the idle-film step's
        _pic("named", "i3", 30),                                           # its id is named in another row
        _pic("nostamp", "i3", 30, updated_at=None),
    ]
    posts = [{"id": "p1", "idea_id": "i2", "status": "rejected", "media_ids": []},
             {"id": "p2", "idea_id": "i9", "status": "draft", "media_ids": ["attached"]}]
    ideas = [{"id": "i1", "status": "drafted"}, {"id": "i2", "status": "drafted"}, {"id": "i3", "status": "drafted"},
             {"id": "i4", "status": "new"}]
    store = _store(media=media, posts=posts, ideas=ideas,
                   semasa_brain_entries=[{"id": "b1", "body": "see picture named"}])
    out = housekeeping.run(store, NOW, dry=False)["deleted_posts"]
    assert out["found"] == 0 and store.removed == [] and len(store.tables["media_generations"]) == len(media)


def test_a_file_another_row_names_keeps_its_picture_but_its_own_row_does_not():
    store = _store(media=[_pic("m1", "i1", 10), _pic("m2", "i1", 10)], ideas=[{"id": "i1", "status": "rejected"}],
                   motions=[{"id": "f1", "storyboard": {"scenes": [{"picture": BASE + "2026/11/m2.png"}]}}])
    housekeeping.run(store, NOW, dry=False)
    assert [r["id"] for r in store.tables["media_generations"]] == ["m2"]


def test_a_picture_taken_by_a_post_between_the_read_and_the_delete_is_kept(monkeypatch):
    store = _store(media=[_pic("m1", "i1", 10)], ideas=[{"id": "i1", "status": "drafted"}])
    real = archive.referenced_text

    def late(*a, **k):
        text = real(*a, **k)
        store.tables["semasa_posts"].append({"id": "p5", "idea_id": "i7", "status": "draft", "media_ids": ["m1"]})
        return text
    monkeypatch.setattr(archive, "referenced_text", late)
    out = housekeeping.run(store, NOW, dry=False)["deleted_posts"]
    assert out["found"] == 1 and out["deleted"] == 0 and store.removed == []
    assert len(store.tables["media_generations"]) == 1


def test_a_failed_read_deletes_nothing(monkeypatch):
    store = _store(media=[_pic("m1", "i1", 10)], ideas=[{"id": "i1", "status": "drafted"}])

    def boom(*a, **k):
        raise RuntimeError("timeout")
    monkeypatch.setattr(archive, "referenced_text", boom)
    out = housekeeping.run(store, NOW, dry=False)["deleted_posts"]
    assert out["error"] == "timeout" and len(store.tables["media_generations"]) == 1 and store.removed == []


def test_no_more_than_the_cap_in_one_run(monkeypatch):
    monkeypatch.setattr(housekeeping, "CAP", 2)
    store = _store(media=[_pic(f"m{i}", "i1", 10) for i in range(5)], ideas=[{"id": "i1", "status": "drafted"}])
    out = housekeeping.run(store, NOW, dry=False)["deleted_posts"]
    assert out["found"] == 5 and out["deleted"] == 2 and len(store.tables["media_generations"]) == 3


# --- idle Motion films --------------------------------------------------------------------------------------------------------

def _film(fid, days, **extra):
    row = {"id": fid, "status": "done", "queued_post_id": None, "updated_at": ago(days), "video_path": f"motion/{fid}.mp4",
           "video_url": BASE + f"motion/{fid}.mp4", "social_url": BASE + f"motion/{fid}-social.mp4",
           "poster_url": BASE + f"motion/{fid}.jpg", "html": "<html/>", "check_report": {"ok": True},
           "bytes": 20_000_000, "social_bytes": 5_000_000}
    row.update(extra)
    return row


def _film_store(settings=None, **kw):
    motions = [_film("f1", 40), _film("f2", 5), _film("f3", 40, queued_post_id="p1"), _film("f4", 40),
               _film("f5", 40, check_report={"film_purged_at": ago(1)})]
    media = [{"id": "v4", "type": "video", "post_id": None, "mode": "prompt", "meta": {"flow": "motion", "motion_id": "f4"},
              "generated_media_url": BASE + "motion/f4-social.mp4", "reference_url": BASE + "motion/f4.mp4"},
             {"id": "v1", "type": "video", "post_id": None, "mode": "upload", "meta": {"flow": "motion", "motion_id": "f1"},
              "generated_media_url": BASE + "motion/f1-social.mp4", "reference_url": BASE + "motion/f1.mp4"}]
    posts = [{"id": "p2", "idea_id": None, "status": "approved", "media_ids": ["v4"]}]
    files = [_file(f"motion/{n}", 1000) for n in ("f1.mp4", "f1-social.mp4", "f1.jpg")]
    return _store(motions=motions, media=media, posts=posts, settings=settings, files=files, **kw)


def test_idle_films_are_only_reported_unless_switched_on():
    store = _film_store()
    out = housekeeping.run(store, NOW, dry=False)["idle_films"]
    assert out["found"] == 1 and out["bytes"] == 3000 and out["deleted"] == 0 and out["switch"] == "report"
    assert out["unposted_films"] == 2 and out["unposted_bytes"] == 50_000_000        # f1 and f2; f3 is queued, f4 on a post
    assert store.removed == [] and store.tables["semasa_motions"][0]["video_url"]
    assert "report only" in housekeeping.summary(housekeeping.run(store, NOW, dry=True))


def test_switched_on_an_idle_film_loses_its_files_and_keeps_its_record():
    store = _film_store(settings=[{"key": "housekeeping", "value": {"idle_films": "delete"}}])
    store.listing["motion/storyboard/f1"] = ["preview-1.jpg"]
    out = housekeeping.run(store, NOW, dry=False)["idle_films"]
    assert out["deleted"] == 1
    assert set(store.removed[-1][1]) == {"motion/f1.mp4", "motion/f1-social.mp4", "motion/f1.jpg",
                                         "motion/storyboard/f1/preview-1.jpg"}
    f1 = store.tables["semasa_motions"][0]
    assert f1["video_url"] == "" and f1["check_report"]["film_purged_at"] and f1["check_report"]["ok"] is True
    v1 = next(m for m in store.tables["media_generations"] if m["id"] == "v1")
    assert v1["generated_media_url"] is None and v1["reference_url"] == "" and v1["meta"]["film_purged_at"]   # upload keeps ""
    assert all(m["video_url"] for m in store.tables["semasa_motions"][1:4])          # young, queued, on a post: untouched


def test_the_orphan_scan_no_longer_reads_ai_usage_rows():
    assert "semasa_api_usage" not in archive.scanned_tables()
    assert {"semasa_posts", "media_generations", "semasa_motions", "semasa_ideas"} <= set(archive.scanned_tables())
