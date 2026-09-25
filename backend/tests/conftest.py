import pathlib

import pytest

FIX = pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture
def fixture():
    def _read(name: str) -> str:
        return (FIX / name).read_text(encoding="utf-8")
    return _read


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """A test that reaches the internet passes or fails on the day's weather, and in CI it would
    fetch real sites. Any real HTTP call fails the test loudly instead; a test that needs a page
    patches the function that fetches it."""
    import requests

    def refuse(*a, **k):
        raise AssertionError(f"a test tried to reach the network: {a[:2]}")
    monkeypatch.setattr(requests.Session, "request", refuse)
