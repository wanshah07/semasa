# ruff: noqa: E501  (long literals: the shapes are copied from live answers)
"""Wan's own sources (Reddit, YouTube, OneDrive folders, MYRA's sheet) read through Composio For You.

Two kinds of test. The CELL tests run the exact Python the workbench would run (foryou.render) against a stub of
`run_composio_tool` whose answers are the shapes measured live on 30 Sep 2026, so a mistake in code that otherwise only
runs inside Composio shows up here. The RUN tests drive intake.run with a fake client and a fake writer."""

import contextlib
import io
import json
from datetime import UTC, date, datetime

import pytest
from fakestore import FakeStore

from semasa import autofill, community, folders, foryou, ideas, intake, myra, senders

NOW = datetime(2026, 9, 30, 2, 0, tzinfo=UTC)               # Wed 30 Sep, 10:00 MYT


# --- running a cell locally -------------------------------------------------------------------------------------------

def run_cell(body, params, tools, budget=140):
    code = foryou.render(body, params, budget)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        exec(code, {"run_composio_tool": tools})              # noqa: S102 - the point of the test
    line = next(x for x in out.getvalue().splitlines() if x.startswith(senders._MARK))
    return json.loads(line[len(senders._MARK):])


def tools_from(table):
    """A stub run_composio_tool: `table` maps a slug to a (data, error) pair or a function of the arguments."""
    def tool(slug, args, account=None, print_schema_for_tool=True, retry_params=None):
        got = table[slug]
        got = got(args, account) if callable(got) else got
        return got
    return tool


def test_the_wrapper_prints_a_marker_line_and_refuses_an_answer_over_the_limit():
    r = run_cell("OUT['x'] = 1", {}, tools_from({}))
    assert r == {"ok": True, "out": {"x": 1}}
    big = run_cell("OUT['x'] = 'a' * 40000", {}, tools_from({}))
    assert big["ok"] is False and "over the workbench limit" in big["message"]
    boom = run_cell("raise ValueError('nope')", {}, tools_from({}))
    assert boom["ok"] is False and "ValueError: nope" in boom["message"]


# --- Reddit and YouTube -----------------------------------------------------------------------------------------------

REDDIT = ({"data": {"posts": [
    {"id": "a1", "title": "Sunscreen SPF50 tak cukup kalau tak reapply?", "score": 55, "num_comments": "260",
     "permalink": "https://www.reddit.com/r/malaysia/comments/a1/x", "created_datetime": "2026-09-28T01:00:00+00:00",
     "subreddit": "malaysia", "selftext": "Ramai kata cukup sekali sehari."},
    {"id": "a2", "title": "Traveling to Malaysia", "score": 9, "num_comments": "4",
     "permalink": "https://www.reddit.com/r/malaysia/comments/a2/y", "created_datetime": "2026-09-26T01:00:00+00:00",
     "subreddit": "malaysia"},
    {"id": "old", "title": "Old thread", "score": 900, "num_comments": "900",
     "permalink": "https://www.reddit.com/r/malaysia/comments/old/z", "created_datetime": "2026-08-01T01:00:00+00:00",
     "subreddit": "malaysia"}]}}, "")
YT_QUOTA = ({}, '{"error": {"code": 429, "message": "Quota exceeded for quota metric \'Search Queries\'"}}')
def cell_posts(n=None):
    """The posts as the community cell hands them back (it renames created_datetime to created)."""
    ps = [{**p, "created": p.get("created_datetime"), "text": p.get("selftext") or ""} for p in REDDIT[0]["data"]["posts"]]
    return ps[:n] if n else ps


CFG = {"subreddit": "malaysia", "terms": ["halal", "skincare"], "window": "week", "limit": 15,
       "youtube": {"enabled": True, "days": 14, "max_results": 8, "queries": ["sunscreen Malaysia"]}}


