"""The one controlled nexabot.id generation (backend/semasa/nexabot_generate.py): its pure decisions (spend guard, click
allow-list, network write guard, job-JSON shapes) and a real browser against a fake studio served from memory. No network. The
browser tests need SEMASA_CHROME."""

import json
import os
import pathlib
import shutil
import subprocess

import pytest

from semasa import nexabot_generate as gen

SRC = pathlib.Path(gen.__file__).read_text()
LABEL = "Generate 0.5 CREDITS ♾️ Unlimited"


# --- the spend guard ------------------------------------------------------------------------------

def test_numbers_are_read_from_the_right_side_of_the_word_credits():
    assert gen.parse_balance("CREDITS 0 UNLIMITED") == 0.0 and gen.parse_balance("Credits: 120") == 120.0
    assert gen.parse_balance("CREDITS\n12.5") == 12.5 and gen.parse_balance("CREDITS 1,000") == 1000.0
    assert gen.parse_balance("Generate 0.5 CREDITS ♾️ Unlimited") is None        # a price is not a balance
    assert gen.parse_price("Generate 0.5 CREDITS") == 0.5 and gen.parse_price("0,5 credit") == 0.5
    assert gen.parse_price("CREDITS 0") is None and gen.parse_price("Generate") is None
    assert gen.is_unlimited("UNLIMITED") and gen.is_unlimited("x ♾️") and not gen.is_unlimited("CREDITS 0")


@pytest.mark.parametrize("balance,label,allowed,word", [
    ("CREDITS 0 UNLIMITED", LABEL, True, "UNLIMITED"),                                   # the real studio on 17 Nov 2026
    ("CREDITS 0", "Generate 0.5 CREDITS", False, "below the price"),                      # no badge, nothing to pay with
    ("CREDITS 0", "Generate 2 CREDITS", False, "cap"),                                    # above the cap, credits 0, no badge
    ("CREDITS 0", "Generate 1.5 CREDITS", False, "cap"),
    ("CREDITS 0 UNLIMITED", "Generate 5 CREDITS ♾️", False, "cap"),             # even a badge does not lift the cap
    ("CREDITS 50", "Generate 5 CREDITS", False, "cap"),
    ("CREDITS 5", "Generate 0.5 CREDITS", True, "covers"),
    ("CREDITS 0", "Generate", False, "could not be read"),
    ("CREDITS 0 UNLIMITED", "Generate", True, "UNLIMITED"),
    ("", "Generate 1 CREDIT", True, "within the cap"),                                    # exactly the cap is allowed
    ("CREDITS 100", "Generate 1.01 CREDITS", False, "cap"),
])
def test_the_spend_guard_decision(balance, label, allowed, word):
    d = gen.spend_decision(balance, label)
    assert d.allowed is allowed and word in d.why, d


def test_the_spend_cap_is_one_constant_and_a_decision_can_be_given_another():
    assert gen.SPEND_CAP_CREDITS == 1.0 and "SPEND_CAP_CREDITS" in SRC
    assert not gen.spend_decision("CREDITS 9", "Generate 2 CREDITS").allowed
    assert gen.spend_decision("CREDITS 9", "Generate 2 CREDITS", cap=2).allowed


# --- the click allow-list ----------------------------------------------------------------------

def _st(**kw):
    return gen.ClickState(**{"orientation": "portrait", "resolution": "720p", **kw})


@pytest.mark.parametrize("role,name", [
    ("button", "Text to Video"), ("menuitem", "Text to Video"), ("button", "Portrait"), ("button", "Portrait 9:16"),
    ("button", "720p"), ("button", "Generate"), ("button", "Generate 0.5 CREDITS ♾️ Unlimited"),
    ("button", "⚡ Generate"), ("textbox", "Describe your video"), ("button", "Start Frame to Video 1-1 img"),
])
def test_what_the_allow_list_lets_through(role, name):
    assert gen.click_allowed(role, name, _st())[0], (role, name)


@pytest.mark.parametrize("role,name", [
    ("button", "Choose payment mode"), ("button", "CANCEL ALL"), ("button", "DELETE ALL"), ("button", "Open member chat"),
    ("button", "Landscape"), ("button", "1080p"),                                        # the options that were NOT asked for
    ("button", "Generate all"), ("button", "Generate and pay"), ("button", "Regenerate"), ("button", "Cancel generate"),
    ("button", "Log out"), ("button", "Sign out"), ("button", "Top up"), ("button", "Buy credits"),
    ("button", "Credits & Wallet"),
    ("link", "Video Generator"), ("link", "Generate"), ("link", "API Keys"), ("link", "Dashboard"), ("button", "API Keys"),
    ("button", "Commission"), ("button", "Settings"), ("button", ""), ("button", "Image to Video"), ("div", "Portrait"),
    ("button", "Download"), ("button", "Delete"), ("button", "Ingredients to Video 1-3 img"),
])
def test_everything_outside_the_allow_list_is_refused(role, name):
    ok, why = gen.click_allowed(role, name, _st(menu_open=True))
    # an "Ingredients to Video" item is the only name that may differ with the menu: with it open, it is refused too
    assert not ok, (role, name, why)


