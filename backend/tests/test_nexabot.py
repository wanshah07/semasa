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


# --- Task: reading any page as text (/api-docs), the secret redactor and the refused paths ----------------------------------

FAKE_KEYS = [
    "nxb_live_8f3a9c2d1e7b4a5c9d0e1f2a3b4c5d6e", "sk-abc123def456ghi789jkl012mno", "nx_9f8e7d6c5b4a3210fedcba",
    "smi_9f8e7d6c5b4a3210", "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PK",
    "A1b2C3d4E5f6G7h8I9j0K1l2M3n4", "0123456789abcdef0123456789abcdef",
]


@pytest.mark.parametrize("key", FAKE_KEYS)
def test_a_fake_key_is_redacted_wherever_it_sits(key):
    for text in (f"key {key} end", f'{{"api_key": "{key}"}}', f"Authorization: Bearer {key}", f"curl -H 'x-api-key: {key}' u",
                 f"https://nexabot.id/api/v1/jobs?api_key={key}&n=1", f"export TOKEN={key}", f"/api/v1/keys/{key}/use"):
        out = pr.redact_secrets(text)
        assert key not in out and "[REDACTED]" in out, (text, out)


def test_plain_words_paths_short_ids_and_placeholders_are_kept():
    keep = ["POST /api/v1/video-generations/status", "text-to-video image-to-video", "job_8x2 and id abc123",
            "video-generation-2026-11-17-status-endpoint", "/api/v1/jobs?scope=&limit=20", "Authorization: Bearer YOUR_API_KEY",
            '{"api_key": "YOUR_API_KEY", "type": "string", "token": "string"}', "Credits: 120", "getVideoGenerationJobStatusById",
            "Start Frame to Video 1-1 img", "a 15-second video from text, a start frame, ingredients", "Status: processing"]
    for text in keep:
        assert pr.redact_secrets(text) == text, text


def test_redact_tree_cleans_strings_inside_a_report_and_counts_them():
    tree = {"a": ["Bearer nxb_live_8f3a9c2d1e7b4a5c9d0e1f2a3b4c5d6e", {"b": "plain text"}], "n": 5, "t": None}
    clean, n = pr.redact_tree(tree)
    assert n >= 1 and clean["n"] == 5 and clean["a"][1] == {"b": "plain text"}
    assert "nxb_live" not in json.dumps(clean) and json.loads(json.dumps(clean))["a"][0].endswith("[REDACTED]")


def test_api_keys_and_sign_out_paths_are_refused_in_every_spelling():
    for bad in ("/api-keys", "/API-KEYS", "/api-keys/", "/api-keys/new", "/settings/api-keys", "/api_keys", "/apikeys",
                "/api-key", "/%61pi-keys", "/logout", "/auth/signout", "//evil.example/api-docs", "https://nexabot.id/api-docs",
                "/x/../api-keys", "/api-docs?next=1", "/api docs", "api-docs"):
        with pytest.raises(pr.PathRefused):
            pr.check_path(bad)
    assert pr.check_path("/api-docs") == "/api-docs" and pr.check_path("/api-docs/") == "/api-docs"
    assert pr.check_path("") == "/video-generator" and pr.check_path("/docs/v1/jobs.html") == "/docs/v1/jobs.html"
    assert pr.main(["probe", "/tmp/never", "--path", "/api-keys"]) == 2


def test_a_request_for_the_keys_page_is_aborted_at_the_network_even_as_a_read():
    class Req:
        def __init__(self, method, url):
            self.method, self.url = method, url

    class Route:
        def __init__(self, req):
            self.request, self.did = req, ""

        def abort(self):
            self.did = "abort"

        def fallback(self):
            self.did = "fallback"

    blocked: list[str] = []
    h = pr.guard_route(blocked)
    for method, url, did in [("GET", "https://nexabot.id/api-keys", "abort"),
                             ("GET", "https://nexabot.id/api/api-keys/list", "abort"),
                             ("GET", "https://nexabot.id/api-docs", "fallback"), ("POST", "https://nexabot.id/api/x", "abort"),
                             ("GET", "https://nexabot.id/logout", "abort")]:
        r = Route(Req(method, url))
        h(r)
        assert r.did == did, (method, url)
    assert any("/api-keys (private page)" in b for b in blocked)


