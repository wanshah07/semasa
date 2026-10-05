import { useEffect, useMemo, useState } from "react";
import { Check, ImageIcon, Loader2, Palette, Plus, Star, Trash2 } from "lucide-react";
import { LOOKS, STUDIO_LOOKS, ensureFonts, renderSlides, setLogo } from "../lib/cards/studio";
import { GROUNDS, MASCOTS, TEMPLATES } from "../lib/cards/library";
import { newDesignId, packDesign, resolveLook, useDesigns } from "../lib/designs";
import { buildDesignFromReference } from "../lib/designFromReference";
import ImageLightbox, { useLightbox } from "./ImageLightbox";
import { useLang } from "../lib/i18n";
import Button from "./ui/Button";
import { Input, Label, Select } from "./ui/Field";

/* My designs (Wan, 4 Oct 2026: "create a default design for carousel, poster and single card, like ERA, Photo, Grid and Semasa.
   I need not fill any text ... don't make it complicated"). A design is chosen once, with NO words:
     1. a family (Grid, Info ERA or Photo)      2. two colours (or the family's own)      3. a background (or none)
     4. which layout the cover, the middle slides, the closing slide and a single card or poster take (Auto = the family decides)
   and shown at once on sample words. Saved, it can be picked wherever a look is picked, or made the DEFAULT: then every draft
   written from an idea is drawn in it and the idea's words fill the layout by themselves. */

const BASE = `${import.meta.env.BASE_URL}cards/`;
const SAMPLE = [
  { title: "Tajuk *anda* di sini", points: ["Satu baris sokongan di bawah tajuk."] },
  { title: "Satu fakta satu slaid", points: ["Ringkas dan bersumber.", "Satu poin lagi."] },
  { title: "Intipati terakhir", points: ["Kesimpulan yang ringkas."] },
];
const PLACES = [["cover", "Kulit", "Cover"], ["middle", "Slaid tengah", "Middle slides"], ["closing", "Penutup", "Closing slide"],
  ["single", "Kad tunggal / poster", "Single card / poster"]];
const BLANK = { id: "", name: "", look: "grid", cover: "", middle: "", closing: "", single: "", accent: "", paper: "", bg: "", scrim: "", mascot: "", eyebrow: "" };

/** Four sample pictures of a design: cover, middle, closing (one carousel) and a single card. Debounced; never leaves the page. */
function useSamples(draft, enabled) {
  const [state, setState] = useState({ pics: [], busy: false, error: "" });
  const key = JSON.stringify(draft);
  useEffect(() => {
    if (!enabled) return undefined;
    let live = true;
    setState((s) => ({ ...s, busy: true }));
    const timer = setTimeout(async () => {
      try {
        setLogo(`${BASE}logo.png`);
        await ensureFonts(BASE);
        const pack = packDesign(draft);
        const g = draft.bg && draft.bg.startsWith("lib:") ? GROUNDS.find((x) => `lib:${x.k}` === draft.bg) : null;
        const photoFallback = draft.look === "photo" && !g ? GROUNDS[0] : null;      // Photo is drawn on a picture: show one
        const opts = { stream: "regulab", eyebrow: draft.eyebrow || "Kosmetik", design: pack, bg: (g || photoFallback)?.url || "",
          mascots: MASCOTS.map((m) => ({ k: m.k, url: m.url })) };
        const set = await renderSlides(SAMPLE, opts);
        const one = await renderSlides(SAMPLE.slice(0, 1), opts);
        if (live) setState({ pics: [set[0], set[1], set[2], one[0]], busy: false, error: "" });
      } catch (e) {
        if (live) setState({ pics: [], busy: false, error: e?.message || String(e) });
      }
    }, 350);
    return () => { live = false; clearTimeout(timer); };
  }, [key, enabled]); // eslint-disable-line react-hooks/exhaustive-deps
  return state;
}

