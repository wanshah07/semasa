import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import { BookmarkPlus, Film, Image as ImageIcon, UploadCloud } from "lucide-react";
import { TABLES, errText, supabase } from "../lib/SupabaseClient";
import { bytesText } from "../lib/format";
import { useLang } from "../lib/i18n";
import { IMAGE_TYPES, MAX_BYTES, refusal, removeReference, uploadReference } from "../lib/storage";
import Button from "./ui/Button";
import Card from "./ui/Card";
import { Input, Segmented, Select } from "./ui/Field";

export const providersOf = (t) => [
  { id: "", label: t("Lalai (tetapan runner)", "Default (runner setting)") },
  { id: "replicate", label: "Replicate" },
  { id: "openai", label: "OpenAI" },
  { id: "cloudflare", label: t("Cloudflare (gambar sahaja, percuma)", "Cloudflare (pictures only, free)") },
];

/* Unsplash sits in the same menu (Wan, 26 Sep 2026: "why still no unsplashed", looking for it here): it does not
   generate, it searches Unsplash for the words and offers 12 free photos under Results, one click to keep one
   (backend/semasa/unsplash.py). Not in providersOf, because a failed generation cannot be retried "on Unsplash". */
const UNSPLASH = "unsplash";

/* Flow B. Two ways in:
     Prompt sahaja   words only → an image (or a still, then a video)
     Rujukan         a picture of yours → the bot READS it (describes it), then recreates it
                     with your words as the changes
   Tick "Simpan prompt" to keep the words (and the reference) in the library for next time.
   Everything after the insert is the runner's; this component's job ends at the row. */
