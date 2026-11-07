import { useMemo } from "react";
import { motion } from "framer-motion";
import { fadeUp } from "../design/motion";
import { TABLES } from "../lib/SupabaseClient";
import { useLang } from "../lib/i18n";
import { useTable } from "../lib/hooks";
import { timeAgo } from "../lib/format";
import { commitDays, gateways, latestRuns, medianMs, versionOf } from "../lib/techOverview";
import pkg from "../../package.json";
import { BentoStyles, CardTitle, GlowCard, Icon, StackCard, TECHS, cx, useAnimatedNumber } from "@/components/ui/interactive-tech-stack-bento-grid-with-hover-effects";

/* Technology overview (Wan, 7 Nov 2026: the bento grid, "Teknologi: ringkasan (Disyorkan)"). The pasted grid's look, fed with
   what Semasa really measures: the AI gateways as the probe last saw them (semasa_api_status, every 6 hours), the latest run of
   every workflow in the office and the commits a day (semasa_repos, every 6 hours), each repo's health score, and the stack
   this site and its workers are built on. No figure is invented: a card with no rows says so. */
export const PYTHON = "3.12";          // what the workflows run (techOverview.test.mjs checks it against .github/workflows)
const DEPS = { ...pkg.dependencies, ...pkg.devDependencies };
const pick = (id) => TECHS.find((x) => x.id === id)?.icon;
const DOT = { up: "bg-emerald-400", models: "bg-amber-400", stale: "bg-amber-400", key: "bg-rose-400", down: "bg-rose-400", nokey: "bg-slate-500", none: "bg-slate-500" };
const MARK = { ok: ["✓", "text-emerald-300"], bad: ["✗", "text-rose-300"], running: ["●", "text-cyan-300"], none: ["›", "text-slate-500"] };

export default function TechOverviewTab({ go }) {
  const { t } = useLang();
  const apiT = useTable(TABLES.apiStatus, { enabled: true, order: "role", ascending: true, limit: 20, realtime: false, everyMs: 300_000 });
  const reposT = useTable(TABLES.repos, { enabled: true, order: "full_name", ascending: true, limit: 100, realtime: false, everyMs: 300_000 });
  const gw = useMemo(() => gateways(apiT.rows), [apiT.rows]);
  const runs = useMemo(() => latestRuns(reposT.rows, 11), [reposT.rows]);
  const days = useMemo(() => commitDays(reposT.rows, 14), [reposT.rows]);
  const health = useMemo(() => [...reposT.rows].filter((r) => r.health != null).sort((a, b) => (a.health ?? 0) - (b.health ?? 0)).slice(0, 4), [reposT.rows]);
  const lastProbe = apiT.rows.reduce((m, r) => (r.checked_at > m ? r.checked_at : m), "");
  const lastRepos = reposT.rows.reduce((m, r) => (r.fetched_at > m ? r.fetched_at : m), "");

  const stack = [
    { id: "react", name: "React", version: versionOf(DEPS, "react"), rgb: "97, 218, 251", icon: pick("react"), desc: t("React · halaman Semasa ini (web/)", "React · this Semasa site (web/)") },
    { id: "vite", name: "Vite", version: versionOf(DEPS, "vite"), rgb: "189, 147, 249", icon: <Icon><path d="M17 4 8 18h7l-1 10 9-15h-7l1-9Z" /></Icon>, desc: t("Vite · membina halaman ke GitHub Pages", "Vite · builds the site for GitHub Pages") },
    { id: "ts", name: "TypeScript", version: versionOf(DEPS, "typescript"), rgb: "96, 165, 250", icon: pick("ts"), desc: t("TypeScript · komponen dalam components/ui", "TypeScript · the components in components/ui") },
    { id: "tailwind", name: "Tailwind", version: versionOf(DEPS, "tailwindcss"), rgb: "56, 189, 248", icon: pick("tailwind"), desc: t("Tailwind · gaya dan token tema", "Tailwind · styles and theme tokens") },
    { id: "postgres", name: "Supabase", version: versionOf(DEPS, "@supabase/supabase-js"), rgb: "62, 207, 142", icon: pick("postgres"), desc: t("Supabase (Postgres) · pangkalan data, log masuk dan realtime", "Supabase (Postgres) · database, sign-in and realtime") },
    { id: "python", name: "Python", version: PYTHON, rgb: "250, 204, 21", icon: <Icon><path d="M16 4c-5 0-5 2-5 4v3h6v1H8c-2 0-4 1.5-4 5s2 5 4 5h2v-3c0-2 1.5-3.5 3.5-3.5h5c2 0 3.5-1.5 3.5-3.5V8c0-2-2-4-6-4Z" /><path d="M16 28c5 0 5-2 5-4v-3h-6v-1h9c2 0 4-1.5 4-5s-2-5-4-5h-2v3c0 2-1.5 3.5-3.5 3.5h-5C11.5 16.5 10 18 10 20v4c0 2 2 4 6 4Z" /></Icon>, desc: t("Python · pekerja backend/semasa", "Python · the backend/semasa workers") },
    { id: "actions", name: "GitHub Actions", version: "", rgb: "148, 163, 184", icon: <Icon><circle cx="9" cy="9" r="3" /><circle cx="23" cy="23" r="3" /><circle cx="23" cy="9" r="3" /><path d="M9 12v5a6 6 0 0 0 6 6h5M12 9h8" /></Icon>, desc: t("GitHub Actions · setiap larian berjadual: scrape, metrik, penerbit, repo", "GitHub Actions · every scheduled run: scrape, metrics, publisher, repos") },
    { id: "motion", name: "Framer Motion", version: versionOf(DEPS, "framer-motion"), rgb: "244, 114, 182", icon: <Icon><path d="M8 4h16v8H16Zm0 8h8l8 8H8Zm0 8h8v8Z" /></Icon>, desc: t("Framer Motion + GSAP · animasi halaman", "Framer Motion + GSAP · page animation") },
  ];

  return (
    <main className="mx-auto max-w-page px-4 pb-20 pt-10 sm:px-6" data-tech-overview>
      <BentoStyles />
      <motion.div variants={fadeUp} initial="hidden" animate="show" className="mb-6">
        <h1 className="font-display text-3xl">{t("Ringkasan teknologi", "Technology overview")}</h1>
        <p className="mt-1 max-w-2xl text-sm text-muted">{t("Gerbang AI, larian workflow, kesihatan repo dan stack Semasa, daripada bacaan sebenar. Disemak setiap 6 jam.",
          "AI gateways, workflow runs, repo health and Semasa's stack, from real readings. Checked every 6 hours.")}</p>
      </motion.div>
      {(apiT.error || reposT.error) && <p className="mb-4 rounded-tile bg-danger/10 p-3 text-sm text-danger">{[apiT.error, reposT.error].filter(Boolean).join(" · ")}</p>}

      <section className="rounded-card bg-[#07080d] p-4 text-slate-200 sm:p-6">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:auto-rows-[210px] lg:grid-cols-4">
          <GatewayCard gw={gw} at={lastProbe} t={t} go={go} />
          <RunsCard runs={runs} at={lastRepos} t={t} />
          <HealthCard rows={health} t={t} go={go} />
          <CommitsCard days={days} t={t} />
          <StackCard techs={stack} title={t("Stack Semasa", "Semasa's stack")} hint={t("Tuding atau tab ke alat untuk lihat gunanya.", "Point or tab to a tool to see what it does.")} />
        </div>
      </section>
    </main>
  );
}

