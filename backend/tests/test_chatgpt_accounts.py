"""More than one ChatGPT account for pictures (supabase/095; Wan, 24 Nov 2026: "add chatgpt segment that I can add multiple
accounts to support image gen using chatgpt"). The main login is asked first; an account that says its allowance is used up
rests and the next one draws. Fake logins and an in-memory store; nothing here reaches OpenAI."""

import base64
import json
from datetime import UTC, datetime, timedelta

import pytest
from fakestore import FakeStore

from semasa import chatgpt_device as dev
from semasa import chatgpt_login as cl
from semasa import media_generator
from semasa import motion_gpt_images as gi
from semasa.providers import ProviderError

NOW = datetime(2026, 11, 24, 18, 0, tzinfo=UTC)
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
TOK = {"tokens": {"refresh_token": "rt", "access_token": "at"}}


def main_row(**kw):
    return {"id": "main", "auth": TOK, "account": "wan@example.com", "enabled": True, "model": "gpt-main", "max_images": 6, **kw}


def acc(n, **kw):
    return {"id": f"acc{n}", "auth": TOK, "account": f"extra{n}@example.com", "enabled": True, "model": f"gpt-acc{n}",
            "max_images": 6, "limit_until": None, **kw}


def store(*extras, main=True, **kw):
    tables = {cl.ACCOUNTS: list(extras)}
    if main:
        tables[cl.TABLE] = [main_row(**kw)]
    return FakeStore(**tables)


def names(logins):
    return [cl.name_of(x) for x in logins]


def answers(monkeypatch, by):
    """Login.draw answers from `by[name]`: bytes, or an exception to raise. Returns the (name, model) pairs asked, in order."""
    asked = []

    def draw(self, prompt, *, size="1024x1024", model=cl.DEFAULT_MODEL, timeout=300, image_model=""):
        asked.append((cl.name_of(self), model))
        got = by[cl.name_of(self)]
        if isinstance(got, Exception):
            raise got
        return got
    monkeypatch.setattr(cl.Login, "draw", draw)
    return asked


LIMIT = cl.ChatGPTError("You've hit your usage limit", limit=True)
REFUSED = cl.ChatGPTError("ChatGPT refused the saved login (401)", auth=True)
NO_MODEL = cl.ChatGPTError("no model of this plan draws", model=True)
DOWN = cl.ChatGPTError("ChatGPT could not be reached")


# ---- who is asked, and in what order -------------------------------------------------------------------------------------
def test_the_main_login_is_asked_first_then_the_extra_accounts_in_id_order():
    st = store(acc(2), acc(1))
    assert names(cl.picture_logins(st, NOW)) == ["main", "acc1", "acc2"]


def test_an_account_switched_off_without_tokens_or_resting_is_not_asked():
    later, earlier = (NOW + timedelta(hours=1)).isoformat(), (NOW - timedelta(minutes=1)).isoformat()
    st = store(acc(1, enabled=False), acc(2, auth={"tokens": {}}), acc(3, limit_until=later), acc(4, limit_until=earlier),
               acc(5, limit_until="not a date"))
    assert names(cl.picture_logins(st, NOW)) == ["main", "acc4", "acc5"], "a rest that is over, or unreadable, is asked again"


def test_the_main_switch_turns_every_chatgpt_picture_off_and_no_main_login_leaves_the_extras():
    assert cl.picture_logins(store(acc(1), enabled=False), NOW) == []
    assert names(cl.picture_logins(store(acc(1), main=False), NOW)) == ["acc1"]
    assert cl.picture_logins(FakeStore(), NOW) == [], "095 not applied and no login: nothing, and no error"


def test_at_most_eight_extra_accounts_are_asked():
    st = store(*[acc(n) for n in range(1, 12)])
    assert len(cl.picture_logins(st, NOW)) == 1 + cl.MAX_ACCOUNTS