def test_while_the_mode_menu_is_closed_only_the_mode_button_may_carry_another_modes_name():
    assert gen.click_allowed("button", "Ingredients to Video 1-3 img", _st(menu_open=False))[0]
    assert not gen.click_allowed("menuitem", "Ingredients to Video 1-3 img", _st(menu_open=True))[0]
    assert not gen.click_allowed("menuitem", "Reference Video to Video video+img", _st(menu_open=True))[0]
    assert gen.click_allowed("menuitem", "Text to Video", _st(menu_open=True))[0]


def test_the_orientation_and_resolution_asked_for_are_the_only_ones_allowed():
    landscape = _st(orientation="landscape", resolution="1080p")
    assert gen.click_allowed("button", "Landscape", landscape)[0] and gen.click_allowed("button", "1080p", landscape)[0]
    assert not gen.click_allowed("button", "Portrait", landscape)[0] and not gen.click_allowed("button", "720p", landscape)[0]


def test_generate_is_allowed_once_and_then_refused():
    st = _st()
    assert gen.click_allowed("button", "Generate", st)[0]
    st.generate_clicks = 1
    ok, why = gen.click_allowed("button", "Generate", st)
    assert not ok and "already clicked" in why
    assert not gen.click_allowed("button", "Generate 0.5 CREDITS", st)[0]


class FakeEl:
    def __init__(self, label):
        self.label, self.clicks = label, 0

    def get_attribute(self, _name):
        return self.label

    def inner_text(self):
        return self.label

    def click(self, timeout=0):
        self.clicks += 1


def test_the_clicker_counts_generate_before_it_clicks_and_never_clicks_a_refused_name():
    ck = gen.Clicker(_st())
    g, cancel, dele = FakeEl("Generate"), FakeEl("CANCEL ALL"), FakeEl("DELETE ALL")
    assert ck.click(g, "button") and g.clicks == 1 and ck.state.generate_clicks == 1
    assert not ck.click(g, "button") and g.clicks == 1                      # a second Generate click is never made
    assert not ck.click(cancel, "button") and not ck.click(dele, "button")
    assert cancel.clicks == 0 and dele.clicks == 0
    assert len(ck.clicked) == 1 and len(ck.refused) == 3

    class Boom(FakeEl):
        def click(self, timeout=0):
            raise RuntimeError("the click failed")

    ck2 = gen.Clicker(_st())
    with pytest.raises(RuntimeError):
        ck2.click(Boom("Generate"), "button")
    assert ck2.state.generate_clicks == 1                                   # counted before the click: a failure is not retried
    assert not ck2.click(FakeEl("Generate"), "button")


def test_the_source_has_one_guarded_click_and_nothing_that_navigates_or_submits():
    import re
    assert SRC.count(".click(timeout") == 1                                  # the one real click, on the element
    assert all(m == "ck" for m in re.findall(r"(\w+)\.click\((?!timeout)", SRC)), "every other click goes through the Clicker"
    assert "click_allowed(role, name, self.state)" in SRC.split(".click(timeout")[0].rsplit("def click", 1)[1]
    for bad in (".dblclick(", ".tap(", ".reload(", ".go_back(", ".go_forward(", ".check(", ".select_option(", ".set_input_files(",
                ".press(", "keyboard.", ".hover(", ".drag_to(", ".dispatch_event(", ".submit(", "click()", "requestSubmit"):
        assert bad not in SRC, bad
    assert SRC.count(".goto(") == 1
    for bad in ('.post(', '.put(', '.delete(', '.patch(', '.fetch('):
        assert bad not in SRC, bad
    assert not re.search(r"method:\s*['\"]", SRC), "no write is made from inside the page"
    assert "fetch(" not in SRC.replace("await fetch(src)", ""), "the only in-page fetch is the blob read"

    for sink in ("telegram", "supabase", "import-video", "video_import", "semasa-import"):
        assert sink not in SRC.lower().replace("no telegram, no supabase, no import call", "").replace(
            "nothing is sent to telegram, supabase", ""), sink


# --- the network write guard ----------------------------------------------------------------------

