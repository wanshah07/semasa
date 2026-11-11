import { useMemo, useState } from "react";
import { Loader2, Pin, PinOff, RefreshCw, Star, Zap } from "lucide-react";
import Robot3D from "./Robot3D";
import { useLang } from "../lib/i18n";
import { stampMYT, timeAgo } from "../lib/format";
import { DOES, EFFORTS, EFFORT_WORDS, JOBS, decisionOf, decisionPending, effortOf, fmtMs, liveLines, modelsFor, pinFor, rateCheck, rateImage, robotsFor, teamCards, withEffort, withPin } from "../lib/aiTeam";
import { checkAI, checkImageAI } from "../lib/chat";
import Card from "./ui/Card";
import Button from "./ui/Button";

/* The AI team as its robots (Wan, 23 Oct 2026: "make sure robots appear as attach ... for all segments, make sure can have
   each robot, AI providers and its model, and the model automatically switch"). Three Wanshah robots, each with its state
   (active = worked in the last 3 h, standby = reachable, offline = not), the jobs it does, the model it runs, its speed.
   `compact` is the Papan strip; the full card (API tab) also shows the router's decision for each job and lets Wan pin a
   robot + model per job — a pin the router still switches away from when that robot is down. */

const STATE_CLS = { active: "bg-ok/15 text-ok", standby: "bg-warn/15 text-warn", offline: "bg-danger/15 text-danger" };
const STATE_WORDS = { active: ["Aktif", "Active"], standby: ["Sedia", "Standby"], offline: ["Luar talian", "Offline"] };

