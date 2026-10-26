"""motion_captions.py: each platform's caption fitted to its own limits, and the film's format following its platform."""

from test_motion import GOOD, NOW, SCRIPT, FakeLLM, Store, _no_real_voice, _row, _runner  # noqa: F401 (the autouse voice stub)

from semasa import compliance, motion, motion_captions, motion_styles

LONG = ("Senarai ketoksikan memberitahu kita apa yang berlaku. Peta AOP mula memberitahu kita bagaimana ia berlaku.\n\n"
        + "Itulah sebabnya ulasan kritikal ini menarik perhatian saya. Ia menggunakan pendekatan PRISMA-ScR. " * 12
        + "\n\n#kosmetik #npra #toksikologi")
SCENES = [{"id": "s1", "heading": "Enam kategori bahan kosmetik dikaji", "lines": ["Pengawet", "Penapis UV"],
           "narration": "Enam kategori."},
          {"id": "brand-outro", "heading": "Jangan lupa follow kami", "lines": []}]


def test_a_caption_is_fitted_to_the_platform_it_goes_to():
    """The real case of 26 Oct: one 1,553-character caption on Threads, whose limit is 500."""
    for plat, (mx, tags) in {"instagram": (2200, 8), "facebook": (63206, 3), "threads": (500, 1)}.items():
        out = motion_captions.fit(LONG, "regulab", plat)
        assert len(out) <= mx, plat
        assert len([w for w in out.split() if w.startswith("#")]) <= tags, plat
    threads = motion_captions.fit(LONG, "regulab", "threads")
    assert threads.startswith("Senarai ketoksikan") and threads.split("\n\n")[0].endswith(".")
    assert threads.endswith("#kosmetik") and len(threads) <= 500
    assert motion_captions.fit("Pendek sahaja.", "regulab", "threads") == "Pendek sahaja."
    assert len(motion_captions.fit("x" * 4000, "linkedin", "linkedin")) <= 3000


def test_the_writers_captions_are_fitted_cleaned_and_one_for_each_platform_of_the_stream():
    answer = {"captions": {"instagram": "Fakta — penting.\n\n#a #b", "facebook": "Panjang. " * 50, "threads": LONG}}
    llm = FakeLLM([answer])
    got = motion_captions.write(llm, {"stream": "regulab"}, SCENES, "PFAS", lang="bm", voice="ws.regulab",
                                speak_as=motion.speaker("bm"))
    assert set(got) == {"instagram", "facebook", "threads"}
    assert "—" not in got["instagram"], "the anti-slop edits run on every caption"
    assert len(got["threads"]) <= 500 and len(got["facebook"]) <= 63206
    system, user = llm.asked[0]
    assert "Under 420 characters" in system and "ONE tight post" in system and "Malaysian, never Indonesian" in system
    assert "Enam kategori bahan kosmetik dikaji" in user and "Jangan lupa follow kami" not in user, "the outro is not a fact"
    li = motion_captions.write(FakeLLM([{"captions": {"linkedin": "I read the instrument."}}]), {"stream": "linkedin"}, SCENES,
                               "PFAS", lang="en", voice="a named chemist", speak_as=motion.speaker("en"))
    assert list(li) == ["linkedin"] and li["linkedin"] == "I read the instrument."


def test_a_writer_that_fails_leaves_captions_built_from_the_script():
    for llm in (None, FakeLLM([]), FakeLLM([{"captions": "not an object"}])):
        got = motion_captions.write(llm, {"stream": "regulab"}, SCENES, "PFAS: enam kategori", lang="bm", voice="v",
                                    speak_as=motion.speaker("bm"))
        assert set(got) == {"instagram", "facebook", "threads"} and all(got.values())
        assert got["threads"].startswith("PFAS: enam kategori") and len(got["threads"]) <= 500
        assert "Pengawet" in got["instagram"]

    class Boom:
        def chat_json(self, *a, **k):
            raise RuntimeError("down")
    assert motion_captions.write(Boom(), {"stream": "regulab"}, SCENES, "T", lang="en", voice="v",
                                 speak_as=motion.speaker("en"))["threads"].startswith("T")