def test_write_guard_lets_one_job_post_through_and_aborts_every_other_write():
    g = gen.GuardState()
    jobs, other = "https://nexabot.id/api/v1/jobs", "https://nexabot.id/api/v1/other"
    assert gen.write_allowed("GET", jobs + "?scope=&limit=20", g)[0]                  # reads are free
    assert not gen.write_allowed("POST", jobs, g)[0], "a POST before Generate is armed"
    g.armed = True
    assert gen.write_allowed("POST", jobs, g) == (True, "the job-creating write, once")
    ok, why = gen.write_allowed("POST", jobs, g)
    assert not ok and "already took" in why                                               # never twice, even armed
    assert not gen.write_allowed("POST", jobs + "?x=1", g)[0]
    assert gen.write_allowed("POST", other, g)[0]                                         # a different path, once
    for method, url in [("POST", "https://nexabot.id/video-generator"), ("POST", "https://nexabot.id/login"),
                        ("POST", "https://nexabot.id/"), ("POST", "https://evil.example/api/v1/jobs"),
                        ("POST", "https://cdn.nexabot.id/api/v1/jobs"), ("PUT", "https://nexabot.id/api/v1/x"),
                        ("PATCH", "https://nexabot.id/api/v1/x"), ("DELETE", "https://nexabot.id/api/v1/jobs/1"),
                        ("POST", "http://nexabot.id/api/v1/jobs2")]:
        assert not gen.write_allowed(method, url, g)[0], (method, url)


@pytest.mark.parametrize("path", [
    "/api/v1/payment", "/api/payments/create", "/api/checkout", "/api/v1/top-up", "/api/topup", "/api/wallet/add",
    "/api/credits/buy", "/api/v1/credits", "/api/commission/withdraw", "/api/v1/jobs/delete", "/api/v1/jobs/cancel",
    "/api/v1/jobs/cancel-all", "/api/auth/logout", "/api/auth/signout", "/api/chat/messages", "/api/api-keys",
    "/api/v1/keys/apikeys", "/api/billing/portal", "/api/v1/subscribe", "/api/account/delete", "/api/settings",
])
def test_a_money_account_chat_or_key_write_is_never_sent_even_armed_and_under_api(path):
    g = gen.GuardState(armed=True)
    ok, why = gen.write_allowed("POST", "https://nexabot.id" + path, g)
    assert not ok and ("payment" in why or "path" in why or "private" in why), (path, why)
    assert not g.posts


def test_the_keys_page_and_sign_out_are_not_fetched_even_as_reads():
    g = gen.GuardState(armed=True)
    for u in ("https://nexabot.id/api-keys", "https://nexabot.id/logout", "https://nexabot.id/api/v1/api-keys"):
        assert not gen.write_allowed("GET", u, g)[0], u
    assert gen.write_allowed("GET", "https://nexabot.id/api/v1/jobs?limit=1", g)[0]


def test_at_most_a_few_distinct_post_paths_are_let_through():
    g = gen.GuardState(armed=True)
    got = [gen.write_allowed("POST", f"https://nexabot.id/api/v1/p{i}", g)[0] for i in range(6)]
    assert got == [True] * gen.MAX_POSTS + [False] * (6 - gen.MAX_POSTS)


class Req:
    def __init__(self, method, url):
        self.method, self.url = method, url


class Route:
    def __init__(self, method, url):
        self.request, self.did = Req(method, url), ""

    def abort(self):
        self.did = "abort"

    def fallback(self):
        self.did = "fallback"


def test_the_route_handler_aborts_notes_and_lets_the_job_post_continue():
    g, blocked, allowed = gen.GuardState(), [], []
    h = gen.guard_route(g, blocked, allowed)
    r = Route("POST", "https://nexabot.id/api/track?id=1")
    h(r)
    assert r.did == "abort" and blocked == ["POST nexabot.id/api/track (a write before Generate was armed)"]
    g.armed = True
    r = Route("POST", "https://nexabot.id/api/v1/jobs")
    h(r)
    assert r.did == "fallback" and allowed == ["POST nexabot.id/api/v1/jobs"]
    r = Route("POST", "https://nexabot.id/api/v1/jobs")
    h(r)
    assert r.did == "abort"                                                                # the second one never leaves
    r = Route("GET", "https://nexabot.id/api/v1/jobs?limit=20")
    h(r)
    assert r.did == "fallback" and len(allowed) == 1


# --- the job JSON ---------------------------------------------------------------------------------

