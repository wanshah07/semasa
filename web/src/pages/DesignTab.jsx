import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { AlertTriangle, CheckCircle2, Clock, ExternalLink, ImagePlus, LayoutTemplate, Loader2, Plus, RotateCcw, Trash2,
  Wand2, X } from "lucide-react";
import { fadeUp } from "../design/motion";
import { STREAMS } from "../lib/brand";
import { normaliseSlides, scan } from "../lib/compliance";
import { timeAgo } from "../lib/format";
import { useLang } from "../lib/i18n";
import { IMAGE_TYPES, refusal, removeReference, uploadReference } from "../lib/storage";
import { TABLES, errText, supabase } from "../lib/SupabaseClient";
import LookPicker from "../components/LookPicker";
import { UnsplashResults, UnsplashSearch } from "../components/Unsplash";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import { Input, Label, Segmented, Select, TextArea } from "../components/ui/Field";

/* The Design tab (Wan, 25 Sep 2026: "add design section - to create poster, single card and carousel for post" and
   "the slide can create based on upload and prompt/idea provided"). The page only registers a job: the worker
   (backend/semasa/design.py + slides.py) writes the words from an idea when asked, then draws them with no AI and no
   cost, on brand paper, on Wan's own picture, or on a picture the image provider makes for it first. */

const SIZE_PX = { square: [1080, 1080], portrait: [1080, 1350], story: [1080, 1920] };
const SIZE_LABEL = { square: "1:1 · 1080×1080", portrait: "4:5 · 1080×1350", story: "9:16 · 1080×1920" };
const MAX_POINTS = { poster: 5, card: 3, carousel: 3 };
const blankSlide = () => ({ title: "", points: "" });
const defaultSize = (design, stream) => (design === "poster" ? "portrait" : design === "card" ? "square"
  : stream === "linkedin" ? "portrait" : "square");

