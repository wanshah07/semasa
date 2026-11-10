"""The follow line is said once, with the logo (Wan, 10 Nov 2026: "jangan lupa follow kami untuk tips seterusnya jangan ulang,
hanya appear bersama dengan logo saja")."""

from semasa import motion, motion_captions


def test_a_follow_invitation_is_recognised_and_a_guideline_to_follow_is_not():
    for line in ("Jangan lupa follow kami untuk tip seterusnya.", "Ikuti kami untuk tip macam ni.", "Follow us for more.",
                 "Follow for more like this", "Ikuti saya untuk maklumat lanjut", "Jangan lupa ikuti kami"):
        assert motion_captions.follow_ask(line), line
    for line in ("Ikuti garis panduan NPRA.", "Peraturan ini perlu diikuti.", "Pastikan mereka faham anatomi mata."):
        assert not motion_captions.follow_ask(line), line


def test_only_the_invitation_sentence_is_taken_out_of_a_scene():
    said = "Tanya pengamal sama ada kawasan itu selamat. Jangan lupa follow kami untuk tip seterusnya."
    assert motion_captions.without_follow_asks(said) == "Tanya pengamal sama ada kawasan itu selamat."
    assert motion.no_follow(said) == "Tanya pengamal sama ada kawasan itu selamat."
    assert motion.no_follow(said, teaser=True) == said, "the 10 s teaser carries its own exact call to action"
    assert motion_captions.without_follow_asks("Cerita.\n#hashtag") == "Cerita.\n#hashtag"


def test_the_closing_card_keeps_its_line_and_the_prompt_forbids_it_elsewhere():
    assert motion.motion_styles.cta({"stream": "regulab", "language": "bm"}) == "Jangan lupa follow kami untuk tip seterusnya"
    assert motion.motion_styles.cta({"stream": "linkedin", "language": "en"}) == "Follow me for more info"
    assert "never write 'follow'" in motion.STRUCTURE_RULE