function Strip({ pics, busy, error, placeLabel, onOpen = null }) {
  if (error) return <p className="text-[12px] text-danger">{error}</p>;
  return (
    <div className="flex gap-2 overflow-x-auto pb-1" style={{ scrollSnapType: "x mandatory" }}>
      {PLACES.map(([k, bm, en], i) => (
        <figure key={k} className="w-28 shrink-0 snap-start sm:w-32">
          <button type="button" disabled={!pics[i]?.url || !onOpen} onClick={() => onOpen && onOpen(i)} title={placeLabel("Klik untuk zum", "Click to zoom")}
            className="relative block w-full cursor-zoom-in overflow-hidden rounded-tile border border-line bg-surface-2" style={{ aspectRatio: "1 / 1" }}>
            {pics[i]?.url ? <img src={pics[i].url} alt={placeLabel(bm, en)} className="h-full w-full object-cover" />
              : <span className="absolute inset-0 grid place-items-center text-muted">{busy ? <Loader2 size={14} className="animate-spin" /> : "·"}</span>}
          </button>
          <figcaption className="mt-0.5 truncate text-[10.5px] text-muted">{placeLabel(bm, en)}</figcaption>
        </figure>
      ))}
    </div>
  );
}

function Editor({ initial, onSave, onCancel, isDefault }) {
  const { t, lang } = useLang();
  const [d, setD] = useState(initial);
  const [asDefault, setAsDefault] = useState(isDefault);
  const [busy, setBusy] = useState(false);
  const set = (patch) => setD((x) => ({ ...x, ...patch }));
  const family = d.look[0];
  const tplOptions = useMemo(() => [["", t("Auto (keluarga memilih)", "Auto (the family chooses)")],
    ...TEMPLATES.filter((x) => x.k[0] === family).map((x) => [x.k, lang === "bm" ? x.name.split(" · ")[1] : x.en.split(" · ")[1]])], [family, lang]); // eslint-disable-line react-hooks/exhaustive-deps
  const samples = useSamples(d, true);
  const box = useLightbox(samples.pics.filter((p) => p?.url).map((p, i) => ({ url: p.url, title: t(PLACES[i][1], PLACES[i][2]) })));
  const named = d.name.trim().length >= 2;
  const pal = (k, auto) => (
    <label className="block min-w-0"><Label>{k === "accent" ? t("Warna aksen", "Accent colour") : t("Warna kertas", "Paper colour")}</Label>
      <div className="flex items-center gap-2">
        <input type="color" value={d[k] || auto} onChange={(e) => set({ [k]: e.target.value })} aria-label={k}
          className="h-9 w-12 cursor-pointer rounded border border-line bg-transparent p-0.5" />
        <span className="text-[11px] text-muted">{d[k] || t("warna keluarga", "the family's own")}</span>
        {d[k] && <button type="button" onClick={() => set({ [k]: "" })} className="text-[11px] text-accent hover:underline">{t("Auto", "Auto")}</button>}
      </div>
    </label>
  );
  return (
    <div className="space-y-3 rounded-tile border border-line p-3">
      <label className="block"><Label>{t("Nama reka bentuk", "Design name")}</Label>
        <Input value={d.name} maxLength={40} onChange={(e) => set({ name: e.target.value })} placeholder={t("Cth: Biru NPRA", "E.g. NPRA blue")} /></label>
      <div>
        <Label>{t("Bermula daripada", "Start from")}</Label>
        <div role="radiogroup" className="grid grid-cols-3 gap-2">
          {LOOKS.filter((l) => STUDIO_LOOKS.includes(l.k)).map((l) => (
            <button key={l.k} type="button" role="radio" aria-checked={d.look === l.k}
              onClick={() => set({ look: l.k, cover: "", middle: "", closing: "", single: "" })}
              className={`rounded-tile border px-2 py-1.5 text-left text-[12px] ${d.look === l.k ? "border-accent ring-2 ring-accent/30" : "border-line hover:border-ink/30"}`}>
              <span className="block font-semibold">{lang === "bm" ? l.bm : l.en}</span>
            </button>
          ))}
        </div>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        {pal("accent", d.look === "era" ? "#d8232a" : "#e24b1a")}
        {pal("paper", d.look === "era" ? "#efe8dc" : "#f7f2e8")}
        <label className="block min-w-0"><Label hint={d.look === "photo" ? t("Foto perlu gambar; satu dipilih daripada foto Wan", "Photo needs a picture; pick one of Wan's photos") : ""}>
          {t("Latar", "Background")}</Label>
          <Select value={d.bg} onChange={(v) => set({ bg: v })} className="w-full"
            options={[["", t("Tiada (kertas keluarga)", "None (the family's paper)")], ...GROUNDS.map((g) => [`lib:${g.k}`, g.name])]} /></label>
        {d.bg && <label className="block min-w-0"><Label>{t("Tutupan atas gambar", "How much the words cover it")}</Label>
          <Select value={d.scrim} onChange={(v) => set({ scrim: v })} className="w-full"
            options={[["", t("Auto (gambar cerah = tiada)", "Auto (a light picture gets none)")], ["none", t("Tiada", "None")], ["light", t("Ringan", "Light")],
              ["medium", t("Sederhana", "Medium")], ["heavy", t("Tebal", "Heavy")]]} /></label>}
        <label className="block min-w-0"><Label>{t("Maskot", "Mascot")}</Label>
          <Select value={d.mascot} onChange={(v) => set({ mascot: v })} className="w-full"
            options={[["", t("Auto (ikut templat)", "Auto (by template)")], ["none", t("Tiada", "None")], ...MASCOTS.map((m) => [m.k, lang === "bm" ? m.name : m.en])]} /></label>
        <label className="block min-w-0"><Label hint={t("pilihan · label kecil di atas", "optional · the small label on top")}>{t("Label", "Label")}</Label>
          <Input value={d.eyebrow} maxLength={40} onChange={(e) => set({ eyebrow: e.target.value })} placeholder={t("Cth: Kosmetik", "E.g. Cosmetics")} /></label>
      </div>
      <div>
        <Label hint={t("Auto = keluarga memilih ikut isi", "Auto = the family chooses by the words")}>{t("Susun atur setiap tempat", "Layout for each place")}</Label>
        <div className="grid gap-2 sm:grid-cols-2">
          {PLACES.map(([k, bm, en]) => (
            <label key={k} className="block min-w-0"><span className="text-[11px] text-muted">{t(bm, en)}</span>
              <Select value={d[k]} onChange={(v) => set({ [k]: v })} options={tplOptions} className="w-full" aria-label={t(bm, en)} /></label>
          ))}
        </div>
      </div>
      <div>
        <p className="mb-1 text-[11px] text-muted">{t("Contoh dengan perkataan palsu sahaja: perkataan sebenar masuk bila draf dibuat.",
          "Shown on sample words only: the real words go in when a draft is made.")}</p>
        <Strip {...samples} placeLabel={(bm, en) => t(bm, en)} onOpen={box.open} />
        <ImageLightbox {...box.props} />
      </div>
      <label className="flex cursor-pointer items-center gap-2 text-[12px]">
        <input type="checkbox" checked={asDefault} onChange={(e) => setAsDefault(e.target.checked)} className="accent-[var(--accent)]" />
        {t("Guna untuk draf baharu (bila idea tidak pilih reka bentuk)", "Use for new drafts (when the idea picked no design)")}
      </label>
      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" size="sm" onClick={onCancel}>{t("Batal", "Cancel")}</Button>
        <Button type="button" size="sm" disabled={!named || busy} onClick={async () => { setBusy(true); try { await onSave(d, asDefault); } finally { setBusy(false); } }}>
          {busy ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />} {t("Simpan reka bentuk", "Save design")}</Button>
      </div>
    </div>
  );
}