def test_a_shape_keeps_names_and_types_and_only_the_value_of_enum_like_fields():
    obj = {"ok": True, "job": {"id": "job_8x2abc", "status": "processing", "prompt": "a secret prompt", "orientation": "portrait",
                               "progress": 40, "videoUrl": "https://cdn.x/v/a.mp4?sig=SECRETSIG", "email": "wan@example.com",
                               "history": [{"status": "queued", "at": "2026-11-17T00:00:00Z"}], "empty": [], "n": None}}
    shape = gen.shape_of(obj)
    blob = json.dumps(shape)
    assert shape["job"]["status"] == "processing" and shape["job"]["orientation"] == "portrait"
    assert shape["job"]["prompt"] == "str" and shape["job"]["progress"] == "number" and shape["ok"] == "bool"
    assert shape["job"]["history"] == {"list": 1, "item": {"status": "queued", "at": "str"}}
    assert shape["job"]["empty"] == {"list": 0, "item": None} and shape["job"]["n"] == "null"
    for leak in ("SECRETSIG", "wan@example.com", "a secret prompt", "job_8x2abc", "cdn.x"):
        assert leak not in blob


def test_video_links_are_found_best_first_and_thumbnails_are_not_video():
    obj = {"thumbnail": "https://c/t.jpg", "posterUrl": "https://c/p.png", "result": {"video": "https://c/v/final.mp4?sig=1"},
           "download_url": "https://c/d/x", "other": ["https://c/z.webm"], "link": "https://c/page"}
    assert gen.find_video_urls(obj) == ["https://c/v/final.mp4?sig=1", "https://c/z.webm", "https://c/d/x"]
    assert gen.find_video_urls({"a": "not a url", "thumb_url": "https://c/t.jpg"}) == []


def test_a_video_address_is_masked_and_its_query_signature_dropped():
    m = gen.mask_url("https://cdn.example.com/out/0123456789abcdef0123/clip.mp4?Signature=SECRETSIG&Expires=1")
    assert m == "https://cdn.example.com/out/:id/clip.mp4 (query signature dropped)" and "SECRETSIG" not in m
    assert gen.mask_url("https://cdn.example.com/v/ab3fe91c7d02a4c5e6.mp4") == "https://cdn.example.com/v/:id.mp4"


def test_status_values_are_sorted_into_done_failed_and_pending():
    for s in ("completed", "Succeeded", "DONE", "finished", "ready"):
        assert gen.classify_status(s) == "done"
    for s in ("failed", "Error", "cancelled", "CANCELED", "timeout"):
        assert gen.classify_status(s) == "failed"
    assert gen.classify_status("queued") == "pending" and gen.classify_status("processing") == "pending"
    assert gen.classify_status("") == ""


def test_the_tracker_never_takes_an_older_job_for_ours():
    tr = gen.Tracker()
    old = {"ok": True, "jobs": [{"id": "old1", "status": "completed", "videoUrl": "https://c/old.mp4"}]}
    tr.feed("GET", "/api/v1/jobs?scope=&limit=", 200, old)                       # before Generate: the baseline
    tr.live = True
    tr.feed("GET", "/api/v1/jobs?scope=&limit=", 200, old)
    assert tr.outcome()[0] == "none"
    new = {"ok": True, "jobs": [{"id": "new2", "status": "queued"}, old["jobs"][0]]}
    tr.feed("POST", "/api/v1/jobs", 200, {"ok": True, "job": {"id": "new2", "status": "queued"}})
    tr.feed("GET", "/api/v1/jobs?scope=&limit=", 200, new)
    assert tr.outcome() == ("pending", "queued", "")
    new["jobs"][0] = {"id": "new2", "status": "completed", "videoUrl": "https://c/new.mp4?sig=1"}
    tr.feed("GET", "/api/v1/jobs?scope=&limit=", 200, new)
    assert tr.outcome() == ("done", "completed", "https://c/new.mp4?sig=1") and tr.statuses == ["queued", "completed"]
    assert any(r["has_video_url"] for r in tr.shapes) and tr.shapes[0]["method"] == "GET"
    assert next(r for r in tr.shapes if r["method"] == "POST")["shape"]["job"]["status"] == "queued"


def test_a_failed_job_and_an_envelope_with_a_success_status_are_told_apart():
    tr = gen.Tracker()
    tr.live = True
    tr.feed("GET", "/api/x", 200, {"status": "success", "data": {"n": 1}})        # an envelope, not a job: no id, not in a list
    assert tr.outcome()[0] == "none"
    tr.feed("GET", "/api/v1/jobs", 200, {"jobs": [{"id": "j1", "state": "failed"}]})
    assert tr.outcome()[:2] == ("failed", "failed")


# --- download and ffprobe -------------------------------------------------------------------------

class FakeResp:
    def __init__(self, body=b"", status=200, ctype="video/mp4", length=None):
        self._b, self.status, self.ok = body, status, 200 <= status < 300
        self.headers = {"content-type": ctype, **({"content-length": str(length)} if length is not None else {})}

    def body(self):
        return self._b

    def json(self):
        return json.loads(self._b)


class FakePage:
    url = "https://nexabot.id/video-generator"


