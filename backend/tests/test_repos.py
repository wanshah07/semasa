"""Repo tracker: GitHub's answers → one semasa_repos row with six dimensions."""

from datetime import UTC, datetime

from fakestore import FakeStore

from semasa import db, repos

NOW = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)


class FakeGitHub:
    """Answers by exact path, with "?state=open" / "?state=closed" keys for the pulls list; counts calls like the real one."""

    def __init__(self, answers):
        self.answers, self.calls = answers, 0

    def get(self, path, params=None, *, raw=False):
        self.calls += 1
        state = (params or {}).get("state")
        key = f"{path}?state={state}" if state and f"{path}?state={state}" in self.answers else path
        if key in self.answers:
            return self.answers[key]
        raise LookupError(f"404 {path}")

    def maybe(self, path, params=None, *, raw=False, default=None):
        try:
            return self.get(path, params, raw=raw)
        except LookupError:
            return default


def _gh():
    base = "/repos/wanshah07/semasa"
    return FakeGitHub(
        {
            base + "/commits": [
                {
                    "sha": "abc1234567",
                    "commit": {
                        "message": "Prestasi: post analytics\n\nlong body",
                        "committer": {"date": "2026-10-09T05:00:00Z"},
                        "author": {"name": "Wan", "date": "2026-10-09T05:00:00Z"},
                    },
                },
                {
                    "sha": "def",
                    "commit": {
                        "message": "older",
                        "committer": {"date": "2026-09-20T05:00:00Z"},
                        "author": {"name": "Wan", "date": "2026-09-20T05:00:00Z"},
                    },
                },
            ],
            base + "/pulls?state=open": [
                {
                    "number": 52,
                    "title": "Prestasi",
                    "draft": True,
                    "updated_at": "2026-10-09T05:00:00Z",
                    "html_url": "u",
                    "head": {"sha": "abc"},
                }
            ],
            base + "/pulls?state=closed": [
                {"number": 51, "merged_at": "2026-10-08T05:00:00Z"},
                {"number": 3, "merged_at": "2026-08-01T05:00:00Z"},
                {"number": 4, "merged_at": None},
            ],
            base + "/commits/abc/check-runs": {
                "check_runs": [{"status": "completed", "conclusion": "success"}, {"status": "completed", "conclusion": "success"}]
            },
            base + "/issues": [
                {"number": 7, "title": "An issue", "updated_at": "2026-10-01T00:00:00Z", "html_url": "i"},
                {"number": 52, "title": "PR as issue", "pull_request": {"url": "p"}},
            ],
            base + "/actions/workflows": {
                "workflows": [
                    {"id": 1, "name": "CI", "path": ".github/workflows/ci.yml", "state": "active"},
                    {"id": 2, "name": "Publish", "path": ".github/workflows/publish.yml", "state": "active"},
                    {"id": 3, "name": "Old", "path": ".github/workflows/old.yml", "state": "disabled_manually"},
                ]
            },
            base + "/contents/.github/workflows/ci.yml": "on:\n  push:\n",
            base + "/contents/.github/workflows/publish.yml": "on:\n  schedule:\n    - cron: '20 22,3,11 * * *'   # 06:20 MYT\n",
            base + "/actions/workflows/1/runs": {
                "workflow_runs": [
                    {"status": "completed", "conclusion": "success", "updated_at": "2026-10-09T05:01:00Z", "html_url": "r1"}
                ]
            },
            base + "/actions/workflows/2/runs": {
                "workflow_runs": [
                    {"status": "completed", "conclusion": "failure", "updated_at": "2026-10-09T03:21:00Z", "html_url": "r2"}
                ]
            },
            base + "/pages": {"html_url": "https://semasa.kkmhalalconsultant.com/", "status": "built"},
            base + "/pages/builds/latest": {"status": "built", "updated_at": "2026-10-09T05:02:00Z"},
            base: {
                "name": "semasa",
                "description": "",
                "private": False,
                "default_branch": "main",
                "html_url": "h",
                "pushed_at": "2026-10-09T05:00:00Z",
                "has_pages": True,
            },
        }
    )


