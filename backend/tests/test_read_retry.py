import httpx
import pytest

from semasa import db


class Q:
    def __init__(self, fails, exc=httpx.RemoteProtocolError):
        self.fails, self.calls, self.exc = fails, 0, exc

    def execute(self):
        self.calls += 1
        if self.calls <= self.fails:
            raise self.exc("Server disconnected")
        return "rows"


def test_retries_a_dropped_read(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    q = Q(2)
    assert db.read_with_retry(q) == "rows"
    assert q.calls == 3


def test_gives_up_after_three(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    q = Q(5, httpx.WriteError)
    with pytest.raises(httpx.WriteError):
        db.read_with_retry(q)
    assert q.calls == 3


def test_other_errors_are_not_retried(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    q = Q(1, ValueError)
    with pytest.raises(ValueError):
        db.read_with_retry(q)
    assert q.calls == 1
