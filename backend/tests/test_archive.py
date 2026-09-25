"""A published post is never written again, and is compacted and archived 24 hours after it went out."""

from datetime import UTC, datetime, timedelta

import pytest
from fakestore import FakeStore

from semasa import archive, ideas
from semasa.config import LLMSettings

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)


def _post(pid, hours_ago, **k):
    return {"id": pid, "status": "posted", "lang": "bm", "stream": "regulab", "hook": "Logo halal",
            "posted_at": (NOW - timedelta(hours=hours_ago)).isoformat(), "archived_at": None,
            "text": {"bm": {"facebook": "FB", "instagram": "IG", "threads": "TH"}, "en": {"facebook": "EN"}},
            "published": {"facebook": {"id": "b1"}, "instagram": {"id": "b2"}}, "media_ids": ["m1"],
            "flags": [{"level": "soft"}], "errors": {"threads": "x"}, **k}


def test_a_post_is_archived_24_hours_after_it_went_out_and_compacted():
    media = [{"id": "m1", "post_id": "p1", "status": "done", "meta": {"generated_path": "2026/09/m1.png"}},
             {"id": "m2", "post_id": "p1", "status": "done", "meta": {"generated_path": "2026/09/m2.png"}},
             {"id": "s1", "post_id": "p1", "status": "done", "meta": {"slide_paths": ["a.jpg", "b.jpg"]}},
             {"id": "q1", "post_id": "p1", "status": "pending", "meta": {}},
             {"id": "x1", "post_id": "other", "status": "done", "meta": {"generated_path": "x.png"}}]
    store = FakeStore(semasa_posts=[_post("p1", 25), _post("p2", 5), _post("p3", 30, status="approved")],
                      media_generations=media, semasa_log=[])
    assert archive.run(store, NOW) == "archive: 1 post(s) archived, 2 unused media removed"
    p1, p2, p3 = store.tables["semasa_posts"]
    assert p1["archived_at"] and p1["text"] == {"bm": {"facebook": "FB", "instagram": "IG"}}
    assert p1["flags"] == [] and p1["errors"] == {} and p1["published"] and p1["media_ids"] == ["m1"]
    assert p2["archived_at"] is None and p3["archived_at"] is None           # too recent / never posted
    left = {m["id"] for m in store.tables["media_generations"]}
    assert left == {"m1", "q1", "x1"}                                        # the picture that went out is kept
    assert store.removed == [("semasa-generated", ["2026/09/m2.png", "a.jpg", "b.jpg"])]
    assert [r["event"] for r in store.tables["semasa_log"]] == ["post.archived"]
    assert archive.run(store, NOW + timedelta(hours=1)).startswith("archive: 0 post(s)")   # once only


def test_no_channel_recorded_keeps_every_caption_of_the_sent_language():
    assert archive.compact_text(_post("p", 30, published={})) == {"bm": {"facebook": "FB", "instagram": "IG", "threads": "TH"}}


def test_archive_waits_for_its_sql():
    class NoColumn:
        def table(self, name):
            raise RuntimeError("column semasa_posts.archived_at does not exist")
    assert archive.run(NoColumn(), NOW) == "archive: skipped (run supabase/010_archive.sql)"


class LLMOn:
    def __init__(self):
        self.s = LLMSettings(provider="openai", api_key="k", base_url="https://rootsys.cloud/v1", model="m", timeout=5)
        self.calls = 0

    @property
    def configured(self):
        return True

    def why_off(self):
        return ""

    def chat_json(self, *a, **k):
        self.calls += 1
        return None


def _idea(iid, **k):
    return {"id": iid, "stream": "regulab", "trend_id": "t1", "source_url": "https://bh/x", "note": "", **k}


def test_a_published_story_is_not_written_again_as_a_new_draft():
    store = FakeStore(semasa_ideas=[_idea("i1"), _idea("i2")],
                      semasa_posts=[{"id": "p1", "idea_id": "i1", "status": "posted", "hook": "Logo halal",
                                     "date": "2026-09-25"}])
    llm = LLMOn()
    with pytest.raises(ideas.IdeaError, match="already has a posted post"):
        ideas.process_idea(store, llm, _idea("i2"), {})
    assert llm.calls == 0                                                     # nothing is spent on it


def test_the_guard_lets_through_a_draft_a_rejection_another_stream_and_a_follow_up_with_a_note():
    posts = [{"id": "p1", "idea_id": "i1", "status": "draft"}, {"id": "p9", "idea_id": "i9", "status": "rejected"}]
    store = FakeStore(semasa_ideas=[_idea("i1"), _idea("i9"), _idea("i2")], semasa_posts=posts)
    assert ideas.already_published(store, _idea("i2")) is None
    store = FakeStore(semasa_ideas=[_idea("i1", stream="linkedin"), _idea("i2")],
                      semasa_posts=[{"id": "p1", "idea_id": "i1", "status": "posted"}])
    assert ideas.already_published(store, _idea("i2")) is None                # LinkedIn's post does not block ws.regulab
    store = FakeStore(semasa_ideas=[_idea("i1"), _idea("i2", note="susulan: kesan kepada pengeluar")],
                      semasa_posts=[{"id": "p1", "idea_id": "i1", "status": "posted"}])
    llm = LLMOn()
    with pytest.raises(ideas.IdeaError, match="did not answer"):             # it goes on to the writer
        ideas.process_idea(store, llm, _idea("i2", note="susulan: kesan kepada pengeluar"), {})
    assert llm.calls == 1
