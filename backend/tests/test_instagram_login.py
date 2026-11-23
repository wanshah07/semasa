"""ops/instagram_login.py: the standalone login saver Wan runs on his own computer (no repo, no semasa import)."""

import base64
import importlib.util
import json
from pathlib import Path

PATH = Path(__file__).resolve().parents[2] / "ops" / "instagram_login.py"
spec = importlib.util.spec_from_file_location("instagram_login", PATH)
il = importlib.util.module_from_spec(spec)
spec.loader.exec_module(il)


def _c(name, domain, size=10):
    return {"name": name, "value": "x" * size, "domain": domain}


def test_it_needs_nothing_from_the_repo():
    code = PATH.read_text().split('"""', 2)[2]                    # after the docstring, which names the repo's checker
    assert "import semasa" not in code and "from semasa" not in code


def test_it_reports_which_login_cookies_are_missing_by_name():
    state = {"cookies": [_c("sessionid", ".instagram.com"), _c("ds_user_id", ".instagram.com"), _c("c_user", ".facebook.com")]}
    assert il.held(state) == {"instagram": [], "facebook": ["xs"]}


def test_the_secret_keeps_only_facebook_and_instagram_cookies_and_drops_page_data():
    state = {"cookies": [_c("sessionid", ".instagram.com"), _c("other", ".example.com")],
             "origins": [{"origin": "https://x", "localStorage": []}]}
    out = il.slim(state)
    assert [c["name"] for c in out["cookies"]] == ["sessionid"] and out["origins"] == []
    assert json.loads(base64.b64decode(il.encoded(out)))["cookies"][0]["name"] == "sessionid"


def test_a_secret_over_githubs_limit_falls_back_to_the_login_cookies():
    big = [_c(f"junk{i}", ".facebook.com", 400) for i in range(200)]
    state = {"cookies": [*big, _c("c_user", ".facebook.com"), _c("xs", ".facebook.com")]}
    assert len(il.encoded({"cookies": big, "origins": []})) > il.LIMIT
    out = il.slim(state)
    assert {c["name"] for c in out["cookies"]} == {"c_user", "xs"} and len(il.encoded(out)) < il.LIMIT
