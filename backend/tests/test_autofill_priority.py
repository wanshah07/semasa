from datetime import UTC, datetime

from semasa.autofill import rank_candidates


def test_current_and_publicly_urgent_items_beat_older_generic_items():
    now = datetime(2026, 11, 8, tzinfo=UTC)
    old = {"title": "General background", "summary": "A background note", "created_at": "2026-10-30T00:00:00+00:00"}
    current = {"title": "Regulator update after a product recall", "summary": "latest announcement",
               "created_at": "2026-11-07T00:00:00+00:00"}
    assert rank_candidates([old, current], now)[0] is current


def test_rank_keeps_source_facts_and_does_not_invent_engagement():
    now = datetime(2026, 11, 8, tzinfo=UTC)
    item = {"title": "Viral claim", "summary": "No engagement count supplied", "created_at": "2026-11-07T00:00:00+00:00"}
    got = rank_candidates([item], now)[0]
    assert got is item
    assert "engagement" not in got
