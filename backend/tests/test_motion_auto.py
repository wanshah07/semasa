"""Every film gets the styles that suit it (Wan, 25 Oct 2026), a layout that cannot overlap, Unsplash photos and a pace
that fits how the film is heard (narrated: brisk; silent: slow enough to read)."""

import io
import json
from pathlib import Path

import pytest
from PIL import Image

from semasa import motion, motion_auto, motion_layout
from semasa.motion_styles import EFFECT_LIBRARY

ROW = {"id": "r1", "brief": "label myth vs fact in cosmetics", "language": "bm"}


def scene(i, heading, lines=(), narration="", **over):
    return {"id": f"s{i}", "role": motion_auto.ROLES[i - 1], "kicker": "", "heading": heading, "lines": list(lines),
            "narration": narration, "start": (i - 1) * 7.0, "duration": 6.8, **over}


FILM = [scene(1, "Adakah produk anda boleh dijual?", ["Ramai tidak sedar"]),
        scene(2, "Notifikasi bukan kelulusan", ["NPRA menerima notifikasi", "Syarikat kekal bertanggungjawab"]),
        scene(3, "Label salah boleh ditarik balik", ["Pengguna hilang percaya", "Stok ditarik", "Kos naik"]),
        scene(4, "Semak sebelum lancar", ["Senarai bahan", "Label dan tuntutan"])]


def test_every_one_of_the_99_effects_is_accounted_for():
    plan = motion_auto.choose(ROW, [dict(s) for s in FILM], voiced=False, lang="bm")
    ids = {e["id"] for e in EFFECT_LIBRARY["effects"]}
    assert len(ids) == plan["considered"] == 99
    handled = set(plan["assigned"]) | set(plan["native"]) | set(plan["audio"]) | set(plan["unavailable"])
    assert handled == ids, "no effect is silently dropped: each is used or named with a reason"
    assert not set(plan["assigned"]) & set(plan["unavailable"]) or all(
        plan["unavailable"][c] for c in set(plan["assigned"]) & set(plan["unavailable"]))
    assert set(motion_auto.RECIPES) <= ids and set(motion_auto.UNAVAILABLE) <= ids
    assert not set(motion_auto.RECIPES) & set(motion_auto.UNAVAILABLE), "an effect is built or refused, never both"


def test_each_scene_gets_styles_that_suit_its_role_and_words():
    plan = motion_auto.choose(ROW, [dict(s) for s in FILM], voiced=False, lang="bm")
    assert all(plan["scenes"][f"s{i}"] for i in (1, 2, 3, 4)), "every scene has at least one style"
    assert any(c.startswith("H") for c in plan["scenes"]["s1"]), "the hook gets a hook style"
    assert plan["video"]["captions"] in motion_auto.CAPTION and plan["video"]["transition"] in motion_auto.TRANSITION
    assert plan["video"]["finish"] in motion_auto.FINISH
    assert "S05" not in plan["audio"], "the silence drop is for voiced films only"
    voiced = motion_auto.choose(ROW, [dict(s) for s in FILM], voiced=True, lang="bm")
    assert "S05" in voiced["audio"] and {"S08", "S10"} <= set(voiced["audio"])
    # a style that needs a thing the film does not have is never chosen
    flat = {c for codes in plan["scenes"].values() for c in codes}
    assert "C10" not in flat and plan["video"]["captions"] != "C10", "bilingual captions need a bilingual film"
    assert not {"H03"} & flat, "a question style needs a question heading"
    both = motion_auto.choose(ROW, [dict(s) for s in FILM], voiced=True, lang="both")
    assert both["video"]["captions"] in motion_auto.CAPTION


def test_the_choice_is_stable_for_a_row_and_varies_between_rows():
    a1 = motion_auto.choose(ROW, [dict(s) for s in FILM], voiced=True, lang="bm")
    a2 = motion_auto.choose(ROW, [dict(s) for s in FILM], voiced=True, lang="bm")
    assert a1 == a2
    picks = {json.dumps(motion_auto.choose({**ROW, "id": f"row{i}"}, [dict(s) for s in FILM], voiced=True,
                                           lang="bm")["scenes"], sort_keys=True) for i in range(12)}
    assert len(picks) > 1, "twelve different films do not all look the same"


def test_a_photo_style_needs_a_photo_and_the_fact_scene_stays_words():
    scenes = [dict(s) for s in FILM]
    motion_auto.assign_photos(scenes, [{"path": f"assets/photo-{i}.jpg", "credit": f"P{i} / Unsplash"} for i in (1, 2, 3)])
    assert [bool(s.get("photo")) for s in scenes] == [True, False, True, True]
    plan = motion_auto.choose(ROW, scenes, voiced=True, lang="bm")
    assert not {"M03", "B05", "L05", "L06", "X06"} & set(plan["scenes"]["s2"]), "no photo, no photo style"
    motion_auto.assign_photos(scenes, [{"path": "assets/photo-1.jpg"}])
    assert [bool(s.get("photo")) for s in scenes] == [True, False, False, False]
    motion_auto.assign_photos(scenes, [])
    assert not any(s.get("photo") for s in scenes)


