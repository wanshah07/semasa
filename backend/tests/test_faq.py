"""FAQ: the rewrite, the category rules, the candidates the scraper offers, and the sheet mirror."""

import json

import pytest
from fakestore import FakeStore

from semasa import faq, faq_sources
from semasa.config import LLMSettings

WAN_Q = ("Salam, Hi. Saya ada soalan berkenaan sijil halal. Kilang kami ada beberapa customer yang buat OEM dengan kami. "
         "Ada 1 customer ni request untuk ada maklumat mereka sebagai pemilik jenama (pemegang sijil halal) saja dalam "
         "sijil halal. Adakah JAKIM boleh provide sijil halal seperti itu selepas permohonan diluluskan?")
WAN_A = "Tak silap format sijil halal sekarang memang ada nama dan alamat kilang oem kat bawah."
GOOD = {"question_bm": "Bolehkah sijil halal produk OEM memaparkan maklumat pemilik jenama sahaja?",
        "answer_bm": "Setahu kami, format sijil halal semasa memaparkan nama dan alamat kilang OEM di bahagian bawah.",
        "question_en": "Can an OEM product's halal certificate show only the brand owner's details?",
        "answer_en": "As far as we know, the current certificate format shows the OEM factory's name and address at the bottom.",
        "category": "halal", "subcategory": "oem & kontrak pengilangan", "tags": ["oem", "sijil", "a", "b", "c", "d"],
        "instrument": "", "answer_source": "given", "needs_check": True,
        "check_note": "Sahkan format sijil halal semasa untuk produk OEM."}


class FakeLLM:
    def __init__(self, out):
        self.out, self.seen = out, []
        self.s = LLMSettings(provider="openai", api_key="k", base_url="https://x/v1", model="m", timeout=5)

    @property
    def configured(self):
        return bool(self.s.api_key)

    def chat_json(self, system, user, max_tokens=0, **_):
        self.seen.append((system, user))
        return self.out


def _store(*rows, settings=None):
    return FakeStore(semasa_faqs=list(rows), semasa_settings=settings or [])


# --- categories ------------------------------------------------------------------------

def test_default_categories_and_a_settings_override():
    cats = faq.categories({})
    assert [c["key"] for c in cats][:2] == ["halal", "skincare"] and cats[-1]["key"] == "lain"
    mine = faq.categories({"faq": {"categories": [{"key": "halal", "bm": "Halal", "subs": ["Logo"]}]}})
    assert [c["key"] for c in mine] == ["halal", "lain"]              # "lain" is always there to fall back to


def test_the_writer_is_held_to_the_list():
    cats = faq.categories({})
    assert faq.pick_category(cats, "Halal", "OEM & KONTRAK PENGILANGAN") == ("halal", "OEM & kontrak pengilangan")
    assert faq.pick_category(cats, "halal", "made up") == ("halal", "")
    assert faq.pick_category(cats, "astrology", "x") == ("lain", "")


# --- the rewrite ------------------------------------------------------------------------

def test_wans_example_is_rewritten_keeps_its_doubt_and_is_published():
    row = {"id": "f1", "status": "working", "source_kind": "paste", "raw_question": WAN_Q, "raw_answer": WAN_A}
    store = _store(row)
    llm = FakeLLM(GOOD)
    faq.process(store, llm, row, faq.categories({}))
    got = store.tables["semasa_faqs"][0]
    assert got["status"] == "ready" and got["error"] is None                   # Wan chose: published as rewritten
    assert got["category"] == "halal" and got["subcategory"] == "OEM & kontrak pengilangan"
    assert got["answer_source"] == "given" and len(got["tags"]) == 5
    # Wan: firm and formal. The writer is told, asked again when it hedges, and an opening hedge is trimmed
    assert got["answer_bm"].startswith("Format sijil halal semasa") and "setahu" not in got["answer_bm"].lower()
    assert got["answer_en"].startswith("The current certificate format") and "as far as" not in got["answer_en"].lower()
    system, user = llm.seen[0]
    assert WAN_Q[:60] in user and WAN_A in user
    assert "Do NOT add any fact" in system and "Anonymise" in system and "FIRMLY and FORMALLY" in system
    assert len(llm.seen) == 2 and "still hedges (setahu kami, as far as we know)" in llm.seen[1][1]


