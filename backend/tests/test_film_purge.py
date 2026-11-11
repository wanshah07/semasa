"""A Motion film is deleted for good 72 hours after its post went out (Wan, 11 Nov 2026)."""

from datetime import UTC, datetime, timedelta

from fakestore import FakeStore

from semasa import archive

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
BASE = "https://x.supabase.co/storage/v1/object/public/semasa-generated/"


def _store(hours_ago=80, post_status="posted", other=None, flow="motion"):
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
    assert archive.purge_films(store, NOW) == "films: 1 Motion film(s) deleted 72h after posting, 5 file(s) removed"
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
    for store in (_store(hours_ago=71), _store(post_status="approved")):
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
