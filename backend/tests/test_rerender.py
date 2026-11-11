"""Redraw approved artwork in place and keep the approval (Wan, 11 Nov 2026)."""

import shutil
import subprocess
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fakestore import FakeStore

from semasa import db, media_generator, rerender

NOW = datetime(2026, 11, 11, 1, 30, tzinfo=UTC)          # 09:30 MYT
BASE = "https://x.supabase.co/storage/v1/object/public/semasa-generated/"


class Zernio:
    def __init__(self, fail_on=None):
        self.deleted, self.fail_on = [], fail_on

    def delete(self, post_id, account_id=""):
        if post_id == self.fail_on:
            from semasa.senders import SendError
            raise SendError("refused", "Zernio refused (500)")
        self.deleted.append((post_id, account_id))
        return {}


def _rec(i, status="scheduled", route="zernio"):
    return {"id": f"z{i}", "route": route, "status": status, "account": f"a{i}"}


def _post(pid="p1", date="2026-11-12", slot="13:00", status="scheduled", media=("m1",), stream="regulab", published=None):
    return {"id": pid, "stream": stream, "status": status, "date": date, "slot": slot, "media_ids": list(media),
            "published": published if published is not None else {"instagram": _rec(1), "threads": _rec(2)},
            "errors": {}}


def _slides(mid="m1", **meta):
    return {"id": mid, "mode": "slides", "type": "image", "status": "done", "generated_media_url": BASE + "old1.jpg",
            "meta": {"slides": [{"title": "T", "points": []}], "slide_urls": [BASE + "old1.jpg", BASE + "old2.jpg"],
                     "slide_paths": ["old1.jpg", "old2.jpg"], "stream": "regulab", **meta}}


def _store(posts, media):
    return FakeStore(semasa_posts=posts, media_generations=media, semasa_motions=[], semasa_log=[])


def test_who_is_redrawn_and_who_is_left_alone():
    posts = [_post("ok"), _post("soon", date="2026-11-11", slot="10:30"), _post("linkedin", stream="linkedin"),
             _post("sent", published={"instagram": _rec(1, "sent")}), _post("done", media=("mc",)),
             _post("design", media=("md",)),
             _post("draft", status="draft")]
    media = [_slides("m1"), _slides("mc", cover=True), _slides("md", design="poster")]
    got = rerender.candidates(_store(posts, media), NOW)
    assert [(c["post"]["id"], c["kind"]) for c in got] == [("ok", "carousel")]
    assert rerender.candidates(_store(posts, media), NOW, only={"nope"}) == []


def test_a_dry_run_changes_nothing():
    store = _store([_post()], [_slides()])
    out = rerender.run(store, NOW, dry=True)
    assert out["candidates"] == 1 and "carousel" in out["lines"][0]
    assert store.tables["semasa_posts"][0]["published"] and store.tables["media_generations"][0]["status"] == "done"


def test_a_carousel_is_drawn_again_its_zernio_copy_deleted_and_the_approval_kept(monkeypatch):
    seen = {}

    def fake_slides(store, row, settings, llm=None):
        seen["status_during"] = store.tables["media_generations"][0]["status"]
        seen["post_during"] = dict(store.tables["semasa_posts"][0])
        meta = {**row["meta"], "cover": True, "closing_logo": True, "slide_urls": [BASE + "n1.jpg", BASE + "n2.jpg"]}
        db_row = store.tables["media_generations"][0]
        db_row.update(status="done", generated_media_url=BASE + "n1.jpg", meta=meta)
        return True
    monkeypatch.setattr(media_generator, "process_slides", fake_slides)
    store, z = _store([_post()], [_slides()]), Zernio()
    out = rerender.run(store, NOW, clients={"zernio": z}, settings=SimpleNamespace())
    assert out["done"] == 1 and out["failed"] == 0
    assert z.deleted == [("z1", "a1"), ("z2", "a2")]
    post = store.tables["semasa_posts"][0]
    assert post["status"] == "approved" and post["published"] == {} and post["date"] == "2026-11-12" and post["slot"] == "13:00"
    assert seen["status_during"] == "processing"                 # held back from the publisher while it is redrawn
    assert seen["post_during"]["published"] == {}                # the Zernio copy was gone BEFORE the old files could be
    m = store.tables["media_generations"][0]
    assert m["status"] == "done" and m["meta"]["cover"] is True
    assert [r["event"] for r in store.tables["semasa_log"]] == ["post.rerendered"]