export default function DesignTab({ user, gens, posts, brand, onToast }) {
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
  const [attach, setAttach] = useState("");
  const [fromPost, setFromPost] = useState("");
  const [busy, setBusy] = useState("");
  const [look, setLook] = useState("classic");
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
  const ready = (words === "ai" ? brief.trim().length > 0 : own.length > 0)
    && (bg !== "upload" || file) && (bg !== "ai" || bgPrompt.trim()) && (bg !== "unsplash" || unsplashReady) && !lookBlocked;
  const previewBg = bg === "upload" ? preview : bg === "unsplash" ? (uRow?.generated_media_url || unsplashPick?.thumb || "") : "";
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

  async function submit(e) {
    e.preventDefault();
    if (!ready) return onToast(t("Lengkapkan perkataan dan latar dahulu.", "Fill in the words and the background first."), "warn");
    setBusy("send");
    let uploaded = null;
    try {
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
      const meta = { flow: "design", design, format, stream, bg: bgValue, look, eyebrow: eyebrow.trim(), citation: citation.trim(),
        ...(words === "ai" ? { brief: brief.trim() } : { slides: own }), ...(fromPost ? { from_post: fromPost } : {}) };
      const ins = await supabase.from(TABLES.media).insert({
        mode: "slides", type: "image", status: "pending", created_by: user.id, prompt: "", post_id: attach || null,
        reference_url: uploaded?.url ?? null, reference_path: uploaded?.path ?? null, meta,
      });
      if (ins.error) throw new Error(errText(ins.error));
      onToast(t("Dalam giliran. Hasil muncul di bawah dalam beberapa minit.", "Queued. The result appears below within a few minutes."), "ok");
      gens.reload();
      setFile(null);
    } catch (err) {
      if (uploaded) await removeReference(uploaded.path);
      onToast(err.message || String(err), "danger");
    } finally {
      setBusy("");
    }
  }

  const results = gens.rows.filter((r) => r.meta?.design);
  const designs = [["poster", "Poster"], ["card", t("Kad tunggal", "Single card")], ["carousel", "Carousel"]];

  return (
    <main className="mx-auto max-w-page px-4 pb-20 pt-10 sm:px-6">
      <motion.div variants={fadeUp} initial="hidden" animate="show">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-accent">{t("Reka bentuk", "Design")}</p>
        <h1 className="mt-2 text-4xl leading-tight">{t("Poster, kad dan carousel untuk post.", "Posters, cards and carousels for posts.")}</h1>
        <p className="mt-3 max-w-2xl text-sm text-muted">
          {t("Beri idea atau prompt dan bot tulis perkataannya, atau tulis sendiri. Pilih latar: kertas jenama, gambar anda, "
            + "atau gambar AI. Lukisan dibuat tanpa AI dan percuma; peraturan post (tiada CTA, tiada URL, [SAHKAN]) berlaku pada setiap perkataan.",
          "Give an idea or a prompt and the bot writes the words, or write them yourself. Pick a background: brand paper, your "
            + "own picture, or an AI picture. The drawing is made without AI and is free; the post rules (no CTA, no URL, [SAHKAN]) apply to every word.")}
        </p>
      </motion.div>

      <Card as="form" onSubmit={submit} className="mt-8 p-5 sm:p-6">
        <div className="grid gap-4 md:grid-cols-2">
          <div className="min-w-0 space-y-4">
            <div><Label>{t("Jenis", "Kind")}</Label><Segmented value={design} onChange={setDesign} options={designs} /></div>
            <div><Label>{t("Untuk", "For")}</Label><Segmented value={stream} onChange={setStream} options={STREAMS} /></div>
            <div><Label>{t("Saiz", "Size")}</Label>
              <Segmented value={format} onChange={setFormat} options={Object.entries(SIZE_LABEL)} /></div>
            <label className="block"><Label hint={t("pilihan · isi borang daripada post sedia ada", "optional · fill the form from an existing post")}>{t("Daripada post", "From a post")}</Label>
              <Select value={fromPost} onChange={usePost} className="w-full" aria-label={t("Daripada post", "From a post")}
                options={[["", "—"], ...usable.slice(0, 150).map((p) => [p.id, `${p.date || "—"} · ${(p.hook || "").slice(0, 60) || p.id.slice(0, 8)}`])]} /></label>
          </div>
          <div className="min-w-0 space-y-4">
            <div><Label>{t("Latar", "Background")}</Label>
              <Segmented value={bg} onChange={setBg} options={[["none", t("Kertas jenama", "Brand paper")],
                ["upload", t("Gambar saya", "My picture")], ["ai", t("Gambar AI", "AI picture")], ["unsplash", "Unsplash"]]} /></div>
            {bg === "unsplash" && (
              <div className="space-y-2">
                <UnsplashSearch user={user} stream={stream} onToast={onToast} compact
                  onQueued={(id) => { setUnsplashRow(id); setUnsplashPick(null); gens.reload(); }} />
                {uRow && <div className="rounded-tile border border-line"><UnsplashResults row={uRow} onToast={onToast}
                  chosenId={uRow.meta?.pick || unsplashPick?.id} onPicked={(_, p) => { setUnsplashPick(p); gens.reload(); }} /></div>}
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

        <div className="mt-5 border-t border-line pt-4">
          <LookPicker value={look} onChange={setLook} slides={previewSlides} sample={sampleWords} stream={stream}
            eyebrow={eyebrow.trim()} citation={citation.trim()} bgUrl={previewBg} bgChosen={bg !== "none"}
            size={SIZE_PX[format]} onBlocked={setLookBlocked} />
        </div>

        <div className="mt-5 flex flex-wrap items-center justify-end gap-3">
          <span className="text-xs text-muted">{SIZE_LABEL[format]} · {t("dilukis tanpa AI, percuma", "drawn without AI, free")}</span>
          <Button type="submit" disabled={!!busy || !ready}>
            {busy ? <Loader2 size={14} className="animate-spin" /> : <Wand2 size={14} />} {t("Jana reka bentuk", "Make the design")}</Button>
        </div>
      </Card>

      <h2 className="mb-4 mt-12 text-xl">{t("Hasil", "Results")}</h2>
      {gens.error && <p className="mb-4 rounded-tile bg-danger/10 p-3 text-sm text-danger">{gens.error}</p>}
      <DesignResults rows={results} user={user} gens={gens} onToast={onToast} designs={Object.fromEntries(designs)} />
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

function DesignResults({ rows, user, gens, onToast, designs }) {
  const { t } = useLang();
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
                <span className={`inline-flex items-center gap-1.5 rounded-pill px-2.5 py-1 font-semibold ${r.status === "done" ? "bg-ok/10 text-ok"
                  : r.status === "error" ? "bg-danger/10 text-danger" : "bg-warn/10 text-warn"}`}>
                  <Icon size={12} className={r.status === "processing" ? "animate-spin" : ""} />
                  {r.status === "done" ? t("Siap", "Done") : r.status === "error" ? t("Gagal", "Failed") : r.status === "processing" ? t("Melukis", "Drawing") : t("Menunggu", "Waiting")}
                </span>
                <span className="text-muted">{designs[m.design] || m.design} · {SIZE_LABEL[m.format] || "—"} · {timeAgo(r.created_at)}</span>
              </div>
              <p className="mt-2 line-clamp-2 [overflow-wrap:anywhere] text-sm">{(m.slides?.[0]?.title || m.brief || "").replace(/\*/g, "")}</p>
              {m.stream && <p className="mt-1 text-[11px] text-muted">{m.stream === "linkedin" ? "LinkedIn" : "ws.regulab"}
                {urls.length > 1 ? ` · ${t("{n} slaid", "{n} slides", { n: urls.length })}` : ""}{r.post_id ? ` · ${t("dilampirkan pada post", "attached to a post")}` : ""}</p>}
              {m.bg_missing && <p className="mt-2 text-[11px] text-warn">{t("Gambar latar belum siap, jadi dilukis atas kertas.", "The background picture was not ready, so it was drawn on paper.")}</p>}
              {hard.length > 0 && <ul className="mt-2 space-y-1 text-[11px] text-danger">{hard.map((f, i) => <li key={i} className="[overflow-wrap:anywhere]"><b>{f.where}</b>: {f.msg}</li>)}</ul>}
              {soft.length > 0 && <ul className="mt-2 space-y-1 text-[11px] text-warn">{soft.map((f, i) => <li key={i} className="[overflow-wrap:anywhere]"><b>{f.where}</b>: {f.msg}</li>)}</ul>}
              {r.error && <p className="mt-2 [overflow-wrap:anywhere] rounded-tile bg-danger/5 p-2 text-[11px] text-danger">{r.error}</p>}
              <div className="mt-3 flex flex-wrap items-center gap-2">
                {urls[0] && <a href={urls[0]} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-[11px] text-accent hover:underline">
                  <ExternalLink size={11} /> {t("Buka fail", "Open file")}</a>}
                {mine && (
                  <span className="ml-auto flex gap-1">
                    {r.status === "error" && <Button size="sm" variant="soft" title={t("Cuba lagi", "Try again")}
                      onClick={() => guard(async () => { await gens.requeue(r.id); onToast(t("Dimasukkan semula ke giliran.", "Put back in the queue."), "ok"); })}><RotateCcw size={12} /></Button>}
                    {r.status !== "processing" && <Button size="sm" variant="danger" title={t("Padam", "Delete")}
                      onClick={() => guard(async () => { if (window.confirm(t("Padam reka bentuk ini?", "Delete this design?"))) { await gens.remove(r); onToast(t("Dipadam.", "Deleted."), "info"); } })}><Trash2 size={12} /></Button>}
                  </span>
                )}
              </div>
            </div>
          </Card>
        );
      })}
    </div>
  );
}
