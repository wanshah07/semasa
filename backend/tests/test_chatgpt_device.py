"""The ChatGPT device-code login (Wan, 6 Nov 2026): a code and a link on the card, the tokens saved when Wan approves.
Fake HTTP and an in-memory store; nothing here reaches OpenAI."""

import base64
import json
from datetime import UTC, datetime, timedelta

import requests
from fakestore import FakeStore

from semasa import chatgpt_device as dev
from semasa import chatgpt_login as cl

NOW = datetime(2026, 11, 6, 17, 0, tzinfo=UTC)


def jwt(**claims) -> str:
    def part(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
    return f"{part({'alg': 'none'})}.{part(claims)}.sig"


class Resp:
    def __init__(self, code=200, body=None, text=""):
        self.status_code, self.body, self.text = code, body if body is not None else {}, text

    def json(self):
        return self.body


class Http:
    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def post(self, url, **kw):
        self.calls.append((url, kw))
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a


CODE = {"device_auth_id": "deviceauth_abc", "user_code": "3CA1-GJOWC", "interval": "5",
        "expires_at": (NOW + timedelta(minutes=15)).isoformat()}
PENDING = Resp(403, {"error": {"message": "pending", "code": "deviceauth_authorization_pending"}})
APPROVED = Resp(200, {"authorization_code": "ac-1", "code_challenge": "cc", "code_verifier": "cv-1"})
EXP = int((NOW + timedelta(days=9)).timestamp())
TOKENS = Resp(200, {"id_token": jwt(email="wan@example.com", **{"https://api.openai.com/auth": {"chatgpt_account_id": "acct-9"}}),
                    "access_token": jwt(exp=EXP), "refresh_token": "rt-1"})


def store(state="requested", **row):
    return FakeStore(**{dev.TABLE: [{"id": "main", "state": state, "requested_at": "T1", **row}]})


def run(st, http, ticks=None):
    """Runs the login with the clock advancing one minute a sleep, so a 15-minute code dies after 15 pending polls."""
    clock = {"t": NOW}

    def sleep(_s):
        clock["t"] += timedelta(minutes=1)
        if ticks:
            ticks(st, clock["t"])
    return dev.run(st, http=http, sleep=sleep, now=lambda: clock["t"])


def row(st):
    return st.tables[dev.TABLE][0]


def test_the_endpoints_are_the_codex_cli_ones():
    assert dev.USERCODE == "https://auth.openai.com/api/accounts/deviceauth/usercode"
    assert dev.POLL == "https://auth.openai.com/api/accounts/deviceauth/token"
    assert dev.EXCHANGE == "https://auth.openai.com/oauth/token"
    assert dev.VERIFY_URL == "https://auth.openai.com/codex/device"


def test_nothing_is_done_unless_the_page_asked():
    http = Http()
    for s in (store("idle"), store("waiting"), FakeStore()):
        assert "no ChatGPT login" in run(s, http)
    assert http.calls == []


def test_a_code_is_shown_then_approval_saves_the_login_where_motion_reads_it():
    st = store()
    seen = []

    def watch(s, t):
        seen.append((row(s)["state"], row(s).get("user_code"), row(s).get("verification_url")))
    http = Http(Resp(200, CODE), PENDING, PENDING, APPROVED, TOKENS)
    assert run(st, http, watch) == "done: ChatGPT is connected"
    assert seen[0] == ("waiting", "3CA1-GJOWC", "https://auth.openai.com/codex/device"), "the code is on the row while it waits"
    assert http.calls[0][1]["json"] == {"client_id": cl.CLIENT_ID}
    assert http.calls[1][1]["json"] == {"device_auth_id": "deviceauth_abc", "user_code": "3CA1-GJOWC"}
    url, kw = http.calls[-1]
    assert url == dev.EXCHANGE and kw["data"]["grant_type"] == "authorization_code" and kw["data"]["code"] == "ac-1"
    assert kw["data"]["code_verifier"] == "cv-1" and kw["data"]["redirect_uri"] == dev.REDIRECT
    assert kw["data"]["client_id"] == cl.CLIENT_ID
    saved = st.tables[cl.TABLE][0]
    assert saved["id"] == "main" and saved["account"] == "wan@example.com"
    assert saved["auth"]["tokens"]["refresh_token"] == "rt-1" and saved["auth"]["tokens"]["account_id"] == "acct-9"
    assert saved["checked_at"] is None and saved["last_ok_at"] is None and saved["last_error"] is None
    assert saved["access_expires_at"].startswith("2026-11-15")
    assert row(st)["state"] == "done" and row(st)["user_code"] is None and row(st)["device_auth_id"] is None


def test_a_new_login_keeps_the_switch_the_model_and_the_picture_count():
    st = store()
    st.tables[cl.TABLE] = [{"id": "main", "auth": {"tokens": {"refresh_token": "old"}}, "enabled": False, "model": "gpt-5.1",
                            "max_images": 3}]
    run(st, Http(Resp(200, CODE), APPROVED, TOKENS))
    saved = st.tables[cl.TABLE][0]
    assert saved["auth"]["tokens"]["refresh_token"] == "rt-1"
    assert (saved["enabled"], saved["model"], saved["max_images"]) == (False, "gpt-5.1", 3)


def test_a_code_nobody_approves_expires_after_fifteen_minutes():
    st = store()
    http = Http(Resp(200, CODE), *[PENDING] * 20)
    assert run(st, http).startswith("expired")
    assert row(st)["state"] == "expired" and row(st)["device_auth_id"] is None
    assert len(http.calls) <= 16, "it stops polling once the code is dead"


def test_a_new_request_or_a_cancel_stops_this_run_without_touching_the_row():
    st = store()

    def newer(s, t):
        row(s).update(state="requested", requested_at="T2", user_code=None)            # Wan pressed "new code"
    http = Http(Resp(200, CODE), PENDING)
    assert run(st, http, newer).startswith("stopped")
    assert row(st)["requested_at"] == "T2" and row(st)["state"] == "requested" and len(http.calls) == 1
    st2 = store()
    run(st2, Http(Resp(200, CODE), PENDING), lambda s, t: row(s).update(state="idle"))
    assert row(st2)["state"] == "idle"


def test_slow_down_and_429_back_off_but_keep_waiting():
    st = store()
    http = Http(Resp(200, CODE), Resp(400, {"error": {"code": "slow_down"}}), Resp(429), APPROVED, TOKENS)
    assert run(st, http) == "done: ChatGPT is connected"


def test_openai_refusing_the_code_request_is_an_error_on_the_card():
    st = store()
    assert run(st, Http(Resp(500, text="boom"))).startswith("error")
    assert row(st)["state"] == "error" and "500" in row(st)["error"]
    st2 = store()
    run(st2, Http(requests.ConnectionError("down")))
    assert row(st2)["state"] == "error" and "could not be reached" in row(st2)["error"]


def test_an_unexpected_answer_while_waiting_is_an_error():
    st = store()
    assert run(st, Http(Resp(200, CODE), Resp(500, text="oops"))).startswith("error")
    assert row(st)["state"] == "error" and "500" in row(st)["error"] and row(st)["device_auth_id"] is None


def test_the_network_dropping_for_a_while_is_survived_but_not_for_ever():
    ok = Http(Resp(200, CODE), requests.ConnectionError("x"), requests.ConnectionError("x"), APPROVED, TOKENS)
    assert run(store(), ok) == "done: ChatGPT is connected"
    st = store()
    gone = Http(Resp(200, CODE), *[requests.ConnectionError("x")] * dev.MAX_FAILS)
    assert run(st, gone).startswith("error") and row(st)["state"] == "error"


def test_a_failed_token_exchange_is_an_error_and_saves_nothing():
    st = store()
    assert run(st, Http(Resp(200, CODE), APPROVED, Resp(400, text="invalid_grant"))).startswith("error")
    assert row(st)["state"] == "error" and st.tables.get(cl.TABLE, []) == []


def test_no_token_or_device_id_is_ever_in_the_status_the_page_reads():
    st = store()
    run(st, Http(Resp(200, CODE), PENDING), lambda s, t: row(s).update(state="idle"))
    assert "deviceauth_abc" not in json.dumps({k: v for k, v in row(st).items() if k != "device_auth_id"})