def test_read_repo_builds_the_six_dimensions():
    row = repos.read_repo(_gh(), "wanshah07/semasa", NOW)
    assert row["commits_7d"] == 1 and row["commits_30d"] == 2
    assert row["last_commit"]["sha"] == "abc1234" and row["last_commit"]["message"] == "Prestasi: post analytics"
    assert [p["number"] for p in row["open_prs"]] == [52] and row["open_prs"][0]["ci"] == "green"
    assert row["merged_30d"] == 1  # one merged in the window, one too old, one closed unmerged
    assert row["open_issues"] == 1  # the PR masquerading as an issue is not counted
    assert len(row["workflows"]) == 2  # the disabled one is dropped
    assert row["workflows"][1]["cron"] == "20 22,3,11 * * *"
    assert row["ci"] == "red"  # Publish's latest run failed
    assert row["pages"]["url"].startswith("https://semasa")
    assert row["progress"] == 50  # 1 merged ÷ (1 merged + 1 open)
    assert set(row["dims"]) == set(repos.DIM_KEYS)
    assert row["dims"]["ci"]["state"] == "bad" and "Publish" in row["dims"]["ci"]["detail"]
    assert row["dims"]["schedules"]["state"] == "bad"  # the failing workflow is the cron one
    assert row["dims"]["deploy"]["state"] == "ok"
    assert len(row["commit_days"]) == 14 and row["commit_days"][-1] == {"date": "2026-10-09", "n": 1}


def test_health_penalises_red_ci_and_staleness():
    fresh = {"ci": "green", "pushed_at": "2026-10-09T05:00:00Z", "open_prs": [], "open_issues": 0, "workflows": []}
    assert repos.health_of(fresh, NOW) == 100
    stale_red = {
        "ci": "red",
        "pushed_at": "2026-08-01T05:00:00Z",
        "open_prs": [{"ci": "red"}] * 4,
        "open_issues": 9,
        "workflows": [{"cron": "1 2 * * *", "last": {"conclusion": "failure"}}],
    }
    assert repos.health_of(stale_red, NOW) == 100 - 30 - 20 - 10 - 10 - 10 - 10


def test_ci_of_states():
    assert repos.ci_of([]) == "none"
    assert repos.ci_of([{"last": {"status": "completed", "conclusion": "success"}}]) == "green"
    assert (
        repos.ci_of(
            [{"last": {"status": "in_progress", "conclusion": None}}, {"last": {"status": "completed", "conclusion": "success"}}]
        )
        == "running"
    )
    assert repos.ci_of([{"last": {"status": "completed", "conclusion": "failure"}}, {"last": {"status": "in_progress"}}]) == "red"


def test_crons_of_reads_quoted_and_bare():
    assert repos.crons_of('on:\n  schedule:\n    - cron: "10 5 * * *"\n    - cron: 0 */6 * * *  # six-hourly\n') == [
        "10 5 * * *",
        "0 */6 * * *",
    ]
    assert repos.crons_of("on: push\n") == []


def test_run_upserts_and_keeps_an_unreadable_repo_with_its_error():
    names = ["wanshah07/semasa", "wanshah07/private-one"]
    store = FakeStore(**{db.SETTINGS: [{"key": "repos", "value": {"list": names, "days": 30}}]})
    out = repos.run(store, _gh(), NOW)
    assert out == {"ok": 1, "failed": 1, "calls": out["calls"]}
    rows = {r["full_name"]: r for r in store.tables[db.REPOS]}
    assert rows["wanshah07/semasa"]["health"] < 100 and rows["wanshah07/semasa"]["error"] == ""
    assert rows["wanshah07/private-one"]["error"].startswith("404")
    assert store.tables[db.LOG][0]["area"] == "repos"
    # a second run updates in place
    repos.run(store, _gh(), NOW)
    assert len(store.tables[db.REPOS]) == 2
