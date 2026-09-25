import { ExternalLink, HelpCircle, Lightbulb } from "lucide-react";
import { hostOf, stampMYT, timeAgo } from "../lib/format";
import { useLang } from "../lib/i18n";
import CategoryBadge from "./ui/CategoryBadge";
import { TBODY, TD, TH, THEAD, TR, TableFrame } from "./ViewToggle";

/* The current issues as rows: the same actions as the cards, nothing cut: long titles wrap. */
export default function TrendTable({ rows, loading, onCategory, onIdea, onFaq }) {
  const { t } = useLang();
  if (loading) return <p className="p-10 text-center text-sm text-muted">{t("Memuatkan…", "Loading…")}</p>;
  if (!rows.length) {
    return <p className="rounded-card border border-dashed border-line p-10 text-center text-sm text-muted">{t("Tiada isu sepadan.", "No matching issues.")}</p>;
  }
  return (
    <TableFrame label={t("Isu semasa", "Current issues")}>
      <thead className={THEAD}>
        <tr>
          <th className={TH}>{t("Kategori", "Category")}</th>
          <th className={`${TH} w-[45%]`}>{t("Tajuk", "Title")}</th>
          <th className={TH}>{t("Sumber", "Source")}</th>
          <th className={TH}>{t("Masa", "When")}</th>
          {onIdea && <th className={TH}>{t("Tindakan", "Actions")}</th>}
        </tr>
      </thead>
      <tbody className={TBODY}>
        {rows.map((r) => {
          const when = r.published_at || r.created_at;
          return (
            <tr key={r.id} className={`${TR} hover:bg-surface-2/50`}>
              <td className={TD} data-label={t("Kategori", "Category")}><CategoryBadge category={r.category} onClick={onCategory ? () => onCategory(r.category) : undefined} /></td>
              <td className={`${TD} [overflow-wrap:anywhere]`} data-label={t("Tajuk", "Title")}>
                <a href={r.url} target="_blank" rel="noopener noreferrer" className="font-medium leading-snug hover:text-accent">
                  {r.title} <ExternalLink size={11} className="inline align-baseline text-muted" /></a>
                {r.summary && <p className="mt-1 line-clamp-2 text-[12px] text-muted">{r.summary}</p>}
              </td>
              <td className={`${TD} [overflow-wrap:anywhere] text-[12px] text-muted`} data-label={t("Sumber", "Source")}>
                {r.source}{hostOf(r.url) && !hostOf(r.url).includes("google") ? ` · ${hostOf(r.url)}` : ""}
                <span className="ml-1 uppercase">· {r.lang}</span>
                {r.summary_source === "llm" && <span className="ml-1 rounded-pill bg-accent/10 px-1.5 text-[10px] text-accent">AI</span>}
              </td>
              <td className={`${TD} whitespace-nowrap text-[12px] text-muted`} title={stampMYT(when)} data-label={t("Masa", "When")}>{timeAgo(when)}</td>
              {onIdea && (
                <td className={TD} data-label={t("Tindakan", "Actions")}>
                  <span className="flex flex-wrap items-start gap-3 md:flex-col md:gap-1.5">
                    <button type="button" onClick={() => onIdea(r)} className="inline-flex items-center gap-1 whitespace-nowrap text-xs font-medium text-accent hover:underline">
                      <Lightbulb size={12} /> {t("Jadikan idea", "Make an idea")}</button>
                    {onFaq && <button type="button" onClick={() => onFaq(r)} className="inline-flex items-center gap-1 whitespace-nowrap text-xs font-medium text-accent hover:underline">
                      <HelpCircle size={12} /> {t("Jadikan FAQ", "Make an FAQ")}</button>}
                  </span>
                </td>
              )}
            </tr>
          );
        })}
      </tbody>
    </TableFrame>
  );
}