def test_the_community_cell_restricts_reddit_in_the_query_text_and_survives_a_youtube_quota_answer():
    seen = {}

    def reddit(args, account):
        seen.update(args)
        return REDDIT

    out = run_cell(community._CELL, {"subreddit": "malaysia", "terms": ["halal", "skincare"], "window": "week", "limit": 15,
                                     "youtube": CFG["youtube"]},
                   tools_from({"REDDIT_SEARCH_ACROSS_SUBREDDITS": reddit, "YOUTUBE_SEARCH_YOU_TUBE": YT_QUOTA}))["out"]
    assert seen["search_query"] == "subreddit:malaysia (halal OR skincare)" and seen["result_type"] == ["link"]
    assert len(out["posts"]) == 3 and out["youtube_error"] == "quota" and out["videos"] == []


def test_the_community_cell_reads_video_view_counts_from_the_details_call():
    def search(args, account):
        assert args["order"] == "viewCount" and args["regionCode"] == "MY" and "relevanceLanguage" not in args
        return ({"data": {"items": [{"id": {"videoId": "v1"}}, {"id": {"videoId": "v2"}}]}}, "")

    def details(args, account):
        assert args["id"] == ["v1", "v2"] and args["parts"] == ["snippet", "statistics"]
        return ({"data": {"items": [{"id": "v1", "snippet": {"title": "Sunscreen mitos", "channelTitle": "C",
                                                                "publishedAt": "2026-09-25T00:00:00Z"},
                                     "statistics": {"viewCount": "125000", "commentCount": "300"}}]}}, "")

    out = run_cell(community._CELL, {"subreddit": "malaysia", "terms": ["halal"], "window": "week", "limit": 5,
                                     "youtube": CFG["youtube"]},
                   tools_from({"REDDIT_SEARCH_ACROSS_SUBREDDITS": ({"data": {"posts": []}}, ""),
                               "YOUTUBE_SEARCH_YOU_TUBE": search, "YOUTUBE_GET_VIDEO_DETAILS_BATCH": details}))["out"]
    assert out["youtube_error"] == "" and out["videos"][0]["views"] == "125000"


def test_candidates_are_ranked_by_comments_and_stale_or_linkless_ones_are_dropped():
    raw = {"posts": cell_posts() + [{"id": "n", "title": "no link", "num_comments": "50"}],
           "videos": [{"id": "v1", "title": "Sunscreen mitos", "published": "2026-09-25T00:00:00Z", "views": "125000",
                       "channel": "C"}]}
    got = community.candidates(raw, NOW)
    reddit = [c for c in got if c["platform"] == "reddit"]
    video = [c for c in got if c["platform"] == "youtube"]
    assert [c["title"] for c in reddit] == ["Sunscreen SPF50 tak cukup kalau tak reapply?", "Traveling to Malaysia"]
    assert all("Old thread" != c["title"] and c["url"] for c in got)          # stale and linkless rows are gone
    assert reddit[0]["metrics"] == "260 komen" and video[0]["url"] == "https://www.youtube.com/watch?v=v1"
    assert video[0]["metrics"] == "125,000 tontonan"


class Writer:
    """A fake writer: answers each job by the words in its system prompt."""
    configured = True

    def __init__(self, answer):
        self.answer, self.calls = answer, []

    def chat_json(self, system, user, **_kw):
        self.calls.append((system, user))
        return self.answer(system, user)


def community_answer(system, user):
    rows = [json.loads(x) for x in user.splitlines()[1:]]
    return {"items": [{"i": r["i"], "relevant": "Sunscreen" in r["title"],
                       "title": "SPF50 tak perlu disapu semula", "summary": "Orang ramai berhujah. Ada yang setuju.",
                       "why": "Peniaga perlu berhati-hati dengan dakwaan.", "domain": "kosmetik"} for r in rows]}