# ---- one picture, from the first account that draws it --------------------------------------------------------------------
def test_a_used_up_account_rests_and_the_next_one_draws_with_its_own_model(monkeypatch):
    st = store(acc(1), acc(2))
    asked = answers(monkeypatch, {"main": LIMIT, "acc1": LIMIT, "acc2": PNG})
    spent = set()
    data, login, model = cl.draw_any(st, "a flask", logins=cl.picture_logins(st, NOW), skip=spent)
    assert data == PNG and cl.name_of(login) == "acc2" and model == "gpt-acc2"
    assert asked == [("main", "gpt-main"), ("acc1", "gpt-acc1"), ("acc2", "gpt-acc2")]
    assert spent == {"main", "acc1"}
    rows = {r["id"]: r for r in st.tables[cl.ACCOUNTS]}
    assert rows["acc1"]["limit_until"] and "usage limit" in rows["acc1"]["last_error"], "the used-up extra account rests"
    assert rows["acc2"]["limit_until"] is None and rows["acc2"]["last_ok_at"], "the one that drew is proven"
    main = st.tables[cl.TABLE][0]
    assert "usage limit" in main["last_error"] and "limit_until" not in main, "the main login only notes it: text still needs it"
    # the resting account is not listed until its rest is over
    assert names(cl.picture_logins(st)) == ["main", "acc2"]
    assert "acc1" in names(cl.picture_logins(st, datetime.now(UTC) + cl.LIMIT_REST + timedelta(minutes=1)))


def test_an_account_already_seen_to_fail_in_this_run_is_not_asked_again(monkeypatch):
    st = store(acc(1))
    asked = answers(monkeypatch, {"main": LIMIT, "acc1": PNG})
    logins, spent = cl.picture_logins(st, NOW), set()
    cl.draw_any(st, "one", logins=logins, skip=spent)
    cl.draw_any(st, "two", logins=logins, skip=spent)
    assert [n for n, _ in asked] == ["main", "acc1", "acc1"]


def test_a_refused_login_or_a_plan_with_no_model_hands_over_and_is_noted_without_a_rest(monkeypatch):
    st = store(acc(1), acc(2))
    answers(monkeypatch, {"main": REFUSED, "acc1": NO_MODEL, "acc2": PNG})
    _, login, _ = cl.draw_any(st, "a flask", logins=cl.picture_logins(st, NOW))
    assert cl.name_of(login) == "acc2"
    row = next(r for r in st.tables[cl.ACCOUNTS] if r["id"] == "acc1")
    assert row["limit_until"] is None and "no model" in row["last_error"]


def test_a_failure_that_is_the_same_for_every_account_is_raised_at_once(monkeypatch):
    st = store(acc(1))
    asked = answers(monkeypatch, {"main": DOWN, "acc1": PNG})
    with pytest.raises(cl.ChatGPTError) as e:
        cl.draw_any(st, "a flask", logins=cl.picture_logins(st, NOW))
    assert not e.value.limit and [n for n, _ in asked] == ["main"], "no other account is spent on an outage"


def test_when_no_account_draws_the_error_says_limit_only_if_every_one_was_at_its_limit(monkeypatch):
    st = store(acc(1))
    answers(monkeypatch, {"main": LIMIT, "acc1": LIMIT})
    spent = set()
    with pytest.raises(cl.ChatGPTError) as e:
        cl.draw_any(st, "a flask", logins=cl.picture_logins(st, NOW), skip=spent)
    assert e.value.limit and "2" in str(e.value)
    with pytest.raises(cl.ChatGPTError) as again:                      # everyone already failed in this run: nobody is asked
        cl.draw_any(st, "a flask", logins=cl.picture_logins(st, NOW), skip=spent)
    assert again.value.limit
    st2 = store(acc(1))
    answers(monkeypatch, {"main": LIMIT, "acc1": REFUSED})
    with pytest.raises(cl.ChatGPTError) as mixed:
        cl.draw_any(st2, "a flask", logins=cl.picture_logins(st2, NOW))
    assert mixed.value.auth and not mixed.value.limit
    with pytest.raises(cl.ChatGPTError) as none:
        cl.draw_any(FakeStore(), "a flask")
    assert none.value.auth