function Empty({ children }) {
  return <p className="flex flex-1 items-center justify-center text-center text-sm text-slate-500">{children}</p>;
}

function GatewayCard({ gw, at, t, go }) {
  const med = medianMs(gw);
  const shown = useAnimatedNumber(med ?? 0, 600);
  const up = gw.filter((g) => g.verdict === "up").length;
  const max = Math.max(1, ...gw.map((g) => g.ms || 0));
  return (
    <GlowCard accent="indigo" className="min-h-[420px] sm:col-span-2 lg:row-span-2">
      <CardTitle right={at ? <span className="text-xs text-slate-500">{t("diperiksa", "checked")} {timeAgo(at)}</span> : null}>{t("Gerbang AI", "AI gateways")}</CardTitle>
      {gw.length ? (
        <>
          <div className="mb-4 flex flex-wrap items-end gap-x-5 gap-y-2">
            <div className="flex items-end gap-1.5">
              <span className="text-5xl font-semibold leading-none tracking-tight text-white [font-variant-numeric:tabular-nums]" data-tech-median>{med == null ? "–" : Math.round(shown)}</span>
              <span className="mb-1 text-sm text-slate-500">{t("ms (median jawapan)", "ms (median answer)")}</span>
            </div>
            <span className="mb-1 text-xs text-slate-400">{t("{u} daripada {n} menjawab", "{u} of {n} answering", { u: up, n: gw.length })}</span>
          </div>
          <ul className="flex flex-1 flex-col gap-2 overflow-y-auto">
            {gw.map((g) => (
              <li key={g.name} className="rounded-lg px-2 py-1.5 transition-colors hover:bg-white/[0.05]" data-tech-gateway={g.verdict}>
                <div className="flex items-center gap-3 text-sm">
                  <span className={cx("h-2 w-2 shrink-0 rounded-full", DOT[g.verdict] || DOT.none)} />
                  <span className="flex-1 truncate text-slate-200">{g.name}<span className="ml-2 text-xs text-slate-500">{g.role}{g.model ? ` · ${g.model}` : ""}</span></span>
                  <span className="text-xs text-slate-300 [font-variant-numeric:tabular-nums]">{g.ms != null ? `${g.ms} ms` : "–"}</span>
                </div>
                {g.ms != null && <span className="mt-1 block h-1 rounded bg-indigo-400/60" style={{ width: `${Math.max(4, (g.ms / max) * 100)}%` }} />}
              </li>
            ))}
          </ul>
          {go && <button type="button" onClick={() => go("api")} className="mt-3 self-start text-xs text-indigo-300 underline">{t("Buka tab API", "Open the API tab")}</button>}
        </>
      ) : <Empty>{t("Tiada bacaan gerbang lagi: larian API di GitHub mengisinya.", "No gateway readings yet: the API workflow on GitHub fills them.")}</Empty>}
    </GlowCard>
  );
}

