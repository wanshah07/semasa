"""Ayat al-Quran: the worker fetches a verse to the same words as the page (rules/quran_cases.json, answers recorded from the
two sources), never lets a model's words stand in for a verse, and re-checks a stored verse before it is drawn."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from semasa import carousel, compliance, quran

DOC = json.loads((Path(__file__).resolve().parents[2] / "rules" / "quran_cases.json").read_text(encoding="utf-8"))


class _R:
    def __init__(self, code, body):
        self.status_code, self._body = code, body

    def json(self):
        return self._body


class Fake:
    """An HTTP client that answers from the recorded responses; a host in `down` answers 503."""

    def __init__(self, down=(), swap=None):
        self.down, self.swap, self.asked = down, swap or {}, []

    def get(self, url, **kw):
        self.asked.append(url)
        if any(d in url for d in self.down) or url not in DOC["responses"]:
            return _R(503, None)
        return _R(200, self.swap.get(url, DOC["responses"][url]))


@pytest.mark.parametrize("case", DOC["cases"], ids=lambda c: f"{c['ref']}-{c['stream']}-{'+'.join(c['down']) or 'up'}")
def test_a_verse_is_fetched_to_the_recorded_words(case):
    try:
        got = {"out": quran.fetch(case["ref"], case["stream"], Fake(case["down"]))}
    except quran.QuranError as e:
        got = {"error": str(e)}
    assert got == ({"out": case["out"]} if "out" in case else {"error": case["error"]})


def test_the_rules_carry_114_surahs_and_6236_ayat():
    assert len(quran.SURAHS) == 114 and sum(int(c) for _, c in quran.SURAHS) == 6236
    assert quran.parse("2:286") == (2, 286, 286) and quran.parse("2:287") is None and quran.parse("115:1") is None
    assert quran.parse("9:1-4") is None, "at most three ayat on a slide"
    assert quran.parse("2:169-168") is None, "a range runs forwards"
    assert quran.label("103:1-3") == "Al-'Asr 103:1-3" == compliance.ayat_label("103:1-3")


def test_the_bismillah_before_a_surah_is_not_part_of_its_first_ayat():
    b = quran.BISMILLAH
    assert quran.clean_arabic(f"{b} قُلْ هُوَ ٱللَّهُ أَحَدٌ", 112, 1) == "قُلْ هُوَ ٱللَّهُ أَحَدٌ"
    assert quran.clean_arabic("﻿" + b, 1, 1) == b, "in Al-Fatihah the Bismillah IS ayat 1"
    assert quran.clean_arabic(f"{b} قُلْ هُوَ ٱللَّهُ أَحَدٌ", 112, 2).startswith(b), "only before ayat 1"
    # the source marks the Bismillah before a surah differently from the one that is 1:1: recognised by its letters
    got = quran.fetch("112:1", "regulab", Fake())
    assert quran.skeleton(got["ayat_ar"]) == quran.skeleton("قُلْ هُوَ ٱللَّهُ أَحَدٌ")


def test_two_sources_that_disagree_on_the_arabic_are_refused():
    ed = quran.edition("linkedin")
    url = quran.QURAN_COM.format(key="2:168", tid=ed["quran_com"])
    wrong = json.loads(json.dumps(DOC["responses"][url]))
    wrong["verse"]["text_uthmani"] = "قُلْ هُوَ ٱللَّهُ أَحَدٌ"
    with pytest.raises(quran.QuranError, match="do not give the same Arabic"):
        quran.fetch("2:168", "linkedin", Fake(swap={url: wrong}))


def test_a_source_that_answers_with_another_ayat_is_not_believed():
    ed = quran.edition("regulab")
    url = quran.CLOUD.format(key="2:168", arabic=quran.RULES["arabic"]["edition"], edition=ed["id"])
    other = quran.CLOUD.format(key="112:1", arabic=quran.RULES["arabic"]["edition"], edition=ed["id"])
    got = quran.fetch("2:168", "regulab", Fake(swap={url: DOC["responses"][other]}))
    assert got["ayat_ed"] == "ms.basmeih@quran.com", "the answer for 112:1 was refused and the other source was asked"


def test_a_model_may_name_a_verse_and_never_write_one():
    raw = [{"title": "Peringatan", "ayat": "2:168", "ayat_ar": "kata-kata model", "ayat_tr": "terjemahan model",
            "ayat_ed": "ms.basmeih@alquran.cloud", "ayat_ok": "1", "ayat_label": "An-Nas 114:1"}, {"title": "Biasa"}, "teks"]
    clean = quran.untrusted(raw)
    assert clean[0] == {"title": "Peringatan", "ayat": "2:168"} and clean[1:] == raw[1:]
    filled = quran.fill(compliance.normalise_slides(clean), "regulab", Fake())
    want = next(c["out"] for c in DOC["cases"] if c["ref"] == "2:168" and c["stream"] == "regulab" and not c["down"])
    assert {k: filled[0][k] for k in want} == want and "ayat_ok" not in filled[0], "Wan's tick is never set by the worker"
    # nothing reachable: the reference stays, no words, and the scan blocks the post
    bare = quran.fill(compliance.normalise_slides(clean), "regulab", Fake(down=("api.",)))
    assert bare[0].get("ayat") == "2:168" and not bare[0].get("ayat_ar")
    flags = compliance.scan({"stream": "regulab", "lang": "bm", "text": {"bm": {"instagram": "Halal lagi baik.",
                             "facebook": "Halal lagi baik.", "threads": "Halal lagi baik."}}, "slides": bare,
                             "media": [{"id": "m", "alt": "kad"}]})
    assert any(f["hard"] and "have not been fetched" in f["msg"] for f in flags)


def test_a_stored_verse_is_rechecked_before_it_is_drawn():
    good = quran.fetch("2:168", "regulab", Fake())
    quran.verify([{"title": "x"}, good], "regulab", Fake())
    quran.verify([good], "regulab", Fake(down=("api.",)))               # a network fault is not a difference
    quran.verify([good], "regulab", Fake(down=("api.alquran.cloud",)))  # the other source: the Arabic by its letters
    with pytest.raises(quran.QuranError, match="slide 2.*differ from the published source"):
        quran.verify([{"title": "x"}, {**good, "ayat_ar": "قُلْ هُوَ ٱللَّهُ أَحَدٌ"}], "regulab", Fake())
    with pytest.raises(quran.QuranError, match="differ from the published source"):
        quran.verify([{**good, "ayat_tr": "Makanlah apa sahaja."}], "regulab", Fake())
    with pytest.raises(quran.QuranError, match="not this stream's"):
        quran.verify([good], "linkedin", Fake())
    with pytest.raises(quran.QuranError, match="is not an ayat"):
        quran.verify([{**good, "ayat": "2:999"}], "regulab", Fake())


def test_a_verse_slide_is_never_joined_to_a_neighbour_and_never_replaced_by_the_cover():
    verse = {"title": "Peringatan", "points": [], "ayat": "2:168", "ayat_ar": "ar", "ayat_tr": "tr"}
    plain = {"title": "Satu", "points": ["a"]}
    assert carousel.join(verse, plain) is None and carousel.join(plain, verse) is None
    assert carousel.cover_words(verse) is None and carousel.cover_words({"title": "Peringatan", "points": []}) is not None
    deck = [{"title": "Kulit", "points": []}, *[{"title": f"S{i}", "points": ["a"]} for i in range(3)], verse,
            *[{"title": f"T{i}", "points": ["b"]} for i in range(3)], {"title": "Tutup", "points": []}]
    out, _ = carousel.compact(deck, "regulab")
    assert verse in out, "squeezing a long carousel leaves the verse slide whole"


def test_the_slide_normaliser_keeps_a_verse_only_with_a_reference_and_works_out_its_label():
    kept = compliance.normalise_slides([{"ayat": "2:168", "ayat_ar": "x", "ayat_tr": "y", "ayat_ed": "ms.basmeih@alquran.cloud",
                                         "ayat_ok": "1", "ayat_label": "An-Nas 114:1"}])
    assert kept == [{"title": "", "points": [], "ayat": "2:168", "ayat_ar": "x", "ayat_tr": "y",
                     "ayat_ed": "ms.basmeih@alquran.cloud", "ayat_ok": "1", "ayat_label": "Al-Baqarah 2:168"}]
    no_ref = compliance.normalise_slides([{"title": "A", "ayat_ar": "x", "ayat_tr": "y", "ayat_ok": "1"}])
    assert no_ref == [{"title": "A", "points": []}], "verse words with no reference are dropped"
    assert compliance.normalise_slides([{"title": "A", "ayat": "2:999", "ayat_ed": "made.up"}]) == [
        {"title": "A", "points": [], "ayat": "2:999"}]


def test_the_writer_is_told_to_name_a_verse_and_never_write_one():
    from semasa import ideas
    for stream in ("regulab", "linkedin"):
        rules = " ".join(ideas.SLIDES_RULES[stream].split())
        assert '"ayat": "2:168"' in rules and "YOU NEVER WRITE A VERSE" in rules and "no Arabic script anywhere" in rules
        assert "when unsure, use none" in rules
