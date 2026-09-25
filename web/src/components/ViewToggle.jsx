import { useState } from "react";
import { LayoutGrid, Table2 } from "lucide-react";
import { useLang } from "../lib/i18n";

/** Card or table, remembered per list in this browser only (a convenience: a blocked storage just forgets). */
export function useView(key, fallback = "card") {
  const id = `semasa.view.${key}`;
  const [view, setView] = useState(() => {
    try { return window.localStorage.getItem(id) || fallback; } catch { return fallback; }
  });
  const set = (v) => {
    setView(v);
    try { window.localStorage.setItem(id, v); } catch { /* private window: keep it for this visit */ }
  };
  return [view, set];
}

export default function ViewToggle({ view, setView }) {
  const { t } = useLang();
  return (
    <div role="radiogroup" aria-label={t("Paparan", "View")} className="inline-flex rounded-pill bg-surface-2 p-1 text-xs">
      {[["card", LayoutGrid, t("Kad", "Cards")], ["table", Table2, t("Jadual", "Table")]].map(([v, Icon, l]) => (
        <button type="button" key={v} role="radio" aria-checked={view === v} onClick={() => setView(v)}
          className={`inline-flex items-center gap-1.5 rounded-pill px-3 py-1.5 ${view === v ? "bg-surface text-ink shadow-card" : "text-muted"}`}>
          <Icon size={13} /> {l}
        </button>
      ))}
    </div>
  );
}

/** A table that never pushes the page sideways and never cuts a column off: from md up it is a table; on a phone
    every row stacks into a block, each cell under its own label (data-label), so nothing needs a sideways scroll. */
export function TableFrame({ children, label }) {
  return (
    <div className="max-w-full rounded-card border border-line bg-surface shadow-card md:overflow-x-auto" role="region" aria-label={label}>
      <table className="block w-full text-left text-sm md:table">{children}</table>
    </div>
  );
}

export const THEAD = "hidden md:table-header-group";
export const TBODY = "block md:table-row-group";
export const TR = "block border-b border-line/60 px-2 py-2 last:border-b-0 md:table-row md:p-0";
export const TH = "border-b border-line px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-muted";
export const TD = "block min-w-0 px-2 py-1 md:table-cell md:border-b md:border-line/60 md:px-3 md:py-2 md:align-top "
  + "max-md:before:mb-0.5 max-md:before:block max-md:before:text-[10px] max-md:before:font-semibold max-md:before:uppercase "
  + "max-md:before:tracking-wide max-md:before:text-muted max-md:before:content-[attr(data-label)]";
