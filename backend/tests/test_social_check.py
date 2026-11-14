"""The login checker's pure parts (13 Nov 2026): what a saved login holds, and the plain line it prints per platform."""

import base64
import json

from semasa import social_check


def _state(*cookies):
    return {"cookies": [{"name": n, "domain": d, "value": "secret-value"} for n, d in cookies], "origins": []}


def test_it_reports_which_platforms_the_file_has_a_login_for_by_cookie_name_only():
    held = social_check.inspect_state(_state(("sessionid", ".instagram.com"), ("ds_user_id", ".instagram.com"),
                                             ("c_user", ".facebook.com")))
    assert held["instagram"] == {"has": ["sessionid", "ds_user_id"], "missing": []}
    assert held["facebook"] == {"has": ["c_user"], "missing": ["xs"]}
    assert social_check.inspect_state({"cookies": []})["instagram"]["missing"] == ["sessionid", "ds_user_id"]


def test_the_verdict_says_what_to_do_in_each_case():
    ok = {"has": ["sessionid"], "missing": []}
    assert social_check.verdict("instagram", ok, 5, "") == "Instagram: OK, 5 post(s) read."
    assert "LOGIN WALL" in social_check.verdict("instagram", ok, 0, "Instagram asked for a login (save one)")
    assert "no Facebook login" in social_check.verdict("facebook", {"has": [], "missing": ["c_user", "xs"]}, 0, "")
    assert "no posts came back" in social_check.verdict("facebook", ok, 0, "")
    assert "could not read" in social_check.verdict("facebook", ok, 0, "TimeoutError: slow")


def test_the_report_never_prints_a_cookie_value_and_writes_the_base64_the_sweep_can_read(tmp_path, capsys, monkeypatch):
    path = tmp_path / "state.json"
    path.write_text(json.dumps(_state(("sessionid", ".instagram.com"))))
    out = tmp_path / "secret.txt"
    monkeypatch.setitem(__import__("sys").modules, "playwright.sync_api", None)      # no browser: stops after the file checks
    social_check.main(["social_check", str(path), "--b64", str(out)])
    printed = capsys.readouterr().out
    assert "secret-value" not in printed and "Base64 size" in printed
    monkeypatch.setenv("PW_STORAGE_STATE_B64", out.read_text())
    assert json.load(open(social_check.social_web.storage_state_path()))["cookies"][0]["name"] == "sessionid"
    assert json.loads(base64.b64decode(out.read_text())) == social_check.shrink(_state(("sessionid", ".instagram.com")))[0]


def test_a_login_file_bloated_by_page_data_is_shrunk_to_the_two_sites_cookies_and_fits_a_secret():
    state = _state(("sessionid", ".instagram.com"), ("c_user", ".facebook.com"), ("other", ".google.com"))
    state["origins"] = [{"origin": "https://www.facebook.com", "localStorage": [{"name": "k", "value": "x" * 90_000}]}]
    out, why = social_check.shrink(state)
    assert [c["name"] for c in out["cookies"]] == ["sessionid", "c_user"]         # google's cookie goes
    assert out["origins"] == []                                                    # and so does the page data
    assert social_check._encoded_size(out) < social_check.GITHUB_SECRET_LIMIT and "dropped" in why
    assert social_check.inspect_state(out)["instagram"]["has"] == ["sessionid"]   # what the sweep needs stays


def test_when_even_the_two_sites_cookies_are_too_large_only_the_login_cookies_are_kept():
    state = _state(("sessionid", ".instagram.com"), ("c_user", ".facebook.com"))
    state["cookies"] += [{"name": f"junk{i}", "domain": ".facebook.com", "value": "y" * 1000} for i in range(80)]
    out, why = social_check.shrink(state)
    assert sorted(c["name"] for c in out["cookies"]) == ["c_user", "sessionid"] and "only the login cookies" in why
