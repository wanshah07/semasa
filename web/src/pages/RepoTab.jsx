import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { AlertTriangle, CalendarClock, CheckCircle2, CircleDashed, ExternalLink, GitBranch, GitCommitHorizontal, GitPullRequest, Globe, Lock, MessageSquareWarning, PlayCircle, RefreshCw, Save, XCircle } from "lucide-react";
import { fadeUp } from "../design/motion";
import { TABLES } from "../lib/SupabaseClient";
import { useLang } from "../lib/i18n";
import { useSettings, useTable } from "../lib/hooks";
import { stampMYT, timeAgo } from "../lib/format";
import { DIMS, DIM_WORDS, officeSummary, parseRepoList, rankRepos, schedules, sparkline, staleDays, worstState } from "../lib/repos";
import Card from "../components/ui/Card";
import Button from "../components/ui/Button";
import { TextArea } from "../components/ui/Field";

/* Repo: the office repositories in six dimensions (Wan, 9 Oct 2026: "add all repo office environment in 6D in the system so i
   can track the repos progress and status"). Rows come from semasa_repos (supabase/035_repos_api.sql), written every 6 hours by
   backend/semasa/repos.py from GitHub; the page reads them and edits only the list of repositories (settings.repos). */

const STATE_CLS = { ok: "bg-ok/15 text-ok", warn: "bg-warn/15 text-warn", bad: "bg-danger/15 text-danger", none: "bg-surface-2 text-muted" };
const EDGE_CLS = { ok: "border-l-ok", warn: "border-l-warn", bad: "border-l-danger", none: "border-l-line" };
const CI_WORDS = { green: ["lulus", "passing"], red: ["gagal", "failing"], running: ["berjalan", "running"], none: ["tiada", "none"] };
const DIM_ICON = { code: GitCommitHorizontal, prs: GitPullRequest, ci: PlayCircle, issues: MessageSquareWarning, schedules: CalendarClock, deploy: Globe };