def test_a_pinned_chat_model_is_asked_of_every_account_and_a_picture_model_goes_to_the_tool(monkeypatch):
    st = store(acc(1))
    seen = []

    def draw(self, prompt, *, size="1024x1024", model=cl.DEFAULT_MODEL, timeout=300, image_model=""):
        seen.append((cl.name_of(self), model, image_model))
        if cl.name_of(self) == "main":
            raise LIMIT
        return PNG
    monkeypatch.setattr(cl.Login, "draw", draw)
    cl.draw_any(st, "a flask", model="gpt-pinned", logins=cl.picture_logins(st, NOW))
    cl.draw_any(st, "a flask", image_model="gpt-image-2", logins=cl.picture_logins(st, NOW))
    assert seen == [("main", "gpt-pinned", ""), ("acc1", "gpt-pinned", ""),
                    ("main", "gpt-main", "gpt-image-2"), ("acc1", "gpt-acc1", "gpt-image-2")]


# ---- the picture provider (pictures, slides, comics) ----------------------------------------------------------------------
def test_the_picture_provider_draws_with_the_next_account_and_the_job_says_which(monkeypatch):
    st = store(acc(1))
    asked = answers(monkeypatch, {"main": LIMIT, "acc1": PNG})
    p = media_generator.ChatGPTImageProvider(st)
    one = p.generate_from_text("a flask", {})
    two = p.generate_from_text("a beaker", {})
    assert one.meta == {"chatgpt_model": "gpt-acc1", "chatgpt_account": "acc1"} and two.meta["chatgpt_account"] == "acc1"
    assert [n for n, _ in asked] == ["main", "acc1", "acc1"], "the used-up main login is asked once in this run"


def test_the_provider_hands_over_to_the_next_maker_only_when_no_account_draws(monkeypatch):
    st = store(acc(1))
    answers(monkeypatch, {"main": LIMIT, "acc1": LIMIT})
    with pytest.raises(ProviderError) as e:
        media_generator.ChatGPTImageProvider(st).generate_from_text("a flask", {})
    assert e.value.kind == "limit"


def test_chatgpt_counts_as_connected_with_only_an_extra_account_and_not_when_the_switch_is_off():
    assert media_generator.has_credentials("chatgpt", None, store(acc(1), main=False))       # the settings are not read for it
    assert not media_generator.has_credentials("chatgpt", None, store(acc(1), enabled=False))
    with pytest.raises(ProviderError) as e:
        media_generator.ChatGPTImageProvider(store(acc(1), enabled=False))
    assert e.value.kind == "auth"


# ---- a film's scene pictures -----------------------------------------------------------------------------------------------
ROW = {"id": "m1", "title": "Tabir suria", "brief": "SPF", "stream": "regulab"}
SCENES = [{"id": f"s{i}", "kind": "point", "heading": f"Scene {i}", "body": "text"} for i in range(1, 5)]
PAL = {"bg": "#ffffff", "ink": "#111111", "accent": "#0a7"}


class Off:
    def ready(self):
        return False

    def max_images(self):
        return 6


def film(st, tmp_path):
    return gi.draw_scenes(st, ROW, SCENES, tmp_path, design="bright-editorial", palette=PAL, ambient="mint",
                          resolution="square", style_name="", gemini=Off(), cloudflare=Off())


def picture():
    import io
    import os

    from PIL import Image
    buf = io.BytesIO()
    Image.frombytes("RGB", (300, 300), os.urandom(300 * 300 * 3)).save(buf, "PNG")
    return buf.getvalue()


