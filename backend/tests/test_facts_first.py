# ruff: noqa: E501
"""Facts first (Wan, 22 Nov 2026): official announcements lead, the newspaper is off, plain language, and every technical term
explained twice in the same words: a small footnote on the artwork (`foot`) and a Definisi paragraph at the end of the caption.
The glossary is rules/glossary.json; web/src/lib/glossary.js is its twin and web/*.test.mjs hold the page's side."""

import io
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from fakestore import FakeStore
from PIL import Image, ImageChops
from test_ideas import BRAND, FakeLLM

from semasa import autofill, caption_fit, carousel, compliance, glossary, ideas, slides, video_import
from semasa.media_generator import classic_words

NOW = datetime(2026, 9, 24, 2, 0, tzinfo=UTC)
FOLLOW = "Follow untuk tip regulatori yang senang faham."
TAGS = "#npra #kosmetik"


# ---------------------------------------------------------------- the glossary file
def test_the_glossary_file_is_well_formed_and_every_wording_fits_a_footnote():
    raw = json.loads((Path(__file__).resolve().parents[2] / "rules" / "glossary.json").read_text("utf-8"))
    assert "WAN REVIEWS" in raw["_about"] and len(raw["terms"]) >= 40
    ids, forms = set(), {}
    for e in raw["terms"]:
        assert e["id"] not in ids
        ids.add(e["id"])
        assert e["term"] and e["bm"].strip() and e["en"].strip() and e["source"].strip(), e["id"]
        assert set(e["label"]) == {"bm", "en"}, e["id"]
        for lang in ("bm", "en"):
            assert len(e[lang].split()) <= glossary.MEANING_WORDS, (e["id"], lang)       # it must fit a card's footnote
            assert not re.search(r"https?://|www\.|\d+\s?%", e[lang]), (e["id"], "a meaning carries no link and no figure")
        for f in e["term"]:
            assert forms.setdefault(f.lower(), e["id"]) == e["id"], f"{f!r} names two entries"
    # the terms Wan listed are all in
    for term in ("notifikasi kosmetik", "NPRA", "PIF", "SPHM", "sijil halal", "JAKIM", "FSQD", "BKKM", "KKM", "ACD", "bahan terlarang",
                 "racun berjadual", "tarik balik", "SDS", "CPNP", "SCCS", "MoS", "NOAEL", "GMP", "CGMP", "HACCP", "MeSTI", "DRGD",
                 "MAL number", "NOT number", "halal logo", "traceability"):
        assert glossary.lookup(term), term


def test_a_term_is_found_as_a_whole_word_and_a_form_with_capitals_keeps_them():
    found = {e["id"]: w for e, w in glossary.used("Fail PIF mesti ada. Notifikasi kosmetik dibuat di QUEST3+.")}
    assert found == {"pif": "PIF", "notifikasi_kosmetik": "Notifikasi kosmetik", "quest3": "QUEST3+"}
    assert glossary.used("Pifagoras dan sdsx tidak ada kaitan.") == []                  # never inside another word
    assert glossary.used("mos pasar") == [] and [w for _, w in glossary.used("Kira MoS dahulu")] == ["MoS"]   # capitals matter for MoS
    assert [w for _, w in glossary.used("a COSMETIC NOTIFICATION")] == ["COSMETIC NOTIFICATION"]            # a lowercase form matches any case
    # the words so familiar the check never asks for them: still found when asked, never by default
    assert glossary.used("KKM umum tarik balik NPRA") == []
    assert {e["id"] for e, _ in glossary.used("KKM umum tarik balik NPRA", scan_only=False)} == {"kkm", "tarik_balik", "npra"}