def test_a_redraw_that_fails_puts_the_old_artwork_back_and_the_post_is_queued_again(monkeypatch):
    def boom(store, row, settings, llm=None):
        store.tables["media_generations"][0].update(status="error", generated_media_url=None, error="no")
        raise RuntimeError("renderer down")
    monkeypatch.setattr(media_generator, "process_slides", boom)
    store = _store([_post()], [_slides()])
    out = rerender.run(store, NOW, clients={"zernio": Zernio()}, settings=SimpleNamespace())
    assert out["done"] == 0 and out["failed"] == 1
    m = store.tables["media_generations"][0]
    assert m["status"] == "done" and m["generated_media_url"] == BASE + "old1.jpg" and not m["meta"].get("cover")
    assert store.tables["semasa_posts"][0]["status"] == "approved"      # the publisher queues it again with what it had


def test_a_copy_zernio_will_not_delete_leaves_the_post_exactly_as_it_was():
    post = _post(published={"instagram": _rec(1), "threads": _rec(2)})
    store = _store([post], [_slides()])
    out = rerender.run(store, NOW, clients={"zernio": Zernio(fail_on="z1")}, settings=SimpleNamespace())
    assert out["failed"] == 1 and "NOT touched" in out["lines"][0]
    kept = store.tables["semasa_posts"][0]
    assert kept["published"] == post["published"] and kept["status"] == "scheduled"
    assert store.tables["media_generations"][0]["status"] == "done"


def test_the_channels_already_deleted_are_cleared_when_a_later_one_fails():
    store = _store([_post()], [_slides()])
    out = rerender.run(store, NOW, clients={"zernio": Zernio(fail_on="z2")}, settings=SimpleNamespace())
    post = store.tables["semasa_posts"][0]
    assert out["failed"] == 1 and list(post["published"]) == ["threads"] and post["status"] == "approved"


def test_a_post_held_by_buffer_is_never_touched():
    store = _store([_post(published={"instagram": _rec(1, route="buffer")})], [_slides()])
    z = Zernio()
    out = rerender.run(store, NOW, clients={"zernio": z}, settings=SimpleNamespace())
    assert out["failed"] == 1 and z.deleted == [] and store.tables["semasa_posts"][0]["published"]


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_a_film_gets_its_cover_in_place(tmp_path, monkeypatch):
    film = tmp_path / "film.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0xaa3333:s=270x480:r=30:d=2",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", str(film)], check=True)
    monkeypatch.setattr(rerender.requests, "get", lambda url, timeout=0: SimpleNamespace(
        content=film.read_bytes(), raise_for_status=lambda: None))
    uploads = []
    monkeypatch.setattr(db, "upload_generated", lambda store, path, data, ct: uploads.append(path) or BASE + path)
    media = {"id": "mf", "type": "video", "status": "done", "generated_media_url": BASE + "motion/f1-social.mp4",
             "reference_url": BASE + "motion/f1.mp4", "meta": {"flow": "motion", "motion_id": "f1", "seconds": 2}}
    store = FakeStore(semasa_posts=[_post(media=("mf",))], media_generations=[media], semasa_log=[],
                      semasa_motions=[{"id": "f1", "title": "Satu", "video_path": "motion/f1.mp4",
                                       "video_url": BASE + "motion/f1.mp4",
                                       "social_url": BASE + "motion/f1-social.mp4", "poster_url": BASE + "motion/f1.jpg",
                                       "script": [{"heading": "Kesan sampingan ni akan hilang sendiri?", "kicker": "Kosmetik"}],
                                       "check_report": {}}])
    out = rerender.run(store, NOW, clients={"zernio": Zernio()}, settings=SimpleNamespace())
    assert out["done"] == 1, out["lines"]
    f = store.tables["semasa_motions"][0]
    assert f["video_url"] != BASE + "motion/f1.mp4" and f["duration_s"] > 2.8 and f["check_report"]["cover"]
    m = store.tables["media_generations"][0]
    assert m["status"] == "done" and m["meta"]["cover_added_at"] and m["generated_media_url"] == f["social_url"]
    assert store.removed and set(store.removed[0][1]) == {"motion/f1.mp4", "motion/f1-social.mp4", "motion/f1.jpg"}
    assert rerender.candidates(store, NOW) == []                        # once only