def test_a_film_goes_on_with_the_next_account_when_the_main_one_is_used_up(monkeypatch, tmp_path):
    st = store(acc(1))
    left = {"main": 1}

    def draw(self, prompt, *, size="1024x1024", model=cl.DEFAULT_MODEL, timeout=300, image_model=""):
        if cl.name_of(self) == "main":
            if left["main"] <= 0:
                raise LIMIT
            left["main"] -= 1
        return picture()
    monkeypatch.setattr(cl.Login, "draw", draw)
    drawn, note = film(st, tmp_path)
    assert list(drawn) == ["s1", "s2", "s3", "s4"], "the scene the main login refused is drawn by the next account, not lost"
    assert "4 of 4" in note and "account acc1 drew" in note and "usage limit" in note
    assert st.tables[cl.TABLE][0]["last_ok_at"] and st.tables[cl.ACCOUNTS][0]["last_ok_at"], "both drew, both are proven"


def test_a_film_stops_asking_chatgpt_only_when_every_account_is_used_up(monkeypatch, tmp_path):
    st = store(acc(1))
    asked = answers(monkeypatch, {"main": LIMIT, "acc1": LIMIT})
    drawn, note = film(st, tmp_path)
    assert drawn == {} and [n for n, _ in asked] == ["main", "acc1"], "each account is asked once, not once a scene"
    assert st.tables[cl.ACCOUNTS][0]["limit_until"]


def test_a_film_with_no_main_login_draws_with_an_extra_account_and_the_switch_still_turns_it_off(monkeypatch, tmp_path):
    answers(monkeypatch, {"acc1": picture()})
    st = store(acc(1, max_images=2), main=False)
    assert gi.ready(st, gemini=Off(), cloudflare=Off())
    drawn, _ = film(st, tmp_path)
    assert list(drawn) == ["s1", "s2"], "the extra account's own picture count is used"
    off = store(acc(1), enabled=False)
    assert not gi.ready(off, gemini=Off(), cloudflare=Off())
    assert film(off, tmp_path) == ({}, "ChatGPT pictures: switched off")


# ---- adding an account: the same link-and-code login, saved as its own row ------------------------------------------------
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
    def __init__(self, *answers_):
        self.answers = list(answers_)

    def post(self, url, **kw):
        return self.answers.pop(0)


CODE = Resp(200, {"device_auth_id": "deviceauth_abc", "user_code": "3CA1-GJOWC", "interval": "5",
                  "expires_at": (NOW + timedelta(minutes=15)).isoformat()})
APPROVED = Resp(200, {"authorization_code": "ac-1", "code_verifier": "cv-1"})
EXP = int((NOW + timedelta(days=9)).timestamp())


def tokens(email, refresh="rt-new"):
    return Resp(200, {"id_token": jwt(email=email), "access_token": jwt(exp=EXP), "refresh_token": refresh})


def login_run(st, email, refresh="rt-new"):
    clock = {"t": NOW}

    def sleep(_s):
        clock["t"] += timedelta(minutes=1)
    return dev.run(st, http=Http(CODE, APPROVED, tokens(email, refresh)), sleep=sleep, now=lambda: clock["t"])


def asked_for(target, *extras, **main):
    st = store(*extras, **main)
    st.tables[dev.TABLE] = [{"id": "main", "state": "requested", "requested_at": "T1", "target": target}]
    return st


def test_a_code_asked_for_one_more_account_saves_a_new_row_and_never_touches_the_main_login():
    st = asked_for("new")
    assert login_run(st, "second@example.com") == "done: ChatGPT account acc1 is connected for pictures"
    row = st.tables[cl.ACCOUNTS][0]
    assert row["id"] == "acc1" and row["account"] == "second@example.com" and row["auth"]["tokens"]["refresh_token"] == "rt-new"
    assert row["access_expires_at"].startswith("2026-12-03")
    assert st.tables[cl.TABLE][0] == main_row(), "the main login is exactly as it was"
    assert st.tables[dev.TABLE][0]["state"] == "done" and st.tables[dev.TABLE][0]["user_code"] is None
    assert names(cl.picture_logins(st, NOW)) == ["main", "acc1"], "and it is asked for pictures from now on"


