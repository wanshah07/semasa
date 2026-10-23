"""Motion: the authoring prompt, the composition guard, the check report, and the worker loop with a fake CLI."""

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from fakestore import FakeStore

from semasa import motion

NOW = datetime(2026, 10, 23, 6, 0, tzinfo=UTC)
GOOD = ('<!doctype html><html lang="ms" data-resolution="portrait"><head><script src="' + motion.GSAP + '"></script></head>'
        '<body><div id="root" data-composition-id="main" data-start="0" data-duration="12" data-width="1080" data-height="1920">'
        '<h1 id="t" class="clip" data-start="0" data-duration="12">Hai</h1></div>'
        '<script>const tl = gsap.timeline({paused: true}); window.__timelines["main"] = tl; tl.seek(0);</script></body></html>')


def test_build_system_carries_size_seconds_voice_and_wans_prompt():
    s = motion.build_system({"stream": "regulab", "resolution": "portrait", "seconds": 15}, "Guna warna hijau.")
    assert 'data-resolution="portrait"' in s and "width=1080, height=1920" in s and "15 seconds" in s
    assert "Bahasa Malaysia" in s and "WAN'S OWN INSTRUCTIONS:\nGuna warna hijau." in s and motion.GSAP in s
    s2 = motion.build_system({"stream": "linkedin", "resolution": "landscape", "seconds": 8}, "")
    assert "width=1920, height=1080" in s2 and "English" in s2 and "WAN'S OWN" not in s2
    assert "gsap.timeline({ paused: true })" in s2 and '{"title":' in s2, "literal braces survive the format"


def test_build_user_adds_the_link_words_and_the_findings():
    u = motion.build_user({"brief": "PFAS dalam kosmetik", "source_url": "https://x/y"}, "Tajuk", "Isi halaman")
    assert "BRIEF: PFAS" in u and "LINK: https://x/y" in u and "title: Tajuk" in u and "Isi halaman" in u
    findings = [{"code": "clip_missing", "message": "no data-start"}]
    u2 = motion.build_user({"brief": "b"}, "", "", findings, "<html>old</html>")
    assert "THE CHECK FAILED" in u2 and "[clip_missing] no data-start" in u2 and "PREVIOUS FILE:\n<html>old</html>" in u2


def test_clean_html_strips_fences_and_refuses_media_or_random():
    assert motion.clean_html("```html\n" + GOOD + "\n```") == GOOD
    bads = ("<html><body>no timeline</body></html>", GOOD.replace("<h1", "<video src=x></video><h1"),
            GOOD + "<script>Math.random()</script>")
    for bad in bads:
        try:
            motion.clean_html(bad)
        except ValueError:
            continue
        raise AssertionError("accepted " + bad[:40])