def test_the_prompt_names_each_style_and_leaves_native_headings_to_the_worker():
    plan = motion_auto.choose(ROW, [dict(s) for s in FILM], voiced=False, lang="bm")
    block = motion_auto.prompt_block(plan, [dict(s) for s in FILM])
    assert "STYLES CHOSEN FOR THIS FILM" in block and "WHOLE FILM" in block and "outrank every effect" in block
    for code in plan["native"]:
        assert f"{code} " not in block.split("WHOLE FILM")[0], "the worker animates native headings, not the writer"
    assert {r["id"] for r in motion_auto.effect_rows(plan)} == set(plan["native"])


def _compose(scenes, narrated=False, lang="bm", size=(1080, 1920)):
    plan = motion_auto.choose(ROW, scenes, voiced=narrated, lang=lang)
    return motion_layout.compose(scenes=scenes + [{"id": "brand-outro", "start": 28, "duration": 3, "heading": "x"}],
                                 total=31, w=size[0], h=size[1], lang=lang, plan=plan, palette=motion.PALETTE["regulab"],
                                 gsap=motion.GSAP, html_lang="ms", resolution="portrait")


def test_the_safe_layout_has_one_column_per_scene_and_nothing_placed_by_coordinates():
    scenes = [dict(s) for s in FILM]
    motion_auto.assign_photos(scenes, [{"path": f"assets/photo-{i}.jpg", "credit": "x"} for i in (1, 2, 3)])
    html, rep = _compose(scenes)
    assert rep["layout"] == "safe-layout" and html.startswith("<!doctype html>") and motion.GSAP in html
    assert html.count('class="clip sc"') == 4 and "kicker" not in html and ".k{" not in html, "no labels on screen"
    for sid in ("s1", "s2", "s3", "s4"):
        assert f'id="{sid}"' in html
    body = html.split('<div id="root"')[1]
    assert "<img" not in body and "mascot" not in html.lower(), "photos are backgrounds; there is no presenter"
    assert "background-image:url(assets/photo-1.jpg)" in html and "border-radius:" in html
    assert 'window.__timelines["main"] = tl' in html and "Math.random" not in html and "Date.now" not in html
    # every text block is a flow child: no heading, line or subtitle is placed by coordinates in its own style
    assert not __import__("re").search(r'<(?:h2|p)\b[^>]*position:absolute', html)


def test_a_long_heading_shrinks_and_an_impossible_column_drops_lines_never_overlaps():
    long = scene(1, "Label yang salah boleh menyebabkan tarikan produk dan denda besar kepada syarikat anda hari ini juga",
                 ["Satu baris yang agak panjang untuk menguji lipatan teks dalam ruang yang terhad sekali",
                  "Dua baris yang agak panjang untuk menguji lipatan teks dalam ruang yang terhad sekali",
                  "Tiga baris yang agak panjang untuk menguji lipatan teks dalam ruang yang terhad sekali",
                  "Empat baris yang agak panjang untuk menguji lipatan teks dalam ruang yang terhad sekali"])
    html, rep = _compose([long, *[dict(s) for s in FILM[1:]]], size=(1080, 1080))
    assert rep["dropped_lines"], "the column could not hold it at a readable size, so lines were dropped and recorded"
    sizes = __import__("re").findall(r"font-size:(\d+)px", html.split("</style>")[1])
    assert sizes and all(int(px) >= 44 for px in sizes), "never below 44px"


def test_narration_becomes_two_subtitle_chunks_in_their_own_lane():
    narration = "Notifikasi bukan kelulusan. NPRA menerima notifikasi sebelum jualan bermula dan syarikat kekal bertanggungjawab."
    sc = scene(2, "Notifikasi bukan kelulusan", narration=narration, audio="assets/voice-2.mp3", audio_s=6.0, start=7.0,
               duration=6.6, words=[[i * 0.4, i * 0.4 + 0.3, w] for i, w in enumerate(narration.split())])
    chunks = motion_layout.caption_chunks(sc)
    assert len(chunks) == 2 and " ".join(c[0] for c in chunks) == narration
    assert chunks[0][1] == 7.0 and chunks[0][2] == chunks[1][1] and chunks[1][2] == 13.6
    assert chunks[1][1] == pytest.approx(7.0 + 0.4 * 6), "the second chunk starts at the word the voice reaches"
    html, _ = _compose([dict(s) for s in FILM[:1]] + [sc, dict(FILM[2]), dict(FILM[3])], narrated=True)
    assert html.count('class="clip cap"') == 2 and "top:1498px" in html, "the subtitle lane sits below the column"
    silent, _ = _compose([dict(s) for s in FILM])
    assert 'class="clip cap"' not in silent, "a silent film reads its lines, there is nothing to subtitle"


def test_findings_that_mean_words_collide_are_told_apart_from_cosmetic_ones():
    f = [{"code": "content_overlap", "message": "a over b"}, {"code": "text_occluded", "message": "hidden"},
         {"code": "clip_missing_start", "message": "no data-start on .clip"}, {"code": "container_overflow", "message": "x"},
         {"code": "x", "message": "the heading is clipped by its box"}]
    got = [x["code"] for x in motion_layout.layout_findings(f)]
    assert got == ["content_overlap", "text_occluded", "container_overflow", "x"]


