from datetime import UTC, datetime

import pytest
from fakestore import FakeStore

from semasa import ideas
from semasa.config import LLMSettings
from semasa.llm import LLM

BRAND = {
    "regulab": {"slots": ["08:00", "13:00", "21:00"],
                "schedule": {"0": ["halal_my", "fatwa"], "1": ["kosmetik", "sains_kosmetik"], "2": ["halal_my", "fatwa"],
                             "3": ["kosmetik", "kajian_kes"], "4": ["farmaseutikal", "makanan"],
                             "5": ["kosmetik", "sains_kosmetik"], "6": []}},
    "linkedin": {"slots": ["06:00", "19:00"], "days": [1, 3, 5], "angles": {"A": "Regulatory change"}},
}
NOW = datetime(2026, 9, 24, 2, 0, tzinfo=UTC)            # Thursday 24 Sep, 10:00 MYT


def test_parse_article_reads_og_tags_and_paragraphs():
    html = """<html><head><meta property="og:title" content="NPRA batal notifikasi">
    <meta property="og:image" content="/img/a.jpg"><meta name="description" content="Ringkasan"></head>
    <body><nav><p>menu menu menu menu menu menu menu menu menu menu menu menu menu menu menu</p></nav>
    <article><p>Kementerian Kesihatan Malaysia hari ini membatalkan notifikasi tiga produk kosmetik yang dikesan.</p>
    <p>pendek</p></article></body></html>"""
    out = ideas.parse_article(html, "https://berita.my/a/b")
    assert out["ok"] and out["title"] == "NPRA batal notifikasi"
    assert out["image"] == "https://berita.my/img/a.jpg" and out["description"] == "Ringkasan"
    assert "membatalkan notifikasi" in out["text"] and "menu" not in out["text"] and "pendek" not in out["text"]


def test_google_news_links_are_not_pretended_read():
    out = ideas.read_source("https://news.google.com/rss/articles/CBMi123")
    assert out["ok"] is False and "Google News" in out["why"]
    assert ideas.read_source(None)["ok"] is False


def test_normalise_text_forces_lang_outer_platform_inner():
    flat = ideas.normalise_text({"instagram": "a", "facebook": "b", "threads": "c"}, "regulab", "bm")
    assert flat == {"bm": {"instagram": "a", "facebook": "b", "threads": "c"}}
    # Studio's 19 Sep bug: a BM caption nested under en.bm is dropped, not kept where nothing reads it
    mis = ideas.normalise_text({"en": {"linkedin": "x", "bm": "y"}}, "linkedin", "en")
    assert mis == {"en": {"linkedin": "x"}}
    assert ideas.normalise_text({"en": "x", "bm": "y"}, "linkedin", "en") == {"en": {"linkedin": "x"}, "bm": {"linkedin": "y"}}
    assert ideas.normalise_text("nope", "regulab", "bm") == {}


def test_next_free_position_follows_rota_slots_and_taken():
    # tomorrow is Fri 25 Sep: kosmetik day
    assert ideas.next_free_position("regulab", "kosmetik", BRAND, set(), NOW) == ("2026-09-25", "08:00")
    taken = {("2026-09-25", "08:00"), ("2026-09-25", "13:00")}
    assert ideas.next_free_position("regulab", "kosmetik", BRAND, taken, NOW) == ("2026-09-25", "21:00")
    # halal: Fri no, Sat is a no-posting day, Sun yes
    assert ideas.next_free_position("regulab", "halal_my", BRAND, set(), NOW) == ("2026-09-27", "08:00")
    # no domain: first posting day, skipping Saturday's empty rota
    full = {("2026-09-25", s) for s in ("08:00", "13:00", "21:00")}
    assert ideas.next_free_position("regulab", None, BRAND, full, NOW) == ("2026-09-27", "08:00")
    # linkedin: Mon/Wed/Fri only
    assert ideas.next_free_position("linkedin", None, BRAND, {("2026-09-25", "06:00")}, NOW) == ("2026-09-25", "19:00")


def test_media_jobs_own_refs_then_page_picture_then_words():
    idea = {"id": "i1", "created_by": "u", "make_media": "image", "reference_urls": ["https://r/own.png"]}
    out = {"visual_prompt": "a lab bench", "alt": "meja makmal"}
    jobs = ideas.media_jobs(idea, {"image": "https://news/p.jpg"}, out, "p1")
    assert len(jobs) == 1 and jobs[0]["reference_url"] == "https://r/own.png" and jobs[0]["meta"]["flow"] == "A-own"
    idea["reference_urls"] = []
    jobs = ideas.media_jobs(idea, {"image": "https://news/p.jpg"}, out, "p1")
    assert jobs[0]["mode"] == "recreate" and jobs[0]["meta"]["flow"] == "A" and jobs[0]["post_id"] == "p1"
    jobs = ideas.media_jobs(idea, {"image": None}, out, "p1")
    assert jobs[0]["mode"] == "prompt" and jobs[0]["prompt"] == "a lab bench"
    idea["make_media"] = "none"
    assert ideas.media_jobs(idea, {"image": "x"}, out, "p1") == []