def test_no_answer_means_an_ai_answer_that_is_always_flagged():
    row = {"id": "f1", "source_kind": "auto", "raw_question": "Sunscreen SPF 50 boleh guna untuk bayi?", "raw_answer": ""}
    out = {**GOOD, "answer_source": "given", "needs_check": False, "check_note": ""}
    fields = faq.clean(out, faq.categories({}), had_answer=False)
    assert fields["answer_source"] == "ai" and fields["needs_check"] is True and "AI" in fields["check_note"]
    _, user = faq.build_request(row, faq.categories({}), None)
    assert "ANSWER: (none given)" in user


def test_an_empty_field_is_an_error_not_a_half_entry():
    with pytest.raises(faq.FaqError, match="answer_en"):
        faq.clean({**GOOD, "answer_en": " "}, faq.categories({}), True)


def test_a_headline_is_read_and_the_writer_told_it_is_news(monkeypatch):
    import semasa.ideas as ideas
    monkeypatch.setattr(ideas, "read_source", lambda url: {"ok": True, "title": "T", "description": "D", "text": "Body"})
    row = {"id": "f1", "source_kind": "headline", "source_url": "https://x/a", "raw_question": "NPRA batal notifikasi",
           "raw_answer": "ringkasan"}
    store = _store(row)
    llm = FakeLLM(GOOD)
    faq.process(store, llm, row, faq.categories({}))
    assert "NEWS ARTICLE" in llm.seen[0][1] and "Body" in llm.seen[0][1]


def test_run_records_failures_and_skips_without_the_table(monkeypatch):
    monkeypatch.delenv("FAQ_SHEET_URL", raising=False)
    store = _store({"id": "a", "status": "new", "created_at": "1", "attempts": 0, "raw_question": "Q", "raw_answer": "A",
                    "source_kind": "paste"})
    note = faq.run(store, FakeLLM(None))
    row = store.tables["semasa_faqs"][0]
    assert row["status"] == "error" and "did not answer" in row["error"] and row["attempts"] == 1
    assert "0/1" in note and "not configured" in note

    class NoTable:
        def table(self, name):
            raise RuntimeError('relation "semasa_faqs" does not exist')
    assert faq.run(NoTable(), FakeLLM(GOOD)).startswith("FAQ: skipped")


# --- the sheet --------------------------------------------------------------------------

def _ready(i, cat):
    return {"id": f"r{i}", "status": "ready", "category": cat, "subcategory": "", "question_bm": f"S{i}",
            "answer_bm": "J", "question_en": "Q", "answer_en": "A", "tags": ["x"], "needs_check": i == 1,
            "check_note": "", "instrument": "", "answer_source": "given", "source_kind": "paste",
            "created_at": str(i), "updated_at": str(i)}