def test_the_next_account_takes_the_lowest_free_number():
    st = asked_for("new", acc(1), acc(3))
    assert "acc2" in login_run(st, "second@example.com")
    assert sorted(r["id"] for r in st.tables[cl.ACCOUNTS]) == ["acc1", "acc2", "acc3"]


def test_the_main_logins_own_account_is_refused_as_an_extra_one():
    st = asked_for("new")
    out = login_run(st, "WAN@example.com ")
    assert out.startswith("error") and "different ChatGPT account" in out
    assert st.tables[cl.ACCOUNTS] == [] and st.tables[cl.TABLE][0] == main_row()
    dv = st.tables[dev.TABLE][0]
    assert dv["state"] == "error" and "different ChatGPT account" in dv["error"] and dv["user_code"] is None


def test_logging_in_again_with_an_extra_account_repairs_its_row_and_ends_its_rest():
    later = (NOW + timedelta(hours=2)).isoformat()
    st = asked_for("new", acc(1, limit_until=later, last_error="refused", enabled=False))
    assert "acc1" in login_run(st, "extra1@example.com", refresh="rt-again")
    row, = st.tables[cl.ACCOUNTS]
    assert row["auth"]["tokens"]["refresh_token"] == "rt-again" and row["limit_until"] is None and row["last_error"] is None
    assert row["enabled"] is False and row["model"] == "gpt-acc1", "its switch and its model stay as set"


def test_a_ninth_account_is_refused():
    st = asked_for("new", *[acc(n) for n in range(1, cl.MAX_ACCOUNTS + 1)])
    out = login_run(st, "ninth@example.com")
    assert out.startswith("error") and "remove one first" in out and len(st.tables[cl.ACCOUNTS]) == cl.MAX_ACCOUNTS


def test_a_code_for_the_main_login_still_saves_the_main_login():
    for target in ("main", None):
        st = asked_for(target, acc(1))
        assert login_run(st, "other@example.com") == "done: ChatGPT is connected"
        assert st.tables[cl.TABLE][0]["account"] == "other@example.com" and len(st.tables[cl.ACCOUNTS]) == 1


# ---- the 6-hourly check keeps the extra logins alive ------------------------------------------------------------------------
def test_the_check_refreshes_every_extra_account_and_names_them_by_id_only(monkeypatch):
    st = store(acc(1), acc(2, auth={"tokens": {}}), acc(3))

    def refresh(self, force=False):
        if self.row_id == "acc3":
            raise cl.ChatGPTError("ChatGPT refused the saved login (401)", auth=True)
        return "at", "acct"
    monkeypatch.setattr(cl.Login, "refresh", refresh)
    lines = cl.check_accounts(st)
    assert lines == ["ChatGPT account acc1: accepted", "ChatGPT account acc2: no login saved",
                     "ChatGPT account acc3: ChatGPT refused the saved login (401)"]
    assert "example.com" not in " ".join(lines), "never an e-mail in a log"
    rows = {r["id"]: r for r in st.tables[cl.ACCOUNTS]}
    assert rows["acc1"]["checked_at"] and "refused" in rows["acc3"]["last_error"]
    assert cl.check_accounts(FakeStore()) == []


def test_an_extra_accounts_own_model_and_reasoning_reach_its_requests():
    logins = cl.picture_logins(store(acc(1, model="gpt-6.2-sol", reasoning="medium")))
    extra = next(x for x in logins if cl.name_of(x) == "acc1")
    assert extra.settings()["model"] == "gpt-6.2-sol" and extra.settings()["reasoning"] == "medium"
    assert extra._body("a lab", "gpt-6.2-sol", "1024x1024", 0)["reasoning"] == {"effort": "medium"}
    main = next(x for x in logins if cl.name_of(x) == "main")
    assert "reasoning" not in main._body("a lab", "gpt-main", "1024x1024", 0)