def test_a_footnote_and_a_definisi_paragraph_are_read_back_into_terms():
    foot = "Definisi: PIF = fail; Notifikasi kosmetik = pemberitahuan kepada NPRA."
    assert glossary.pairs_of(foot) == [("PIF", "fail"), ("Notifikasi kosmetik", "pemberitahuan kepada NPRA")]
    assert glossary.defined_in(foot) == {"pif", "notifikasi_kosmetik"}
    assert glossary.defined_in("Definition: cosmetic notification = telling NPRA") == {"notifikasi_kosmetik"}
    cap = f"Isi.\n\nDefinisi: PIF = fail.\n\n{FOLLOW}\n\n{TAGS}"
    assert glossary.defined_in_caption(cap) == {"pif"} and "Definisi" not in glossary.strip_definisi(cap)
    assert glossary.defined_in_caption("Ada Definisi: PIF = fail di tengah ayat.") == set()      # only a paragraph of its own


def test_a_glossary_term_always_takes_the_glossarys_own_wording_and_a_long_custom_one_is_dropped():
    pif = glossary.lookup("PIF")
    got = glossary.clean_foot("Definisi: PIF = fail yang saya tulis sendiri", "bm")
    assert got == f"Definisi: PIF = {glossary.meaning(pif, 'bm').rstrip('.')}."
    assert glossary.clean_foot("Definisi: ZXQ = " + "kata " * 20, "bm") == ""
    assert glossary.clean_foot("Definisi: ZXQ = benda kecil; PIF = x; NPRA = y; MoS = z", "bm").count(" = ") == 2     # two terms at most
    assert glossary.clean_foot("Definisi: ZXQ = https://contoh.my", "bm") == ""
    assert glossary.clean_foot("Definisi: PIF = x", "en").startswith("Definition: PIF = A cosmetic's technical")


# ---------------------------------------------------------------- the soft check
def _post(caption="", slide_list=None, lang="bm", stream="regulab"):
    plats = ("instagram", "facebook", "threads") if stream == "regulab" else ("linkedin",)
    post = {"stream": stream, "lang": lang, "text": {lang: {p: caption for p in plats}}, "media": [{"id": "m", "alt": "x"}]}
    if slide_list is not None:
        post["slides"] = slide_list
    return post


def _explain(flags):
    return sorted((f["where"], f["msg"]) for f in flags if f["msg"].startswith("explain "))


def test_an_unexplained_term_in_a_caption_or_a_slide_is_a_soft_warning_never_a_block():
    flags = compliance.scan(_post("Setiap kosmetik perlu PIF yang lengkap."))
    assert ("Caption (instagram)", 'explain "PIF": add a footnote (Nota kaki)') in _explain(flags)
    assert not any(f["hard"] for f in flags if f["msg"].startswith("explain "))
    covered = compliance.scan(_post("Setiap kosmetik perlu PIF yang lengkap.\n\nDefinisi: PIF = fail maklumat produk."))
    assert _explain(covered) == []
    # the Definisi paragraph is not itself "using" a term, and a term in it is not warned about
    assert _explain(compliance.scan(_post("Isi tanpa istilah.\n\nDefinisi: PIF = fail maklumat produk."))) == []


def test_a_slide_term_is_explained_by_its_own_foot_or_by_the_captions_definisi_line():
    word = {"title": "Apa itu PIF", "points": ["NPRA boleh minta PIF."]}
    assert ("Slide 1", 'explain "PIF": add a footnote (Nota kaki)') in _explain(compliance.scan(_post("Isi.", [word])))
    assert _explain(compliance.scan(_post("Isi.", [{**word, "foot": "Definisi: PIF = fail maklumat produk"}]))) == []
    assert _explain(compliance.scan(_post("Isi.\n\nDefinisi: PIF = fail maklumat produk.", [word]))) == []
    # the foot is not the slide's own words: a term only its foot names is not "used" on the slide
    assert _explain(compliance.scan(_post("Isi.", [{"title": "Satu", "points": [], "foot": "Definisi: PIF = fail"}]))) == []
    # a word so common the check never asks for it
    assert _explain(compliance.scan(_post("KKM dan NPRA umum tarik balik.", [{"title": "KKM tarik balik", "points": []}]))) == []