def test_a_silent_film_is_paced_for_reading_and_a_narrated_one_is_brisk():
    heavy = [scene(i, "Satu dua tiga empat lima enam tujuh", ["lapan sembilan sepuluh sebelas dua belas"]) for i in (1, 2, 3, 4)]
    assert all(motion.reading_seconds(s) >= motion.SILENT_MIN for s in heavy)
    assert motion.reading_seconds(heavy[0]) == round(13 / motion.READ_WPS + motion.READ_PAD, 2)
    scenes = [*(dict(s) for s in heavy), {"id": "brand-outro", "heading": "Follow", "lines": [], "narration": ""}]
    trimmed = motion.trim_for_reading(scenes, 30)
    assert sum(motion.reading_seconds(s) for s in trimmed[:-1]) <= 27, "lines are dropped before the pace is rushed"
    fit, total = motion.fit_scenes(trimmed, 30)
    assert total == 30 and all(s["duration"] >= motion.reading_seconds(s) for s in fit[:-1])
    assert motion.voice_mod.tempo_for("en-US-AndrewMultilingualNeural") == 1.15
    assert motion.voice_mod.tempo_for("ms-MY-OsmanNeural") == 1.25
    assert (motion.SCENE_GAP, motion.VOICE_PAD) == (0.2, 0.3)


def test_the_script_prompt_asks_for_the_flow_and_the_pace_that_matches_the_voice():
    voiced = motion.build_script_system({"stream": "regulab", "seconds": 30, "language": "bm", "voice": "male"}, "")
    assert "HOOK · FAKTA · KENAPA · SOLUSI" in voiced and "EXACTLY 4 teaching scene" in voiced and "BRISK" in voiced
    assert "70 words" in voiced and "photo_query" in voiced
    silent = motion.build_script_system({"stream": "regulab", "seconds": 30, "language": "en", "voice": "off"}, "")
    assert "HOOK · FACT · WHY · SOLUTION" in silent and "NO narrator" in silent and "READS, slowly" in silent
    assert "at most 33 words" in silent
    teaser = motion.build_script_system({"stream": "regulab", "seconds": 10, "voice": "off"}, "", 1)
    assert "EXACTLY 1 teaching scene" in teaser


def test_the_plan_is_asked_again_when_it_has_the_wrong_number_of_scenes():
    class LLM:
        def __init__(self, answers):
            self.answers, self.asked = answers, []

        def chat_json(self, system, user, **kw):
            self.asked.append(user)
            return self.answers.pop(0)
    one = {"title": "t", "scenes": [{"heading": "h", "narration": "n"}]}
    four = {"title": "t", "photo_query": "  science lab ",
            "scenes": [{"heading": f"h{i}", "narration": "n"} for i in range(4)]}
    llm = LLM([one, four])
    plan = motion.plan_scenes(llm, {"voice": "male", "language": "en"}, "", "", "")
    assert len(llm.asked) == 2 and "YOUR LAST PLAN HAD 1 SCENES" in llm.asked[1]
    assert [s["kicker"] for s in plan["scenes"]] == ["HOOK", "FACT", "WHY", "SOLUTION", ""]
    assert plan["photo_query"] == "science lab" and plan["scenes"][-1]["id"] == "brand-outro"
    assert not any("mascot" in s for s in plan["scenes"]), "no presenter in the plan"
    silent = motion.plan_scenes(LLM([four]), {"voice": "off", "language": "bm"}, "", "", "")
    assert all(s["narration"] == "" for s in silent["scenes"][:4]) and silent["scenes"][3]["kicker"] == "SOLUSI"


def _jpeg(size=(2400, 1600)):
    buf = io.BytesIO()
    Image.new("RGB", size, (90, 140, 120)).save(buf, "JPEG")
    return buf.getvalue()


def test_photos_come_from_unsplash_resized_credited_and_a_failure_never_stops_the_film(tmp_path):
    results = [{"id": f"p{i}", "name": f"Aina {i}", "page": f"https://unsplash.com/photos/p{i}", "alt": "lab"} for i in range(5)]
    asked = []
    photos, note = motion.fetch_photos("science lab", tmp_path, search=lambda q, o: asked.append((q, o)) or list(results),
                                       get=lambda p: _jpeg())
    assert asked == [("science lab", "landscape")] and len(photos) == 3 and note.startswith("photos: 3 from Unsplash")
    assert photos[0] == {"path": "assets/photo-1.jpg", "id": "p0", "credit": "Aina 0 / Unsplash",
                         "page": "https://unsplash.com/photos/p0", "alt": "lab"}
    with Image.open(tmp_path / "assets" / "photo-3.jpg") as im:
        assert max(im.size) == 1600 and im.format == "JPEG"
    none, note = motion.fetch_photos("zzz qqq", tmp_path / "b", search=lambda q, o: [], get=None)
    assert none == [] and "found nothing" in note

    def boom(q, o):
        raise RuntimeError("UNSPLASH_ACCESS_KEY is not set")
    none, note = motion.fetch_photos("x", tmp_path / "c", search=boom)
    assert none == [] and "photos not fetched: UNSPLASH_ACCESS_KEY is not set" in note
    assert motion.fetch_photos("", tmp_path / "d", search=lambda q, o: results)[0] == [], "no search words, no photos"


