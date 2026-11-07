/* Technology overview (Wan, 7 Nov 2026: the bento grid, "Teknologi: ringkasan (Disyorkan)", real figures only). Pure, so
   web/techOverview.test.mjs runs it under Node: the page reads semasa_api_status and semasa_repos and hands the rows here.
   Nothing is sampled, averaged over a guess or animated from random numbers: a card with nothing to show says so. */
import { verdictOf } from "./api.js";

/** The latest run of every workflow in the office, newest first: {repo, name, verdict: ok | bad | running | none, at, url}. */
export function latestRuns(repos, limit = 11) {
  const out = [];
  for (const r of repos || []) {
    for (const w of r.workflows || []) {
      const last = w.last || {};
      if (!last.at) continue;
      const c = last.conclusion, s = last.status;
      out.push({ repo: r.name || r.full_name || "", name: w.name || w.path || "", at: last.at, url: last.url || "",
        verdict: s && s !== "completed" ? "running" : c == null ? "none" : ["success", "skipped", "neutral"].includes(c) ? "ok" : "bad" });
    }
  }
  return out.sort((a, b) => String(b.at).localeCompare(String(a.at))).slice(0, limit);
}

/** Commits a day across every repo, oldest first, the last `days` days that any repo reported. */
export function commitDays(repos, days = 14) {
  const by = new Map();
  for (const r of repos || []) for (const d of r.commit_days || []) if (d?.date) by.set(d.date, (by.get(d.date) || 0) + (Number(d.n) || 0));
  return [...by.entries()].sort(([a], [b]) => a.localeCompare(b)).slice(-days).map(([date, n]) => ({ date, n }));
}

/** Each AI gateway as the probe last saw it: {name, role, verdict, ms, model, at}; ms is the answer time, else the reach time. */
export function gateways(rows, now = Date.now()) {
  return (rows || []).map((r) => ({ name: r.name || r.slug || "", role: r.role || "", verdict: verdictOf(r, now),
    ms: r.chat_ms ?? r.latency_ms ?? null, model: r.model || "", at: r.checked_at || "" }));
}

/** The middle answer time of the gateways that answered (null when none did). */
export function medianMs(list) {
  const ms = (list || []).filter((g) => g.verdict === "up" && Number.isFinite(g.ms)).map((g) => g.ms).sort((a, b) => a - b);
  if (!ms.length) return null;
  const m = Math.floor(ms.length / 2);
  return ms.length % 2 ? ms[m] : Math.round((ms[m - 1] + ms[m]) / 2);
}

/** A version from package.json ("^18.3.1" -> "18.3"), major.minor only, or "" when it is not a dependency. */
export const versionOf = (deps, name) => {
  const v = String((deps || {})[name] || "").replace(/^[^\d]*/, "");
  return v ? v.split(".").slice(0, 2).join(".") : "";
};
