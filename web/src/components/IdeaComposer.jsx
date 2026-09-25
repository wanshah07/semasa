import { useEffect, useState } from "react";
import { ImagePlus, X } from "lucide-react";
import { TABLES, errText, supabase } from "../lib/SupabaseClient";
import { CATEGORY_TO_DOMAIN, STREAMS } from "../lib/brand";
import { useLang } from "../lib/i18n";
import { IMAGE_TYPES, refusal, removeReference, uploadReference } from "../lib/storage";
import Button from "./ui/Button";
import { Input, Label, Modal, Segmented, Select, TextArea } from "./ui/Field";

/* Flow A, step one. From a headline ("Jadikan idea") or by hand. Inserting the row is all the
   page does: the worker reads the source, writes the draft and queues the pictures. */
export default function IdeaComposer({ open, onClose, trend, user, brand, onToast, onDone }) {
  const { t } = useLang();
  const [stream, setStream] = useState("regulab");
  const [media, setMedia] = useState("image");
  const [slides, setSlides] = useState(false);
  const [domain, setDomain] = useState("");
  const [angle, setAngle] = useState("");
  const [note, setNote] = useState("");
  const [title, setTitle] = useState("");
  const [url, setUrl] = useState("");
  const [refs, setRefs] = useState([]);           // [{url, path, name}]
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setStream("regulab"); setMedia("image"); setSlides(false); setAngle(""); setNote(""); setRefs([]);
    setDomain(trend ? CATEGORY_TO_DOMAIN[trend.category] || "" : "");
    setTitle(trend?.title || ""); setUrl(trend?.url || "");
  }, [open, trend]);

  async function addFiles(files) {
    for (const f of files) {
      const why = refusal(f);
      if (why) { onToast(why, "warn"); continue; }
      try {
        const up = await uploadReference(user, f);
        setRefs((r) => [...r, { ...up, name: f.name }]);
      } catch (e) { onToast(e.message, "danger"); }
    }
  }

  async function dropRef(i) {
    const r = refs[i];
    setRefs((all) => all.filter((_, j) => j !== i));
    await removeReference(r.path);
  }

  // closing without sending leaves no orphan files behind
  function cancel() {
    const paths = refs.map((r) => r.path);
    setRefs([]);
    paths.forEach((p) => removeReference(p));
    onClose();
  }

  async function submit(e) {
    e.preventDefault();
    if (!title.trim()) return onToast(t("Perlukan tajuk atau isu.", "A title or an issue is needed."), "warn");
    setBusy(true);
    const row = {
      trend_id: trend?.id ?? null,
      source_title: title.trim(), source_url: url.trim() || null,
      source_name: trend?.source ?? null, source_summary: trend?.summary ?? null,
      stream, make_media: media, note: note.trim(),
      domain: stream === "regulab" ? domain || null : null,
      angle: stream === "linkedin" ? angle || null : null,
      reference_urls: refs.map((r) => r.url), status: "new", created_by: user.id,
    };
    // sent only when asked: the column arrives with supabase/006_slides.sql
    if (slides) row.make_slides = true;
    const { error } = await supabase.from(TABLES.ideas).insert(row);
    setBusy(false);
    if (error) {
      return onToast(/make_slides/.test(errText(error))
        ? t("Slaid belum disediakan dalam pangkalan data: jalankan supabase/006_slides.sql sekali, kemudian cuba lagi.",
          "Slides are not set up in the database yet: run supabase/006_slides.sql once, then try again.")
        : errText(error), "danger");
    }
    onToast(slides
      ? t("Idea dihantar. Bot akan tulis draf dan slaid, jana gambar, kemudian lukis slaid.",
        "Idea sent. The bot will write the draft and slides, generate a picture, then draw the slides.")
      : t("Idea dihantar. Bot akan baca sumber, tulis draf dan jana gambar.",
        "Idea sent. The bot will read the source, write the draft and generate a picture."), "ok");
    onDone?.();
    onClose();
  }

  const domains = Object.entries(brand.regulab.domains || {});
  const angles = Object.entries(brand.linkedin.angles || {});
  return (
    <Modal open={open} onClose={cancel} title={trend ? t("Jadikan idea", "Make an idea") : t("Idea baharu", "New idea")}>
      <form onSubmit={submit} className="space-y-3">
        {trend ? (
          <p className="rounded-tile bg-surface-2 p-3 text-sm">{trend.title}<span className="block text-[11px] text-muted">{trend.source}</span></p>
        ) : (
          <>
            <label className="block"><Label>{t("Isu / tajuk", "Issue / title")}</Label><Input value={title} onChange={(e) => setTitle(e.target.value)} required /></label>
            <label className="block"><Label hint={t("pilihan", "optional")}>{t("Pautan sumber", "Source link")}</Label><Input type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" /></label>
          </>
        )}
        <div><Label>{t("Untuk", "For")}</Label><Segmented value={stream} onChange={setStream} options={STREAMS} /></div>
        {stream === "regulab"
          ? <label className="block"><Label hint={t("kosong = bot pilih", "empty = the bot chooses")}>Domain</Label>
              <Select value={domain} onChange={setDomain} options={[["", t("Bot pilih", "Bot chooses")], ...domains]} className="w-full" /></label>
          : <label className="block"><Label hint={t("kosong = bot pilih", "empty = the bot chooses")}>{t("Sudut", "Angle")}</Label>
              <Select value={angle} onChange={setAngle} options={[["", t("Bot pilih", "Bot chooses")], ...angles.map(([k, v]) => [k, `${k} · ${v}`])]} className="w-full" /></label>}
        <div><Label>Media</Label><Segmented value={media} onChange={setMedia} options={[["image", t("Imej", "Image")], ["video", "Video"], ["none", t("Tiada", "None")]]} /></div>
        <label className="flex items-start gap-2 text-sm">
          <input type="checkbox" className="mt-1" checked={slides} onChange={(e) => setSlides(e.target.checked)} />
          <span>{t("Buat slaid carousel", "Make carousel slides")}
            <span className="block text-[11px] text-muted">
              {t("Bot tulis 5 hingga 7 slaid, kemudian lukis sendiri ({size}, tanpa AI, percuma).",
                "The bot writes 5 to 7 slides, then draws them itself ({size}, no AI, free).",
                { size: stream === "linkedin" ? "1080×1350" : "1080×1080" })}
              {media === "image" ? t(" Gambar post jadi latar slaid.", " The post picture becomes the slide background.") : ""}
            </span>
          </span>
        </label>
        <label className="block"><Label hint={t("pilihan", "optional")}>{t("Apa yang anda mahu daripada isu ini", "What you want from this issue")}</Label>
          <TextArea rows={3} value={note} onChange={(e) => setNote(e.target.value)} maxLength={1500}
            placeholder={t("Cth: fokus pada kesan kepada pengeluar kosmetik PKS; sebut Garis Panduan NPRA",
              "E.g. focus on the impact on SME cosmetic manufacturers; mention the NPRA Guidelines")} /></label>
        <div>
          <Label hint={t("pilihan · gambar anda sendiri; bot baca dan cipta semula", "optional · your own pictures; the bot reads and recreates them")}>
            {t("Rujukan", "References")}
          </Label>
          <div className="flex flex-wrap gap-2">
            {refs.map((r, i) => (
              <span key={r.path} className="relative">
                <img src={r.url} alt={r.name} className="h-16 w-16 rounded-tile object-cover" />
                <button type="button" onClick={() => dropRef(i)} aria-label={t("Buang", "Remove")} className="absolute -right-1 -top-1 rounded-full bg-ink p-0.5 text-bg"><X size={11} /></button>
              </span>
            ))}
            <label className="flex h-16 w-16 cursor-pointer items-center justify-center rounded-tile border-2 border-dashed border-line text-muted hover:border-accent">
              <ImagePlus size={18} />
              <input type="file" accept={IMAGE_TYPES.join(",")} multiple className="hidden" onChange={(e) => { addFiles([...(e.target.files || [])]); e.target.value = ""; }} />
            </label>
          </div>
          {!refs.length && media !== "none" && (
            <p className="mt-1 text-[11px] text-muted">
              {t("Tanpa rujukan: bot baca gambar pada halaman berita dan lukis gambar baharu (tidak disalin), atau lukis daripada draf.",
                "No reference: the bot reads the picture on the news page and draws a new one (not copied), or draws from the draft.")}
            </p>
          )}
        </div>
        <div className="flex justify-end gap-2 pt-1">
          <Button type="button" variant="ghost" onClick={cancel}>{t("Batal", "Cancel")}</Button>
          <Button type="submit" disabled={busy}>{busy ? t("Menghantar…", "Sending…") : t("Hantar ke bot", "Send to the bot")}</Button>
        </div>
      </form>
    </Modal>
  );
}