def test_sheet_replaced_only_when_the_list_changes(monkeypatch):
    monkeypatch.setenv("FAQ_SHEET_URL", "https://script/exec")
    monkeypatch.setenv("FAQ_SHEET_TOKEN", "tok")
    posts = []

    class Resp:
        status_code = 200
        text = ""

        def json(self):
            return {"ok": True}
    monkeypatch.setattr(faq.sheet.requests, "post", lambda url, data, **k: posts.append(json.loads(data)) or Resp())
    store = _store(_ready(1, "skincare"), _ready(2, "halal"), {"id": "n", "status": "new"})
    cats = faq.categories({})
    assert faq.sync_sheet(store, {}, cats) == "sheet: 2 rows written"
    body = posts[0]
    assert body["token"] == "tok" and body["action"] == "replace"
    assert [r["category_bm"] for r in body["rows"]] == ["Halal", "Penjagaan kulit"]     # in the category list's order
    assert body["rows"][1]["needs_check"] == "YA"
    state = next(r for r in store.tables["semasa_settings"] if r["key"] == "faq_sheet")["value"]
    settings = {"faq_sheet": state}
    assert faq.sync_sheet(store, settings, cats).startswith("sheet: unchanged") and len(posts) == 1
    store.tables["semasa_faqs"][0]["answer_bm"] = "Dibetulkan"                          # an edit in the page
    assert faq.sync_sheet(store, settings, cats) == "sheet: 2 rows written" and len(posts) == 2


def test_a_refused_sheet_write_keeps_the_old_hash(monkeypatch):
    monkeypatch.setenv("FAQ_SHEET_URL", "https://script/exec")
    monkeypatch.setenv("FAQ_SHEET_TOKEN", "bad")

    class Resp:
        status_code = 200
        text = ""

        def json(self):
            return {"ok": False, "error": "Unauthorised"}
    monkeypatch.setattr(faq.sheet.requests, "post", lambda *a, **k: Resp())
    store = _store(_ready(1, "halal"))
    assert "FAILED (Unauthorised)" in faq.sync_sheet(store, {}, faq.categories({}))
    assert store.tables["semasa_settings"] == []


# --- candidates --------------------------------------------------------------------------

JAKIM_PAGE = """<html><body><h1>Bahan Ramuan</h1>
<h3><span>PENJELASAN ISU STATUS HALAL PRODUK BISKUT OREO</span></h3>
<div><p>1&#65039;&#8419; Tular di media sosial berkenaan produk biskut Oreo yang didakwa diperbuat daripada lemak babi.</p>
<p>2&#65039;&#8419; Produk tersebut telah dipersijilkan halal oleh BPJPH, badan yang diiktiraf oleh JAKIM.</p></div>
<h3>PENJELASAN PENDEK</h3><p>Terlalu pendek.</p>
<h2>Lain</h2><p>Bukan penjelasan.</p>
<div>Report abuse</div></body></html>"""

REDDIT_FEED = """<feed><entry><title>Is this sunscreen halal? Anyone knows</title>
<link href="https://www.reddit.com/r/malaysia/comments/abc123/is_this_sunscreen_halal/" />
<content type="html">&lt;p&gt;Bought it at a pharmacy.&lt;/p&gt; submitted by /u/someone [link]</content></entry>
<entry><title>Photos of the new MRT line</title>
<link href="https://www.reddit.com/r/malaysia/comments/zzz999/photos/" /></entry></feed>"""


def test_jakim_entries_arrive_with_jakims_answer():
    rows = faq_sources.parse_jakim(JAKIM_PAGE, "bahan-ramuan")
    assert len(rows) == 1
    r = rows[0]
    assert r["raw_question"] == "PENJELASAN ISU STATUS HALAL PRODUK BISKUT OREO"
    assert "BPJPH" in r["raw_answer"] and "Report abuse" not in r["raw_answer"]
    assert r["status"] == "candidate" and r["source_key"].startswith("jakim:bahan-ramuan:")


def test_reddit_keeps_questions_only_and_never_the_username():
    rows = faq_sources.parse_reddit(REDDIT_FEED, "q")
    assert [r["source_key"] for r in rows] == ["reddit:abc123"]
    assert "Bought it at a pharmacy." in rows[0]["raw_question"] and "/u/" not in rows[0]["raw_question"]
    assert rows[0]["raw_answer"] == ""


