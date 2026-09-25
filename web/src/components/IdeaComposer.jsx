import { useEffect, useState } from "react";
import { ImagePlus, X } from "lucide-react";
import { TABLES, errText, supabase } from "../lib/SupabaseClient";
import { CATEGORY_TO_DOMAIN, STREAMS } from "../lib/brand";
import { IMAGE_TYPES, refusal, removeReference, uploadReference } from "../lib/storage";
import Button from "./ui/Button";
import { Input, Label, Modal, Segmented, Select, TextArea } from "./ui/Field";

/* Flow A, step one. From a headline ("Jadikan idea") or by hand. Inserting the row is all the
   page does: the worker reads the source, writes the draft and queues the pictures. */
export default function IdeaComposer({ open, onClose, trend, user, brand, onToast, onDone }) {
  const [stream, setStream] = useState("regulab");
  const [media, setMedia] = useState("image");
  const [domain, setDomain] = useState("");
  const [angle, setAngle] = useState("");
  const [note, setNote] = useState("");
  const [title, setTitle] = useState("");
  const [url, setUrl] = useState("");
  const [refs, setRefs] = useState([]);           // [{url, path, name}]
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setStream("regulab"); setMedia("image"); setAngle(""); setNote(""); setRefs([]);
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
    if (!title.trim()) return onToast("Perlukan tajuk atau isu.", "warn");
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
    const { error } = await supabase.from(TABLES.ideas).insert(row);
    setBusy(false);
    if (error) return onToast(errText(error), "danger");
    onToast("Idea dihantar. Bot akan baca sumber, tulis draf dan jana gambar.", "ok");
    onDone?.();
    onClose();
  }

  const domains = Object.entries(brand.regulab.domains || {});
  const angles = Object.entries(brand.linkedin.angles || {});
  return (
    <Modal open={open} onClose={cancel} title={trend ? "Jadikan idea" : "Idea baharu"}>
      <form onSubmit={submit} className="space-y-3">
        {trend ? (
          <p className="rounded-tile bg-surface-2 p-3 text-sm">{trend.title}<span className="block text-[11px] text-muted">{trend.source}</span></p>
        ) : (
          <>
            <label className="block"><Label>Isu / tajuk</Label><Input value={title} onChange={(e) => setTitle(e.target.value)} required /></label>
            <label className="block"><Label hint="pilihan">Pautan sumber</Label><Input type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" /></label>
          </>
        )}
        <div><Label>Untuk</Label><Segmented value={stream} onChange={setStream} options={STREAMS} /></div>
        {stream === "regulab"
          ? <label className="block"><Label hint="kosong = bot pilih">Domain</Label>
              <Select value={domain} onChange={setDomain} options={[["", "Bot pilih"], ...domains]} className="w-full" /></label>
          : <label className="block"><Label hint="kosong = bot pilih">Sudut</Label>
              <Select value={angle} onChange={setAngle} options={[["", "Bot pilih"], ...angles.map(([k, v]) => [k, `${k} · ${v}`])]} className="w-full" /></label>}
        <div><Label>Media</Label><Segmented value={media} onChange={setMedia} options={[["image", "Imej"], ["video", "Video"], ["none", "Tiada"]]} /></div>
        <label className="block"><Label hint="pilihan">Apa yang anda mahu daripada isu ini</Label>
          <TextArea rows={3} value={note} onChange={(e) => setNote(e.target.value)} maxLength={1500}
            placeholder="Cth: fokus pada kesan kepada pengeluar kosmetik PKS; sebut Garis Panduan NPRA" /></label>
        <div>
          <Label hint="pilihan · gambar anda sendiri; bot baca dan cipta semula">Rujukan</Label>
          <div className="flex flex-wrap gap-2">
            {refs.map((r, i) => (
              <span key={r.path} className="relative">
                <img src={r.url} alt={r.name} className="h-16 w-16 rounded-tile object-cover" />
                <button type="button" onClick={() => dropRef(i)} aria-label="Buang" className="absolute -right-1 -top-1 rounded-full bg-ink p-0.5 text-bg"><X size={11} /></button>
              </span>
            ))}
            <label className="flex h-16 w-16 cursor-pointer items-center justify-center rounded-tile border-2 border-dashed border-line text-muted hover:border-accent">
              <ImagePlus size={18} />
              <input type="file" accept={IMAGE_TYPES.join(",")} multiple className="hidden" onChange={(e) => { addFiles([...(e.target.files || [])]); e.target.value = ""; }} />
            </label>
          </div>
          {!refs.length && media !== "none" && (
            <p className="mt-1 text-[11px] text-muted">Tanpa rujukan: bot baca gambar pada halaman berita dan lukis gambar baharu (tidak disalin), atau lukis daripada draf.</p>
          )}
        </div>
        <div className="flex justify-end gap-2 pt-1">
          <Button type="button" variant="ghost" onClick={cancel}>Batal</Button>
          <Button type="submit" disabled={busy}>{busy ? "Menghantar…" : "Hantar ke bot"}</Button>
        </div>
      </form>
    </Modal>
  );
}