def test_annotate_keeps_relevant_hides_the_rest_and_never_shows_an_unanswered_row():
    cands = community.candidates({"posts": cell_posts(2)}, NOW)
    kept, rejected = community.annotate(Writer(community_answer), cands)
    assert [k["title"] for k in kept] == ["SPF50 tak perlu disapu semula"] and len(rejected) == 1
    row = community.to_row(kept[0])
    assert row["section"] == "reddit" and row["url"].startswith("https://www.reddit.com/") and row["relevant"] is True
    assert "malaysia" not in row["title"].lower() and "reddit" not in row["title"].lower()
    assert community.tombstone(rejected[0])["relevant"] is False and community.tombstone(rejected[0])["summary"] is None
    assert community.annotate(Writer(lambda s, u: None), cands) == ([], [])          # the writer never answered
    assert community.annotate(None, cands) == ([], [])


# --- MYRA -------------------------------------------------------------------------------------------------------------

SHEET = [
    ["25/09/2026", "Yes", "Yes", "EU (France), EU (Sweden)", "EU Safety Gate terbitkan laporan minggu 38; Ada 3 amaran kosmetik baharu",
     "SR/02536/26", "https://ec.europa.eu/alert/1"],
    ["28/09/2026", "Yes", "Yes", "EU", "Amaran kosmetik baharu SR/02676/26", "SR/02676/26", "-"],
    ["29/09/2026", "Yes", "No (separa)", "EU", "Separuh liputan", "-", "\\-"],
    ["26/09/2026", "Yes", "No", "", "", "", ""],
    ["01/09/2026", "Yes", "Yes", "EU", "Terlalu lama", "-", "https://x/1"],
]


def test_myra_findings_split_on_semicolons_flag_a_shared_link_and_skip_no_updates():
    got = myra.findings(SHEET, date(2026, 9, 30), days=10)
    assert [g["title"] for g in got] == ["Amaran kosmetik baharu SR/02676/26", "EU Safety Gate terbitkan laporan minggu 38",
                                         "Ada 3 amaran kosmetik baharu"]
    a, b, c = got
    assert a["url"] == "myra://2026-09-28-1" and a["raw"]["link"] is None                       # "-" means none
    assert b["url"] == "https://ec.europa.eu/alert/1#myra-2026-09-25-1" and b["raw"]["link_shared"] is True
    assert c["url"] != b["url"] and c["raw"]["ref_no"] == "SR/02536/26"
    assert b["published_at"] == datetime(2026, 9, 25, tzinfo=UTC) and b["country"] == "EU (France)"


def test_the_myra_cell_reads_the_sheet_read_only_with_the_owners_account():
    seen = {}

    def batch(args, account):
        seen.update(args=args, account=account)
        return ({"data": {"valueRanges": [{"values": [["Tarikh"] + [""] * 6] + SHEET}]}}, "")

    out = run_cell(myra._CELL, {"id": "SHEET", "range": "Sheet1!A1:G500", "account": "googlesheets_serau-tucker"},
                   tools_from({"GOOGLESHEETS_BATCH_GET": batch}))["out"]
    assert seen["account"] == "googlesheets_serau-tucker" and seen["args"]["ranges"] == ["Sheet1!A1:G500"]
    assert len(out["rows"]) == len(SHEET) and len(out["rows"][0]) == 7


# --- OneDrive folders -------------------------------------------------------------------------------------------------

def test_the_folder_listing_cell_reads_each_domain_folder_and_only_todays_and_tomorrows_urgent_subfolders():
    def kids(args, account):
        assert account == "Muhammad-Ridzuan" and args["use_me_drive"] is True
        path = args["folder_path"]
        table = {
            "/40. HERMES/Cosmetic": [{"id": "f1", "name": "guide.pdf", "size": 900, "file": {"mimeType": "application/pdf"},
                                      "webUrl": "https://od/f1", "lastModifiedDateTime": "2026-08-29T01:00:00Z"}],
            "/40. HERMES/Food": [{"id": "d1", "name": "sub", "folder": {"childCount": 2}}],
            "/40. HERMES/urgent post": [{"id": "u1", "name": "011026", "folder": {}}, {"id": "u2", "name": "300926", "folder": {}}],
            "/40. HERMES/urgent post/011026": [{"id": "f9", "name": "rush.pdf", "size": 10,
                                                "file": {"mimeType": "application/pdf"}}],
        }
        return ({"data": {"value": table.get(path, [])}}, "")

    out = run_cell(folders._LIST, {"root": "/40. HERMES", "account": "Muhammad-Ridzuan",
                                   "domains": {"kosmetik": "Cosmetic", "makanan": "Food"}, "urgent": "urgent post",
                                   "urgent_dates": ["300926", "011026"]}, tools_from({"ONE_DRIVE_LIST_FOLDER_CHILDREN": kids}))["out"]
    assert {(f["id"], f["domain"], f["urgent_for"]) for f in out["files"]} == {("f1", "kosmetik", None), ("f9", None, "2026-10-01")}
    assert out["errors"] == []