def test_the_foot_is_kept_by_normalise_slides_compared_by_slides_key_and_judged_like_any_slide_word():
    s = compliance.normalise_slides([{"title": "A", "points": ["b"], "foot": "  Definisi: PIF = fail  ", "footnote": "NPRA"}])
    assert s == [{"title": "A", "points": ["b"], "footnote": "NPRA", "foot": "Definisi: PIF = fail"}]
    assert compliance.slides_key([{"title": "A", "foot": "x"}]) != compliance.slides_key([{"title": "A"}])
    assert "Definisi: PIF" in compliance.slide_text(s[0]) and "Definisi" not in compliance.slide_body(s[0])
    assert compliance.normalise_slides([{"foot": "Definisi: PIF = fail"}]) == [{"title": "", "points": [], "foot": "Definisi: PIF = fail"}]
    bad = compliance.scan(_post("Isi.", [{"title": "A", "points": [], "foot": "Hubungi kami untuk PIF"}]))
    assert any(not f["hard"] and f["where"] == "Slide 1" for f in bad), "a call to action in a foot is named, as a warning"
    assert not any(f["hard"] and f["where"] == "Slide 1" for f in bad), "and no longer blocks (Wan, 23 Nov 2026)"


def test_an_imported_film_gets_the_same_soft_check_on_its_caption():
    flags = video_import.draft_flags("regulab", "bm", {"instagram": "Setiap kosmetik perlu PIF."}, ["instagram"], "Film", {})
    assert [f for f in flags if f["msg"] == 'explain "PIF": add a footnote (Nota kaki)' and not f["hard"]]
    done = video_import.draft_flags("regulab", "bm", {"instagram": "Setiap kosmetik perlu PIF.\n\nDefinisi: PIF = fail."},
                                    ["instagram"], "Film", {})
    assert _explain(done) == []


# ---------------------------------------------------------------- the caption: the Definisi paragraph is protected
DEF = "Definisi: PIF = Fail maklumat dan bukti keselamatan produk kosmetik; NPRA = Agensi di bawah KKM."


def _caption(n):
    body = "\n\n".join(f"{i}. Fakta {i}. " + "Ayat penuh di sini. " * 12 for i in range(1, n + 1))
    return f"Hook yang menarik.\n\n{body}\n\n{DEF}\n\n{FOLLOW}\n\n{TAGS}"


def test_trimming_a_caption_keeps_the_definisi_paragraph_with_the_follow_line_and_the_tags():
    cap = _caption(30)
    out = caption_fit.fit_caption(cap, 2200)
    assert caption_fit.units(out) <= 2200 and out.startswith("Hook yang menarik.")
    assert out.endswith(f"{DEF}\n\n{FOLLOW}\n\n{TAGS}"), "the tail survives whole, in order"
    # so tight that only the hook and the tail fit: the body goes first, the definitions stay
    tight = caption_fit.fit_caption(cap, len(f"Hook yang menarik.\n\n{DEF}\n\n{FOLLOW}\n\n{TAGS}") + 5)
    assert "Definisi:" in tight and tight.endswith(TAGS) and "1. Fakta" not in tight
    assert caption_fit.fit_caption("Pendek.\n\n" + DEF, 2200) == "Pendek.\n\n" + DEF
    en = caption_fit.fit_caption(_caption(30).replace("Definisi:", "Definition:"), 2200)
    assert "Definition: PIF" in en


