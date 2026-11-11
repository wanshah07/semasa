import { useEffect, useRef, useState } from "react";
import { ImagePlus, Settings2, X } from "lucide-react";
import { useLang } from "../lib/i18n";
import { DEFAULT_GLASS, GROUNDS, IMAGE_KEY, IMAGE_MAX_BLUR, IMAGE_MAX_SHOW, IMAGE_MIN_SHOW, PRESETS, absoluteUrl, applyGlass, imageUrl, minOpacity, normalizeGlass, readGlass, writeGlass } from "../lib/glass";

/* "Laras kaca": the glass controls of the pasted dashboard, for the whole app (lib/glass.js says why it stays readable).
   `big`: the phone menu's version. The panel is this page's own, never a browser dialog. */
const store = () => (typeof localStorage === "undefined" ? null : localStorage);
const BASE = import.meta.env.BASE_URL || "./";
const readCustom = () => { try { return store()?.getItem(IMAGE_KEY) || ""; } catch { return ""; } };

/** A picture from this device, shrunk to at most 1600 px and saved as a JPEG data URL: small enough for this browser's
    storage, and it never leaves the device. Rejects when the file is not a picture the browser can draw. */
function shrink(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      const k = Math.min(1, 1600 / Math.max(img.width, img.height));
      const c = document.createElement("canvas");
      c.width = Math.max(1, Math.round(img.width * k)); c.height = Math.max(1, Math.round(img.height * k));
      c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
      URL.revokeObjectURL(url);
      resolve(c.toDataURL("image/jpeg", 0.8));
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("not a picture")); };
    img.src = url;
  });
}

export default function GlassControl({ big = false }) {
  const { t } = useLang();
  const [glass, setGlass] = useState(() => (store() ? readGlass(store()) : normalizeGlass(null)));
  const [open, setOpen] = useState(false);
  const [custom, setCustom] = useState(readCustom);
  const [note, setNote] = useState("");
  const box = useRef(null);
  const file = useRef(null);

  useEffect(() => { applyGlass(document.documentElement, glass, absoluteUrl(imageUrl(glass, custom, BASE), document.baseURI)); }, [glass, custom]);
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
  const addPicture = async (f) => {
    setNote("");
    if (!f) return;
    try {
      const data = await shrink(f);
      try { store()?.setItem(IMAGE_KEY, data); } catch { setNote(t("Gambar terlalu besar untuk disimpan; ia kekal sehingga tab ini ditutup.", "The picture is too large to keep; it stays until this tab closes.")); }
      setCustom(data);
      update({ image: "custom", on: true });
    } catch { setNote(t("Fail itu bukan gambar yang boleh dibuka.", "That file is not a picture that can be opened.")); }
  };
  const low = minOpacity(glass);
  const ranges = [
    ["blur", t("Kabur", "Blur"), 0, 40, 1, `${Math.round(glass.blur)} px`],
    ["opacity", t("Kelegapan", "Opacity"), low, 1, 0.01, `${Math.round(glass.opacity * 100)}%`],
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
          className={`absolute z-50 mt-2 max-h-[min(80vh,640px)] w-72 max-w-[calc(100vw-1.5rem)] overflow-y-auto rounded-card border border-line bg-surface p-4 text-ink shadow-lift ${big ? "left-0" : "right-0"}`}>
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
          <div className="mt-4">
            <p className="text-xs font-semibold text-ink">{t("Gambar latar", "Background picture")}</p>
            <div className="mt-2 grid grid-cols-4 gap-1.5" data-glass-images>
              <button type="button" onClick={() => update({ image: "" })} aria-pressed={!glass.image}
                className={`h-12 rounded-tile border text-[11px] text-ink ${!glass.image ? "border-accent" : "border-line"} hover:bg-surface-2`}>{t("Tiada", "None")}</button>
              {GROUNDS.map((g) => (
                <button key={g} type="button" onClick={() => update({ image: `ground:${g}`, on: true })} aria-pressed={glass.image === `ground:${g}`}
                  aria-label={t(`Gambar ${g.slice(2, -4)}`, `Picture ${g.slice(2, -4)}`)}
                  className={`h-12 overflow-hidden rounded-tile border-2 ${glass.image === `ground:${g}` ? "border-accent" : "border-transparent"}`}>
                  <img src={`${BASE}cards/grounds/${g}`} alt="" loading="lazy" className="h-full w-full object-cover" />
                </button>
              ))}
              {custom && (
                <button type="button" onClick={() => update({ image: "custom", on: true })} aria-pressed={glass.image === "custom"} aria-label={t("Gambar saya", "My picture")}
                  className={`h-12 overflow-hidden rounded-tile border-2 ${glass.image === "custom" ? "border-accent" : "border-transparent"}`}>
                  <img src={custom} alt="" className="h-full w-full object-cover" />
                </button>
              )}
            </div>
            <input ref={file} type="file" accept="image/*" className="hidden" data-glass-file onChange={(e) => { addPicture(e.target.files?.[0]); e.target.value = ""; }} />
            <button type="button" onClick={() => file.current?.click()} className="mt-2 flex min-h-[40px] w-full items-center justify-center gap-1.5 rounded-tile border border-line px-2 text-xs text-ink hover:bg-surface-2">
              <ImagePlus size={14} /> {custom ? t("Tukar gambar saya", "Change my picture") : t("Tambah gambar saya", "Add my picture")}
            </button>
            {glass.image && [
              ["imgBlur", t("Kabur gambar", "Picture blur"), 0, IMAGE_MAX_BLUR, 1, `${Math.round(glass.imgBlur)} px`],
              ["imgOpacity", t("Kelegapan gambar", "Picture opacity"), IMAGE_MIN_SHOW, IMAGE_MAX_SHOW, 0.01, `${Math.round(glass.imgOpacity * 100)}%`],
              ["imgSaturation", t("Warna gambar", "Picture colour"), 0, 2, 0.05, `${Math.round(glass.imgSaturation * 100)}%`],
            ].map(([key, label, min, max, step, shown]) => (
              <label key={key} className="mt-3 block text-xs text-ink" data-glass-picture-control={key}>
                <span className="flex justify-between"><span>{label}</span><output className="tabular-nums text-muted">{shown}</output></span>
                <input type="range" aria-label={label} min={min} max={max} step={step} value={glass[key]}
                  onChange={(e) => update({ [key]: Number(e.target.value) })} className="mt-1.5 w-full accent-[rgb(var(--c-accent))]" />
              </label>
            ))}
            {glass.image && <p className="mt-1.5 text-[11px] text-muted">{t("Dengan gambar, kad kekal sekurang-kurangnya {n}% legap supaya tulisan jelas. Lebih jelas gambar, lebih legap kad.", "With a picture, cards stay at least {n}% opaque so the words stay clear. The more the picture shows, the more opaque the cards.", { n: Math.round(low * 100) })}</p>}
            {note && <p className="mt-1.5 text-[11px] text-warn" role="alert">{note}</p>}
          </div>
          <button type="button" onClick={() => update(DEFAULT_GLASS)} className="mt-4 w-full rounded-tile border border-line px-2 py-2 text-xs text-ink hover:bg-surface-2">{t("Set semula", "Reset")}</button>
        </div>
      )}
    </div>
  );
}