def test_candidates_are_never_offered_twice():
    store = _store({"id": "x", "source_key": "reddit:abc123", "status": "dismissed"})
    rows = faq_sources.parse_reddit(REDDIT_FEED, "q") + faq_sources.parse_reddit(REDDIT_FEED, "q")
    assert faq_sources.insert_candidates(store, rows) == 0
    assert faq_sources.insert_candidates(store, faq_sources.parse_jakim(JAKIM_PAGE, "s") * 2) == 1
    assert store.tables["semasa_faqs"][0]["status"] == "dismissed"                   # a dismissed one stays dismissed


def test_collect_reports_each_source_and_names_the_missing_table(monkeypatch):
    class Resp:
        def __init__(self, text):
            self.text = text
    monkeypatch.setattr(faq_sources.fetch, "get",
                        lambda url, timeout=25: Resp(REDDIT_FEED if "reddit" in url else JAKIM_PAGE))
    store = _store()
    report = faq_sources.collect(store)
    assert [(r["name"], r["ok"], r["items"]) for r in report] == [
        ("FAQ · JAKIM Isu Tular Halal", True, 8), ("FAQ · Reddit r/malaysia", True, 1)]   # one entry x 8 sections

    class NoTable:
        def table(self, name):
            raise RuntimeError('Could not find the table public.semasa_faqs')
    report = faq_sources.collect(NoTable())
    assert all(not r["ok"] and "007_faq.sql" in r["error"] for r in report)


def test_a_category_wan_chose_survives_the_rewrite():
    row = {"id": "f1", "source_kind": "paste", "raw_question": "Q", "raw_answer": "A", "category": "skincare",
           "subcategory": "", "category_by": "wan"}
    store = _store(row)
    llm = FakeLLM({**GOOD, "category": "halal", "subcategory": "Logo & sijil"})
    faq.process(store, llm, row, faq.categories({}))
    got = store.tables["semasa_faqs"][0]
    assert (got["category"], got["subcategory"]) == ("skincare", "")        # the writer's halal sub does not fit
    assert "CATEGORY WANTED (Wan chose it; use it): skincare" in llm.seen[0][1]
    row2 = {**row, "id": "f2", "subcategory": "Sunscreen"}
    store2 = _store(row2)
    faq.process(store2, FakeLLM({**GOOD, "category": "skincare", "subcategory": "Serum"}), row2, faq.categories({}))
    assert store2.tables["semasa_faqs"][0]["subcategory"] == "Sunscreen"
    assert got["category_by"] == "wan" and store2.tables["semasa_faqs"][0]["category_by"] == "wan"
    default = {**row, "id": "f3", "category": "lain", "category_by": "bot"}
    store3 = _store(default)
    faq.process(store3, FakeLLM(GOOD), default, faq.categories({}))
    assert store3.tables["semasa_faqs"][0]["category"] == "halal"            # the default: let the writer pick
    assert store3.tables["semasa_faqs"][0]["category_by"] == "bot"


def test_the_bots_own_earlier_pick_is_not_sticky_but_wans_lain_is():
    base = {"source_kind": "paste", "raw_question": "Q", "raw_answer": "A", "subcategory": ""}
    bot = {**base, "id": "b", "category": "skincare", "category_by": "bot"}
    store = _store(bot)
    llm = FakeLLM(GOOD)
    faq.process(store, llm, bot, faq.categories({}))
    assert store.tables["semasa_faqs"][0]["category"] == "halal" and "CATEGORY WANTED" not in llm.seen[0][1]
    lain = {**base, "id": "w", "category": "lain", "category_by": "wan"}
    store = _store(lain)
    faq.process(store, FakeLLM(GOOD), lain, faq.categories({}))
    assert store.tables["semasa_faqs"][0]["category"] == "lain"              # Wan put it there on purpose