def test_a_threads_chain_carries_the_definitions_on_its_last_post():
    posts = "\n\n---\n\n".join(["Hook thread.\n\nApa yang ada.\n\nPerinciannya di bawah."]
                              + [f"Label {i}:\n\n" + "\n".join(f"{j}. Satu perkara penting nombor {j} dalam thread." for j in range(1, 6))
                                 for i in range(1, 7)])
    cap = f"{posts}\n\nDefinisi: PIF = Fail maklumat produk.\n\n{FOLLOW}\n\n#npra"
    out = caption_fit.fit_thread(cap, 500, 5)
    parts = [p for p in out.split("\n\n---\n\n")]
    assert len(parts) <= 5 and all(caption_fit.units(p) <= 500 for p in parts)
    assert "Definisi: PIF = Fail maklumat produk." in parts[-1] and parts[-1].endswith("#npra")


# ---------------------------------------------------------------- the writer path
def test_build_definitions_merges_every_foot_once_in_order():
    items = [{"title": "A", "foot": "Definisi: PIF = x; Notifikasi kosmetik = y."}, {"title": "B"},
             {"title": "C", "foot": "Definisi: PIF = z; Annex III = w."}]
    para = ideas.build_definitions(items, "bm")
    assert para.startswith("Definisi: PIF = Fail maklumat") and para.count("PIF =") == 1
    assert [t for t, _ in glossary.pairs_of(para)] == ["PIF", "Notifikasi kosmetik", "Annex III"] and para.endswith(".")
    assert ideas.build_definitions(items, "en").startswith("Definition: PIF = A cosmetic's")
    assert ideas.build_definitions([{"title": "A"}], "bm") == ""
    assert len(glossary.pairs_of(ideas.build_definitions(items, "bm", cap=2))) == 2


def test_clean_feet_never_puts_a_foot_on_the_cover_or_the_closing_slide_and_fills_what_the_writer_missed():
    deck = [{"title": "Kulit", "foot": "Definisi: PIF = x"},
            {"title": "Apa itu PIF", "points": ["Notifikasi kosmetik dan Annex III dan SDS."], "foot": "Definisi: PIF = fail saya"},
            {"title": "Tiada istilah", "points": ["Biasa."], "foot": "Definisi: PIF = x"},
            {"title": "Tutup", "points": ["PIF"], "foot": "Definisi: PIF = x"}]
    out = ideas.clean_feet(deck, "bm")
    assert "foot" not in out[0] and "foot" not in out[3]
    assert out[1]["foot"].startswith("Definisi: PIF = Fail maklumat") and out[1]["foot"].count(" = ") == 2     # topped up, two at most
    assert "foot" not in out[2], "a term that is not on the slide is not defined there"
    assert ideas.clean_feet([{"title": "Poster PIF", "points": []}], "bm")[0]["foot"].startswith("Definisi: PIF")   # a lone poster keeps its own
    assert "foot" not in ideas.clean_feet([{"ayat": "2:168", "title": "x", "foot": "Definisi: PIF = x"}] * 3, "bm")[1]


def test_the_definisi_paragraph_lands_before_the_follow_line_and_the_hashtags_and_is_never_doubled():
    feet = [{"title": "A", "points": [], "foot": "Definisi: PIF = x"}]
    caption = f"Hook.\n\n1. Fakta tentang PIF.\n\n{FOLLOW}\n\n{TAGS}"
    out = ideas.with_definitions({"bm": {"instagram": caption, "threads": caption}, "en": {"instagram": caption}}, [feet], "regulab", "bm")
    para = out["bm"]["instagram"].split("\n\n")
    assert para[-1] == TAGS and para[-2] == FOLLOW and para[-3].startswith("Definisi: PIF = Fail maklumat")
    assert out["en"]["instagram"].split("\n\n")[-3].startswith("Definition: PIF = A cosmetic's")      # the other language, its own wording
    again = ideas.with_definitions(out, [feet], "regulab", "bm")
    assert again == out and again["bm"]["instagram"].count("Definisi:") == 1
    # a caption with nothing to define is left alone; LinkedIn has no follow line and says "Definition:"
    assert ideas.with_definitions({"bm": {"instagram": "Tiada istilah."}}, [[]], "regulab", "bm") == {"bm": {"instagram": "Tiada istilah."}}
    li = ideas.with_definitions({"en": {"linkedin": "Hook.\n\n1. A fact about PIF.\n\n#npra"}}, [[]], "linkedin", "en")
    assert li["en"]["linkedin"].split("\n\n")[-2].startswith("Definition: PIF = A cosmetic's") and li["en"]["linkedin"].endswith("#npra")
    # a term of the writer's own is defined only in the post's own language, and a glossary term is put back in Wan's wording
    own = ideas.with_definitions({"bm": {"instagram": "Hook.\n\nDefinisi: ZXQ = benda kecil; PIF = ayat saya."},
                                  "en": {"instagram": "Hook.\n\nDefinition: ZXQ = a small thing; PIF = my words."}}, [[]], "regulab", "bm")
    assert "ZXQ = benda kecil" in own["bm"]["instagram"] and "my words" not in own["en"]["instagram"]
    assert "ZXQ" not in own["en"]["instagram"] and "ayat saya" not in own["bm"]["instagram"]


