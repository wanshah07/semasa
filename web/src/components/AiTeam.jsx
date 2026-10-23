import { useMemo, useState } from "react";
import { Pin, PinOff, Zap } from "lucide-react";
import Robot3D from "./Robot3D";
import { useLang } from "../lib/i18n";
import { stampMYT, timeAgo } from "../lib/format";
import { DOES, JOBS, decisionOf, fmtMs, modelsFor, pinFor, robotsFor, teamCards, withPin } from "../lib/aiTeam";
import Card from "./ui/Card";
import Button from "./ui/Button";
import { Select } from "./ui/Field";

/* The AI team as its robots (Wan, 23 Oct 2026: "make sure robots appear as attach ... for all segments, make sure can have
   each robot, AI providers and its model, and the model automatically switch"). Three Wanshah robots, each with its state
   (active = worked in the last 3 h, standby = reachable, offline = not), the jobs it does, the model it runs, its speed.
   `compact` is the Papan strip; the full card (API tab) also shows the router's decision for each job and lets Wan pin a
   robot + model per job — a pin the router still switches away from when that robot is down. */

const STATE_CLS = { active: "bg-ok/15 text-ok", standby: "bg-warn/15 text-warn", offline: "bg-danger/15 text-danger" };
const STATE_WORDS = { active: ["Aktif", "Active"], standby: ["Sedia", "Standby"], offline: ["Luar talian", "Offline"] };