def test_every_caption_stays_inside_the_rules_the_publisher_scans_with():
    got = motion_captions.from_script("T", [{"id": "s1", "heading": "H " * 400, "lines": []}], "regulab")
    for plat, text in got.items():
        assert len(text) <= compliance.RULES["limits"]["regulab"][plat]["max"]


def test_the_film_takes_the_format_of_its_platform():
    assert motion.size_of({"stream": "regulab"}) == "portrait", "Reels and Threads are upright 9:16"
    assert motion.size_of({"stream": "linkedin"}) == "square", "the LinkedIn feed shows 1:1 best"
    assert motion.size_of({"stream": "linkedin", "resolution": "auto"}) == "square"
    assert motion.size_of({"stream": "linkedin", "resolution": "landscape"}) == "landscape", "an explicit choice stands"
    assert motion.size_of({"resolution": "nonsense"}) == "portrait"


def test_a_linkedin_film_closes_in_wans_own_voice_not_the_brands():
    assert motion_styles.cta({"stream": "linkedin", "language": "en", "seconds": 30}) == "Follow me for more info"
    assert motion_styles.cta({"stream": "linkedin", "language": "bm", "seconds": 30}) == "Ikuti saya untuk maklumat lanjut"
    teaser = {"stream": "linkedin", "language": "en", "seconds": 10, "options": {"mode": "teaser"}}
    assert motion_styles.cta(teaser) == "Stay tuned. Follow me for more info"
    assert motion_styles.cta({"stream": "regulab", "language": "en", "seconds": 30}) == "Follow us for more"


def test_process_saves_the_captions_with_the_film(tmp_path):
    for stream, keys in (("regulab", {"instagram", "facebook", "threads"}), ("linkedin", {"linkedin"})):
        store = Store()
        r = _row(store, stream=stream, resolution="")
        cap = {"captions": {k: f"Caption {k}." for k in keys}}
        llm = FakeLLM([SCRIPT, {"title": "PFAS: tiga perkara", "html": GOOD}, cap])
        assert motion.process(store, llm, {**r, "attempts": 1}, {"prompt": "", "cli": "0.8.188"}, runner=_runner(),
                              workdir=tmp_path / stream, now=NOW)
        got = store.table(motion.TABLE).select("*").eq("id", r["id"]).execute().data[0]
        assert got["status"] == "done" and set(got["captions"]) == keys
        assert "You write the caption" in llm.asked[-1][0]


def test_a_linkedin_film_shows_no_ws_regulab_name_in_a_browser_frame():
    from semasa import motion_layout
    scenes = [{"id": "s1", "role": "hook", "start": 0, "duration": 8, "kicker": "x", "heading": "Enam kategori",
               "lines": ["Pengawet"], "narration": "x"}]
    plan = {"scenes": {"s1": ["B01"]}, "video": {}}

    def built(stream):
        return motion_layout.compose(scenes=[dict(s) for s in scenes], total=8, w=1080, h=1080, lang="en", plan=plan,
                                     palette=motion.PALETTE[stream], gsap=motion.GSAP, html_lang="en", resolution="square",
                                     stream=stream)[0]
    assert "ws.regulab" in built("regulab"), "the frame names the brand on its own stream (so this test sees the frame)"
    assert "ws.regulab" not in built("linkedin")


