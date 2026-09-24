from datetime import UTC, datetime

from semasa.sources import SOURCES, Source, clean_url, parse_html, parse_rss, parse_trends, strip_gnews_suffix

BH = next(s for s in SOURCES if s.name == "Berita Harian")
GN = next(s for s in SOURCES if s.name == "Google News MY (BM)")
TR = next(s for s in SOURCES if s.name == "Google Trends MY")
AW = next(s for s in SOURCES if s.name == "Astro Awani")


def test_registry_shape():
    assert all(s.kind in ("rss", "trends", "html") for s in SOURCES)
    assert len({s.url for s in SOURCES}) == len(SOURCES)


def test_clean_url_strips_tracking_only():
    assert clean_url("https://a.my/x?utm_source=rss&id=3&fbclid=9#top") == "https://a.my/x?id=3"
    assert clean_url("https://a.my/x") == "https://a.my/x"


def test_rss_bharian(fixture):
    items = parse_rss(BH, fixture("bharian.xml"))
    assert len(items) == 3
    first = items[0]
    assert first.title == "2 pelajar didakwa di mahkamah kes buli di sekolah"
    assert first.url.endswith("/2-pelajar-didakwa-di-mahkamah-kes-buli-di-sekolah")  # utm stripped
    assert first.source == "Berita Harian"
    assert first.published_at == datetime(2026, 9, 23, 22, 0, 26, tzinfo=UTC)
    assert first.snippet.startswith("PAPAR: Dua pelajar")
    assert "Kes" in first.tags


def test_rss_google_news_uses_publisher_and_drops_suffix(fixture):
    items = parse_rss(GN, fixture("gnews.xml"))
    assert [i.source for i in items] == ["Sinar Harian", "astroawani.com"]
    assert items[0].title == "'Anthony Loke betul mahu berhenti atau drama?' - Fadhli Shaari | Sinar Harian"
    assert items[1].title == "SUK, penasihat undang-undang NS jalankan tugas selaras arahan KSN dan AGC"
    assert items[0].snippet is None  # Google's description is a link list, not a summary
    assert "aggregator" in items[0].tags


def test_strip_gnews_suffix_without_publisher():
    assert strip_gnews_suffix("Tajuk berita - Kosmo Online", None) == "Tajuk berita"
    assert strip_gnews_suffix("A - B - C", None) == "A - B - C"


def test_trends(fixture):
    items = parse_trends(TR, fixture("trends.xml"))
    assert len(items) == 3
    assert items[0].title == "PN sudah terima notis RoS?"
    assert items[0].source == "MalaysiaGazette"
    assert "carian:perikatan nasional" in items[0].tags and "trafik:1000+" in items[0].tags
    assert items[0].published_at.tzinfo is not None
    assert items[2].source == "Harian Metro"


def test_html_generic_headlines(fixture):
    items = parse_html(AW, fixture("awani.html"))
    titles = [i.title for i in items]
    assert titles == [
        "Anthony Loke tetap mahu letak jawatan, serah surat selepas pulang dari China",
        "Kes tikam pelajar: Skizofrenia remaja tidak dirawat selama 5 tahun sebelum insiden - Mahkamah",
        "Digilis lori: Murid Tahun Empat maut selepas 24 jam bertarung nyawa",
    ]
    # absolute+utm and relative forms of the same story collapse to one URL
    assert len({i.url for i in items}) == 3
    assert all(i.url.startswith("https://www.astroawani.com/berita-") for i in items)


def test_html_respects_skip_paths():
    src = Source("X", "html", "https://x.my/", skip_paths=("/promo",))
    text = "Tajuk yang cukup panjang untuk lulus saringan ini"
    html = f'<a href="/promo/tajuk-yang-cukup-panjang-untuk-lulus-saringan-ini">{text}</a>'
    assert parse_html(src, html) == []
