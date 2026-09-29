"""The two roads out (senders.py) against a recorded fake of the HTTP layer: what goes on the wire, and how every
answer is named (full / transient / refused)."""

import json

import pytest

from semasa import senders


class Resp:
    def __init__(self, status=200, body=None, headers=None, content=b""):
        self.status_code, self._body, self.headers, self.content = status, body, headers or {}, content

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


class Session:
    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def _next(self, method, url, **kw):
        self.calls.append((method, url, kw))
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a

    def post(self, url, **kw):
        return self._next("POST", url, **kw)

    def get(self, url, **kw):
        return self._next("GET", url, **kw)

    def put(self, url, **kw):
        return self._next("PUT", url, **kw)

    def request(self, method, url, **kw):
        return self._next(method, url, **kw)


OK_POST = {"data": {"createPost": {"__typename": "PostActionSuccess",
                                   "post": {"id": "a" * 24, "status": "scheduled", "dueAt": "2026-10-03T00:00:00Z"}}}}


def test_buffer_create_sends_studios_exact_shape():
    s = Session(Resp(body=OK_POST))
    p = senders.Buffer("k", "org", session=s).create("ig1", "instagram", "Kapsyen", ["https://x/1.jpg"], "alt",
                                                      "2026-10-03T00:00:00+00:00")
    assert p["id"] == "a" * 24
    method, url, kw = s.calls[0]
    inp = kw["json"]["variables"]["input"]
    assert kw["headers"]["Authorization"] == "Bearer k"
    assert inp["mode"] == "customScheduled" and inp["dueAt"] == "2026-10-03T00:00:00+00:00"
    assert inp["metadata"] == {"instagram": {"type": "post", "shouldShareToFeed": False}}
    assert inp["assets"] == [{"image": {"url": "https://x/1.jpg", "metadata": {"altText": "alt"}}}]
    assert inp["schedulingType"] == "automatic" and inp["saveToDraft"] is False


def test_buffer_share_now_has_no_due_time_and_threads_has_no_metadata():
    s = Session(Resp(body=OK_POST))
    senders.Buffer("k", "org", session=s).create("th1", "threads", "t", [], "", None)
    inp = s.calls[0][2]["json"]["variables"]["input"]
    assert inp["mode"] == "shareNow" and "dueAt" not in inp and "metadata" not in inp


@pytest.mark.parametrize("answer,kind", [
    ({"data": {"createPost": {"__typename": "LimitReachedError",
                              "message": "Limit reached: Scheduled posts limit reached"}}}, "full"),
    ({"data": {"createPost": {"__typename": "InvalidInputError", "message": "Text is too long"}}}, "refused"),
    ({"errors": [{"message": "Internal error, please try again"}]}, "transient"),
])
def test_buffer_errors_are_named(answer, kind):
    with pytest.raises(senders.SendError) as e:
        senders.Buffer("k", "org", session=Session(Resp(body=answer))).create("f", "facebook", "t", [], "", None)
    assert e.value.kind == kind


def test_buffer_5xx_and_429_are_transient():
    for code in (429, 502):
        with pytest.raises(senders.SendError) as e:
            senders.Buffer("k", "org", session=Session(Resp(status=code, body={}))).get("x")
        assert e.value.kind == "transient"


def test_buffer_confirm_polls_until_settled_and_never_calls_unsettled_sent():
    sending = {"data": {"post": {"id": "p", "status": "sending"}}}
    b = senders.Buffer("k", "org", session=Session(*[Resp(body=sending)] * 3), sleep=lambda _s: None)
    got = b.confirm("p", tries=3)
    assert got["unconfirmed"] is True and got["status"] == "sending"


def test_buffer_posts_pages_through():
    page1 = {"data": {"posts": {"edges": [{"node": {"id": "1"}}], "pageInfo": {"hasNextPage": True, "endCursor": "c"}}}}
    page2 = {"data": {"posts": {"edges": [{"node": {"id": "2"}}], "pageInfo": {"hasNextPage": False}}}}
    s = Session(Resp(body=page1), Resp(body=page2))
    assert [p["id"] for p in senders.Buffer("k", "org", session=s).posts(["c1"], "a", "b")] == ["1", "2"]
    assert s.calls[1][2]["json"]["variables"]["after"] == "c"


def test_linkedin_card_post_uploads_each_picture_then_posts_once():
    s = Session(
        Resp(body={"items": [{"id": "ca_1"}]}),                                           # the one LinkedIn account
        Resp(headers={"content-type": "image/jpeg"}, content=b"JPEGDATA"),                # fetch slide 1
        Resp(body={"id": "f", "key": "s3/key1", "type": "x", "new_presigned_url": "https://s3/put1"}),
        Resp(status=200),                                                                 # PUT to S3
        Resp(body={"successful": True, "data": {"x_restli_id": "urn:li:share:9"}}),
    )
    # account() is asked lazily, after the uploads: the order on the wire is fetch, presign, put, account, execute
    s.answers = [s.answers[1], s.answers[2], s.answers[3], s.answers[0], s.answers[4]]
    res = senders.LinkedIn("key", "urn:li:person:X", session=s).post("Hello", ["https://cdn/1.jpg"])
    assert res.urn == "urn:li:share:9"
    presign = s.calls[1][2]["json"]
    assert presign["tool_slug"] == "LINKEDIN_CREATE_LINKED_IN_POST" and presign["mimetype"] == "image/jpeg"
    assert s.calls[2][2]["data"] == b"JPEGDATA" and s.calls[2][2]["headers"]["Content-Type"] == "image/jpeg"
    body = s.calls[4][2]["json"]
    assert s.calls[4][1].endswith("/api/v3.1/tools/execute/LINKEDIN_CREATE_LINKED_IN_POST")
    assert body["connected_account_id"] == "ca_1"
    assert body["arguments"]["images"] == [{"name": "slide-01.jpg", "mimetype": "image/jpeg", "s3key": "s3/key1"}]
    assert s.calls[4][2]["headers"]["x-api-key"] == "key"


def test_linkedin_text_post_has_no_images_key():
    s = Session(Resp(body={"successful": True, "data": {"x_restli_id": "urn:li:share:1"}}))
    senders.LinkedIn("k", "urn:li:person:X", session=s, account_id="ca_1").post("Just words", [])
    assert "images" not in s.calls[0][2]["json"]["arguments"]


def test_linkedin_refuses_to_guess_the_account():
    s = Session(Resp(body={"items": [{"id": "a"}, {"id": "b"}]}))
    with pytest.raises(senders.SendError) as e:
        senders.LinkedIn("k", "urn:li:person:X", session=s).post("t", [])
    assert "exactly 1" in e.value.message


def test_linkedin_bad_picture_and_missing_urn_are_refusals():
    s = Session(Resp(status=404, headers={"content-type": "text/html"}))
    with pytest.raises(senders.SendError) as e:
        senders.LinkedIn("k", "urn:li:person:X", session=s, account_id="c").post("t", ["https://x/1.jpg"])
    assert e.value.kind == "refused"
    s = Session(Resp(body={"successful": True, "data": {}}))
    with pytest.raises(senders.SendError) as e:
        senders.LinkedIn("k", "urn:li:person:X", session=s, account_id="c").post("t", [])
    assert "without a post id" in e.value.message


def test_text_key_ignores_spacing():
    assert senders.text_key("A  b\n\nc") == senders.text_key("A b c")
    assert json.dumps(senders.text_key("x" * 300)).count("x") == 100