export default function AiTeam({ statusRows, usageRows, state, team, save, onToast, compact = false }) {
  const { t, lang } = useLang();
  const L = lang === "en" ? 1 : 0;
  const w = (v) => (Array.isArray(v) ? v[L] : v);
  const cards = useMemo(() => teamCards(statusRows, usageRows), [statusRows, usageRows]);
  const reader = decisionOf(state, "reader");
  const chosen = reader.chosen?.slug;

  return (
    <div className={compact ? "grid gap-3 grid-cols-1 min-[480px]:grid-cols-3" : "grid gap-4 sm:grid-cols-2 xl:grid-cols-3"}>
      {cards.map((c) => {
        const order = reader.order.find((o) => o.slug === c.slug);
        const skipped = reader.skipped.find((o) => o.slug === c.slug);
        const r = c.row;
        return (
          <Card key={c.slug} className={`p-4 ${compact ? "flex flex-col items-center text-center" : ""}`} data-robot={c.robot}>
            <div className={`flex ${compact ? "flex-col items-center" : "flex-col sm:flex-row sm:items-center"} gap-3`}>
              <div className="shrink-0"><Robot3D tone={c.tone} state={c.state} size={compact ? 96 : 118} name={c.name} label={c.robot} /></div>
              <div className="min-w-0 w-full">
                <div className={`flex flex-wrap items-center gap-2 ${compact ? "justify-center" : ""}`}>
                  <span className="font-display text-lg">{c.name}</span>
                  <span className={`rounded-pill px-2 py-0.5 text-[11px] ${STATE_CLS[c.state]}`}>● {w(STATE_WORDS[c.state])}</span>
                  {chosen === c.slug && <span className="rounded-pill bg-accent/15 px-2 py-0.5 text-[11px] text-accent"><Zap size={10} className="mr-0.5 inline" />{t("menulis sekarang", "writing now")}</span>}
                  {reader.backup?.slug === c.slug && <span className="rounded-pill bg-surface-2 px-2 py-0.5 text-[11px] text-muted">{t("sandaran", "backup")}</span>}
                </div>
                <div className={`mt-1 flex flex-wrap gap-1 ${compact ? "justify-center" : ""}`}>
                  {c.does.map((d) => <span key={d} className="rounded-pill bg-surface-2 px-2 py-0.5 text-[10px] uppercase tracking-wider text-muted">{w(DOES[d])}</span>)}
                </div>
                {!compact && (
                  <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs">
                    <dt className="text-muted">{t("Gerbang", "Gateway")}</dt><dd className="truncate">{r?.name || c.slug}{r?.base_url ? <span className="text-muted"> · {r.base_url.replace(/^https?:\/\//, "")}</span> : ""}</dd>
                    <dt className="text-muted">{t("Model", "Model")}</dt><dd className="truncate font-medium">{order?.model || r?.model || "—"}</dd>
                    <dt className="text-muted">{t("Kelajuan", "Speed")}</dt><dd>{fmtMs(order?.speed_ms ?? r?.chat_ms ?? r?.latency_ms)}{order?.why ? <span className="text-muted"> · {order.why}</span> : ""}</dd>
                    {r?.checked_at && <><dt className="text-muted">{t("Disemak", "Checked")}</dt><dd>{timeAgo(r.checked_at)}</dd></>}
                    {skipped && <><dt className="text-danger">{t("Dilangkau", "Skipped")}</dt><dd className="text-danger">{skipped.why}</dd></>}
                    {!r && <><dt className="text-muted">{t("Kunci", "Key")}</dt><dd className="text-muted">{t("belum ditetapkan di Tetapan → Tetapan AI", "not set in Tetapan → AI settings")}</dd></>}
                    {r?.error && !skipped && <><dt className="text-danger">{t("Ralat", "Error")}</dt><dd className="truncate text-danger" title={r.error}>{r.error}</dd></>}
                  </dl>
                )}
                {compact && <p className="mt-1 truncate text-xs text-muted">{order?.model || r?.model || (r ? "" : t("tiada kunci", "no key"))}</p>}
              </div>
            </div>
          </Card>
        );
      })}
      {!compact && <JobPins cards={cards} state={state} team={team} save={save} onToast={onToast} />}
    </div>
  );
}

/* One row per job: what runs it now and why, and the pin (robot + model) Wan may set. Auto = the router's own choice. */
function JobPins({ cards, state, team, save, onToast }) {
  const { t, lang } = useLang();
  const L = lang === "en" ? 1 : 0;
  const [busy, setBusy] = useState("");
  const jobs = ["reader", "motion", "image_gen", "image_reader"];
  const canSave = typeof save === "function";

  const setPin = async (job, pin) => {
    if (!canSave) return;
    setBusy(job);
    try {
      await save("ai_team", withPin(team, job, pin));
      onToast?.(pin ? t("Disemat: larian seterusnya cuba {r} dahulu (masih bertukar jika ia rosak).", "Pinned: the next run tries {r} first (it still switches if it is down).", { r: pin.gateway })
        : t("Auto: pengarah pilih robot terpantas yang sihat.", "Auto: the router picks the fastest healthy robot."), "ok");
    } catch (e) { onToast?.(e.message || String(e), "error"); } finally { setBusy(""); }
  };

  return (
    <Card className="p-4 sm:col-span-2 xl:col-span-3" data-ai-pins>
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-medium">{t("Siapa buat apa", "Who does what")}</h2>
        <span className="text-[11px] text-muted">{state?.at ? `${t("diputuskan", "decided")} ${stampMYT(state.at)}` : t("belum diputuskan: larian seterusnya menulisnya", "not decided yet: the next run writes it")}</span>
      </div>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {jobs.map((job) => {
          const d = decisionOf(state, job);
          const pin = pinFor(team, job);
          const choices = robotsFor(cards, job);
          const pinnedCard = choices.find((c) => c.slug === pin?.gateway);
          const models = pinnedCard ? modelsFor(pinnedCard.row, job) : [];
          return (
            <div key={job} className="rounded-tile bg-surface-2/60 p-3" data-ai-job={job}>
              <p className="text-[11px] uppercase tracking-widest text-muted">{JOBS[job][L]}</p>
              {job === "reader" || job === "motion" ? (
                <p className="mt-1 text-sm">{d.chosen ? <><span className="font-medium">{d.chosen.name}</span> · {d.chosen.model}</> : <span className="text-muted">{d.why || t("tiada robot teks dengan kunci", "no text robot with a key")}</span>}</p>
              ) : (
                <p className="mt-1 text-sm text-muted">{pin ? <><span className="font-medium text-ink">{pinnedCard?.name || pin.gateway}</span>{pin.model ? ` · ${pin.model}` : ""}</> : t("ikut Tetapan → Tetapan AI", "as set in Tetapan → AI settings")}</p>
              )}
              {(job === "reader" || job === "motion") && d.why && d.chosen && <p className="text-[11px] text-muted">{d.why}{d.backup ? ` · ${t("sandaran", "backup")}: ${d.backup.name || d.backup.slug}` : ""}</p>}
              {(job === "reader" || job === "motion") && d.order.length > 1 && (
                <ol className="mt-1 text-[11px] text-muted">{d.order.map((o, i) => <li key={o.slug}>{i + 1}. {o.name} · {o.model || "—"} · {o.why}</li>)}</ol>
              )}
              {(job === "reader" || job === "motion") && d.skipped.map((o) => <p key={o.slug} className="mt-1 text-[11px] text-danger">{o.why}</p>)}
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <Select value={pin?.gateway || ""} disabled={!canSave || busy === job}
                  onChange={(v) => setPin(job, v ? { gateway: v, model: "" } : null)}
                  options={[["", t("Auto (terpantas)", "Auto (fastest)")], ...choices.map((c) => [c.slug, `${c.name} · ${c.row?.name || c.slug}`])]} />
                {pin && (
                  <Select value={pin.model || ""} disabled={!canSave || busy === job} onChange={(v) => setPin(job, { ...pin, model: v })}
                    options={[["", t("model lalai", "default model")], ...models.map((m) => [m, m])]} />
                )}
                {pin
                  ? <Button size="sm" variant="ghost" disabled={!canSave || busy === job} onClick={() => setPin(job, null)}><PinOff size={12} /> {t("Auto", "Auto")}</Button>
                  : <span className="inline-flex items-center gap-1 text-[11px] text-muted"><Pin size={11} /> {t("auto", "auto")}</span>}
              </div>
            </div>
          );
        })}
      </div>
      <p className="mt-3 text-[11px] text-muted">{t("Semat ialah keutamaan, bukan kunci: robot yang disemat tetapi rosak (ujian gagal, atau lebih separuh panggilan 48 jam gagal) dilangkau dan yang terpantas mengambil alih. Wanshah 3 melukis sahaja; ia tidak pernah menulis teks.",
        "A pin is a preference, not a lock: a pinned robot that is down (probe failed, or more than half its calls in 48 h failed) is skipped and the fastest takes over. Wanshah 3 only paints; it never writes text.")}</p>
    </Card>
  );
}