def _answer(**more):
    cap = f"Hook.\n\n1. NPRA minta PIF.\n\n{FOLLOW}\n\n{TAGS}"
    return {"fit": True, "hook": "Hook", "hook_shape": 21, "domain": "kosmetik", "citation": "NPRA, Garis Panduan",
            "text": {"bm": {"instagram": cap, "facebook": cap, "threads": cap}}, "visual_prompt": "botol", "alt": "botol", **more}


def _write(monkeypatch, answer, brief):
    monkeypatch.setattr(ideas, "read_source", lambda url: {"ok": False, "why": "no link", "image": None})
    store = FakeStore(semasa_settings=[{"key": "brand", "value": BRAND}], semasa_posts=[], media_generations=[], semasa_ideas=[])
    llm = FakeLLM(answer)
    idea = {"id": "i1", "stream": "regulab", "source_title": "T", "created_by": "u", "make_media": "image", "brief": brief}
    store.tables["semasa_ideas"].append({**idea, "status": "working"})
    ideas.process_idea(store, llm, idea, ideas.load_settings(store))
    return store, llm


def test_a_carousel_draft_gets_clean_feet_and_one_definisi_paragraph_in_every_caption(monkeypatch):
    slides_out = [{"title": "Apa itu PIF", "points": []},
                  {"title": "Fail yang wajib", "lead": "Simpan PIF di syarikat.", "points": ["NPRA boleh minta fail ini."],
                   "foot": "Definisi: PIF = fail saya sendiri"},
                  {"title": "Tutup", "points": ["Sedia sebelum jual."], "foot": "Definisi: PIF = x"}]
    store, llm = _write(monkeypatch, _answer(slides=slides_out), {"format": "carousel"})
    post = store.tables["semasa_posts"][0]
    mid = post["slides"][1]
    assert mid["foot"] == f"Definisi: PIF = {glossary.meaning(glossary.lookup('PIF'), 'bm').rstrip('.')}."
    assert "foot" not in post["slides"][0] and "foot" not in post["slides"][2]
    for plat in ("instagram", "facebook", "threads"):
        paras = post["text"]["bm"][plat].split("\n\n")
        assert paras[-1] == TAGS and paras[-2] == FOLLOW and paras[-3].startswith("Definisi: PIF = Fail maklumat"), plat
    assert not [f for f in post["flags"] if f["msg"].startswith("explain ")], "a post written this way raises no footnote warning"
    system = llm.seen[0][0]
    assert "FACTS FIRST" in system and "Definisi: <term> = <what it is, at most 14 words>" in system and "Fail maklumat dan bukti" in system
    job = store.tables["media_generations"][0]
    assert job["meta"]["slides"][1]["foot"] == mid["foot"]


