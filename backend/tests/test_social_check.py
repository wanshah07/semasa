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
    assert base64.b64decode(out.read_text()) == path.read_bytes()