def test_the_silence_drop_ducks_the_music_before_the_solusi_scene(tmp_path):
    seen = []

    def runner(cmd, **kw):
        seen.append(cmd)
        Path(cmd[-1]).write_bytes(b"x")
        return type("R", (), {"returncode": 0, "stderr": ""})()
    video = tmp_path / "renders" / "motion.mp4"
    video.parent.mkdir()
    video.write_bytes(b"v")
    voiced = [{"id": "s1", "start": 0.0, "audio": "assets/a.mp3", "audio_s": 3.0}]
    motion.mix_music(video, voiced, 30, runner, (20.4, 21.0))
    assert "*if(between(t,20.4,21),0.15,1)" in seen[-1][seen[-1].index("-filter_complex") + 1]
    motion.mix_music(video, voiced, 30, runner)
    assert "between(t,20.4" not in seen[-1][seen[-1].index("-filter_complex") + 1]


def test_narration_that_does_not_fit_is_cut_and_recorded_again_never_rushed_never_failed(tmp_path, monkeypatch):
    from test_motion import GOOD, NOW, FakeLLM, Store, _row, _runner, fake_speak
    monkeypatch.setattr(motion.voice_mod, "speak", fake_speak)
    sentences = " ".join(f"Satu dua tiga empat lima{i}." for i in range(4))          # 20 words = 8 s a scene
    plan = {"title": "t", "photo_query": "lab", "scenes": [{"heading": f"Tajuk {i}", "lines": [], "narration": sentences}
                                                          for i in range(4)]}
    store = Store()
    row = _row(store, language="bm", voice="male")
    assert motion.process(store, FakeLLM([plan, {"html": GOOD}]), {**row, "attempts": 1}, {"prompt": "", "cli": "0.8.188"},
                          runner=_runner(), workdir=tmp_path, now=NOW)
    got = store.table(motion.TABLE).select("*").eq("id", row["id"]).execute().data[0]
    assert got["status"] == "done"
    spoken = [sc["narration"] for sc in got["script"][:4]]
    assert all(spoken) and sum(sc.count(".") for sc in spoken) < 16, "sentences were dropped, no scene emptied"


def test_shorten_narration_drops_a_sentence_then_a_quarter_of_the_words():
    plan = [{"id": "s1", "narration": "Satu dua. Tiga empat."}, {"id": "s2", "narration": "a b c d e f g h"}]
    timed = [{"id": "s1", "audio": "x", "audio_s": 5.0}, {"id": "s2", "audio": "y", "audio_s": 3.0}]
    assert motion.shorten_narration(plan, timed) and plan[0]["narration"] == "Satu dua."
    timed[0]["audio_s"] = 1.0
    assert motion.shorten_narration(plan, timed) and plan[1]["narration"] == "a b c d e f."
    assert not motion.shorten_narration(plan, [{"id": "s1"}]), "nothing recorded, nothing to cut"


def test_a_silent_film_may_be_read_a_quarter_faster_but_no_more_and_the_error_names_the_numbers():
    def quiet(n):
        return [{"id": f"s{i}", "kicker": "", "heading": "satu dua tiga empat lima enam tujuh", "lines": ["a b c d e f"]}
                for i in range(n)] + [{"id": "brand-outro", "heading": "Follow", "lines": [], "narration": ""}]
    fit, total = motion.fit_scenes(quiet(3), 30)       # 3 x 10.29 s = 30.9 s needed, 27 available: read 13% faster
    assert total == 30 and fit[0]["duration"] < motion.reading_seconds(fit[0])
    with pytest.raises(ValueError, match=r"needs \d+\.\ds, has 27\.0s"):
        motion.fit_scenes(quiet(4), 30)               # 41 s of reading in 27 s is not "a quarter faster"


PAGE = """<!doctype html><html><head><style>
html,body{margin:0;width:1080px;height:1920px}#root{position:absolute;inset:0}
.clip{position:absolute;left:0;top:0;width:1080px;height:1920px}
h2,p{margin:0;position:absolute;left:100px;font:60px/1.1 sans-serif}
.ph{position:absolute;left:100px;width:400px;height:300px;background-image:url(data:image/gif;base64,R0lGODlhAQABAAAAACw=)}
</style></head><body><div id="root" data-composition-id="main" data-start="0" data-duration="6">
%s
</div><script>window.__timelines={main:{seek(){},pause(){}}};</script></body></html>"""


def _probe(tmp_path, body):
    pytest.importorskip("playwright")
    from semasa import motion_probe
    if not motion_probe.chrome_path():
        pytest.skip("no Chrome here")
    (tmp_path / "index.html").write_text(PAGE % body)
    return motion_probe.overlaps(tmp_path, 1080, 1920, 6)


