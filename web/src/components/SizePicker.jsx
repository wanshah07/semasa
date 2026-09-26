import { useMemo, useState } from "react";
import { Search } from "lucide-react";
import { useLang } from "../lib/i18n";
import { PLATFORMS, SIZES, ratioLabel } from "../lib/sizes";

/* Canva's resize panel, for Semasa: platform chips, a search box, and a grid of tiles each drawing its own shape. */
export default function SizePicker({ value, onChange, only }) {
  const { t, lang } = useLang();
  const [platform, setPlatform] = useState("all");
  const [q, setQ] = useState("");
  const rows = useMemo(() => Object.entries(SIZES)
    .filter(([id]) => !only || only.includes(id))
    .filter(([, s]) => platform === "all" || s[0] === platform)
    .filter(([, s]) => !q.trim() || `${s[1]} ${s[2]}x${s[3]} ${s[2]}×${s[3]}`.toLowerCase().includes(q.trim().toLowerCase())),
  [platform, q, only]);
  const platforms = PLATFORMS.filter(([p]) => p === "all" || Object.entries(SIZES).some(([id, s]) => s[0] === p && (!only || only.includes(id))));
  return (
    <div className="min-w-0 rounded-tile border border-line p-2">
      <label className="flex items-center gap-2 rounded-pill border border-line bg-bg px-3 py-1.5 text-xs">
        <Search size={13} className="shrink-0 text-muted" />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("Cari saiz (cth: story, 1080)", "Search sizes (e.g. story, 1080)")}
          className="w-full min-w-0 bg-transparent outline-none" aria-label={t("Cari saiz", "Search sizes")} />
      </label>
      <div className="mt-2 flex gap-1 overflow-x-auto pb-1" role="tablist">
        {platforms.map(([p, bm, en]) => (
          <button type="button" key={p} role="tab" aria-selected={platform === p} onClick={() => setPlatform(p)}
            className={`shrink-0 whitespace-nowrap rounded-pill border px-2.5 py-1 text-[11px] ${platform === p ? "border-accent bg-surface-2 text-ink" : "border-line text-muted hover:text-ink"}`}>
            {lang === "en" ? en : bm}
          </button>
        ))}
      </div>
      <div className="mt-1 grid max-h-64 grid-cols-2 gap-1.5 overflow-y-auto sm:grid-cols-3">
        {rows.map(([id, [, name, w, h]]) => {
          const scale = 34 / Math.max(w, h);
          return (
            <button type="button" key={id} onClick={() => onChange(id)} aria-pressed={value === id} title={`${name} · ${w}×${h}`}
              className={`flex min-w-0 items-center gap-2 rounded-tile border p-1.5 text-left transition ${value === id ? "border-accent bg-surface-2" : "border-line hover:bg-surface-2"}`}>
              <span className="grid h-10 w-10 shrink-0 place-items-center rounded bg-surface-2">
                <span className="block rounded-[2px] border border-muted/60 bg-surface" style={{ width: Math.max(4, w * scale), height: Math.max(4, h * scale) }} />
              </span>
              <span className="min-w-0">
                <span className="block truncate text-[11px] font-semibold">{name}</span>
                <span className="block [overflow-wrap:anywhere] text-[10px] text-muted">{w}×{h} · {ratioLabel(w, h)}</span>
              </span>
            </button>
          );
        })}
        {!rows.length && <p className="col-span-full p-3 text-center text-[11px] text-muted">{t("Tiada saiz sepadan.", "No size matches.")}</p>}
      </div>
    </div>
  );
}
