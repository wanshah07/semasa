import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Activity, AlertTriangle, CheckCircle2, Cpu, KeyRound, RefreshCw, Timer, Wallet, XCircle } from "lucide-react";
import { fadeUp } from "../design/motion";
import { TABLES } from "../lib/SupabaseClient";
import { useLang } from "../lib/i18n";
import { useTable } from "../lib/hooks";
import { stampMYT, timeAgo } from "../lib/format";
import { fmtTokens, orderedModels, usageByArea, usageByDay, usageByGateway, verdictOf } from "../lib/api";
import Card from "../components/ui/Card";
import { Segmented } from "../components/ui/Field";

/* API: the AI gateways (rootsys = Afiq's, Mireld), their keys, their models and the tokens we spend (Wan, 9 Oct 2026: "track
   status of token from mireld and afiq API including their models"). Status rows come from semasa_api_status (the probe, every
   6 hours); usage rows from semasa_api_usage (every AI call every worker makes). The page reads; it never holds a key. */

const VERDICT = {
  up: { cls: "bg-ok/15 text-ok", icon: CheckCircle2, bm: "Hidup", en: "Up" },
  models: { cls: "bg-warn/15 text-warn", icon: AlertTriangle, bm: "Model tidak menjawab", en: "Model did not answer" },
  key: { cls: "bg-danger/15 text-danger", icon: KeyRound, bm: "Kunci ditolak", en: "Key refused" },
  down: { cls: "bg-danger/15 text-danger", icon: XCircle, bm: "Tidak sampai", en: "Unreachable" },
  nokey: { cls: "bg-surface-2 text-muted", icon: KeyRound, bm: "Tiada kunci", en: "No key" },
  stale: { cls: "bg-warn/15 text-warn", icon: Timer, bm: "Belum disemak 13 jam", en: "Not checked in 13 h" },
  none: { cls: "bg-surface-2 text-muted", icon: Cpu, bm: "—", en: "—" },
};
const COLOURS = ["rgb(var(--c-accent))", "rgb(var(--c-ok))", "rgb(var(--c-warn))", "rgb(var(--c-danger))", "rgb(var(--c-muted))"];

