"""Regulatory and Latest publication: the regulators' own pages parsed as they were on 26 Sep 2026 (fixtures cut from
the live pages), PubMed read through its API, the writer's verdicts kept, and the sweep run once every 24 hours."""

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from fakestore import FakeStore

from semasa import ideas, watch

FIX = Path(__file__).parent / "fixtures" / "watch"
TODAY = date(2026, 9, 26)


def _parse(name, i):
    src = watch.SOURCES[i]
    return src.parse((FIX / name).read_text(encoding="utf-8"), src.url, TODAY)


def test_npra_notices_are_read_with_their_dates_and_kinds_and_menus_are_not():
    got = _parse("npra.html", 0)
    by = {g["title"][:40]: g for g in got}
    assert all(g["url"].startswith("https://www.npra.gov.my/") and "?" not in g["url"] for g in got)
    assert not any("Cancellation of Notified Cosmetic Products" == g["title"] for g in got)       # a menu link
    kmk = next(g for g in got if g["title"].startswith("Kenyataan Media KKM 24 Ogos 2026"))
    assert kmk["published_at"] == date(2026, 8, 24) and kmk["kind"] == "Kenyataan Media KKM"
    dirs = [g for g in got if g["title"].startswith("Direktif Pelaksanaan dan Pengendalian Label Keselamatan")]
    assert len(dirs) == 1 and dirs[0]["kind"] == "Directive" and dirs[0]["published_at"] == date(2026, 9, 18)  # linked twice
    assert not any("Veterinary" in g["title"] or g["title"] == "New Products Approved" for g in got)
    assert any(g["kind"] == "Safety alert" for g in got) and all(g["published_at"] for g in got)
    assert len(by) == len(got)


def test_a_day_and_month_with_no_year_never_lands_in_the_future():
    html = ('<div class="sppb-addon-article"><span class="sppb-meta-date">20</span><span class="sppb-meta-month">Dec</span>'
            '<h3><a href="/index.php/en/some-news/1234567-a-notice-about-labels.html">'
            'A notice about cosmetic labels</a></h3></div>')
    [g] = watch.parse_npra(html, watch.SOURCES[0].url, TODAY)
    assert g["published_at"] == date(2025, 12, 20)


def test_the_halal_portal_tells_apart_items_sharing_one_address():
    got = _parse("halal.html", 1)
    assert got[0]["title"].startswith("MEDIA STATEMENT - ANNOUNCEMENT RECALL") and got[0]["published_at"] == date(2025, 4, 24)
    assert got[0]["kind"] == "Announcement" and "chevron_right" not in got[0]["title"]
    assert len({g["url"] for g in got}) == len(got)                        # shared content_id made unique
    assert not any("Foreign Halal Certification Body" == g["title"] for g in got)


def test_hsa_sgs_eu_uk_and_china_pages():
    hsa = _parse("hsa.html", 2)
    assert hsa and hsa[0]["published_at"] == date(2026, 9, 25) and not hsa[0]["title"].startswith("25 September")
    assert "Audiences" not in hsa[0]["title"]
    sccs = _parse("sccs.html", 3)
    ace = next(g for g in sccs if "Acetophenone" in g["title"])
    assert ace["ref"] == "SCCS/1689/26" and ace["published_at"] == date(2026, 4, 30)
    opss = _parse("opss.atom", 4)
    assert any("cosmetic" in g["title"].lower() for g in opss) and all(g["published_at"] for g in opss)
    nmpa = _parse("nmpa.html", 5)
    assert nmpa[0]["published_at"].year >= 2019 and nmpa[0]["url"].startswith("https://english.nmpa.gov.cn/")


def test_malay_and_english_dates_in_words():
    assert watch.date_in_words("Kenyataan Media KKM 24 Ogos 2026- Makluman") == date(2026, 8, 24)
    assert watch.date_in_words("SCCS/1688/26 - 26 March 2026") == date(2026, 3, 26)
    assert watch.date_in_words("2 Disember 2025") == date(2025, 12, 2)
    assert watch.date_in_words("no date here") is None