def test_the_overlap_probe_flags_text_on_text_text_on_a_photo_and_text_off_the_frame(tmp_path):
    clip = '<div class="clip" data-start="0" data-duration="6">%s</div>'
    clean = clip % '<h2 style="top:200px">Title</h2><p style="top:400px">Line</p>'
    assert _probe(tmp_path, clean) == []
    stacked = clip % '<h2 style="top:200px">Title here</h2><p style="top:215px">Line over it</p>'
    assert {f["code"] for f in _probe(tmp_path, stacked)} == {"text_overlap"}
    on_photo = clip % '<div class="ph" style="top:200px"></div><h2 style="top:300px">Hi</h2>'
    assert {f["code"] for f in _probe(tmp_path, on_photo)} == {"text_on_photo"}
    off = clip % '<h2 style="top:200px;left:900px;white-space:nowrap">Too far right</h2>'
    assert "text_off_frame" in {f["code"] for f in _probe(tmp_path, off)}
    # two scenes that never share a moment may share a place
    apart = ('<div class="clip" data-start="0" data-duration="3"><h2 style="top:200px">One</h2></div>'
             '<div class="clip" data-start="3" data-duration="3"><h2 style="top:200px">Two</h2></div>')
    assert _probe(tmp_path, apart) == []


def test_a_probe_finding_counts_as_a_layout_finding_and_an_unavailable_probe_does_not_fail_a_film():
    f = [{"code": "text_on_photo", "message": "x"}, {"code": "text_overlap", "message": "y"},
         {"code": "text_off_frame", "message": "z"}]
    assert len(motion_layout.layout_findings(f)) == 3
    unavailable = [{"code": "probe_unavailable", "message": "no Chrome found for the overlap test"}]
    assert motion_layout.layout_findings(unavailable) == []


def test_a_writer_that_answers_nothing_still_ends_in_the_safe_layout_film(tmp_path, monkeypatch):
    # run 37 (26 Oct 2026): the writer's JSON was unparsable twice, chat_json gave None and the fallback crashed on it
    from test_motion import NOW, FakeLLM, Store, _row, _runner, fake_speak
    monkeypatch.setattr(motion.voice_mod, "speak", fake_speak)
    store = Store()
    row = _row(store, language="bm", voice="male")
    plan = {"title": "t", "photo_query": "lab", "scenes": [{"heading": f"Tajuk {i}", "lines": [], "narration": "Satu dua tiga."}
                                                          for i in range(4)]}
    assert motion.process(store, FakeLLM([plan, None, None]), {**row, "attempts": 1}, {"prompt": "", "cli": "0.8.188"},
                          runner=_runner(), workdir=tmp_path, now=NOW)
    got = store.table(motion.TABLE).select("*").eq("id", row["id"]).execute().data[0]
    assert got["status"] == "done" and "safe layout used" in got["style_note"]


def test_wans_ws_regulab_motion_skill_is_installed_for_claude_code_and_reaches_the_writer():
    skill = motion.SKILL
    assert (skill / "SKILL.md").is_file(), "a Claude Code project skill: .claude/skills/<name>/SKILL.md"
    head = (skill / "SKILL.md").read_text().split("---")[1]
    assert "name: ws-regulab-motion" in head and "user-invocable: true" in head
    for rel in ("references/contract.md", "references/catalog.json", "templates/BrightPhotoDiagramEditorial.html",
                "templates/ContinuousLine.html", "assets/official-logo-transparent.png", "scripts/resolve.py"):
        assert (skill / rel).is_file(), rel
    one = motion.skill_context({"options": {"design": "bright-editorial"}})
    assert "Production contract" in one and "BrightPhotoDiagramEditorial.html" in one and "ContinuousLine.html" not in one
    two = motion.skill_context({"options": {"design": "continuous-line"}})
    assert "ContinuousLine.html" in two and "those win" in two
    assert "WAN'S SKILL ws-regulab-motion" in motion.build_user({"brief": "b"}, "", "")


def test_the_writer_may_answer_with_plain_html_a_fenced_file_or_the_old_json():
    from test_motion import GOOD
    plain = "<!-- title: Notifikasi bukan kelulusan -->\n" + GOOD + "\nThat is all."
    got = motion.parse_writer(plain)
    assert got["title"] == "Notifikasi bukan kelulusan"
    assert got["html"].startswith("<!doctype") and got["html"].endswith("</html>")
    fenced = motion.parse_writer("```html\n" + GOOD + "\n```")
    assert fenced["html"] == GOOD and fenced["title"] == ""
    old = motion.parse_writer('{"title": "T", "html": ' + __import__("json").dumps(GOOD) + "}")
    assert old["title"] == "T" and old["html"] == GOOD
    assert motion.parse_writer("sorry, I cannot") == {} and motion.parse_writer(None) == {}
    assert motion.clean_html(plain and got["html"]) == GOOD


def test_ask_writer_prefers_plain_text_and_falls_back_to_json():
    from test_motion import GOOD

    class TextLLM:
        def chat_text(self, system, user, *, max_tokens):
            return "<!-- title: X -->" + GOOD

    class JsonLLM:
        def chat_json(self, system, user, *, max_tokens):
            return {"title": "J", "html": GOOD}

    class Silent:
        def chat_text(self, system, user, *, max_tokens):
            return None
    assert motion.ask_writer(TextLLM(), "s", "u")["title"] == "X"
    assert motion.ask_writer(JsonLLM(), "s", "u")["title"] == "J"
    assert motion.ask_writer(Silent(), "s", "u") is None


