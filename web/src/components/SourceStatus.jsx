import { Loader2, Radio, RefreshCw } from "lucide-react";
import { useState } from "react";
import { useLang } from "../lib/i18n";
import { LIGHT_NAME, LIGHT_TINT, SOURCES, checkedText, lightCounts, lightOf } from "../lib/sourceLights";
import Card from "./ui/Card";
import SourceLight from "./SourceLight";

/* Papan's live status of every scrape source (Wan, 14 Nov 2026: "add status live in dashboard, make button color based on status
   and what time checked"). One tile a source, tinted by its light, with the state in words, the reason and the time it was last
   swept. It reads settings.source_lights, the same reading the tabs of Isu semasa and the watchdog e-mail use, and the settings
   are re-read every 90 seconds, so it cannot say something the watchdog does not. A press opens that source's own tab. */
// the sweep part behind each tile (backend intake.PARTS): the five social tiles are ONE sweep ("community"); regulatory and
// publications are swept by the regulator watch instead (settings "watch")
const PART_OF = { reddit: "community", youtube: "community", threads: "community", facebook: "community", instagram: "community",
  folder: "folders", myra: "myra", expert: "experts" };
const WATCH_IDS = ["regulatory", "publication"];

export default function SourceStatus({ setting, go, settings, save, onToast }) {
  const { t, lang } = useLang();
  const [asking, setAsking] = useState("");
  const waiting = Boolean(settings?.sources?.force) || Boolean(settings?.watch?.force);
  /* A refresh is a "Sweep now" for that source (Wan, 26 Nov 2026: "add button to refresh sweep platform"): it saves force:true on
     the setting the worker's own trigger watches (supabase/024), with the part to sweep, and the rest between Instagram and
     Threads reads (social_pace.py) is waived because he asked. `all` sweeps every part and the regulator watch. */
  async function refresh(id) {
    if (!save || asking) return;
    setAsking(id);
    try {
      if (id === "all") {
        await save("sources", { ...(settings?.sources || {}), force: true, force_part: null });
        await save("watch", { ...(settings?.watch || {}), force: true });
      } else if (WATCH_IDS.includes(id)) {
        await save("watch", { ...(settings?.watch || {}), force: true });
      } else {
        await save("sources", { ...(settings?.sources || {}), force: true, force_part: PART_OF[id] || null });
      }
      onToast?.(t("Diminta. Pekerja menyapu dalam beberapa minit; lampu dikemas kini sendiri.",
        "Asked. The worker sweeps within a few minutes; the lights update by themselves."), "ok");
    } catch (e) {
      onToast?.(e?.message || String(e), "danger");
    } finally { setAsking(""); }
  }
  const en = lang === "en";
  const now = Date.now();
  const n = lightCounts(setting, now);
  const updated = checkedText(setting?.at, now, en);
  function open(id, tab) {
    // Isu semasa remembers its open tab on this browser (useView "isu.segment"): set it, so the press lands on the source itself
    if (tab === "isu") { try { window.localStorage.setItem("semasa.view.isu.segment", id); } catch { /* private window */ } }
    go(tab);
  }
  return (
    <Card as="section" className="p-4 sm:p-5" data-source-status-card aria-label={t("Status sumber", "Source status")}>
      <div className="flex flex-wrap items-end justify-between gap-x-4 gap-y-1">
        <h2 className="flex items-center gap-2 text-base font-semibold text-ink"><Radio size={15} /> {t("Status sumber langsung", "Live source status")}</h2>
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink/80">
          <span className="inline-flex items-center gap-1.5"><SourceLight light="green" />{n.green} {t("hidup", "live")}</span>
          <span className="inline-flex items-center gap-1.5"><SourceLight light="orange" />{n.orange} {t("siaga", "standby")}</span>
          <span className="inline-flex items-center gap-1.5"><SourceLight light="red" />{n.red} {t("tidak hidup", "unlive")}</span>
          {n.unknown > 0 && <span className="inline-flex items-center gap-1.5"><SourceLight light="unknown" />{n.unknown} {t("belum diketahui", "unknown")}</span>}
          {updated && <span className="tabular-nums text-ink/70">· {t("pengawas dikemas kini", "watchdog updated")} {updated} MYT</span>}
          {save && <button type="button" onClick={() => refresh("all")} disabled={!!asking || waiting} data-refresh="all"
            title={t("Sapu semua sumber sekarang", "Sweep every source now")}
            className="inline-flex items-center gap-1.5 rounded-pill border border-line px-2.5 py-1 text-xs font-medium text-ink hover:bg-ink/5 disabled:opacity-60">
            {asking === "all" || waiting ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
            {waiting ? t("Menunggu sapuan", "Waiting for the sweep") : t("Segar semula semua", "Refresh all")}</button>}
        </p>
      </div>
      {/* a phone gets the compact form: a chip a source (light, name, time), then only the sources that need a look, each with
          its reason. Ten full tiles were five rows of two there, most of them saying "live". */}
      <div className="mt-3 md:hidden" data-source-compact>
        <ul className="flex flex-wrap gap-1.5">
          {SOURCES.map(([id, bm, enName, tab]) => {
            const l = lightOf(setting, id, now);
            const when = checkedText(l.checked, now, en);
            return (
              <li key={id}>
                <button type="button" onClick={() => open(id, tab)} data-source-chip={id} data-light={l.light} aria-label={`${t(bm, enName)}: ${t(LIGHT_NAME[l.light][0], LIGHT_NAME[l.light][1])}. ${l.why}`}
                  className={`inline-flex min-h-[36px] items-center gap-1.5 rounded-pill px-2.5 py-1 text-xs font-medium text-ink ${LIGHT_TINT[l.light]}`}>
                  <SourceLight light={l.light} why={l.why} className="!h-2 !w-2" />{t(bm, enName)}
                  {when && <span className="text-[10px] font-normal tabular-nums text-ink/70">{when}</span>}
                </button>
              </li>
            );
          })}
        </ul>
        {SOURCES.some(([id]) => ["orange", "red"].includes(lightOf(setting, id, now).light)) ? (
          <ul className="mt-2.5 space-y-1.5">
            {SOURCES.map(([id, bm, enName]) => [id, t(bm, enName), lightOf(setting, id, now)]).filter(([, , l]) => ["orange", "red"].includes(l.light)).map(([id, name, l]) => (
              <li key={id} className="flex gap-2 text-[11px] leading-snug text-ink/80" data-source-why={id}>
                <SourceLight light={l.light} why={l.why} className="mt-1 !h-2 !w-2" />
                <span className="[overflow-wrap:anywhere]"><strong className="font-semibold text-ink">{name}</strong> · {t(LIGHT_NAME[l.light][0], LIGHT_NAME[l.light][1])}: {l.why}</span>
              </li>
            ))}
          </ul>
        ) : n.unknown === 0 && <p className="mt-2 text-[11px] text-ink/70">{t("Semua sumber hidup.", "Every source is live.")}</p>}
      </div>
      <ul className="mt-3 hidden grid-cols-2 gap-2 md:grid md:grid-cols-3 xl:grid-cols-5">
        {SOURCES.map(([id, bm, enName, tab]) => {
          const l = lightOf(setting, id, now);
          const when = checkedText(l.checked, now, en);
          return (
            <li key={id} className="relative min-w-0">
              {save && <button type="button" onClick={() => refresh(id)} disabled={!!asking || waiting} data-refresh={id}
                title={t("Sapu sumber ini sekarang", "Sweep this source now")} aria-label={`${t("Segar semula", "Refresh")} ${t(bm, enName)}`}
                className="absolute right-2 top-2 z-10 rounded-pill p-1 text-ink/70 hover:bg-ink/10 hover:text-ink disabled:opacity-50">
                {asking === id ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}</button>}
              <button type="button" onClick={() => open(id, tab)} data-source={id} data-light={l.light} title={l.why}
                className={`flex h-full w-full flex-col rounded-tile p-3 text-left text-ink transition hover:brightness-95 ${LIGHT_TINT[l.light]}`}>
                <span className="flex items-center gap-1.5 pr-6 text-sm font-semibold"><SourceLight light={l.light} why={l.why} /><span className="truncate">{t(bm, enName)}</span></span>
                <span className="mt-1 text-[11px] font-medium">{t(LIGHT_NAME[l.light][0], LIGHT_NAME[l.light][1])}{when ? <span className="font-normal tabular-nums text-ink/70"> · {t("disemak", "checked")} {when}</span> : null}</span>
                <span className="mt-0.5 line-clamp-2 text-[11px] leading-snug text-ink/75 [overflow-wrap:anywhere]">{l.why}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}