def tiny_pdf(text):
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offs = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    x = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for o in offs:
        out += f"{o:010d} 00000 n \n".encode()
    return out + f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{x}\n%%EOF".encode()


def _download(monkeypatch, blobs):
    import requests

    class R:
        def __init__(self, b):
            self.content = b

    monkeypatch.setattr(requests, "get", lambda url, timeout=0: R(blobs[url]))

    def dl(args, account):
        assert args["item_id"] and args["file_name"] and account == "Muhammad-Ridzuan"
        return ({"data": {"content": {"s3url": "s3://" + args["item_id"], "name": args["file_name"]}}}, "")
    return dl


def test_the_read_cell_extracts_pdf_text_with_page_markers_and_reports_what_it_cannot_read(monkeypatch):
    pytest.importorskip("pypdf")
    dl = _download(monkeypatch, {"s3://p1": tiny_pdf("Notifikasi kosmetik bukan kelulusan produk"), "s3://z1": b"zip"})
    files = [{"id": "p1", "name": "a.pdf", "size": 5000}, {"id": "z1", "name": "b.zip", "size": 10},
             {"id": "big", "name": "c.pdf", "size": 90_000_000}]
    out = run_cell(folders._READ, {"account": "Muhammad-Ridzuan", "files": files, "max_chars": 14000, "max_bytes": 60_000_000,
                                   "matrix": {}}, tools_from({"ONE_DRIVE_DOWNLOAD_FILE": dl}))["out"]
    by = {d["id"]: d for d in out["docs"]}
    assert by["p1"]["kind"] == "pdf" and by["p1"]["pages"] == 1 and "[hlm 1]" in by["p1"]["text"]
    assert "Notifikasi kosmetik" in by["p1"]["text"]
    assert by["z1"]["error"].startswith("type .zip") and by["big"]["error"].startswith("too big")


def test_the_read_cell_stops_at_its_time_budget_and_says_what_it_skipped(monkeypatch):
    dl = _download(monkeypatch, {})
    out = run_cell(folders._READ, {"account": "x", "files": [{"id": "p1", "name": "a.pdf", "size": 1}], "max_chars": 100,
                                   "max_bytes": 1000, "matrix": {}}, tools_from({"ONE_DRIVE_DOWNLOAD_FILE": dl}), budget=10)["out"]
    assert out["docs"] == [] and out["skipped"] == ["p1"]


def test_the_read_cell_takes_the_next_unused_rows_of_a_post_matrix_workbook(monkeypatch):
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Post Matrix"
    ws.append(["h"] * 12)
    for n in range(2, 7):
        ws.append(["", "", "", "", "", "", f"Cite {n}", "", f"English text {n}. More.", f"Teks BM {n}", "visual", "prompt"])
    buf = io.BytesIO()
    wb.save(buf)
    dl = _download(monkeypatch, {"s3://m1": buf.getvalue()})
    out = run_cell(folders._READ, {"account": "Muhammad-Ridzuan", "files": [{"id": "m1", "name": "LabMuffin.xlsx", "size": 999}],
                                   "max_chars": 1000, "max_bytes": 10**8, "matrix": {"skip": [2, 3], "want": 2}},
                   tools_from({"ONE_DRIVE_DOWNLOAD_FILE": dl}))["out"]
    doc = out["docs"][0]
    assert doc["kind"] == "matrix" and [r["row"] for r in doc["rows"]] == [4, 5]
    rows = folders.matrix_rows({"id": "m1", "name": "x", "folder": "Cosmetic Case Studies"}, doc)
    assert rows[0]["url"] == "onedrive://m1#r4" and rows[0]["domain"] == "kajian_kes" and rows[0]["title"] == "English text 4."
    assert rows[0]["raw"]["bm"] == "Teks BM 4" and rows[0]["raw"]["matrix"] is True