export default function ApiTab() {
  const { t, lang } = useLang();
  const L = lang === "en" ? "en" : "bm";
  const statusT = useTable(TABLES.apiStatus, { enabled: true, order: "role", ascending: true, limit: 20, realtime: false, everyMs: 300_000 });
  const usageT = useTable(TABLES.apiUsage, { enabled: true, order: "created_at", limit: 5000, realtime: false, everyMs: 300_000 });
  const [days, setDays] = useState(30);
  const [showAll, setShowAll] = useState({});
  const byGw = useMemo(() => usageByGateway(usageT.rows, days), [usageT.rows, days]);
  const byDay = useMemo(() => usageByDay(usageT.rows, days), [usageT.rows, days]);
  const byArea = useMemo(() => usageByArea(usageT.rows, days), [usageT.rows, days]);
  const missing = /semasa_api_(status|usage)/.test(statusT.error || usageT.error || "");
  const total = Object.values(byGw).reduce((n, g) => n + g.tokens, 0);
  const calls = Object.values(byGw).reduce((n, g) => n + g.calls, 0);
  const failed = Object.values(byGw).reduce((n, g) => n + g.failed, 0);
  const lastCheck = statusT.rows.reduce((m, r) => (r.checked_at > m ? r.checked_at : m), "");

  return (
    <main className="mx-auto max-w-page px-4 pb-20 pt-10 sm:px-6">
      <motion.div {...fadeUp} className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-3xl">API</h1>
          <p className="mt-1 max-w-2xl text-sm text-muted">{t("Gerbang AI (rootsys milik Afiq, Mireld): hidup atau tidak, kunci diterima atau tidak, model yang disenaraikan, dan token yang kita belanja. Disemak setiap 6 jam; penggunaan ditulis oleh setiap larian.",
            "The AI gateways (Afiq's rootsys, Mireld): up or not, key accepted or not, the models each lists, and the tokens we spend. Checked every 6 hours; usage is written by every run.")}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {lastCheck && <span className="text-xs text-muted"><RefreshCw size={12} className="mr-1 inline" />{t("disemak", "checked")} {timeAgo(lastCheck)}</span>}
          <Segmented value={String(days)} onChange={(v) => setDays(Number(v))} options={[["7", t("7 hari", "7 days")], ["30", t("30 hari", "30 days")], ["90", t("90 hari", "90 days")]]} />
        </div>
      </motion.div>

      {missing && <p className="mb-4 rounded-tile bg-warn/10 p-3 text-sm text-warn">{t("Jadual belum ada: jalankan supabase/035_repos_api.sql sekali, kemudian larian API status di GitHub.", "The tables are not there yet: run supabase/035_repos_api.sql once, then the API status workflow on GitHub.")}</p>}
      {(statusT.error || usageT.error) && !missing && <p className="mb-4 rounded-tile bg-danger/10 p-3 text-sm text-danger">{statusT.error || usageT.error}</p>}
      {!statusT.loading && !statusT.error && !statusT.rows.length && (
        <p className="mb-4 rounded-tile bg-surface-2 p-3 text-sm text-muted">{t("Belum disemak: larian API status (GitHub → Actions → API status → Run workflow) menanya setiap gerbang dan mengisi kad di bawah.",
          "Not checked yet: the API status workflow (GitHub → Actions → API status → Run workflow) asks every gateway and fills the cards below.")}</p>
      )}

      <div className="mb-6 grid gap-4 lg:grid-cols-2">
        {statusT.rows.map((r) => {
          const v = verdictOf(r);
          const V = VERDICT[v] || VERDICT.none;
          const u = byGw[r.slug] || { calls: 0, failed: 0, tokens: 0, prompt: 0, completion: 0, ms: 0, models: {} };
          const models = orderedModels(r);
          const all = showAll[r.slug];
          const shown = all ? models : models.slice(0, 12);
          return (
            <Card key={r.slug} className="p-4">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <p className="font-display text-lg">{r.name || r.slug} <span className="text-xs text-muted">· {r.role}</span></p>
                  <p className="truncate text-xs text-muted">{r.base_url}</p>
                </div>
                <span className={`inline-flex items-center gap-1 rounded-pill px-2 py-0.5 text-[11px] ${V.cls}`}><V.icon size={12} /> {V[L]}</span>
              </div>
              <div className="mt-3 grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
                <Stat label={t("Kunci", "Key")} value={r.key_set ? `…${r.key_last4}` : "—"} hint={r.key_ok === false ? t("ditolak", "refused") : r.key_ok ? t("diterima", "accepted") : t("belum ditanya", "not asked")} />
                <Stat label={t("Model", "Model")} value={r.model || "—"} hint={r.model_listed === true ? t("dalam senarai", "listed") : r.model_listed === false ? t("TIADA dalam senarai", "NOT listed") : ""} warn={r.model_listed === false} />
                <Stat label={t("Masa jawab", "Latency")} value={r.chat_ms != null ? `${r.chat_ms} ms` : r.latency_ms != null ? `${r.latency_ms} ms` : "—"} hint={r.http ? `HTTP ${r.http}` : ""} />
                <Stat label={t("Token {d} hari", "Tokens {d} days", { d: days })} value={fmtTokens(u.tokens)} hint={t("{n} panggilan, {f} gagal", "{n} calls, {f} failed", { n: u.calls, f: u.failed })} warn={u.failed > 0} />
              </div>
              {r.balance && Object.keys(r.balance).length > 1 && (
                <p className="mt-2 text-xs text-muted"><Wallet size={12} className="mr-1 inline" />{Object.entries(r.balance).filter(([k]) => k !== "path").map(([k, val]) => `${k}: ${val}`).join(" · ")} <span className="opacity-70">({r.balance.path})</span></p>
              )}
              {r.error && <p className="mt-2 rounded-tile bg-danger/10 p-2 text-xs text-danger">{r.error}</p>}
              <div className="mt-3">
                <p className="mb-1 text-[11px] uppercase tracking-widest text-muted">{t("Model disenaraikan", "Models listed")} · {models.length}</p>
                {models.length ? (
                  <div className="flex flex-wrap gap-1">
                    {shown.map((m) => <span key={m} className={`rounded-pill px-2 py-0.5 text-[11px] ${m === r.model ? "bg-accent/15 text-accent" : u.models[m] ? "bg-ok/10 text-ok" : "bg-surface-2 text-muted"}`} title={u.models[m] ? `${fmtTokens(u.models[m])} tokens` : ""}>{m}</span>)}
                    {models.length > 12 && <button type="button" className="rounded-pill px-2 py-0.5 text-[11px] text-accent hover:underline" onClick={() => setShowAll((s) => ({ ...s, [r.slug]: !all }))}>{all ? t("kurang", "fewer") : t("+{n} lagi", "+{n} more", { n: models.length - 12 })}</button>}
                  </div>
                ) : <p className="text-xs text-muted">{t("Gerbang tidak menyenaraikan model (atau kunci ditolak).", "The gateway lists no models (or the key was refused).")}</p>}
              </div>
              <p className="mt-2 text-[11px] text-muted">{r.checked_at ? `${t("disemak", "checked")} ${stampMYT(r.checked_at)}` : ""}</p>
            </Card>
          );
        })}
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="p-4 lg:col-span-2">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="flex items-center gap-2 text-sm font-medium"><Activity size={14} className="text-accent" /> {t("Token sehari", "Tokens a day")}</h2>
            <span className="text-[11px] text-muted">{fmtTokens(total)} {t("token", "tokens")} · {calls} {t("panggilan", "calls")}{failed ? ` · ${failed} ${t("gagal", "failed")}` : ""}</span>
          </div>
          <div className="h-52">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={byDay.series} margin={{ top: 6, right: 8, left: -14, bottom: 0 }}>
                <CartesianGrid vertical={false} stroke="rgb(var(--c-line))" />
                <XAxis dataKey="date" tickFormatter={(d) => d.slice(8, 10)} tick={{ fontSize: 10 }} stroke="rgb(var(--c-muted))" interval={days > 30 ? 9 : days > 7 ? 4 : 0} />
                <YAxis tick={{ fontSize: 10 }} stroke="rgb(var(--c-muted))" tickFormatter={fmtTokens} />
                <Tooltip contentStyle={{ fontSize: 12, borderRadius: 12 }} formatter={(v, k) => [fmtTokens(v), k]} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                {byDay.gateways.map((g, i) => <Bar key={g} dataKey={g} stackId="t" fill={COLOURS[i % COLOURS.length]} radius={i === byDay.gateways.length - 1 ? [4, 4, 0, 0] : 0} />)}
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card className="p-4">
          <h2 className="mb-2 text-sm font-medium">{t("Siapa belanja", "Who spends")}</h2>
          {byArea.length ? byArea.map((a) => (
            <div key={a.area} className="mb-1.5">
              <div className="flex justify-between text-xs"><span>{a.area}</span><span className="tabular-nums text-muted">{fmtTokens(a.tokens)}</span></div>
              <div className="h-1.5 rounded-pill bg-surface-2"><div className="h-1.5 rounded-pill bg-accent" style={{ width: `${total ? Math.max(2, (100 * a.tokens) / total) : 0}%` }} /></div>
            </div>
          )) : <p className="text-xs text-muted">{t("Tiada penggunaan direkod dalam tempoh ini. Setiap larian scrape, media, idea dan resit menulis baris di sini mulai sekarang.", "No usage recorded in this window. Every scrape, media, idea and receipt run writes rows here from now on.")}</p>}
          <p className="mt-3 text-[11px] text-muted">{t("Token ialah apa yang gerbang laporkan dalam `usage`; gerbang yang tidak melaporkan dikira sebagai panggilan dengan 0 token.", "Tokens are what the gateway reports in `usage`; a gateway that reports none counts as a call with 0 tokens.")}</p>
        </Card>
      </div>
    </main>
  );
}

function Stat({ label, value, hint, warn }) {
  return (
    <div>
      <p className="text-[10px] uppercase tracking-widest text-muted">{label}</p>
      <p className="truncate font-medium tabular-nums" title={String(value)}>{value}</p>
      {hint && <p className={`text-[11px] ${warn ? "text-danger" : "text-muted"}`}>{hint}</p>}
    </div>
  );
}
