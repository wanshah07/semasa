import assert from "node:assert/strict";
import { officeSummary, parseRepoList, rankRepos, schedules, sparkline, staleDays, worstState } from "./src/lib/repos.js";

const rows = [
  { name: "semasa", full_name: "w/semasa", ci: "green", health: 90, pushed_at: "2026-10-09T05:00:00Z", open_prs: [{ number: 1 }], open_issues: 1, commits_7d: 5, merged_30d: 4,
    dims: { code: { state: "ok" }, prs: { state: "warn" }, ci: { state: "ok" }, issues: { state: "ok" }, schedules: { state: "ok" }, deploy: { state: "ok" } },
    commit_days: [{ date: "2026-10-08", n: 2 }, { date: "2026-10-09", n: 4 }],
    workflows: [{ name: "Publish", cron: "20 22 * * *", last: { status: "completed", conclusion: "failure", at: "x", url: "u" } }, { name: "CI", cron: "", last: { status: "completed", conclusion: "success" } }],
    fetched_at: "2026-10-09T06:00:00Z" },
  { name: "argus", full_name: "w/argus", ci: "red", health: 40, pushed_at: "2026-09-01T05:00:00Z", open_prs: [], open_issues: 3, commits_7d: 0, merged_30d: 0,
    dims: { code: { state: "warn" }, prs: { state: "ok" }, ci: { state: "bad" }, issues: { state: "ok" }, schedules: { state: "none" }, deploy: { state: "none" } },
    commit_days: [], workflows: [{ name: "creator-watch", cron: "0 1 * * *", last: { status: "in_progress" } }], fetched_at: "2026-10-09T06:01:00Z", error: "" },
  { name: "kpi", full_name: "w/kpi", ci: "none", health: 0, error: "404", open_prs: [], open_issues: 0, fetched_at: "2026-10-09T05:00:00Z" },
];

// worst first: red CI, then lowest health
assert.deepEqual(rankRepos(rows).map((r) => r.name), ["argus", "kpi", "semasa"]);

const s = officeSummary(rows);
assert.equal(s.repos, 3); assert.equal(s.red, 1); assert.equal(s.green, 1);
assert.equal(s.openPrs, 1); assert.equal(s.openIssues, 4); assert.equal(s.commits7d, 5); assert.equal(s.merged30d, 4);
assert.equal(s.unread, 1); assert.equal(s.lastRead, "2026-10-09T06:01:00Z");

assert.equal(staleDays(rows[1], Date.parse("2026-10-09T06:00:00Z")), 38);
assert.equal(staleDays(rows[2]), null);

assert.equal(worstState(rows[0]), "warn");
assert.equal(worstState(rows[1]), "bad");
assert.equal(worstState({}), "none");

const sp = sparkline(rows[0]);
assert.equal(sp.length, 2); assert.equal(sp[1].h, 1); assert.equal(sp[0].h, 0.5);
assert.deepEqual(sparkline({}), []);

const sch = schedules(rows);
assert.deepEqual(sch.map((x) => [x.name, x.verdict]), [["Publish", "bad"], ["creator-watch", "running"]]);   // CI has no cron: not a schedule

assert.deepEqual(parseRepoList("wanshah07/semasa\nhttps://github.com/wanshah07/argus/\n wanshah07/semasa , bad line, w/x.git"),
  ["wanshah07/semasa", "wanshah07/argus", "w/x"]);
assert.deepEqual(parseRepoList(""), []);

console.log("repos.test.mjs: 20 checks OK");