MP4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x00" * 64


def test_download_saves_an_mp4_under_the_cap_and_masks_the_address(tmp_path):
    seen = []

    def getter(url, timeout=0):
        seen.append(url)
        return FakeResp(MP4)

    url = "https://cdn.x.com/v/clip.mp4?sig=SECRETSIG"
    out = gen.download_video(None, FakePage(), url, tmp_path / "video.mp4", getter=getter)
    assert out["saved"] and (tmp_path / "video.mp4").read_bytes() == MP4 and out["bytes"] == len(MP4)
    assert "SECRETSIG" not in json.dumps(out) and seen == ["https://cdn.x.com/v/clip.mp4?sig=SECRETSIG"]


def test_download_skips_a_file_over_the_cap_a_non_mp4_and_a_refusal(tmp_path):
    big = gen.download_video(None, FakePage(), "https://c/v.mp4", tmp_path / "a.mp4",
                             getter=lambda u, timeout=0: FakeResp(b"", length=gen.MAX_VIDEO_BYTES + 1))
    assert not big["saved"] and big["bytes"] == gen.MAX_VIDEO_BYTES + 1 and "not saved" in big["reason"]
    over = gen.download_video(None, FakePage(), "https://c/v.mp4", tmp_path / "b.mp4", cap=10,
                              getter=lambda u, timeout=0: FakeResp(MP4))
    assert not over["saved"] and over["bytes"] == len(MP4) and not (tmp_path / "b.mp4").exists()
    html = gen.download_video(None, FakePage(), "https://c/v.mp4", tmp_path / "c.mp4",
                              getter=lambda u, timeout=0: FakeResp(b"<html>denied</html>"))
    assert not html["saved"] and "not an MP4" in html["reason"]
    gone = gen.download_video(None, FakePage(), "https://c/v.mp4", tmp_path / "d.mp4",
                              getter=lambda u, timeout=0: FakeResp(status=403))
    assert not gone["saved"] and "403" in gone["reason"]

    def boom(u, timeout=0):
        raise RuntimeError("network down")

    assert "failed" in gen.download_video(None, FakePage(), "https://c/v.mp4", tmp_path / "e.mp4", getter=boom)["reason"]


def test_inputs_are_checked_before_anything_opens():
    assert gen.check_inputs("  a clean bench  ", "portrait", "720p") == "a clean bench"
    for args in (("", "portrait", "720p"), ("ab", "portrait", "720p"), ("x" * 801, "portrait", "720p"),
                 ("ok prompt", "square", "720p"), ("ok prompt", "portrait", "4k"), ("bad \x00 prompt", "portrait", "720p")):
        with pytest.raises(ValueError):
            gen.check_inputs(*args)
    assert gen.main(["g", "/tmp/never", "--orientation", "square"]) == 2
    assert gen.DEFAULT_PROMPT.startswith("A slow cinematic push-in") and "no people, no text" in gen.DEFAULT_PROMPT


def test_the_report_is_redacted_and_holds_calls_never_headers_or_signatures():
    cfg = gen.Config("a bench with key nxb_live_8f3a9c2d1e7b4a5c9d0e1f2a3b4c5d6e")
    body = {"outcome": "generated", "outcome_line": "ok", "clicked": ["button: Generate"], "refused_clicks": [],
            "generate_clicks": 1,
            "job_shapes": [], "statuses_seen": [], "writes_allowed": [], "blocked_writes": [], "problems": [], "notes": [],
            "screenshots": ["01.png"], "video": {"url": "https://c/:id.mp4", "saved": True, "bytes": 5, "reason": ""}}
    ev = [{"method": "POST", "url": "https://nexabot.id/api/v1/jobs?token=abc", "status": 200, "resource_type": "fetch",
           "headers": {"cookie": "x"}}]
    rep = gen.build_report(started="t", final_url="https://nexabot.id/video-generator?x=1#y", title="T", login_names=["s"],
                           cfg=cfg, body=body, events=ev)
    blob = json.dumps(rep) + gen.render_md(rep)
    assert "nxb_live" not in blob and '"headers"' not in blob and "x=1" not in blob
    assert rep["requests"] == [{"method": "POST", "path": "/api/v1/jobs?token=", "status": 200, "count": 1}]
    assert rep["redactions"] >= 1


# --- the workflow ---------------------------------------------------------------------------------

