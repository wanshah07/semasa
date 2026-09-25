"""Fixes from the 25 Sep 2026 screening: reads past Supabase's 1000-row cap, slides that wait for their picture,
a sorter that pauses after a bad answer, and a sheet that is rewritten only when the words change."""

import json
from datetime import UTC, datetime, timedelta

from fakestore import FakeStore

from semasa import db, faq, faq_sort, media_generator
from semasa.config import LLMSettings, MediaSettings


def test_fetch_all_reads_past_the_row_cap():
    store = FakeStore(t=[{"id": f"{i:05d}"} for i in range(2345)])
    store.max_rows = 1000
    assert len(store.table("t").select("*").limit(5000).execute().data) == 1000        # what a plain read gets
    got = db.fetch_all(lambda: store.table("t").select("*").order("id"))
    assert len(got) == 2345 and len({r["id"] for r in got}) == 2345


def test_a_picked_headline_survives_even_past_the_first_thousand_ideas():
    old = "2026-09-01T00:00:00+00:00"
    ideas = [{"id": f"i{i:05d}", "trend_id": f"t{i:05d}"} for i in range(1500)]
    trends = [{"id": f"t{i:05d}", "created_at": old, "published_at": old} for i in range(1500)] + \
             [{"id": "orphan", "created_at": old, "published_at": old}]
    store = FakeStore(semasa_ideas=ideas, isu_semasa_trends=trends, semasa_faqs=[])
    store.max_rows = 1000
    dropped = db.drop_unpicked(store, "2026-09-20T00:00:00+00:00", "2026-09-20T00:00:00+00:00")
    assert dropped == 1 and [r["id"] for r in store.tables["isu_semasa_trends"]].count("orphan") == 0
    assert len(store.tables["isu_semasa_trends"]) == 1500


def _ready(i, **k):
    return {"id": f"f{i:05d}", "status": "ready", "category": "halal", "subcategory": "", "question_bm": f"Q{i}",
            "answer_bm": "A", "question_en": "Q", "answer_en": "A", "tags": [], "created_at": "2026-09-01T00:00:00Z",
            "updated_at": "2026-09-01T00:00:00Z", **k}


class Resp:
    status_code = 200
    text = ""

    def json(self):
        return {"ok": True}


def test_the_sheet_gets_every_faq_and_is_not_rewritten_for_a_timestamp(monkeypatch):
    monkeypatch.setenv("SEMASA_SHEET_URL", "https://script/exec")
    monkeypatch.setenv("SEMASA_SHEET_TOKEN", "tok")
    sent = []
    monkeypatch.setattr(faq.sheet.requests, "post", lambda url, data, **k: sent.append(json.loads(data)) or Resp())
    store = FakeStore(semasa_faqs=[_ready(i) for i in range(1500)], semasa_settings=[], semasa_log=[])
    store.max_rows = 1000
    cats = faq.categories({})
    assert faq.sync_sheet(store, {}, cats) == "sheet: 1500 rows written" and len(sent[0]["rows"]) == 1500
    settings = {"faq_sheet": next(r for r in store.tables["semasa_settings"] if r["key"] == "faq_sheet")["value"]}
    for r in store.tables["semasa_faqs"][:10]:
        r["updated_at"] = "2026-09-25T09:00:00Z"                    # the sorter looked at them, nothing else
    assert faq.sync_sheet(store, settings, cats).startswith("sheet: unchanged") and len(sent) == 1
    store.tables["semasa_faqs"][0]["answer_bm"] = "Jawapan baharu"
    assert faq.sync_sheet(store, settings, cats) == "sheet: 1500 rows written"


def _slide_job(created=None, bg="post_image"):
    return {"id": "s1", "post_id": "p1", "mode": "slides", "type": "image", "status": "processing", "attempts": 1,
            "created_at": created or datetime.now(UTC).isoformat(),
            "meta": {"slides": [{"title": "Tajuk", "points": ["Satu"]}], "bg": bg, "stream": "regulab"}}


def test_slides_wait_while_the_posts_picture_is_still_being_made():
    job = _slide_job()
    store = FakeStore(media_generations=[job, {"id": "m1", "post_id": "p1", "mode": "prompt", "status": "pending"}])
    assert media_generator.picture_pending(store, job)
    assert media_generator.process_slides(store, job, MediaSettings.load()) is True
    back = next(r for r in store.tables["media_generations"] if r["id"] == "s1")
    assert back["status"] == "pending" and back["attempts"] == 0                    # a wait spends no attempt


def test_slides_do_not_wait_when_there_is_nothing_to_wait_for():
    job = _slide_job()
    done = FakeStore(media_generations=[job, {"id": "m1", "post_id": "p1", "mode": "prompt", "status": "done"}])
    assert not media_generator.picture_pending(done, job)
    paper = _slide_job(bg="none")
    busy = FakeStore(media_generations=[paper, {"id": "m1", "post_id": "p1", "mode": "prompt", "status": "pending"}])
    assert not media_generator.picture_pending(busy, paper)
    stale = _slide_job(created=(datetime.now(UTC) - timedelta(hours=3)).isoformat())
    busy2 = FakeStore(media_generations=[stale, {"id": "m1", "post_id": "p1", "mode": "prompt", "status": "pending"}])
    assert not media_generator.picture_pending(busy2, stale)                          # never waits for ever


class FakeLLM:
    def __init__(self, out):
        self.out, self.calls = out, 0
        self.s = LLMSettings(provider="openai", api_key="k", base_url="https://x/v1", model="m", timeout=5)

    @property
    def configured(self):
        return True

    def chat_json(self, *a, **k):
        self.calls += 1
        return self.out


def test_a_bad_sorter_answer_pauses_the_sorter_instead_of_paying_every_run():
    store = FakeStore(semasa_faqs=[_ready(1, category="lain", category_by="bot", sorted_at=None)],
                      semasa_settings=[], semasa_log=[])
    llm = FakeLLM("not json")
    assert "3 hours" in faq_sort.run_sort(store, llm, {}, faq.categories({}))
    failed = [r for r in store.tables["semasa_log"] if r["event"] == "faq.sort_failed"]
    assert len(failed) == 1 and failed[0]["level"] == "warn"
    failed[0]["at"] = datetime.now(UTC).isoformat()                                 # the database stamps it
    assert "waiting" in faq_sort.run_sort(store, llm, {}, faq.categories({})) and llm.calls == 1
    failed[0]["at"] = (datetime.now(UTC) - timedelta(hours=4)).isoformat()
    faq_sort.run_sort(store, llm, {}, faq.categories({}))
    assert llm.calls == 2