export default function AiTeam({ statusRows, usageRows, state, team, save, onToast, compact = false, providers = [] }) {
  const { t, lang } = useLang();
  const L = lang === "en" ? 1 : 0;
  const w = (v) => (Array.isArray(v) ? v[L] : v);
  const cards = useMemo(() => teamCards(statusRows, usageRows, Date.now(), providers), [statusRows, usageRows, providers]);
  const reader = decisionOf(state, "reader");
  const chosen = reader.chosen?.slug;

  return (
    <div className={compact ? "grid gap-3 grid-cols-2 min-[480px]:grid-cols-3" : "grid gap-4 sm:grid-cols-2 xl:grid-cols-3"}>
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
                  {c.does.map((d) => <span key={d} className="rounded-pill bg-surface-2 px-2 py-0.5 text-[11px] font-medium text-muted">{w(DOES[d])}</span>)}
                </div>
                {!compact && (
                  <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs">
                    <dt className="text-muted">{t("Gerbang", "Gateway")}</dt><dd className="truncate">{r?.name || c.slug}{r?.base_url ? <span className="text-muted"> · {r.base_url.replace(/^https?:\/\//, "")}</span> : ""}</dd>
                    <dt className="text-muted">{t("Model", "Model")}</dt><dd className="truncate font-medium">{order?.model || r?.model || t("Tiada", "None")}</dd>
                    <dt className="text-muted">{t("Kelajuan", "Speed")}</dt><dd>{fmtMs(order?.speed_ms ?? r?.chat_ms ?? r?.latency_ms) || t("Tiada", "None")}{order?.why ? <span className="text-muted"> · {order.why}</span> : ""}</dd>
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
const LIVE_KEY = "semasa.aiteam.liveOnPick";
const liveOnPick = () => { try { return localStorage.getItem(LIVE_KEY) !== "off"; } catch { return true; } };

/* A model's rating as stars and the numbers behind them, under its buttons. */
function Rating({ r, t }) {
  if (!r) return null;
  if (r.busy) return <p className="mt-2 flex items-center gap-1 text-[11px] text-accent" data-ai-rate><Loader2 size={11} className="animate-spin" />{t("menguji model ini terus (gambar mengambil sehingga seminit)…", "testing this model live (a picture can take up to a minute)…")}</p>;
  if (!r.tested) return <p className="mt-2 text-[11px] text-muted" data-ai-rate>{t("Tidak diuji terus: ", "Not tested live: ")}{r.why}</p>;
  const p = r.parts;
  if (r.kind === "image") return (
    <p className="mt-2 text-[11px]" data-ai-rate={r.score} data-ai-rate-kind="image">
      <span className="inline-flex items-center gap-0.5 text-warn" aria-label={`${r.stars} / 5`}>
        {[1, 2, 3, 4, 5].map((n) => <Star key={n} size={12} className={n <= r.stars ? "fill-current" : "opacity-30"} />)}</span>
      <b className="ml-1">{r.score}/100</b>
      <span className="text-muted"> · {r.ms != null ? fmtMs(r.ms) : t("tiada masa", "no time")} · {t("melukis gambar", "drew a picture")} {p.drew ? "✓" : "✗"}{r.note ? ` · ${r.note}` : ""}</span>
    </p>
  );
  return (
    <p className="mt-2 text-[11px]" data-ai-rate={r.score}>
      <span className="inline-flex items-center gap-0.5 text-warn" aria-label={`${r.stars} / 5`}>
        {[1, 2, 3, 4, 5].map((n) => <Star key={n} size={12} className={n <= r.stars ? "fill-current" : "opacity-30"} />)}</span>
      <b className="ml-1">{r.score}/100</b>
      <span className="text-muted"> · {r.ms != null ? fmtMs(r.ms) : t("tiada masa", "no time")} · {t("baca gambar", "reads a picture")} {p.picture ? "✓" : "✗"} · {t("guna alat", "calls a tool")} {p.tools ? "✓" : "✗"}{r.note ? ` · ${r.note}` : ""}</span>
    </p>
  );
}

function JobPins({ cards, state, team, save, onToast }) {
  const { t, lang } = useLang();
  const L = lang === "en" ? 1 : 0;
  const [busy, setBusy] = useState("");
  const [liveOn, setLive] = useState(liveOnPick);                 // try the model live as soon as it is picked (Wan, 9 Nov 2026), or not
  const [rates, setRates] = useState({});                       // "slug|model" -> rating, kept while the page is open
  const toggleLive = (on) => { setLive(on); try { localStorage.setItem(LIVE_KEY, on ? "on" : "off"); } catch { /* not remembered */ } };
  // The function's own live check of one robot + model: a real chat call with a picture and a tool. Image makers cannot be asked this.
  const rate = async (slug, model, job) => {
    const key = `${slug}|${model}`;
    setRates((r) => ({ ...r, [key]: { busy: true } }));
    let out;
    // a picture maker has no chat to ask: the function draws one small real picture at its own address (a few cents at most) and says whether one came back
    try { out = job === "image_gen" ? rateImage(await checkImageAI(key)) : rateCheck(await checkAI(key)); } catch (e) { out = { tested: false, why: e.message || String(e) }; }
    setRates((r) => ({ ...r, [key]: out }));
  };
  const jobs = ["reader", "motion", "image_gen", "image_reader"];
  const canSave = typeof save === "function";
  const pending = decisionPending(team, state);

  // "Test live": the same pins saved again with a new time, which wakes the worker (supabase/057) to ask the gateways and decide
  const retest = async () => {
    if (!canSave) return;
    setBusy("retest");
    try {
      await save("ai_team", withPin(team, "reader", pinFor(team, "reader")));
      onToast?.(t("Gerbang ditanya sekarang: keputusan baharu dalam kira-kira seminit.", "The gateways are being asked now: the new decision shows in about a minute."), "ok");
    } catch (e) { onToast?.(e.message || String(e), "error"); } finally { setBusy(""); }
  };

  const setPin = async (job, pin, tryIt = false) => {
    if (!canSave) return;
    setBusy(job);
    if (tryIt && liveOn && pin?.gateway && pin?.model) rate(pin.gateway, pin.model, job);     // runs beside the save: the rating does not wait for it
    try {
      await save("ai_team", withPin(team, job, pin));
      onToast?.(pin ? t("Disemat: {r} diuji terus sebentar lagi, keputusannya muncul di sini dalam kira-kira seminit (masih bertukar jika ia rosak).", "Pinned: {r} is tested live in a moment, the decision shows here in about a minute (it still switches if it is down).", { r: pin.gateway })
        : t("Auto: model dicari terus pada setiap gerbang, dan pengarah pilih robot terpantas yang sihat.", "Auto: the models are searched live on each gateway and the router picks the fastest healthy robot."), "ok");
    } catch (e) { onToast?.(e.message || String(e), "error"); } finally { setBusy(""); }
  };

  return (
    <Card className="p-4 sm:col-span-2 xl:col-span-3" data-ai-pins>
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-medium">{t("Siapa buat apa", "Who does what")}</h2>
        <span className="flex items-center gap-2 text-[11px] text-muted" data-ai-decided>
          {pending && <span className="inline-flex items-center gap-1 text-accent" data-ai-testing><Loader2 size={11} className="animate-spin" />{t("menguji model yang dipilih terus…", "testing your choice live…")}</span>}
          {state?.at ? `${t("diputuskan", "decided")} ${stampMYT(state.at)}` : t("belum diputuskan: larian seterusnya menulisnya", "not decided yet: the next run writes it")}
          <Button size="sm" variant="ghost" disabled={!canSave || !!busy} onClick={retest} title={t("Tanya gerbang sekarang dan putuskan semula", "Ask the gateways now and decide again")}><RefreshCw size={11} /> {t("Uji terus", "Test live")}</Button>
        </span>
      </div>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {jobs.map((job) => {
          const d = decisionOf(state, job);
          const pin = pinFor(team, job);
          const choices = robotsFor(cards, job);
          const pinnedCard = choices.find((c) => c.slug === pin?.gateway);
          const listed = pinnedCard ? modelsFor(pinnedCard.row, job) : [];
          const models = pin?.model && !listed.includes(pin.model) ? [pin.model, ...listed] : listed;     // a chosen model stays choosable whatever the list says
          const live = liveLines(d.live, job);
          return (
            <div key={job} className="rounded-tile bg-surface-2/60 p-3" data-ai-job={job}>
              <p className="text-xs font-medium text-muted">{JOBS[job][L]}</p>
              {job === "reader" || job === "motion" ? (
                <p className="mt-1 text-sm">{d.chosen ? <><span className="font-medium">{d.chosen.name}</span> · {d.chosen.model}</> : <span className="text-muted">{d.why || t("tiada robot teks dengan kunci", "no text robot with a key")}</span>}</p>
              ) : (
                <p className="mt-1 text-sm text-muted">{pin ? <><span className="font-medium text-ink">{pinnedCard?.name || pin.gateway}</span>{pin.model ? ` · ${pin.model}` : ""}</> : t("ikut Tetapan → Tetapan AI", "as set in Tetapan → AI settings")}</p>
              )}
              {(job === "reader" || job === "motion") && d.why && d.chosen && <p className="text-[11px] text-muted">{d.why}{d.backup ? ` · ${t("sandaran", "backup")}: ${d.backup.name || d.backup.slug}` : ""}</p>}
              {(job === "reader" || job === "motion") && d.order.length > 1 && (
                <ol className="mt-1 text-[11px] text-muted">{d.order.map((o, i) => <li key={o.slug}>{i + 1}. {o.name} · {o.model || t("Tiada", "None")} · {o.why}</li>)}</ol>
              )}
              {(job === "reader" || job === "motion") && d.skipped.map((o) => <p key={o.slug} className="mt-1 text-[11px] text-danger">{o.why}</p>)}
              {(job === "reader" || job === "motion") && live.length > 0 && (
                <ul className="mt-1 text-[11px]" data-ai-live>{live.map((l, i) => <li key={i} className={l.ok ? "text-ok" : "text-danger"}>{l.found ? t("dicari terus: ", "found live: ") : t("ujian terus: ", "live test: ")}{l.text}</li>)}</ul>
              )}
              {(job === "reader" || job === "motion") && !pin && <p className="mt-1 text-[11px] text-muted">{t("Auto: jika model sesebuah gerbang tidak menjawab, senarai modelnya dicari terus dan yang menjawab dipakai. Semat robot untuk memilih model sendiri.", "Auto: when a gateway's model does not answer, its model list is searched live and one that answers is used. Pin a robot to choose the model yourself.")}</p>}
              <div className="mt-2 flex flex-wrap items-center gap-1.5" role="radiogroup" aria-label={t("Gerbang", "Gateway")}>
                {[["", t("Auto (terpantas)", "Auto (fastest)")], ...choices.map((c) => [c.slug, c.name])].map(([slug, label]) => {
                  const on = (pin?.gateway || "") === slug;
                  return (
                    <button type="button" key={slug || "auto"} role="radio" aria-checked={on} data-robot-button={slug || "auto"}
                      disabled={!canSave || busy === job} onClick={() => setPin(job, slug ? { gateway: slug, model: "" } : null)}
                      className={`rounded-pill border px-2.5 py-1 text-[11px] font-medium transition ${on ? "border-accent bg-accent/15 text-accent" : "border-line text-muted hover:border-ink/40 hover:text-ink"} disabled:opacity-50`}>{label}</button>
                  );
                })}
              </div>
              {pin && (
                <div className="mt-2" data-ai-models={job}>
                  <div className="flex flex-wrap gap-1.5" role="radiogroup" aria-label={t("Model", "Model")}>
                    <button type="button" role="radio" aria-checked={!pin.model} data-model-button="" disabled={!canSave || busy === job}
                      onClick={() => setPin(job, { ...pin, model: "" })}
                      className={`rounded-pill border px-2.5 py-1 text-[11px] transition ${!pin.model ? "border-accent bg-accent/15 text-accent" : "border-line text-muted hover:border-ink/40 hover:text-ink"} disabled:opacity-50`}>{t("model lalai", "default model")}</button>
                    {models.map((m) => {
                      const on = pin.model === m, r = rates[`${pin.gateway}|${m}`];
                      const dot = r?.tested ? (r.stars >= 4 ? "bg-ok" : r.stars >= 3 ? "bg-warn" : "bg-danger") : "";
                      return (
                        <button type="button" key={m} role="radio" aria-checked={on} data-model-button={m} disabled={!canSave || busy === job}
                          onClick={() => setPin(job, { ...pin, model: m }, true)} title={r?.tested ? `${r.score}/100` : ""}
                          className={`inline-flex items-center gap-1 rounded-pill border px-2.5 py-1 text-[11px] transition ${on ? "border-accent bg-accent/15 font-medium text-accent" : "border-line text-muted hover:border-ink/40 hover:text-ink"} disabled:opacity-50`}>
                          {dot && <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />}{m}</button>
                      );
                    })}
                  </div>
                  <div className="mt-1.5 flex flex-wrap items-center gap-2">
                    <label className="inline-flex cursor-pointer items-center gap-1.5 text-[11px] text-muted">
                      <input type="checkbox" checked={liveOn} onChange={(e) => toggleLive(e.target.checked)} data-live-switch className="accent-[var(--accent)]" />
                      {t("uji terus bila model dipilih", "try it live when a model is picked")}{job === "image_gen" ? t(" (melukis satu gambar kecil)", " (draws one small picture)") : ""}</label>
                    {pin.model && <Button size="sm" variant="ghost" disabled={rates[`${pin.gateway}|${pin.model}`]?.busy} onClick={() => rate(pin.gateway, pin.model, job)}
                      title={job === "image_gen" ? t("Melukis satu gambar kecil sebenar (beberapa sen)", "Draws one small real picture (a few cents)") : ""}><RefreshCw size={11} /> {t("Uji & nilai", "Test & rate")}</Button>}
                    <Button size="sm" variant="ghost" disabled={!canSave || busy === job} onClick={() => setPin(job, null)}><PinOff size={12} /> {t("Auto", "Auto")}</Button>
                  </div>
                  <Rating r={rates[`${pin.gateway}|${pin.model}`]} t={t} />
                </div>
              )}
              {job !== "image_gen" && (() => {
                // the model this job runs: the pinned one, else the one the router chose; an effort belongs to that model at that gateway
                const slug = pin?.gateway || d.chosen?.slug || "";
                const model = pin ? (pin.model || team?.models?.[pin.gateway] || pinnedCard?.row?.model || "") : (d.chosen?.model || "");
                if (!slug || !model) return null;
                const now = effortOf(team, slug, model);
                const set = async (e) => {
                  if (!canSave) return;
                  setBusy(`effort-${job}`);
                  try {
                    await save("ai_team", withEffort(team, slug, model, e));
                    onToast?.(e ? t("Usaha {m}: {e}. Dipakai pada panggilan seterusnya.", "{m} effort: {e}. Used from the next call.", { m: model, e: EFFORT_WORDS[e][L] })
                      : t("Usaha {m}: ikut asal model.", "{m} effort: the model's own default.", { m: model }), "ok");
                  } catch (err) { onToast?.(err.message || String(err), "error"); } finally { setBusy(""); }
                };
                return (
                  <div className="mt-2" data-ai-effort={job}>
                    <p className="text-[11px] text-muted">{t("Usaha berfikir untuk", "Thinking effort for")} <span className="font-medium text-ink">{model}</span></p>
                    <div className="mt-1 flex flex-wrap gap-1.5" role="radiogroup" aria-label={t("Usaha", "Effort")}>
                      {[["", t("Asal", "Default")], ...EFFORTS.map((e) => [e, EFFORT_WORDS[e][L]])].map(([e, label]) => (
                        <button type="button" key={e || "default"} role="radio" aria-checked={now === e} data-effort-button={e || "default"}
                          disabled={!canSave || busy === `effort-${job}`} onClick={() => set(e)}
                          className={`rounded-pill border px-2.5 py-1 text-[11px] transition ${now === e ? "border-accent bg-accent/15 font-medium text-accent" : "border-line text-muted hover:border-ink/40 hover:text-ink"} disabled:opacity-50`}>
                          {label}</button>
                      ))}
                    </div>
                  </div>
                );
              })()}
              {!pin && <span className="mt-1 inline-flex items-center gap-1 text-[11px] text-muted"><Pin size={11} /> {t("auto", "auto")}</span>}
            </div>
          );
        })}
      </div>
      <p className="mt-3 text-[11px] text-muted">{t("Semat ialah keutamaan, bukan kunci: robot yang disemat tetapi rosak (ujian gagal, atau lebih separuh panggilan 48 jam gagal) dilangkau dan yang terpantas mengambil alih. Wanshah 3 melukis sahaja; ia tidak pernah menulis teks.",
        "A pin is a preference, not a lock: a pinned robot that is down (probe failed, or more than half its calls in 48 h failed) is skipped and the fastest takes over. Wanshah 3 only paints; it never writes text.")}</p>
      <p className="mt-1 text-[11px] text-muted" data-ai-effort-note>{t("Usaha berfikir dihantar hanya kepada model itu di gerbang itu. Jika model tidak menerimanya, ia ditanya semula tanpa usaha dan dilangkau untuk larian itu.",
        "The thinking effort is sent only to that model at that gateway. If a model does not take it, it is asked again without it and left alone for that run.")}</p>
    </Card>
  );
}
