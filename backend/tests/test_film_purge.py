"""A Motion film is deleted for good 72 hours after its post went out (Wan, 11 Nov 2026)."""

from datetime import UTC, datetime, timedelta

from fakestore import FakeStore

from semasa import archive

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
BASE = "https://x.supabase.co/storage/v1/object/public/semasa-generated/"


def _store(hours_ago=14, post_status="posted", other=None, flow="motion"):
    when = (NOW - timedelta(hours=hours_ago)).isoformat()
    posts = [{"id": "p1", "status": post_status, "media_ids": ["m1"], "posted_at": when}]
    if other:
        posts.append({"id": "p2", "status": other, "media_ids": ["m1"], "posted_at": None})
    store = FakeStore(
        semasa_posts=posts,
        media_generations=[{"id": "m1", "type": "video", "post_id": "p1", "status": "done",
                            "generated_media_url": BASE + "motion/f1-social.mp4?t=1", "reference_url": BASE + "motion/f1.mp4",
                            "meta": {"flow": flow, "motion_id": "f1", "poster_url": BASE + "motion/f1.jpg"}}],
        semasa_motions=[{"id": "f1", "status": "done", "title": "Satu", "video_path": "motion/f1.mp4",
                         "video_url": BASE + "motion/f1.mp4", "social_url": BASE + "motion/f1-social.mp4",
                         "poster_url": BASE + "motion/f1.jpg", "html": "<html>big</html>", "check_report": {"ok": True},
                         "script": [{"id": "s1"}], "captions": {"x": 1}}],
        semasa_log=[])
    store.listing["motion/storyboard/f1"] = ["preview-1.jpg", "preview-sheet.jpg"]
    return store


def test_a_film_is_deleted_72_hours_after_its_post_went_out_and_the_record_stays():
    store = _store()
    assert archive.purge_films(store, NOW) == "films: 1 Motion film(s) deleted 12h after posting, 5 file(s) removed"
    bucket, paths = store.removed[0]
    assert bucket == "semasa-generated"
    assert set(paths) == {"motion/f1.mp4", "motion/f1-social.mp4", "motion/f1.jpg", "motion/storyboard/f1/preview-1.jpg",
                          "motion/storyboard/f1/preview-sheet.jpg"} and len(paths) == len(set(paths)) == 5
    f = store.tables["semasa_motions"][0]
    assert f["video_url"] == f["social_url"] == f["poster_url"] == f["video_path"] == f["html"] == ""
    assert f["check_report"]["ok"] is True and f["check_report"]["film_purged_at"]          # the record of it stays
    assert f["script"] == [{"id": "s1"}] and f["captions"] == {"x": 1} and f["title"] == "Satu"
    m = store.tables["media_generations"][0]
    assert m["generated_media_url"] is None and m["reference_url"] is None and m["meta"]["film_purged_at"]
    assert [r["event"] for r in store.tables["semasa_log"]] == ["film.purged"]
    assert archive.purge_films(store, NOW + timedelta(hours=1)).startswith("films: 0")     # once only


def test_nothing_is_deleted_before_72_hours_or_for_a_post_that_has_not_gone_out():
    for store in (_store(hours_ago=11), _store(post_status="approved")):
        assert archive.purge_films(store, NOW).startswith("films: 0") and store.removed == []
        assert store.tables["semasa_motions"][0]["video_url"]


def test_a_post_with_no_readable_posted_stamp_is_never_purged():
    store = _store()
    store.tables["semasa_posts"][0]["posted_at"] = None
    assert archive.purge_films(store, NOW).startswith("films: 0") and store.removed == []


def test_a_film_another_post_that_is_still_to_go_out_uses_is_kept():
    for other, kept in (("approved", True), ("scheduled", True), ("posted", False)):
        store = _store(other=other)
        archive.purge_films(store, NOW)
        assert bool(store.tables["semasa_motions"][0]["video_url"]) is kept


def test_a_picture_or_a_non_motion_video_is_left_alone():
    store = _store(flow="clip")
    assert archive.purge_films(store, NOW).startswith("films: 0") and store.removed == []


def test_a_failed_delete_changes_no_record_so_the_next_run_tries_again():
    store = _store()
    store.remove_error = RuntimeError("storage is down")
    assert archive.purge_films(store, NOW).startswith("films: 0")
    assert store.tables["semasa_motions"][0]["video_url"] and store.tables["media_generations"][0]["generated_media_url"]
    store.remove_error = None
    assert archive.purge_films(store, NOW).startswith("films: 1")


def test_an_address_outside_the_bucket_names_no_file():
    assert archive.path_of("https://elsewhere.example/motion/a.mp4") == "" and archive.path_of(None) == ""
    assert archive.path_of(BASE + "motion/a.mp4?token=1") == "motion/a.mp4"


# --- pictures of a posted post, and the orphan sweep (Wan, 12 Nov 2026) -----------------------------------------------------

