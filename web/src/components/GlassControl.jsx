import { useEffect, useRef, useState } from "react";
import { Settings2, X } from "lucide-react";
import { useLang } from "../lib/i18n";
import { DEFAULT_GLASS, MIN_OPACITY, PRESETS, applyGlass, normalizeGlass, readGlass, writeGlass } from "../lib/glass";

/* "Laras kaca": the glass controls of the pasted dashboard, for the whole app (lib/glass.js says why it stays readable).
   `big`: the phone menu's version. The panel is this page's own, never a browser dialog. */
const store = () => (typeof localStorage === "undefined" ? null : localStorage);

export default function GlassControl({ big = false }) {
  const { t } = useLang();
  const [glass, setGlass] = useState(() => (store() ? readGlass(store()) : normalizeGlass(null)));
  const [open, setOpen] = useState(false);
  const box = useRef(null);

  useEffect(() => { applyGlass(document.documentElement, glass); }, [glass]);
  useEffect(() => {
    if (!open) return undefined;
    const away = (e) => { if (box.current && !box.current.contains(e.target)) setOpen(false); };
    const esc = (e) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", away); document.removeEventListener("keydown", esc); };
  }, [open]);

  const update = (patch) => setGlass((g) => {
    const next = normalizeGlass({ ...g, ...patch });
    if (store()) writeGlass(store(), next);
    return next;
  });
  const ranges = [
    ["blur", t("Kabur", "Blur"), 0, 40, 1, `${Math.round(glass.blur)} px`],
    ["opacity", t("Kelegapan", "Opacity"), MIN_OPACITY, 1, 0.01, `${Math.round(glass.opacity * 100)}%`],
    ["saturation", t("Ketepuan", "Saturation"), 0.5, 2, 0.05, `${Math.round(glass.saturation * 100)}%`],
    ["edge", t("Cahaya tepi", "Edge light"), 0, 1, 0.05, `${Math.round(glass.edge * 100)}%`],
  ];
  const presets = [["clear", t("Jernih", "Clear")], ["frosted", t("Beku", "Frosted")], ["solid", t("Pejal", "Solid")]];

  return (
    <div ref={box} className={`relative ${big ? "w-full" : ""}`}>
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-haspopup="dialog" data-glass-open
        title={t("Laras kaca", "Adjust glass")}
        className={`flex items-center gap-1.5 rounded-pill border border-line bg-surface text-ink transition hover:bg-surface-2 ${big ? "min-h-[44px] w-full px-4 text-sm" : "px-2.5 py-1.5 text-xs"}`}>
        <Settings2 size={13} /> <span className={big ? "" : "hidden 2xl:inline"}>{t("Laras kaca", "Adjust glass")}</span>
      </button>
      {open && (
        <div role="dialog" aria-label={t("Rupa kaca", "Glass appearance")} data-glass-panel
          className={`absolute z-50 mt-2 w-72 rounded-card border border-line bg-surface p-4 text-ink shadow-lift ${big ? "left-0" : "right-0"}`}>
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-ink">{t("Rupa kaca", "Glass appearance")}</h2>
            <button type="button" onClick={() => setOpen(false)} aria-label={t("Tutup", "Close")} className="grid h-8 w-8 place-items-center rounded-full text-muted hover:bg-surface-2 hover:text-ink"><X size={15} /></button>
          </div>
          <p className="mt-1 text-xs text-muted">{t("Untuk kad di setiap halaman. Disimpan dalam pelayar ini sahaja.", "For the cards on every page. Kept in this browser only.")}</p>
          <label className="mt-3 flex items-center justify-between gap-3 text-sm text-ink">
            {t("Kesan kaca", "Glass effect")}
            <input type="checkbox" checked={glass.on} onChange={(e) => update({ on: e.target.checked })} className="h-4 w-4 accent-[rgb(var(--c-accent))]" data-glass-toggle />
          </label>
          <div className="mt-3 flex gap-1.5">
            {presets.map(([id, label]) => (
              <button key={id} type="button" onClick={() => update({ ...PRESETS[id], on: true })}
                className="flex-1 rounded-tile border border-line px-2 py-1.5 text-xs text-ink hover:bg-surface-2">{label}</button>
            ))}
          </div>
          {ranges.map(([key, label, min, max, step, shown]) => (
            <label key={key} className={`mt-3 block text-xs ${glass.on ? "text-ink" : "text-muted"}`}>
              <span className="flex justify-between"><span>{label}</span><output className="tabular-nums text-muted">{shown}</output></span>
              <input type="range" aria-label={label} min={min} max={max} step={step} value={glass[key]} disabled={!glass.on}
                onChange={(e) => update({ [key]: Number(e.target.value) })} className="mt-1.5 w-full accent-[rgb(var(--c-accent))]" />
            </label>
          ))}
          <button type="button" onClick={() => update(DEFAULT_GLASS)} className="mt-4 w-full rounded-tile border border-line px-2 py-2 text-xs text-ink hover:bg-surface-2">{t("Set semula", "Reset")}</button>
        </div>
      )}
    </div>
  );
}