def test_masking_removes_emails_phone_numbers_and_company_names_before_anything_is_sent():
    text = "Hubungi ali@abc.com atau +60 12-345 6789. Untuk Glow Beauty Sdn Bhd dan Maju Jaya Berhad sahaja."
    out = folders.mask(text)
    assert "ali@abc.com" not in out and "345 6789" not in out and "Glow Beauty" not in out and "Maju Jaya" not in out
    assert "[e-mel]" in out and "[nombor]" in out and out.count("[syarikat]") == 2


def test_urgent_dates_are_todays_and_tomorrows_ddmmyy_in_malaysia_time():
    assert folders.urgent_dates(datetime(2026, 9, 30, 17, 0, tzinfo=UTC)) == ["011026", "021026"]     # 01:00 MYT on 1 Oct


def test_plan_reads_urgent_files_first_then_the_newest_and_never_a_mined_file():
    files = [{"id": "old", "modified": "2026-01-01"}, {"id": "new", "modified": "2026-08-30"},
             {"id": "mid", "modified": "2026-06-01"}, {"id": "u", "modified": "2020-01-01", "urgent_for": "2026-10-01"},
             {"id": "done", "modified": "2026-09-01"}, {"id": "mx", "modified": "2026-08-30"}]
    todo, matrix = folders.plan(files, {"mined": {"done", "mx"}, "matrix_files": {"mx"}}, 3)
    assert [f["id"] for f in todo] == ["u", "new", "mid"] and [f["id"] for f in matrix] == ["mx"]


def test_an_empty_file_is_recorded_as_one_hidden_marker_so_it_is_not_read_again():
    rows = folders.angle_rows({"id": "f1", "name": "n", "folder": "Food", "domain": "makanan"}, {"kind": "pdf"}, [])
    assert len(rows) == 1 and rows[0]["relevant"] is False and rows[0]["url"] == "onedrive://f1#0"
    assert folders.file_id_of(rows[0]["url"]) == "f1"


# --- a whole run ------------------------------------------------------------------------------------------------------

class Client:
    """Stands in for ForYou: answers each cell by which cell it is."""

    def __init__(self, community_out=None, listing=None, docs=None, sheet=None):
        self.community_out, self.listing, self.docs, self.sheet = community_out, listing, docs, sheet
        self.asked = []

    def cell(self, body, params=None, thought="", budget=0):
        self.asked.append(body)
        if body is community._CELL:
            return self.community_out
        if body is folders._LIST:
            return self.listing
        if body is folders._READ:
            return self.docs(params) if callable(self.docs) else self.docs
        if body is myra._CELL:
            return self.sheet
        raise AssertionError("an unknown cell")


def everything_writer(system, user):
    if "public online arguments" in system:
        return community_answer(system, user)
    if "post ANGLES" in system:
        return {"angles": [{"title": f"Sudut {i}", "summary": "Ringkasan.", "why": "Kenapa.", "cite": f"hlm {i}",
                            "domain": "kosmetik"} for i in (1, 2)]}
    return {"items": [{"i": i, "relevant": True, "domain": "kosmetik", "summary": "Ringkasan MYRA.", "why": "Kenapa."}
                      for i in range(20)]}


def store(**kw):
    return FakeStore(semasa_watch=kw.get("watch", []), semasa_ideas=kw.get("ideas", []),
                     semasa_settings=kw.get("settings", []), semasa_log=[])


def full_client():
    return Client(
        community_out={"posts": cell_posts(2), "videos": [], "reddit_error": "", "youtube_error": "quota"},
        listing={"files": [{"id": "p1", "name": "guide.pdf", "size": 10, "folder": "Cosmetic", "domain": "kosmetik", "modified": "2026-08-29"}],
                 "errors": []},
        docs={"docs": [{"id": "p1", "kind": "pdf", "pages": 3, "text": "Teks panduan. " * 40}], "skipped": []},
        sheet={"rows": SHEET, "error": ""})