def test_the_workflow_is_manual_guarded_short_lived_and_takes_inputs_through_the_environment():
    raw = (pathlib.Path(__file__).parents[2] / ".github/workflows/nexabot-generate.yml").read_text()
    flow = "\n".join(line for line in raw.splitlines() if not line.lstrip().startswith("#"))
    assert "workflow_dispatch" in flow and "schedule" not in flow and "push:" not in flow and "pull_request" not in flow
    assert "workflow_run" not in flow and "workflow_call" not in flow
    assert "github.repository != 'wanshah07/argus'" in flow and "contents: read" in flow
    assert "timeout-minutes: 25" in flow and "retention-days: 1" in flow
    assert "NEXABOT_STORAGE_STATE_B64" in flow and "SUPABASE" not in flow and "TELEGRAM" not in flow.upper()
    for inp in ("prompt:", "orientation:", "resolution:", "options: [portrait, landscape]", "options: [720p, 1080p]",
                "default: portrait", "default: 720p"):
        assert inp in flow, inp
    assert "A slow cinematic push-in on a clean laboratory bench" in flow
    assert "NB_PROMPT: ${{ inputs.prompt }}" in flow and '--prompt "$NB_PROMPT"' in flow
    run_text = flow.split("run: |", 1)[1] if "run: |" in flow else flow
    assert "${{ inputs." not in run_text.split("Summary")[0], "an input must never be pasted into shell text"
    assert "ensure-ffmpeg.sh" in flow and "ensure-chromium.sh" in flow


# --- a real browser against a fake studio (needs SEMASA_CHROME) ----------------------------------------------------------

STUDIO = """<!doctype html><meta charset="utf-8"><title>NEXABOT fake</title>
<header><span>CREDITS 0</span> <span id="badge">{BADGE}</span> <button>Open member chat</button></header>
<aside><a href="/api-keys">API Keys</a><a href="/dashboard">Dashboard</a></aside>
<main><h1>What do you want to bring to life?</h1>
<button id="mode" aria-haspopup="menu" aria-expanded="false">{MODE}</button>
<div id="menu" role="menu" hidden><button role="menuitem" id="t2v">Text to Video</button>
 <button role="menuitem">Start Frame to Video 1-1 img</button><button role="menuitem">Ingredients to Video 1-3 img</button>
 <button role="menuitem">Reference Video to Video video+img</button></div>
<button aria-pressed="false">Landscape</button><button aria-pressed="false">Portrait</button>
<button aria-pressed="false">720p</button><button aria-pressed="false">1080p</button>
<textarea placeholder="Describe your video… e.g. A cinematic drone shot" {HIDE}></textarea>
<button id="gen" disabled>Generate <span>{PRICE}</span> <span>{INF}</span></button>
<button>Choose payment mode</button><button>CANCEL ALL</button><button>DELETE ALL</button>
<section id="results"><h2>RESULTS</h2><div id="list">No generations yet</div></section></main>
<script>
window.__clicks = [];
document.addEventListener('click', (e) => { const b = e.target.closest('button,a');
  if (b) window.__clicks.push((b.innerText || '').split('\\n')[0].trim()); }, true);
const box = document.querySelector('textarea'), gen = document.getElementById('gen'), opts = {};
document.querySelectorAll('button[aria-pressed]').forEach((b) => b.addEventListener('click', () => {
  const grp = /^(Land|Port)/.test(b.innerText) ? /^(Land|Port)/ : /p$/;
  document.querySelectorAll('button[aria-pressed]').forEach((x) => {
    if (grp.test(x.innerText)) x.setAttribute('aria-pressed', 'false'); });
  b.setAttribute('aria-pressed', 'true'); }));
box.addEventListener('input', () => { gen.disabled = !box.value.trim(); });
document.getElementById('mode').onclick = () => { document.getElementById('menu').hidden = false; };
document.getElementById('t2v').onclick = () => { document.getElementById('mode').innerText = 'Text to Video';
  box.hidden = false; document.getElementById('menu').hidden = true; };
const vid = (j) => j.videoUrl ? '<video controls src="' + j.videoUrl + '"></video>' : '';
const render = (jobs) => { const l = document.getElementById('list');
  if (!jobs.length) { l.innerText = 'No generations yet'; return; }
  l.innerHTML = jobs.map((j) => '<div>' + j.status + vid(j) + '</div>').join(''); };
const load = async () => { try { const r = await fetch('/api/v1/jobs?scope=&limit=20');
  render((await r.json()).jobs || []); } catch (_) {} };
load(); setInterval(load, 400);
gen.onclick = async () => { if ({NOSEND}) return;
  await fetch('/api/v1/jobs', {method: 'POST', headers: {'content-type': 'application/json'},
    body: JSON.stringify({prompt: box.value, mode: 'text', orientation: 'portrait', resolution: '720p'})}); };
fetch('/api/track', {method: 'POST', body: 'x'});
</script>"""


