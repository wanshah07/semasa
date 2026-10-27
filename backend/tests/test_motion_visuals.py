"""Map, people, ring, trend line, columns, news clipping and calendar (Wan, 27 Oct 2026): drawn only from what a scene says or
from the idea's own source, never invented."""

import shutil

import pytest
from PIL import Image

from semasa import motion, motion_auto, motion_layout
from semasa import motion_visuals as mv

PAL = motion.PALETTE["regulab"]
NEWS_ROW = {"id": "n1", "brief": "recall", "language": "bm", "options": {"evidence": {
    "source_url": "https://www.bharian.com.my/berita/nasional/2026/10/kkm-tarik-balik-produk",
    "source_title": "KKM tarik balik 12 produk kosmetik mengandungi bahan terlarang selepas pemeriksaan"}}}


def scene(i, heading, lines=(), **over):
    return {"id": f"s{i}", "role": motion_auto.ROLES[i - 1], "kicker": "", "heading": heading, "lines": list(lines),
            "narration": "", "start": (i - 1) * 7.0, "duration": 6.8, **over}


def _args(w=1080, h=1920, lang="bm", stream="regulab"):
    return dict(total=11, w=w, h=h, lang=lang, palette=PAL, gsap=motion.GSAP, html_lang="ms", resolution="portrait",
                stream=stream)


def _film(sc, code, news=None, **kw):
    scenes = [sc, {"id": "brand-outro", "start": 7, "duration": 3, "heading": "x"}]
    return motion_layout.compose(scenes=scenes, plan={"scenes": {sc["id"]: [code]}, "video": {}, "news": news}, **_args(**kw))


def test_a_map_is_drawn_for_places_the_words_name_and_never_for_malaysia_alone():
    assert mv.places_in("Malaysia, Singapura dan Indonesia") == ["MYS", "SGP", "IDN"]
    assert set(mv.places_in("Peraturan EU dan ASEAN")) == {"EU", "ASEAN"}
    assert mv.places_in("Jepun, Jerman dan Amerika Syarikat") == ["JPN", "DEU", "USA"]
    assert mv.places_in("the US and the UK") == ["USA", "GBR"]
    assert mv.places_in("uses a bus; revenue; menus") == [], "a short capital name is read as a word, not inside another"
    assert mv.meaningful_places("Produk dijual di Malaysia") == [], "Malaysia alone is every film's setting: a map adds nothing"
    assert mv.meaningful_places("Malaysia dan Singapura") == ["MYS", "SGP"]
    assert mv.meaningful_places("tiada tempat di sini") == []


def test_the_figures_the_words_carry_are_read_not_guessed():
    assert mv.ratio_in(["3 daripada 10 produk gagal"]) == ("3 daripada 10 produk gagal", 3.0, 10.0)
    assert mv.ratio_in(["1 in 4 shoppers"])[1:] == (1.0, 4.0)
    assert mv.ratio_in(["35% pengguna"])[1:] == (35.0, 100.0)
    assert mv.ratio_in(["tahun 2026 sahaja", "dari 12 produk"]) is None
    assert mv.percent_in(["tiada", "12.5% naik"])[1] == 12.5
    assert mv.trend_in(["2022: 120 kes", "2023: 180 kes", "2024: 260 kes"]) == [("2022", 120.0, "120"), ("2023", 180.0, "180"),
                                                                                   ("2024", 260.0, "260")]
    assert mv.trend_in(["2022: 120 kes", "2023: 180 kes"]) == [], "two points are not a trend"
    cols = mv.columns_in(["Denda RM 25,000 untuk individu", "Denda RM 50,000 untuk syarikat", "naik 40%", "tahun 2026"])
    got = [(v, raw) for _, v, raw, _ in cols]
    assert got == [(25000.0, "RM 25,000"), (50000.0, "RM 50,000")], "a % or a year line is left out"
    assert mv.columns_in(["Hanya satu 12"]) == []
    assert mv._value("1,234.5") == 1234.5 and mv._value("1.234") == 1234.0 and mv._value("2,5") == 2.5


def test_dates_are_read_in_malay_and_english_and_never_made_up():
    assert mv.dates_in("Berkuat kuasa 1 Januari 2027") == [(1, 1, 2027)]
    assert mv.dates_in("effective March 5, 2027 and 30 Jun 2028") == [(5, 3, 2027), (30, 6, 2028)]
    assert mv.dates_in("tamat Jun 2028") == [(None, 6, 2028)]
    assert mv.dates_in("sejak 2026-10-27") == [(27, 10, 2026)]
    assert mv.dates_in("pada 1/12/2026") == [(1, 12, 2026)], "day first, the Malaysian way"
    assert mv.dates_in("tahun 2026 dan Mac") == [], "a year alone or a month alone is not a date"
    assert len(mv.dates_in("1 Jan 2027, 2 Feb 2027, 3 Mac 2027")) == 2, "two tiles at most"