def test_a_full_run_writes_each_section_once_and_a_second_run_writes_nothing_new():
    s, w = store(), Writer(everything_writer)
    rep = intake.run(s, w, full_client(), now=NOW)
    rows = s.tables["semasa_watch"]
    by = {}
    for r in rows:
        by.setdefault(r["section"], []).append(r)
    assert len(by["reddit"]) == 2 and sum(1 for r in by["reddit"] if r["relevant"]) == 1     # one shown, one hidden marker
    assert len(by["folder"]) == 2 and all(r["url"].startswith("onedrive://p1#") for r in by["folder"])
    assert len(by["myra"]) == 3 and rep["community"]["youtube_error"] == "quota"
    assert rep["folders"]["angles"] == 2 and rep["myra"]["new"] == 3
    saved = next(r for r in s.tables["semasa_settings"] if r["key"] == "sources")["value"]
    assert saved["report"]["community"]["ok"] is True and saved["last_run"]
    again = intake.run(s, w, full_client(), now=NOW)
    assert len(s.tables["semasa_watch"]) == len(rows) and again["myra"]["new"] == 0 and again["community"]["new"] == 0


def test_a_dry_run_reads_and_judges_but_writes_nothing():
    s = store()
    rep = intake.run(s, Writer(everything_writer), full_client(), now=NOW, dry=True)
    assert s.tables["semasa_watch"] == [] and not s.tables["semasa_settings"] and rep["folders"]["angles"] == 2


def test_one_dead_source_does_not_stop_the_other_two():
    c = full_client()
    c.sheet = {"rows": [], "error": "403 The caller does not have permission"}
    rep = intake.run(store(), Writer(everything_writer), c, now=NOW)
    assert rep["myra"]["ok"] is False and "403" in rep["myra"]["error"]
    assert rep["community"]["ok"] and rep["folders"]["ok"]


def test_the_missing_sql_is_named_not_swallowed():
    class Refuses(FakeStore):
        def table(self, name):
            q = super().table(name)
            if name == "semasa_watch":
                real = q.upsert

                def upsert(*a, **k):
                    raise RuntimeError('new row violates check constraint "semasa_watch_section_check"')
                q.upsert = upsert
                del real
            return q
    s = Refuses(semasa_watch=[], semasa_ideas=[], semasa_settings=[], semasa_log=[])
    with pytest.raises(intake.NeedsMigration) as e:
        intake.run(s, Writer(everything_writer), full_client(), now=NOW)
    assert "024_sources.sql" in str(e.value)


def test_a_file_the_writer_could_not_read_is_tried_again_and_a_file_with_no_angles_is_not():
    class Silent(Writer):
        pass
    c = full_client()
    rep = intake.run(store(), Writer(lambda s, u: None if "post ANGLES" in s else everything_writer(s, u)), c, now=NOW)
    assert rep["folders"]["mined"] == 0 and any("will retry" in e for e in rep["folders"]["errors"])
    s = store()
    intake.run(s, Writer(lambda sy, u: {"angles": []} if "post ANGLES" in sy else everything_writer(sy, u)), full_client(), now=NOW)
    marker = [r for r in s.tables["semasa_watch"] if r["url"] == "onedrive://p1#0"]
    assert len(marker) == 1 and marker[0]["relevant"] is False


