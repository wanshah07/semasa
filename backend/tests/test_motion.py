"""Motion: the authoring prompt, the composition guard, the check report, and the worker loop with a fake CLI."""

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fakestore import FakeStore

from semasa import motion

NOW = datetime(2026, 10, 23, 6, 0, tzinfo=UTC)
# the writer's plan (the first answer every film needs since the voice came in, 24 Oct 2026)
SCRIPT = {"title": "PFAS: tiga perkara", "photo_query": "laboratory chemicals", "scenes": [
    {"kicker": "x", "heading": "Tiga perkara", "lines": ["satu", "dua"], "narration": "Hai. Tiga perkara tentang PFAS."},
    {"kicker": "x", "heading": "PFAS ialah bahan kimia", "lines": ["tahan lama"],
     "narration": "PFAS ialah bahan kimia tahan lama."},
    {"kicker": "x", "heading": "Kenapa ia penting", "lines": [], "narration": "Ia kekal lama dalam alam."},
    {"kicker": "x", "heading": "Semak label", "lines": [], "narration": "Semak label dahulu."}]}


def four(heading="Tajuk", **over):
    """A four-scene plan (Hook, Fakta, Kenapa, Solusi) with every scene carrying `over`."""
    return {**SCRIPT, "scenes": [{"kicker": "x", "heading": heading, "lines": ["satu"], "narration": "Satu dua tiga.", **over}
                                 for _ in range(4)]}


def fake_speak(text, voice, out, runner=None):
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(b"ID3" + b"\x00" * 2000)
    n = len(text.split())
    return {"duration": round(0.4 * n, 2),
            "words": [[round(0.4 * i, 2), round(0.4 * i + 0.3, 2), w] for i, w in enumerate(text.split())]}


@pytest.fixture(autouse=True)
def _no_real_voice(monkeypatch):
    monkeypatch.setattr(motion.voice_mod, "speak", fake_speak)
GOOD = ('<!doctype html><html lang="ms" data-resolution="portrait"><head><script src="' + motion.GSAP + '"></script></head>'
        '<body><div id="root" data-composition-id="main" data-start="0" data-duration="12" data-width="1080" data-height="1920">'
        '<h1 id="t" class="clip" data-start="0" data-duration="12">Hai</h1></div>'
        '<script>const tl = gsap.timeline({paused: true}); window.__timelines["main"] = tl; tl.seek(0);</script></body></html>')


def test_build_system_carries_size_seconds_voice_and_wans_prompt():
    s = motion.build_system({"stream": "regulab", "resolution": "portrait", "seconds": 15}, "Guna warna hijau.")
    assert 'data-resolution="portrait"' in s and "width=1080, height=1920" in s and "30 seconds" in s
    assert "Bahasa Malaysia" in s and "WAN'S OWN INSTRUCTIONS:\nGuna warna hijau." in s and motion.GSAP in s
    s2 = motion.build_system({"stream": "linkedin", "resolution": "landscape", "seconds": 8}, "")
    assert "width=1920, height=1080" in s2 and "English" in s2 and "WAN'S OWN" not in s2
    assert "gsap.timeline({ paused: true })" in s2 and "<!-- title:" in s2, "literal braces survive the format"


