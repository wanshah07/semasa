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


def test_an_idea_from_the_faq_is_written_from_its_answer(monkeypatch):
    from semasa import ideas as ideas_mod
    monkeypatch.setattr(ideas_mod, "read_source", lambda url: pytest.fail("an FAQ has no page to read"))
    idea = {"id": "i9", "stream": "regulab", "source_name": "FAQ Semasa", "source_url": None,
            "source_title": "Bolehkah pemegang sijil halal menyembunyikan nama pengilang OEM?",
            "source_summary": "Tidak. Nama dan alamat pengilang OEM tetap dipaparkan.\n\nSumber: JAKIM"}
    src = ideas_mod.faq_source(idea)
    assert src["ok"] and "tetap dipaparkan" in src["text"]
    system, user = ideas_mod.build_request(idea, src, {})
    assert "SOURCE (an entry of Wan's own FAQ)" in user and "only the headline" not in user
    assert ideas_mod.faq_source({**idea, "source_name": "Berita Harian"}) is None


def test_a_retry_after_a_failure_part_way_finishes_the_same_draft(monkeypatch):
    # the media insert failed after the draft was written: "Cuba lagi" wrote a second draft on a second slot
    monkeypatch.setattr(ideas, "read_source", lambda url: {"ok": False, "why": "no link", "image": None})
    store = _store()
    cap = "Notifikasi kosmetik bukan kelulusan produk."
    llm = FakeLLM({"fit": True, "hook": "h", "domain": "kosmetik", "citation": "NPRA",
                   "text": {"bm": {"instagram": cap, "facebook": cap, "threads": cap}},
                   "visual_prompt": "botol di rak", "alt": "botol"})
    idea = {"id": "i1", "stream": "regulab", "source_title": "T", "created_by": "u", "make_media": "image"}
    store.tables["semasa_ideas"].append({**idea, "status": "working"})
    real_insert = store.table("media_generations").__class__.insert
    fail = {"on": True}

    def flaky(self, payload):
        if self.table == "media_generations" and fail["on"]:
            raise RuntimeError("502 Bad Gateway")
        return real_insert(self, payload)
    monkeypatch.setattr(store.table("media_generations").__class__, "insert", flaky)
    with pytest.raises(RuntimeError):
        ideas.process_idea(store, llm, idea, ideas.load_settings(store))
    fail["on"] = False
    again = {**idea, "brief": store.tables["semasa_ideas"][0].get("brief")}
    pid = ideas.process_idea(store, llm, again, ideas.load_settings(store))
    assert len(store.tables["semasa_posts"]) == 1 and store.tables["semasa_posts"][0]["id"] == pid
    assert len(store.tables["media_generations"]) == 1
    assert store.tables["semasa_ideas"][0]["status"] == "drafted"


def test_a_retry_whose_draft_already_has_jobs_does_not_pay_the_writer_again(monkeypatch):
    # review 27 Sep 2026: writing again overwrote the post's slides while the queued slide job kept the old ones
    monkeypatch.setattr(ideas, "read_source", lambda url: {"ok": False, "why": "x", "image": None})
    store = _store()
    store.tables["semasa_posts"].append({"id": "p1", "status": "draft", "slides": [{"title": "old", "points": []}]})
    store.tables["media_generations"].append({"id": "m1", "post_id": "p1", "mode": "slides", "status": "pending"})
    idea = {"id": "i1", "stream": "regulab", "brief": {"partial_post_id": "p1"}, "make_media": "image"}
    store.tables["semasa_ideas"].append({**idea, "status": "working"})
    llm = FakeLLM({"fit": True})
    assert ideas.process_idea(store, llm, idea, ideas.load_settings(store)) == "p1"
    assert llm.seen == [] and len(store.tables["semasa_posts"]) == 1
    assert store.tables["semasa_posts"][0]["slides"] == [{"title": "old", "points": []}]
    got = store.tables["semasa_ideas"][0]
    assert got["status"] == "drafted" and got["brief"]["post_id"] == "p1" and "partial_post_id" not in got["brief"]


def _revise_store(**post):
    store = _store()
    cap = "Notifikasi kosmetik ialah pemberitahuan kepada NPRA, bukan kelulusan produk."
    row = {"id": "p1", "stream": "regulab", "lang": "bm", "status": "draft", "domain": "kosmetik", "hook": "Lama",
           "citation": "NPRA, Garis Panduan Kawalan Kosmetik",
           "text": {"bm": {"instagram": cap, "facebook": cap, "threads": cap}},
           "slides": [{"title": "Kekal", "points": [], "template": "g_title"}], "media_ids": [],
           "revise_state": "new", "revise_note": "Pendekkan, mula dengan kesilapan biasa", "versions": [], "decisions": [],
           "updated_at": "2026-09-24T00:00:00+00:00", **post}
    store.tables["semasa_posts"].append(row)
    return store