def test_llm_chat_text_asks_each_writer_once_and_returns_the_first_real_answer(monkeypatch):
    from types import SimpleNamespace

    import requests

    from semasa import llm as llm_mod
    bot = llm_mod.LLM.__new__(llm_mod.LLM)
    bot.s = SimpleNamespace(timeout=5)
    bot.calls, bot.failures, bot.last_model = 0, 0, ""
    bot.answers, bot.misses = {"primary": 0, "backup": 0}, {"primary": 0, "backup": 0}
    bot._writers = lambda model, backup: [("primary", "openai", "b1", "k", "m1"), ("backup", "openai", "b2", "k", "m2")]
    replies = iter([requests.Timeout("slow"), "<html>ok</html>"])

    def call(system, user, max_tokens, model, **kw):
        r = next(replies)
        if isinstance(r, Exception):
            raise r
        return r
    bot._call = call
    assert bot.chat_text("s", "u", max_tokens=10) == "<html>ok</html>"
    assert bot.last_model == "m2" and bot.misses["primary"] == 1 and bot.answers["backup"] == 1
    bot._call = lambda *a, **k: ""
    assert bot.chat_text("s", "u", max_tokens=10) is None and bot.failures == 1


def test_a_native_heading_effect_leaves_the_heading_on_screen_after_its_entrance():
    from semasa import native_text
    doc = '<html><body><div id="root"><div id="s1"><h2>Keep food safe</h2></div></div></body></html>'
    scenes = [{"id": "s1", "heading": "Keep food safe", "start": 0, "duration": 6}]
    report = {"effects": [{"id": "H01"}]}
    out = native_text.inject(doc, report, scenes, 30)
    assert "native-H01" in out and "opacity:0,duration:.18" not in out


def test_the_safe_layout_background_is_the_reference_gradient_and_never_a_circle():
    html, _ = _compose([dict(s) for s in FILM])
    assert "linear-gradient(145deg,#dff0c2,#fbf7da 70%)" in html and 'id="grad2"' in html
    assert 'id="grid-all"' in html, "the line grid is behind every scene"
    assert 'class="bg"' not in html and 'id="bg' not in html and ".bg{" not in html, "no circles behind the text"
    line, _ = motion_layout.compose(scenes=[dict(s) for s in FILM], total=31, w=1080, h=1920, lang="bm",
                                    plan={"scenes": {}, "video": {}}, palette=motion.PALETTE["regulab"], gsap=motion.GSAP,
                                    html_lang="ms", resolution="portrait", design="continuous-line")
    assert "linear-gradient(150deg,#e2f0c6,#fbf8de)" in line


@pytest.mark.parametrize("voiced", [True, False])
@pytest.mark.parametrize("photos", [0, 1, 3])
@pytest.mark.parametrize("lang", ["bm", "en", "both"])
@pytest.mark.parametrize("lines", [0, 2])
def test_every_film_gets_at_least_fifteen_of_the_99_styles(voiced, photos, lang, lines):
    # Wan, 26 Oct 2026: "make sure at least 15 styles from 99 styles apply to the motion video"
    film = [scene(1, "Is it approved?", ["a b"] * lines), scene(2, "Notification is not approval", ["x y", "z w"][:lines]),
            scene(3, "A wrong label means recall", ["one"] * lines),
            scene(4, "Check before launch", ["list a", "list b"][:lines])]
    motion_auto.assign_photos(film, [{"path": f"p{i}.jpg"} for i in range(photos)])
    plan = motion_auto.choose(ROW, film, voiced=voiced, lang=lang)
    assert plan["applied"] >= motion_auto.MIN_STYLES == 15
    seen = {c for codes in plan["scenes"].values() for c in codes} | set(plan["video"].values()) | set(plan["audio"])
    assert len(seen) == plan["applied"], "the count is the styles actually assigned, none twice"


@pytest.mark.parametrize("row, key", [
    ({"seconds": 10, "options": {"mode": "teaser"}, "language": "bm"}, "gimmick"),
    ({"options": {"design": "continuous-line"}, "language": "en"}, "preview"),
    ({"language": "bm"}, "malay"), ({"language": "both"}, "malay"), ({"language": "en"}, "english"),
])
def test_each_film_is_one_of_wans_four_formats_and_the_writer_gets_that_formats_skill(row, key):
    assert motion.format_of(row) == key
    skill = motion.SKILL.parent / f"ws-regulab-motion-{key}"
    assert (skill / "SKILL.md").is_file() and (skill / "reference" / "reference.mp4").is_file()
    assert (skill / "reference" / "contact-sheet.jpg").is_file()
    head = (skill / "SKILL.md").read_text().split("---")[1]
    assert f"name: ws-regulab-motion-{key}" in head and "user-invocable: true" in head
    context = motion.format_context(row)
    assert f"FORMAT SKILL ws-regulab-motion-{key}" in context and "NEVER circles" in context and "15 of the 99" in context
    assert "FORMAT SKILL" in motion.build_user({"brief": "b", **row}, "", "")


def test_the_worker_leaves_a_waiting_row_alone_until_wan_starts_it():
    # the queue (Wan, 26 Oct 2026): an idea made into a video waits for its styles; only 'pending' is claimed
    from test_motion import Store, _row
    store = Store()
    waiting = _row(store, status="waiting")
    pending = _row(store, status="pending")
    claimed = [r["id"] for r in motion.claim(store)]
    assert claimed == [pending["id"]]
    assert store.table(motion.TABLE).select("*").eq("id", waiting["id"]).execute().data[0]["status"] == "waiting"


