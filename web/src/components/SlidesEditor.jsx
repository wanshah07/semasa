import { useState } from "react";
import { ArrowDown, ArrowUp, Expand, ImageIcon, Layers, Loader2, Minimize2, Paintbrush, Plus, Trash2 } from "lucide-react";
import { SLIDE_WORDS, isPromo, normaliseSlides, slidesKey } from "../lib/compliance";
import { cardFromCaption, slidesFromCaption } from "../lib/cards/fromCaption";
import { useLang } from "../lib/i18n";
import { LOOKS, isStudioLook, takesMascot } from "../lib/cards/studio";
import { MASCOTS, TEMPLATES, noteLabel, templateOf } from "../lib/cards/library";
import BackgroundPicker from "./BackgroundPicker";
import ImageLightbox, { useLightbox } from "./ImageLightbox";
import LookPicker from "./LookPicker";
import TemplateCatalogue from "./TemplateCatalogue";
import Button from "./ui/Button";
import { Input, Label, Select, TextArea } from "./ui/Field";

export const MAX_SLIDES = 10;

/* A slide's own design (Studio's per-slide editor): the words its template draws besides the headline and the points,
   and how it is drawn. Empty = the look decides. */
const DESIGN = [...Object.keys(SLIDE_WORDS), "template", "scrim", "bg", "mascot", "type_size", "font", "mascot_pos", "mascot_size"];
/* The compact-text preset (Wan, 3 Oct 2026): smaller type in the narrower face, and a smaller character. */
const COMPACT = { type_size: "80", font: "sans", mascot_size: "80" };
const STYLE_KEYS = ["type_size", "font", "mascot_pos", "mascot_size"];

/** Editor rows <-> stored slides. The editor keeps empty rows while typing; the scan and the save
    see normaliseSlides() of them, which drops empties exactly as the worker does. */
export const toRows = (slides) => (Array.isArray(slides) ? slides : []).map((s) => ({
  title: String(s?.title ?? ""), points: (Array.isArray(s?.points) ? s.points : []).join("\n"),
  ...Object.fromEntries(DESIGN.map((k) => [k, String(s?.[k] ?? "")])),
}));
export const fromRows = (rows) => rows.map((r) => ({ title: r.title, points: r.points,
  ...Object.fromEntries(DESIGN.filter((k) => String(r[k] ?? "").trim()).map((k) => [k, r[k]])) }));
const blankRow = () => ({ title: "", points: "", ...Object.fromEntries(DESIGN.map((k) => [k, ""])) });

const lookName = (k, lang) => { const l = LOOKS.find((x) => x.k === (k || "classic")) || LOOKS[0]; return lang === "bm" ? l.bm : l.en; };

const kindOf = (t, i, n) => (i === 0 ? t("Kulit", "Cover") : i === n - 1 && n > 1 ? t("Penutup · sumber dilukis di sini", "Closing · source drawn here")
  : t("Slaid {n}", "Slide {n}", { n: i + 1 }));

/* The carousel of one post: its words, where they are drawn from, and the drawn pictures.
   Drawing is done by the worker (backend/semasa/slides.py) with no AI and no key. */