export default function MediaUploader({ user, onToast, onQueued, preset, onPresetUsed }) {
  const { t } = useLang();
  const [mode, setMode] = useState("prompt");
  const [file, setFile] = useState(null);
  const [savedRef, setSavedRef] = useState(null);     // {url, path} from a library prompt
  const [type, setType] = useState("image");
  const [provider, setProvider] = useState("");
  const [orientation, setOrientation] = useState("squarish");
  const [prompt, setPrompt] = useState("");
  const [keep, setKeep] = useState(false);
  const [keepTitle, setKeepTitle] = useState("");
  const [drag, setDrag] = useState(false);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState("");
  const [fromPrompt, setFromPrompt] = useState(null);  // the library row this job was started from
  const inputRef = useRef(null);
  const preview = useMemo(() => (file ? URL.createObjectURL(file) : ""), [file]);
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);

  useEffect(() => {
    if (!preset) return;
    setPrompt(preset.prompt || ""); setType(preset.type || "image"); setFile(null);
    if (preset.reference_url) { setMode("recreate"); setSavedRef({ url: preset.reference_url, path: preset.reference_path }); }
    else { setMode("prompt"); setSavedRef(null); }
    setKeep(false); setFromPrompt({ id: preset.id, uses: preset.uses || 0, prompt: (preset.prompt || "").trim() });
    onPresetUsed?.();
  }, [preset, onPresetUsed]);

  const take = useCallback((f) => {
    if (!f) return;
    const why = refusal(f);
    if (why) return onToast(why, "warn");
    setFile(f); setSavedRef(null); setMode("recreate");
  }, [onToast]);

  const unsplash = provider === UNSPLASH;
  // a search is words only and a still picture: choosing Unsplash sets both, leaving either unchooses Unsplash
  const chooseProvider = (v) => { setProvider(v); if (v === UNSPLASH) { setMode("prompt"); setType("image"); } };
  const chooseMode = (v) => { setMode(v); if (v === "recreate" && unsplash) setProvider(""); };
  const chooseType = (v) => { setType(v); if (v === "video" && unsplash) setProvider(""); };
  const needsRef = mode === "recreate";
  const hasRef = Boolean(file || savedRef);
  const cfVideo = provider === "cloudflare" && type === "video";   // Cloudflare's free neurons draw pictures only
  const ready = prompt.trim() && (!needsRef || hasRef) && !cfVideo;

  async function searchUnsplash() {
    setBusy(true);
    const words = prompt.trim().slice(0, 120);
    const { data, error } = await supabase.from(TABLES.media).insert({
      mode: "prompt", type: "image", provider: UNSPLASH, prompt: words, status: "pending", created_by: user.id,
      meta: { flow: "unsplash", orientation, alt: words },
    }).select().single();
    setBusy(false);
    if (error) return onToast(errText(error), "danger");
    onToast(t("Carian dihantar. 12 foto muncul di Hasil dalam kira-kira seminit: klik satu untuk guna.",
      "Search sent. 12 photos appear under Results in about a minute: click one to use it."), "ok");
    onQueued?.(data);
    setPrompt(""); setFromPrompt(null);
  }

  async function submit(e) {
    e.preventDefault();
    if (unsplash) {
      if (!prompt.trim()) return onToast(t("Tulis perkataan carian dahulu.", "Type what to search for first."), "warn");
      return searchUnsplash();
    }
    if (!ready) return onToast(needsRef ? t("Perlukan gambar rujukan dan prompt.", "Needs a reference picture and a prompt.")
      : t("Perlukan prompt.", "Needs a prompt."), "warn");
    setBusy(true);
    let uploaded = null;
    try {
      let ref = needsRef ? savedRef : null;
      if (needsRef && file) {
        setProgress(t("Memuat naik rujukan…", "Uploading reference…"));
        uploaded = await uploadReference(user, file);
        ref = uploaded;
      }
      // linked to the library row only while its words are still the ones being sent
      const linked = fromPrompt && fromPrompt.prompt === prompt.trim() ? fromPrompt : null;
      let promptId = linked?.id ?? null;
      if (keep) {
        setProgress(t("Menyimpan prompt…", "Saving prompt…"));
        const saved = await supabase.from(TABLES.prompts).insert({
          title: keepTitle.trim() || prompt.trim().slice(0, 60), prompt: prompt.trim(), type,
          reference_url: ref?.url ?? null, reference_path: ref?.path ?? null, created_by: user.id,
        }).select("id").single();
        if (saved.error) throw new Error(errText(saved.error));
        promptId = saved.data.id;
      }
      setProgress(t("Mendaftar kerja…", "Registering job…"));
      const row = {
        // a reference kept in the library belongs to the library, not to this job: deleting the
        // job must not delete the file a saved prompt still points at
        mode, reference_url: ref?.url ?? null, reference_path: keep ? null : uploaded?.path ?? null, type,
        prompt: prompt.trim(), provider: provider || null, status: "pending", created_by: user.id, prompt_id: promptId,
        meta: { flow: "B", ...(file ? { original_name: file.name, size: file.size, mime: file.type } : {}) },
      };
      const ins = await supabase.from(TABLES.media).insert(row).select().single();
      if (ins.error) throw new Error(errText(ins.error));
      if (promptId && !keep) {
        await supabase.from(TABLES.prompts).update({ uses: (linked?.uses || 0) + 1 }).eq("id", promptId);
      }
      onToast(t("Dalam giliran. Runner mula dalam beberapa saat hingga 15 minit.", "Queued. The runner starts within a few seconds to 15 minutes."), "ok");
      onQueued?.(ins.data);
      setFile(null); setPrompt(""); setSavedRef(null); setKeep(false); setKeepTitle(""); setFromPrompt(null);
      if (inputRef.current) inputRef.current.value = "";
    } catch (err) {
      if (uploaded && !keep) await removeReference(uploaded.path);   // no orphan for a job that never existed
      onToast(err.message || String(err), "danger");
    } finally {
      setBusy(false); setProgress("");
    }
  }

  return (
    <Card as="form" onSubmit={submit} className="p-5 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-lg">{t("Jana imej atau video", "Generate an image or video")}</h3>
          <p className="mt-1 text-sm text-muted">
            {t("Tulis prompt sahaja, atau muat naik rujukan: bot membacanya dan mencipta semula.",
              "Write a prompt only, or upload a reference: the bot reads it and recreates it.")}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Segmented value={mode} onChange={chooseMode} options={[["prompt", t("Prompt sahaja", "Prompt only")], ["recreate", t("Rujukan + prompt", "Reference + prompt")]]} />
          <div className="flex rounded-pill bg-surface-2 p-1 text-xs">
            {[["image", ImageIcon, t("Imej", "Image")], ["video", Film, "Video"]].map(([v, Icon, l]) => (
              <button type="button" key={v} onClick={() => chooseType(v)}
                className={`flex items-center gap-1 rounded-pill px-3 py-1.5 ${type === v ? "bg-surface text-ink shadow-card" : "text-muted"}`}>
                <Icon size={13} /> {l}
              </button>
            ))}
          </div>
        </div>
      </div>

      {needsRef && (
        <motion.label
          onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => { e.preventDefault(); setDrag(false); take(e.dataTransfer.files?.[0]); }}
          animate={{ scale: drag ? 1.01 : 1 }}
          className={`mt-5 flex cursor-pointer flex-col items-center justify-center gap-2 rounded-card border-2 border-dashed p-8 text-center transition
            ${drag ? "border-accent bg-accent/5" : "border-line bg-bg hover:border-accent/60"}`}
        >
          <input ref={inputRef} type="file" accept={IMAGE_TYPES.join(",")} className="hidden" onChange={(e) => take(e.target.files?.[0])} />
          <UploadCloud size={26} className="text-accent" />
          {file || savedRef ? (
            <>
              <span className="text-sm font-medium">{file ? file.name : t("Rujukan daripada pustaka prompt", "Reference from the prompt library")}</span>
              {file && <span className="text-xs text-muted">{bytesText(file.size)} · {file.type}</span>}
              <img src={preview || savedRef?.url} alt="" className="mt-2 max-h-48 rounded-tile object-contain" />
            </>
          ) : (
            <>
              <span className="text-sm font-medium">{t("Seret gambar ke sini, atau klik", "Drag a picture here, or click")}</span>
              <span className="text-xs text-muted">PNG · JPG · WEBP · GIF · {t("sehingga {max}", "up to {max}", { max: bytesText(MAX_BYTES) })}</span>
            </>
          )}
        </motion.label>
      )}

      <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={3} maxLength={2000} aria-label="Prompt"
        placeholder={unsplash
          ? t("Cari foto Unsplash (perkataan Inggeris lebih tepat), cth: cosmetic laboratory, halal food market…",
            "Search Unsplash photos, e.g. cosmetic laboratory, halal food market…")
          : needsRef
          ? t("Apa yang mahu diubah? Cth: latar makmal bersih, warna biru muda, kekalkan botol seperti asal…",
            "What should change? E.g. clean lab background, light blue, keep the bottle as it is…")
          : type === "video" ? t("Cth: botol serum di atas marmar, kamera bergerak perlahan ke kanan, cahaya pagi…",
            "E.g. serum bottle on marble, camera moving slowly to the right, morning light…")
            : t("Cth: botol serum kaca di atas marmar putih, cahaya lembut dari tingkap, gaya fotografi produk…",
              "E.g. glass serum bottle on white marble, soft window light, product photography style…")}
        className="mt-4 w-full resize-y rounded-tile border border-line bg-bg p-3 text-sm outline-none focus:border-accent" />

      {!unsplash && <div className="mt-3 flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-xs text-muted">
          <input type="checkbox" checked={keep} onChange={(e) => setKeep(e.target.checked)} />
          <BookmarkPlus size={13} /> {t("Simpan prompt", "Save prompt")}
        </label>
        {keep && <Input value={keepTitle} onChange={(e) => setKeepTitle(e.target.value)} placeholder={t("Nama (pilihan)", "Name (optional)")} className="max-w-xs" />}
      </div>}

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <select value={provider} onChange={(e) => chooseProvider(e.target.value)} aria-label={t("Penyedia", "Provider")}
          className="max-w-full rounded-pill border border-line bg-surface px-3 py-2 text-xs text-ink outline-none">
          {providersOf(t).map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
          <option value={UNSPLASH}>{t("Unsplash (cari foto percuma)", "Unsplash (search free photos)")}</option>
        </select>
        {unsplash && (
          <Select value={orientation} onChange={setOrientation} aria-label={t("Orientasi", "Orientation")}
            options={[["squarish", t("Segi empat", "Square")], ["portrait", t("Potret", "Portrait")], ["landscape", t("Landskap", "Landscape")]]} />
        )}
        <span className="text-xs text-muted">{cfVideo
          ? t("Cloudflare buat gambar sahaja: pilih Replicate atau OpenAI untuk video", "Cloudflare makes pictures only: choose Replicate or OpenAI for a video")
          : unsplash ? t("Foto sebenar, bukan AI. Jurugambar dikreditkan.", "Real photos, not AI. The photographer is credited.") : progress}</span>
        <Button type="submit" className="ml-auto" disabled={busy || (unsplash ? !prompt.trim() : !ready)}>
          {busy ? t("Menghantar…", "Sending…") : unsplash ? t("Cari di Unsplash", "Search Unsplash")
            : type === "video" ? t("Jana video", "Generate video") : t("Jana imej", "Generate image")}
        </Button>
      </div>
    </Card>
  );
}