function RunsCard({ runs, at, t }) {
  return (
    <GlowCard accent="fuchsia" className="min-h-[340px] sm:col-span-2 lg:col-span-1 lg:row-span-2">
      <CardTitle right={at ? <span className="text-xs text-slate-500">{timeAgo(at)}</span> : null}>{t("Larian terkini", "Latest runs")}</CardTitle>
      {runs.length ? (
        <div className="flex flex-1 flex-col gap-1.5 overflow-hidden rounded-xl border border-white/5 bg-black/30 p-4 font-mono text-xs leading-relaxed" role="log" aria-label={t("Larian workflow", "Workflow runs")}>
          {runs.map((r, i) => {
            const [mark, cls] = MARK[r.verdict] || MARK.none;
            return (
              <div key={`${r.repo}-${r.name}-${i}`} className="tb-slide flex gap-2" data-tech-run={r.verdict}>
                <span className={cx("w-3 shrink-0 text-center", cls)}>{mark}</span>
                <span className="min-w-0 flex-1 truncate text-slate-300">{r.url ? <a href={r.url} target="_blank" rel="noreferrer" className="hover:underline">{r.repo} · {r.name}</a> : `${r.repo} · ${r.name}`}</span>
                <span className="shrink-0 text-slate-500">{timeAgo(r.at)}</span>
              </div>
            );
          })}
        </div>
      ) : <Empty>{t("Tiada larian direkodkan lagi.", "No runs recorded yet.")}</Empty>}
    </GlowCard>
  );
}

function HealthCard({ rows, t, go }) {
  const radius = 20, circumference = 2 * Math.PI * radius;
  return (
    <GlowCard accent="emerald" className="min-h-[200px]">
      <CardTitle right={go ? <button type="button" onClick={() => go("office")} className="text-xs text-emerald-300 underline">{t("Repo pejabat", "Office repos")}</button> : null}>{t("Kesihatan repo", "Repo health")}</CardTitle>
      {rows.length ? (
        <div className="flex flex-1 items-center justify-between gap-1">
          {rows.map((r) => {
            const score = Math.max(0, Math.min(100, r.health ?? 0));
            const colour = score >= 70 ? "#34d399" : score >= 40 ? "#fbbf24" : "#fb7185";
            return (
              <div key={r.full_name || r.name} className="group flex min-w-0 flex-col items-center gap-2" data-tech-health={score}>
                <div className="relative h-14 w-14">
                  <svg viewBox="0 0 50 50" className="h-full w-full -rotate-90" aria-hidden="true">
                    <circle cx="25" cy="25" r={radius} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="4" />
                    <circle cx="25" cy="25" r={radius} fill="none" stroke={colour} strokeWidth="4" strokeLinecap="round" strokeDasharray={circumference}
                      className="tb-ring" style={{ "--from": `${circumference}`, "--to": `${circumference * (1 - score / 100)}` }} />
                  </svg>
                  <span className="absolute inset-0 flex items-center justify-center text-sm font-semibold text-white">{score}</span>
                </div>
                <span className="max-w-[4.5rem] truncate text-[11px] text-slate-500" title={r.full_name}>{r.name}</span>
              </div>
            );
          })}
        </div>
      ) : <Empty>{t("Tiada repo dibaca lagi.", "No repos read yet.")}</Empty>}
    </GlowCard>
  );
}

function CommitsCard({ days, t }) {
  const total = days.reduce((s, d) => s + d.n, 0);
  const shown = useAnimatedNumber(total, 600);
  const max = Math.max(1, ...days.map((d) => d.n));
  return (
    <GlowCard accent="cyan" className="min-h-[200px]">
      <CardTitle right={<span className="text-xs text-slate-500">{t("{n} hari", "{n} days", { n: days.length })}</span>}>{t("Commit di pejabat", "Commits in the office")}</CardTitle>
      {days.length ? (
        <>
          <div className="text-4xl font-semibold leading-none tracking-tight text-white [font-variant-numeric:tabular-nums]" data-tech-commits>{Math.round(shown)}</div>
          <div className="mt-auto flex h-14 items-end gap-1">
            {days.map((d, i) => (
              <span key={d.date} title={`${d.date}: ${d.n}`}
                className={cx("flex-1 rounded-sm transition-all duration-700 ease-out", i === days.length - 1 ? "bg-cyan-300 shadow-[0_0_10px_rgba(103,232,249,0.8)]" : "bg-cyan-400/30")}
                style={{ height: `${Math.max((d.n / max) * 100, 8)}%` }} />
            ))}
          </div>
        </>
      ) : <Empty>{t("Tiada data commit lagi.", "No commit data yet.")}</Empty>}
    </GlowCard>
  );
}