export default function RepoTab({ settings, save, onToast }) {
  const { t, lang } = useLang();
  const L = lang === "en" ? 1 : 0;
  const reposT = useTable(TABLES.repos, { enabled: true, order: "full_name", ascending: true, limit: 100, realtime: false, everyMs: 300_000 });
  const [open, setOpen] = useState(null);
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const rows = useMemo(() => rankRepos(reposT.rows), [reposT.rows]);
  const sum = useMemo(() => officeSummary(rows), [rows]);
  const sched = useMemo(() => schedules(rows), [rows]);
  const list = settings?.repos?.list || [];
  const missing = /semasa_repos/.test(reposT.error || "");
  const notYet = list.filter((n) => !rows.some((r) => r.full_name === n));

  const tiles = [
    { label: t("Repositori", "Repositories"), value: sum.repos, hint: sum.unread ? t("{n} tidak dapat dibaca", "{n} could not be read", { n: sum.unread }) : t("semua dibaca", "all read"), icon: GitBranch },
    { label: t("CI merah", "CI red"), value: sum.red, hint: t("{n} hijau", "{n} green", { n: sum.green }), icon: sum.red ? XCircle : CheckCircle2, cls: sum.red ? "text-danger" : "text-ok" },
    { label: t("PR terbuka", "Open PRs"), value: sum.openPrs, hint: t("{n} digabung 30 hari", "{n} merged in 30 days", { n: sum.merged30d }), icon: GitPullRequest },
    { label: t("Commit 7 hari", "Commits 7 days"), value: sum.commits7d, hint: t("{n} isu terbuka", "{n} open issues", { n: sum.openIssues }), icon: GitCommitHorizontal },
  ];

  const startEdit = () => { setText(list.join("\n")); setEditing(true); };
  const saveList = async () => {
    const next = parseRepoList(text);
    if (!next.length) { onToast?.(t("Senarai kosong: tulis sekurang-kurangnya satu owner/nama.", "Empty list: write at least one owner/name."), "warn"); return; }
    setBusy(true);
    try {
      await save("repos", { ...(settings?.repos || {}), list: next });
      setEditing(false);
      onToast?.(t("Senarai disimpan: larian Repos seterusnya membacanya.", "List saved: the next Repos run reads it."), "ok");
    } catch (e) { onToast?.(e.message || String(e), "error"); } finally { setBusy(false); }
  };

  return (
    <main className="mx-auto max-w-page px-4 pb-20 pt-10 sm:px-6">
      <motion.div {...fadeUp} className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-3xl">{t("Repo", "Repos")}</h1>
          <p className="mt-1 max-w-2xl text-sm text-muted">{t("Setiap repositori pejabat dalam enam dimensi: kod, pull request, CI, isu, jadual dan deploy. Dibaca dari GitHub setiap 6 jam.",
            "Every office repository in six dimensions: code, pull requests, CI, issues, schedules and deploy. Read from GitHub every 6 hours.")}</p>
        </div>
        <div className="flex items-center gap-2 text-xs text-muted">
          {sum.lastRead && <span><RefreshCw size={12} className="mr-1 inline" />{t("dibaca", "read")} {timeAgo(sum.lastRead)}</span>}
          <Button variant="ghost" size="sm" onClick={startEdit}>{t("Senarai repo", "Repo list")}</Button>
        </div>
      </motion.div>

      {missing && <p className="mb-4 rounded-tile bg-warn/10 p-3 text-sm text-warn">{t("Jadual belum ada: jalankan supabase/035_repos_api.sql sekali, kemudian larian Repos di GitHub.", "The table is not there yet: run supabase/035_repos_api.sql once, then the Repos workflow on GitHub.")}</p>}
      {reposT.error && !missing && <p className="mb-4 rounded-tile bg-danger/10 p-3 text-sm text-danger">{reposT.error}</p>}
      {!reposT.loading && !reposT.error && !rows.length && (
        <p className="mb-4 rounded-tile bg-surface-2 p-3 text-sm text-muted">{t("Tiada baris lagi: larian Repos (GitHub → Actions → Repos → Run workflow) membaca repositori dan mengisi jadual ini. Ia perlukan rahsia REPOS_TOKEN untuk repo peribadi.",
          "No rows yet: the Repos workflow (GitHub → Actions → Repos → Run workflow) reads the repositories and fills this table. It needs the REPOS_TOKEN secret for private repos.")}</p>
      )}

      {editing && (
        <Card className="mb-6 p-4">
          <p className="text-sm font-medium">{t("Repositori yang dijejak", "Tracked repositories")}</p>
          <p className="mb-2 text-xs text-muted">{t("Satu owner/nama setiap baris. Repo peribadi perlukan token yang boleh membacanya (REPOS_TOKEN).", "One owner/name a line. A private repo needs a token that can read it (REPOS_TOKEN).")}</p>
          <TextArea rows={7} value={text} onChange={(e) => setText(e.target.value)} className="font-mono text-xs" />
          <div className="mt-2 flex gap-2">
            <Button size="sm" onClick={saveList} disabled={busy}><Save size={14} /> {t("Simpan", "Save")}</Button>
            <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>{t("Batal", "Cancel")}</Button>
          </div>
        </Card>
      )}

      <div className="mb-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {tiles.map((s) => (
          <Card key={s.label} className="p-4">
            <div className="flex items-center justify-between"><span className="text-[11px] uppercase tracking-widest text-muted">{s.label}</span><s.icon size={16} className={s.cls || "text-muted"} /></div>
            <p className="mt-2 font-display text-2xl tabular-nums">{s.value}</p>
            <p className="mt-0.5 text-xs text-muted">{s.hint}</p>
          </Card>
        ))}
      </div>

      <div className="grid gap-4">
        {rows.map((r) => {
          const edge = EDGE_CLS[worstState(r)] || EDGE_CLS.none;
          const stale = staleDays(r);
          const isOpen = open === r.full_name;
          return (
            <Card key={r.full_name} className={`border-l-4 p-4 ${edge}`}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <a href={r.html_url || `https://github.com/${r.full_name}`} target="_blank" rel="noreferrer" className="font-display text-lg hover:underline">{r.name}</a>
                    {r.private ? <Lock size={13} className="text-muted" /> : <Globe size={13} className="text-muted" />}
                    <span className={`rounded-pill px-2 py-0.5 text-[11px] ${STATE_CLS[r.ci === "green" ? "ok" : r.ci === "red" ? "bad" : r.ci === "running" ? "warn" : "none"]}`}>CI {CI_WORDS[r.ci || "none"]?.[L]}</span>
                    {r.error && <span className="rounded-pill bg-danger/15 px-2 py-0.5 text-[11px] text-danger"><AlertTriangle size={11} className="mr-1 inline" />{r.error.slice(0, 60)}</span>}
                  </div>
                  <p className="mt-0.5 truncate text-xs text-muted">{r.full_name}{r.description ? ` · ${r.description}` : ""}</p>
                  {r.last_commit?.message && <p className="mt-1 truncate text-sm"><GitCommitHorizontal size={13} className="mr-1 inline text-muted" />{r.last_commit.message}
                    <span className="text-xs text-muted"> · {r.last_commit.author} · {r.last_commit.at ? timeAgo(r.last_commit.at) : ""}</span></p>}
                </div>
                <div className="flex items-center gap-4">
                  <Spark row={r} />
                  <Ring value={r.health ?? 0} label={t("sihat", "health")} />
                  <Ring value={r.progress ?? 0} label={t("maju", "progress")} tone="accent" />
                </div>
              </div>
              <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6">
                {DIMS.map((d) => {
                  const dim = r.dims?.[d] || { state: "none", label: "—", detail: "" };
                  const Icon = DIM_ICON[d];
                  return (
                    <button key={d} type="button" onClick={() => setOpen(isOpen ? null : r.full_name)} title={dim.detail || ""}
                      className={`rounded-tile p-2 text-left ${STATE_CLS[dim.state] || STATE_CLS.none}`}>
                      <p className="flex items-center gap-1 text-[10px] uppercase tracking-widest opacity-80"><Icon size={11} /> {DIM_WORDS[d][L]}</p>
                      <p className="mt-0.5 truncate text-sm font-medium">{dim.label}</p>
                    </button>
                  );
                })}
              </div>
              {stale != null && stale > 14 && <p className="mt-2 text-xs text-warn">{t("Tiada push selama {n} hari.", "No push for {n} days.", { n: stale })}</p>}
              {isOpen && <Details r={r} t={t} />}
            </Card>
          );
        })}
        {notYet.map((n) => (
          <Card key={n} className="border-l-4 border-l-line p-4 text-sm text-muted"><CircleDashed size={14} className="mr-1 inline" />{n} · {t("belum dibaca: tunggu larian Repos seterusnya", "not read yet: wait for the next Repos run")}</Card>
        ))}
      </div>

      {sched.length > 0 && (
        <Card className="mt-6 p-4">
          <h2 className="mb-2 flex items-center gap-2 text-sm font-medium"><CalendarClock size={14} className="text-accent" /> {t("Semua jadual (cron) di pejabat", "Every schedule (cron) in the office")}</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-[11px] uppercase tracking-widest text-muted"><th className="py-1 pr-3">Repo</th><th className="py-1 pr-3">{t("Aliran kerja", "Workflow")}</th><th className="py-1 pr-3">Cron (UTC)</th><th className="py-1 pr-3">{t("Larian terakhir", "Last run")}</th><th className="py-1"></th></tr></thead>
              <tbody>
                {sched.map((s) => (
                  <tr key={`${s.full_name}/${s.name}`} className="border-t border-line/60">
                    <td className="py-1.5 pr-3">{s.repo}</td>
                    <td className="py-1.5 pr-3">{s.name}</td>
                    <td className="py-1.5 pr-3 font-mono text-xs">{s.cron}</td>
                    <td className="py-1.5 pr-3"><span className={`rounded-pill px-2 py-0.5 text-[11px] ${STATE_CLS[s.verdict === "ok" ? "ok" : s.verdict === "bad" ? "bad" : s.verdict === "running" ? "warn" : "none"]}`}>{s.verdict}</span> <span className="text-xs text-muted">{s.at ? stampMYT(s.at) : ""}</span></td>
                    <td className="py-1.5 text-right">{s.url && <a href={s.url} target="_blank" rel="noreferrer" className="text-muted hover:text-ink"><ExternalLink size={13} /></a>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </main>
  );
}

function Spark({ row }) {
  const bars = sparkline(row);
  if (!bars.length) return null;
  return (
    <div className="hidden h-8 items-end gap-[2px] sm:flex" title="commits, last 14 days">
      {bars.map((b) => <span key={b.date} className="w-[5px] rounded-sm bg-accent/70" style={{ height: `${Math.max(2, b.h * 32)}px`, opacity: b.n ? 1 : 0.25 }} />)}
    </div>
  );
}

function Ring({ value, label, tone = "ok" }) {
  const r = 16, c = 2 * Math.PI * r, v = Math.max(0, Math.min(100, value));
  const colour = tone === "accent" ? "rgb(var(--c-accent))" : v >= 70 ? "rgb(var(--c-ok))" : v >= 40 ? "rgb(var(--c-warn))" : "rgb(var(--c-danger))";
  return (
    <div className="flex flex-col items-center">
      <svg width="42" height="42" viewBox="0 0 42 42" aria-label={`${label} ${v}`}>
        <circle cx="21" cy="21" r={r} fill="none" stroke="rgb(var(--c-line))" strokeWidth="4" />
        <circle cx="21" cy="21" r={r} fill="none" stroke={colour} strokeWidth="4" strokeLinecap="round" strokeDasharray={`${(v / 100) * c} ${c}`} transform="rotate(-90 21 21)" />
        <text x="21" y="24" textAnchor="middle" fontSize="10" fill="currentColor">{v}</text>
      </svg>
      <span className="text-[10px] uppercase tracking-widest text-muted">{label}</span>
    </div>
  );
}

function Details({ r, t }) {
  return (
    <div className="mt-3 grid gap-3 border-t border-line/60 pt-3 text-sm md:grid-cols-3">
      <div>
        <p className="mb-1 text-[11px] uppercase tracking-widest text-muted">{t("Pull request terbuka", "Open pull requests")}</p>
        {(r.open_prs || []).length ? (r.open_prs || []).map((p) => (
          <p key={p.number} className="truncate"><a href={p.url} target="_blank" rel="noreferrer" className="hover:underline">#{p.number} {p.title}</a>
            <span className={`ml-1 rounded-pill px-1.5 text-[10px] ${STATE_CLS[p.ci === "green" ? "ok" : p.ci === "red" ? "bad" : p.ci === "running" ? "warn" : "none"]}`}>{p.draft ? "draft · " : ""}{p.ci || "—"}</span></p>
        )) : <p className="text-muted">{t("tiada", "none")}</p>}
      </div>
      <div>
        <p className="mb-1 text-[11px] uppercase tracking-widest text-muted">{t("Aliran kerja", "Workflows")}</p>
        {(r.workflows || []).length ? (r.workflows || []).map((w) => (
          <p key={w.path} className="truncate">{w.last?.url ? <a href={w.last.url} target="_blank" rel="noreferrer" className="hover:underline">{w.name}</a> : w.name}
            <span className="ml-1 text-xs text-muted">{w.cron ? `⏱ ${w.cron} · ` : ""}{w.last?.conclusion || w.last?.status || "—"}</span></p>
        )) : <p className="text-muted">{t("tiada", "none")}</p>}
      </div>
      <div>
        <p className="mb-1 text-[11px] uppercase tracking-widest text-muted">{t("Isu terbuka", "Open issues")}</p>
        {(r.issues || []).length ? (r.issues || []).map((i) => (
          <p key={i.number} className="truncate"><a href={i.url} target="_blank" rel="noreferrer" className="hover:underline">#{i.number} {i.title}</a></p>
        )) : <p className="text-muted">{t("tiada", "none")}</p>}
        {r.pages?.url && <p className="mt-2 text-xs text-muted">Pages: <a href={r.pages.url} target="_blank" rel="noreferrer" className="hover:underline">{r.pages.url}</a> · {r.pages.status}</p>}
      </div>
    </div>
  );
}
