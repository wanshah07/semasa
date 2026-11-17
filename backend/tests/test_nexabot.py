"""The nexabot.id studio tooling, Phase A (ops/NEXABOT-LOGIN.md): the login checker's pure parts and the read-only probe.
No network. The browser test needs SEMASA_CHROME (a real Chromium) and serves a fake studio from memory."""

import base64
import json
import os
import pathlib
import sys

import pytest

from semasa import nexabot_check as chk
from semasa import nexabot_probe as pr

COOKIE = "c0ok1e-VALUE-should-never-print-9f8e7d"
TOKEN = "eyJhbGciOiJIUzI1NiJ9.TOKEN-VALUE-should-never-print.sig"


def _state(cookies=(), origins=()):
    return {"cookies": [{"name": n, "domain": d, "value": COOKIE, "path": "/"} for n, d in cookies], "origins": list(origins)}


# --- the checker: shrink, sizes, cookie names ---------------------------------------------------------------------------------

def test_login_cookie_names_are_matched_by_name_and_never_carry_a_value():
    st = _state([("__Secure-next-auth.session-token", ".nexabot.id"), ("csrf-token", "nexabot.id"), ("theme", "nexabot.id"),
                 ("sessionid", ".instagram.com"), ("Authorization", "app.nexabot.id"), ("session_x", "evilnexabot.id")])
    names = chk.login_cookie_names(st)
    assert names == ["Authorization", "__Secure-next-auth.session-token", "csrf-token"]
    assert COOKIE not in json.dumps(names)
    assert chk.login_cookie_names({}) == []


def test_shrink_keeps_only_this_sites_cookies_and_its_small_page_data():
    ls = {"origin": "https://nexabot.id", "localStorage": [{"name": "k", "value": "v"}]}
    other = {"origin": "https://www.facebook.com", "localStorage": [{"name": "big", "value": "x" * 90_000}]}
    st = _state([("session", ".nexabot.id"), ("c_user", ".facebook.com")], [ls, other])
    out, how = chk.shrink(st)
    assert [c["name"] for c in out["cookies"]] == ["session"]
    assert out["origins"] == [ls] and "saved page data" in how and "dropped" not in how


def test_shrink_drops_a_large_local_storage_and_decides_by_size():
    big = {"origin": "https://nexabot.id", "localStorage": [{"name": "k", "value": "x" * 60_000}]}
    out, how = chk.shrink(_state([("session", ".nexabot.id")], [big]))
    assert out["origins"] == [] and "too large" in how
    assert chk._encoded_size(out) <= chk.GITHUB_SECRET_LIMIT


def test_shrink_falls_back_to_the_login_looking_cookies_when_the_cookies_alone_are_too_big():
    st = {"cookies": [{"name": "session-token", "domain": ".nexabot.id", "value": "a"},
                      {"name": "junk", "domain": ".nexabot.id", "value": "z" * 60_000}], "origins": []}
    out, how = chk.shrink(st)
    assert [c["name"] for c in out["cookies"]] == ["session-token"] and "only the login-looking" in how


# --- the verdict: a pure function over a final URL, the cookie names, the status and the title ------------------

@pytest.mark.parametrize("url,names,status,title,code", [
    ("https://nexabot.id/video-generator", ["next-auth.session-token"], 200, "NEXABOT", "ok"),
    ("https://nexabot.id/video-generator?tab=video#x", [], 200, "NEXABOT", "ok"),
    ("https://nexabot.id/login", [], 200, "NEXABOT", "wall"),
    ("https://nexabot.id/login?callbackUrl=%2Fvideo-generator", ["x-auth"], 200, "NEXABOT", "wall"),
    ("https://nexabot.id/video-generator", [], 403, "Forbidden", "blocked"),
    ("https://nexabot.id/video-generator", [], 200, "Just a moment...", "blocked"),
    ("https://nexabot.id/", ["session"], 200, "NEXABOT", "other"),
    ("https://accounts.example.com/signin", [], 200, "x", "other"),
    ("", [], None, "", "other"),
])
def test_the_verdict_decision(url, names, status, title, code):
    got, line = chk.verdict(url, names, status, title)
    assert got == code and line.startswith("nexabot.id: ")
    assert COOKIE not in line


def test_the_verdict_lines_say_what_to_do_and_name_cookies_only_by_name():
    assert "LOGIN WALL" in chk.verdict("https://nexabot.id/login", [], 200, "")[1]
    assert "record it again" in chk.verdict("https://nexabot.id/login", [], 200, "")[1]
    ok = chk.verdict("https://nexabot.id/video-generator", ["next-auth.session-token"], 200, "")[1]
    assert "LOGGED IN" in ok and "next-auth.session-token" in ok
    assert "no cookie whose name contains" in chk.verdict("https://nexabot.id/video-generator", [], 200, "")[1]
    assert "BLOCKED" in chk.verdict("https://nexabot.id/video-generator", [], 429, "")[1]


