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


def _run_with(monkeypatch, probe_ok, answers, n_items=30):
    """Drive scraper._run with a fake LLM, fake sources and a fake store; return (exit, finish_run fields, calls)."""
    from semasa import scraper
    from semasa.config import LLMSettings, ScraperSettings

    calls = []

    class FakeLLM:
        configured = True

        def __init__(self, s):
            self.s = s

        def probe(self):
            return probe_ok

    def fake_annotate(llm, batch):
        calls.append(len(batch))
        return {b["i"]: {"summary": "Ringkasan.", "category": "ekonomi", "lang": "ms"} for b in batch} if answers else {}

    items = [_item(f"https://a/{i}", title=f"Tajuk berita nombor {i} yang panjang") for i in range(n_items)]
    finished = {}
    monkeypatch.setattr(scraper, "LLM", FakeLLM)
    monkeypatch.setattr(scraper.categorize, "llm_annotate", fake_annotate)
    monkeypatch.setattr(scraper, "collect", lambda sources, s: (items, [{"name": "x", "kind": "rss", "ok": True,
                                                                          "items": n_items, "error": None}]))
    monkeypatch.setattr(scraper, "dedupe_and_filter", lambda it, h: it)
    monkeypatch.setattr(scraper.db, "existing_urls", lambda store, urls: set())
    monkeypatch.setattr(scraper.db, "upsert_trends", lambda store, rows: len(rows))
    monkeypatch.setattr(scraper.db, "prune_older_than", lambda store, c: None)
    monkeypatch.setattr(scraper.db, "finish_run", lambda store, rid, **f: finished.update(f))
    s = ScraperSettings(max_per_source=40, max_age_hours=48, llm_batch=12, use_playwright=False,
                        request_timeout=5, keep_days=30)
    ls = LLMSettings(provider="openai", api_key="k", base_url="https://x/v1", model="m", timeout=5)
    return scraper._run(None, "run-1", s, ls), finished, calls


def test_a_junk_probe_no_longer_switches_off_a_working_llm(monkeypatch):
    code, finished, calls = _run_with(monkeypatch, probe_ok=False, answers=True)
    assert code == 0 and finished["llm_ok"] is True
    assert calls == [12, 12, 6]                                        # every batch was summarised
    assert "probe answer was malformed" in finished["note"]


def test_a_dead_llm_costs_one_batch_then_goes_rules_only(monkeypatch):
    code, finished, calls = _run_with(monkeypatch, probe_ok=False, answers=False)
    assert code == 2 and finished["llm_ok"] is False
    assert calls == [12]                                               # gave up after the first real batch


def test_a_passing_probe_keeps_going_even_if_one_batch_is_empty(monkeypatch):
    code, finished, calls = _run_with(monkeypatch, probe_ok=True, answers=False)
    assert calls == [12, 12, 6] and finished["llm_ok"] is True and code == 0