def test_page_verdict_for_an_ordinary_page():
    assert pr.page_verdict("https://nexabot.id/api-docs", 200, "Docs", "/api-docs", ["s"])[0] == "ok"
    assert pr.page_verdict("https://nexabot.id/login?next=%2Fapi-docs", 200, "Login", "/api-docs", [])[0] == "wall"
    assert pr.page_verdict("https://nexabot.id/video-generator", 200, "NEXABOT", "/api-docs", [])[0] == "other"
    assert pr.page_verdict("https://nexabot.id/api-docs", 403, "Forbidden", "/api-docs", [])[0] == "blocked"
    assert "LOGIN WALL" in pr.page_verdict("https://nexabot.id/login", 200, "", "/api-docs", [])[1]


def test_the_workflow_takes_a_path_input_through_an_env_var_not_the_shell_text():
    raw = (pathlib.Path(__file__).parents[2] / ".github/workflows/nexabot-probe.yml").read_text()
    flow = "\n".join(line for line in raw.splitlines() if not line.lstrip().startswith("#"))
    assert "path:" in flow and "NB_PATH: ${{ inputs.path }}" in flow and '--path "$NB_PATH"' in flow
    assert "run: python" not in flow and "inputs.path }}\"" not in flow


DOCS = """<!doctype html><title>API Docs</title><main><h1>Nexabot API</h1>
<p>Send your key as a bearer token.</p>
<div role="tablist"><button role="tab" aria-selected="true" onclick="document.getElementById('py').hidden=true;
 document.getElementById('sh').hidden=false">cURL</button><button role="tab" onclick="document.getElementById('sh').hidden=true;
 document.getElementById('py').hidden=false">Python</button></div>
<pre id="sh">curl -X POST https://nexabot.id/api/v1/jobs -H "Authorization: Bearer nxb_live_8f3a9c2d1e7b4a5c9d0e1f2a3b4c5d6e"
  -d '{"prompt":"a cat","orientation":"portrait"}'</pre>
<pre id="py" hidden>requests.post(url, headers={"x-api-key": "sk-abc123def456ghi789jkl012mno"})</pre>
<table><tr><th>Field</th><th>Type</th></tr><tr><td>prompt</td><td>string</td></tr><tr><td>orientation</td><td>portrait|landscape</td></tr>
</table><a href="/api-keys">Your keys</a><button onclick="window.fetch('/api-keys')">Show</button></main>
<script>window.fetch('/api/docs/index'); window.fetch('/api/track',{method:'POST',body:'x'});</script>"""


@browser
def test_a_docs_page_is_read_as_text_with_its_keys_redacted_and_the_keys_page_never_fetched(tmp_path):
    from playwright.sync_api import sync_playwright
    seen: list[tuple[str, str]] = []

    def fake_site(route):
        req = route.request
        seen.append((req.method, req.url))
        if req.url.endswith("/api-docs"):
            route.fulfill(status=200, content_type="text/html", body=DOCS)
        else:
            route.fulfill(status=200, content_type="application/json", body="{}")

    events: list[dict] = []
    blocked: list[str] = []
    with sync_playwright() as pw:
        b = chk.launch_browser(pw)
        ctx = b.new_context(viewport={"width": 1366, "height": 900})
        ctx.route("**/*", fake_site)
        ctx.route("**/*", pr.guard_route(blocked))
        ctx.on("response", lambda r: events.append({"method": r.request.method, "url": r.url, "status": r.status,
                                                    "resource_type": r.request.resource_type}))
        page = ctx.new_page()
        page.goto(chk.ORIGIN + "/api-docs")
        page.wait_for_timeout(300)
        body = pr.read_page(page, tmp_path, events, blocked, "/api-docs")
        # the page's own script tries the keys page: click that button the way a visitor would (the probe itself never does)
        page.evaluate("() => window.fetch('/api-keys').catch(() => 0)")
        page.wait_for_timeout(300)
        b.close()
    assert not any("/api-keys" in u for _, u in seen), seen             # aborted before it reached the (fake) network
    assert all(m == "GET" for m, _ in seen), seen
    rep = pr.build_page_report(started="t", final_url=chk.ORIGIN + "/api-docs?x=1", title="API Docs", status=200, code="ok",
                               line="l", login_names=[], body=body, events=events, blocked_writes=blocked)
    md = pr.render_page_md(rep)
    blob = json.dumps(rep) + md
    for key in ("nxb_live_8f3a9c2d1e7b4a5c9d0e1f2a3b4c5d6e", "sk-abc123def456ghi789jkl012mno"):
        assert key not in blob, key
    assert "Nexabot API" in md and "Authorization: Bearer [REDACTED]" in md and "x-api-key" in md          # the shape stays
    assert rep["redactions"] >= 2 and len(rep["code_blocks"]) == 2                    # the hidden Python tab is read too
    assert any("orientation | portrait|landscape" in "\n".join(t) for t in rep["tables"])
    assert "Python" in {o["name"] for o in rep["opened"]}                                # a tab was opened, nothing chosen
    assert rep["final_url"] == chk.ORIGIN + "/api-docs"                                  # no query
    assert any("/api-keys" in x for x in rep["blocked_writes"]) and "POST nexabot.id/api/track" in rep["blocked_writes"]
    assert (tmp_path / body["screenshots"][0]).exists()
    pr.write_reports(tmp_path, rep, None)
    assert "nxb_live" not in (tmp_path / "report.md").read_text() + (tmp_path / "report.json").read_text()
    assert json.loads((tmp_path / "report.json").read_text())["mode"] == "page"