ESEARCH = {"esearchresult": {"idlist": ["111", "222"]}}
ESUMMARY = {"result": {"uids": ["111", "222"],
                       "111": {"title": "Permeation of cosmetic actives into the stratum corneum.",
                               "fulljournalname": "Int J Pharm",
                               "sortpubdate": "2026/09/23 00:00", "authors": [{"name": "Tan A"}, {"name": "Lee B"}],
                               "articleids": [{"idtype": "doi", "value": "10.1016/j.ijpharm.2026.127447"}]},
                       "222": {"title": "", "fulljournalname": "X"}}}
EFETCH = """<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>111</PMID><Article><Abstract>
<AbstractText Label="BACKGROUND">Actives cross the skin.</AbstractText><AbstractText Label="RESULTS">Depth varied.</AbstractText>
</Abstract></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>"""


def test_pubmed_papers_come_with_journal_doi_and_abstract(monkeypatch):
    calls = []

    def get(url, timeout):
        calls.append(url)
        if "esearch" in url:
            return json.dumps(ESEARCH)
        if "esummary" in url:
            return json.dumps(ESUMMARY)
        return EFETCH
    monkeypatch.setattr(watch, "_get", get)
    items, report = watch.pubmed()
    assert len(items) == 1                                                 # a paper with no title is dropped
    p = items[0]
    assert p["url"] == "https://pubmed.ncbi.nlm.nih.gov/111/" and p["published_at"] == date(2026, 9, 23)
    assert p["raw"]["doi"] == "10.1016/j.ijpharm.2026.127447" and p["source"] == "PubMed · Int J Pharm"
    assert p["snippet"] == "BACKGROUND: Actives cross the skin. RESULTS: Depth varied."
    assert len(report) == len(watch.PUBMED_QUERIES) and all(r["ok"] for r in report)
    assert all("tool=semasa" in u for u in calls) and not any("email" in u for u in calls)


class Writer:
    configured = True

    def __init__(self):
        self.seen = []

    def chat_json(self, system, user, max_tokens=0, **k):
        self.seen.append(user)
        items = [json.loads(line) for line in user.split("\n")[1:]]
        return {"items": [{"i": it["i"], "relevant": "Gates" not in it["title"], "domain": "kosmetik",
                           "summary": f"Ringkasan {it['i']}", "why": "Semak label anda."} for it in items]}


def _collected(monkeypatch):
    rows = [{"section": "regulatory", "source": "NPRA", "title": "Kenyataan Media KKM 24 Ogos 2026", "url": "https://n/1",
             "published_at": date(2026, 8, 24), "kind": "Kenyataan Media KKM", "country": "MY", "lang": "en"},
            {"section": "regulatory", "source": "China NMPA", "title": "Huang Guo meets with Gates Foundation", "url": "https://n/2",
             "published_at": date(2026, 9, 23), "kind": "News", "country": "CN", "lang": "en"},
            {"section": "publication", "source": "PubMed · Int J Pharm", "title": "Paper", "url": "https://p/111",
             "published_at": date(2026, 9, 23), "kind": "Paper", "snippet": "abstract", "domain": "sains_kosmetik",
             "raw": {"doi": "10.1/x"}}]
    monkeypatch.setattr(watch, "collect", lambda timeout=30: ([dict(r) for r in rows], [{"name": "NPRA", "ok": True}]))


def test_a_sweep_stores_new_items_once_with_the_writers_verdicts(monkeypatch):
    _collected(monkeypatch)
    store = FakeStore(semasa_watch=[{"url": "https://n/1", "title": "old"}], semasa_settings=[], semasa_log=[])
    w = Writer()
    res = watch.sweep(store, w)
    assert res["new"] == 2 and res["by_section"] == {"regulatory": 1, "publication": 1}
    rows = {r["url"]: r for r in store.tables["semasa_watch"]}
    assert rows["https://n/1"]["title"] == "old"                            # already stored: untouched
    assert rows["https://n/2"]["relevant"] is False and rows["https://n/2"]["summary_source"] == "llm"
    paper = rows["https://p/111"]
    assert paper["raw"] == {"doi": "10.1/x", "abstract": "abstract"} and paper["published_at"] == "2026-09-23"


