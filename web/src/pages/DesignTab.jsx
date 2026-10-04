import { useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import { AlertTriangle, CheckCircle2, Clock, ExternalLink, Eye, ImagePlus, LayoutTemplate, Loader2, Palette, PenTool, Pencil, Plus, RotateCcw,
  Save, Trash2, Wand2, X } from "lucide-react";
import { fadeUp } from "../design/motion";
import { STREAMS } from "../lib/brand";
import { normaliseSlides, scan } from "../lib/compliance";
import { timeAgo } from "../lib/format";
import { sizeLabel, sizeMeta, sizeOf } from "../lib/sizes";
import { useLang } from "../lib/i18n";
import { IMAGE_TYPES, refusal, removeReference, uploadReference } from "../lib/storage";
import { TABLES, errText, supabase } from "../lib/SupabaseClient";
import LookPicker from "../components/LookPicker";
import { GROUNDS, MASCOTS, groundOf } from "../lib/cards/library";
import SizePicker from "../components/SizePicker";
import { UnsplashResults, UnsplashSearch } from "../components/Unsplash";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import { Input, Label, Modal, Segmented, Select, TextArea } from "../components/ui/Field";
import { cloneLayout, refineLayout } from "../lib/designClone";
import { layoutToSeed, patchBoxes, slotsOf, wordsFromLayout } from "../lib/designCloneSeed";
import { loadImageFile, samplePatches, sizeLike } from "../lib/designPatch";
import { renderSeedPreview } from "../lib/kanvasBuild";
import DesignLibrary from "../components/DesignLibrary";
import CanvaHandoff from "../components/CanvaHandoff";

/* The Design tab (Wan, 25 Sep 2026: "add design section - to create poster, single card and carousel for post" and
   "the slide can create based on upload and prompt/idea provided"). The page only registers a job: the worker
   (backend/semasa/design.py + slides.py) writes the words from an idea when asked, then draws them with no AI and no
   cost, on brand paper, on Wan's own picture, or on a picture the image provider makes for it first. */

// every size Canva lists for social media (lib/sizes.js); the three Studio shapes keep their old ids
const pxOf = (id) => { const s = sizeOf(id); return s ? [s.w, s.h] : [1080, 1350]; };
const MAX_POINTS = { poster: 5, card: 3, carousel: 3 };
const blankSlide = () => ({ title: "", points: "" });
const defaultSize = (design, stream) => (design === "poster" ? "portrait" : design === "card" ? "square"
  : stream === "linkedin" ? "portrait" : "square");

export default function DesignTab({ user, gens, posts, brand, onToast, onCanvas }) {
  const { t } = useLang();
  const [design, setDesign] = useState("poster");
  const [stream, setStream] = useState("regulab");
  const [format, setFormat] = useState("portrait");
  const [words, setWords] = useState("ai");                 // ai | own
  const [brief, setBrief] = useState("");
  const [rows, setRows] = useState([blankSlide()]);
  const [eyebrow, setEyebrow] = useState("");
  const [citation, setCitation] = useState("");
  const [bg, setBg] = useState("none");                    // none | upload | ai | unsplash
  const [unsplashRow, setUnsplashRow] = useState("");       // the search this form made
  const [unsplashPick, setUnsplashPick] = useState(null);   // the photo chosen from it
  const [file, setFile] = useState(null);
  const [bgPrompt, setBgPrompt] = useState("");
  const [libPick, setLibPick] = useState(GROUNDS[0]?.k || "");   // Wan's own photographs, Studio's grounds
  const [attach, setAttach] = useState("");
  const [fromPost, setFromPost] = useState("");
  const [busy, setBusy] = useState("");
  const [look, setLook] = useState("classic");
  const [fit, setFit] = useState(true);                      // fit the design to each slide (studio.js fitTemplate)
  // a reference to take ideas from (Wan, 26 Sep 2026: "upload reference and AI will review > render and get
  // confirmation to save the design"): read by the worker, drawn, and kept only when Wan presses Simpan
  const [styleFile, setStyleFile] = useState(null);
  const [autoLook, setAutoLook] = useState(true);
  // how the reference is used (Wan, 1 Oct 2026: "upload design, then ai render similarly, only context is different"):
  // inspire = the worker draws an original design in its mood (as before); rebuild = its layout is rebuilt as editable Kanvas layers
  const [refMode, setRefMode] = useState("inspire");
  // rebuild on the reference picture itself (only the words change: "almost 100% serupa") or as rebuilt layers (every shape editable)
  const [refBase, setRefBase] = useState("original");
  const [cloneReview, setCloneReview] = useState(null);       // { layout, removed, words, image, base, size, mode, refUrl } waiting for the words to be checked
  const stylePreview = useMemo(() => (styleFile ? URL.createObjectURL(styleFile) : ""), [styleFile]);
  useEffect(() => () => { if (stylePreview) URL.revokeObjectURL(stylePreview); }, [stylePreview]);
  useEffect(() => { if (!styleFile && bg === "from_ref") setBg("none"); }, [styleFile]); // eslint-disable-line react-hooks/exhaustive-deps
  const [lookBlocked, setLookBlocked] = useState(null);
  const preview = useMemo(() => (file ? URL.createObjectURL(file) : ""), [file]);
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);
  useEffect(() => { setFormat(defaultSize(design, stream)); }, [design, stream]);
  useEffect(() => {                                          // a poster or a card is one picture: one slide of words
    if (design !== "carousel" && rows.length > 1) setRows(rows.slice(0, 1));
  }, [design]); // eslint-disable-line react-hooks/exhaustive-deps

  const drafts = posts.rows.filter((p) => p.status === "draft");
  const usable = posts.rows.filter((p) => p.status !== "rejected");
  const own = normaliseSlides(rows.map((r) => ({ title: r.title, points: r.points.split("\n") })));
  // the post rules, on the words as typed: a hard flag is shown now, and blocks the post the artwork is attached to
  const flags = useMemo(() => (words === "own" && own.length ? scan({ stream, citation, media: [{ artwork: own }] },
    brand?.regulab).filter((f) => f.where.startsWith("Design") || f.where === "Source") : []),
  [words, JSON.stringify(own), stream, citation, brand]); // eslint-disable-line react-hooks/exhaustive-deps
  const uRow = gens.rows.find((r) => r.id === unsplashRow);
  const unsplashReady = !!uRow && (!!uRow.generated_media_url || !!uRow.meta?.pick) && uRow.status !== "error";
  const rebuild = !!styleFile && refMode === "rebuild";
  const wordsOk = words === "ai" ? brief.trim().length > 0 : own.length > 0;
  const ready = rebuild
    ? wordsOk && design !== "carousel" && (bg !== "upload" || !!file)
    : wordsOk
    && (bg !== "upload" || file) && (bg !== "ai" || bgPrompt.trim()) && (bg !== "unsplash" || unsplashReady)
    && (bg !== "library" || !!groundOf(libPick))
    && (!lookBlocked || (styleFile && autoLook));
  const previewBg = bg === "upload" ? preview : bg === "unsplash" ? (uRow?.generated_media_url || unsplashPick?.thumb || "")
    : bg === "library" ? (groundOf(libPick)?.url || "") : "";
  // the design preview: Wan's own words when he writes them, sample words while the bot is to write them
  const sampleWords = !(words === "own" && own.length);
  const previewSlides = sampleWords ? designSample(design, stream) : own;

  function usePost(id) {
    setFromPost(id);
    const p = posts.rows.find((x) => x.id === id);
    if (!p) return;
    setStream(p.stream || "regulab");
    setAttach(p.status === "draft" ? p.id : "");
    if (p.citation) setCitation(p.citation);
    const slides = normaliseSlides(p.slides);
    if (design === "carousel" && slides.length) {
      setWords("own");
      setRows(slides.map((s) => ({ title: s.title, points: s.points.join("\n") })));
      return;
    }
    const lang = p.lang || (p.stream === "linkedin" ? "en" : "bm");
    const text = p.text?.[lang] || {};
    const caption = text.instagram || text.linkedin || text.facebook || text.threads || "";
    setWords("ai");
    setBrief([p.hook, caption].filter(Boolean).join("\n\n").slice(0, 3500));
  }

  // Rebuild: the AI reads the reference ONCE as a layout (no picture is made); the words are then checked here against the post rules,
  // the result is drawn as a preview, a refine pass compares that preview with the reference, and the design opens in Kanvas as layers,
  // every piece movable. `mode` "inspire" asks for an ORIGINAL composition in the reference's visual language instead.
  async function startClone(mode = "clone") {
    setBusy(mode === "inspire" ? "inspire" : "clone");
    try {
      const base = mode === "clone" && refBase === "original" ? "original" : "layers";
      let size = pxOf(format);
      if (base === "original") {                      // the canvas takes the reference's own shape, so its picture fits edge to edge
        const img = await loadImageFile(styleFile);
        size = sizeLike(img.naturalWidth, img.naturalHeight);
      }
      const got = await cloneLayout({ file: styleFile, width: size[0], height: size[1], stream, brief: words === "ai" ? brief : "", mode });
      let w;
      if (words === "own" && own.length) w = { eyebrow: eyebrow.trim(), headline: own[0].title, points: own[0].points, source: citation.trim() };
      else {
        w = wordsFromLayout(got.layout);
        if (eyebrow.trim()) w.eyebrow = eyebrow.trim();
        if (citation.trim()) w.source = citation.trim();
      }
      setCloneReview({ layout: got.layout, removed: got.removed, words: w, model: got.model, image: got.image, base, size, mode,
        refUrl: base === "original" ? URL.createObjectURL(styleFile) : "" });
    } catch (err) {
      onToast(err.message || String(err), "danger");
    } finally {
      setBusy("");
    }
  }

  // layout + words → the seed Kanvas draws, the same for the preview and for opening (so what is shown is what opens)
  async function seedFor(review, layout, w) {
    const [W, H] = review.size;
    const name = styleFile?.name ? styleFile.name.replace(/\.[^.]+$/, "") : "";
    if (review.base === "original") {
      // the old words are where the FIRST reading put them; a refine pass moves the boxes towards the truth, so both sets are patched
      // (a moved box uncovered the top of the old headline in the Chromium check)
      const boxes = [...patchBoxes(review.layout), ...patchBoxes(layout)];
      const seen = new Set();
      const patches = await samplePatches(styleFile, boxes.filter((bx) => { const k = [bx.x, bx.y, bx.w, bx.h].map((v) => v.toFixed(3)).join(); if (seen.has(k)) return false; seen.add(k); return true; }));
      return layoutToSeed(layout, w, { width: W, height: H, referenceUrl: review.refUrl, patches, t, name });
    }
    const pictureUrl = bg === "upload" && file ? URL.createObjectURL(file) : bg === "library" ? (groundOf(libPick)?.url || "") : "";
    return layoutToSeed(layout, w, { width: W, height: H, pictureUrl, t, name });
  }

  async function previewOf(review, layout, w) {
    const { seed } = await seedFor(review, layout, w);
    return (await renderSeedPreview(seed, { maxSide: 1000 })).dataUrl;
  }

  async function refineOnce(review, layout, w) {
    const render = await previewOf(review, layout, w);
    const [W, H] = review.size;
    return (await refineLayout({ image: review.image, render, layout, width: W, height: H })).layout;
  }

  async function openInKanvas(review, layout, w) {
    const { seed, notes } = await seedFor(review, layout, w);
    notes.slice(0, 3).forEach((n) => onToast(n, "info"));
    setCloneReview(null);
    onCanvas?.({ ...seed, sizeId: review.base === "original" ? null : format });
  }

  function closeReview() {
    if (cloneReview?.refUrl) URL.revokeObjectURL(cloneReview.refUrl);
    setCloneReview(null);
  }

  async function submit(e) {
    e.preventDefault();
    if (!ready) return onToast(t("Lengkapkan perkataan dan latar dahulu.", "Fill in the words and the background first."), "warn");
    if (rebuild) return startClone();
    setBusy("send");
    let uploaded = null;
    let styleUp = null;
    try {
      if (styleFile) styleUp = await uploadReference(user, styleFile);
      let bgValue = "none";
      if (bg === "upload") {
        uploaded = await uploadReference(user, file);
        bgValue = "reference";
      } else if (bg === "ai") {
        // the picture is made first (the default image provider: Cloudflare, free), and the drawing waits for it
        const pic = await supabase.from(TABLES.media).insert({
          mode: "prompt", type: "image", status: "pending", created_by: user.id, provider: null,
          prompt: `${bgPrompt.trim()}. A calm, uncluttered background for text: no words, no letters, no logos, no people's faces.`,
          meta: { flow: "design-bg" },
        }).select("id").single();
        if (pic.error) throw new Error(errText(pic.error));
        bgValue = pic.data.id;
      } else if (bg === "unsplash") {
        bgValue = unsplashRow;                               // the worker waits for the pick to be stored, then draws on it
      }
      if (bg === "from_ref") bgValue = "from_ref";           // an original background in the reference's mood (worker)
      if (bg === "library") bgValue = `lib:${libPick}`;     // one of Wan's own photographs (web/public/cards/grounds)
      const meta = { flow: "design", design, format, ...sizeMeta(format), stream, bg: bgValue, look: styleUp && autoLook ? "auto" : look, fit: fit && look !== "classic",
        eyebrow: eyebrow.trim(), citation: citation.trim(),
        ...(styleUp ? { style_ref: { url: styleUp.url, path: styleUp.path, name: styleFile.name } } : {}),
        ...(words === "ai" ? { brief: brief.trim() } : { slides: own }), ...(fromPost ? { from_post: fromPost } : {}) };
      const ins = await supabase.from(TABLES.media).insert({
        mode: "slides", type: "image", status: "pending", created_by: user.id, prompt: "", post_id: attach || null,
        reference_url: uploaded?.url ?? null, reference_path: uploaded?.path ?? null, meta,
      });
      if (ins.error) throw new Error(errText(ins.error));
      onToast(styleUp
        ? t("Dalam giliran. AI semak rujukan, lukis, kemudian tunggu anda tekan Simpan.", "Queued. The AI reviews the reference, draws, then waits for you to press Save.")
        : t("Dalam giliran. Hasil muncul di bawah dalam beberapa minit.", "Queued. The result appears below within a few minutes."), "ok");
      gens.reload();
      setFile(null); setStyleFile(null);
    } catch (err) {
      if (uploaded) await removeReference(uploaded.path);
      if (styleUp) await removeReference(styleUp.path);
      onToast(err.message || String(err), "danger");
    } finally {
      setBusy("");
    }
  }

  const results = gens.rows.filter((r) => r.meta?.design);
  // a design inside an approved, scheduled or posted post cannot be deleted (supabase/017: the database refuses it)
  const lockedBy = (id) => (posts?.rows || []).find((p) => ["approved", "scheduled", "posted"].includes(p.status) && (p.media_ids || []).includes(id));
  const designs = [["poster", "Poster"], ["card", t("Kad tunggal", "Single card")], ["carousel", "Carousel"]];

  return (
    <main className="mx-auto max-w-page px-4 pb-20 pt-10 sm:px-6">
      <motion.div variants={fadeUp} initial="hidden" animate="show">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-accent">{t("Reka bentuk", "Design")}</p>
        <h1 className="mt-2 text-4xl leading-tight">{t("Poster, kad dan carousel untuk post.", "Posters, cards and carousels for posts.")}</h1>
        <p className="mt-3 max-w-2xl text-sm text-muted">
          {t("Beri idea atau prompt dan bot tulis perkataannya, atau tulis sendiri. Pilih latar: kertas jenama, gambar anda, "
            + "atau gambar AI. Lukisan dibuat tanpa AI dan percuma; peraturan post (tiada CTA, tiada URL, tiada sumber media sosial) berlaku pada setiap perkataan.",
          "Give an idea or a prompt and the bot writes the words, or write them yourself. Pick a background: brand paper, your "
            + "own picture, or an AI picture. The drawing is made without AI and is free; the post rules (no CTA, no URL, no social source) apply to every word.")}
        </p>
      </motion.div>

      <Card as="form" onSubmit={submit} className="mt-8 p-5 sm:p-6">
        <div className="grid gap-4 md:grid-cols-2">
          <div className="min-w-0 space-y-4">
            <div><Label>{t("Jenis", "Kind")}</Label><Segmented value={design} onChange={setDesign} options={designs} /></div>
            <div><Label>{t("Untuk", "For")}</Label><Segmented value={stream} onChange={setStream} options={STREAMS} /></div>
            <div><Label hint={sizeLabel(format)}>{t("Saiz", "Size")}</Label>
              <SizePicker value={format} onChange={setFormat} /></div>
            <label className="block"><Label hint={t("pilihan · isi borang daripada post sedia ada", "optional · fill the form from an existing post")}>{t("Daripada post", "From a post")}</Label>
              <Select value={fromPost} onChange={usePost} className="w-full" aria-label={t("Daripada post", "From a post")}
                options={[["", "—"], ...usable.slice(0, 150).map((p) => [p.id, `${p.date || "—"} · ${(p.hook || "").slice(0, 60) || p.id.slice(0, 8)}`])]} /></label>
          </div>
          <div className="min-w-0 space-y-4">
            <div className="rounded-tile border border-dashed border-line p-3">
              <Label hint={t("pilihan · AI semak, lukis, anda sahkan", "optional · the AI reviews, draws, you confirm")}>{t("Rujukan reka bentuk", "Design reference")}</Label>
              <div className="flex flex-wrap items-center gap-3">
                {stylePreview ? <img src={stylePreview} alt="" className="h-20 w-20 rounded-tile object-cover" />
                  : <span className="grid h-20 w-20 place-items-center rounded-tile bg-surface-2 text-muted"><Eye size={18} /></span>}
                <div className="min-w-0 flex-1 space-y-1.5">
                  <label className="cursor-pointer text-sm text-accent underline">
                    {styleFile ? t("Tukar rujukan", "Change reference") : t("Muat naik reka bentuk yang anda suka", "Upload a design you like")}
                    <input type="file" accept={IMAGE_TYPES.join(",")} className="hidden" onChange={(e) => {
                      const f = e.target.files?.[0]; e.target.value = "";
                      if (!f) return;
                      const why = refusal(f);
                      if (why) onToast(why, "warn"); else setStyleFile(f);
                    }} />
                  </label>
                  {styleFile && (
                    <>
                      <Segmented value={refMode} onChange={setRefMode} options={[["inspire", t("Ilham", "Inspired")], ["rebuild", t("Bina semula serupa", "Rebuild it the same")]]} />
                      {refMode === "inspire" && <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={autoLook} onChange={(e) => setAutoLook(e.target.checked)} />
                        {t("Biar AI pilih reka bentuk yang paling hampir", "Let the AI pick the nearest design")}</label>}
                      {refMode === "rebuild" && <Segmented value={refBase} onChange={setRefBase} options={[["original", t("Atas gambar rujukan (paling serupa)", "On the reference picture (closest)")], ["layers", t("Lapisan dibina semula", "Rebuilt layers")]]} />}
                      <button type="button" onClick={() => setStyleFile(null)} className="inline-flex items-center gap-1 text-[11px] text-muted hover:text-danger">
                        <X size={12} /> {t("Buang rujukan", "Remove reference")}</button>
                    </>
                  )}
                </div>
              </div>
              {rebuild && <p className="mt-2 text-[11px] text-accent">{design === "carousel"
                ? t("Bina semula untuk satu gambar sahaja: pilih Poster atau Kad tunggal.", "Rebuild makes one picture: choose Poster or Single card.")
                : refBase === "original"
                  ? t("Gambar rujukan kekal sebagai latar (saiz ikut rujukan): perkataan lama, logo dan wajah ditampal dengan warna di belakangnya, perkataan baharu diletakkan di tempat yang sama, kemudian AI banding pratonton dengan rujukan dan betulkan kedudukan. Semuanya lapisan boleh sunting di Kanvas.",
                    "The reference picture stays as the background (the size follows the reference): the old words, logos and faces are patched in the colour behind them, the new words go in the same places, then the AI compares the preview with the reference and corrects the placing. Everything is an editable layer in Kanvas.")
                  : t("AI baca susun atur rujukan (latar, bentuk, kawasan gambar, setiap blok teks) dan ia dibina semula sebagai lapisan boleh sunting di Kanvas dengan perkataan anda, kemudian banding pratonton dengan rujukan dan betulkan. Logo, nama jenama, laman web, CTA dan wajah orang tidak disalin.",
                    "The AI reads the reference's layout (background, shapes, picture areas, every text block) and it is rebuilt as editable layers in Kanvas with your words, then compares the preview with the reference and corrects it. Logos, brand names, websites, calls to action and people's faces are not copied.")}</p>}
              <p className={`mt-2 text-[11px] text-muted ${rebuild ? "hidden" : ""}`}>{t("AI baca rujukan: apa yang baik, apa yang mesti diubah (CTA, laman web, logo jenama lain), dan buat reka bentuk asli, bukan salinan. Pratonton menunggu anda tekan Simpan; yang tidak disimpan dipadam selepas 7 hari.",
                "The AI reads the reference: what works, what must change (a CTA, a website, another brand's logo), and makes an original design, not a copy. The preview waits for your Save; one not saved is deleted after 7 days.")}</p>
            </div>
            <div><Label>{t("Latar", "Background")}</Label>
              <Segmented value={bg} onChange={setBg} options={[["none", t("Kertas jenama", "Brand paper")],
                ["upload", t("Gambar saya", "My picture")], ["library", t("Foto Wan", "Wan's photos")], ["ai", t("Gambar AI", "AI picture")], ["unsplash", "Unsplash"],
                ...(styleFile ? [["from_ref", t("Ilham rujukan (AI)", "From the reference (AI)")]] : [])]} /></div>
            {bg === "unsplash" && (
              <div className="space-y-2">
                <UnsplashSearch user={user} stream={stream} onToast={onToast} compact
                  onQueued={(id) => { setUnsplashRow(id); setUnsplashPick(null); gens.reload(); }} />
                {uRow && <div className="rounded-tile border border-line"><UnsplashResults row={uRow} onToast={onToast}
                  chosenId={uRow.meta?.pick || unsplashPick?.id} onPicked={(_, p) => { setUnsplashPick(p); gens.reload(); }} /></div>}
              </div>
            )}
            {bg === "library" && (
              <div role="radiogroup" aria-label={t("Foto Wan", "Wan's photos")} className="flex gap-2 overflow-x-auto pb-1" style={{ scrollSnapType: "x mandatory" }}>
                {GROUNDS.map((g) => (
                  <button key={g.k} type="button" role="radio" aria-checked={libPick === g.k} onClick={() => setLibPick(g.k)} title={g.alt}
                    className={`shrink-0 overflow-hidden rounded-tile border ${libPick === g.k ? "border-accent ring-2 ring-accent/30" : "border-line"}`} style={{ scrollSnapAlign: "start" }}>
                    <img src={g.url} alt={g.alt} className="h-24 w-20 object-cover" loading="lazy" />
                    <span className="block px-1 py-0.5 text-center text-[10px] text-muted">{g.name}</span>
                  </button>
                ))}
              </div>
            )}
            {bg === "upload" && (
              <div className="flex items-center gap-3">
                {preview ? <img src={preview} alt="" className="h-20 w-20 rounded-tile object-cover" />
                  : <span className="grid h-20 w-20 place-items-center rounded-tile border-2 border-dashed border-line text-muted"><ImagePlus size={18} /></span>}
                <label className="cursor-pointer text-sm text-accent underline">
                  {file ? t("Tukar gambar", "Change picture") : t("Pilih gambar", "Choose a picture")}
                  <input type="file" accept={IMAGE_TYPES.join(",")} className="hidden" onChange={(e) => {
                    const f = e.target.files?.[0]; e.target.value = "";
                    if (!f) return;
                    const why = refusal(f);
                    if (why) onToast(why, "warn"); else setFile(f);
                  }} />
                </label>
                {file && <button type="button" onClick={() => setFile(null)} aria-label={t("Buang", "Remove")} className="text-muted hover:text-danger"><X size={14} /></button>}
              </div>
            )}
            {bg === "ai" && (
              <label className="block"><Label hint={t("dijana dahulu oleh penyedia gambar (Cloudflare: percuma), kemudian dijadikan latar", "made first by the image provider (Cloudflare: free), then used as the background")}>
                {t("Gambar latar", "Background picture")}</Label>
                <TextArea rows={2} value={bgPrompt} onChange={(e) => setBgPrompt(e.target.value)} maxLength={600}
                  placeholder={t("Cth: makmal kosmetik yang bersih, cahaya siang lembut", "E.g. a clean cosmetics lab, soft daylight")} /></label>
            )}
            <label className="block"><Label hint={t("pilihan · label kecil di atas", "optional · the small label on top")}>{t("Label", "Label")}</Label>
              <Input value={eyebrow} onChange={(e) => setEyebrow(e.target.value)} maxLength={60} placeholder={t("Cth: Halal Malaysia", "E.g. Halal Malaysia")} /></label>
            <label className="block"><Label hint={t("instrumen atau pengawal selia; dilukis di bawah", "the instrument or regulator; drawn at the foot")}>{t("Sumber", "Source")}</Label>
              <Input value={citation} onChange={(e) => setCitation(e.target.value)} maxLength={300} placeholder="NPRA, Guidelines for Control of Cosmetic Products in Malaysia" /></label>
            <label className="block"><Label hint={t("pilihan · ditambah pada gambar post draf itu", "optional · added to that draft post's pictures")}>{t("Lampirkan pada post", "Attach to a post")}</Label>
              <Select value={attach} onChange={setAttach} className="w-full" aria-label={t("Lampirkan pada post", "Attach to a post")}
                options={[["", t("Tidak", "No")], ...drafts.slice(0, 150).map((p) => [p.id, `${p.date || "—"} · ${(p.hook || "").slice(0, 60) || p.id.slice(0, 8)}`])]} /></label>
          </div>
        </div>

        <div className="mt-5 border-t border-line pt-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <Label>{t("Perkataan", "Words")}</Label>
            <Segmented value={words} onChange={setWords} options={[["ai", t("Bot tulis daripada idea", "The bot writes from an idea")], ["own", t("Saya tulis sendiri", "I write them")]]} />
          </div>
          {words === "ai" ? (
            <label className="mt-2 block"><Label hint={design === "carousel" ? t("bot tulis 5 hingga 7 slaid", "the bot writes 5 to 7 slides")
              : t("bot tulis satu tajuk dan hingga {n} poin", "the bot writes one headline and up to {n} points", { n: MAX_POINTS[design] })}>
              {t("Idea atau prompt", "Idea or prompt")}</Label>
              <TextArea rows={5} value={brief} onChange={(e) => setBrief(e.target.value)} maxLength={4000}
                placeholder={t("Cth: pemegang sijil halal tidak boleh sembunyikan nama pengilang OEM; fakta daripada MPPHM 2020",
                  "E.g. a halal certificate holder cannot hide the OEM manufacturer's name; facts from MPPHM 2020")} /></label>
          ) : (
            <SlideRows rows={rows} setRows={setRows} design={design} />
          )}
          {flags.length > 0 && (
            <ul className="mt-3 space-y-1 text-[12px]">
              {flags.map((f, i) => (
                <li key={i} className={`flex items-start gap-1.5 [overflow-wrap:anywhere] ${f.hard ? "text-danger" : "text-warn"}`}>
                  <AlertTriangle size={12} className="mt-0.5 shrink-0" /> <span><b>{f.where}</b>: {f.msg}</span></li>
              ))}
            </ul>
          )}
        </div>

        {!rebuild && <div className="mt-5 border-t border-line pt-4">
          {styleFile && autoLook && <p className="mb-2 text-[12px] text-accent">{t("AI akan memilih reka bentuk daripada rujukan; pilihan di bawah hanya pratonton.",
            "The AI picks the design from the reference; the choice below is only a preview.")}</p>}
          <LookPicker value={look} onChange={setLook} slides={previewSlides} sample={sampleWords} stream={stream}
            eyebrow={eyebrow.trim()} citation={citation.trim()} bgUrl={previewBg} bgChosen={bg !== "none"} mascots={MASCOTS}
            size={pxOf(format)} onBlocked={setLookBlocked} fit={fit} onFit={setFit} />
        </div>}

        <div className="mt-5 flex flex-wrap items-center justify-end gap-3">
          <span className="text-xs text-muted">{sizeLabel(format)} · {rebuild ? t("AI baca susun atur sekali; selebihnya tanpa AI", "the AI reads the layout once; the rest is drawn without AI") : t("dilukis tanpa AI, percuma", "drawn without AI, free")}</span>
          {styleFile && refMode === "inspire" && design !== "carousel" && (
            <Button type="button" variant="soft" disabled={!!busy || !wordsOk} onClick={() => startClone("inspire")}
              title={t("AI gubah reka bentuk asli dalam gaya rujukan (warna, jenis huruf, suasana) dan buka terus di Kanvas, tanpa menunggu pekerja.", "The AI composes an original design in the reference's style (colours, type, mood) and opens it in Kanvas at once, with no worker queue.")}>
              {busy === "inspire" ? <Loader2 size={14} className="animate-spin" /> : <PenTool size={14} />} {t("Jana di Kanvas (serta-merta)", "Make it in Kanvas (now)")}</Button>
          )}
          <Button type="submit" disabled={!!busy || !ready}>
            {busy ? <Loader2 size={14} className="animate-spin" /> : <Wand2 size={14} />} {rebuild ? t("Bina semula di Kanvas", "Rebuild in Kanvas") : t("Jana reka bentuk", "Make the design")}</Button>
        </div>
      </Card>

      {cloneReview && <CloneReview data={cloneReview} stream={stream} brand={brand} onClose={closeReview} onToast={onToast}
        onPreview={(layout, w) => previewOf(cloneReview, layout, w)} onRefine={(layout, w) => refineOnce(cloneReview, layout, w)}
        onOpen={(layout, w) => openInKanvas(cloneReview, layout, w)} />}

      <h2 className="mb-4 mt-12 text-xl">{t("Hasil", "Results")}</h2>
      {gens.error && <p className="mb-4 rounded-tile bg-danger/10 p-3 text-sm text-danger">{gens.error}</p>}
      <DesignResults lockedBy={lockedBy} rows={results} user={user} gens={gens} onToast={onToast} designs={Object.fromEntries(designs)} onCanvas={onCanvas} />
      <DesignLibrary />
    </main>
  );
}

