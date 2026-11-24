import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Activity, AlertTriangle, CheckCircle2, Cpu, KeyRound, RefreshCw, Timer, Wallet, XCircle } from "lucide-react";
import { fadeUp } from "../design/motion";
import { TABLES, errText, supabase } from "../lib/SupabaseClient";
import { useLang } from "../lib/i18n";
import { useApiUsage, useTable } from "../lib/hooks";
import { stampMYT, timeAgo } from "../lib/format";
import { fmtTokens, orderedModels, usageByArea, usageByDay, usageByGateway, verdictOf } from "../lib/api";
import { modelOverride, rateCheck, robotOf, stateOf, withModel } from "../lib/aiTeam";
import { colourFor } from "../lib/robots";
import { formOf, rpcArgs } from "../lib/aiProviders";
import { checkAI } from "../lib/chat";
import { withProviderModel } from "../lib/claudeSetup";
import Card from "../components/ui/Card";
import { Segmented } from "../components/ui/Field";
import AiTeam from "../components/AiTeam";
import ApiPulse from "../components/ApiPulse";
import GeminiKeys from "../components/GeminiKeys";
import AiProviders from "../components/AiProviders";
import ClaudeSetup from "../components/ClaudeSetup";
import ChatGptLogin from "../components/ChatGptLogin";
import ThreadsConnect from "../components/ThreadsConnect";
import { AiSettings, MireldTrial } from "./SettingsTab";

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
  none: { cls: "bg-surface-2 text-muted", icon: Cpu, bm: "Tiada", en: "None" },
};
const COLOURS = ["rgb(var(--c-accent))", "rgb(var(--c-ok))", "rgb(var(--c-warn))", "rgb(var(--c-danger))", "rgb(var(--c-muted))"];

// the page's five parts, in setup order: [element id, Bahasa Malaysia, English]
const SECTIONS = [["api-setup", "Tetapan pantas", "Quick setup"], ["api-team", "Siapa buat apa", "Who does what"], ["api-robots", "Setiap robot", "Each robot"],
  ["api-connect", "Kunci dan log masuk", "Keys and logins"], ["api-usage", "Penggunaan", "Usage"]];

// the gateways whose default model is set from GitHub variables or secrets, so a page choice is the only way to move it
const ADJUSTABLE = ["rootsys", "mireld"];

