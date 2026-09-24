from datetime import UTC, datetime, timedelta

from semasa.scraper import annotate, dedupe_and_filter, retention_cutoff
from semasa.sources import Item

NOW = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)


def _item(url, hours_old=1, title="Tajuk yang cukup panjang", snippet=None):
    return Item(title=title, url=url, source="S", lang="ms",
                published_at=NOW - timedelta(hours=hours_old), snippet=snippet)


def test_dedupe_and_age():
    items = [_item("https://a/1"), _item("https://a/1"), _item("https://a/2", hours_old=90),
             Item(title="tanpa tarikh", url="https://a/3", source="S", lang="ms")]
    out = dedupe_and_filter(items, 48, now=NOW)
    assert [i.url for i in out] == ["https://a/1", "https://a/3"]  # dup dropped, stale dropped, undated kept


def test_annotate_rules_only_marks_source():
    rows = annotate([_item("https://a/1", title="NPRA batal notifikasi produk kosmetik", snippet="Ringkasan feed.")], None, 10)
    assert rows[0]["category"] == "kosmetik"
    assert rows[0]["summary"] == "Ringkasan feed."
    assert rows[0]["summary_source"] == "rules"
    rows = annotate([_item("https://a/2", title="Tajuk tanpa ringkasan langsung")], None, 10)
    assert rows[0]["summary"] is None and rows[0]["summary_source"] == "none"


def test_annotate_llm_overrides_only_answered(monkeypatch):
    class FakeLLM:
        pass

    def fake_annotate(llm, batch):
        return {0: {"summary": "LLM kata.", "category": "halal", "lang": "en"}}

    monkeypatch.setattr("semasa.scraper.categorize.llm_annotate", fake_annotate)
    rows = annotate([_item("https://a/1", title="JAKIM x"), _item("https://a/2", title="Polis tahan y")], FakeLLM(), 10)
    assert rows[0]["summary_source"] == "llm" and rows[0]["summary"] == "LLM kata." and rows[0]["lang"] == "en"
    assert rows[1]["summary_source"] == "none" and rows[1]["category"] == "jenayah"


def test_retention_cutoff():
    assert retention_cutoff(NOW, 30) == (NOW - timedelta(days=30)).isoformat()
    assert retention_cutoff(NOW, 0) is None
    assert retention_cutoff(NOW, -1) is None


def test_crash_still_closes_the_run_row(monkeypatch):
    import pytest

    from semasa import scraper

    closed = {}
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "k")
    monkeypatch.setattr(scraper.db, "client", lambda s: object())
    monkeypatch.setattr(scraper.db, "start_run", lambda store, sha: "run-1")
    monkeypatch.setattr(scraper.db, "finish_run", lambda store, rid, **f: closed.update(rid=rid, **f))

    def boom(*a, **k):
        raise RuntimeError("400 Bad Request")

    monkeypatch.setattr(scraper, "_run", boom)
    with pytest.raises(RuntimeError):
        scraper.main()
    assert closed["rid"] == "run-1"
    assert closed["note"] == "crashed: RuntimeError: 400 Bad Request"
