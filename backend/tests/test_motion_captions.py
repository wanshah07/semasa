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
    assert motion_styles.cta({"stream": "linkedin", "language": "en", "seconds": 30}) == "Follow me for more"
    assert motion_styles.cta({"stream": "linkedin", "language": "bm", "seconds": 30}) == "Ikuti saya untuk tip seterusnya"
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
