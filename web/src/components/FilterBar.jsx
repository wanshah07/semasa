import { Search } from "lucide-react";
import { CATEGORIES } from "../lib/format";
import CategoryBadge from "./ui/CategoryBadge";

export default function FilterBar({ query, setQuery, category, setCategory, lang, setLang, counts }) {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <label className="flex flex-1 items-center gap-2 rounded-pill border border-line bg-surface px-4 py-2 shadow-card">
          <Search size={15} className="text-muted" />
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Cari tajuk, sumber, ringkasan…"
            className="w-full bg-transparent text-sm outline-none placeholder:text-muted" />
        </label>
        <div className="flex rounded-pill bg-surface-2 p-1 text-xs">
          {[["", "Semua"], ["ms", "BM"], ["en", "EN"]].map(([v, l]) => (
            <button key={v} onClick={() => setLang(v)}
              className={`rounded-pill px-3 py-1.5 ${lang === v ? "bg-surface shadow-card text-ink" : "text-muted"}`}>{l}</button>
          ))}
        </div>
      </div>
      <div className="flex flex-wrap gap-1.5">
        <button onClick={() => setCategory("")}
          className={`rounded-pill px-3 py-1 text-[11px] font-semibold uppercase tracking-wide ${category === "" ? "bg-ink text-bg" : "bg-surface-2 text-muted"}`}>
          Semua {counts.all ? `· ${counts.all}` : ""}
        </button>
        {CATEGORIES.filter((c) => counts[c]).map((c) => (
          <CategoryBadge key={c} category={c} active={category === c} onClick={() => setCategory(category === c ? "" : c)} />
        ))}
      </div>
    </div>
  );
}
