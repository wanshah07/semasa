"""Wan, 10 Nov 2026: the storyboard is shown with its pictures before anything is rendered; the approved pictures are the
film's; no writer's label (HOOK...) reaches a reader; the closing card carries the real logo."""
import io
from types import SimpleNamespace

from PIL import Image

from semasa import motion, motion_remotion, motion_review


def _jpg(colour=(40, 120, 90)):
    buf = io.BytesIO()
    Image.new("RGB", (900, 900), colour).save(buf, "JPEG")
    return buf.getvalue()


def _plan():
    return {"photo_query": "lab bench", "scenes": [
        {"id": f"s{i}", "role": r, "kicker": k, "heading": f"Tajuk {i}", "lines": ["a"], "narration": "kata", "shot": f"shot {i}"}
        for i, (r, k) in enumerate([("hook", "HOOK"), ("fact", "CERITA & FAKTA"), ("why", "TERLEPAS"), ("solution", "CTA")], 1)
    ] + [{"id": "brand-outro", "kicker": "", "heading": "Ikuti kami", "lines": []}]}


def test_every_teaching_scene_of_the_storyboard_gets_a_stored_picture(tmp_path, monkeypatch):
    plan, row, up = _plan(), {"id": "m1", "stream": "regulab", "options": {}}, {}

    def draw(store, row, scenes, folder, **kw):
        out = {}
        for sc in scenes:
            if sc["id"] != "brand-outro":
                (folder / "assets").mkdir(parents=True, exist_ok=True)
                (folder / "assets" / f"scene-{sc['id']}.jpg").write_bytes(_jpg())
                out[sc["id"]] = {"path": f"assets/scene-{sc['id']}.jpg", "id": sc["id"], "credit": "", "page": "", "alt": ""}
        return out, "Pictures: 4 of 4 scenes drawn"

    monkeypatch.setattr(motion, "idea_pictures", lambda *a, **k: ([], ""))
    monkeypatch.setattr(motion, "fetch_photos", lambda *a, **k: ([], ""))
    monkeypatch.setattr(motion.motion_gpt_images, "draw_scenes", draw)
    monkeypatch.setattr(motion.db, "upload_generated",
                        lambda store, path, data, ct: up.setdefault(path, f"https://cdn.example/{path}"))
    note = motion.storyboard_pictures(None, row, plan, tmp_path)
    assert "storyboard pictures: 4" in note
    teach = plan["scenes"][:4]
    assert [sc["image"] for sc in teach] == [f"https://cdn.example/motion/storyboard/m1/s{i}.jpg" for i in range(1, 5)]
    assert all(sc["image_shot"] == sc["shot"] and "photo" not in sc for sc in teach)
    assert "image" not in plan["scenes"][4]                           # the closing card has no picture


def test_a_picture_maker_that_fails_never_stops_the_storyboard(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("no picture maker")
    monkeypatch.setattr(motion, "idea_pictures", boom)
    plan = _plan()
    assert "not made" in motion.storyboard_pictures(None, {"id": "m1"}, plan, tmp_path)
    assert len(plan["scenes"]) == 5


def test_the_approved_pictures_are_reused_and_a_rewritten_shot_is_drawn_again(tmp_path):
    scenes = _plan()["scenes"]
    for sc in scenes[:4]:
        sc.update(image=f"https://cdn.example/{sc['id']}.jpg", image_shot=sc["shot"], image_credit="A / Unsplash")
    scenes[1]["shot"] = "a different picture"                         # Wan rewrote this one in review
    scenes[2]["image"] = "http://insecure.example/x.jpg"              # not an address the worker will fetch
    asked = []

    def get(url):
        asked.append(url)
        return SimpleNamespace(content=_jpg(), raise_for_status=lambda: None)

    got = motion.approved_pictures(scenes, tmp_path, get=get)
    assert sorted(got) == ["s1", "s4"] and asked == ["https://cdn.example/s1.jpg", "https://cdn.example/s4.jpg"]
    assert got["s1"]["path"] == "assets/scene-s1.jpg" and (tmp_path / got["s1"]["path"]).exists()
    assert got["s1"]["credit"] == "A / Unsplash"


def test_a_picture_that_cannot_be_fetched_is_simply_drawn_again(tmp_path):
    scenes = _plan()["scenes"][:1]
    scenes[0].update(image="https://cdn.example/s1.jpg", image_shot=scenes[0]["shot"])

    def get(url):
        raise OSError("gone")
    assert motion.approved_pictures(scenes, tmp_path, get=get) == {}


def test_the_review_shows_scene_numbers_and_pictures_never_the_writers_labels():
    plan = _plan()
    plan["scenes"][0]["image"] = "https://cdn.example/s1.jpg"
    sb = {"kind": "explainer", "plan": plan}
    rows = motion_review.scenes_of(sb)
    assert [r["label"] for r in rows] == ["Babak 1", "Babak 2", "Babak 3", "Babak 4", "Penutup"]
    assert rows[0]["image"] == "https://cdn.example/s1.jpg"
    text = motion_review.telegram_text({"id": "m1", "brief": "x"}, sb)
    assert "HOOK" not in text and "TERLEPAS" not in text and "https://cdn.example/s1.jpg" in text


def test_remotion_draws_no_label_and_closes_on_the_real_logo():
    scenes = [{**sc, "start": i * 3.0, "duration": 3.0} for i, sc in enumerate(_plan()["scenes"])]
    pal = {"ground": "#fff", "ink": "#000", "accent": "#111", "accent2": "#eee"}
    p = motion_remotion.props(scenes, 15.0, 1080, 1920, pal, name="ws.regulab", logo="assets/official-logo-transparent.png")
    assert all("kicker" not in sc for sc in p["scenes"])
    assert p["outro"] == {"name": "ws.regulab", "line": "Ikuti kami", "logo": "assets/official-logo-transparent.png",
                          "brand": True}
    li = motion_remotion.props(scenes, 15.0, 1080, 1080, pal, name="Ts. ChM Ridzuan", logo="assets/wan.png")
    assert li["outro"]["brand"] is False and li["outro"]["name"] == "Ts. ChM Ridzuan"