def test_the_checker_prints_names_and_sizes_never_a_value_and_writes_the_base64(tmp_path, capsys, monkeypatch):
    path = tmp_path / "state.json"
    path.write_text(json.dumps(_state([("next-auth.session-token", ".nexabot.id"), ("other", ".example.com")])))
    out = tmp_path / "secret.txt"
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)      # no browser: stops after the file checks
    chk.main(["nexabot_check", str(path), "--b64", str(out)])
    printed = capsys.readouterr().out
    assert COOKIE not in printed and "next-auth.session-token" in printed
    assert "Base64 size" in printed and "48,000" in printed and "NEXABOT_STORAGE_STATE_B64" in printed
    assert json.loads(base64.b64decode(out.read_text())) == chk.shrink(json.loads(path.read_text()))[0]


# --- the probe's guard: which names may be clicked ------------------------------------------------------------------------

@pytest.mark.parametrize("name", [
    "Generate", "Generate video", "generate", "GENERATE 5 credits", "Create", "Buat video", "Buat", "Hasilkan", "Kirim", "Send",
    "Submit", "Start", "Pay now", "Bayar", "Buy credits", "Beli kredit", "Top up", "Top-up", "Topup", "Isi saldo", "Checkout",
    "Upgrade", "Upgrade to Pro", "Subscribe", "Confirm", "Log out", "Sign out", "Delete", "Run",
])
def test_a_name_that_could_spend_or_submit_is_refused(name):
    assert pr.is_forbidden(name), name


@pytest.mark.parametrize("name", ["Video", "Image", "Voice", "Music", "Text to video", "Model", "Omni Flash", "16:9", "10s",
                                  "Aspect ratio", "Quality", "Duration", "1080p", "", "Image to video"])
def test_a_plain_tab_or_option_name_is_allowed(name):
    assert not pr.is_forbidden(name), name


def test_only_tabs_and_menu_triggers_are_ever_opened():
    tab = {"role": "tab", "name": "Video", "type": "", "disabled": False}
    assert pr.may_open(tab)[0]
    assert pr.may_open({"role": "button", "name": "Model", "haspopup": "listbox"})[0]
    assert pr.may_open({"role": "combobox", "name": "Duration"})[0]
    assert pr.may_open({"role": "button", "name": "Options", "expanded": "false"})[0]
    # refused: a forbidden name, a submit button, a disabled one, a plain button, a link, an input
    assert not pr.may_open({"role": "tab", "name": "Generate"})[0]
    assert not pr.may_open({"role": "button", "name": "Model", "haspopup": "listbox", "type": "submit"})[0]
    assert not pr.may_open({"role": "tab", "name": "Video", "disabled": True})[0]
    assert not pr.may_open({"role": "button", "name": "Video"})[0]
    assert not pr.may_open({"role": "link", "name": "Video", "href": "/video", "expanded": "false"})[0]
    assert not pr.may_open({"role": "textbox", "name": "Prompt", "placeholder": "Describe your video"})[0]
    assert not pr.may_open({"role": "button", "name": "Buat video", "haspopup": "menu"})[0]
    assert "forbidden" in pr.may_open({"role": "tab", "name": "Pay"})[1]


def test_the_probe_source_has_no_click_but_the_guarded_one_and_never_types():
    src = pathlib.Path(pr.__file__).read_text()
    assert src.count(".click(") == 1 and "may_open(el)" in src.split(".click(")[0].split("for n, el in")[1]
    for bad in (".fill(", ".type(", ".press_sequentially(", ".check(", ".select_option(", ".set_input_files(",
                ".dblclick(", ".tap("):
        assert bad not in src, bad
    assert 'keyboard.press("Escape")' in src


# --- the network record: method, path, status, nothing else -------------------------------------------------------------------

