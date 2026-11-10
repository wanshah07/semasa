"""Wan, 10 Nov 2026: a preview sheet of the film before every approval, and every storyboard says what its subject IS."""
import json
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from semasa import motion, motion_remotion, motion_review

MEANING = "alat yang menumpukan gelombang ultrabunyi untuk memanaskan lapisan kulit"


def _plan():
    return {"scenes": [
        {"id": f"s{i}", "role": r, "heading": f"Tajuk {i}", "lines": ["satu", "dua"], "shot": "x",
         "narration": "Satu dua tiga empat lima enam tujuh lapan sembilan sepuluh."}
        for i, r in enumerate(["hook", "fact", "why", "solution"], 1)
    ] + [{"id": "brand-outro", "heading": "Ikuti kami", "lines": [], "narration": "Ikuti kami"}]}


def test_the_preview_sheet_is_stored_on_the_plan_and_a_failure_never_stops_the_storyboard(tmp_path, monkeypatch):
    up, seen = {}, {}
    monkeypatch.setattr(motion.db, "upload_generated", lambda st, path, data, ct: up.setdefault(path, f"https://cdn/{path}"))

    def fake_preview(folder, data, frames, runner=None):
        seen["props"], seen["frames"] = data, frames
        out = []
        for i in range(len(frames)):
            p = folder / "preview" / f"f{i}.png"
            p.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (270, 480), (200, 230, 215)).save(p)
            out.append(p)
        return out
    monkeypatch.setattr(motion_remotion, "preview", fake_preview)
    plan = _plan()
    note = motion.storyboard_preview(None, {"id": "m1", "stream": "regulab", "options": {}}, plan, tmp_path,
                                     {"s1": "assets/scene-s1.jpg"})
    assert note == "preview sheet: 5 scenes"
    pv = plan["preview"]
    assert pv["sheet"] == "https://cdn/motion/storyboard/m1/preview-sheet.jpg" and len(pv["frames"]) == 5
    assert seen["frames"] == [96, 306, 516, 726, 936]                       # 3.2 s into each provisional 7 s scene
    scenes = seen["props"]["scenes"]
    assert scenes[0]["photo"] == "assets/scene-s1.jpg" and scenes[0]["captions"]         # the first subtitle is on the frame
    assert scenes[-1]["captions"] == [] and seen["props"]["outro"]["logo"].startswith("assets/")
    assert (tmp_path / "preview" / "sheet.jpg").exists()

    def broken(folder, data, frames, runner=None):
        raise RuntimeError("Remotion is not installed on this worker")
    monkeypatch.setattr(motion_remotion, "preview", broken)
    again = _plan()
    again["preview"] = {"sheet": "old"}
    assert "not made" in motion.storyboard_preview(None, {"id": "m1"}, again, tmp_path, {})
    assert "preview" not in again


def test_the_contact_sheet_puts_the_frames_side_by_side(tmp_path):
    for i in range(3):
        Image.new("RGB", (540, 960), (10 * i, 100, 100)).save(tmp_path / f"f{i}.png")
    out = motion_remotion.contact_sheet([tmp_path / f"f{i}.png" for i in range(3)], tmp_path / "s.jpg", height=320, gap=10)
    im = Image.open(out)
    assert im.height == 340 and im.width == 3 * 180 + 4 * 10


def test_the_preview_is_made_by_one_bundle_and_many_stills(tmp_path, monkeypatch):
    monkeypatch.setattr(motion_remotion, "ready", lambda: True)
    monkeypatch.setenv("REMOTION_BROWSER", "/x/chrome")
    cmds = []

    def runner(cmd, **kw):
        cmds.append(cmd)
        for i in range(2):
            Path(cmd[4]).mkdir(parents=True, exist_ok=True)
            (Path(cmd[4]) / f"f{i}.png").write_bytes(b"x")
        return SimpleNamespace(returncode=0, stdout="stills 2", stderr="")
    got = motion_remotion.preview(tmp_path, {"a": 1}, [96, 306], runner)
    assert [p.name for p in got] == ["f0.png", "f1.png"] and len(cmds) == 1
    assert cmds[0][:2] == ["node", "preview.mjs"] and cmds[0][5] == "96,306" and cmds[0][-1] == "/x/chrome"
    assert json.loads((tmp_path / "remotion-preview-props.json").read_text()) == {"a": 1}


def test_the_writer_is_told_to_say_what_the_subject_is_and_the_terms_are_kept():
    row = {"stream": "regulab", "language": "bm", "voice": "male", "options": {}}
    system = motion.build_script_system(row, "")
    assert "WHAT IT IS (every film)" in system and '"terms"' in system and "BEFORE the fact" in system
    plan = {"title": "t", "hook": "Benda pasal HIFU yg takde sapa bagitau kau", "hook_shape": 21,
            "terms": [{"term": "HIFU", "meaning": MEANING},
                      {"term": "", "meaning": "tiada"}, {"term": "PIF", "meaning": "cari sendiri di laman web"}, "x"],
            "scenes": [{"heading": f"H{i}", "lines": ["a"], "narration": "Satu dua tiga empat lima."} for i in range(4)]}

    class LLM:
        def chat_json(self, *a, **k):
            return plan
    import semasa.hook_bank as hb
    orig = hb.declared
    hb.declared = lambda *a, **k: 21
    try:
        got = motion.plan_scenes(LLM(), row, "", "t", "x")
    finally:
        hb.declared = orig
    assert got["terms"] == [{"term": "HIFU", "meaning": MEANING}]


def test_the_review_shows_the_terms_and_the_preview_link_on_telegram():
    plan = _plan()
    plan["terms"] = [{"term": "HIFU", "meaning": "alat gelombang ultrabunyi"}]
    plan["preview"] = {"sheet": "https://cdn/preview-sheet.jpg", "frames": []}
    text = motion_review.telegram_text({"id": "m1", "brief": "x"}, {"kind": "explainer", "plan": plan})
    assert "📖 Apa itu:" in text and "• HIFU: alat gelombang ultrabunyi" in text and "https://cdn/preview-sheet.jpg" in text
    none = motion_review.telegram_text({"id": "m1", "brief": "x"}, {"kind": "explainer", "plan": _plan()})
    assert "Apa itu" not in none and "Pratonton" not in none
