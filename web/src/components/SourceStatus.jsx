import { Radio } from "lucide-react";
import { useLang } from "../lib/i18n";
import { LIGHT_NAME, LIGHT_TINT, SOURCES, checkedText, lightCounts, lightOf } from "../lib/sourceLights";
import Card from "./ui/Card";
import SourceLight from "./SourceLight";

/* Papan's live status of every scrape source (Wan, 14 Nov 2026: "add status live in dashboard, make button color based on status
   and what time checked"). One tile a source, tinted by its light, with the state in words, the reason and the time it was last
   swept. It reads settings.source_lights, the same reading the tabs of Isu semasa and the watchdog e-mail use, and the settings
   are re-read every 90 seconds, so it cannot say something the watchdog does not. A press opens that source's own tab. */
export default function SourceStatus({ setting, go }) {
  const { t, lang } = useLang();
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
        </p>
      </div>
      <ul className="mt-3 grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-5">
        {SOURCES.map(([id, bm, enName, tab]) => {
          const l = lightOf(setting, id, now);
          const when = checkedText(l.checked, now, en);
          return (
            <li key={id} className="min-w-0">
              <button type="button" onClick={() => open(id, tab)} data-source={id} data-light={l.light} title={l.why}
                className={`flex h-full w-full flex-col rounded-tile p-3 text-left text-ink transition hover:brightness-95 ${LIGHT_TINT[l.light]}`}>
                <span className="flex items-center gap-1.5 text-sm font-semibold"><SourceLight light={l.light} why={l.why} /><span className="truncate">{t(bm, enName)}</span></span>
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