class FakeStudio:
    """The studio and its API served from memory. `posts` and `requests` record what reached it; `final` is the status the job
    ends on."""

    def __init__(self, *, badge="UNLIMITED", inf="♾️ Unlimited", price="0.5 CREDITS", mode="Text to Video", final="completed",
                 nosend=False, video=MP4, old=True, steps_to_done=8):
        self.badge, self.inf, self.price, self.mode = badge, inf, price, mode
        self.final, self.nosend, self.video = final, nosend, video
        self.steps_to_done = steps_to_done
        old_job = {"id": "old999zzz", "status": "completed", "videoUrl": "https://cdn.fake.test/v/old.mp4?sig=OLDSIG"}
        self.jobs = [old_job] if old else []
        self.posts: list[tuple[str, dict]] = []
        self.requests: list[tuple[str, str]] = []
        self.gets_since = 0

    def html(self):
        return (STUDIO.replace("{BADGE}", self.badge).replace("{INF}", self.inf).replace("{PRICE}", self.price)
                .replace("{MODE}", self.mode).replace("{HIDE}", "" if self.mode == "Text to Video" else "hidden")
                .replace("{NOSEND}", "true" if self.nosend else "false"))

    def route(self, route):                                           # the fake network, behind the guard
        req = route.request
        self.requests.append((req.method, req.url))
        path = req.url.split("nexabot.id", 1)[-1].split("?")[0]
        if req.url.endswith("/video-generator"):
            return route.fulfill(status=200, content_type="text/html; charset=utf-8", body=self.html())
        if req.method == "POST" and path == "/api/v1/jobs":
            self.posts.append((path, json.loads(req.post_data or "{}")))
            self.jobs.insert(0, {"id": "new555abc", "status": "queued", "prompt": "x"})
            return route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True, "job": self.jobs[0]}))
        if req.method == "GET" and path == "/api/v1/jobs":
            return route.fulfill(status=200, content_type="application/json", body=json.dumps(self._list()))
        if "cdn.fake.test" in req.url:
            return route.fulfill(status=200, content_type="video/mp4", body=self.video)
        return route.fulfill(status=200, content_type="application/json", body="{}")

    def _list(self):
        if self.posts:
            self.gets_since += 1
            new = self.jobs[0]
            new["status"] = ("queued", "processing")[min(self.gets_since // 2, 1)]
            if self.gets_since >= self.steps_to_done:
                new["status"] = self.final
                if self.final == "completed":
                    new["videoUrl"] = "https://cdn.fake.test/v/new.mp4?sig=NEWSIG"
        return {"ok": True, "jobs": self.jobs}

    def getter(self, url, timeout=0):                               # the context's own GET, replaced
        self.requests.append(("GET*", url))
        assert url.startswith(("https://nexabot.id/api/v1/jobs", "https://cdn.fake.test/")), url
        if "cdn.fake.test" in url:
            return FakeResp(self.video)
        return FakeResp(json.dumps(self._list()).encode(), ctype="application/json")


browser = pytest.mark.skipif(not os.environ.get("SEMASA_CHROME"), reason="set SEMASA_CHROME to run a real browser")


def _make_mp4(path):
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        return None
    p = subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=160x284:rate=10:duration=1",
                        "-pix_fmt", "yuv420p", "-c:v", "libx264", str(path)], capture_output=True, timeout=60)
    return path.read_bytes() if p.returncode == 0 and path.exists() else None


def _short(clicked):
    """'button: Generate 0.5 CREDITS ...' -> 'button: Generate' (the click log carries the button's whole name)."""
    return [c.split(" 0.5 ")[0].split(" 5 CREDITS")[0] for c in clicked]


def _run(tmp_path, fake, **cfg):
    base = dict(wait_s=25, poll_s=0.3, start_s=3)
    code, rep = gen.run(tmp_path / "out", None, gen.Config("A clean bench, no people", **{**base, **cfg}), fake=fake.route,
                        getter=fake.getter)
    return code, rep, tmp_path / "out"