def test_the_language_is_the_rows_choice_and_falls_back_to_the_stream():
    # Wan, 24 Oct 2026: "choice for english, malay, or english + malay version"
    assert motion.language_of({"stream": "regulab"}) == "bm" and motion.language_of({"stream": "linkedin"}) == "en"
    assert motion.language_of({"stream": "regulab", "language": "en"}) == "en"
    assert motion.language_of({"stream": "linkedin", "language": "nope"}) == "en"
    s = motion.build_system({"stream": "regulab", "resolution": "portrait", "seconds": 10, "language": "en"}, "")
    assert 'lang="en"' in s and "Write the words in English." in s and "ws.regulab" in s, "English words, ws.regulab's voice"
    s = motion.build_system({"stream": "linkedin", "resolution": "square", "seconds": 10, "language": "both"}, "")
    assert 'lang="ms"' in s and "BOTH languages" in s and "English line directly under it" in s


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
            meta = {"streams": [{"width": 1080, "height": 1920}], "format": {"duration": "30.0"}}
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
    llm = FakeLLM([SCRIPT, {"title": "PFAS: tiga perkara", "html": GOOD}])
    calls = []
    assert motion.process(store, llm, {**r, "attempts": 1}, settings, runner=_runner(calls=calls), workdir=tmp_path, now=NOW)
    got = store.table(motion.TABLE).select("*").eq("id", r["id"]).execute().data[0]
    assert got["status"] == "done" and got["title"] == "PFAS: tiga perkara"
    assert got["video_url"] == f"https://cdn/motion/{r['id']}.mp4"
    assert got["poster_url"].endswith(".jpg") and got["width"] == 1080 and got["duration_s"] == 30.0 and got["model"] == "m1"
    assert ">Hai</h1>" in got["html"] and got["check_report"]["ok"] is True and got["bytes"] > 0
    assert [sc["kicker"] for sc in got["script"]] == ["HOOK", "FAKTA", "KENAPA", "SOLUSI", ""], "the flow, labelled by the worker"
    assert "Guna font besar." in llm.asked[1][0] and "BRIEF: Tiga perkara" in llm.asked[1][1]
    assert "SCENES, FIXED" in llm.asked[1][1] and 'data-start="0"' in llm.asked[1][1], "the film is written to the recorded times"
    assert [c[3] if len(c) > 3 else c[0] for c in calls][:2] == ["check", "render"]
    index = (tmp_path / r["id"][:8] / "index.html").read_text()
    assert 'id="sv-s1"' in index and 'src="assets/voice-1.mp3"' in index and "<audio" in index
    assert "mascot" not in index and "sm-mouth" not in index, "no presenter (Wan, 25 Oct 2026)"
    assets = tmp_path / r["id"][:8] / "assets"
    assert (assets / "voice-2.mp3").exists() and not list(assets.glob("mascot-*"))
    assert got["script"][0]["narration"] == "Hai. Tiga perkara tentang PFAS." and got["script"][1]["start"] > 0
    assert "voice: ms-MY-OsmanNeural" in got["style_note"]
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


def test_a_failed_check_goes_back_to_the_writer(tmp_path):
    store = Store()
    r = _row(store)
    bad_then_good = [SCRIPT, {"title": "t", "html": GOOD.replace("Hai", "Dulu")}, {"title": "t", "html": GOOD}]
    llm = FakeLLM(bad_then_good)
    reports = [{"ok": False, "lint": {"findings": [{"code": "x", "severity": "error", "message": "fix me"}]}}, {"ok": True}]

    def runner(cmd, **kw):
        if "check" in cmd:
            return SimpleNamespace(returncode=0, stdout=json.dumps(reports.pop(0)), stderr="")
        return _runner()(cmd, **kw)
    cfg = {"prompt": "", "cli": "0.8.188"}
    assert motion.process(store, llm, {**r, "attempts": 1}, cfg, runner=runner, workdir=tmp_path, now=NOW)
    assert len(llm.asked) == 3 and "THE CHECK FAILED" in llm.asked[2][1] and "[x] fix me" in llm.asked[2][1]
    assert ">Hai</h1>" in store.table(motion.TABLE).select("*").eq("id", r["id"]).execute().data[0]["html"]


def test_a_render_failure_retries_then_errors(tmp_path):
    store = Store()
    r = _row(store)
    ok = motion.process(store, FakeLLM([SCRIPT, {"html": GOOD}]), {**r, "attempts": 1}, {"prompt": "", "cli": "0.8.188"},
                        runner=_runner(render_ok=False), workdir=tmp_path, now=NOW)
    got = store.table(motion.TABLE).select("*").eq("id", r["id"]).execute().data[0]
    assert ok is False and got["status"] == "pending" and "Chrome crashed" in got["error"]
    motion.process(store, FakeLLM([SCRIPT, {"html": GOOD}]), {**r, "attempts": motion.MAX_ATTEMPTS},
                   {"prompt": "", "cli": "0.8.188"},
                   runner=_runner(render_ok=False), workdir=tmp_path, now=NOW)
    assert store.table(motion.TABLE).select("*").eq("id", r["id"]).execute().data[0]["status"] == "error"


def test_a_bad_composition_ends_in_the_safe_layout_and_no_llm_says_so(tmp_path):
    store = Store()
    r = _row(store)
    motion.process(store, FakeLLM([SCRIPT, {"html": "<html>nope</html>"}]), {**r, "attempts": 1},
                   {"prompt": "", "cli": "0.8.188"},
                   runner=_runner(), workdir=tmp_path, now=NOW)
    got = store.table(motion.TABLE).select("*").eq("id", r["id"]).execute().data[0]
    assert got["status"] == "done" and "safe layout used" in got["style_note"], "a film, never a stuck row"
    assert got["check_report"]["layout"]["layout"] == "safe-layout" and "perkara" in got["html"]
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


