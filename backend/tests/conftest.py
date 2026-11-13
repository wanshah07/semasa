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


@pytest.fixture(autouse=True)
def proofread_without_a_writer(request, monkeypatch):
    """The proofreader asks the writer one more question (semasa/proofread.py). Tests that count or script the writer's answers
    were written before it existed, so by default it runs its deterministic step only; `real_proofread` runs all of it."""
    if "real_proofread" in request.keywords:
        return
    from semasa import proofread
    real = proofread.proofread
    monkeypatch.setattr(proofread, "proofread", lambda llm, fields, lang: real(None, fields, lang))


@pytest.fixture(autouse=True)
def no_remotion_here(monkeypatch):
    """Whether Remotion is installed on the machine running the tests must not change what they see: its preview and its
    renders are tested on their own, with `ready` switched on and a stand-in runner."""
    from semasa import motion_remotion
    monkeypatch.setattr(motion_remotion, "ready", lambda: False)


@pytest.fixture(autouse=True)
def storyboard_approved(request, monkeypatch):
    """Every film now stops at its storyboard until Wan approves it (supabase/071, semasa/motion_review.py). Most motion tests
    were written for a whole film, so this stand-in plays Wan: when a run stops at 'review' it approves the saved storyboard,
    unchanged, and runs the worker again, exactly as the page's Approve does (the row keeps the caller's attempts). A test
    marked `storyboard_gate` runs the worker as it is and sees the stop."""
    if "storyboard_gate" in request.keywords:
        return
    from types import SimpleNamespace

    from semasa import motion
    real = motion.process
    # the storyboard's pictures are stored when it is written and fetched back once approved (Wan, 10 Nov 2026): the stand-in
    # keeps what was stored and serves it, so the approved film uses the pictures of its storyboard without the network
    stored: dict[str, bytes] = {}
    upload = motion.db.upload_generated

    def remember(db_, path, data, content_type):
        url = upload(db_, path, data, content_type)
        if path.startswith("motion/storyboard/"):
            stored[str(url)] = data
        return url

    def served(url):
        if url not in stored:
            raise OSError("not a stored storyboard picture")
        return SimpleNamespace(content=stored[url], raise_for_status=lambda: None)
    monkeypatch.setattr(motion.db, "upload_generated", remember)
    monkeypatch.setattr(motion, "picture_response", served)

    def process(store, llm, row, settings, **k):
        out = real(store, llm, row, settings, **k)
        try:
            got = store.table(motion.TABLE).select("*").eq("id", row["id"]).execute().data or []
        except Exception:  # noqa: BLE001 - a fake store without the row: nothing to approve
            return out
        if not got or got[0].get("status") != "review" or not got[0].get("storyboard"):
            return out
        stamp = "2026-11-07T00:00:00+00:00"
        store.table(motion.TABLE).update({"status": "pending", "storyboard_approved_at": stamp}).eq("id", row["id"]).execute()
        again = {**row, "storyboard": got[0]["storyboard"], "storyboard_approved_at": stamp, "status": "working",
                 "stage_times": got[0].get("stage_times") or row.get("stage_times")}
        return real(store, llm, again, settings, **k)
    monkeypatch.setattr(motion, "process", process)


@pytest.fixture(autouse=True)
def no_live_threads_browser(monkeypatch):
    """semasa.threads_web.fetch opens a real Chromium on threads.com, which no_network cannot see (it is not `requests`). Under
    test it reads nothing; a test of the reader passes its own page to threads_web.collect()."""
    from semasa import threads_web

    monkeypatch.setattr(threads_web, "fetch", lambda cfg, now=None: ([], ""))