@browser
def test_one_generation_end_to_end_clicks_only_the_allow_list_and_saves_the_video(tmp_path):
    real = _make_mp4(tmp_path / "real.mp4")
    fake = FakeStudio(video=real or MP4)
    code, rep, out = _run(tmp_path, fake)
    assert code == 0 and rep["outcome"] == "generated", rep["outcome_line"]
    assert rep["generate_clicks"] == 1, rep["clicked"]
    assert _short(rep["clicked"]) == ["button: Portrait", "button: 720p", "button: Generate"], rep["clicked"]
    assert rep["refused_clicks"] == []
    assert len(fake.posts) == 1 and fake.posts[0][1]["prompt"] == "A clean bench, no people"      # exactly one job-creating POST
    assert rep["writes_allowed"] == ["POST nexabot.id/api/v1/jobs"]
    assert any(b.startswith("POST nexabot.id/api/track") for b in rep["blocked_writes"])    # the page's own write was aborted
    # nothing else was touched: no payment, cancel, delete, key or sign-out request ever reached the network
    for _m, u in fake.requests:
        assert not any(w in u for w in ("api-keys", "payment", "cancel", "delete", "logout", "wallet")), u
    assert rep["statuses_seen"] == ["queued", "processing", "completed"]
    assert rep["job_final_status"] == "completed" and rep["video"]["saved"] and rep["spend_guard"]["allowed"]
    assert (out / "video.mp4").read_bytes() == (real or MP4)                                 # the NEW job's, not the old one
    if real:
        ff = rep["ffprobe"]
        assert (ff["width"], ff["height"]) == (160, 284) and ff["vcodec"] == "h264" and ff["duration_s"] > 0.5
    shapes = {(s["method"], s["path"]) for s in rep["job_shapes"]}
    assert ("POST", "/api/v1/jobs") in shapes and any(m == "GET" and p.startswith("/api/v1/jobs") for m, p in shapes)
    post = next(s for s in rep["job_shapes"] if s["method"] == "POST")
    assert post["shape"]["job"]["status"] == "queued" and post["request_shape"]["orientation"] == "portrait"
    assert rep["balance_before"] == 0.0 and rep["unlimited_before"] and "0.5 CREDITS" in rep["generate_label_before"]
    assert rep["balance_text_after"] and rep["seconds_to_ready"] > 0
    assert len(rep["screenshots"]) >= 3 and all((out / s).exists() for s in rep["screenshots"])
    text = (out / "report.md").read_text() + (out / "report.json").read_text()
    for leak in ("NEWSIG", "OLDSIG", "old999zzz", "new555abc"):
        assert leak not in text, leak
    assert "## What did NOT work" in text and "Generate clicked: **1**" in text and "(query signature dropped)" in text


@browser
def test_the_spend_guard_stops_the_run_before_generate_when_the_price_is_over_the_cap(tmp_path):
    fake = FakeStudio(badge="", inf="", price="5 CREDITS")
    code, rep, out = _run(tmp_path, fake)
    assert code == 1 and rep["outcome"] == "stopped_spend_guard" and rep["generate_clicks"] == 0
    assert "cap" in rep["outcome_line"] and "Generate was NOT clicked" in rep["outcome_line"]
    assert fake.posts == [] and "button: Generate" not in _short(rep["clicked"])
    assert "Spend guard: **STOPPED**" in (out / "report.md").read_text()


@browser
def test_a_generate_that_starts_nothing_is_reported_and_never_clicked_again(tmp_path):
    fake = FakeStudio(nosend=True, old=False)
    code, rep, _out = _run(tmp_path, fake, start_s=2)
    assert code == 1 and rep["outcome"] == "not_started" and rep["generate_clicks"] == 1
    assert _short(rep["clicked"]).count("button: Generate") == 1 and fake.posts == []
    assert "not clicked again" in rep["outcome_line"] and "video" not in rep


@browser
def test_a_failed_job_is_reported_and_nothing_is_retried(tmp_path):
    fake = FakeStudio(final="failed")
    code, rep, _out = _run(tmp_path, fake)
    assert code == 1 and rep["outcome"] == "failed" and rep["generate_clicks"] == 1 and len(fake.posts) == 1
    assert rep["statuses_seen"][-1] == "failed" and "video" not in rep


@browser
def test_a_studio_in_another_mode_is_moved_to_text_to_video_without_choosing_another_mode(tmp_path):
    fake = FakeStudio(mode="Start Frame to Video 1-1 img")
    code, rep, _out = _run(tmp_path, fake)
    assert code == 0 and rep["clicked"][:2] == ["button: Start Frame to Video 1-1 img", "menuitem: Text to Video"], rep["clicked"]
    assert _short(rep["clicked"])[-1] == "button: Generate" and rep["generate_clicks"] == 1
    assert not any("Ingredients" in c or "Reference" in c for c in rep["clicked"])


@browser
def test_a_login_wall_ends_the_run_with_the_refused_login_message(tmp_path):
    def wall(route):
        if route.request.url.endswith("/video-generator"):
            return route.fulfill(status=302, headers={"location": "https://nexabot.id/login"})
        return route.fulfill(status=200, content_type="text/html", body="<!doctype html><title>Login</title><p>Masuk</p>")

    fake = FakeStudio()
    fake.route = wall
    code, rep, _out = _run(tmp_path, fake)
    assert code == 1 and rep["outcome"] == "login_refused" and "LOGIN WALL" in rep["outcome_line"]
    assert rep["generate_clicks"] == 0 and rep["clicked"] == [] and "record it again" in rep["outcome_line"]