def test_the_sweep_runs_once_a_day_or_when_asked(monkeypatch):
    _collected(monkeypatch)
    store = FakeStore(semasa_watch=[], semasa_settings=[], semasa_log=[])
    now = datetime(2026, 9, 26, 23, 20, tzinfo=UTC)
    assert "new" in watch.run_if_due(store, Writer(), now=now)             # never ran: it runs, and makes its row
    v = next(r for r in store.tables["semasa_settings"] if r["key"] == "watch")["value"]
    assert v["last_run"] == now.isoformat() and v["force"] is False and v["result"]["new"] == 3
    assert "next sweep" in watch.run_if_due(store, Writer(), now=now + timedelta(hours=8))
    assert watch.run_if_due(store, Writer(), now=now + timedelta(hours=8), only_forced=True) == ""
    next(r for r in store.tables["semasa_settings"] if r["key"] == "watch")["value"]["force"] = True
    assert "new" in watch.run_if_due(store, Writer(), now=now + timedelta(hours=9), only_forced=True)
    assert "new" in watch.run_if_due(store, Writer(), now=now + timedelta(hours=33))


def test_no_table_yet_is_a_line_not_a_crash():
    class Broken:
        def table(self, name):
            raise RuntimeError("relation does not exist")
    assert "012_watch.sql" in watch.run_if_due(Broken(), None)


def test_an_idea_from_a_regulator_cites_the_regulator_and_a_news_idea_hides_its_portal():
    src = {"ok": True, "text": "notice text"}
    _, reg = ideas.build_request({"source_title": "Kenyataan Media KKM", "source_name": "NPRA"}, src, {})
    _, news = ideas.build_request({"source_title": "Berita", "source_name": "Berita Harian"}, src, {})
    _, paper = ideas.build_request({"source_title": "Paper", "source_name": "PubMed · Int J Pharm"}, src, {})
    assert "ISSUER: NPRA" in reg and "cite it by name" in reg and "never name it" not in reg
    assert "PUBLISHER: Berita Harian" in news and "never name it in the post" in news
    assert "ISSUER: PubMed" in paper


def test_an_idea_can_ask_for_a_carousel_or_a_poster():
    assert ideas.format_of({"make_slides": True}) == "carousel"
    assert ideas.format_of({"brief": {"format": "poster"}}) == "poster"
    assert ideas.format_of({"brief": {"format": "nonsense"}}) == "post"
    job = ideas.poster_job({"id": "i1", "brief": {"look": "grid"}}, {"stream": "regulab", "citation": "NPRA"}, "p1",
                           [{"title": "T", "points": ["a"]}])
    assert job["meta"]["design"] == "poster" and job["meta"]["format"] == "portrait" and job["meta"]["look"] == "grid"
    assert job["post_id"] == "p1" and job["mode"] == "slides"


@pytest.mark.parametrize("q", [q for _, q in watch.PUBMED_QUERIES])
def test_pubmed_queries_are_balanced(q):
    assert q.count("(") == q.count(")") and q.count('"') % 2 == 0


# --- a pasted link ---------------------------------------------------------------------------------------------------

class Resp:
    def __init__(self, text="", status=200, ctype="text/html", url="", content=None):
        self.text, self.status_code, self.url = text, status, url
        self.headers = {"content-type": ctype}
        self.content = content if content is not None else text.encode()