def _pic_store(hours_ago=14, status="posted", other=None, design=False):
    when = (NOW - timedelta(hours=hours_ago)).isoformat()
    posts = [{"id": "p1", "status": status, "media_ids": ["m1"], "posted_at": when}]
    if other:
        posts.append({"id": "p2", "status": other, "media_ids": ["m1"], "posted_at": None})
    meta = {"slide_urls": [BASE + "2026/11/a-slide01.jpg", BASE + "2026/11/a-slide02.jpg"],
            "slide_paths": ["2026/11/a-slide01.jpg", "2026/11/a-slide02.jpg"], "count": 2}
    if design:
        meta["design"] = True
    return FakeStore(semasa_posts=posts, semasa_log=[],
                     media_generations=[{"id": "m1", "type": "image", "mode": "slides", "post_id": "p1", "status": "done",
                                         "generated_media_url": BASE + "2026/11/a-slide01.jpg", "reference_url": None,
                                         "meta": meta}])


def test_the_pictures_of_a_posted_post_are_deleted_after_12_hours_and_the_record_stays():
    store = _pic_store()
    assert archive.purge_pictures(store, NOW) == "pictures: 1 picture set(s) deleted 12h after posting, 2 file(s) removed"
    assert set(store.removed[0][1]) == {"2026/11/a-slide01.jpg", "2026/11/a-slide02.jpg"}
    m = store.tables["media_generations"][0]
    assert m["generated_media_url"] is None and m["meta"]["slide_urls"] == [] and m["meta"]["files_purged_at"]
    assert m["meta"]["purge_hours"] == 12 and m["meta"]["count"] == 2
    assert [r["event"] for r in store.tables["semasa_log"]] == ["pictures.purged"]
    assert archive.purge_pictures(store, NOW).startswith("pictures: 0")                    # once only


def test_pictures_are_kept_inside_the_window_for_an_unposted_post_a_design_or_a_shared_picture():
    for store in (_pic_store(hours_ago=11), _pic_store(status="scheduled"), _pic_store(design=True),
                  _pic_store(other="approved")):
        assert archive.purge_pictures(store, NOW).startswith("pictures: 0") and store.removed == []
        assert store.tables["media_generations"][0]["meta"]["slide_urls"]


def test_a_failed_file_delete_leaves_the_picture_row_untouched_for_the_next_run():
    store = _pic_store()
    store.remove_error = RuntimeError("storage down")
    assert archive.purge_pictures(store, NOW).startswith("pictures: 0")
    assert store.tables["media_generations"][0]["meta"]["slide_urls"]


def test_the_window_is_a_setting_and_never_below_two_hours():
    store = FakeStore(semasa_settings=[{"key": "prune", "value": {"hours": 36}}])
    assert archive.prune_hours(store) == 36
    assert archive.prune_hours(FakeStore(semasa_settings=[])) == 12
    assert archive.prune_hours(FakeStore(semasa_settings=[{"key": "prune", "value": {"hours": 0.5}}])) == 2
    assert archive.prune_hours(FakeStore(semasa_settings=[{"key": "prune", "value": {"hours": 1}}])) == 2


def _orphan_store():
    old, young = (NOW - timedelta(hours=30)).isoformat(), (NOW - timedelta(hours=2)).isoformat()
    f = lambda n, when, size: {"name": n, "id": "x", "created_at": when, "metadata": {"size": size}}  # noqa: E731
    store = FakeStore(
        semasa_posts=[{"id": "p1", "text": {"bm": "x"}}], semasa_log=[], semasa_motions=[],
        media_generations=[{"id": "m1", "meta": {"slide_paths": ["2026/11/used.jpg"]},
                            "generated_media_url": BASE + "motion/film.mp4"}])
    store.listing[""] = [{"name": "2026", "id": None}, {"name": "motion", "id": None}]
    store.listing["2026"] = [{"name": "11", "id": None}]
    store.listing["2026/11"] = [f("used.jpg", old, 1048576), f("lost.jpg", old, 2097152), f("new.jpg", young, 524288)]
    store.listing["motion"] = [f("film.mp4", old, 10485760), f("gone.mp4", old, 5242880)]
    return store


def test_the_orphan_sweep_reports_by_default_and_deletes_nothing():
    store = _orphan_store()
    out = archive.sweep_orphans(store, NOW)
    assert out.startswith("orphans: 2 unreferenced file(s), 7 MB") and "report only" in out
    assert store.removed == []


def test_the_orphan_sweep_deletes_only_old_files_nothing_names_and_never_a_referenced_or_young_one():
    store = _orphan_store()
    out = archive.sweep_orphans(store, NOW, mode="delete")
    assert out.startswith("orphans: 2 unreferenced file(s) deleted") and "0 left" in out
    assert sorted(store.removed[0][1]) == ["2026/11/lost.jpg", "motion/gone.mp4"]      # used.jpg, film.mp4 and new.jpg stay
    assert [r["event"] for r in store.tables["semasa_log"]] == ["orphans.deleted"]


def test_the_orphan_sweep_deletes_nothing_when_a_table_cannot_be_read():
    store = _orphan_store()
    del store.tables["semasa_motions"]
    store.tables["semasa_posts"] = None
    out = archive.sweep_orphans(store, NOW, mode="delete")
    assert out.startswith("orphans: skipped") and store.removed == []
