"""Design 3, the blurred photo (Wan, 10 Nov 2026: "another design with image background but blurry so the text visible and easy to
read, make the transition more wow"): each scene's own picture, blurred, under a pale veil; the words stay dark and readable."""

from semasa import motion, motion_layout

PAL = motion.PALETTE["regulab"]


def _compose(design, photo="https://example.test/p.jpg"):
    scenes = [{"id": "s1", "role": "hook", "kicker": "", "heading": "Notifikasi bukan kelulusan", "lines": ["satu", "dua"],
               "narration": "", "start": 0, "duration": 6.8, "photo": photo},
              {"id": "brand-outro", "start": 7, "duration": 3, "heading": "x"}]
    return motion_layout.compose(scenes=scenes, plan={"scenes": {"s1": []}, "video": {}}, total=10, w=1080, h=1920, lang="bm",
                                 palette=PAL, gsap=motion.GSAP, html_lang="ms", resolution="portrait", stream="regulab",
                                 design=design)


def test_both_blur_designs_are_known_so_neither_is_swapped_for_design_one():
    for d in ("blur-photo", "blur-full"):
        assert d in motion_layout.GRADIENT and d in motion_layout.BLUR_LOOKS


def test_design_3_keeps_the_sharp_picture_over_its_blurred_backdrop_and_the_zoom_through_exit():
    look = motion_layout.BLUR_LOOKS["blur-photo"]
    html, _ = _compose("blur-photo")
    assert 'id="s1-bgb"' in html and f"blur({look['blur']}px)" in html and f"rgba(255,255,255,{look['veil']})" in html
    assert 'id="s1-photo"' in html, "Design 3 is saved as it was: the sharp picture is still on the slide"
    assert 'tl.fromTo("#s1-bgi"' in html and 'tl.to("#s1-bgi",{scale:1.55' in html, \
        "arrives from heavy blur, leaves by zooming through"
    assert 'tl.fromTo("#s1-wp"' in html, "an accent band sweeps across at the cut"
    assert html.index('id="s1-bgb"') < html.index('id="s1"'), "the backdrop sits behind the scene's words"


def test_design_4_is_only_the_fully_blurred_background_with_no_sharp_copy_on_the_slide():
    """Wan, 10 Nov 2026: "the background make images full blurry ... this design as design 4"."""
    look = motion_layout.BLUR_LOOKS["blur-full"]
    assert look["blur"] > motion_layout.BLUR_LOOKS["blur-photo"]["blur"] and look["veil"] < 0.66 and not look["sharp"]
    html, _ = _compose("blur-full")
    assert 'id="s1-bgi"' in html and f"blur({look['blur']}px)" in html and 'id="s1-photo"' not in html
    sharp, _ = _compose("bright-editorial")
    assert 'id="s1-photo"' in sharp, "Design 1 still shows its picture"


def test_design_one_is_untouched_and_a_scene_without_a_picture_gets_no_backdrop():
    html, _ = _compose("bright-editorial")
    assert "-bgb" not in html and "-bgi" not in html
    html, _ = _compose("blur-photo", photo=None)
    assert 'id="s1-bgb"' not in html


def test_the_backdrop_is_marked_decorative_so_the_overlap_probe_does_not_read_it_as_a_photo_under_the_words():
    """The first real Design 3 film failed on the worker: motion_probe counted the blurred backdrop (a background-image) as a
    photo frame and every word of scene 1 as text on it ("text overlap remains even in the safe layout")."""
    from semasa import motion_probe
    html, _ = _compose("blur-photo")
    for d in ("blur-photo", "blur-full"):
        assert 'id="s1-bgb" data-backdrop="1"' in _compose(d)[0]
    assert "closest('[data-backdrop]')" in motion_probe.JS