def test_the_tabung_reaches_the_writer_and_a_slip_is_flagged():
    tab = [{"indo": "memakai", "bm": "menggunakan"}]
    row = {"id": "f1", "source_kind": "paste", "raw_question": "Q", "raw_answer": "A"}
    store = _store(row)
    llm = FakeLLM({**GOOD, "needs_check": False, "check_note": "", "answer_bm": "Kilang boleh memakai bahan ini. Ini obat."})
    faq.process(store, llm, row, faq.categories({}), tab)
    assert 'ALSO NEVER USE' in llm.seen[0][0] and '"memakai" (write "menggunakan")' in llm.seen[0][0]
    got = store.tables["semasa_faqs"][0]
    assert got["status"] == "ready" and got["needs_check"] is True
    assert "memakai" in got["check_note"] and "obat" in got["check_note"]
    clean_row = {**row, "id": "f2"}
    store2 = _store(clean_row)
    faq.process(store2, FakeLLM({**GOOD, "needs_check": False, "check_note": ""}), clean_row, faq.categories({}), tab)
    assert store2.tables["semasa_faqs"][0]["needs_check"] is False


def test_a_hedge_the_writer_cannot_drop_is_flagged_not_published_silently():
    row = {"id": "f1", "source_kind": "paste", "raw_question": "Q", "raw_answer": "A"}
    store = _store(row)
    hedged = {**GOOD, "needs_check": False, "check_note": "",
              "answer_bm": "Format sijil, tak silap saya, memaparkan alamat kilang."}
    faq.process(store, FakeLLM(hedged), row, faq.categories({}))
    got = store.tables["semasa_faqs"][0]
    assert got["needs_check"] is True and "tak silap saya" in got["check_note"]


def test_experience_alone_is_not_a_reason_to_flag():
    fields = faq.clean({**GOOD, "answer_bm": "Format sijil memaparkan alamat kilang.", "needs_check": False,
                        "check_note": "", "instrument": ""}, faq.categories({}), had_answer=True)
    assert fields["needs_check"] is False and fields["check_note"] == ""
    assert "Never set it merely because no instrument is" in faq.SYSTEM


def test_hedges_are_trimmed_only_where_it_is_safe():
    assert faq.strip_leading_hedges("Setahu kami, format sijil memaparkan alamat. Rasanya ini wajib.") == \
        "Format sijil memaparkan alamat. Ini wajib."
    assert faq.strip_leading_hedges("As far as we know, the certificate shows it.") == "The certificate shows it."
    assert faq.strip_leading_hedges("Sijil ini, tak silap, sah.") == "Sijil ini, tak silap, sah."   # mid-sentence: left
    assert faq.hedges_in({"answer_bm": "Kotak ini kotor."}) == []                                  # "kot" is a whole word


# --- Telegram ------------------------------------------------------------------------------

def _tg(uid, mid, text, reply_to=None, chat=None, bot=False):
    chat = chat or {"id": -100, "type": "supergroup", "title": "Kumpulan Halal", "username": "halalgrp"}
    m = {"message_id": mid, "chat": chat, "text": text, "from": {"id": 7, "is_bot": bot, "first_name": "Ahmad",
                                                                  "username": "ahmad_personal"}}
    if reply_to:
        m["reply_to_message"] = reply_to
    return {"update_id": uid, "message": m}


Q_TEXT = "Salam semua, nak tanya sijil halal OEM boleh letak nama pemilik jenama sahaja ke?"


def test_telegram_questions_and_replies_never_keep_who_wrote_them():
    q = _tg(1, 10, Q_TEXT)["message"]
    ups = [_tg(1, 10, Q_TEXT), _tg(2, 11, "ok noted"), _tg(3, 12, "/start"), _tg(4, 13, "Bot reply?", bot=True),
           _tg(5, 14, "Sijil memaparkan alamat kilang pengeluar.", reply_to=q),
           _tg(6, 15, Q_TEXT, chat={"id": 5, "type": "private"})]
    questions, replies = faq_sources.parse_telegram(ups)
    assert [x["source_key"] for x in questions] == ["tg:-100:10"]
    assert questions[0]["source_url"] == "https://t.me/halalgrp/10" and questions[0]["source_name"] == "Telegram · Kumpulan Halal"
    assert [r["key"] for r in replies] == ["tg:-100:10"]
    dumped = json.dumps([questions, replies])
    assert "Ahmad" not in dumped and "ahmad_personal" not in dumped