def test_a_page_read_writes_no_screenshot(tmp_path):
    """A docs page can show a real credential on screen and a picture cannot be redacted, so only the studio is photographed."""
    class FakePage:
        def __init__(self):
            self.calls = 0

        def screenshot(self, path, full_page):
            self.calls += 1
            pathlib.Path(path).write_bytes(b"png")

    page = FakePage()
    pr.SCREENSHOTS_ON = False
    try:
        assert pr._shot(page, tmp_path, "x.png", True) == "" and page.calls == 0 and not list(tmp_path.iterdir())
    finally:
        pr.SCREENSHOTS_ON = True
    assert pr._shot(page, tmp_path, "y.png", True) == "y.png" and page.calls == 1


# --- Phase B: the post text passes through to the import (Wan, 17 Nov 2026) ----------------------------------------------------

import re  # noqa: E402
from datetime import UTC, datetime  # noqa: E402

from semasa import nexabot_generate as gen  # noqa: E402

WORKFLOW = pathlib.Path(__file__).resolve().parents[2] / ".github" / "workflows" / "nexabot-generate.yml"
NOW = datetime(2026, 11, 17, 5, 6, 7, tzinfo=UTC)


def test_a_bare_run_sends_what_it_always_sent():
    assert gen.import_form("a cup of tea", None, NOW) == {
        "source": "nexabot", "title": "a cup of tea", "idempotency_key": "nexabot-20261117-050607"}
    assert gen.import_form("p" * 300, {}, NOW)["title"] == "p" * 160


def test_title_caption_channels_lang_and_source_are_sent_as_the_intake_reads_them():
    odd = 'Satu "caption" $HOME `x`\nbaris dua'
    f = gen.import_form(
        "prompt", {"title": "Teh tarik", "caption": odd, "channels": "Instagram, threads", "lang": "bm", "source": "hermes"}, NOW)
    assert f["title"] == "Teh tarik" and f["source"] == "hermes" and f["lang"] == "bm"
    assert f["caption"] == 'Satu "caption" $HOME `x`\nbaris dua', "the caption is sent exactly, quotes and all"
    assert f["channels"] == "instagram,threads"


def test_per_channel_captions_go_as_one_json_object_and_override_the_plain_one():
    caps = {"instagram": "IG", "facebook": "FB"}
    f = gen.import_form("p", {"captions": caps, "caption": "all", "channels": "instagram,facebook,threads"}, NOW)
    assert json.loads(f["caption"]) == {"instagram": "IG", "facebook": "FB", "threads": "all"}
    assert json.loads(gen.import_form("p", {"captions": caps}, NOW)["caption"]) == caps


def test_captions_json_is_checked_before_anything_is_generated():
    assert gen.parse_captions_json('{"instagram": "a", "threads": "b"}') == {"instagram": "a", "threads": "b"}
    for bad in ("not json", "[1]", "{}", '{"tiktok": "x"}', '{"instagram": 3}'):
        with pytest.raises(ValueError):
            gen.parse_captions_json(bad)
    assert gen.main(["x", "/tmp/never", "--prompt", "p", "--captions-json", "{broken"]) == 2