def test_revise_rewrites_the_words_keeps_slides_and_history():
    store = _revise_store()
    new = "Ramai sangka notifikasi itu kelulusan. Ia hanya pemberitahuan kepada NPRA."
    llm = FakeLLM({"fit": True, "hook": "Baru", "citation": "NPRA, Garis Panduan Kawalan Kosmetik",
                   "text": {"bm": {"instagram": new, "facebook": new, "threads": new}},
                   "slides": [{"title": "Jangan tukar", "points": []}]})
    assert ideas.revise_posts(store, llm) == "Revise: 1/1 rewritten"
    p = store.tables["semasa_posts"][0]
    assert p["hook"] == "Baru" and p["text"]["bm"]["instagram"] == new
    assert p["slides"] == [{"title": "Kekal", "points": [], "template": "g_title"}]      # designs and pictures kept
    assert p["versions"][0]["hook"] == "Lama" and p["versions"][0]["why"].startswith("Pendekkan")
    assert "slides" not in p["versions"][0]
    assert p["decisions"][-1]["action"] == "revised" and p["decisions"][-1]["by"] == "bot"
    assert p["revise_state"] is None and p["revise_note"] is None and isinstance(p["flags"], list)
    system, user = llm.seen[0]
    assert "Pendekkan, mula dengan kesilapan biasa" in user and "CURRENT CAPTION (bm)" in user
    assert "SLIDES WANTED" not in system
    assert any(r.get("event") == "post.revised" for r in store.tables.get("semasa_log", []))


def test_revise_never_touches_an_approved_post():
    store = _revise_store(status="approved")
    llm = FakeLLM({"fit": True, "hook": "x", "text": {"bm": {"instagram": "y"}}})
    ideas.revise_posts(store, llm)
    p = store.tables["semasa_posts"][0]
    assert p["hook"] == "Lama" and p["revise_state"] == "error" and "only a draft" in p["revise_error"]
    assert llm.seen == []


def test_revise_keeps_the_post_when_the_writer_returns_nothing():
    store = _revise_store()
    ideas.revise_posts(store, FakeLLM({"fit": True, "hook": "x", "text": {"en": {"linkedin": "wrong language"}}}))
    p = store.tables["semasa_posts"][0]
    assert p["hook"] == "Lama" and p["revise_state"] == "error" and "no BM caption" in p["revise_error"]
    assert p["versions"] == []


def test_revise_picks_up_a_stale_claim_and_skips_other_runs_claims():
    store = _revise_store(revise_state="working", updated_at="2026-01-01T00:00:00+00:00")
    fresh = dict(store.tables["semasa_posts"][0], id="p2", revise_state="working",
                 updated_at=datetime.now(UTC).isoformat())
    store.tables["semasa_posts"].append(fresh)
    new = "Ramai sangka notifikasi itu kelulusan. Ia hanya pemberitahuan kepada NPRA."
    ideas.revise_posts(store, FakeLLM({"fit": True, "hook": "Baru", "text": {"bm": {"instagram": new}}}))
    p1, p2 = store.tables["semasa_posts"]
    assert p1["hook"] == "Baru" and p2["hook"] == "Lama" and p2["revise_state"] == "working"


def test_revise_without_021_is_a_quiet_skip():
    class Broken:
        def table(self, name):
            raise RuntimeError('column "revise_state" does not exist')
    assert ideas.revise_posts(Broken(), FakeLLM({})).startswith("Revise: skipped")


def test_a_case_study_takes_any_posting_day():
    # Fri 25 Sep is a kosmetik/sains_kosmetik day, yet a case study still goes there (Studio's e2: one a day)
    assert ideas.next_free_position("regulab", "kajian_kes", BRAND, set(), NOW) == ("2026-09-25", "08:00")
    # but never on a no-posting day (Sat 26 has an empty rota)
    full = {("2026-09-25", s) for s in ("08:00", "13:00", "21:00")}
    assert ideas.next_free_position("regulab", "kajian_kes", BRAND, full, NOW) == ("2026-09-27", "08:00")


