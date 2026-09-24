import { useCallback, useRef, useState } from "react";
import { motion } from "framer-motion";
import { Film, Image as ImageIcon, UploadCloud } from "lucide-react";
import { BUCKETS, TABLES, errText, supabase } from "../lib/SupabaseClient";
import { bytesText } from "../lib/format";
import Button from "./ui/Button";
import Card from "./ui/Card";

const ACCEPT = ["image/png", "image/jpeg", "image/webp", "image/gif", "text/plain", "text/markdown", "application/pdf"];
const MAX_BYTES = 50 * 1024 * 1024;
const PROVIDERS = [
  { id: "", label: "Lalai (tetapan runner)" },
  { id: "replicate", label: "Replicate" },
  { id: "openai", label: "OpenAI" },
];

function safeName(name) {
  return name.normalize("NFKD").replace(/[^\w.\-]+/g, "-").replace(/-+/g, "-").slice(-80);
}

/* Drag a reference in → it lands in Storage under <uid>/… → one `pending` row is inserted →
   the Supabase trigger fires repository_dispatch → the runner generates and writes the URL back.
   Everything after the insert is the backend's; this component's job ends at the row. */
export default function MediaUploader({ user, onToast, onQueued }) {
  const [file, setFile] = useState(null);
  const [type, setType] = useState("image");
  const [provider, setProvider] = useState("");
  const [prompt, setPrompt] = useState("");
  const [drag, setDrag] = useState(false);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState("");
  const inputRef = useRef(null);

  const take = useCallback((f) => {
    if (!f) return;
    if (!ACCEPT.includes(f.type)) return onToast(`Jenis fail ${f.type || "tidak dikenali"} tidak disokong.`, "warn");
    if (f.size > MAX_BYTES) return onToast(`Fail melebihi ${bytesText(MAX_BYTES)}.`, "warn");
    setFile(f);
  }, [onToast]);

  async function submit(e) {
    e.preventDefault();
    if (!file || !prompt.trim()) return onToast("Perlukan fail rujukan dan prompt.", "warn");
    setBusy(true);
    try {
      const path = `${user.id}/${Date.now()}-${safeName(file.name)}`;
      setProgress("Memuat naik rujukan…");
      const up = await supabase.storage.from(BUCKETS.reference).upload(path, file, { contentType: file.type, upsert: false });
      if (up.error) throw new Error(errText(up.error));
      const { data: pub } = supabase.storage.from(BUCKETS.reference).getPublicUrl(path);

      setProgress("Mendaftar kerja…");
      const row = {
        reference_url: pub.publicUrl,
        reference_path: path,
        type,
        prompt: prompt.trim(),
        provider: provider || null,
        status: "pending",
        created_by: user.id,
        meta: { original_name: file.name, size: file.size, mime: file.type },
      };
      const ins = await supabase.from(TABLES.media).insert(row).select().single();
      if (ins.error) {
        await supabase.storage.from(BUCKETS.reference).remove([path]); // no orphan file for a row that never existed
        throw new Error(errText(ins.error));
      }
      onToast("Dalam giliran. Runner akan mula dalam beberapa saat hingga 15 minit.", "ok");
      onQueued?.(ins.data);
      setFile(null); setPrompt("");
      if (inputRef.current) inputRef.current.value = "";
    } catch (err) {
      onToast(err.message || String(err), "danger");
    } finally {
      setBusy(false); setProgress("");
    }
  }

  return (
    <Card as="form" onSubmit={submit} className="p-5 sm:p-6">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-lg">Jana media daripada rujukan</h3>
          <p className="mt-1 text-sm text-muted">Muat naik gambar rujukan, tulis apa yang mahu, pilih imej atau video.</p>
        </div>
        <div className="flex rounded-pill bg-surface-2 p-1 text-xs">
          {[["image", ImageIcon, "Imej"], ["video", Film, "Video"]].map(([v, Icon, l]) => (
            <button type="button" key={v} onClick={() => setType(v)}
              className={`flex items-center gap-1 rounded-pill px-3 py-1.5 ${type === v ? "bg-surface text-ink shadow-card" : "text-muted"}`}>
              <Icon size={13} /> {l}
            </button>
          ))}
        </div>
      </div>

      <motion.label
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); take(e.dataTransfer.files?.[0]); }}
        animate={{ scale: drag ? 1.01 : 1 }}
        className={`mt-5 flex cursor-pointer flex-col items-center justify-center gap-2 rounded-card border-2 border-dashed p-8 text-center transition
          ${drag ? "border-accent bg-accent/5" : "border-line bg-bg hover:border-accent/60"}`}
      >
        <input ref={inputRef} type="file" accept={ACCEPT.join(",")} className="hidden" onChange={(e) => take(e.target.files?.[0])} />
        <UploadCloud size={26} className="text-accent" />
        {file ? (
          <>
            <span className="text-sm font-medium">{file.name}</span>
            <span className="text-xs text-muted">{bytesText(file.size)} · {file.type}</span>
            {file.type.startsWith("image/") && (
              <img src={URL.createObjectURL(file)} alt="" className="mt-2 max-h-48 rounded-tile object-contain" />
            )}
          </>
        ) : (
          <>
            <span className="text-sm font-medium">Seret fail ke sini, atau klik</span>
            <span className="text-xs text-muted">PNG · JPG · WEBP · GIF · PDF · TXT · sehingga {bytesText(MAX_BYTES)}</span>
          </>
        )}
      </motion.label>

      <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={3} maxLength={2000}
        placeholder={type === "video" ? "Cth: gerakkan kamera perlahan ke kanan, cahaya pagi, gaya iklan skincare…"
          : "Cth: jadikan latar makmal bersih, warna biru muda, kekalkan botol produk seperti asal…"}
        className="mt-4 w-full resize-y rounded-tile border border-line bg-bg p-3 text-sm outline-none focus:border-accent" />

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <select value={provider} onChange={(e) => setProvider(e.target.value)}
          className="rounded-pill border border-line bg-surface px-3 py-2 text-xs text-ink outline-none">
          {PROVIDERS.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
        </select>
        <span className="text-xs text-muted">{progress}</span>
        <Button type="submit" className="ml-auto" disabled={busy || !file || !prompt.trim()}>
          {busy ? "Menghantar…" : `Jana ${type === "video" ? "video" : "imej"}`}
        </Button>
      </div>
    </Card>
  );
}