class FakeGH:
    def __init__(self, files):
        self.files, self.calls = files, []

    def maybe(self, path, params=None, *, raw=False, default=None):
        self.calls.append(path)
        for name, text in self.files.items():
            if path.endswith("/" + name):
                return text
        return default


def test_style_words_reads_the_chosen_motion_repo_and_the_writer_is_told_it_is_a_reference():
    store = FakeStore()
    lib = store.table("semasa_repo_library").insert({"full_name": "heygen-com/hyperframes", "url": "https://github.com/heygen-com/hyperframes",
                                                     "summary_en": "HTML to MP4.", "how_to_run": "npx hyperframes render",
                                                     "default_branch": "main", "readme_excerpt": "excerpt"}).execute().data[0]
    gh = FakeGH({"readme": "# HyperFrames\nWrite HTML.", "SKILL.md": "Use power3.out eases."})
    name, text = motion.style_words(store, gh, {"style_repo_id": lib["id"]})
    assert name == "heygen-com/hyperframes" and "HTML to MP4." in text and "Write HTML." in text and "power3.out" in text
    assert "npx hyperframes render" in text
    # no GitHub reader: the library's own excerpt stands in
    _n, text2 = motion.style_words(store, None, {"style_repo_id": lib["id"]})
    assert "excerpt" in text2 and "Write HTML." not in text2
    assert motion.style_words(store, gh, {"style_repo_id": None}) == ("", "")
    assert motion.style_words(store, gh, {"style_repo_id": "missing"}) == ("", "")
    u = motion.build_user({"brief": "b"}, "", "", style=(name, text))
    assert "STYLE REFERENCE (the motion repo heygen-com/hyperframes)" in u and "not a dependency" in u and "power3.out" in u
    assert "STYLE REFERENCE" not in motion.build_user({"brief": "b"}, "", "")


def test_process_records_the_style_it_used(tmp_path):
    store = Store()
    lib = store.table("semasa_repo_library").insert({"full_name": "a/style", "summary_en": "Bold type."}).execute().data[0]
    r = _row(store, style_repo_id=lib["id"])
    llm = FakeLLM([SCRIPT, {"title": "t", "html": GOOD}])
    assert motion.process(store, llm, {**r, "attempts": 1}, {"prompt": "", "cli": "0.8.188"}, runner=_runner(), workdir=tmp_path,
                          now=NOW, gh=FakeGH({}))
    got = store.table(motion.TABLE).select("*").eq("id", r["id"]).execute().data[0]
    assert got["style_note"].startswith("a/style: ") and "Bold type." in llm.asked[0][1]


class FakePicture:
    name = "openai"

    def __init__(self, fail=False):
        self.fail, self.prompts = fail, []

    def generate_from_text(self, prompt, options):
        self.prompts.append(prompt)
        if self.fail:
            raise RuntimeError("402 credits")
        from semasa.providers import Generated
        return Generated(b"\x89PNG...", "image/png", "gpt-image-2")


def test_the_ai_background_is_drawn_handed_to_the_writer_and_recorded(tmp_path):
    store = Store()
    r = _row(store, ai_background=True)
    llm = FakeLLM([SCRIPT, {"title": "t", "html": GOOD}])
    pic = FakePicture()
    assert motion.process(store, llm, {**r, "attempts": 1}, {"prompt": "", "cli": "0.8.188"}, runner=_runner(), workdir=tmp_path,
                          now=NOW, picture_provider=pic)
    assert (tmp_path / r["id"][:8] / "assets" / "bg.png").read_bytes().startswith(b"\x89PNG")
    assert "url(assets/bg.png)" in llm.asked[1][0] and "Tiga perkara tentang PFAS" in pic.prompts[0]
    got = store.table(motion.TABLE).select("*").eq("id", r["id"]).execute().data[0]
    assert got["status"] == "done" and "background: gpt-image-2 via openai" in got["style_note"]


