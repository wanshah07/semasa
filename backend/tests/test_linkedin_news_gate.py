"""LinkedIn takes a news story only when it is about an authority's act (Wan, 20 Nov 2026: "for linkedn, no need include idea
from recent issue unless berkaitan regulatory, circular from authority etc"). The headlines are the ones that reached LinkedIn on
19 and 20 Nov before this rule."""
from __future__ import annotations

import pytest
from fakestore import FakeStore

from semasa import ideas


def _idea(title, summary="", **kw):
    return {"id": "i1", "stream": "linkedin", "trend_id": "t1", "source_title": title, "source_summary": summary, "note": "",
            **kw}


NOT_REGULATORY = [
    "Hasrat Muhammad Aidil derma organ jadi kenyataan – Ibu",
    "Lebih 30 sengatan tebuan, pesawah terjun parit selamatkan diri",
    "Ovari wanita tersilap dibuang ketika pembedahan, hospital mohon maaf",
    "Best Biohacking Programme - Wellness Awards 2026",
    "Puteri Sarah raih pengiktirafan 100 Usahawan Muda Paling Berpengaruh",
    "KKM tunggu laporan lengkap kes kematian pelajar SBP di Kuala Kangsar",
    "Import daging babi meningkat lebih lima kali ganda sejak 2020",
]
REGULATORY = [
    "NPRA tarik balik pendaftaran 12 produk kosmetik mengandungi merkuri",
    "Pekeliling baharu KKM: label wajib dalam Bahasa Melayu mulai 1 Januari",
    "Malaysian govt weighs changes to drug law to shift focus from punishment",
    "JAKIM batal pensijilan halal sebuah kilang sos",
    "Authorities seize 27,000 hair dye bottles over a fake halal logo",
    "EU bans two UV filters from sunscreen from 2027",
    "Garis panduan baharu pelabelan makanan diumumkan",
]


@pytest.mark.parametrize("title", NOT_REGULATORY)
def test_a_news_story_with_no_authority_in_it_is_not_written_for_linkedin(title):
    assert "regulation, a circular" in ideas.linkedin_news_gate(_idea(title), {})


@pytest.mark.parametrize("title", REGULATORY)
def test_a_news_story_about_an_authoritys_act_is_written(title):
    assert ideas.linkedin_news_gate(_idea(title), {}) == ""


def test_the_summary_and_the_article_count_too():
    assert ideas.linkedin_news_gate(_idea("Kilang sos ditutup", "JAKIM membatalkan sijil halal selepas pemeriksaan"), {}) == ""
    assert ideas.linkedin_news_gate(_idea("Kilang sos ditutup"), {"title": "", "description": "BKKM mengeluarkan notis"}) == ""


def test_only_a_linkedin_news_story_is_judged_and_wans_own_note_overrides():
    news = "Hasrat Muhammad Aidil derma organ jadi kenyataan – Ibu"
    assert ideas.linkedin_news_gate(_idea(news, stream="regulab"), {}) == "", "ws.regulab is not judged here"
    assert ideas.linkedin_news_gate(_idea(news, trend_id=None), {}) == "", "a regulator row, a paper, a website, a folder"
    assert ideas.linkedin_news_gate(_idea(news, note="tulis tentang peraturan derma organ"), {}) == "", "his words are his call"
    assert ideas.linkedin_news_gate(_idea(news, brief={"source_kind": "regulator"}), {}) == ""


def test_the_writer_is_not_paid_for_a_story_the_gate_shuts(monkeypatch):
    class NoCall:
        configured = True

        def chat_json(self, *a, **k):
            raise AssertionError("the writer was called")
    monkeypatch.setattr(ideas, "read_source", lambda url: {"ok": False, "why": "no link", "image": None})
    store = FakeStore(semasa_settings=[{"key": "brand", "value": {}}], semasa_posts=[], media_generations=[], semasa_ideas=[])
    idea = _idea("Lebih 30 sengatan tebuan, pesawah terjun parit selamatkan diri", created_by="u", make_media="none")
    store.tables["semasa_ideas"].append({**idea, "status": "working"})
    with pytest.raises(ideas.IdeaError, match="LinkedIn takes a news story"):
        ideas.process_idea(store, NoCall(), idea, ideas.load_settings(store))


def test_the_writer_is_also_told_to_decline_such_a_story():
    system, user = ideas.build_request(_idea("Kilang sos ditutup"), {"ok": False, "why": "x", "image": None}, {})
    assert "NEWSPAPER STORY ON LINKEDIN" in user and '"fit": false' in user
    assert "NEWSPAPER STORY ON LINKEDIN" not in ideas.build_request(_idea("x", trend_id=None), {"ok": False}, {})[1]