/* A design made FROM A REFERENCE, the way ERA, Grid and Photo were made (Wan, 4 Oct 2026): upload a reference picture once. The AI reads
   its layout (where the headline, the points, the label, the source, the pictures and the logo go; colours, type, shapes), the colours
   are then measured from the picture's own pixels, and the layout is saved with NO words. Every draft pours its own words into it. */
const PLACE_FILES = [["cover", "Kulit", "Cover"], ["middle", "Slaid tengah", "Middle slides"], ["closing", "Penutup", "Closing slide"], ["single", "Kad tunggal / poster", "Single card / poster"]];

function RefEditor({ initial, onSave, onCancel, isDefault, user }) {
  const { t } = useLang();
  const [d, setD] = useState(initial);
  const [asDefault, setAsDefault] = useState(isDefault !== false);        // a new design is the default for new drafts unless unticked
  const [busy, setBusy] = useState("");                                 // "" | place being read | "save"
  const [steps, setSteps] = useState([]);
  const [built, setBuilt] = useState(null);                             // { score, first, image, render } of the last read
  const [error, setError] = useState("");
  const layouts = d.layouts || {};
  const hasAny = Object.keys(layouts).length > 0;
  const samples = useSamples(d, hasAny);
  const named = d.name.trim().length >= 2 && hasAny;
  const items = [...samples.pics.filter((p) => p?.url).map((p, i) => ({ url: p.url, title: t(PLACES[i][1], PLACES[i][2]) })),
    ...(built ? [{ url: built.image, title: t("Rujukan", "Reference") }, { url: built.render, title: t("Lukisan kita", "Our drawing") }] : [])];
  const box = useLightbox(items);
  async function pick(place, file) {
    if (!file) return;
    setBusy(place); setError(""); setSteps([]);
    try {
      const r = await buildDesignFromReference(file, { stream: "regulab", t, onStep: (x) => setSteps((s) => [...s, x].slice(-8)) });
      setD((x) => ({ ...x, name: x.name || file.name.replace(/\.[^.]+$/, "").slice(0, 40), layouts: { ...(x.layouts || {}), [place]: r.layout },
        ...(place === "main" ? { bg_prompt: r.bgPrompt } : {}) }));
      if (place === "main") setBuilt({ score: r.score, first: r.first, image: r.image, render: r.render, removed: r.removed });
    } catch (e) { setError(e?.message || String(e)); } finally { setBusy(""); }
  }
  async function save() {
    setBusy("save"); setError("");
    try {
      await onSave({ ...d, look: "grid", kind: "ref" }, asDefault);
    } catch (e) { setError(`${t("Gagal disimpan", "Could not save")}: ${e?.message || String(e)}`); } finally { setBusy(""); }
  }
  const fileBtn = (place, label, req) => (
    <label key={place} className={`flex min-w-0 cursor-pointer items-center gap-2 rounded-tile border px-3 py-2 text-[12px] ${layouts[place] ? "border-accent bg-accent/5" : "border-line hover:border-ink/30"}`}>
      {busy === place ? <Loader2 size={14} className="animate-spin" /> : layouts[place] ? <Check size={14} className="text-accent" /> : <ImageIcon size={14} className="text-muted" />}
      <span className="min-w-0 flex-1 truncate">{label}{req && <span className="text-muted"> · {t("wajib", "required")}</span>}</span>
      <span className="text-accent">{layouts[place] ? t("Tukar", "Replace") : t("Pilih gambar", "Choose picture")}</span>
      <input type="file" accept="image/png,image/jpeg,image/webp" className="sr-only" disabled={!!busy}
        onChange={(e) => { pick(place, e.target.files?.[0]); e.target.value = ""; }} aria-label={label} />
    </label>
  );
  return (
    <div className="space-y-3 rounded-tile border border-line p-3">
      <label className="block"><Label>{t("Nama reka bentuk", "Design name")}</Label>
        <Input value={d.name} maxLength={40} onChange={(e) => setD({ ...d, name: e.target.value })} placeholder={t("Cth: Poster NPRA", "E.g. NPRA poster")} /></label>
      <div>
        <Label hint={t("AI membaca susun atur, melukis rekaan BAHARU dan membandingkan dengan rujukan (sehingga 3 pusingan). Gambar rujukan tidak digunakan semula: setiap draf mendapat latar baharu yang dijana AI.", "The AI reads the layout, draws NEW artwork and compares it with the reference (up to 3 passes). The reference picture is never reused: every draft gets a new AI-generated background.")}>
          {t("Gambar rujukan", "Reference picture")}</Label>
        {fileBtn("main", t("Untuk semua tempat", "For every place"), true)}
        {busy && busy !== "save" && steps.length > 0 && (
          <ul className="mt-1.5 space-y-0.5 text-[11px] text-muted">{steps.map((x, i) => <li key={i} className={i === steps.length - 1 ? "text-ink" : ""}>{i === steps.length - 1 ? "▸ " : "✓ "}{x}</li>)}</ul>
        )}
        <details className="mt-2">
          <summary className="cursor-pointer text-[12px] text-accent">{t("Rujukan berlainan untuk tempat tertentu (pilihan)", "A different reference for one place (optional)")}</summary>
          <div className="mt-2 grid gap-2 sm:grid-cols-2">{PLACE_FILES.map(([k, bm, en]) => fileBtn(k, t(bm, en), false))}</div>
        </details>
        {error && <p className="mt-1.5 rounded-tile bg-danger/10 p-2 [overflow-wrap:anywhere] text-[12px] text-danger" role="alert">{error}</p>}
      </div>
      {built && (
        <div>
          <p className="text-[12px] font-medium">{t("Padanan dengan rujukan", "Match to the reference")}: <b className={built.score >= 85 ? "text-ok" : built.score >= 70 ? "text-warn" : "text-danger"}>{Math.round(built.score)}%</b>
            {built.first != null && Math.round(built.first) !== Math.round(built.score) && <span className="font-normal text-muted"> ({t("bermula", "from")} {Math.round(built.first)}%)</span>}</p>
          <div className="mt-1 flex gap-2">
            {[[built.image, t("Rujukan", "Reference"), samples.pics.filter((p) => p?.url).length], [built.render, t("Lukisan kita (perkataan contoh)", "Our drawing (sample words)"), samples.pics.filter((p) => p?.url).length + 1]].map(([u, label, at]) => (
              <figure key={label} className="w-32 shrink-0 sm:w-40">
                <button type="button" onClick={() => box.open(at)} className="block w-full cursor-zoom-in overflow-hidden rounded-tile border border-line bg-surface-2"><img src={u} alt={label} className="w-full" /></button>
                <figcaption className="mt-0.5 text-[10.5px] text-muted">{label}</figcaption>
              </figure>
            ))}
          </div>
          {built.removed.length > 0 && <p className="mt-1 text-[11px] text-muted">{t("Tidak disalin (jenama, wajah, CTA):", "Not copied (brands, faces, CTA):")} {built.removed.slice(0, 4).join("; ")}.</p>}
        </div>
      )}
      {hasAny && (
        <div>
          <p className="mb-1 text-[11px] text-muted">{t("Contoh pada saiz kad dengan perkataan palsu: perkataan sebenar masuk bila draf dibuat. Klik untuk zum.", "Shown at card size on sample words: the real words go in when a draft is made. Click to zoom.")}</p>
          <Strip {...samples} placeLabel={(bm, en) => t(bm, en)} onOpen={box.open} />
        </div>
      )}
      <ImageLightbox {...box.props} />
      <label className="flex cursor-pointer items-center gap-2 text-[12px]">
        <input type="checkbox" checked={asDefault} onChange={(e) => setAsDefault(e.target.checked)} className="accent-[var(--accent)]" />
        {t("Guna untuk draf baharu (bila idea tidak pilih reka bentuk)", "Use for new drafts (when the idea picked no design)")}
      </label>
      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" size="sm" onClick={onCancel}>{t("Batal", "Cancel")}</Button>
        <Button type="button" size="sm" disabled={!named || !!busy} onClick={save}>
          {busy === "save" ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />} {t("Simpan reka bentuk", "Save design")}</Button>
      </div>
      {!named && <p className="text-right text-[11px] text-muted">{!hasAny ? t("Pilih gambar rujukan dahulu.", "Choose the reference picture first.") : t("Beri nama (sekurang-kurangnya 2 huruf).", "Give it a name (at least 2 letters).")}</p>}
    </div>
  );
}