def test_a_clipping_comes_only_from_a_news_page_and_the_linkedin_stream_never_names_an_aggregator():
    got = mv.news_of(NEWS_ROW)
    assert got["outlet"] == "Berita Harian" and got["title"].startswith("KKM tarik balik 12 produk")
    def ev(url, title="A headline long enough to be a news item here"):
        return {"options": {"evidence": {"source_url": url, "source_title": title}}}
    for url in ("https://pubmed.ncbi.nlm.nih.gov/42926343/", "https://www.youtube.com/watch?v=x", "https://www.npra.gov.my/x",
                "https://efsa.onlinelibrary.wiley.com/doi/10.2903/j.efsa.2026.10388", "onedrive://abc#r18",
                "https://www.reddit.com/r/malaysia"):
        assert mv.news_of(ev(url)) is None, url
    assert mv.news_of(ev("https://www.bharian.com.my/a", "Hook: sunscreen is one slice of cheese in this sheet")) is None
    assert mv.news_of(ev("https://www.bharian.com.my/a", "Too short")) is None
    agg = ev("https://www.chemlinked.com/news/x")
    assert mv.news_of(agg, "regulab")["outlet"] == "chemlinked.com" and mv.news_of(agg, "linkedin") is None
    long = mv.news_of(ev("https://www.thestar.com.my/a", "word " * 60))
    assert len(long["title"]) <= 131 and long["title"].endswith("…") and long["outlet"] == "The Star"


def test_the_chooser_gives_a_picture_only_to_a_scene_whose_words_carry_it():
    film = [scene(1, "Larangan baharu", ["Malaysia dan Singapura menyelaras kawalan", "Berkuat kuasa 1 Januari 2027"]),
            scene(2, "Ramai terkesan", ["35% pengguna salah baca label", "Semak dahulu"]),
            scene(3, "Kes meningkat", ["2022: 120 kes", "2023: 180 kes", "2024: 260 kes"]),
            scene(4, "Tiada angka", ["Semak label", "Simpan rekod"])]
    motion_auto.assign_photos(film, [{"path": "p.jpg"}] * 3)
    plan = motion_auto.choose(NEWS_ROW, film, voiced=False, lang="bm")
    got = {sid: [c for c in codes if c in mv.CODES] for sid, codes in plan["scenes"].items()}
    assert len(got["s1"]) == 1 and got["s1"][0] in {"G01", "G07", "G06"}, "one picture a scene"
    assert got["s2"] and got["s2"][0] in {"G02", "G03", "G06"} and got["s3"] and got["s3"][0] in {"G04", "G06"}
    assert got["s4"] == [], "a scene with no place, figure or date gets no picture, so nothing is invented"
    assert sum("G06" in v for v in got.values()) <= 1, "one clipping a film"
    assert plan["news"]["outlet"] == "Berita Harian" and set(plan["visual"]) == {c for v in got.values() for c in v}
    # no news source, no clipping
    plan2 = motion_auto.choose({**NEWS_ROW, "options": {}}, film, voiced=False, lang="bm")
    assert "G06" not in {c for v in plan2["scenes"].values() for c in v} and plan2["news"] is None
    # a ring and a chart of the same percentage are not both asked for
    for codes in plan["scenes"].values():
        assert not ({"G02", "G03"} & set(codes) and "V09" in codes)


@pytest.mark.parametrize("code, head, lines, needle", [
    ("G01", "Larangan baharu", ["Malaysia dan Singapura menyelaras kawalan", "Thailand menyusul"], 'class="gmap"'),
    ("G02", "Ramai terkesan", ["3 daripada 10 produk gagal semakan"], 'class="gpic"'),
    ("G03", "Ramai terkesan", ["35% pengguna salah baca label"], 'stroke-dasharray'),
    ("G04", "Kes meningkat", ["2022: 120 kes", "2023: 180 kes", "2024: 260 kes"], "<polyline"),
    ("G05", "Kos", ["Denda RM 25,000 untuk individu", "Denda RM 50,000 untuk syarikat"], 'class="gcol"'),
    ("G07", "Tarikh", ["Berkuat kuasa 1 Januari 2027"], 'class="mo"'),
])
def test_each_picture_style_is_built_into_the_scene_and_reported(code, head, lines, needle):
    html, rep = _film(scene(1, head, lines), code)
    assert needle in html and rep["visual"] == [code] and code in rep["built"] and code not in rep["not_built"]