export default function ApiTab({ settings, save, onToast, go }) {
  const { t, lang } = useLang();
  const L = lang === "en" ? "en" : "bm";
  // realtime: the 5-minute pulse (supabase/075, semasa-pulse) rewrites these rows and every robot card redraws as the row lands
  const statusT = useTable(TABLES.apiStatus, { enabled: true, order: "role", ascending: true, limit: 20, realtime: true, everyMs: 60_000 });
  // 90 days of daily totals (the widest window the page offers; supabase/091, 545 rows on 22 Nov 2026), re-read for the last two
  // days every 5 minutes; until 091 is run, the raw rows as before (at most 5,000), read on only for what is new
  const usage = useApiUsage({ days: 90, rawPulse: true,
    rawSelect: "id,gateway,model,area,prompt_tokens,completion_tokens,total_tokens,ms,ok,created_at" });
  // the providers Wan added (supabase/074): read here so the AI team cards number them W6, W7, ... (realtime: the table is published)
  const providersT = useTable(TABLES.aiProviders, { enabled: true, order: "created_at", ascending: true, limit: 50, everyMs: 120_000 });
  const [days, setDays] = useState(30);
  const [picking, setPicking] = useState("");                                  // "slug|model" while a default-model choice is being saved
  // A robot's own default model (Wan, 9 Nov 2026: "allow me to adjust model mireld"): its probe asks this one and its jobs use it unless
  // a pin names another. Click a listed model to make it the default, click it again (or Reset) to go back to the configured one.
  const setDefaultModel = async (slug, model) => {
    if (typeof save !== "function") return;
    setPicking(`${slug}|${model}`);
    try {
      await save("ai_team", withModel(settings?.ai_team, slug, model));
      onToast?.(model ? t("{m} ialah model lalai {r}: disemak dalam kira-kira 5 minit.", "{m} is {r}'s default model: it is checked within about 5 minutes.", { m: model, r: slug })
        : t("Model lalai {r} kembali kepada yang ditetapkan di GitHub.", "{r}'s default model is back to the one GitHub sets.", { r: slug }), "ok");
    } catch (e) { onToast?.(e?.message || String(e), "danger"); } finally { setPicking(""); }
  };
  // A provider Wan added (Claude, W6..): its model lives on its own row, which the workers AND the chat and Telegram functions read, so a
  // click saves it there, moves the pins that name this provider, wakes the worker's live check and asks the model one live question now
  // (Wan, 24 Nov 2026: "function by click the model to change the model is live").
  const setProviderModel = async (slug, model) => {
    const row = providersT.rows.find((p) => p.id === slug);
    if (!row || typeof save !== "function" || !supabase) return;
    setPicking(`${slug}|${model}`);
    try {
      const { error } = await supabase.rpc("semasa_save_ai_provider", rpcArgs({ ...formOf(row), model }));
      if (error) throw new Error(errText(error));
      await providersT.reload?.();
      await save("ai_team", withProviderModel(settings?.ai_team, slug, model));
      onToast?.(t("{m} disimpan untuk {r}. Menguji terus…", "{m} saved for {r}. Testing it live…", { m: model, r: row.name || slug }), "ok");
      const r = rateCheck(await checkAI(`${slug}|${model}`));
      if (r.tested && r.parts?.answered) onToast?.(t("{m} menjawab dalam {s} s: ia hidup.", "{m} answered in {s} s: it is live.", { m: model, s: r.ms ? (r.ms / 1000).toFixed(1) : "?" }), "ok");
      else onToast?.(t("{m} tidak menjawab ujian terus: {w}", "{m} did not answer the live test: {w}", { m: model, w: r.why || r.note || "-" }), "danger");
    } catch (e) { onToast?.(e?.message || String(e), "danger"); } finally { setPicking(""); }
  };
  const byGw = useMemo(() => usageByGateway(usage.daily, days), [usage.daily, days]);
  const byDay = useMemo(() => usageByDay(usage.daily, days), [usage.daily, days]);
  const byArea = useMemo(() => usageByArea(usage.daily, days), [usage.daily, days]);
  const missing = /semasa_api_(status|usage)/.test(statusT.error || usage.error || "");
  const total = Object.values(byGw).reduce((n, g) => n + g.tokens, 0);
  const calls = Object.values(byGw).reduce((n, g) => n + g.calls, 0);
  const failed = Object.values(byGw).reduce((n, g) => n + g.failed, 0);
  const lastCheck = statusT.rows.reduce((m, r) => (r.checked_at > m ? r.checked_at : m), "");

  return (
    <main className="mx-auto max-w-page px-4 pb-20 pt-10 sm:px-6">
      <motion.div variants={fadeUp} initial="hidden" animate="show" className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-3xl">API</h1>
          <p className="mt-1 max-w-2xl text-sm text-muted">{t("Gerbang AI (rootsys milik Afiq, Mireld): hidup atau tidak, kunci diterima atau tidak, model yang disenaraikan, dan token yang kita belanja. Disemak penuh setiap 6 jam dan didenyut setiap 5 minit; penggunaan ditulis oleh setiap larian.",
            "The AI gateways (Afiq's rootsys, Mireld): up or not, key accepted or not, the models each lists, and the tokens we spend. Checked in full every 6 hours and pulsed every 5 minutes; usage is written by every run.")}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {lastCheck && <span className="text-xs text-muted"><RefreshCw size={12} className="mr-1 inline" />{t("disemak", "checked")} {timeAgo(lastCheck)}</span>}
          <Segmented value={String(days)} onChange={(v) => setDays(Number(v))} options={[["7", t("7 hari", "7 days")], ["30", t("30 hari", "30 days")], ["90", t("90 hari", "90 days")]]} />
        </div>
      </motion.div>

      {missing && <p className="mb-4 rounded-tile bg-warn/10 p-3 text-sm text-warn">{t("Jadual belum ada: jalankan supabase/035_repos_api.sql sekali, kemudian larian API status di GitHub.", "The tables are not there yet: run supabase/035_repos_api.sql once, then the API status workflow on GitHub.")}</p>}
      {(statusT.error || usage.error) && !missing && <p className="mb-4 rounded-tile bg-danger/10 p-3 text-sm text-danger">{statusT.error || usage.error}</p>}
      {!statusT.loading && !statusT.error && !statusT.rows.length && (
        <p className="mb-4 rounded-tile bg-surface-2 p-3 text-sm text-muted">{t("Belum disemak: larian API status (GitHub → Actions → API status → Run workflow) menanya setiap gerbang dan mengisi kad di bawah.",
          "Not checked yet: the API status workflow (GitHub → Actions → API status → Run workflow) asks every gateway and fills the cards below.")}</p>
      )}

      {/* The page in five numbered parts, in the order Wan sets things up (24 Nov 2026: "rearrange API layout so easy to configure"):
          set it up, see who does what, look at each robot, connect keys and logins, read the spend. The row below jumps to each. */}
      <nav className="mb-5 flex flex-wrap gap-2" aria-label={t("Bahagian halaman API", "API page sections")} data-api-nav>
        {SECTIONS.map(([id, bm, en], n) => (
          <button key={id} type="button" onClick={() => document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" })}
            className="rounded-pill border border-line bg-surface px-3 py-1.5 text-xs font-medium text-ink hover:border-accent hover:text-accent" data-api-jump={id}>
            <span className="mr-1 text-muted">{n + 1}</span>{L === "en" ? en : bm}
          </button>
        ))}
      </nav>

      <section className="mb-8 scroll-mt-20" id="api-setup" data-api-section="setup">
        <SectionHead n={1} title={t("Tetapan pantas", "Quick setup")} hint={t("Satu kad: Claude untuk teks, ChatGPT untuk gambar, dengan butang Uji dan Betulkan.", "One card: Claude for text, ChatGPT for pictures, with its Test and Fix buttons.")} />
        <ClaudeSetup providers={providersT.rows} statusRows={statusT.rows} team={settings?.ai_team} request={settings?.ai_test}
          result={settings?.ai_test_result} save={save} onChanged={providersT.reload} onToast={onToast} />
      </section>

      <section className="mb-8 scroll-mt-20" id="api-team" data-ai-team data-api-section="team">
        <SectionHead n={2} title={t("Siapa buat apa", "Who does what")} hint={t("Setiap robot dengan warnanya sendiri, dan robot serta model yang dipilih untuk setiap kerja.", "Every robot in its own colour, and the robot and model chosen for each job.")} />
        <div className="mb-3"><ApiPulse onToast={onToast} /></div>
        <AiTeam statusRows={statusT.rows} usageRows={usage.recent} state={settings?.ai_team_state} team={settings?.ai_team} save={save} onToast={onToast} providers={providersT.rows} />
      </section>

      <section className="mb-8 scroll-mt-20" id="api-robots" data-api-section="robots">
        <SectionHead n={3} title={t("Setiap robot: kunci, model, kelajuan", "Each robot: key, model, speed")} hint={t("Klik model untuk menukarnya. Ralat terakhir setiap gerbang ditunjukkan di sini.", "Click a model to change it. Each gateway's last error shows here.")} />
      <div className="mb-6 grid gap-4 lg:grid-cols-2">
        {statusT.rows.map((r) => {
          const v = verdictOf(r);
          const V = VERDICT[v] || VERDICT.none;
          const u = byGw[r.slug] || { calls: 0, failed: 0, tokens: 0, prompt: 0, completion: 0, ms: 0, models: {} };
          const models = orderedModels(r);
          const provRow = providersT.rows.find((p) => p.id === r.slug);
          // the robot's own colour on its card while it is live, one grey when it is not (the same rule as the robot cards above)
          const colour = colourFor(robotOf(r.slug, r, providersT.rows), stateOf(r, usage.recent) !== "offline");
          // a provider's chosen model is its own row's; a built-in robot's is the override Wan clicked (settings.ai_team.models)
          const over = r.role === "provider" && provRow ? "" : modelOverride(settings?.ai_team, r.slug);
          const isProvider = r.role === "provider" && providersT.rows.some((p) => p.id === r.slug);
          const canAdjust = typeof save === "function" && (ADJUSTABLE.includes(r.slug) || isProvider);
          return (
            <Card key={r.slug} className="p-4" data-status-card={r.slug} data-robot-colour={colour} style={{ borderLeft: `4px solid ${colour}` }}>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <p className="font-display text-lg"><span className="mr-2 inline-block h-2.5 w-2.5 rounded-full align-middle" style={{ background: colour }} aria-hidden="true" />{r.name || r.slug} <span className="text-xs text-muted">· {r.role}</span></p>
                  <p className="truncate text-xs text-muted">{r.base_url}</p>
                </div>
                <span className={`inline-flex items-center gap-1 rounded-pill px-2 py-0.5 text-[11px] ${V.cls}`}><V.icon size={12} /> {V[L]}</span>
              </div>
              <div className="mt-3 grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
                <Stat label={t("Kunci", "Key")} value={r.key_set ? `…${r.key_last4}` : t("Tiada", "None")} hint={r.key_ok === false ? t("ditolak", "refused") : r.key_ok ? t("diterima", "accepted") : t("belum ditanya", "not asked")} />
                <Stat label={t("Model", "Model")} value={r.model || t("Tiada", "None")} hint={r.model_listed === true ? t("dalam senarai", "listed") : r.model_listed === false ? t("TIADA dalam senarai", "NOT listed") : ""} warn={r.model_listed === false} />
                <Stat label={t("Masa jawab", "Latency")} value={r.chat_ms != null ? `${r.chat_ms} ms` : r.latency_ms != null ? `${r.latency_ms} ms` : t("Tiada", "None")} hint={r.http ? `HTTP ${r.http}` : ""} />
                <Stat label={t("Token {d} hari", "Tokens {d} days", { d: days })} value={fmtTokens(u.tokens)} hint={t("{n} panggilan, {f} gagal", "{n} calls, {f} failed", { n: u.calls, f: u.failed })} warn={u.failed > 0} />
              </div>
              {balanceLine(r.balance) && (
                <p className="mt-2 text-xs text-muted"><Wallet size={12} className="mr-1 inline" />{balanceLine(r.balance)} <span className="opacity-70">({r.balance.path})</span>
                  {r.balance.credit && <> · <button type="button" className="underline hover:text-accent" onClick={() => go?.("kredit")}>{t("Baki kredit API", "API credit")}</button></>}</p>
              )}
              {r.error && <p className="mt-2 rounded-tile bg-danger/10 p-2 text-xs text-danger">{r.error}</p>}
              <div className="mt-3">
                <p className="mb-1 flex flex-wrap items-center gap-2 text-xs font-medium text-muted">{t("Model disenaraikan", "Models listed")} · {models.length}
                  {canAdjust && <span className="font-normal">{over
                    ? <>· {t("lalai anda", "your default")}: <b className="text-ink">{over}</b> <button type="button" className="underline hover:text-accent" onClick={() => setDefaultModel(r.slug, "")} disabled={!!picking}>{t("Set semula", "Reset")}</button></>
                    : isProvider ? <>· {t("klik model untuk menukar model {r}: disimpan dan diuji terus", "click a model to change {r}'s model: saved and tested live", { r: r.name || r.slug })}</>
                    : <>· {t("klik model untuk jadikan lalai {r}", "click a model to make it {r}'s default", { r: r.name || r.slug })}</>}</span>}
                </p>
                {models.length ? (
                  <div className={`flex flex-wrap gap-1 ${models.length > 24 ? "max-h-44 overflow-y-auto pr-1" : ""}`} data-model-list={r.slug}>
                    {models.map((m) => {
                      const cls = `rounded-pill px-2 py-0.5 text-[11px] ${m === r.model ? "bg-accent/15 text-accent" : u.models[m] ? "bg-ok/10 text-ok" : "bg-surface-2 text-muted"}`;
                      const title = u.models[m] ? `${fmtTokens(u.models[m])} tokens` : "";
                      if (!canAdjust) return <span key={m} className={cls} title={title}>{m}</span>;
                      const mine = isProvider ? m === provRow?.model : m === over;
                      return (
                        <button type="button" key={m} onClick={() => (isProvider ? (mine ? null : setProviderModel(r.slug, m)) : setDefaultModel(r.slug, mine ? "" : m))}
                          disabled={!!picking} aria-pressed={mine} data-default-model={m}
                          title={isProvider ? (mine ? t("Model {r} sekarang", "{r}'s model now", { r: r.name || r.slug }) : t("Tukar {r} kepada model ini dan uji terus", "Change {r} to this model and test it live", { r: r.name || r.slug }))
                            : mine ? t("Model lalai anda: klik untuk kembali", "Your default model: click to go back") : t("Jadikan model lalai {r}", "Make this {r}'s default model", { r: r.name || r.slug })}
                          className={`${cls} border transition hover:border-accent hover:text-accent disabled:opacity-50 ${mine ? "border-accent font-medium ring-1 ring-accent/40" : "border-transparent"}`}>
                          {picking === `${r.slug}|${m}` ? "…" : ""}{m}{mine ? " ✓" : ""}</button>
                      );
                    })}
                  </div>
                ) : <p className="text-xs text-muted">{t("Gerbang tidak menyenaraikan model (atau kunci ditolak).", "The gateway lists no models (or the key was refused).")}</p>}
              </div>
              <p className="mt-2 text-[11px] text-muted">{r.checked_at ? `${t("disemak", "checked")} ${stampMYT(r.checked_at)}` : ""}</p>
            </Card>
          );
        })}
      </div>

      </section>

      <section className="mb-8 scroll-mt-20 space-y-5" id="api-connect" data-ai-settings data-api-section="connect">
        <SectionHead n={4} title={t("Kunci dan log masuk", "Keys and logins")} hint={t("Tambah atau tukar kunci, log masuk ChatGPT, kunci Gemini, penyedia tambahan dan aplikasi Threads.", "Add or change keys, the ChatGPT login, the Gemini keys, extra providers and the Threads app.")} />
        {/* ChatGPT beside the other robots (Wan, 7 Nov 2026: "for chatgpt put together in API, same with others"); Motion uses it from here */}
        <div data-chatgpt-section><ChatGptLogin onToast={onToast} /></div>
        <div data-gemini-section><GeminiKeys settings={settings} save={save} onToast={onToast} /></div>
        {/* extra providers: Anthropic, a second KiosAPI key, any OpenAI-compatible gateway, as robots W6, W7, ... */}
        <AiProviders statusRows={statusT.rows} usageRows={usage.recent} onToast={onToast} />
        {/* moved here from Tetapan (Wan, 7 Nov 2026: "API in setting" goes to its segment): the workers' keys and endpoints, and one Mireld run */}
        <AiSettings onToast={onToast} github={{ scrape: settings?.ai_github_scrape, media: settings?.ai_github_media }} />
        {/* Wan's own Threads app (supabase/080): the viral-post feed reads Threads through it, Composio's shared app having no search permission */}
        <div data-threads-section><ThreadsConnect onToast={onToast} /></div>
        <MireldTrial settings={settings || {}} save={save} onToast={onToast} />
      </section>

      <section className="scroll-mt-20" id="api-usage" data-api-section="usage">
        <SectionHead n={5} title={t("Penggunaan token", "Token usage")} hint={t("Token sehari mengikut gerbang, dan siapa yang membelanjakannya.", "Tokens a day by gateway, and who spends them.")} />
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
          {usage.missing && <p className="mt-1 text-[11px] text-muted" data-usage-raw>{t("Jalankan supabase/091_api_usage_daily.sql sekali untuk jumlah harian penuh. Sehingga itu, halaman ini membaca 5,000 panggilan terkini sahaja.",
            "Run supabase/091_api_usage_daily.sql once for full daily totals. Until then this page reads only the latest 5,000 calls.")}</p>}
        </Card>
      </div>
      </section>
    </main>
  );
}

/** The one line of figures a balance endpoint answered (its numbers and short words), without the credit reading's own objects. */
function balanceLine(b) {
  if (!b || !b.path) return "";
  return Object.entries(b).filter(([k, val]) => k !== "path" && ["number", "string"].includes(typeof val) && k !== "checked_at").map(([k, val]) => `${k}: ${val}`).join(" · ");
}

function SectionHead({ n, title, hint }) {
  return (
    <div className="mb-3">
      <h2 className="flex items-center gap-2 font-display text-xl">
        <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-accent/15 text-xs font-semibold text-accent">{n}</span>{title}</h2>
      {hint && <p className="mt-0.5 text-[12px] text-muted">{hint}</p>}
    </div>
  );
}

function Stat({ label, value, hint, warn }) {
  return (
    <div>
      <p className="text-[11px] font-medium text-muted">{label}</p>
      <p className="truncate font-medium tabular-nums" title={String(value)}>{value}</p>
      {hint && <p className={`text-[11px] ${warn ? "text-danger" : "text-muted"}`}>{hint}</p>}
    </div>
  );
}
