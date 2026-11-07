"""The Motion queue (7 Nov 2026 review): one film claimed at a time inside a time budget, and a film left 'working' by a runner
that died goes back to 'pending', or to 'error' once it has had MAX_ATTEMPTS. The storyboard gate itself is not touched here."""

from datetime import UTC, datetime

from test_motion import FakeLLM, Store, _row

from semasa import motion

NOW = datetime(2026, 11, 7, 6, 0, tzinfo=UTC)
OLD = "2026-11-07T04:00:00+00:00"            # two hours before NOW: a runner that died long ago
FRESH = "2026-11-07T05:50:00+00:00"          # ten minutes before NOW: still being made


def _status(store, row):
    return store.table(motion.TABLE).select("*").eq("id", row["id"]).execute().data[0]


def test_films_are_claimed_one_at_a_time_and_only_while_each_is_made(monkeypatch):
    store = Store()
    rows = [_row(store, created_at=f"2026-11-07T0{i}:00:00Z") for i in range(4)]
    working_at_once = []

    def process(s, llm, row, settings, **kw):
        working_at_once.append(sum(r["status"] == "working" for r in s.tables[motion.TABLE]))
        s.table(motion.TABLE).update({"status": "done"}).eq("id", row["id"]).execute()
        return True
    monkeypatch.setattr(motion, "process", process)
    assert motion.run(store, FakeLLM([]), now=NOW) == {"claimed": 4, "done": 4, "failed": 0}
    assert working_at_once == [1, 1, 1, 1], "never more than the one film being made is 'working'"
    assert all(_status(store, r)["status"] == "done" for r in rows)


def test_no_new_film_is_started_after_the_budget_and_the_rest_stay_pending(monkeypatch):
    store = Store()
    rows = [_row(store, created_at=f"2026-11-07T0{i}:00:00Z") for i in range(3)]
    ticks = iter([0, 0, 10 * 60, motion.CLAIM_BUDGET_S + 1, motion.CLAIM_BUDGET_S + 2])
    made = []

    def process(s, llm, row, settings, **kw):
        made.append(row["id"])
        s.table(motion.TABLE).update({"status": "done"}).eq("id", row["id"]).execute()
        return True
    monkeypatch.setattr(motion, "process", process)
    out = motion.run(store, FakeLLM([]), now=NOW, clock=lambda: next(ticks))
    assert out == {"claimed": 2, "done": 2, "failed": 0}
    assert made == [rows[0]["id"], rows[1]["id"]]
    left = _status(store, rows[2])
    assert left["status"] == "pending" and int(left["attempts"] or 0) == 0, "an unstarted film is not charged an attempt"


def test_a_film_that_fails_waits_for_the_next_run_rather_than_being_retried_at_once(monkeypatch):
    store = Store()
    r = _row(store)
    calls = []

    def process(s, llm, row, settings, **kw):
        calls.append(row["attempts"])
        s.table(motion.TABLE).update({"status": "pending", "error": "boom"}).eq("id", row["id"]).execute()
        return False
    monkeypatch.setattr(motion, "process", process)
    assert motion.run(store, FakeLLM([]), now=NOW) == {"claimed": 1, "done": 0, "failed": 1}
    assert calls == [1] and _status(store, r)["status"] == "pending"


def test_a_film_stuck_working_goes_back_to_the_queue_and_is_made_in_the_same_run(monkeypatch):
    store = Store()
    stuck = _row(store, status="working", attempts=1, updated_at=OLD, stage="film")
    seen = []

    def process(s, llm, row, settings, **kw):
        seen.append((row["id"], row["attempts"]))
        s.table(motion.TABLE).update({"status": "done"}).eq("id", row["id"]).execute()
        return True
    monkeypatch.setattr(motion, "process", process)
    out = motion.run(store, FakeLLM([]), now=NOW)
    assert out == {"claimed": 1, "done": 1, "failed": 0, "requeued": 1}
    assert seen == [(stuck["id"], 2)], "the second attempt, counted at the claim as always"


def test_a_film_that_killed_its_runner_max_attempts_times_ends_in_error_with_a_reason(monkeypatch):
    store = Store()
    dead = _row(store, status="working", attempts=motion.MAX_ATTEMPTS, updated_at=OLD)
    monkeypatch.setattr(motion, "process", lambda *a, **k: (_ for _ in ()).throw(AssertionError("never made again")))
    assert motion.run(store, FakeLLM([]), now=NOW) == {"claimed": 0, "done": 0, "failed": 0}
    got = _status(store, dead)
    assert got["status"] == "error"
    assert "stopped its runner" in got["error"] and "film" in got["error"]


def test_a_film_still_being_made_and_a_storyboard_waiting_for_wan_are_left_alone(monkeypatch):
    store = Store()
    live = _row(store, status="working", attempts=1, updated_at=FRESH)
    review = _row(store, status="review", attempts=1, updated_at=OLD, storyboard={"plan": {}})
    waiting = _row(store, status="waiting", attempts=0, updated_at=OLD)
    monkeypatch.setattr(motion, "process", lambda *a, **k: (_ for _ in ()).throw(AssertionError("nothing to claim")))
    assert motion.run(store, FakeLLM([]), now=NOW) == {"claimed": 0, "done": 0, "failed": 0}
    assert _status(store, live)["status"] == "working"
    assert _status(store, review)["status"] == "review", "the storyboard gate is Wan's; recovery never touches it"
    assert _status(store, waiting)["status"] == "waiting"


def test_requeue_never_stops_the_run_when_the_database_refuses(monkeypatch):
    store = Store()
    pending = _row(store)
    real = store.table

    def table(name):
        q = real(name)
        if name == motion.TABLE:
            run_q = q.execute

            def execute():
                if q.op == "update" and (q.payload or {}).get("status") in ("error",) and "runner" in str(q.payload.get("error")):
                    raise RuntimeError("database is down for a moment")
                return run_q()
            q.execute = execute
        return q
    store.table = table
    monkeypatch.setattr(motion, "process", lambda s, llm, row, settings, **kw: True)
    assert motion.run(store, FakeLLM([]), now=NOW)["claimed"] == 1
    assert _status(store, pending)["status"] == "working"