def _pdf(text: str) -> bytes:
    """A one-page PDF carrying `text`, built by hand (pypdf rebuilds the cross-reference table itself)."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offs = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 6\n0000000000 65535 f \n" + b"".join(b"%010d 00000 n \n" % o for o in offs)
    return out + b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % xref


def test_who_issued_a_pasted_page():
    assert watch.issuer_of("https://www.npra.gov.my/index.php/en/x.html") == ("NPRA", "MY")
    assert watch.issuer_of("https://sites.google.com/islam.gov.my/skkbph/isu-isu-tular-halal") == ("JAKIM", "MY")
    assert watch.issuer_of("https://www.legislation.gov.uk/uksi/2026/109") == ("legislation.gov.uk", "UK")
    assert watch.issuer_of("https://eur-lex.europa.eu/eli/reg/2009/1223") == ("EUR-Lex", "EU")
    assert watch.issuer_of("https://www.thestar.com.my/news") is None
    assert watch.is_issuer("NPRA") and watch.is_issuer("Paper · Int J Cosmet Sci") and not watch.is_issuer("The Star")


def test_a_pubmed_or_doi_link_becomes_the_pubmed_record(monkeypatch):
    seen = []

    def get(url, timeout):
        seen.append(url)
        if "esearch" in url:
            return json.dumps({"esearchresult": {"idlist": ["111"]}})
        return json.dumps(ESUMMARY) if "esummary" in url else EFETCH
    monkeypatch.setattr(watch, "_get", get)
    monkeypatch.setattr(watch, "EUTILS_GAP", 0)
    p = watch.resolve({"url": "https://pubmed.ncbi.nlm.nih.gov/111/", "section": "publication"})
    assert p["source"] == "PubMed · Int J Pharm" and p["raw"]["abstract"].startswith("BACKGROUND")
    seen.clear()
    d = watch.resolve({"url": "https://doi.org/10.1016/j.ijpharm.2026.127447", "section": "publication"})
    assert "10.1016%2Fj.ijpharm.2026.127447%5Bdoi%5D" in seen[0] and d["raw"]["pmid"] == "111"


JOURNAL = """<html><head><title>x</title>
<meta name="citation_title" content="Niacinamide stability in emulsions">
<meta name="citation_journal_title" content="Cosmetics"><meta name="citation_doi" content="10.3390/cosmetics1301">
<meta name="citation_author" content="Tan, A"><meta name="citation_author" content="Lee, B">
<meta name="citation_publication_date" content="2026/09/20">
<meta name="citation_abstract" content="We measured niacinamide over 12 weeks."></head><body><p>x</p></body></html>"""
NOTICE = """<html><head><meta property="og:title" content="Kenyataan Media: Kosmetik Mengandungi Racun Berjadual"></head>
<body><article><p>Kementerian Kesihatan Malaysia memaklumkan produk kosmetik berikut telah dibatalkan notifikasi
pada 24 Ogos 2026 kerana dikesan mengandungi racun berjadual.</p></article></body></html>"""


def test_a_journal_page_a_notice_and_a_pdf(monkeypatch):
    pages = {"https://www.mdpi.com/2079-9284/13/1/1": Resp(JOURNAL, url="https://www.mdpi.com/2079-9284/13/1/1"),
             "https://www.npra.gov.my/index.php/en/x.html": Resp(NOTICE, url="https://www.npra.gov.my/index.php/en/x.html"),
             "https://www.npra.gov.my/images/a.pdf": Resp(ctype="application/pdf", url="https://www.npra.gov.my/images/a.pdf",
                                                          content=_pdf("Direktif Label Keselamatan 18 September 2026"))}
    monkeypatch.setattr(watch.fetch, "get", lambda url, timeout=25, retries=2: pages[url])
    monkeypatch.setattr(watch, "pmid_for_doi", lambda doi, timeout=30: pytest.fail("no DOI in this link"))
    j = watch.resolve({"url": "https://www.mdpi.com/2079-9284/13/1/1", "section": "publication"})
    assert j["source"] == "Paper · Cosmetics" and j["kind"] == "Paper" and j["published_at"] == date(2026, 9, 20)
    assert j["raw"]["doi"] == "10.3390/cosmetics1301" and j["raw"]["authors"] == ["Tan, A", "Lee, B"]
    n = watch.resolve({"url": "https://www.npra.gov.my/index.php/en/x.html", "section": "regulatory"})
    assert n["source"] == "NPRA" and n["country"] == "MY" and n["published_at"] == date(2026, 8, 24)
    assert n["title"].startswith("Kenyataan Media") and "racun berjadual" in n["snippet"]
    f = watch.resolve({"url": "https://www.npra.gov.my/images/a.pdf", "section": "regulatory"})
    assert f["kind"] == "PDF" and "Direktif Label Keselamatan" in f["title"] and f["published_at"] == date(2026, 9, 18)


def test_a_site_that_refuses_says_what_to_paste_instead(monkeypatch):
    import requests

    def refuse(url, timeout=25, retries=2):
        raise requests.HTTPError("403", response=Resp(status=403))
    monkeypatch.setattr(watch.fetch, "get", refuse)
    with pytest.raises(watch.PasteError, match="PubMed link or DOI"):
        watch.resolve({"url": "https://onlinelibrary.wiley.com/doi/abs/x", "section": "publication"})
    with pytest.raises(watch.PasteError, match="http"):
        watch.resolve({"url": "npra.gov.my", "section": "regulatory"})


def test_pasted_links_are_read_once_named_by_wan_and_never_hidden(monkeypatch):
    rows = [{"id": "a", "section": "regulatory", "url": "https://www.npra.gov.my/n", "title": "https://www.npra.gov.my/n",
             "status": "pending", "attempts": 0, "pasted": True, "created_at": "2026-09-26T10:00:00Z"},
            {"id": "b", "section": "regulatory", "url": "https://x.example/bad", "title": "Label rule (mine)",
             "status": "pending", "attempts": 0, "pasted": True, "created_at": "2026-09-26T10:01:00Z"},
            {"id": "c", "section": "publication", "url": "https://y.example", "title": "old", "status": "ready"}]
    store = FakeStore(semasa_watch=rows, semasa_log=[])

    def resolve(row, timeout=30):
        if "bad" in row["url"]:
            raise watch.PasteError("the site refused GitHub's machine (403)")
        return {"title": "Kenyataan Media KKM", "source": "NPRA", "kind": "Notice", "country": "MY", "lang": "en",
                "published_at": date(2026, 9, 25), "snippet": "teks notis", "raw": {"final_url": row["url"]}}
    monkeypatch.setattr(watch, "resolve", resolve)

    class Picky(Writer):
        def chat_json(self, system, user, max_tokens=0, **k):
            out = super().chat_json(system, user, max_tokens)
            for it in out["items"]:
                it["relevant"] = False                      # the writer would hide it; Wan's paste is shown anyway
            return out
    note = watch.process_pasted(store, Picky())
    a, b, c = (next(r for r in store.tables["semasa_watch"] if r["id"] == i) for i in "abc")
    assert note == "Pasted links: 1 read, 1 failed"
    assert a["status"] == "ready" and a["relevant"] is True and a["title"] == "Kenyataan Media KKM" and a["source"] == "NPRA"
    assert a["summary_source"] == "llm" and a["published_at"] == "2026-09-25" and a["attempts"] == 1
    assert b["status"] == "error" and "403" in b["error"] and b["title"] == "Label rule (mine)"
    assert c["status"] == "ready" and c["title"] == "old"
    assert watch.process_pasted(store, Picky()) == ""       # nothing left waiting


def test_paste_before_013_is_a_line_not_a_crash():
    class Broken:
        def table(self, name):
            raise RuntimeError('column "status" does not exist')
    assert "013_watch_paste.sql" in watch.process_pasted(Broken(), None)


def test_an_idea_made_from_a_pasted_pdf_reads_the_pdf(monkeypatch):
    pdf = Resp(ctype="application/pdf", url="https://www.npra.gov.my/a.pdf", content=_pdf("Direktif Label Keselamatan 2026"))
    monkeypatch.setattr(ideas, "get", lambda url, timeout=20, retries=1: pdf)
    src = ideas.read_source("https://www.npra.gov.my/a.pdf")
    assert src["ok"] and "Direktif Label Keselamatan" in src["text"]