export default function MyDesigns({ onToast = () => {}, user = null }) {
  const { t } = useLang();
  const { designs, defaultId, ready, saveDesigns, setDefault } = useDesigns();
  const [editing, setEditing] = useState(null);                       // a design (new or existing) being edited, or null
  const [open, setOpen] = useState(true);                          // open by default: the button to make a design must be seen
  useEffect(() => {                                                 // "Add my design" in the slide-design picker opens and shows this section
    const show = () => { setOpen(true); document.getElementById("my-designs")?.scrollIntoView({ behavior: "smooth", block: "start" }); };
    window.addEventListener("semasa:my-designs", show);
    return () => window.removeEventListener("semasa:my-designs", show);
  }, []);
  const fail = (e) => onToast(e?.message || String(e), "danger");

  async function save(d, asDefault) {
    const id = d.id || newDesignId();
    const next = { ...d, id, name: d.name.trim() };
    const list = designs.some((x) => x.id === id) ? designs.map((x) => (x.id === id ? next : x)) : [...designs, next];
    try {
      await saveDesigns(list);
      if (asDefault && defaultId !== id) await setDefault(id);
      if (!asDefault && defaultId === id) await setDefault("");
      onToast(t("Reka bentuk disimpan.", "Design saved."), "ok");
      setEditing(null);
    } catch (e) { fail(e); }
  }
  async function remove(id) {
    try {
      await saveDesigns(designs.filter((x) => x.id !== id));
      if (defaultId === id) await setDefault("");
      onToast(t("Reka bentuk dibuang. Draf yang sudah dilukis tidak berubah.", "Design removed. Drafts already drawn do not change."), "ok");
    } catch (e) { fail(e); }
  }

  return (
    <section id="my-designs" className="mb-6 scroll-mt-20 rounded-card border border-line bg-surface p-4 sm:p-5">
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} className="flex w-full items-center gap-2 text-left">
        <Palette size={16} />
        <span className="min-w-0 flex-1">
          <span className="block text-base font-semibold">{t("Reka bentuk saya", "My designs")}</span>
          <span className="block text-[12px] text-muted">{t("Cipta sekali tanpa perkataan. Draf daripada idea mengisi susun atur itu sendiri: carousel, poster dan kad tunggal.",
            "Make one once, with no words. Drafts from ideas fill the layout by themselves: carousel, poster and single card.")}</span>
        </span>
        <span className="text-[11px] text-muted">{designs.length}</span>
      </button>
      {open && (
        <div className="mt-3 space-y-3">
          {!ready && <p className="rounded-tile bg-warn/10 p-2.5 text-[12px] text-warn">{t("Belum disediakan: jalankan supabase/027_my_designs.sql sekali dalam Supabase.",
            "Not set up yet: run supabase/027_my_designs.sql once in Supabase.")}</p>}
          {designs.map((d) => {
            const r = resolveLook(`d:${d.id}`, designs);
            return (
              <div key={d.id} className="flex flex-wrap items-center gap-2 rounded-tile border border-line px-3 py-2">
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">{d.name}{defaultId === d.id && <span className="ml-2 rounded-pill bg-accent/15 px-2 py-0.5 text-[10px] text-accent">{t("lalai", "default")}</span>}</span>
                  <span className="block text-[11px] text-muted">{d.kind === "ref" ? `${t("daripada rujukan", "from a reference")} · ${Object.keys(d.layouts || {}).length} ${t("susun atur", "layout(s)")}` : `${r.look} · ${[d.cover, d.middle, d.closing, d.single].filter(Boolean).length || t("auto", "auto")} ${t("susun atur dipilih", "layouts chosen")}`}
                    {d.accent && <span className="ml-2 inline-block h-2.5 w-2.5 rounded-full align-middle" style={{ background: d.accent }} />}
                    {d.paper && <span className="ml-1 inline-block h-2.5 w-2.5 rounded-full border border-line align-middle" style={{ background: d.paper }} />}</span>
                </span>
                {defaultId !== d.id && ready && <button type="button" onClick={() => setDefault(d.id).catch(fail)} className="inline-flex items-center gap-1 text-[11px] text-accent hover:underline"><Star size={11} /> {t("Jadikan lalai", "Make default")}</button>}
                <button type="button" onClick={() => setEditing(d)} className="text-[11px] text-accent hover:underline">{t("Ubah", "Edit")}</button>
                <button type="button" onClick={() => remove(d.id)} aria-label={t("Buang", "Remove")} className="text-muted hover:text-danger"><Trash2 size={13} /></button>
              </div>
            );
          })}
          {editing ? (
            editing.kind === "ref"
              ? <RefEditor key={editing.id || "newref"} user={user} initial={{ ...BLANK, ...editing }} isDefault={editing.id ? defaultId === editing.id : true} onSave={save} onCancel={() => setEditing(null)} />
              : <Editor key={editing.id || "new"} initial={{ ...BLANK, ...editing }} isDefault={!!editing.id && defaultId === editing.id} onSave={save} onCancel={() => setEditing(null)} />
          ) : (
            <div className="flex flex-wrap gap-2">
              <Button type="button" size="sm" disabled={!ready} onClick={() => setEditing({ ...BLANK, kind: "ref", layouts: {} })}>
                <ImageIcon size={12} /> {t("Reka bentuk baharu daripada gambar rujukan", "New design from a reference picture")}</Button>
              <Button type="button" size="sm" variant="soft" disabled={!ready} onClick={() => setEditing({ ...BLANK })}>
                <Plus size={12} /> {t("Mudah: pilih keluarga dan warna", "Simple: pick a family and colours")}</Button>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