def test_a_picture_style_with_nothing_to_draw_is_not_drawn_and_says_so():
    for code in ("G01", "G02", "G03", "G04", "G05", "G07"):
        html, rep = _film(scene(1, "Tiada apa", ["Semak label", "Simpan rekod"]), code)
        assert rep["visual"] == [] and code in rep["not_built"] and 'class="gm' not in html, code
    html, rep = _film(scene(1, "Berita", ["Satu"]), "G06", news=None)
    assert rep["visual"] == [] and "Keratan" not in html


def test_the_clipping_carries_the_outlet_and_the_headline_as_the_source_gave_them():
    html, rep = _film(scene(1, "Tarik balik", ["Tiada raksa"]), "G06", news=mv.news_of(NEWS_ROW))
    assert rep["visual"] == ["G06"] and "Berita Harian" in html and "Keratan akhbar" in html
    assert "KKM tarik balik 12 produk kosmetik mengandungi bahan terlarang selepas pemeriksaan" in html
    en, _ = _film(scene(1, "Recall", ["No mercury"]), "G06", news=mv.news_of(NEWS_ROW), lang="en")
    assert "News clipping" in en and "Keratan akhbar" not in en


def test_the_ring_counts_to_the_percentage_and_the_line_is_not_printed_twice():
    html, _ = _film(scene(1, "Ramai terkesan", ["35% pengguna salah baca label", "Semak dahulu"]), "G03")
    assert html.count("pengguna salah baca label") == 1 and ">35<" in html and 'textContent:35' in html


def test_a_film_is_laid_out_again_until_it_shows_at_least_25_styles_and_reports_what_it_really_draws():
    film = [scene(1, "Larangan baharu", ["Malaysia dan Singapura menyelaras kawalan", "Berkuat kuasa 1 Januari 2027"]),
            scene(2, "Ramai terkesan", ["35% pengguna salah baca label", "Semak dahulu"]),
            scene(3, "Kes meningkat", ["2022: 120 kes", "2023: 180 kes"]),
            scene(4, "Kos", ["Denda RM 25,000", "Denda RM 50,000"])]
    motion_auto.assign_photos(film, [{"path": f"p{i}.jpg"} for i in range(4)])
    scenes = film + [{"id": "brand-outro", "start": 28, "duration": 3, "heading": "x"}]
    plan = motion_layout.styled(NEWS_ROW, scenes, voiced=False, lang="bm", stream="regulab", compose_args=_args())
    assert plan["drawn"] >= motion_auto.MIN_STYLES == 25, plan["not_drawn"]
    _, rep = motion_layout.compose(scenes=scenes, plan=plan, **_args())
    shown = set(rep["built"]) | set(plan["native"]) | set(plan["audio"])
    assert len(shown) == plan["drawn"], "the count is what the layout draws"
    assert rep["visual"], "the film shows at least one picture of the facts"
    # a style the layout could not draw is left out of the next choice
    again = motion_auto.choose(NEWS_ROW, film, voiced=False, lang="bm", exclude={"G03", "G04"})
    assert not {"G03", "G04"} & {c for v in again["scenes"].values() for c in v}


def test_the_new_picture_blocks_never_overlap_the_words_in_a_real_browser(tmp_path):
    from semasa import motion_probe
    if not motion_probe.chrome_path():
        pytest.skip("no Chrome here")
    film = [scene(1, "Larangan baharu di ASEAN", ["Malaysia dan Singapura menyelaras kawalan", "Berkuat kuasa 1 Januari 2027"]),
            scene(2, "Ramai terkesan", ["35% pengguna salah baca label", "3 daripada 10 produk gagal"]),
            scene(3, "Kes meningkat", ["2022: 120 kes", "2023: 180 kes", "2024: 260 kes"]),
            scene(4, "Kos tindakan", ["Denda RM 25,000 untuk individu", "Denda RM 50,000 untuk syarikat"])]
    for (w, h) in ((1080, 1920), (1080, 1350), (1920, 1080)):
        motion_auto.assign_photos(film, [{"path": "p.jpg", "credit": "x"}] * 3)
        scenes = [dict(s) for s in film] + [{"id": "brand-outro", "start": 28, "duration": 3, "heading": "x"}]
        args = _args(w=w, h=h) | {"total": 31}
        plan = motion_layout.styled(NEWS_ROW, scenes, voiced=False, lang="bm", stream="regulab", compose_args=args)
        html, rep = motion_layout.compose(scenes=scenes, plan=plan, **args)
        folder = tmp_path / f"{w}x{h}"
        folder.mkdir()
        (folder / "index.html").write_text(html)
        Image.new("RGB", (60, 60), "#234").save(folder / "p.jpg")
        found = [f for f in motion_probe.overlaps(folder, w, h, 31) if f["code"] != "probe_unavailable"]
        shutil.rmtree(folder, ignore_errors=True)
        assert not found, (w, h, rep["visual"], found)
