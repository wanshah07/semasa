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


@pytest.fixture(autouse=True)
def no_live_ai_questions(monkeypatch):
    """The AI team router asks gateways a live five-token question at decision time (semasa.ai_team.Live). A test that wants it
    passes its own stand-in to route(); the real one never runs under test."""
    monkeypatch.setenv("AI_TEAM_LIVE", "0")


@pytest.fixture(autouse=True)
def writer_on(request, monkeypatch):
    """Most motion tests were written for the AI writer's path. The worker composes films itself by default (26 Oct 2026),
    so those tests switch the writer back on; a test marked `composed` runs the default path."""
    if "composed" in request.keywords:
        monkeypatch.delenv("MOTION_WRITER", raising=False)
    else:
        monkeypatch.setenv("MOTION_WRITER", "1")


FITTED: dict = {}      # the length the last film was fitted to: the fake ffprobe answers with it (a film is as long as it needs)


@pytest.fixture(autouse=True)
def remember_the_fitted_length(monkeypatch):
    from semasa import motion
    real = motion.fit_scenes

    def fit(*a, **k):
        out = real(*a, **k)
        FITTED["total"] = out[1]
        return out
    monkeypatch.setattr(motion, "fit_scenes", fit)
    FITTED.clear()
