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


def test_the_blur_design_is_known_so_it_is_not_swapped_for_design_one():
    assert motion_layout.BLUR_DESIGN in motion_layout.GRADIENT


def test_a_scene_with_a_picture_gets_a_blurred_backdrop_behind_a_veil_and_the_zoom_through_exit():
    html, _ = _compose("blur-photo")
    assert 'id="s1-bgb"' in html and "blur(30px)" in html and "rgba(255,255,255,0.66)" in html
    assert 'tl.fromTo("#s1-bgi"' in html and 'tl.to("#s1-bgi",{scale:1.55' in html, \
        "arrives from heavy blur, leaves by zooming through"
    assert 'tl.fromTo("#s1-wp"' in html, "an accent band sweeps across at the cut"
    assert html.index('id="s1-bgb"') < html.index('id="s1"'), "the backdrop sits behind the scene's words"


def test_design_one_is_untouched_and_a_scene_without_a_picture_gets_no_backdrop():
    html, _ = _compose("bright-editorial")
    assert "-bgb" not in html and "-bgi" not in html
    html, _ = _compose("blur-photo", photo=None)
    assert 'id="s1-bgb"' not in html