def test_a_linkedin_film_closes_on_wans_icon_and_name_never_the_brand_logo(tmp_path):
    outro = {"id": "brand-outro", "heading": "Follow me for more info", "start": 20, "duration": 3}
    li = motion.closing_card(outro, 1080, "linkedin", "Ts. ChM Muhammad Ridzuan")
    assert "assets/wan-icon.png" in li and "Ts. ChM Muhammad Ridzuan" in li and "Follow me for more info" in li
    assert "official-logo" not in li and "ws.regulab" not in li
    assert 'id="wan-brand-final"' in li and 'data-start="20"' in li
    reg = motion.closing_card({**outro, "heading": "Follow us for more"}, 1080)
    assert "official-logo-transparent.png" in reg and "wan-icon" not in reg
    assert "Ts. ChM" in motion.closing_card(outro, 1080, "linkedin"), "no name given: the default byline"
    html = motion.inject_layers('<div id="root" data-duration="1"></div>', [outro], 23, 1080, 1080, "linkedin", "Wan")
    assert "wan-icon.png" in html and ">Wan<" in html
    motion.write_project(tmp_path / "li", "<html></html>", "linkedin")
    motion.write_project(tmp_path / "rg", "<html></html>")
    assert (tmp_path / "li" / "assets" / "wan-icon.png").stat().st_size > 1000
    assert not (tmp_path / "li" / "assets" / "official-logo-transparent.png").exists()
    assert (tmp_path / "rg" / "assets" / "official-logo-transparent.png").exists()


def test_the_byline_comes_from_the_brand_settings_with_a_default():
    store = Store()
    assert motion.byline(store) == motion.LINKEDIN_NAME
    store.tables["semasa_settings"] = [{"key": "brand", "value": {"linkedin": {"name": "Ts. ChM Muhammad"}}}]
    assert motion.byline(store) == "Ts. ChM Muhammad"


def test_the_detector_knows_sending_the_viewer_away_from_saying_the_point():
    for away in ("Check the guideline for the limit.", "Find out more on the NPRA website.", "Cari sendiri di laman NPRA.",
                 "Rujuk garis panduan untuk maklumat lanjut.", "Please visit the official portal.", "Semak sendiri ya."):
        assert motion_captions.hand_off(away), away
    for point in ("The limit is 0.5% and the label must say so.", "Semak label dahulu sebelum jual.",
                  "Under the 2026 Directive, every label carries the warning.", "Check the source before deciding.",
                  "Notifikasi bukan kelulusan produk."):
        assert not motion_captions.hand_off(point), point
    assert motion_captions.without_hand_offs("Had ialah 0.5%. Cari sendiri di laman NPRA. Label mesti jelas.\n\n#kosmetik") == \
        "Had ialah 0.5%. Label mesti jelas.\n\n#kosmetik"


def _script_with(narration, lines=("satu",)):
    return {"title": "t", "photo_query": "q", "scenes": [
        {"heading": f"Tajuk {i}", "lines": list(lines), "narration": narration if i == 2 else "Satu dua tiga."}
        for i in range(4)]}


def test_a_script_that_sends_the_viewer_away_is_asked_again_with_the_offending_words():
    away = _script_with("Had ialah 0.5%. Untuk maklumat lanjut, cari sendiri di laman NPRA.")
    good = _script_with("Had ialah 0.5%. Label mesti menyebutnya.")
    llm = FakeLLM([away, good])
    plan = motion.plan_scenes(llm, {"voice": "off", "language": "bm", "stream": "regulab"}, "", "", "")
    assert len(llm.asked) == 2 and "SENT THE VIEWER AWAY" in llm.asked[1][1] and "cari sendiri" in llm.asked[1][1]
    assert plan["scenes"][2]["narration"] == "" or "cari sendiri" not in plan["scenes"][2]["narration"]
    voiced = motion.plan_scenes(FakeLLM([good]), {"voice": "male", "language": "bm", "stream": "regulab"}, "", "", "")
    assert "Had ialah 0.5%" in voiced["scenes"][2]["narration"]


def test_a_second_plan_that_still_sends_away_is_cleaned_not_refused_and_a_failed_second_ask_keeps_the_first():
    away = _script_with("Had ialah 0.5%. Cari sendiri di laman NPRA.", lines=("Rujuk garis panduan", "Had 0.5%"))
    plan = motion.plan_scenes(FakeLLM([away, away]), {"voice": "male", "language": "bm"}, "", "", "")
    scene = plan["scenes"][2]
    assert "cari sendiri" not in scene["narration"].lower() and "Had ialah 0.5%" in scene["narration"]
    assert scene["lines"] == ["Had 0.5%"], "the line that only sends away is dropped, the one with the fact stays"
    kept = motion.plan_scenes(FakeLLM([away]), {"voice": "male", "language": "bm"}, "", "", "")      # the retry answers nothing
    assert len(kept["scenes"]) == 5


