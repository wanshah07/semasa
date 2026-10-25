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
    assert motion.voice_mod.rate_for("en-US-AndrewMultilingualNeural") == "+15%"
    assert motion.voice_mod.rate_for("ms-MY-OsmanNeural") == "+25%"
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