def test_a_poster_draft_carries_its_foot_to_the_render_job_and_its_terms_to_the_caption(monkeypatch):
    poster = {"eyebrow": "Kosmetik", "title": "Hook", "lead": "NPRA umum.", "points": ["Semak PIF anda."], "foot": "Definisi: PIF = x"}
    store, _ = _write(monkeypatch, _answer(poster=poster), {"format": "poster"})
    job = store.tables["media_generations"][0]
    assert job["meta"]["design"] == "poster" and job["meta"]["slides"][0]["foot"].startswith("Definisi: PIF = Fail maklumat")
    assert "Definisi: PIF = Fail maklumat" in store.tables["semasa_posts"][0]["text"]["bm"]["instagram"]


def test_both_writers_are_told_facts_first_and_an_announcement_is_told_to_open_with_who_what_when():
    for stream, label, tail in (("regulab", "Definisi", "the follow line and the hashtags"), ("linkedin", "Definition", "the hashtags")):
        block = ideas.facts_first(stream)
        assert "EVERY CLAIM IS A FACT" in block and "ANNOUNCEMENT" in block.upper() and "PLAIN LANGUAGE" in block
        assert f'"{label}: <term> = <what it is, at most 14 words>"' in block and f"before {tail}" in block
        assert glossary.meaning(glossary.lookup("PIF"), "en" if stream == "linkedin" else "bm") in block
    system, user = ideas.build_request({"stream": "regulab", "source_title": "Pekeliling NPRA", "source_name": "NPRA",
                                        "brief": {"announcement": True, "source_priority": "official"}}, {"ok": False}, {})
    assert "WHO announced WHAT" in user and "FROM WHEN" in user and "the 25 hook shapes" not in user
    assert "hook" in system.lower()                           # the first-line hook rule stays
    assert "ANNOUNCEMENT BY A REGULATOR" not in ideas.build_request({"stream": "regulab", "source_title": "t", "brief": {}},
                                                                    {"ok": False}, {})[1]


# ---------------------------------------------------------------- the artwork
def test_the_classic_drawing_carries_the_foot_and_a_long_one_loses_its_last_term_never_half_a_word():
    foot = "Definisi: PIF = Fail maklumat dan bukti keselamatan produk kosmetik; Notifikasi kosmetik = Memaklumkan NPRA tentang produk kosmetik sebelum dijual."
    deck = [{"title": "Kulit", "points": []}, {"title": "Apa itu PIF", "points": ["Fail ini mesti ada."], "foot": foot},
            {"title": "Tutup", "points": ["Sedia."], "foot": foot}]
    with_foot = slides.render(deck, stream="regulab", source="NPRA", website="www.x.com")
    without = slides.render([{k: v for k, v in s.items() if k != "foot"} for s in deck], stream="regulab", source="NPRA",
                            website="www.x.com")
    px = lambda b: Image.open(io.BytesIO(b)).convert("L")  # noqa: E731
    low = (0, 1100, 1080, 1280)
    assert ImageChops.difference(px(with_foot[1]).crop(low), px(without[1]).crop(low)).getbbox(), "the note is drawn on a middle slide"
    for i in (0, 2):                                           # the cover and the closing slide carry none
        assert with_foot[i] == without[i]
    three = foot + "; Annex III = Senarai bahan yang dibenarkan dalam kosmetik hanya dengan had atau syarat tertentu."
    lines, font = slides.foot_layout(three, 904)
    assert len(lines) <= slides.FOOT_LINES
    drawn = " ".join(" ".join(r.text for r in ln.runs) for ln in lines)
    assert drawn.startswith("Definisi: PIF = Fail maklumat") and "Annex" not in drawn and drawn.endswith(".")
    assert slides.foot_layout("Definisi: " + "x" * 400, 904)[0] == [], "not even the first term fits: no note, never a cut one"
    assert classic_words([{"title": "T", "points": ["a"], "foot": "Definisi: PIF = x"}])[0]["foot"] == "Definisi: PIF = x"
    assert "foot" not in classic_words([{"title": "T", "points": ["a"]}])[0]