def test_the_matrix_pool_is_topped_up_to_its_size_and_only_as_rows_are_used():
    doc = lambda p: {"docs": [{"id": "m1", "kind": "matrix", "rows": [   # noqa: E731
        {"row": n, "cite": "c", "en": f"Teks {n}.", "bm": "b", "visual": "v", "design": "d"} for n in (2, 3, 4)][:p["matrix"]["want"]]}],
        "skipped": []}
    listing = {"files": [{"id": "m1", "name": "x.xlsx", "size": 5, "folder": "Cosmetic Case Studies", "domain": "kajian_kes"}],
               "errors": []}
    s = store(settings=[{"key": "sources", "value": {"folders": {"matrix_pool": 3}}}])
    c = Client(community_out={"posts": [], "videos": []}, listing=listing, docs=doc, sheet={"rows": [], "error": ""})
    intake.run(s, Writer(everything_writer), c, now=NOW, only=["folders"])
    assert sorted(r["url"] for r in s.tables["semasa_watch"]) == ["onedrive://m1#r2", "onedrive://m1#r3", "onedrive://m1#r4"]
    intake.run(s, Writer(everything_writer), c, now=NOW, only=["folders"])                 # pool full: nothing is read
    assert len(s.tables["semasa_watch"]) == 3 and c.asked.count(folders._READ) == 1
    s.tables["semasa_ideas"].append({"source_url": "onedrive://m1#r2", "status": "drafted"})   # one row used: one refill
    d = lambda p: {"docs": [{"id": "m1", "kind": "matrix", "rows": [   # noqa: E731
        {"row": n, "cite": "", "en": f"Teks {n}.", "bm": "", "visual": "", "design": ""} for n in (5, 6)][:p["matrix"]["want"]]}],
        "skipped": []}
    c.docs = d
    intake.run(s, Writer(everything_writer), c, now=NOW, only=["folders"])
    assert "onedrive://m1#r5" in {r["url"] for r in s.tables["semasa_watch"]} and len(s.tables["semasa_watch"]) == 4


# --- what autofill and the writer do with them ------------------------------------------------------------------------

def test_stored_source_hands_the_writer_the_rows_own_words_and_withholds_the_address():
    for url in ("https://www.reddit.com/r/malaysia/comments/a1/x", "https://youtu.be/abc", "onedrive://f1#2", "myra://2026-09-28-1"):
        got = ideas.stored_source({"source_url": url, "source_title": "T", "source_summary": "Ringkasan."})
        assert got["ok"] is True and got["url"] is None and got["text"] == "Ringkasan."
    assert ideas.stored_source({"source_url": "https://www.npra.gov.my/x", "source_summary": "s"}) is None
    assert ideas.stored_source({"source_url": "https://notreddit.com/x", "source_summary": "s"}) is None
    assert ideas.stored_source({"source_url": "onedrive://f1#2", "source_summary": ""})["ok"] is False


def test_autofill_keeps_the_folder_bank_beyond_the_news_window_and_gives_an_urgent_file_its_day():
    old = "2026-05-01T00:00:00+00:00"
    watch = [
        {"id": "n1", "section": "regulatory", "url": "https://n/1", "title": "News", "relevant": True, "dismissed": False,
         "domain": "kosmetik", "created_at": "2026-09-29T00:00:00+00:00"},
        {"id": "b1", "section": "folder", "url": "onedrive://f#1", "title": "Bank", "relevant": True, "dismissed": False,
         "domain": "halal_my", "created_at": old, "raw": {}},
        {"id": "b2", "section": "folder", "url": "onedrive://f#2", "title": "Used", "relevant": True, "dismissed": False,
         "domain": "halal_my", "created_at": old, "raw": {}},
        {"id": "u1", "section": "folder", "url": "onedrive://g#1", "title": "Rush", "relevant": True, "dismissed": False,
         "domain": "makanan", "created_at": old, "raw": {"urgent_for": "2026-10-01"}},
    ]
    s = store(watch=watch, ideas=[{"source_url": "onedrive://f#2", "status": "drafted"}])
    pool = autofill.candidates(s, NOW)
    assert {r["id"] for r in pool} == {"n1", "b1", "u1"}
    assert autofill.pick(pool, "regulab", ["kosmetik"], "2026-10-01")["id"] == "u1"           # urgent, off-rota, its own day
    assert autofill.pick(pool, "regulab", ["halal_my"], "2026-10-02")["id"] == "b1"
    assert autofill.pick(pool, "regulab", ["fatwa"], "2026-10-02") is None