def test_import_posts_the_file_with_that_form(tmp_path, monkeypatch):
    import requests

    mp4 = tmp_path / "film.mp4"
    mp4.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"0" * 40)
    seen = {}

    class R:
        status_code, text = 202, '{"ok": true}'

    def post(url, headers=None, files=None, data=None, timeout=None):
        seen.update(url=url, headers=headers, data=data, name=files["file"][0])
        return R()

    monkeypatch.setattr(requests, "post", post)
    monkeypatch.setenv("SEMASA_IMPORT_URL", "https://x.test/functions/v1/semasa-import-video")
    monkeypatch.setenv("SEMASA_IMPORT_TOKEN", "smi_" + "0" * 48)
    report: dict = {"prompt": "a cup of tea"}
    assert gen._import(str(mp4), report, {"title": "T", "captions": {"threads": "hi"}, "lang": "en"}) == 0
    assert seen["data"]["title"] == "T" and seen["data"]["lang"] == "en"
    assert json.loads(seen["data"]["caption"]) == {"threads": "hi"}
    assert seen["data"]["source"] == "nexabot" and seen["name"] == "film.mp4"
    assert report["import"]["status"] == 202
    assert "smi_" not in json.dumps(report)
    seen.clear()
    gen._import(str(mp4), {"prompt": "a cup of tea"})  # no options: the old behaviour
    assert seen["data"]["title"] == "a cup of tea" and "caption" not in seen["data"] and "channels" not in seen["data"]


def _run_blocks(text):
    """The shell text of every `run:` block in the workflow (a block scalar: the lines indented under it)."""
    lines, out, i = text.split("\n"), [], 0
    while i < len(lines):
        m = re.match(r"^(\s*)(?:- )?run:\s*(.*)$", lines[i])
        if not m:
            i += 1
            continue
        indent, first, block = len(m.group(1)), m.group(2), []
        if first and first not in ("|", ">", "|-", ">-"):
            block.append(first)
        i += 1
        while i < len(lines) and (not lines[i].strip() or len(lines[i]) - len(lines[i].lstrip()) > indent):
            block.append(lines[i])
            i += 1
        out.append("\n".join(block))
    return out


def test_the_workflow_takes_the_new_inputs_and_hands_them_over_only_as_environment_variables():
    text = WORKFLOW.read_text("utf-8")
    for name in ("prompt", "dry", "import", "title", "caption", "captions_json", "channels", "lang"):
        assert re.search(rf"^      {name}:\n", text, re.M), f"workflow_dispatch input {name} is missing"
    runs = _run_blocks(text)
    assert runs and any("nexabot_generate" in r for r in runs)
    for r in runs:
        assert "${{" not in r, f"an expression is pasted into shell text: {r[:200]}"
    assert not re.search(r"\$\{\{\s*inputs\.", "\n".join(runs))
    for name, var in (("title", "NB_TITLE"), ("caption", "NB_CAPTION"), ("captions_json", "NB_CAPTIONS_JSON"),
                      ("channels", "NB_CHANNELS"), ("lang", "NB_LANG"), ("prompt", "NB_PROMPT")):
        env = re.search(rf"^\s+{var}: \$\{{\{{ inputs\.{name} \}}\}}$", text, re.M)
        assert env, f"{var} is not an env var from inputs.{name}"
    gen_run = next(r for r in runs if "nexabot_generate" in r)
    assert '"${args[@]}"' in gen_run and '"$NB_TITLE"' in gen_run and '"$NB_CAPTIONS_JSON"' in gen_run
    assert "--dry" in gen_run and "--import" in gen_run, "dry and import keep working"


def test_generate_follows_only_its_own_job(tmp_path, monkeypatch):
    """A finished OLD job on the account must never be taken for the video just asked for (the 17 Nov run stopped in
    seconds on one and saved nothing)."""
    from semasa import nexabot_generate as ng

    monkeypatch.setattr(ng, "POLL_S", 0)

    class Loc:
        def __init__(self, page): self.page = page
        first = property(lambda self: self)
        def wait_for(self, **k): pass
        def fill(self, t): pass
        def is_visible(self): return False
        def is_disabled(self): return False
        def click(self): self.page.clicked = True

    class Req:
        def __init__(self, page): self.page = page
        def get(self, url, timeout=0):
            self.page.fetched.append(url)
            class R:
                status = 200
                def body(self): return b"x" * 20_000
            return R()

    class Ctx:
        def __init__(self, page): self.request = Req(page)

    class Page:
        def __init__(self):
            self.clicked, self.fetched, self.polls = False, [], 0
            self.context = Ctx(self)
        def locator(self, sel): return Loc(self)
        def get_by_role(self, *a, **k): return Loc(self)
        def wait_for_timeout(self, ms): pass
        def evaluate(self, js, arg=None):
            if arg is not None:  # one job by id
                self.polls += 1
                return {"id": arg, "status": "done" if self.polls > 1 else "processing"}
            old = {"id": "old1", "status": "done"}
            return [old] + ([{"id": "new1", "status": "queued"}] if self.clicked else [])

    page, report = Page(), {}
    ng.generate(page, "a prompt", tmp_path, 1, False, report)
    assert report["job_id"] == "new1" and report["job_id_via"] == "list_diff"
    assert report["job_done"] and report["video_saved"]
    assert page.fetched == ["https://nexabot.id/api/v1/jobs/new1/download"]