def test_clean_path_masks_ids_and_keeps_query_keys_only():
    assert pr.clean_path("https://nexabot.id/api/auth/session") == "/api/auth/session"
    assert pr.clean_path("https://nexabot.id/api/chat/messages?limit=20&token=abc123SECRET") == "/api/chat/messages?limit=&token="
    assert pr.clean_path(f"https://nexabot.id/api/jobs/{TOKEN}") == "/api/jobs/:id"
    assert pr.clean_path("https://nexabot.id/api/jobs/123e4567-e89b-12d3-a456-426614174000/status") == "/api/jobs/:id/status"
    assert pr.clean_path("https://nexabot.id/api/jobs/987654321") == "/api/jobs/:id"
    assert pr.clean_path("https://nexabot.id/video-generator") == "/video-generator"
    assert pr.clean_path("https://nexabot.id/api/chat/messages") == "/api/chat/messages"
    assert pr.clean_path("https://nexabot.id/api/abc123def456") == "/api/:id"
    assert pr.clean_path("https://cdn.other.com/a.js") is None
    assert pr.clean_path("http://nexabot.id/a") is None


EVENTS = [
    {"method": "GET", "url": "https://nexabot.id/api/auth/session", "status": 200, "resource_type": "fetch",
     "headers": {"cookie": f"session={COOKIE}", "authorization": f"Bearer {TOKEN}"}, "post_data": f'{{"token":"{TOKEN}"}}',
     "body": f"{COOKIE}", "response_body": TOKEN},
    {"method": "GET", "url": "https://nexabot.id/api/auth/session", "status": 200, "resource_type": "fetch"},
    {"method": "POST", "url": f"https://nexabot.id/api/x/{TOKEN}?access_token={TOKEN}&n=1", "status": 401, "resource_type": "xhr",
     "headers": {"x-csrf": TOKEN}},
    {"method": "GET", "url": "https://nexabot.id/_next/static/a.js", "status": 200, "resource_type": "script"},
    {"method": "GET", "url": "https://analytics.example.com/c?id=1", "status": 200, "resource_type": "fetch"},
]


def test_requests_are_method_path_status_only_and_deduplicated():
    rows = pr.summarise_requests(EVENTS)
    assert rows == [{"method": "GET", "path": "/api/auth/session", "status": 200, "count": 2},
                    {"method": "POST", "path": "/api/x/:id?access_token=&n=", "status": 401, "count": 1}]


def _report(events=EVENTS, areas=None, **kw):
    return pr.build_report(
        started="2026-11-17T00:00:00Z", final_url=f"https://nexabot.id/video-generator?session={COOKIE}#{TOKEN}", title="NEXABOT",
        status=200, code="ok", line="nexabot.id: LOGGED IN.", login_names=["next-auth.session-token"],
        areas=areas or {"main": "Video generator\nCredits: 120"}, elements=[{"role": "tab", "name": "Video", "disabled": False}],
        opened=[], skipped=[], events=events, blocked_writes=kw.get("blocked", []), screenshots=["01.png"], notes=[])


def test_no_cookie_header_token_or_body_reaches_the_report():
    rep = _report()
    blob = json.dumps(rep) + pr.render_md(rep)
    for secret in (COOKIE, TOKEN, "access_token=eyJ", "Bearer", "authorization", "post_data", "response_body"):
        assert secret not in blob, secret
    assert "/api/auth/session" in blob and "GET" in blob and "Credits: 120" in blob
    assert rep["final_url"] == "https://nexabot.id/video-generator"        # no query, no fragment


def test_redact_removes_a_saved_secret_that_somehow_reached_the_text():
    st = _state([("session", ".nexabot.id")], [{"origin": "https://nexabot.id", "localStorage": [{"name": "t", "value": TOKEN}]}])
    secrets = pr.secret_values(st)
    assert COOKIE in secrets and TOKEN in secrets
    leaky = _report(areas={"main": f"Hello {COOKIE} and {TOKEN}"})
    clean = pr.redact(json.dumps(leaky), secrets) + pr.redact(pr.render_md(leaky), secrets)
    assert COOKIE not in clean and TOKEN not in clean and "[redacted]" in clean
    assert pr.redact("short x", ["x"]) == "short x"                     # a 1-character value is not redacted away


def test_balance_text_is_found_and_other_lines_are_not_kept():
    got = pr.balance_lines("Hello\nCredits: 120\nSaldo anda Rp 5.000\nA long paragraph " + "x" * 200 + " credits\nVideo")
    assert got == ["Credits: 120", "Saldo anda Rp 5.000"]


def test_the_md_names_every_section_and_says_what_was_blocked():
    rep = _report(blocked=["POST nexabot.id/api/generate", "POST nexabot.id/api/generate"])
    md = pr.render_md(rep)
    for head in ("## Controls", "## Menus and tabs opened", "## Same-origin XHR", "## Writes blocked at the network",
                 "## Screenshots"):
        assert head in md
    assert md.count("POST nexabot.id/api/generate") == 1


# --- the workflow ---------------------------------------------------------------------------------------------------------------