class FakeLLM(LLM):
    def __init__(self, answer):
        super().__init__(LLMSettings(provider="openai", api_key="k", base_url="https://x/v1", model="m", timeout=5))
        self.answer, self.seen = answer, []

    def chat_json(self, system, user, **kw):
        self.seen.append((system, user))
        return self.answer


def _store():
    return FakeStore(semasa_settings=[{"key": "brand", "value": BRAND}, {"key": "publishing", "value": {"enabled": False}}],
                     semasa_posts=[], media_generations=[], semasa_ideas=[])


def test_process_idea_writes_a_scanned_draft_and_queues_media(monkeypatch):
    monkeypatch.setattr(ideas, "read_source", lambda url: {"ok": False, "why": "no link", "image": None})
    store = _store()
    cap = "Notifikasi kosmetik bukan kelulusan. Hubungi kami."
    llm = FakeLLM({"fit": True, "hook": "h", "domain": "kosmetik", "citation": "NPRA",
                   "text": {"bm": {"instagram": cap, "facebook": cap, "threads": cap}},
                   "visual_prompt": "botol di rak", "alt": "botol"})
    idea = {"id": "i1", "stream": "regulab", "source_title": "T", "created_by": "u", "make_media": "image"}
    store.tables["semasa_ideas"].append({**idea, "status": "working"})
    pid = ideas.process_idea(store, llm, idea, ideas.load_settings(store))
    post = store.tables["semasa_posts"][0]
    assert post["id"] == pid and post["status"] == "draft" and post["domain"] == "kosmetik"
    assert post["hard_flags"] >= 1 and any("hubungi kami" in f["msg"] for f in post["flags"])
    assert post["date"] and post["slot"]
    assert store.tables["media_generations"][0]["mode"] == "prompt"
    assert store.tables["semasa_ideas"][0]["status"] == "drafted"
    assert "only the headline and summary" in llm.seen[0][1]         # the writer is told it has no article


def test_unfit_idea_and_missing_key_are_errors_with_a_reason(monkeypatch):
    monkeypatch.setattr(ideas, "read_source", lambda url: {"ok": False, "why": "x", "image": None})
    store = _store()
    with pytest.raises(ideas.IdeaError, match="no fit"):
        ideas.process_idea(store, FakeLLM({"fit": False, "why_not": "sukan"}), {"id": "i", "stream": "regulab"}, {})
    nokey = FakeLLM({})
    nokey.s = LLMSettings(provider="openai", api_key=None, base_url="https://x/v1", model="m", timeout=5)
    with pytest.raises(ideas.IdeaError, match="LLM_API_KEY"):
        ideas.process_idea(store, nokey, {"id": "i", "stream": "regulab"}, {})


def test_run_records_errors_on_the_idea_and_claims_once(monkeypatch):
    monkeypatch.setattr(ideas, "read_source", lambda url: {"ok": False, "why": "x", "image": None})
    store = _store()
    store.tables["semasa_ideas"] = [{"id": "a", "status": "new", "stream": "regulab", "created_at": "1", "attempts": 0}]
    note = ideas.run(store, FakeLLM(None))
    row = store.tables["semasa_ideas"][0]
    assert row["status"] == "error" and "did not answer" in row["error"] and row["attempts"] == 1
    assert "0/1" in note
    assert ideas.run(store, FakeLLM(None)) == "Ideas: none waiting"


def test_the_tabung_reaches_the_writer_and_the_scan(monkeypatch):
    monkeypatch.setattr(ideas, "read_source", lambda url: {"ok": False, "why": "x", "image": None})
    store = _store()
    cap = "Kilang boleh memakai bahan ini dengan selamat."
    text = {"bm": {"instagram": cap, "facebook": cap, "threads": cap}}
    llm = FakeLLM({"fit": True, "hook": "h", "citation": "NPRA", "text": text})
    settings = {**ideas.load_settings(store), "bahasa": {"indo": [{"indo": "memakai", "bm": "menggunakan"}]}}
    ideas.process_idea(store, llm, {"id": "i1", "stream": "regulab", "make_media": "none"}, settings)
    assert '"memakai" (write "menggunakan")' in llm.seen[0][0]
    post = store.tables["semasa_posts"][0]
    assert any("memakai" in f["msg"] and f["hard"] for f in post["flags"])