RICH_PLAN = {"scenes": {"s1": ["H05", "L06", "M07", "B05"], "s2": ["V05", "V02", "X10"], "s3": ["B04", "X06", "B08"],
                        "s4": ["V06", "M04", "V10", "H06"]},
             "video": {"captions": "C07", "transition": "M09", "finish": "F02"}}


def _rich(scenes, plan=None, size=(1080, 1920)):
    return motion_layout.compose(scenes=scenes + [{"id": "brand-outro", "start": 28, "duration": 3, "heading": "x"}],
                                 total=31, w=size[0], h=size[1], lang="bm", plan=plan or RICH_PLAN,
                                 palette=motion.PALETTE["regulab"], gsap=motion.GSAP, html_lang="ms", resolution="portrait")


def test_the_safe_layout_builds_the_styles_the_film_was_given_not_just_the_plain_column():
    scenes = [dict(s) for s in FILM]
    motion_auto.assign_photos(scenes, [{"path": f"assets/photo-{i}.jpg", "credit": "x"} for i in (1, 2, 3)])
    scenes[1]["lines"] = ["Syarikat kekal peduli 100% keselamatan", "Label dan tuntutan mesti patuh"]
    html, rep = _rich(scenes)
    assert rep["not_built"] == [], "every style in the plan has a builder"
    wanted = {"H05", "H06", "L06", "M04", "M07", "V02", "V05", "V06", "V10", "B04", "B05", "B08", "X06", "X10", "C07"}
    assert wanted <= set(rep["built"])
    for marker in ('id="s1-cd"', 'id="s4-pa"', 'class="k7"', 'class="trk"', 'class="bd s3-bd"', 'class="gridx"',
                   'class="ln s3-ln"', 'class="cards"', 'class="tl s3-t"', 'class="mut"'):
        assert marker in html, marker
    assert "border-radius:50%" not in html.split('<div id="root"')[1], "no circle is drawn behind anything"


def test_option_cards_stand_down_when_a_word_would_break_in_half():
    scenes = [dict(s) for s in FILM]
    scenes[1]["lines"] = ["Bertanggungjawabkeseluruhannya sepenuhnya", "Label dan tuntutan"]
    html, _ = _rich(scenes)
    assert 'class="cards"' not in html.split('<div id="root"')[1]


def test_the_chooser_prefers_styles_the_worker_can_build():
    assert motion_auto.BUILDABLE <= set(motion_auto.RECIPES)
    plan = motion_auto.choose(ROW, [dict(s) for s in FILM], voiced=True, lang="bm")
    shown = set(plan["assigned"]) - motion_layout.BUILT
    assert len(shown) <= 3, f"almost everything chosen should be buildable, not {sorted(shown)}"


def test_the_rich_layout_has_no_overlap_in_a_real_browser(tmp_path):
    from semasa import motion_probe
    if not motion_probe.chrome_path():
        pytest.skip("no Chrome here")
    import shutil
    scenes = [dict(s) for s in FILM]
    for i, sc in enumerate(scenes):
        sc["start"], sc["duration"] = 7.0 * i, 7.0
    motion_auto.assign_photos(scenes, [{"path": "p.jpg", "credit": "x"} for _ in range(3)])
    html, _ = _rich(scenes)
    (tmp_path / "index.html").write_text(html)
    from PIL import Image
    Image.new("RGB", (60, 60), "#234").save(tmp_path / "p.jpg")
    try:
        found = motion_probe.overlaps(tmp_path, 1080, 1920, 31)
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)
    real = [f for f in found if f["code"] != "probe_unavailable"]
    assert not real, real


@pytest.mark.composed
def test_by_default_the_worker_composes_the_film_and_the_writer_is_not_asked(tmp_path, monkeypatch):
    # 26 Oct 2026: the writer's own layouts failed content_overlap on every try; the film is built by motion_layout
    from test_motion import NOW, FakeLLM, Store, _row, _runner, fake_speak
    monkeypatch.setattr(motion.voice_mod, "speak", fake_speak)
    store = Store()
    row = _row(store, language="bm", voice="male")
    plan = {"title": "t", "photo_query": "lab", "scenes": [
        {"heading": f"Tajuk {i}", "lines": ["Denda 50% kes", "Sejak 2018 dan 2026 syarat baharu"],
         "narration": "Satu dua tiga empat lima enam."} for i in range(4)]}
    llm = FakeLLM([plan])
    assert motion.process(store, llm, {**row, "attempts": 1}, {"prompt": "", "cli": "0.8.188"},
                          runner=_runner(), workdir=tmp_path, now=NOW)
    got = store.table(motion.TABLE).select("*").eq("id", row["id"]).execute().data[0]
    assert got["status"] == "done" and "composed by the worker" in got["style_note"]
    assert "writer_attempts" not in got["check_report"], "no writer layout was asked for or rejected"
    built = got["check_report"]["layout"]["built"]
    assert len(built) >= 8 and {"V09", "P08", "P03", "V02"} & set(built), built