def test_joining_two_slides_keeps_both_definition_notes():
    a = {"title": "A", "points": ["x"], "foot": "Definisi: PIF = fail"}
    b = {"title": "B", "points": ["y"], "foot": "Definisi: Annex III = senarai"}
    joined = carousel.join(a, b)
    assert [t for t, _ in glossary.pairs_of(joined["foot"])] == ["PIF", "Annex III"]
    assert carousel.join({"title": "A", "points": ["x"]}, b)["foot"] == b["foot"]
    assert "foot" not in carousel.join({"title": "A", "points": ["x"]}, {"title": "B", "points": ["y"]})


# ---------------------------------------------------------------- autofill: facts first
def test_the_config_has_news_off_unless_switched_on():
    assert autofill.config({})["news"] is False
    assert autofill.config({"autofill": {"enabled": True, "news": True}})["news"] is True
    assert autofill.config({"autofill": {"enabled": True, "news": "yes"}})["news"] is False


def test_social_rows_never_fill_a_slot_unless_news_is_on():
    def row(i, section):
        return {"id": f"w{i}", "section": section, "source": "x", "title": f"Baris {i}", "url": f"https://x.example/{i}", "summary": "s",
                "domain": "kosmetik", "relevant": True, "dismissed": False, "created_at": "2026-09-23T00:00:00+00:00"}
    store = FakeStore(isu_semasa_trends=[], semasa_watch=[row(1, "reddit"), row(2, "threads"), row(3, "regulatory"), row(4, "folder")],
                      semasa_ideas=[], semasa_posts=[], semasa_log=[], semasa_settings=[])
    assert {r["id"] for r in autofill.candidates(store, NOW)} == {"w3", "w4"}
    assert {r["id"] for r in autofill.candidates(store, NOW, news=True)} == {"w1", "w2", "w3", "w4"}


def test_an_announcement_word_is_a_whole_word_and_a_regulator_notice_is_the_announcement():
    for t in ("NPRA tarik balik produk", "Amaran KKM", "Pekeliling JAKIM 2026", "Recall of a cream", "Larangan baharu", "Notis penguatkuasaan"):
        assert autofill.ANNOUNCEMENT.search(t), t
    for t in ("Urban banking trends", "A bank notes review", "Laporan tahunan"):
        assert not autofill.ANNOUNCEMENT.search(t), t
    assert autofill.is_announcement({"section": "regulatory"}) and not autofill.is_announcement({"section": "publication"})
    assert [autofill.tier(x) for x in ({"section": "regulatory", "title": "Amaran"}, {"section": "regulatory", "title": "x"},
                                       {"section": "publication"}, {"section": "news"}, {"section": "reddit"})] == [0, 1, 2, 6, 7]


def test_the_glossary_answers_the_shared_cases_exactly_as_the_page_does():
    """rules/glossary_cases.json is run by web/glossary.test.mjs against glossary.js too: the two must agree."""
    doc = json.loads((Path(__file__).resolve().parents[2] / "rules" / "glossary_cases.json").read_text("utf-8"))
    for c in doc["used"]:
        assert [[e["id"], w] for e, w in glossary.used(c["text"])] == c["used"], c["text"]
        assert [e["id"] for e, _ in glossary.used(c["text"], False)] == c["all"], c["text"]
    for c in doc["feet"]:
        assert [list(p) for p in glossary.pairs_of(c["foot"])] == c["pairs"], c["foot"]
        assert sorted(glossary.defined_in(c["foot"])) == c["defined"], c["foot"]
        assert glossary.clean_foot(c["foot"], "bm") == c["clean_bm"] and glossary.clean_foot(c["foot"], "en") == c["clean_en"], c["foot"]
    for c in doc["captions"]:
        assert sorted(glossary.defined_in_caption(c["caption"])) == c["defined"] and glossary.strip_definisi(c["caption"]) == c["stripped"]
