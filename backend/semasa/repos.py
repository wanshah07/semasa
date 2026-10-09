"""Repo tracker: the office repositories, six dimensions each (Wan, 9 Oct 2026: "add all repo office environment in 6D in
the system so i can track the repos progress and status").

Reads GitHub for every repository named in settings.repos.list (the six by default: semasa, argus, argus-cards,
kkm-complaints, kpi-system, malaysian-regulatory-affairs) and writes one semasa_repos row each
(supabase/035_repos_api.sql). The six dimensions the page draws:

  code        commits in the last 7 and 30 days, the last commit, a 14-day sparkline
  prs         open pull requests (with the CI verdict on each head) and how many merged in 30 days
  ci          the latest run of every workflow: green when all pass, red when any fails
  issues      open issues (GitHub's open_issues_count includes PRs, so PRs are subtracted)
  schedules   workflows that run on a cron, with the cron read from the workflow file
  deploy      GitHub Pages: its address and the latest build

health (0..100) is a sum of penalties, progress is merged ÷ (merged + open) over 30 days. The page computes nothing it
cannot see in the row. A repository that cannot be read keeps its last row and carries the error.

Token: REPOS_TOKEN (a fine-grained PAT, read-only: Contents, Actions, Issues, Pull requests, Metadata, on every repo in the
list), else LANDING_REPO_TOKEN, else GITHUB_TOKEN (which only reads semasa itself; private repos then say 404).
"""

from __future__ import annotations

import logging
import os
import re
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

import requests

from . import db

log = logging.getLogger("semasa.repos")
SETTINGS_KEY = "repos"
DEFAULT_LIST = [
    "wanshah07/semasa",
    "wanshah07/argus",
    "wanshah07/argus-cards",
    "wanshah07/kkm-complaints",
    "wanshah07/kpi-system",
    "wanshah07/malaysian-regulatory-affairs",
]
API = "https://api.github.com"
CRON_RE = re.compile(r"^\s*-\s*cron:\s*['\"]?([^'\"#\n]+?)['\"]?\s*(#.*)?$", re.M)
DIM_KEYS = ("code", "prs", "ci", "issues", "schedules", "deploy")


class GitHub:
    """The few GitHub reads the tracker makes. Every call is one GET; a 404 on a private repo means the token cannot see it."""

    def __init__(self, token: str | None, timeout: int = 30):
        self.timeout = timeout
        self.headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if token:
            self.headers["Authorization"] = f"Bearer {token}"
        self.calls = 0

    def get(self, path: str, params: dict[str, Any] | None = None, *, raw: bool = False) -> Any:
        self.calls += 1
        headers = dict(self.headers)
        if raw:
            headers["Accept"] = "application/vnd.github.raw+json"
        r = requests.get(f"{API}{path}", headers=headers, params=params, timeout=self.timeout)
        if r.status_code == 404:
            raise LookupError(f"404 {path}")
        r.raise_for_status()
        return r.text if raw else r.json()

    def maybe(self, path: str, params: dict[str, Any] | None = None, *, raw: bool = False, default: Any = None) -> Any:
        try:
            return self.get(path, params, raw=raw)
        except (LookupError, requests.RequestException, ValueError) as exc:
            log.info("%s: %s", path, str(exc)[:120])
            return default


def load_settings(store: Any) -> dict[str, Any]:
    rows = store.table(db.SETTINGS).select("key,value").eq("key", SETTINGS_KEY).execute().data or []
    raw = rows[0]["value"] if rows and isinstance(rows[0].get("value"), dict) else {}
    names = [str(n).strip() for n in (raw.get("list") or DEFAULT_LIST) if str(n).strip()]
    return {"list": names or DEFAULT_LIST, "days": int(raw.get("days") or 30)}


def commit_days(commits: list[dict[str, Any]], now: datetime, days: int = 14) -> list[dict[str, Any]]:
    """[{date, n}] for the last `days` days, oldest first, every day present."""
    counts: dict[str, int] = {}
    for c in commits:
        at = (
            ((c.get("commit") or {}).get("committer") or {}).get("date")
            or ((c.get("commit") or {}).get("author") or {}).get("date")
            or ""
        )
        if at:
            counts[at[:10]] = counts.get(at[:10], 0) + 1
    out = []
    for i in range(days - 1, -1, -1):
        d = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        out.append({"date": d, "n": counts.get(d, 0)})
    return out


def crons_of(text: str) -> list[str]:
    return [m.group(1).strip() for m in CRON_RE.finditer(text or "")]


def ci_of(workflows: list[dict[str, Any]]) -> str:
    """green when every workflow's latest completed run passed, red when any failed, running when one is still going."""
    seen = False
    running = False
    for w in workflows:
        last = w.get("last") or {}
        if not last:
            continue
        seen = True
        if last.get("status") in ("queued", "in_progress", "waiting", "requested"):
            running = True
        elif last.get("conclusion") not in (None, "success", "skipped", "neutral"):
            return "red"
    return "running" if running else "green" if seen else "none"