def test_generate_without_a_baseline_does_not_guess_a_job(tmp_path, monkeypatch):
    """If the pre-click job list could not be read, an old finished job must not be taken as new: with no id from the
    Generate answer the run waits out (here: a short deadline) and saves nothing."""
    from semasa import nexabot_generate as ng

    monkeypatch.setattr(ng, "POLL_S", 0)
    monkeypatch.setattr(ng, "MAX_WAIT_S", 0.05)

    class Loc:
        first = property(lambda self: self)
        def wait_for(self, **k): pass
        def fill(self, t): pass
        def is_visible(self): return False
        def is_disabled(self): return False
        def click(self): pass

    class Page:
        calls = 0
        def locator(self, sel): return Loc()
        def get_by_role(self, *a, **k): return Loc()
        def wait_for_timeout(self, ms): pass
        def evaluate(self, js, arg=None):
            Page.calls += 1
            return None if Page.calls == 1 else [{"id": "old1", "status": "done"}]

    report = {}
    ng.generate(Page(), "a prompt", tmp_path, 1, False, report)
    assert report["jobs_before"] is None
    assert "job_id" not in report and not report.get("video_saved") and report.get("timed_out")


def test_cat_film_story_is_four_scenes_with_four_lines():
    from semasa import nexabot_cat_film as cf

    assert len(cf.SCENES) == len(cf.NARRATION) == 4
    # the words are voice + subtitle: the video prompts carry no quoted speech, and the sheet draws no text
    assert all('"' not in s and "“" not in s for s in cf.SCENES)
    assert "No people, no text" in cf.CHAR_SHEET_PROMPT
    # three named cats appear in the narration, in Malay (not Indonesian)
    assert "Comot" in cf.NARRATION[0] and "Putih" in cf.NARRATION[1] and "Belang" in cf.NARRATION[1]
    assert all(w not in " ".join(cf.NARRATION).lower() for w in ("kucingnya", "sahabat-sahabat"))


def test_cat_film_dry_run_spends_nothing(tmp_path):
    from semasa import nexabot_cat_film as cf

    assert cf.run(tmp_path, "Sulafat", True) == 0
    assert (tmp_path / "report.json").exists()


def test_cat_film_mix_holds_the_last_frame_for_a_long_line(tmp_path):
    """A clip shorter than its voice must be held, not cut: the scene lasts as long as lead + voice + tail."""
    import subprocess

    import pytest

    imageio_ffmpeg = pytest.importorskip("imageio_ffmpeg")
    from semasa import nexabot_cat_film as cf

    ff = imageio_ffmpeg.get_ffmpeg_exe()
    clip, voice = tmp_path / "c.mp4", tmp_path / "v.wav"
    subprocess.run([ff, "-y", "-f", "lavfi", "-i", "color=c=orange:s=320x180:d=1:r=24", "-pix_fmt", "yuv420p", str(clip)],
                   check=True, capture_output=True)
    subprocess.run([ff, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=3", str(voice)], check=True, capture_output=True)
    try:
        seg = cf.scene_segment(clip, voice, "Comot dan kawan-kawan", tmp_path / "s.mp4", size=(320, 180))
    except subprocess.CalledProcessError as exc:
        if b"drawtext" in (exc.stderr or b"") or b"fontfile" in (exc.stderr or b""):
            pytest.skip("the runner has no DejaVu font for drawtext")
        raise
    assert cf.duration(seg) == pytest.approx(cf.LEAD_S + 3 + cf.TAIL_S, abs=0.3)
    out = cf.join([seg, seg], tmp_path / "all.mp4")
    assert cf.duration(out) == pytest.approx(2 * cf.duration(seg), abs=0.4)