def test_the_writers_are_told_to_say_the_point():
    system = motion.build_script_system({"language": "en", "stream": "linkedin", "seconds": 30}, "")
    assert "SAY THE POINT" in system and "NEVER send the viewer away" in system and "shopkeeper" in system
    llm = FakeLLM([{"captions": {"linkedin": "Check the guideline for the limit. The limit is 0.5%."}}])
    got = motion_captions.write(llm, {"stream": "linkedin"}, SCENES, "T", lang="en", voice="v",
                                speak_as=motion.speaker("en"))
    assert got["linkedin"] == "The limit is 0.5%." and "send the reader away" in " ".join(llm.asked[0][0].split())


def test_finished_films_without_captions_are_given_them_from_their_saved_script():
    store = Store()
    script = [{"id": "s1", "heading": "Enam kategori", "lines": ["Pengawet"], "narration": "Enam kategori."},
              {"id": "brand-outro", "heading": "Ikuti saya", "lines": []}]
    bare = _row(store, status="done", script=script, title="Enam kategori", captions={}, language="bm")
    has = _row(store, status="done", script=script, captions={"threads": "Sudah ada."}, language="bm")
    queued = _row(store, status="done", script=script, captions={}, queued_post_id="p1", language="bm")
    old = _row(store, status="done", captions={}, language="bm")                  # no saved script: nothing to write from
    llm = FakeLLM([{"captions": {"instagram": "Satu.", "facebook": "Dua.", "threads": "Tiga."}}])
    assert motion.backfill_captions(store, llm) == 1
    rows = {r["id"]: r for r in store.table(motion.TABLE).select("*").execute().data}
    assert rows[bare["id"]]["captions"] == {"instagram": "Satu.", "facebook": "Dua.", "threads": "Tiga."}
    assert rows[has["id"]]["captions"] == {"threads": "Sudah ada."}, "captions already written are never overwritten"
    assert rows[queued["id"]]["captions"] == {} and rows[old["id"]]["captions"] == {}
    assert len(llm.asked) == 1
    assert motion.backfill_captions(store, llm) == 0 and len(llm.asked) == 1, "done once, not again"
    assert motion.backfill_captions(store, None) == 0
    assert motion.run(store, FakeLLM([]), now=NOW) == {"claimed": 0, "done": 0, "failed": 0}


def test_both_streams_explain_the_way_wan_does_on_linkedin():
    """Wan, 26 Oct 2026: the way LinkedIn explains (the fact first, the deciding rule named once, what it means in plain words)
    applies to the ws.regulab films too."""
    for stream, lang in (("regulab", "bm"), ("regulab", "en"), ("linkedin", "en")):
        system = motion.build_script_system({"language": lang, "stream": stream, "seconds": 30}, "")
        assert "HOW TO EXPLAIN" in system and "never a blog or a news site" in system, (stream, lang)
    row = {"language": "en", "stream": "regulab", "seconds": 10, "options": {"mode": "teaser"}}
    teaser = motion.build_script_system(row, "", 1)
    assert "HOW TO EXPLAIN" in teaser
    seen = []

    class Spy:
        def chat_json(self, system, user, **k):
            seen.append(system)
    for stream in ("regulab", "linkedin"):
        motion_captions.write(Spy(), {"stream": stream}, SCENES, "T", lang="en", voice="v", speak_as=motion.speaker("en"))
    assert all("chemist telling a friend" in " ".join(s.split()) for s in seen) and len(seen) == 2


def test_a_source_that_is_not_a_web_page_is_not_fetched(monkeypatch):
    """The 26 Oct run log: an idea from OneDrive has source_url onedrive://..., and requests answered "No connection adapters"."""
    calls = []
    monkeypatch.setattr(motion.fetch, "get", lambda url, timeout=25: calls.append(url))
    assert motion.source_words("onedrive://176A24AC!s2b#r24") == ("", "")
    assert motion.source_words("") == ("", "") and motion.source_words(None) == ("", "")
    assert calls == [], "nothing was fetched"