def test_threads_posts_with_a_line_of_tags_alone_are_queued_again_and_the_rest_left():
    def with_text(pid, text, status="scheduled"):
        p = _post(pid, status=status)
        p["lang"], p["text"] = "bm", {"bm": {"threads": text}}
        return p
    posts = [with_text("bad", "Ayat.\n\n#Tag"), with_text("fine", "Ayat.\n\nLagi ayat."),
             _post("no_threads", published={"instagram": _rec(1)})]
    store = _store(posts, [])
    z = Zernio()
    res = rerender.requeue_threads(store, z, NOW)
    assert (res["candidates"], res["done"], res["failed"]) == (1, 1, 0)
    assert z.deleted == [("z2", "a2")]
    row = {p["id"]: p for p in store.table(db.POSTS).select("*").execute().data}
    assert "threads" not in row["bad"]["published"] and "instagram" in row["bad"]["published"]      # the other channel stays
    assert row["bad"]["status"] == "approved" and "threads" in row["fine"]["published"]
    dry = rerender.requeue_threads(_store(posts, []), Zernio(), NOW, dry=True)
    assert dry["candidates"] == 1 and dry["done"] == 0


def test_a_refused_delete_leaves_the_threads_post_exactly_as_it_was():
    p = _post("bad")
    p["lang"], p["text"] = "bm", {"bm": {"threads": "Ayat.\n\n#Tag"}}
    store = _store([p], [])
    res = rerender.requeue_threads(store, Zernio(fail_on="z2"), NOW)
    assert (res["done"], res["failed"]) == (0, 1)
    assert store.table(db.POSTS).select("*").execute().data[0]["published"]["threads"]["id"] == "z2"


class _Hub(Zernio):
    def __init__(self):
        super().__init__()
        self.sent = []

    def create(self, channel_id, service, text, pictures, alt, due_at):
        self.sent.append((channel_id, service, text, pictures, due_at))
        return {"id": "znew", "status": "sent", "channelId": channel_id, "dueAt": None,
                "externalLink": "https://www.threads.com/@x/post/1"}

    def create_video(self, channel_id, service, text, video, due_at):
        return self.create(channel_id, service, text, [video["url"]], "", due_at)

    def confirm(self, post_id, **kw):
        return {"id": post_id, "status": "sent", "externalLink": "https://www.threads.com/@x/post/1"}


def _send_setup(monkeypatch, published):
    from semasa import publisher
    post = _post("late", date="2026-11-11", slot="10:30", published=published)
    post["lang"], post["text"], post["channels"] = "bm", {"bm": {"threads": "Ayat satu.\n\n#Tag"}}, ["threads"]
    store = _store([post], [{"id": "m1", "status": "done", "type": "image", "mode": "slides",
                             "generated_media_url": BASE + "a.jpg", "meta": {"slide_urls": [BASE + "a.jpg", BASE + "b.jpg"]}}])
    monkeypatch.setattr(publisher, "load_settings", lambda s: {"channels": {"zernio": {
        "enabled": True, "accounts": {"threads": {"id": "acct-t", "key": "1"}}}}})
    monkeypatch.setattr(publisher, "post_channels", lambda settings, p, has_video=None: ["threads"])
    return store


def test_send_now_sends_the_one_empty_channel_past_the_lateness_rule(monkeypatch):
    store = _send_setup(monkeypatch, {})
    hub = _Hub()
    out = rerender.send_now(store, hub, "late", "threads", datetime(2026, 11, 11, 3, 30, tzinfo=UTC))
    assert out.startswith("threads sent now"), out
    assert hub.sent and hub.sent[0][4] is None                      # no scheduled time: Zernio publishes at once
    row = store.table(db.POSTS).select("*").execute().data[0]
    assert row["published"]["threads"]["status"] == "sent" and row["published"]["threads"]["mode"] == "shareNow"
    assert row["status"] == "posted"


def test_send_now_leaves_a_channel_that_already_has_a_record(monkeypatch):
    store = _send_setup(monkeypatch, {"threads": _rec(9, "scheduled")})
    hub = _Hub()
    assert rerender.send_now(store, hub, "late", "threads", NOW).startswith("not sent: threads already has a record")
    assert hub.sent == []


def test_a_film_made_with_its_cover_is_never_given_a_second_one():
    """Wan, 11 Nov 2026 (Instagram needs the cover): a film whose own report says it opens on the cover is not a candidate."""
    film = {"id": "mf", "mode": "clip", "type": "video", "status": "done", "generated_media_url": BASE + "f.mp4",
            "meta": {"flow": "motion", "motion_id": "f1"}}
    store = FakeStore(semasa_posts=[_post("pf", media=("mf",))], media_generations=[film],
                      semasa_motions=[{"id": "f1", "check_report": {"cover": {"seconds": 1.1}}}], semasa_log=[])
    assert rerender.candidates(store, NOW) == []
    bare = FakeStore(semasa_posts=[_post("pf", media=("mf",))], media_generations=[film],
                     semasa_motions=[{"id": "f1", "check_report": {}}], semasa_log=[])
    assert [c["kind"] for c in rerender.candidates(bare, NOW)] == ["film"]