def test_the_workflow_is_manual_read_only_and_keeps_the_report_one_day():
    raw = (pathlib.Path(__file__).parents[2] / ".github/workflows/nexabot-probe.yml").read_text()
    flow = "\n".join(line for line in raw.splitlines() if not line.lstrip().startswith("#"))
    assert "workflow_dispatch" in flow and "schedule" not in flow and "push:" not in flow and "pull_request" not in flow
    assert "github.repository != 'wanshah07/argus'" in flow
    assert "contents: read" in flow and "retention-days: 1" in flow
    assert "NEXABOT_STORAGE_STATE_B64" in flow and "SUPABASE" not in flow


# --- a real browser against a fake studio (needs SEMASA_CHROME) ---------------------------------------------

STUDIO = """<!doctype html><title>NEXABOT fake</title><main>
<h1>Video generator</h1><p>Credits: 120</p>
<div role="tablist"><button role="tab" aria-selected="true">Video</button><button role="tab">Image</button>
 <button role="tab">Generate pack</button></div>
<button aria-haspopup="listbox" aria-expanded="false" id="m" onclick="document.getElementById('l').hidden=false">Model</button>
<div role="listbox" id="l" hidden><div role="option">Omni Flash</div><div role="option">Pro</div></div>
<select aria-label="Duration"><option>5s</option><option>10s</option></select>
<textarea placeholder="Describe your video"></textarea>
<button type="submit" id="g"
 onclick="window.fetch('/api/generate',{method:'POST',body:'x'});document.title='CLICKED'">Generate</button>
<button id="b" onclick="document.title='CLICKED'">Buat video</button>
<a href="/pricing">Top up</a></main>
<script>window.fetch('/api/me?token=abc123SECRET'); window.fetch('/api/track',{method:'POST',body:'x'});</script>"""

browser = pytest.mark.skipif(not os.environ.get("SEMASA_CHROME"), reason="set SEMASA_CHROME to run a real browser")


@browser
def test_the_probe_reads_a_fake_studio_opens_the_menu_and_never_clicks_generate(tmp_path):
    from playwright.sync_api import sync_playwright
    seen: list[tuple[str, str]] = []

    def fake_site(route):
        req = route.request
        seen.append((req.method, req.url))
        if req.url.endswith("/video-generator"):
            route.fulfill(status=200, content_type="text/html", body=STUDIO)
        else:
            route.fulfill(status=200, content_type="application/json", body="{}")

    events: list[dict] = []
    blocked: list[str] = []
    with sync_playwright() as pw:
        b = chk.launch_browser(pw)
        ctx = b.new_context(viewport={"width": 1366, "height": 900})
        ctx.route("**/*", fake_site)                       # registered first: the guard (second) runs before it
        ctx.route("**/*", pr.guard_route(blocked))
        ctx.on("response", lambda r: events.append({"method": r.request.method, "url": r.url, "status": r.status,
                                                    "resource_type": r.request.resource_type}))
        page = ctx.new_page()
        page.goto(chk.STUDIO_URL)
        page.wait_for_timeout(500)
        body = pr.probe(page, tmp_path, events, blocked)
        title_after = page.title()
        b.close()
    assert title_after == "NEXABOT fake", "a Generate or Buat button was clicked"
    assert all(m == "GET" for m, _ in seen), seen                    # no write ever left the browser
    # only the page's own load-time write, and it was aborted
    assert sorted(set(blocked)) == ["POST nexabot.id/api/track"], blocked
    names = {(o["role"], o["name"]) for o in body["opened"]}
    assert ("tab", "Video") in names and ("tab", "Image") in names and ("button", "Model") in names
    model = next(o for o in body["opened"] if o["name"] == "Model")
    assert model["options"] == ["Omni Flash", "Pro"]
    refused = {s["name"] for s in body["skipped"]}
    assert "Generate pack" in refused
    roles = {(e["role"], e["name"]) for e in body["elements"]}
    assert ("combobox", "Duration") in roles and ("textbox", "Describe your video") in roles and ("button", "Generate") in roles
    dur = next(e for e in body["elements"] if e["name"] == "Duration")
    assert dur["options"] == ["5s", "10s"]
    assert body["screenshots"] and (tmp_path / body["screenshots"][0]).exists()
    rep = pr.build_report(started="t", final_url=chk.STUDIO_URL, title="x", status=200, code="ok", line="l", login_names=[],
                          events=events, blocked_writes=blocked, **body)
    assert {"method": "GET", "path": "/api/me?token=", "status": 200, "count": 1} in rep["requests"]
    assert "abc123SECRET" not in json.dumps(rep) + pr.render_md(rep)
    assert "Credits: 120" in rep["balance_lines"]