def test_a_replacement_keeps_its_slot_and_the_rejected_drafts_pictures(monkeypatch):
    monkeypatch.setattr(ideas, "read_source", lambda url: {"ok": False, "why": "no link", "image": None})
    monkeypatch.setattr(ideas, "datetime", type("D", (), {"now": staticmethod(lambda tz=None: NOW)}))
    store = _store()
    store.tables["media_generations"] += [
        {"id": "m1", "status": "done", "generated_media_url": "https://x/m1.png", "type": "image", "mode": "prompt",
         "meta": {"alt": "Botol di rak"}},
        {"id": "m2", "status": "error", "generated_media_url": None, "type": "image", "mode": "prompt", "meta": {}},
        {"id": "m3", "status": "done", "generated_media_url": "https://x/s.jpg", "type": "image", "mode": "slides", "meta": {}}]
    cap = "Notifikasi kosmetik ialah pemberitahuan kepada NPRA, bukan kelulusan produk."
    llm = FakeLLM({"fit": True, "hook": "h", "domain": "kosmetik", "citation": "NPRA",
                   "text": {"bm": {"instagram": cap, "facebook": cap, "threads": cap}}, "visual_prompt": "x"})
    idea = {"id": "i9", "stream": "regulab", "source_title": "T", "created_by": "u", "make_media": "none",
            "note": "Pengganti draf yang ditolak", "status": "working",
            "brief": {"position": {"date": "2026-09-25", "slot": "13:00"}, "replaces": "old",
                      "keep_media_ids": ["m1", "m2", "m3"]}}
    store.tables["semasa_ideas"].append(idea)
    pid = ideas.process_idea(store, llm, idea, ideas.load_settings(store))
    post = next(p for p in store.tables["semasa_posts"] if p["id"] == pid)
    assert (post["date"], post["slot"]) == ("2026-09-25", "13:00") and post["media_ids"] == ["m1"]
    assert not any(f["msg"] == "instagram needs an image" for f in post["flags"])
    assert len(store.tables["media_generations"]) == 3              # no new picture paid for
    assert store.tables["semasa_ideas"][0]["brief"]["replaces"] == "old"


WRITER = {"regulab": {"voice": "Blunt, warm.", "never": ["Never name a client."], "hashtags_core": ["#NPRA"],
                      "hashtags_rotate": ["#KosmetikMalaysia"], "fatwa_warning": "Keputusan Muzakarah MKI bukan undang-undang.",
                      "pillars": {"kosmetik": ["kajian_kes", "mitos"], "fatwa": ["soal_jawab"]}},
          "linkedin": {"voice": "A named professional."}}


def test_writer_settings_and_pillars_reach_the_writer():
    system, _ = ideas.build_request({"stream": "regulab", "domain": "kosmetik", "source_title": "T"}, {"ok": False}, BRAND,
                                    writer=WRITER)
    assert "Blunt, warm." in system and "Never name a client." in system and "#NPRA" in system
    assert "PILLAR" in system and "mitos = a common belief" in system and "soal_jawab" not in system
    li, _ = ideas.build_request({"stream": "linkedin", "source_title": "T"}, {"ok": False}, BRAND, writer=WRITER)
    assert "A named professional." in li and "PILLAR" not in li and "MKI" not in li
    assert ideas.pillars_for(WRITER, "regulab", None) == ["kajian_kes", "mitos", "soal_jawab"]
    assert ideas.pillar_line({}, "regulab", "kosmetik") == ""


def test_the_writers_pillar_is_kept_only_from_the_list(monkeypatch):
    monkeypatch.setattr(ideas, "read_source", lambda url: {"ok": False, "why": "no link", "image": None})
    cap = "Notifikasi kosmetik ialah pemberitahuan kepada NPRA, bukan kelulusan produk."
    for said, kept in (("mitos", "mitos"), ("invented", None)):
        store = _store()
        store.tables["semasa_settings"].append({"key": "writer", "value": WRITER})
        llm = FakeLLM({"fit": True, "hook": "h", "domain": "kosmetik", "pillar": said, "citation": "NPRA",
                       "text": {"bm": {"instagram": cap, "facebook": cap, "threads": cap}}})
        idea = {"id": "i1", "stream": "regulab", "source_title": "T", "created_by": "u", "make_media": "none",
                "status": "working"}
        store.tables["semasa_ideas"].append(idea)
        pid = ideas.process_idea(store, llm, idea, ideas.load_settings(store))
        post = next(p for p in store.tables["semasa_posts"] if p["id"] == pid)
        assert post.get("pillar") == kept


def test_a_settings_line_asking_for_sahkan_never_reaches_the_writer():
    w = {"regulab": {"voice": "Blunt.", "never": ["Never name a client.", "Unsourced fee: write [SAHKAN: fee] instead."]}}
    block = ideas.writer_block(w, "regulab")
    assert "Never name a client." in block and "SAHKAN" not in block