def test_no_background_asked_means_none_is_drawn_and_a_failed_one_never_stops_the_video(tmp_path):
    store = Store()
    r = _row(store)
    llm = FakeLLM([SCRIPT, {"title": "t", "html": GOOD}])
    pic = FakePicture()
    motion.process(store, llm, {**r, "attempts": 1}, {"prompt": "", "cli": "0.8.188"}, runner=_runner(), workdir=tmp_path,
                   now=NOW, picture_provider=pic)
    assert pic.prompts == [] and "assets/bg" not in llm.asked[0][0]
    r2 = _row(store, ai_background=True)
    llm2 = FakeLLM([SCRIPT, {"title": "t", "html": GOOD}])
    assert motion.process(store, llm2, {**r2, "attempts": 1}, {"prompt": "", "cli": "0.8.188"}, runner=_runner(),
                          workdir=tmp_path, now=NOW, picture_provider=FakePicture(fail=True))
    got = store.table(motion.TABLE).select("*").eq("id", r2["id"]).execute().data[0]
    assert got["status"] == "done" and "background not made: 402 credits" in got["style_note"]
    assert "assets/bg" not in llm2.asked[0][0]


def test_voice_scenes_times_the_film_to_the_recording_and_off_means_silence(tmp_path):
    # Wan, 24 Oct 2026: "make sure got voice or audio"
    scenes = [{"id": "s1", "narration": "Hai semua, tiga perkara."}, {"id": "s2", "narration": ""},
              {"id": "s3", "narration": "Itu sahaja untuk hari ini."}]
    got, total, note = motion.voice_scenes([dict(s) for s in scenes], "bm", "female", tmp_path, speak=fake_speak)
    assert note == "voice: ms-MY-YasminNeural" and got[0]["audio"] == "assets/voice-1.mp3" and got[1]["audio"] == ""
    assert got[0]["start"] == 0 and got[0]["duration"] == 1.9                 # 4 words x 0.4 + the short pad
    assert got[1]["start"] == 2.1 and got[1]["duration"] == motion.SILENT_MIN    # nothing to read: the reading floor
    assert got[2]["start"] == 6.3 and total == round(6.3 + got[2]["duration"], 2)
    off, total_off, note_off = motion.voice_scenes([dict(s) for s in scenes], "bm", "off", tmp_path, speak=fake_speak)
    assert note_off == "no voice" and all(not s["audio"] for s in off) and total_off > 0
    # a voice that fails never stops the film
    def broken(text, voice, out, runner=None):
        raise RuntimeError("TLS")
    quiet, _, n = motion.voice_scenes([dict(s) for s in scenes], "en", "male", tmp_path, speak=broken)
    assert n.startswith("voice failed") and all(not s["audio"] for s in quiet)


def test_the_voice_is_put_into_the_film_after_the_writer_and_no_presenter_is_ever_added():
    scenes, total, _ = motion.voice_scenes([{"id": "s1", "narration": "Hai dunia", "mascot": "point"}], "bm", "male",
                                           Path("/tmp/motion-test-inject"), speak=fake_speak)
    out = motion.inject_layers(GOOD, scenes, total, 1080, 1920)
    root = out.index('id="root"')
    assert out.index("<audio") > root and 'data-start="0"' in out and "data-volume" in out
    assert "sm-mouth" not in out and "mascot" not in out and "scaleY" not in out
    try:
        motion.inject_layers("<html><body>no root</body></html>", scenes, total, 1080, 1920)
    except ValueError:
        pass
    else:
        raise AssertionError("a film with no #root was accepted")


def test_the_script_prompt_speaks_the_films_language_and_both_means_two_lines():
    s = motion.build_script_system({"stream": "regulab", "seconds": 20, "language": "both"}, "Sebut nama produk.")
    assert "about 30 seconds" in s and "70 words" in s and "Bahasa Malaysia with the English line" in s
    assert "WAN'S OWN INSTRUCTIONS:\nSebut nama produk." in s and "ws.regulab" in s
    assert "English" in motion.build_script_system({"stream": "linkedin", "seconds": 8}, "")
    # an English film for ws.regulab: the brand line no longer says "speaking Bahasa Malaysia" (24 Oct 2026, Malay narration)
    en = motion.build_script_system({"stream": "regulab", "seconds": 15, "language": "en"}, "")
    assert "NARRATION LANGUAGE: English." in en and "speaking warm, plain English" in en and "speaking Bahasa Malaysia" not in en
    bm = motion.build_script_system({"stream": "linkedin", "seconds": 15, "language": "bm"}, "")
    assert "speaking Bahasa Malaysia" in bm and "speaking English" not in bm
    assert "speaking warm, plain English" in motion.build_system({"stream": "regulab", "seconds": 10, "language": "en"}, "")
    assert motion.voice_mod.voice_for("both", "female") == "ms-MY-YasminNeural"
    assert motion.voice_mod.voice_for("en", "male") == "en-US-AndrewMultilingualNeural"
    assert motion.voice_mod.voice_for("en", "en-GB-RyanNeural") == "en-GB-RyanNeural"