def health_of(row: dict[str, Any], now: datetime) -> int:
    """100 minus penalties. The figure is a ranking, not a verdict; the dims say what to look at."""
    score = 100
    if row.get("ci") == "red":
        score -= 30
    pushed = row.get("pushed_at")
    if pushed:
        age = (now - datetime.fromisoformat(pushed.replace("Z", "+00:00"))).days
        if age > 30:
            score -= 20
        elif age > 14:
            score -= 10
    open_prs = row.get("open_prs") or []
    if len(open_prs) > 3:
        score -= 10
    if any((p.get("ci") == "red") for p in open_prs):
        score -= 10
    if (row.get("open_issues") or 0) > 5:
        score -= 10
    failing_cron = [
        w
        for w in row.get("workflows") or []
        if w.get("cron") and (w.get("last") or {}).get("conclusion") not in (None, "success", "skipped", "neutral")
    ]
    if failing_cron:
        score -= 10
    return max(0, min(100, score))


def dims_of(row: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The six dimensions, each {state: ok|warn|bad|none, label, detail}: what the page draws as six tiles."""
    code_n = row.get("commits_7d") or 0
    last = row.get("last_commit") or {}
    prs = row.get("open_prs") or []
    red_prs = [p for p in prs if p.get("ci") == "red"]
    wfs = row.get("workflows") or []
    crons = [w for w in wfs if w.get("cron")]
    bad_crons = [w for w in crons if (w.get("last") or {}).get("conclusion") not in (None, "success", "skipped", "neutral")]
    pages = row.get("pages") or {}
    ci = row.get("ci") or "none"
    return {
        "code": {
            "state": "ok" if code_n else "warn",
            "label": f"{code_n} / {row.get('commits_30d') or 0}",
            "detail": (last.get("message") or "")[:120],
        },
        "prs": {
            "state": "bad" if red_prs else "warn" if len(prs) > 3 else "ok",
            "label": f"{len(prs)} open · {row.get('merged_30d') or 0} merged",
            "detail": "; ".join(f"#{p.get('number')} {p.get('title', '')[:50]}" for p in prs[:3]),
        },
        "ci": {
            "state": "bad" if ci == "red" else "warn" if ci == "running" else "ok" if ci == "green" else "none",
            "label": ci,
            "detail": "; ".join(
                f"{w.get('name')}: {(w.get('last') or {}).get('conclusion') or (w.get('last') or {}).get('status') or '-'}"
                for w in wfs
                if (w.get("last") or {}).get("conclusion") not in (None, "success", "skipped", "neutral")
            )[:200],
        },
        "issues": {
            "state": "warn" if (row.get("open_issues") or 0) > 5 else "ok",
            "label": f"{row.get('open_issues') or 0} open",
            "detail": "; ".join(f"#{i.get('number')} {i.get('title', '')[:50]}" for i in (row.get("issues") or [])[:3]),
        },
        "schedules": {
            "state": "bad" if bad_crons else "ok" if crons else "none",
            "label": f"{len(crons)} cron",
            "detail": "; ".join(f"{w.get('name')} ({w.get('cron')})" for w in crons[:4])[:200],
        },
        "deploy": {
            "state": "bad" if pages.get("status") in ("errored", "failed") else "ok" if pages.get("url") else "none",
            "label": pages.get("url") or "no Pages",
            "detail": f"{pages.get('status') or ''} {pages.get('at') or ''}".strip(),
        },
    }


def read_repo(gh: GitHub, full_name: str, now: datetime, days: int = 30) -> dict[str, Any]:
    owner, name = full_name.split("/", 1)
    base = f"/repos/{owner}/{name}"
    repo = gh.get(base)
    since30 = (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    since7 = now - timedelta(days=7)
    commits = gh.maybe(f"{base}/commits", {"since": since30, "per_page": 100}, default=[]) or []
    last = commits[0] if commits else {}
    last_commit = (
        {
            "sha": (last.get("sha") or "")[:7],
            "message": ((last.get("commit") or {}).get("message") or "").split("\n")[0][:160],
            "at": ((last.get("commit") or {}).get("committer") or {}).get("date") or "",
            "author": ((last.get("commit") or {}).get("author") or {}).get("name") or "",
        }
        if last
        else {}
    )
    c7 = sum(
        1
        for c in commits
        if (((c.get("commit") or {}).get("committer") or {}).get("date") or "") >= since7.strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    pulls = gh.maybe(f"{base}/pulls", {"state": "open", "per_page": 30}, default=[]) or []
    open_prs = []
    for p in pulls:
        head_sha = (p.get("head") or {}).get("sha") or ""
        ci = ""
        if head_sha:
            runs = gh.maybe(f"{base}/commits/{head_sha}/check-runs", {"per_page": 20}, default={}) or {}
            concl = [c.get("conclusion") for c in runs.get("check_runs") or [] if c.get("status") == "completed"]
            pending = any(c.get("status") != "completed" for c in runs.get("check_runs") or [])
            ci = (
                "red"
                if any(c not in ("success", "skipped", "neutral") for c in concl)
                else "running"
                if pending
                else "green"
                if concl
                else ""
            )
        open_prs.append(
            {
                "number": p.get("number"),
                "title": p.get("title") or "",
                "draft": bool(p.get("draft")),
                "updated_at": p.get("updated_at") or "",
                "url": p.get("html_url") or "",
                "ci": ci,
            }
        )
    closed = (
        gh.maybe(f"{base}/pulls", {"state": "closed", "per_page": 50, "sort": "updated", "direction": "desc"}, default=[]) or []
    )
    merged_30d = sum(1 for p in closed if (p.get("merged_at") or "") >= since30)
    issues_raw = gh.maybe(f"{base}/issues", {"state": "open", "per_page": 30}, default=[]) or []
    issues = [
        {
            "number": i.get("number"),
            "title": i.get("title") or "",
            "updated_at": i.get("updated_at") or "",
            "url": i.get("html_url") or "",
        }
        for i in issues_raw
        if "pull_request" not in i
    ]
    wf_raw = (gh.maybe(f"{base}/actions/workflows", {"per_page": 50}, default={}) or {}).get("workflows") or []
    workflows = []
    for w in wf_raw:
        if w.get("state") != "active":
            continue
        path = w.get("path") or ""
        text = gh.maybe(f"{base}/contents/{path}", raw=True, default="") or ""
        crons = crons_of(text)
        runs = (gh.maybe(f"{base}/actions/workflows/{w.get('id')}/runs", {"per_page": 1}, default={}) or {}).get(
            "workflow_runs"
        ) or []
        r0 = runs[0] if runs else {}
        workflows.append(
            {
                "name": w.get("name") or path,
                "path": path,
                "cron": ", ".join(crons),
                "last": {
                    "status": r0.get("status"),
                    "conclusion": r0.get("conclusion"),
                    "at": r0.get("updated_at") or r0.get("created_at") or "",
                    "url": r0.get("html_url") or "",
                }
                if r0
                else {},
            }
        )
    pages: dict[str, Any] = {}
    if repo.get("has_pages"):
        pg = gh.maybe(f"{base}/pages", default={}) or {}
        build = gh.maybe(f"{base}/pages/builds/latest", default={}) or {}
        pages = {
            "url": pg.get("html_url") or "",
            "status": build.get("status") or pg.get("status") or "",
            "at": build.get("updated_at") or "",
        }
    row: dict[str, Any] = {
        "full_name": full_name,
        "name": repo.get("name") or name,
        "description": repo.get("description") or "",
        "private": bool(repo.get("private")),
        "default_branch": repo.get("default_branch") or "main",
        "html_url": repo.get("html_url") or "",
        "pushed_at": repo.get("pushed_at"),
        "last_commit": last_commit,
        "commits_7d": c7,
        "commits_30d": len(commits),
        "commit_days": commit_days(commits, now),
        "open_prs": open_prs,
        "merged_30d": merged_30d,
        "open_issues": len(issues),
        "issues": issues[:10],
        "workflows": workflows,
        "ci": ci_of(workflows),
        "pages": pages,
        "error": "",
        "fetched_at": now.isoformat(),
    }
    total = merged_30d + len(open_prs)
    row["progress"] = int(round(100 * merged_30d / total)) if total else 100
    row["health"] = health_of(row, now)
    row["dims"] = dims_of(row)
    return row


def run(store: Any, gh: GitHub, now: datetime | None = None) -> dict[str, int]:
    now = now or datetime.now(UTC)
    cfg = load_settings(store)
    ok = failed = 0
    for full_name in cfg["list"]:
        try:
            row = read_repo(gh, full_name, now, cfg["days"])
            ok += 1
        except (LookupError, requests.RequestException, ValueError) as exc:
            failed += 1
            row = {
                "full_name": full_name,
                "name": full_name.split("/")[-1],
                "error": str(exc)[:300],
                "fetched_at": now.isoformat(),
            }
            log.warning("%s: %s", full_name, str(exc)[:200])
        store.table(db.REPOS).upsert(row, on_conflict="full_name").execute()
    db.log_event(
        store,
        "warn" if failed else "info",
        "repos",
        "repos_read",
        f"Repo: {ok} dibaca, {failed} gagal, {gh.calls} panggilan GitHub",
        detail={"ok": ok, "failed": failed, "calls": gh.calls},
    )
    return {"ok": ok, "failed": failed, "calls": gh.calls}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    store = db.client()
    token = os.environ.get("REPOS_TOKEN") or os.environ.get("LANDING_REPO_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        log.warning("no REPOS_TOKEN / LANDING_REPO_TOKEN / GITHUB_TOKEN: public repositories only, 60 calls an hour")
    out = run(store, GitHub(token))
    print(f"repos: {out}")
    return 0 if not out["failed"] else 1


if __name__ == "__main__":
    sys.exit(main())