/* Sample words for the design preview while the bot is still to write the real ones. */
function designSample(design, stream) {
  const en = stream === "linkedin";
  const cover = { title: en ? "Your *headline* here" : "Tajuk *anda* di sini",
    points: design === "carousel" ? [en ? "One supporting line." : "Satu baris sokongan."]
      : (en ? ["The first point, short and cited.", "The second point.", "The third point."]
        : ["Poin pertama, ringkas dan bersumber.", "Poin kedua.", "Poin ketiga."]) };
  if (design !== "carousel") return [cover];
  return [cover, { title: en ? "What the rule says" : "Apa kata peraturan", points: en ? ["One fact per slide.", "Short and cited."] : ["Satu fakta satu slaid.", "Ringkas dan bersumber."] },
    { title: en ? "Remember this" : "Ingat ini", points: [en ? "The takeaway, never a call to action." : "Kesimpulan, bukan seruan tindakan."] }];
}

/* The words by hand: one row per slide. A poster or a card is one row; a carousel is up to ten. */
function SlideRows({ rows, setRows, design }) {
  const { t } = useLang();
  const set = (i, patch) => setRows(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const many = design === "carousel";
  return (
    <div className="mt-2 space-y-3">
      <p className="text-[11px] text-muted">{t("Tanda satu perkataan dengan *bintang* untuk penekanan. Satu poin satu baris.",
        "Mark one word with *asterisks* for emphasis. One point per line.")}{many ? ` ${t("Slaid pertama ialah kulit; sumber dilukis pada slaid terakhir.", "The first slide is the cover; the source is drawn on the last slide.")}` : ""}</p>
      {rows.map((r, i) => (
        <div key={i} className="rounded-tile bg-surface-2/60 p-3">
          <div className="mb-1.5 flex items-center justify-between gap-2">
            <span className="text-[11px] font-semibold uppercase tracking-wide text-accent">
              {many ? (i === 0 ? t("Kulit", "Cover") : t("Slaid {n}", "Slide {n}", { n: i + 1 })) : t("Tajuk dan poin", "Headline and points")}</span>
            {many && rows.length > 1 && (
              <button type="button" aria-label={t("Buang slaid", "Remove slide")} onClick={() => setRows(rows.filter((_, j) => j !== i))}
                className="rounded p-1 text-muted hover:text-danger"><Trash2 size={13} /></button>
            )}
          </div>
          <Input value={r.title} onChange={(e) => set(i, { title: e.target.value })} maxLength={240}
            placeholder={t("Tajuk", "Headline")} aria-label={t("Tajuk", "Headline")} />
          <TextArea rows={many ? 2 : 4} value={r.points} onChange={(e) => set(i, { points: e.target.value })} className="mt-2"
            placeholder={t("Poin, satu setiap baris (maksimum {n})", "Points, one per line (at most {n})", { n: MAX_POINTS[design] })}
            aria-label={t("Poin", "Points")} />
        </div>
      ))}
      {many && rows.length < 10 && (
        <Button type="button" size="sm" variant="ghost" onClick={() => setRows([...rows, blankSlide()])}><Plus size={12} /> {t("Tambah slaid", "Add slide")}</Button>
      )}
    </div>
  );
}

/* The art director's reading of a reference and Wan's three answers to the preview: Simpan (keep it; it is attached
   to its post only now), Ubah & render semula (a note, then drawn again), Buang. The worker does each, so its files
   and its post stay in step. */
function ReviewPanel({ row, mine, onToast, gens }) {
  const { t } = useLang();
  const [note, setNote] = useState("");
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const m = row.meta || {};
  const rv = m.review || {};
  const waiting = m.awaiting_confirm && row.status === "done";
  async function send(patch, msg) {
    setBusy(true);
    const { data, error } = await supabase.from(TABLES.media)
      .update({ status: "pending", attempts: 0, error: null, meta: { ...m, ...patch } }).eq("id", row.id).select("id");
    setBusy(false);
    if (error) return onToast(errText(error), "danger");
    if (!data?.length) return onToast(t("Tidak disimpan: hanya orang yang membuatnya boleh mengubahnya.", "Not saved: only the person who made it can change it."), "warn");
    onToast(msg, "ok"); setOpen(false); setNote(""); gens.reload();
  }
  return (
    <div className="mt-3 rounded-tile bg-surface-2/70 p-3 text-[12px]">
      <p className="flex items-center gap-2 font-semibold">
        {m.style_ref?.url && <img src={m.style_ref.url} alt="" className="h-9 w-9 shrink-0 rounded object-cover" />}
        {m.flow === "canva" ? t("Dibina dalam Canva oleh bot", "Built in Canva by the bot") : t("Semakan rujukan", "Reference review")}
        {m.look_chosen && <span className="rounded-pill bg-surface px-2 py-0.5 text-[10px] font-normal text-muted">{t("reka bentuk", "design")}: {m.look_chosen}</span>}
      </p>
      {rv.unread ? <p className="mt-1.5 text-warn [overflow-wrap:anywhere]">{t("Rujukan tidak dibaca", "Reference not read")}: {rv.unread}</p> : (
        <>
          {rv.summary && <p className="mt-1.5 [overflow-wrap:anywhere]">{rv.summary}</p>}
          {rv.keep?.length > 0 && <p className="mt-1.5 [overflow-wrap:anywhere]"><b>{t("Diambil", "Taken")}:</b> {rv.keep.join(" · ")}</p>}
          {rv.change?.length > 0 && <p className="mt-1 text-warn [overflow-wrap:anywhere]"><b>{t("Diubah", "Changed")}:</b> {rv.change.join(" · ")}</p>}
          {rv.brands?.length > 0 && <p className="mt-1 text-muted [overflow-wrap:anywhere]">{t("Jenama dalam rujukan (tidak disalin)", "Brands in the reference (not copied)")}: {rv.brands.join(", ")}</p>}
        </>
      )}
      {(m.revisions || []).length > 0 && <p className="mt-1 text-muted [overflow-wrap:anywhere]">{t("Diubah {n} kali · nota terakhir", ["Changed {n} time · last note", "Changed {n} times · last note"], { n: m.revisions.length })}: {m.revisions[m.revisions.length - 1].note || "—"}</p>}
      {m.saved && <p className="mt-2 inline-flex items-center gap-1 font-semibold text-ok"><CheckCircle2 size={12} /> {t("Disimpan", "Saved")}</p>}
      {mine && waiting && (
        <div className="mt-2.5 space-y-2">
          <div className="flex flex-wrap gap-2">
            <Button size="sm" disabled={busy} onClick={() => send({ confirm: "save" }, t("Disimpan. Dilampirkan pada post jika dipilih.", "Saved. Attached to the post if one was chosen."))}>
              <Save size={12} /> {t("Simpan", "Save")}</Button>
            {m.flow !== "canva" && <Button size="sm" variant="soft" disabled={busy} onClick={() => setOpen(!open)}><Pencil size={12} /> {t("Ubah & render semula", "Change & redraw")}</Button>}
          </div>
          {open && (
            <div className="space-y-2">
              <TextArea rows={2} value={note} onChange={(e) => setNote(e.target.value)} maxLength={600} aria-label={t("Apa yang perlu diubah", "What to change")}
                placeholder={t("Cth: latar lebih gelap, tajuk lebih pendek, warna ikut jenama", "E.g. a darker background, a shorter headline, brand colours")} />
              <Button size="sm" disabled={busy || !note.trim()} onClick={() => send({ revise: { note: note.trim() } }, t("Dihantar. Dilukis semula dalam beberapa minit.", "Sent. Redrawn within a few minutes."))}>
                <RotateCcw size={12} /> {t("Render semula", "Redraw")}</Button>
            </div>
          )}
        </div>
      )}
      {row.status !== "done" && (m.confirm || m.revise) && <p className="mt-2 inline-flex items-center gap-1 text-muted"><Loader2 size={12} className="animate-spin" /> {m.confirm ? t("Menyimpan…", "Saving…") : t("Melukis semula…", "Redrawing…")}</p>}
    </div>
  );
}

function DesignResults({ rows, user, gens, onToast, designs, onCanvas, lockedBy = () => null }) {
  const { t } = useLang();
  const [canva, setCanva] = useState(null);                  // the design row being handed to Canva
  if (!rows.length) {
    return <p className="rounded-card border border-dashed border-line p-10 text-center text-sm text-muted">
      {t("Belum ada reka bentuk. Isi borang di atas.", "No designs yet. Fill in the form above.")}</p>;
  }
  async function guard(fn) {
    try { await fn(); } catch (e) { onToast(e.message || String(e), "danger"); }
  }
  return (
    <div className="grid items-start gap-4 md:grid-cols-2 xl:grid-cols-3">
      {rows.map((r) => {
        const m = r.meta || {};
        const urls = m.slide_urls || (r.generated_media_url ? [r.generated_media_url] : []);
        const hard = (m.flags || []).filter((f) => f.hard);
        const soft = (m.flags || []).filter((f) => !f.hard);
        const mine = user && r.created_by === user.id;
        const Icon = r.status === "done" ? CheckCircle2 : r.status === "error" ? AlertTriangle : r.status === "processing" ? Loader2 : Clock;
        return (
          <Card key={r.id} className="min-w-0 overflow-hidden">
            {urls.length > 0 ? (
              <div className="flex snap-x snap-mandatory gap-2 overflow-x-auto bg-surface-2 p-2">
                {urls.map((u, i) => (
                  <a key={u} href={u} target="_blank" rel="noopener noreferrer" className="shrink-0 snap-start" title={t("Buka saiz penuh", "Open full size")}>
                    <img src={u} alt={`${i + 1}`} loading="lazy" className={`h-48 w-auto rounded-tile object-contain ${urls.length === 1 ? "mx-auto" : ""}`} />
                  </a>
                ))}
              </div>
            ) : (
              <div className="grid h-48 place-items-center bg-surface-2 text-muted"><LayoutTemplate size={28} /></div>
            )}
            <div className="p-4">
              <div className="flex flex-wrap items-center justify-between gap-2 text-[11px]">
                <span className={`inline-flex items-center gap-1.5 rounded-pill px-2.5 py-1 font-semibold ${r.status === "done" && m.awaiting_confirm ? "bg-warn/10 text-warn"
                  : r.status === "done" ? "bg-ok/10 text-ok"
                  : r.status === "error" ? "bg-danger/10 text-danger" : "bg-warn/10 text-warn"}`}>
                  <Icon size={12} className={r.status === "processing" ? "animate-spin" : ""} />
                  {r.status === "done" ? (m.awaiting_confirm ? t("Tunggu pengesahan", "Awaiting your Save") : m.saved ? t("Disimpan", "Saved") : t("Siap", "Done"))
                    : r.status === "error" ? t("Gagal", "Failed") : r.status === "processing" ? t("Melukis", "Drawing") : t("Menunggu", "Waiting")}
                </span>
                <span className="text-muted">{designs[m.design] || m.design} · {m.size_name ? `${m.size_name} · ${m.size?.[0]}×${m.size?.[1]}` : sizeLabel(m.format, m.size)} · {timeAgo(r.created_at)}</span>
              </div>
              <p className="mt-2 line-clamp-2 [overflow-wrap:anywhere] text-sm">{(m.slides?.[0]?.title || m.brief || "").replace(/\*/g, "")}</p>
              {m.stream && <p className="mt-1 text-[11px] text-muted">{m.stream === "linkedin" ? "LinkedIn" : "ws.regulab"}
                {urls.length > 1 ? ` · ${t("{n} slaid", "{n} slides", { n: urls.length })}` : ""}{r.post_id ? ` · ${t("dilampirkan pada post", "attached to a post")}` : ""}</p>}
              {m.bg_missing && <p className="mt-2 text-[11px] text-warn">{t("Gambar latar belum siap, jadi dilukis atas kertas.", "The background picture was not ready, so it was drawn on paper.")}</p>}
              {hard.length > 0 && <ul className="mt-2 space-y-1 text-[11px] text-danger">{hard.map((f, i) => <li key={i} className="[overflow-wrap:anywhere]"><b>{f.where}</b>: {f.msg}</li>)}</ul>}
              {soft.length > 0 && <ul className="mt-2 space-y-1 text-[11px] text-warn">{soft.map((f, i) => <li key={i} className="[overflow-wrap:anywhere]"><b>{f.where}</b>: {f.msg}</li>)}</ul>}
              {r.error && <p className="mt-2 [overflow-wrap:anywhere] rounded-tile bg-danger/5 p-2 text-[11px] text-danger">{r.error}</p>}
              {m.style_ref && <ReviewPanel row={r} mine={mine} onToast={onToast} gens={gens} />}
              <div className="mt-3 flex flex-wrap items-center gap-2">
                {urls[0] && onCanvas && r.status === "done" && (
                  // a drawn design is one flat picture: it opens as the background, with room to add text and pictures on top
                  <button type="button" onClick={() => { const [w, h] = m.size?.length === 2 ? m.size : pxOf(m.format); onCanvas({ width: w, height: h, sizeId: m.format || null,
                    name: (m.slides?.[0]?.title || m.brief || t("Reka bentuk", "Design")).replace(/\*/g, "").slice(0, 60), source: "design", sourceId: r.id,
                    layers: [{ kind: "image", role: "bg", url: urls[0], cover: true, name: t("Reka bentuk", "Design") }] }); }}
                    className="inline-flex items-center gap-1 text-[11px] text-accent hover:underline"><PenTool size={11} /> {t("Ubah dalam Kanvas", "Edit in Kanvas")}</button>
                )}
                {urls[0] && <a href={urls[0]} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-[11px] text-accent hover:underline">
                  <ExternalLink size={11} /> {t("Buka fail", "Open file")}</a>}
                {urls[0] && r.status === "done" && m.flow !== "canva" && Array.isArray(m.slides) && m.slides.length > 0 && (
                  <button type="button" onClick={() => setCanva(r)} className="inline-flex items-center gap-1 text-[11px] text-accent hover:underline"
                    title={t("Bina semula sebagai reka bentuk Canva yang boleh disunting", "Rebuild as an editable Canva design")}>
                    <Palette size={11} /> {t("Bina semula dalam Canva", "Rebuild in Canva")}</button>
                )}
                {mine && (
                  <span className="ml-auto flex gap-1">
                    {r.status === "error" && <Button size="sm" variant="soft" title={t("Cuba lagi", "Try again")}
                      onClick={() => guard(async () => { await gens.requeue(r.id); onToast(t("Dimasukkan semula ke giliran.", "Put back in the queue."), "ok"); })}><RotateCcw size={12} /></Button>}
                    {lockedBy(r.id) && <span className="self-center text-[11px] text-muted"
                      title={t("Kembalikan post itu ke draf untuk memadam reka bentuk ini.", "Put that post back to draft to delete this design.")}>
                      {t("Dalam post yang diluluskan", "In an approved post")}</span>}
                    {r.status !== "processing" && !lockedBy(r.id) && <Button size="sm" variant="danger" title={t("Padam", "Delete")}
                      onClick={() => guard(async () => { if (window.confirm(t("Padam reka bentuk ini?", "Delete this design?"))) { await gens.remove(r); onToast(t("Dipadam.", "Deleted."), "info"); } })}><Trash2 size={12} /></Button>}
                  </span>
                )}
              </div>
            </div>
          </Card>
        );
      })}
      <CanvaHandoff open={!!canva} onClose={() => setCanva(null)} slides={canva?.meta?.slides || []} urls={canva?.meta?.slide_urls || []}
        stream={canva?.meta?.stream || "regulab"} size={canva?.meta?.size?.length === 2 ? canva.meta.size : pxOf(canva?.meta?.format)}
        sizeName={canva?.meta?.size_name || ""} look={canva?.meta?.look || "classic"} citation={canva?.meta?.citation || ""}
        eyebrow={canva?.meta?.eyebrow || ""} kind={canva?.meta?.design || "carousel"} />
    </div>
  );
}

/* The words of a rebuilt design, checked before it opens in Kanvas (Wan, 1 Oct 2026). The AI wrote them for each text block when it was
   given an idea, or they are Wan's own; either way every word goes through the same post rules as a post's artwork, and a hard flag
   stops the design opening until it is fixed here. Only the blocks the reference has are offered: a reference with no small label has
   no Label field, because a field with nowhere to go would be a lie. */
function CloneReview({ data, stream, brand, onClose, onOpen, onPreview, onRefine, onToast }) {
  const { t } = useLang();
  const [layout, setLayout] = useState(data.layout);
  const slots = useMemo(() => slotsOf(layout), [layout]);
  const [w, setW] = useState({ eyebrow: data.words.eyebrow || "", headline: data.words.headline || "", points: (data.words.points || []).join("\n"), source: data.words.source || "" });
  const points = w.points.split("\n").map((x) => x.trim()).filter(Boolean);
  const wordsOut = () => ({ eyebrow: slots.eyebrow ? w.eyebrow.trim() : "", headline: w.headline.trim(), points, source: slots.source ? w.source.trim() : "" });
  const flags = useMemo(() => scan({ stream, citation: w.source, media: [{ artwork: normaliseSlides([{ title: w.headline, points: [w.eyebrow, ...points].filter(Boolean) }]) }] },
    brand?.regulab).filter((f) => f.where.startsWith("Design") || f.where === "Source"), [stream, w.source, w.headline, w.eyebrow, w.points, brand]); // eslint-disable-line react-hooks/exhaustive-deps
  const blocked = flags.some((f) => f.hard) || !w.headline.trim();
  const ptLimit = Math.max(slots.points.length, 1);
  // the preview: what Kanvas will open, drawn here first; redrawn (after a pause) when the words or the layout change
  const [preview, setPreview] = useState("");
  const [busy, setBusy] = useState("");                 // "" | "preview" | "refine"
  const [passes, setPasses] = useState(0);
  const auto = useRef(data.mode !== "inspire");         // one refine pass runs by itself on a rebuild; an inspired design has nothing to match
  useEffect(() => {
    let live = true;
    const h = setTimeout(async () => {
      setBusy((b) => b || "preview");
      try {
        const url = await onPreview(layout, wordsOut());
        if (live) setPreview(url);
      } catch (e) {
        if (live) onToast(e.message || String(e), "warn");
      } finally {
        if (live) setBusy((b) => (b === "preview" ? "" : b));
      }
    }, 400);
    return () => { live = false; clearTimeout(h); };
  }, [layout, w.headline, w.eyebrow, w.points, w.source]); // eslint-disable-line react-hooks/exhaustive-deps
  async function refine() {
    if (busy) return;
    setBusy("refine");
    try {
      const next = await onRefine(layout, wordsOut());
      setLayout(next);
      setPasses((n) => n + 1);
    } catch (e) {
      onToast(t("Penghalusan gagal: {e}", "Refining failed: {e}", { e: e.message || String(e) }), "warn");
    } finally {
      setBusy("");
    }
  }
  useEffect(() => {                                     // the first pass, once, as soon as the first preview exists
    if (auto.current && preview && !busy) { auto.current = false; refine(); }
  }, [preview]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <Modal open onClose={onClose} title={data.mode === "inspire" ? t("Reka bentuk diilhamkan: semak sebelum dibuka", "Inspired design: check before it opens") : t("Semak perkataan sebelum dibina", "Check the words before it is rebuilt")}>
      <div className="space-y-3">
        <div className="relative overflow-hidden rounded-tile border border-line bg-surface-2">
          {preview ? <img src={preview} alt={t("Pratonton", "Preview")} className="mx-auto max-h-[22rem] w-auto" />
            : <div className="grid h-40 place-items-center text-xs text-muted"><Loader2 size={16} className="animate-spin" /></div>}
          {busy && <span className="absolute right-2 top-2 inline-flex items-center gap-1 rounded-pill bg-surface/90 px-2 py-1 text-[11px] text-muted">
            <Loader2 size={11} className="animate-spin" /> {busy === "refine" ? t("AI banding dengan rujukan…", "AI comparing with the reference…") : t("Melukis…", "Drawing…")}</span>}
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-muted">
          <span>{data.base === "original" ? t("Atas gambar rujukan · {w}×{h}", "On the reference picture · {w}×{h}", { w: data.size[0], h: data.size[1] }) : t("Lapisan dibina semula · {w}×{h}", "Rebuilt layers · {w}×{h}", { w: data.size[0], h: data.size[1] })}
            {passes > 0 ? ` · ${t("{n} kali dihalusi", "refined {n} time(s)", { n: passes })}` : ""}</span>
          {data.mode !== "inspire" && <button type="button" onClick={refine} disabled={!!busy || passes >= 4} className="inline-flex items-center gap-1 text-accent underline decoration-dotted underline-offset-2 disabled:opacity-50">
            <RotateCcw size={11} /> {t("Halusi lagi (AI banding)", "Refine again (AI compares)")}</button>}
        </div>
        <p className="text-[12px] text-muted">{layout.summary || ""}</p>
        {data.removed.length > 0 && (
          <div className="rounded-tile bg-warn/10 p-2.5 text-[12px] text-warn">
            <p className="font-medium">{t("Tidak disalin daripada rujukan", "Not copied from the reference")}</p>
            <ul className="mt-1 list-disc pl-4 [overflow-wrap:anywhere]">{data.removed.map((r, i) => <li key={i}>{r}</li>)}</ul>
          </div>
        )}
        <label className="block"><Label>{t("Tajuk", "Headline")}</Label>
          <Input value={w.headline} onChange={(e) => setW({ ...w, headline: e.target.value })} maxLength={200} /></label>
        {slots.eyebrow && <label className="block"><Label hint={t("pilihan", "optional")}>{t("Label", "Label")}</Label>
          <Input value={w.eyebrow} onChange={(e) => setW({ ...w, eyebrow: e.target.value })} maxLength={60} /></label>}
        <label className="block"><Label hint={t("satu poin setiap baris; rujukan ada {n} blok", "one point per line; the reference has {n} block(s)", { n: slots.points.length })}>{t("Poin", "Points")}</Label>
          <TextArea rows={Math.min(8, ptLimit + 2)} value={w.points} onChange={(e) => setW({ ...w, points: e.target.value })} maxLength={2000} /></label>
        {slots.source && <label className="block"><Label hint={t("pilihan", "optional")}>{t("Sumber", "Source")}</Label>
          <Input value={w.source} onChange={(e) => setW({ ...w, source: e.target.value })} maxLength={300} /></label>}
        {flags.length > 0 && (
          <ul className="space-y-1 text-[12px]">
            {flags.map((f, i) => (
              <li key={i} className={`flex items-start gap-1.5 [overflow-wrap:anywhere] ${f.hard ? "text-danger" : "text-warn"}`}>
                <AlertTriangle size={12} className="mt-0.5 shrink-0" /> <span><b>{f.where}</b>: {f.msg}</span></li>
            ))}
          </ul>
        )}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>{t("Batal", "Cancel")}</Button>
          <Button type="button" disabled={blocked || !!busy} onClick={() => onOpen(layout, wordsOut())}>
            <PenTool size={14} /> {t("Buka di Kanvas", "Open in Kanvas")}</Button>
        </div>
      </div>
    </Modal>
  );
}
