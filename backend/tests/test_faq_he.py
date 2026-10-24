"""The Halal Executive FAQ mirror: new rows land ready, changed words update, Wan's filing holds, unpublished rows dismiss."""

import pytest
from fakestore import FakeStore

from semasa import faq_he


def _he(i, **over):
    base = {"id": f"FAQ-{i}", "category": "Pensijilan", "subcategory": "Permohonan", "question_en": f"Q{i} en?",
            "question_bm": f"S{i} bm?", "answer_formal_en": f"A{i} formal en", "answer_layman_en": f"A{i} layman en",
            "answer_formal_bm": f"J{i} formal bm", "answer_layman_bm": f"J{i} layman bm", "status": "published"}
    base.update(over)
    return base


class _Resp:
    def __init__(self, body):
        self._b = body

    def json(self):
        return self._b


def _feed(monkeypatch, rows, extra=None):
    calls = []

    def fake_get(url, **kw):
        calls.append(url)
        return _Resp({"ok": True, "faq": rows, **(extra or {})})
    monkeypatch.setattr(faq_he.fetch, "get", fake_get)
    return calls


def _rows(store):
    return {r["source_key"]: r for r in store.tables.get(faq_he.FAQS, [])}


def test_to_row_prefers_the_formal_answer_and_leaves_filing_to_the_sorter():
    r = faq_he.to_row(_he(1))
    assert r["status"] == "ready" and r["source_key"] == "he:FAQ-1" and r["category"] == "lain", "the sorter files it"
    assert r["answer_bm"] == "J1 formal bm" and r["answer_en"] == "A1 formal en" and r["subcategory"] == "Pensijilan · Permohonan"
    assert r["tags"] == ["halal-executive"] and r["needs_check"] is False and r["answer_source"] == "given"
    r2 = faq_he.to_row(_he(2, answer_formal_bm="", answer_formal_en=""))
    assert r2["answer_bm"] == "J2 layman bm" and r2["answer_en"] == "A2 layman en"


def test_first_sync_inserts_every_published_row(monkeypatch):
    store = FakeStore()
    calls = _feed(monkeypatch, [_he(1), _he(2), {"id": "FAQ-3"}, {"no": "id"}])
    out = faq_he.sync(store, "https://script.google.com/macros/s/X/exec")
    assert out == {"feed": 2, "added": 2, "updated": 0, "dismissed": 0}
    assert calls == ["https://script.google.com/macros/s/X/exec?action=data"]
    rows = _rows(store)
    assert set(rows) == {"he:FAQ-1", "he:FAQ-2"} and all(r["status"] == "ready" for r in rows.values())


def test_a_changed_answer_updates_and_an_unchanged_one_is_left_alone(monkeypatch):
    store = FakeStore()
    _feed(monkeypatch, [_he(1), _he(2)])
    faq_he.sync(store, "https://x/exec")
    _feed(monkeypatch, [_he(1, answer_formal_bm="J1 baharu"), _he(2)])
    out = faq_he.sync(store, "https://x/exec")
    assert out["updated"] == 1 and out["added"] == 0
    assert _rows(store)["he:FAQ-1"]["answer_bm"] == "J1 baharu"


def test_wans_own_filing_is_never_moved_but_the_words_still_update(monkeypatch):
    store = FakeStore()
    _feed(monkeypatch, [_he(1)])
    faq_he.sync(store, "https://x/exec")
    row = _rows(store)["he:FAQ-1"]
    store.table(faq_he.FAQS).update({"category": "kosmetik", "subcategory": "Label", "category_by": "wan"}) \
        .eq("id", row["id"]).execute()
    _feed(monkeypatch, [_he(1, subcategory="Logo", question_bm="S1 diubah?")])
    faq_he.sync(store, "https://x/exec")
    got = _rows(store)["he:FAQ-1"]
    assert got["category"] == "kosmetik" and got["subcategory"] == "Label" and got["question_bm"] == "S1 diubah?"


def test_a_row_that_left_the_feed_is_dismissed_and_comes_back_ready(monkeypatch):
    store = FakeStore()
    _feed(monkeypatch, [_he(1), _he(2)])
    faq_he.sync(store, "https://x/exec")
    _feed(monkeypatch, [_he(2)])
    assert faq_he.sync(store, "https://x/exec")["dismissed"] == 1
    assert _rows(store)["he:FAQ-1"]["status"] == "dismissed"
    _feed(monkeypatch, [_he(1), _he(2)])
    assert faq_he.sync(store, "https://x/exec")["updated"] == 1
    assert _rows(store)["he:FAQ-1"]["status"] == "ready"


def test_an_empty_feed_dismisses_nothing(monkeypatch):
    store = FakeStore()
    _feed(monkeypatch, [_he(1)])
    faq_he.sync(store, "https://x/exec")
    _feed(monkeypatch, [])
    assert faq_he.sync(store, "https://x/exec") == {"feed": 0, "added": 0, "updated": 0, "dismissed": 0}
    assert _rows(store)["he:FAQ-1"]["status"] == "ready"


def test_other_faq_rows_are_never_touched(monkeypatch):
    store = FakeStore()
    store.table(faq_he.FAQS).insert({"source_key": "jakim:1", "status": "candidate", "question_bm": "x"}).execute()
    store.table(faq_he.FAQS).insert({"source_key": None, "status": "ready", "question_bm": "pasted"}).execute()
    _feed(monkeypatch, [_he(1)])
    faq_he.sync(store, "https://x/exec")
    assert [r["status"] for r in store.tables[faq_he.FAQS][:2]] == ["candidate", "ready"]


def test_a_feed_without_faq_or_with_an_error_raises(monkeypatch):
    store = FakeStore()
    monkeypatch.setattr(faq_he.fetch, "get", lambda url, **kw: _Resp({"ok": False, "error": "Sheet feed error"}))
    with pytest.raises(RuntimeError, match="Sheet feed error"):
        faq_he.sync(store, "https://x/exec")
    monkeypatch.setattr(faq_he.fetch, "get", lambda url, **kw: _Resp({"settings": {}}))
    with pytest.raises(RuntimeError, match="no `faq` list"):
        faq_he.sync(store, "https://x/exec")


def test_api_url_reads_the_setting_then_the_env(monkeypatch):
    store = FakeStore()
    monkeypatch.delenv("HE_API_URL", raising=False)
    assert faq_he.api_url(store) == ""
    monkeypatch.setenv("HE_API_URL", "https://env/exec")
    assert faq_he.api_url(store) == "https://env/exec"
    store.tables["semasa_settings"] = [{"key": "faq", "value": {"he_api_url": " https://set/exec "}}]
    assert faq_he.api_url(store) == "https://set/exec"