export default function SlidesEditor({ post, rows, setRows, locked, jobs, attachedIds, bg, setBg, bgOptions, busy,
  onRender, onUse, look, setLook, preview, blocked, setBlocked, resolveBg = () => "", captionPost = null, onToast = () => {}, picker = null }) {
  const { t, lang } = useLang();
  const n = rows.length;
  const size = post.stream === "linkedin" ? "1080×1350" : "1080×1080";
  const latest = jobs[0];
  const latestDone = jobs.find((j) => j.status === "done");
  const drawnStale = latestDone && slidesKey(latestDone.meta?.slides) !== slidesKey(fromRows(rows));
  const set = (i, patch) => setRows(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const studio = isStudioLook(look);
  const [open, setOpen] = useState(() => new Set());
  const [pickFor, setPickFor] = useState(null);          // {i: null} the set's background, {i: n} slide n+1's, null closed
  const slideUrls = latestDone?.meta?.slide_urls || [];
  const box = useLightbox(slideUrls.map((u, i) => ({ url: u, title: t("Slaid {n} daripada {m}", "Slide {n} of {m}", { n: i + 1, m: slideUrls.length }) })));
  const toggle = (i) => setOpen((o) => { const x = new Set(o); if (x.has(i)) x.delete(i); else x.add(i); return x; });
  // "Use this background on all N slides" (Studio's #bgAll): this slide's background and scrim, on every slide
  const bgAll = (i) => setRows(rows.map((r) => ({ ...r, bg: rows[i].bg, scrim: rows[i].scrim })));
  const bgClearAll = () => setRows(rows.map((r) => ({ ...r, bg: "", scrim: "" })));
  // typography and the character, from one slide onto every slide (the same idea as the background's "all")
  const styleAll = (i) => setRows(rows.map((r) => ({ ...r, ...Object.fromEntries(STYLE_KEYS.map((k) => [k, rows[i][k]])) })));
  const chooseBg = (token, all) => {
    if (pickFor?.i === null) setBg(token);
    else if (all) setRows(rows.map((r) => ({ ...r, bg: token })));
    else set(pickFor.i, { bg: token });
    setPickFor(null);
  };
  const anyOwnBg = rows.some((r) => r.bg);
  // what the preview draws: the rows as slides, each slide's own background resolved to an address this page can load
  const previewSlides = normaliseSlides(fromRows(rows)).map((s) => (s.bg && s.bg !== "none" ? { ...s, bg_url: resolveBg(s.bg) } : s));
  // Studio's "Reset from caption" and single card: built from the caption as it is on screen now
  const hasWords = rows.some((r) => r.title.trim() || r.points.trim());
  const fromCaption = (single) => {
    if (!captionPost?.caption?.trim()) return onToast(t("Tulis kapsyen dahulu.", "Write the caption first."), "warn");
    if (hasWords && !window.confirm(t("Ganti slaid yang ada dengan slaid daripada kapsyen?", "Replace the slides you have with slides from the caption?"))) return;
    const brand = preview.brand || null;
    const promo = (x) => isPromo(x, brand);
    if (single) {
      setRows(toRows(cardFromCaption(captionPost, promo)));
      return onToast(t("Satu kad daripada kapsyen.", "One card from the caption."), "ok");
    }
    const { slides, over } = slidesFromCaption(captionPost, promo);
    setRows(toRows(slides));
    onToast(over ? t("{n} slaid daripada kapsyen. {m} poin lagi tidak muat dalam 8 slaid dan kekal dalam kapsyen sahaja.",
      "{n} slides from the caption. {m} more points do not fit in 8 slides and stay in the caption only.", { n: slides.length, m: over })
      : t("{n} slaid daripada kapsyen.", "{n} slides from the caption.", { n: slides.length }), over ? "warn" : "ok");
  };
  const move = (i, d) => {
    const j = i + d;
    if (j < 0 || j >= n) return;
    const next = rows.slice();
    [next[i], next[j]] = [next[j], next[i]];
    setRows(next);
  };

  return (
    <div className="rounded-tile border border-line p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="flex items-center gap-1.5 text-sm font-medium"><Layers size={14} /> {t("Slaid carousel", "Carousel slides")}</p>
        <span className="text-[11px] text-muted">{n} / {MAX_SLIDES} {t("slaid", "slides")} · {size} · {t("dilukis tanpa AI, percuma", "drawn without AI, free")}</span>
      </div>
      <p className="mt-1 text-[11px] text-muted">
        {t("Satu fakta satu slaid. Tanda satu perkataan dengan *bintang* untuk penekanan. Sumber dilukis pada slaid terakhir "
          + "daripada medan Sumber. Peraturan kapsyen berlaku pada setiap slaid.",
        "One fact per slide. Mark a word with *asterisks* for emphasis. The source is drawn on the last slide "
          + "from the Source field. Caption rules apply to every slide.")}
      </p>

      <ol className="mt-3 space-y-3">
        {rows.map((r, i) => (
          <li key={i} className="rounded-tile bg-surface-2/60 p-2.5">
            <div className="mb-1.5 flex items-center justify-between gap-2">
              <span className="text-[11px] font-semibold uppercase tracking-wide text-accent">{kindOf(t, i, n)}</span>
              {!locked && (
                <span className="flex gap-1">
                  <button type="button" aria-label={t("Naik", "Move up")} disabled={i === 0} onClick={() => move(i, -1)} className="rounded p-1 text-muted hover:text-ink disabled:opacity-30"><ArrowUp size={13} /></button>
                  <button type="button" aria-label={t("Turun", "Move down")} disabled={i === n - 1} onClick={() => move(i, 1)} className="rounded p-1 text-muted hover:text-ink disabled:opacity-30"><ArrowDown size={13} /></button>
                  <button type="button" aria-label={t("Buang slaid", "Remove slide")} onClick={() => setRows(rows.filter((_, j) => j !== i))} className="rounded p-1 text-muted hover:text-danger"><Trash2 size={13} /></button>
                </span>
              )}
            </div>
            <Input value={r.title} disabled={locked} maxLength={240} onChange={(e) => set(i, { title: e.target.value })}
              placeholder={i === 0 ? t("Tajuk kulit (cth: Notifikasi *bukan* kelulusan)", "Cover title (e.g. Notification is *not* approval)")
                : t("Tajuk slaid", "Slide title")} />
            <label className="mt-1.5 block"><span className="sr-only">{t("Baris sokongan", "Supporting line")}</span>
              <Input value={r.lead} disabled={locked} maxLength={SLIDE_WORDS.lead} onChange={(e) => set(i, { lead: e.target.value })}
                placeholder={templateOf(r.template)?.lead ? t(templateOf(r.template).lead, templateOf(r.template).leadEn)
                  : t("Baris sokongan di bawah tajuk (pilihan)", "Supporting line under the title (optional)")} /></label>
            <TextArea rows={i === 0 ? 2 : 3} value={r.points} disabled={locked} className="mt-1.5"
              onChange={(e) => set(i, { points: e.target.value })}
              placeholder={templateOf(r.template)?.items ? t(templateOf(r.template).items, templateOf(r.template).itemsEn)
                : i === 0 ? t("Poin (pilihan)", "Points (optional)")
                : t("Satu poin satu baris (maksimum 5)", "One point per line (up to 5)")} />
            {studio && (
              <button type="button" onClick={() => toggle(i)} aria-expanded={open.has(i)}
                className="mt-1.5 inline-flex items-center gap-1 text-[11px] font-medium text-accent hover:underline">
                <Paintbrush size={11} /> {t("Reka bentuk slaid ini", "This slide's design")}
                {DESIGN.some((k) => r[k]) && <span className="rounded bg-accent/10 px-1 text-[10px]">{t("diubah", "changed")}</span>}
              </button>
            )}
            {studio && open.has(i) && (
              <SlideDesign r={r} i={i} n={n} set={(patch) => set(i, patch)} locked={locked} bgOptions={bgOptions} stream={post.stream}
                onBgAll={() => bgAll(i)} onStyleAll={() => styleAll(i)} resolveBg={resolveBg} onPick={picker ? () => setPickFor({ i }) : null} />
            )}
          </li>
        ))}
      </ol>

      {!locked && (
        <div className="mt-3 rounded-tile bg-surface-2/40 p-2.5">
          <LookPicker value={look} onChange={setLook} slides={previewSlides} stream={post.stream}
            eyebrow={preview.eyebrow} citation={preview.citation} bgUrl={preview.bgUrl} bgChosen={bg !== "none"}
            mascots={MASCOTS} onBlocked={setBlocked} />
        </div>
      )}

      {!locked && (
        <div className="mt-3 flex flex-wrap items-end gap-2">
          <Button type="button" size="sm" variant="ghost" disabled={n >= MAX_SLIDES}
            onClick={() => setRows([...rows, blankRow()])}><Plus size={12} /> {t("Tambah slaid", "Add slide")}</Button>
          <Button type="button" size="sm" variant="ghost" onClick={() => fromCaption(false)}
            title={t("Kulit, sekurang-kurangnya tiga fakta, dan baris penutup, daripada kapsyen", "A cover, at least three facts and a closing line, from the caption")}>
            {t("Bina daripada kapsyen", "Build from the caption")}</Button>
          <Button type="button" size="sm" variant="ghost" onClick={() => fromCaption(true)}
            title={t("Satu kad sahaja: cangkuk dan baris pertamanya", "One card only: the hook and its first line")}>
            {t("Kad tunggal", "Single card")}</Button>
          {studio && anyOwnBg && <Button type="button" size="sm" variant="ghost" onClick={bgClearAll}
            title={t("Setiap slaid kembali memakai latar set ini", "Every slide goes back to the set's background")}>
            {t("Kosongkan latar setiap slaid", "Clear every slide's background")}</Button>}
          <label className="ml-auto"><Label>{t("Latar", "Background")}</Label>
            <Select value={bg} onChange={setBg} options={bgOptions} aria-label={t("Latar slaid", "Slide background")} /></label>
          {picker && <Button type="button" size="sm" variant="soft" onClick={() => setPickFor({ i: null })}
            title={t("Pilih daripada gambar post, foto Wan, Unsplash atau jana gambar baharu", "Choose from the post's pictures, Wan's photos, Unsplash, or generate a new one")}>
            <ImageIcon size={12} /> {t("Pilih latar…", "Choose background…")}</Button>}
          <Button type="button" size="sm" disabled={busy || !n || !!blocked} onClick={onRender}
            title={t("Simpan post ini, kemudian bot melukis slaid", "Save this post, then the bot draws the slides")}>
            <Layers size={12} /> {t("Jana slaid", "Generate slides")}</Button>
        </div>
      )}

      {latest && (latest.status === "pending" || latest.status === "processing") && (
        <p className="mt-3 flex items-center gap-1.5 text-[12px] text-muted"><Loader2 size={12} className="animate-spin" />
          {t("Bot sedang melukis {n} slaid; ia masuk ke post ini sendiri selagi post ini draf.",
            ["The bot is drawing {n} slide; it comes into this post by itself while it is a draft.", "The bot is drawing {n} slides; they come into this post by themselves while it is a draft."],
            { n: latest.meta?.slides?.length || "" })}</p>
      )}
      {latest && latest.status === "error" && (
        <p className="mt-3 [overflow-wrap:anywhere] rounded-tile bg-danger/5 p-2 text-[12px] text-danger">{t("Lukisan terakhir gagal:", "Last drawing failed:")} {latest.error}</p>
      )}

      {latestDone && (
        <div className="mt-3">
          <div className="flex gap-2 overflow-x-auto pb-1" style={{ scrollSnapType: "x mandatory" }}>
            {(latestDone.meta?.slide_urls || []).map((u, i) => (
              <button type="button" key={u} onClick={() => box.open(i)} className="relative shrink-0 cursor-zoom-in" style={{ scrollSnapAlign: "start" }}
                title={t("Slaid {n}: klik untuk baca perkataan pada kad", "Slide {n}: click to read the words on the card", { n: i + 1 })}>
                <img src={u} alt={t("Slaid {n}", "Slide {n}", { n: i + 1 })} className={`${post.stream === "linkedin" ? "h-72 w-[230px] sm:h-60 sm:w-48 lg:h-[120px] lg:w-24" : "h-64 w-64 sm:h-52 sm:w-52 lg:h-24 lg:w-24"} max-w-[80vw] rounded-tile border border-line object-cover`} />
                <span className="absolute left-1 top-1 rounded bg-ink/80 px-1 text-[10px] text-bg">{i + 1}</span>
                <span className="absolute bottom-1 right-1 rounded bg-ink/70 p-0.5 text-bg"><Expand size={11} /></span>
              </button>
            ))}
          </div>
          <p className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-muted">
            {t("{n} slaid dilukis", ["{n} slide drawn", "{n} slides drawn"], { n: latestDone.meta?.count })}
            {` · ${lookName(latestDone.meta?.look, lang)}`}
            {latestDone.meta?.bg_missing ? ` · ${latestDone.meta.bg_missing}`
              : latestDone.meta?.bg_used ? ` · ${t("atas gambar post", "on the post picture")}` : ` · ${t("atas kertas", "on paper")}`}
            <button type="button" onClick={() => box.open(0)} className="inline-flex items-center gap-0.5 text-accent"><Expand size={10} /> {t("besarkan", "enlarge")}</button>
          </p>
          {drawnStale && <p className="mt-1 text-[12px] text-warn">
            {t("Slaid di atas telah diubah sejak dilukis. Tekan Jana slaid supaya gambar membawa perkataan yang sama.",
              "The slides above changed since they were drawn. Press Generate slides so the pictures carry the same words.")}</p>}
          {!attachedIds.includes(latestDone.id) && !locked && (
            <p className="mt-1 text-[12px] text-muted">
              {t("Set ini belum dilampirkan pada post (post bukan draf ketika ia siap).",
                "This set is not attached to the post yet (the post was not a draft when it finished).")}{" "}
              <button type="button" className="font-medium text-accent underline" onClick={() => onUse(latestDone.id)}>
                {t("Guna set ini", "Use this set")}</button></p>
          )}
        </div>
      )}
      <ImageLightbox {...box.props} />
      {picker && <BackgroundPicker open={!!pickFor} onClose={() => setPickFor(null)} target={pickFor} nSlides={n}
        current={pickFor?.i === null || pickFor === null ? bg : rows[pickFor.i]?.bg} onChoose={chooseBg} picker={picker} />}
    </div>
  );
}

/* One slide's own design, Studio's cardPanel fields: template, eyebrow, chip, note, source line, background, scrim and
   mascot, plus the text size, face and character placement (Wan, 3 Oct 2026). The headline and the supporting line are
   always on the slide above, never in here. Every field left empty means the chosen look decides, exactly as before. */
function SlideDesign({ r, i, n, set, locked, bgOptions, onBgAll, onStyleAll, stream, resolveBg = () => "", onPick = null }) {
  const { t, lang } = useLang();
  const [showCat, setShowCat] = useState(false);
  const tpl = templateOf(r.template);
  const uses = (f) => !tpl || tpl.uses.includes(f);
  const note = tpl ? noteLabel(r.template, t) : t("Nota / belon (pilihan)", "Note / bubble (optional)");
  const groups = [["grid", "Grid"], ["era", "Info ERA"], ["photo", t("Foto", "Photo")]];
  const tplOptions = [["", t("Ikut reka bentuk set (auto)", "As the set's design (auto)")],
    ...groups.flatMap(([g, name]) => TEMPLATES.filter((x) => x.group === g).map((x) => [x.k, `${name} · ${lang === "bm" ? x.name.split(" · ")[1] : x.en.split(" · ")[1]}`]))];
  const mascotOk = !r.template || takesMascot(r.template);
  const f = (k, label, extra = {}) => (
    <label className="block min-w-0"><Label>{label}</Label>
      <Input value={r[k]} disabled={locked} maxLength={SLIDE_WORDS[k]} onChange={(e) => set({ [k]: e.target.value })} {...extra} /></label>
  );
  const bgUrl = r.bg && r.bg !== "none" ? resolveBg(r.bg) : "";
  const compact = Object.entries(COMPACT).every(([k, v]) => r[k] === v);
  return (
    <div className="mt-2 grid gap-2 rounded-tile border border-line bg-surface p-2.5 sm:grid-cols-2">
      <div className="min-w-0 sm:col-span-2">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-muted">{t("Teks dan maskot pada kad", "Text and mascot on the card")}</p>
          <Button type="button" size="sm" variant={compact ? "primary" : "soft"} disabled={locked}
            onClick={() => set(compact ? Object.fromEntries(Object.keys(COMPACT).map((k) => [k, ""])) : COMPACT)}
            title={t("Teks 80%, fon sempit, maskot lebih kecil: lebih banyak ruang untuk gambar", "Text 80%, narrow face, smaller mascot: more room for the picture")}>
            <Minimize2 size={12} /> {compact ? t("Padatkan: hidup (klik untuk kembali)", "Compact: on (click to undo)") : t("Padatkan teks", "Compact the text")}</Button>
          {n > 1 && STYLE_KEYS.some((k) => r[k]) && (
            <Button type="button" size="sm" variant="ghost" disabled={locked} onClick={onStyleAll}>
              {t("Guna pada semua {n} slaid", "Use on all {n} slides", { n })}</Button>
          )}
        </div>
        <div className="mt-1.5 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          <label className="block min-w-0"><Label>{t("Saiz teks", "Text size")}</Label>
            <Select value={r.type_size} onChange={(v) => set({ type_size: v })} disabled={locked} className="w-full"
              aria-label={t("Saiz teks slaid {n}", "Slide {n} text size", { n: i + 1 })}
              options={[["", t("100% (templat)", "100% (the template's)")], ["120", "120%"], ["110", "110%"], ["90", "90%"], ["80", t("80% · padat", "80% · compact")],
                ["70", "70%"], ["60", t("60% · terkecil", "60% · smallest")]]} /></label>
          <label className="block min-w-0"><Label>{t("Jenis fon", "Font")}</Label>
            <Select value={r.font} onChange={(v) => set({ font: v })} disabled={locked} className="w-full"
              aria-label={t("Fon slaid {n}", "Slide {n} font", { n: i + 1 })}
              options={[["", t("Asal templat", "The template's own")], ["sans", t("Sempit (Instrument Sans): muat lebih banyak", "Narrow (Instrument Sans): fits more")],
                ["round", t("Bulat (Poppins)", "Round (Poppins)")], ["hand", t("Tulisan tangan (Caveat)", "Handwritten (Caveat)")]]} /></label>
          {mascotOk && (
            <label className="block min-w-0"><Label>{t("Kedudukan maskot", "Mascot position")}</Label>
              <Select value={r.mascot_pos} onChange={(v) => set({ mascot_pos: v })} disabled={locked} className="w-full"
                aria-label={t("Kedudukan maskot slaid {n}", "Slide {n} mascot position", { n: i + 1 })}
                options={[["", t("Auto", "Auto")], ["bl", t("Kiri bawah", "Bottom left")], ["bc", t("Tengah bawah", "Bottom centre")], ["br", t("Kanan bawah", "Bottom right")]]} /></label>
          )}
          {mascotOk && (
            <label className="block min-w-0"><Label>{t("Saiz maskot", "Mascot size")}</Label>
              <Select value={r.mascot_size} onChange={(v) => set({ mascot_size: v })} disabled={locked} className="w-full"
                aria-label={t("Saiz maskot slaid {n}", "Slide {n} mascot size", { n: i + 1 })}
                options={[["", t("Biasa", "Normal")], ["60", t("Kecil sangat (60%)", "Tiny (60%)")], ["80", t("Kecil (80%)", "Small (80%)")],
                  ["130", t("Besar (130%)", "Large (130%)")], ["160", t("Besar sangat (160%)", "Larger (160%)")]]} /></label>
          )}
        </div>
      </div>

      <div className="min-w-0 sm:col-span-2"><label className="block"><Label hint={tpl ? t(tpl.hint, tpl.hintEn) : ""}>{t("Templat slaid ini", "This slide's template")}</Label>
        <Select value={r.template} onChange={(v) => set({ template: v })} options={tplOptions} disabled={locked} className="w-full"
          aria-label={t("Templat slaid {n}", "Slide {n} template", { n: i + 1 })} /></label>
        <button type="button" onClick={() => setShowCat((x) => !x)} aria-expanded={showCat}
          className="mt-1 text-[11px] font-medium text-accent hover:underline">
          {showCat ? t("Tutup katalog", "Close the catalogue") : t("Pilih dari katalog (12 templat, dilukis)", "Pick from the catalogue (12 templates, drawn)")}</button>
        {showCat && <div className="mt-1.5"><TemplateCatalogue value={r.template} stream={stream} disabled={locked}
          onPick={(k) => set({ template: k })} /></div>}</div>
      {uses("eyebrow") && f("eyebrow", t("Label atas (eyebrow)", "Eyebrow"), { placeholder: t("ikut set", "as the set") })}
      {(tpl ? tpl.group !== "photo" : true) && f("chip", t("Label cip (instrumen, bukan logo)", "Chip label (the instrument, not a logo)"),
        { placeholder: i === n - 1 ? t("Sumber", "Source") : "" })}
      {note && f("note", note)}
      {f("footnote", t("Baris sumber (kaki)", "Source line (footer)"), { placeholder: i === n - 1 ? t("dari medan Sumber", "from the Source field") : "" })}
      <div className="block min-w-0"><Label>{t("Latar slaid ini", "This slide's background")}</Label>
        <div className="flex items-center gap-2">
          <span className="h-9 w-9 shrink-0 overflow-hidden rounded border border-line bg-surface-2">
            {bgUrl && <img src={bgUrl} alt="" className="h-full w-full object-cover" />}</span>
          <Select value={r.bg} onChange={(v) => set({ bg: v })} disabled={locked} className="min-w-0 flex-1"
            options={[["", t("Ikut latar set", "As the set's background")], ["none", t("Tiada gambar", "No picture")], ...bgOptions.filter(([k]) => k !== "none")]}
            aria-label={t("Latar slaid {n}", "Slide {n} background", { n: i + 1 })} />
        </div>
        {onPick && !locked && (
          <button type="button" onClick={onPick} className="mt-1 inline-flex items-center gap-1 text-[11px] font-medium text-accent hover:underline">
            <ImageIcon size={11} /> {t("Pilih daripada Unsplash, gambar post atau jana…", "Pick from Unsplash, the post's pictures, or generate…")}</button>
        )}
      </div>
      <label className="block min-w-0"><Label>{t("Tutupan atas gambar", "How much the words cover the picture")}</Label>
        <Select value={r.scrim} onChange={(v) => set({ scrim: v })} disabled={locked} className="w-full"
          options={[["", t("Lalai", "Default")], ["light", t("Ringan: gambar jelas", "Light: the picture stays visible")],
            ["medium", t("Sederhana", "Medium: balanced")], ["heavy", t("Tebal: gambar sibuk", "Heavy: for a busy photo")]]} /></label>
      {mascotOk && (
        <label className="block min-w-0"><Label>{t("Maskot", "Mascot")}</Label>
          <Select value={r.mascot} onChange={(v) => set({ mascot: v })} disabled={locked} className="w-full"
            options={[["", t("Auto (ikut templat)", "Auto (by template)")], ["none", t("Tiada", "None")],
              ...MASCOTS.map((m) => [m.k, lang === "bm" ? m.name : m.en])]} /></label>
      )}
      {n > 1 && r.bg && (
        <div className="flex items-end sm:col-span-2">
          <Button type="button" size="sm" variant="soft" onClick={onBgAll} disabled={locked}>
            {r.bg === "none" ? t("Tiada gambar pada semua {n} slaid", "No picture on all {n} slides", { n })
              : t("Guna latar ini pada semua {n} slaid", "Use this background on all {n} slides", { n })}</Button>
        </div>
      )}
    </div>
  );
}
