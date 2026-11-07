/* Technology overview (lib/techOverview.js): real rows in, real figures out. `npm test`. */
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { commitDays, gateways, latestRuns, medianMs, versionOf } from "./src/lib/techOverview.js";

let n = 0;
const t = (name, fn) => { try { fn(); n++; } catch (e) { console.error("FAIL:", name); throw e; } };
const repos = [
  { name: "semasa", workflows: [
    { name: "Web", last: { status: "completed", conclusion: "success", at: "2026-11-07T06:00:00Z", url: "u1" } },
    { name: "Worker", last: { status: "in_progress", at: "2026-11-07T07:00:00Z" } },
    { name: "Never ran", last: {} },
  ], commit_days: [{ date: "2026-11-06", n: 3 }, { date: "2026-11-07", n: 5 }] },
  { name: "kpi", workflows: [{ name: "Deploy", last: { status: "completed", conclusion: "failure", at: "2026-11-06T01:00:00Z" } }],
    commit_days: [{ date: "2026-11-07", n: 2 }, { date: "2026-11-05", n: 1 }] },
];

t("the latest runs, newest first, with a verdict from GitHub's own words; a workflow that never ran is left out", () => {
  assert.deepEqual(latestRuns(repos).map((r) => [r.repo, r.name, r.verdict]),
    [["semasa", "Worker", "running"], ["semasa", "Web", "ok"], ["kpi", "Deploy", "bad"]]);
  assert.equal(latestRuns(repos, 1).length, 1);
});
t("commits a day are summed across repos", () => {
  assert.deepEqual(commitDays(repos), [{ date: "2026-11-05", n: 1 }, { date: "2026-11-06", n: 3 }, { date: "2026-11-07", n: 7 }]);
  assert.deepEqual(commitDays(repos, 2).map((d) => d.date), ["2026-11-06", "2026-11-07"]);
});
t("gateways read the probe's row; the median counts only the ones that answered", () => {
  const now = Date.parse("2026-11-07T08:00:00Z");
  const g = gateways([
    { name: "A", key_set: true, reachable: true, chat_ok: true, chat_ms: 900, checked_at: "2026-11-07T06:00:00Z" },
    { name: "B", key_set: true, reachable: true, chat_ok: true, latency_ms: 300, checked_at: "2026-11-07T06:00:00Z" },
    { name: "C", key_set: true, reachable: false, latency_ms: 50, checked_at: "2026-11-07T06:00:00Z" },
    { name: "D", key_set: false },
  ], now);
  assert.deepEqual(g.map((x) => [x.name, x.verdict, x.ms]), [["A", "up", 900], ["B", "up", 300], ["C", "down", 50], ["D", "nokey", null]]);
  assert.equal(medianMs(g), 600);
  assert.equal(medianMs([]), null);
});
t("versions come from package.json, and the Python the stack card names is the one the workflows run", () => {
  const pkg = JSON.parse(readFileSync(new URL("./package.json", import.meta.url), "utf8"));
  const deps = { ...pkg.dependencies, ...pkg.devDependencies };
  assert.match(versionOf(deps, "react"), /^\d+\.\d+$/);
  assert.equal(versionOf(deps, "not-a-thing"), "");
  const dir = new URL("../.github/workflows/", import.meta.url);
  const pys = readdirSync(dir).flatMap((f) => [...readFileSync(new URL(f, dir), "utf8").matchAll(/python-version:\s*"?([\d.]+)/g)].map((m) => m[1]));
  const count = pys.reduce((m, v) => ({ ...m, [v]: (m[v] || 0) + 1 }), {});
  const top = Object.entries(count).sort((a, b) => b[1] - a[1])[0][0];
  const page = readFileSync(new URL("./src/pages/TechOverviewTab.jsx", import.meta.url), "utf8");
  assert.ok(page.includes(`PYTHON = "${top}"`), `the stack card must name Python ${top}, the version most workflows run`);
});

console.log(`techOverview: ${n} checks passed`);
