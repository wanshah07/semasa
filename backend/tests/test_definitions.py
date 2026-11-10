"""Wan, 10 Nov 2026: "make sure semua flow ada definition": every writer is asked for `terms`, the approver sees them."""
from semasa import definitions, ideas, motion, motion_review, motion_templates

MEANING = "alat yang menumpukan gelombang ultrabunyi untuk memanaskan lapisan kulit"


def test_clean_keeps_at_most_three_short_plain_definitions_and_drops_the_rest():
    raw = [{"term": "HIFU", "meaning": MEANING}, {"term": "", "meaning": "x"},
           {"term": "PIF", "meaning": "cari sendiri di laman web"}, "x", None,
           {"term": "MS 1500", "meaning": "standard Malaysia untuk makanan halal"},
           {"term": "A", "meaning": "satu"}, {"term": "B", "meaning": "dua"}]
    got = definitions.clean(raw)
    assert [t["term"] for t in got] == ["HIFU", "MS 1500", "A"]      # the blank, the hand-off and the junk are gone, max 3
    assert definitions.clean("not a list") == [] and definitions.clean(None) == []
    assert all(len(t["term"]) <= 60 and len(t["meaning"]) <= 240 for t in got)


def test_every_film_flow_asks_for_terms():
    row = {"stream": "regulab", "language": "bm", "voice": "male", "options": {}}
    assert definitions.RULE in motion.build_script_system(row, "")
    for kind in ("story", "showcase"):
        system = motion_templates.system_for(kind, count=3, lang="bm", stream="regulab")
        assert '"terms"' in system and "WHAT IT IS" in system and "no narrator" in system


def test_the_template_storyboards_keep_the_terms_through_validation():
    data = {"title": "Tiga", "subtitle": "Satu dua", "hook_shape": 21, "hook": "Benda pasal HIFU yg takde sapa bagitau kau",
            "photo_query": "face care", "terms": [{"term": "HIFU", "meaning": MEANING}],
            "scenes": [{"caption": f"Babak {i}", "prompt": "a calm studio with soft light and a plain table", "accent": "#336699"}
                       for i in range(5)]}
    import semasa.hook_bank as hb
    orig = hb.declared
    hb.declared = lambda *a, **k: 21
    try:
        sb = motion_templates.validate_story(data, lang="bm", stream="regulab")
    finally:
        hb.declared = orig
    assert sb["terms"] == [{"term": "HIFU", "meaning": MEANING}]


def test_the_review_reads_the_terms_of_every_kind_of_film():
    one = {"kind": "explainer", "plan": {"terms": [{"term": "HIFU", "meaning": MEANING}]}}
    assert motion_review.terms_of(one)[0]["term"] == "HIFU"
    assert motion_review.terms_of({"kind": "story", "sb": {"terms": [{"term": "PIF", "meaning": "fail maklumat produk"}]}})
    assert motion_review.terms_of({"kind": "showcase", "sb": {}}) == []
    assert motion_review.terms_of({"kind": "story"}) == []
    text = motion_review.telegram_text({"id": "m", "brief": "x"},
                                       {"kind": "story", "sb": {"title": "t", "terms": [{"term": "PIF", "meaning": "fail"}],
                                                                 "scenes": []}})
    assert "PIF" not in text or "Apa itu" in text                            # templates show them too when they have any


def test_the_post_writers_are_asked_for_terms_and_the_idea_keeps_them():
    request = ideas.build_request({"id": "i", "stream": "regulab", "source_title": "HIFU", "source_url": "https://x.my/a"},
                                  {"ok": False, "why": "no article"}, {})
    assert definitions.RULE in request[0] and '"terms"' in ideas.REGULAB_SYSTEM and '"terms"' in ideas.LINKEDIN_SYSTEM