def test_markup_in_the_script_is_words_only_on_the_film_and_in_the_voice():
    # the paper film (26 Oct 2026) drew '<br><span class="accent">' as letters, and the narration would have been read aloud
    assert motion_layout.plain('Six groups.<br><span class="accent">One safety map?</span>') == "Six groups. One safety map?"
    assert motion_layout.plain("R&amp;D <b>fast</b>  ok") == "R&D fast ok"
    scenes = [{"id": "s1", "role": "hook", "start": 0, "duration": 6,
               "heading": 'Mechanism<br><span class="accent">matters</span>', "lines": ["<i>one</i> line"]}]
    outro = {"id": "brand-outro", "start": 6, "duration": 3, "heading": "x"}
    html, _ = motion_layout.compose(scenes=scenes + [outro], total=9, w=1080, h=1920, lang="en",
                                    plan={"scenes": {}, "video": {}}, palette=motion.PALETTE["regulab"],
                                    gsap=motion.GSAP, html_lang="en", resolution="portrait")
    body = html.split('<div id="root"')[1]
    assert "&lt;" not in body and "<br>" not in body and "Mechanism matters" in body and "one line" in body


def test_no_flash_darkens_the_film_before_its_moment():
    # the paper film (26 Oct 2026) was a darker teal until its M04 scene: a fromTo applies its start value at once
    html, _ = _rich([dict(s) for s in FILM], plan={"scenes": {"s2": ["M04"]}, "video": {}})
    assert 'tl.fromTo("#flash",{opacity:.35},{opacity:0,duration:.4,ease:"power2.out",immediateRender:false}' in html


def _kinds_film(codes, lines=("Syarikat kekal peduli", "Label dan tuntutan patuh", "Semak sebelum lancar")):
    scenes = [{"id": f"s{i + 1}", "role": "fact", "start": i * 5, "duration": 5, "heading": "Notifikasi bukan kelulusan",
               "lines": list(lines)} for i in range(len(codes))]
    plan = {"scenes": {f"s{i + 1}": [c] for i, c in enumerate(codes)}, "video": {}, "evidence_url": "https://pubmed.ncbi.nlm.nih.gov/42919945/"}
    outro = {"id": "brand-outro", "start": len(codes) * 5, "duration": 3, "heading": "x"}
    return motion_layout.compose(scenes=scenes + [outro], total=len(codes) * 5 + 3, w=1080, h=1920, lang="bm", plan=plan,
                                 palette=motion.PALETTE["regulab"], gsap=motion.GSAP, html_lang="ms", resolution="portrait")


def test_styles_that_need_footage_are_drawn_as_concept_diagrams_and_say_so():
    # Wan, 26 Oct 2026: "use style that identify as concept fallback"
    codes = ["B01", "L04", "P04", "P05", "L07", "P01", "B07", "X08", "X02", "L10", "X05", "P07"]
    html, rep = _kinds_film(codes)
    assert set(rep["concept"]) == set(codes), (rep["concept"], rep["not_built"])
    assert "pubmed.ncbi.nlm.nih.gov" in html, "the browser frame shows the source's own host, nothing invented"
    body = html.split('<div id="root"')[1]
    assert "border-radius:50%" not in body
    assert all(c in motion_auto.CONCEPT for c in rep["concept"])


def test_a_concept_diagram_is_not_drawn_when_a_word_would_be_split_in_half():
    html, rep = _kinds_film(["P04", "B07", "L07"], lines=("Bertanggungjawabkeseluruhannya sepenuhnya", "Label tuntutan", "Semak"))
    assert rep["concept"] == [] and sorted(rep["not_built"]) == ["B07", "L07", "P04"]


def test_the_chooser_uses_wow_and_concept_styles_and_none_is_skipped_for_lack_of_footage():
    plan = motion_auto.choose(ROW, [dict(s) for s in FILM], voiced=True, lang="bm")
    assert plan["concept"], "a film includes concept renditions"
    assert not any("footage" in why or "capture" in why for why in plan["unavailable"].values())
    assert motion_auto.WOW & {c for codes in plan["scenes"].values() for c in codes}


def test_karaoke_captions_turn_each_word_dark_as_the_voice_reaches_it():
    narration = "Notifikasi bukan kelulusan produk dan syarikat kekal bertanggungjawab sepenuhnya"
    words = narration.split()
    sc = {"id": "s1", "role": "hook", "start": 0, "duration": 8, "heading": "Notifikasi", "lines": [], "narration": narration,
          "audio": "a.mp3", "audio_s": 6, "words": [[i * 0.5, i * 0.5 + 0.4, w] for i, w in enumerate(words)]}
    plan = {"scenes": {"s1": ["C01"]}, "video": {}}
    html, rep = motion_layout.compose(scenes=[sc, {"id": "brand-outro", "start": 8, "duration": 3, "heading": "x"}], total=11,
                                      w=1080, h=1920, lang="bm", plan=plan, palette=motion.PALETTE["regulab"], gsap=motion.GSAP,
                                      html_lang="ms", resolution="portrait")
    assert "C01" in rep["built"] and html.count('class="kk"') == len(words)
    assert 'tl.fromTo("#s1-kk2",{opacity:.4},{opacity:1,duration:.08},1;' in html.replace("1);", "1;")
