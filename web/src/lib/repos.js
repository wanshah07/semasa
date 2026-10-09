/* Repo tracker arithmetic (Wan, 9 Oct 2026: "track the repos progress and status"). Rows are semasa_repos, written by
   backend/semasa/repos.py; the page only reads them. Pure functions, tested in repos.test.mjs. */

export const DIMS = ["code", "prs", "ci", "issues", "schedules", "deploy"];
export const DIM_WORDS = {
  code: ["Kod", "Code"], prs: ["Pull request", "Pull requests"], ci: ["CI", "CI"], issues: ["Isu", "Issues"],
  schedules: ["Jadual", "Schedules"], deploy: ["Deploy", "Deploy"],
};
export const STATE_ORDER = { bad: 0, warn: 1, none: 2, ok: 3 };

/** Repos worst first: red CI, then lowest health, then the longest since a push. */
export function rankRepos(rows) {
  return [...(rows || [])].sort((a, b) => {
    const ca = a.ci === "red" ? 0 : 1, cb = b.ci === "red" ? 0 : 1;
    if (ca !== cb) return ca - cb;
    if ((a.health ?? 0) !== (b.health ?? 0)) return (a.health ?? 0) - (b.health ?? 0);
    return String(a.pushed_at || "").localeCompare(String(b.pushed_at || ""));
  });
}

/** The office at a glance: how many repos, how many red, open PRs and issues in all, commits this week in all. */
export function officeSummary(rows) {
  const r = rows || [];
  return {
    repos: r.length,
    red: r.filter((x) => x.ci === "red").length,
    green: r.filter((x) => x.ci === "green").length,
    openPrs: r.reduce((n, x) => n + (x.open_prs || []).length, 0),
    openIssues: r.reduce((n, x) => n + (x.open_issues || 0), 0),
    commits7d: r.reduce((n, x) => n + (x.commits_7d || 0), 0),
    merged30d: r.reduce((n, x) => n + (x.merged_30d || 0), 0),
    unread: r.filter((x) => x.error).length,
    lastRead: r.reduce((m, x) => (x.fetched_at > m ? x.fetched_at : m), ""),
  };
}

/** Days since the last push, or null. */
export function staleDays(row, now = Date.now()) {
  if (!row?.pushed_at) return null;
  return Math.max(0, Math.floor((now - new Date(row.pushed_at).getTime()) / 86_400_000));
}

/** The worst dimension state of a row, for the card's edge colour. */
export function worstState(row) {
  const states = DIMS.map((d) => row?.dims?.[d]?.state || "none");
  return states.sort((a, b) => (STATE_ORDER[a] ?? 2) - (STATE_ORDER[b] ?? 2))[0] || "none";
}

/** The sparkline's bars, scaled 0..1 against the busiest day. */
export function sparkline(row) {
  const days = row?.commit_days || [];
  const max = Math.max(1, ...days.map((d) => d.n || 0));
  return days.map((d) => ({ date: d.date, n: d.n || 0, h: (d.n || 0) / max }));
}

/** Every scheduled workflow across the office, soonest-failing first: name, repo, cron, last verdict. */
export function schedules(rows) {
  const out = [];
  for (const r of rows || []) {
    for (const w of r.workflows || []) {
      if (!w.cron) continue;
      const c = w.last?.conclusion, s = w.last?.status;
      out.push({ repo: r.name, full_name: r.full_name, name: w.name, cron: w.cron, at: w.last?.at || "", url: w.last?.url || "",
        verdict: s && s !== "completed" ? "running" : c == null ? "none" : ["success", "skipped", "neutral"].includes(c) ? "ok" : "bad" });
    }
  }
  return out.sort((a, b) => (STATE_ORDER[a.verdict === "running" ? "warn" : a.verdict === "ok" ? "ok" : a.verdict] ?? 2)
    - (STATE_ORDER[b.verdict === "running" ? "warn" : b.verdict === "ok" ? "ok" : b.verdict] ?? 2));
}

/** Parse the Settings text area: one owner/name a line, trimmed, deduplicated, invalid lines dropped. */
export function parseRepoList(text) {
  const seen = new Set();
  const out = [];
  for (const line of String(text || "").split(/[\n,]/)) {
    const s = line.trim().replace(/^https?:\/\/github\.com\//, "").replace(/\.git$/, "").replace(/\/$/, "");
    if (!/^[\w.-]+\/[\w.-]+$/.test(s) || seen.has(s.toLowerCase())) continue;
    seen.add(s.toLowerCase());
    out.push(s);
  }
  return out;
}