def _runner(check_json=None, render_ok=True, calls=None):
    calls = calls if calls is not None else []

    def run(cmd, cwd=None, capture_output=True, text=True, timeout=None, env=None):
        calls.append(cmd)
        if "check" in cmd:
            body = check_json if check_json is not None else {"ok": True}
            return SimpleNamespace(returncode=0, stdout=json.dumps(body), stderr="")
        if "render" in cmd:
            out = Path(cmd[cmd.index("--output") + 1])
            if render_ok:
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"x" * 100)
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            return SimpleNamespace(returncode=1, stdout="", stderr="Chrome crashed")
        if cmd[0] == "ffmpeg":
            Path(cmd[-1]).write_bytes(b"\xff\xd8jpg")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if cmd[0] == "ffprobe":
            meta = {"streams": [{"width": 1080, "height": 1920}], "format": {"duration": "12.0"}}
            return SimpleNamespace(returncode=0, stdout=json.dumps(meta), stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    return run


def test_check_reads_errors_and_warnings_by_section():
    rep = {"ok": False, "lint": {"findings": [{"code": "clip_missing_start", "severity": "error", "message": "x"}]},
           "craft": {"findings": [{"code": "first_frame_empty", "severity": "warning", "message": "y"}]}}
    out = motion.check(Path("/tmp"), "0.8.188", _runner(rep))
    assert out["ok"] is False and [e["code"] for e in out["errors"]] == ["clip_missing_start"]
    assert out["warnings"][0]["section"] == "craft"
    ok = motion.check(Path("/tmp"), "0.8.188", _runner({"ok": True, "craft": {"findings": []}}))
    assert ok == {"ok": True, "errors": [], "warnings": []}


class FakeLLM:
    last_model = "m1"

    def __init__(self, answers):
        self.answers, self.asked = list(answers), []

    def chat_json(self, system, user, **kw):
        self.asked.append((system, user))
        return self.answers.pop(0) if self.answers else None


class Bucket:
    def __init__(self):
        self.files = {}

    def upload(self, path, data, opts):
        self.files[path] = (data, opts["content-type"])

    def get_public_url(self, path):
        return f"https://cdn/{path}"


class Store(FakeStore):
    def __init__(self):
        super().__init__()
        self.bucket = Bucket()
        self.storage = SimpleNamespace(from_=lambda name: self.bucket)


def _row(store, **over):
    row = {"status": "pending", "brief": "Tiga perkara tentang PFAS", "source_url": "", "stream": "regulab",
           "resolution": "portrait", "seconds": 12, "attempts": 0, "created_at": "2026-10-23T05:00:00Z"}
    row.update(over)
    return store.table(motion.TABLE).insert(row).execute().data[0]


def test_process_writes_checks_renders_and_stores_the_video(tmp_path):
    store = Store()
    r = _row(store)
    settings = {"prompt": "Guna font besar.", "cli": "0.8.188"}
    llm = FakeLLM([{"title": "PFAS: tiga perkara", "html": GOOD}])
    calls = []
    assert motion.process(store, llm, {**r, "attempts": 1}, settings, runner=_runner(calls=calls), workdir=tmp_path, now=NOW)
    got = store.table(motion.TABLE).select("*").eq("id", r["id"]).execute().data[0]
    assert got["status"] == "done" and got["title"] == "PFAS: tiga perkara"
    assert got["video_url"] == f"https://cdn/motion/{r['id']}.mp4"
    assert got["poster_url"].endswith(".jpg") and got["width"] == 1080 and got["duration_s"] == 12.0 and got["model"] == "m1"
    assert got["html"] == GOOD and got["check_report"]["ok"] is True and got["bytes"] > 0
    assert "Guna font besar." in llm.asked[0][0] and "BRIEF: Tiga perkara" in llm.asked[0][1]
    assert [c[3] if len(c) > 3 else c[0] for c in calls][:2] == ["check", "render"]
    assert (tmp_path / r["id"][:8] / "index.html").read_text() == GOOD
    assert store.bucket.files[f"motion/{r['id']}.mp4"][1] == "video/mp4"


def test_run_claims_pending_rows_and_reads_the_settings(monkeypatch):
    store = Store()
    _row(store)
    _row(store, status="done")
    store.tables["semasa_settings"] = [{"key": "motion", "value": {"prompt": "P", "cli": "9.9.9"}}]
    seen = []
    monkeypatch.setattr(motion, "process",
                        lambda s, llm, row, settings, **kw: seen.append((row["status"], row["attempts"], settings)) or True)
    assert motion.run(store, FakeLLM([]), now=NOW) == {"claimed": 1, "done": 1, "failed": 0}
    assert seen == [("pending", 1, {"prompt": "P", "cli": "9.9.9"})]
    assert motion.load_settings(FakeStore()) == {"prompt": "", "cli": motion.CLI_VERSION}


def test_a_failed_check_goes_back_to_the_writer_once(tmp_path):
    store = Store()
    r = _row(store)
    bad_then_good = [{"title": "t", "html": GOOD.replace("Hai", "Dulu")}, {"title": "t", "html": GOOD}]
    llm = FakeLLM(bad_then_good)
    reports = [{"ok": False, "lint": {"findings": [{"code": "x", "severity": "error", "message": "fix me"}]}}, {"ok": True}]

    def runner(cmd, **kw):
        if "check" in cmd:
            return SimpleNamespace(returncode=0, stdout=json.dumps(reports.pop(0)), stderr="")
        return _runner()(cmd, **kw)
    cfg = {"prompt": "", "cli": "0.8.188"}
    assert motion.process(store, llm, {**r, "attempts": 1}, cfg, runner=runner, workdir=tmp_path, now=NOW)
    assert len(llm.asked) == 2 and "THE CHECK FAILED" in llm.asked[1][1] and "[x] fix me" in llm.asked[1][1]
    assert store.table(motion.TABLE).select("*").eq("id", r["id"]).execute().data[0]["html"] == GOOD


def test_a_render_failure_retries_then_errors(tmp_path):
    store = Store()
    r = _row(store)
    ok = motion.process(store, FakeLLM([{"html": GOOD}]), {**r, "attempts": 1}, {"prompt": "", "cli": "0.8.188"},
                        runner=_runner(render_ok=False), workdir=tmp_path, now=NOW)
    got = store.table(motion.TABLE).select("*").eq("id", r["id"]).execute().data[0]
    assert ok is False and got["status"] == "pending" and "Chrome crashed" in got["error"]
    motion.process(store, FakeLLM([{"html": GOOD}]), {**r, "attempts": motion.MAX_ATTEMPTS}, {"prompt": "", "cli": "0.8.188"},
                   runner=_runner(render_ok=False), workdir=tmp_path, now=NOW)
    assert store.table(motion.TABLE).select("*").eq("id", r["id"]).execute().data[0]["status"] == "error"


def test_a_bad_composition_is_an_error_at_once_and_no_llm_says_so(tmp_path):
    store = Store()
    r = _row(store)
    motion.process(store, FakeLLM([{"html": "<html>nope</html>"}]), {**r, "attempts": 1}, {"prompt": "", "cli": "0.8.188"},
                   runner=_runner(), workdir=tmp_path, now=NOW)
    got = store.table(motion.TABLE).select("*").eq("id", r["id"]).execute().data[0]
    assert got["status"] == "error" and "whole HyperFrames composition" in got["error"]
    r2 = _row(store)
    motion.process(store, None, {**r2, "attempts": 1}, {"prompt": "", "cli": "0.8.188"}, runner=_runner(), workdir=tmp_path,
                   now=NOW)
    assert "no AI writer" in store.table(motion.TABLE).select("*").eq("id", r2["id"]).execute().data[0]["error"]


def test_source_words_reads_the_link_and_survives_a_dead_one(monkeypatch):
    page = "<html><title>T</title><body><p>Isi penting</p></body></html>"
    monkeypatch.setattr(motion.fetch, "get", lambda url, timeout=25: SimpleNamespace(text=page))
    title, text = motion.source_words("https://x/y")
    assert title == "T" and "Isi penting" in text
    monkeypatch.setattr(motion.fetch, "get", lambda url, timeout=25: (_ for _ in ()).throw(RuntimeError("down")))
    assert motion.source_words("https://x/z") == ("", "")
    assert motion.source_words("") == ("", "")