def test_telegram_run_stores_answers_confirms_updates_and_never_doubles_a_reply(monkeypatch):
    q = _tg(1, 10, Q_TEXT)["message"]
    batches = [[_tg(1, 10, Q_TEXT), _tg(2, 11, "Sijil memaparkan alamat kilang pengeluar.", reply_to=q)],
               [_tg(2, 11, "Sijil memaparkan alamat kilang pengeluar.", reply_to=q),      # replayed after a crash
                _tg(3, 12, "Rujuk juga MPPHM (Domestik) 2020.", reply_to=q)]]
    calls = []

    class Resp:
        status_code = 200
        headers = {"content-type": "application/json"}

        def __init__(self, result):
            self.result = result

        def json(self):
            return {"ok": True, "result": self.result}
    import requests
    monkeypatch.setattr(requests, "get", lambda url, params, timeout: calls.append(params) or Resp(batches[len(calls) - 1]))
    store = _store()
    assert faq_sources.telegram(store, "TOKEN") == 2                    # the question, then its answer
    row = store.tables["semasa_faqs"][0]
    assert row["raw_answer"] == "Sijil memaparkan alamat kilang pengeluar."
    state = store.tables["semasa_settings"][0]["value"]
    assert state["offset"] == 3 and state["chats"] == {"-100": "Kumpulan Halal"}
    faq_sources.telegram(store, "TOKEN")
    assert calls[1]["offset"] == 3                                        # the confirmed updates are not asked for again
    assert store.tables["semasa_faqs"][0]["raw_answer"] == \
        "Sijil memaparkan alamat kilang pengeluar.\nRujuk juga MPPHM (Domestik) 2020."


def test_telegram_is_dormant_without_a_token_and_hides_it_on_failure(monkeypatch):
    class Resp:
        def __init__(self, text):
            self.text = text
    monkeypatch.setattr(faq_sources.fetch, "get", lambda url, timeout=25: Resp(""))
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    assert [r["name"] for r in faq_sources.collect(_store())] == ["FAQ · JAKIM Isu Tular Halal", "FAQ · Reddit r/malaysia"]
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "SECRET123")
    import requests

    def boom(url, **k):
        raise requests.ConnectionError(f"cannot reach {url}")
    monkeypatch.setattr(requests, "get", boom)
    tg = faq_sources.collect(_store())[-1]
    assert tg["name"] == "FAQ · Telegram" and not tg["ok"] and "SECRET123" not in tg["error"] and "***" in tg["error"]


def test_sheet_results_are_logged_in_one_shape(monkeypatch):
    monkeypatch.setenv("FAQ_SHEET_URL", "https://script/exec")
    monkeypatch.setenv("FAQ_SHEET_TOKEN", "tok")

    class Resp:
        status_code = 200
        text = ""

        def __init__(self, ok):
            self.ok = ok

        def json(self):
            return {"ok": True} if self.ok else {"ok": False, "error": "Unauthorised"}
    replies = [Resp(False), Resp(True)]
    monkeypatch.setattr(faq.sheet.requests, "post", lambda *a, **k: replies.pop(0))
    store = _store(_ready(1, "halal"))
    faq.sync_sheet(store, {}, faq.categories({}))
    faq.sync_sheet(store, {}, faq.categories({}))
    logged = [(r["level"], r["area"], r["event"], r["title"]) for r in store.tables["semasa_log"]]
    assert logged == [("error", "faq", "faq.sheet_failed", "Google Sheet gagal dikemas kini: Unauthorised"),
                      ("info", "faq", "faq.sheet", "Google Sheet dikemas kini: 1 soalan")]
