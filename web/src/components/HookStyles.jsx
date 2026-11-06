import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown, ChevronUp, Loader2, Plus, RefreshCw, Save, Sparkles, Trash2, Upload, X } from "lucide-react";
import { TABLES, errText, supabase } from "../lib/SupabaseClient";
import { useTable } from "../lib/hooks";
import { useLang } from "../lib/i18n";
import { removeReference, uploadReference } from "../lib/storage";
import {
  BUILTIN, MAX_IMAGES, STATUS_CLS, STATUS_WORDS, activeId, filesRefusal, isBusy, isReady, shapesToText, summaryLine, textToShapes,
} from "../lib/hookStyles";
import Card from "./ui/Card";
import Button from "./ui/Button";
import { Input, Label, TextArea } from "./ui/Field";

/* Hook styles made from screenshots (Wan, 6 Nov 2026: "add style hook bank, I can add screenshot and bot can analyze and create the
   hook and instruction to replace current instruction when select"). Wan adds screenshots of hooks he likes; the bot reads them
   and writes an instruction and fill-in-the-blank shapes (supabase/060, backend/semasa/hook_styles.py). The style he selects as
   the default, or on one idea, REPLACES the built-in 25 and their default guidance: the writer must build every post's first line
   on one of its shapes. */

export default function HookStyles({ settings, save, onToast }) {
  const { t, lang } = useLang();
  const L = lang === "en" ? 1 : 0;
  const rows = useTable(TABLES.hookStyles, { enabled: true, order: "created_at", ascending: false, limit: 50, realtime: true, everyMs: 8000 });
  const styles = rows.rows || [];
  const missing = /hook_styles|PGRST205|42P01|does not exist/i.test(rows.error || "");
  const current = activeId(settings?.hook_style, styles);
  const [uid, setUid] = useState("");
  const [name, setName] = useState("");
  const [files, setFiles] = useState([]);
  const [busy, setBusy] = useState("");
  const [open, setOpen] = useState("");
  const [sure, setSure] = useState("");
  const fileRef = useRef(null);
  const timers = useRef([]);

  useEffect(() => {
    supabase.auth.getUser().then(({ data }) => setUid(data?.user?.id || "")).catch(() => {});
    return () => timers.current.forEach(clearTimeout);
  }, []);
  const previews = useRef(new Map());
  const previewOf = (f) => {
    if (!previews.current.has(f)) previews.current.set(f, URL.createObjectURL(f));
    return previews.current.get(f);
  };
  useEffect(() => () => previews.current.forEach((u) => URL.revokeObjectURL(u)), []);

  async function add() {
    const why = filesRefusal(files, t);
    if (why) return onToast(why, "warn");
    if (!uid) return onToast(t("Log masuk dahulu.", "Sign in first."), "warn");
    setBusy("add");
    const paths = [];
    try {
      for (const f of files) paths.push((await uploadReference({ id: uid }, f)).path);
      const { error } = await supabase.from(TABLES.hookStyles).insert({ name: name.trim(), images: paths, created_by: uid, status: "new" });
      if (error) throw new Error(errText(error));
      setName(""); setFiles([]); if (fileRef.current) fileRef.current.value = "";
      rows.reload?.();
      onToast(t("Dihantar. Bot membaca tangkapan skrin: biasanya kurang dua minit.", "Sent. The bot is reading the screenshots: usually under two minutes."), "ok");
    } catch (e) {
      await Promise.all(paths.map((p) => removeReference(p).catch(() => {})));     // nothing is left behind by a failed add
      onToast(/hook_styles|PGRST205|42P01/.test(e.message) ? t("Jalankan supabase/060_hook_styles.sql sekali dahulu.", "Run supabase/060_hook_styles.sql once first.") : e.message, "danger");
    }
    setBusy("");
  }

  async function choose(id) {
    setBusy(`use-${id}`);
    try {
      await save("hook_style", { id });
      onToast(id ? t("Gaya ini dipakai untuk semua post baharu.", "This style is now used for every new post.")
        : t("Kembali kepada 25 bentuk terbina.", "Back to the built-in 25."), "ok");
    } catch (e) { onToast(/0 rows/.test(e.message) ? t("Jalankan supabase/060_hook_styles.sql dahulu.", "Run supabase/060_hook_styles.sql first.") : e.message, "danger"); }
    setBusy("");
  }

  async function retry(s) {
    setBusy(`retry-${s.id}`);
    const { error } = await supabase.from(TABLES.hookStyles).update({ status: "new", error: null, attempts: 0, updated_at: new Date().toISOString() }).eq("id", s.id);
    setBusy("");
    if (error) return onToast(errText(error), "danger");
    rows.reload?.();
    onToast(t("Bot cuba lagi.", "The bot is trying again."), "ok");
  }

  async function remove(s) {
    if (sure !== s.id) { setSure(s.id); timers.current.push(setTimeout(() => setSure(""), 6000)); return; }
    setBusy(`del-${s.id}`);
    setSure("");
    const { error } = await supabase.from(TABLES.hookStyles).delete().eq("id", s.id);
    if (error) { setBusy(""); return onToast(errText(error), "danger"); }
    await Promise.all((s.images || []).map((p) => removeReference(p).catch(() => {})));
    if (settings?.hook_style?.id === s.id) await save("hook_style", { id: "" }).catch(() => {});   // whatever its state, the default never points at a deleted style
    setBusy("");
    rows.reload?.();
    onToast(t("Gaya dipadam, dan tangkapan skrinnya.", "Style deleted, and its screenshots."), "ok");
  }

  if (missing) {
    return (
      <Card className="p-5 text-sm text-muted" data-hook-styles>
        <h2 className="flex items-center gap-2 text-lg text-ink"><Sparkles size={16} /> {t("Gaya hook", "Hook styles")}</h2>
        <p className="mt-1">{t("Jalankan supabase/060_hook_styles.sql sekali dahulu.", "Run supabase/060_hook_styles.sql once first.")}</p>
      </Card>
    );
  }

  return (
    <Card className="space-y-4 p-5" data-hook-styles>
      <div>
        <h2 className="flex items-center gap-2 text-lg"><Sparkles size={16} /> {t("Gaya hook daripada tangkapan skrin", "Hook styles from screenshots")}</h2>
        <p className="mt-1 max-w-2xl text-[12px] text-muted">
          {t("Tambah tangkapan skrin hook yang anda suka. Bot membacanya dan menulis arahan serta bentuk hook (___ untuk setiap butiran). Gaya yang dipilih menggantikan 25 bentuk terbina: setiap post mesti bermula dengan salah satu bentuknya. Peraturan lain tetap mengatasi gaya.",
            "Add screenshots of hooks you like. The bot reads them and writes an instruction and hook shapes (___ for every specific). The style you select replaces the built-in 25: every post must open on one of its shapes. The standing rules still outrank any style.")}
        </p>
      </div>

      <ul className="space-y-2">
        <li className="flex flex-wrap items-center gap-2 rounded-tile border border-line p-3 text-sm" data-hook-style="builtin">
          <span className="font-medium">{t("25 bentuk terbina", "The built-in 25")}</span>
          <span className="text-xs text-muted">{t("lima kumpulan, panduan lalai", "five groups, the default guidance")}</span>
          <span className="ml-auto">
            {current === BUILTIN
              ? <span className="inline-flex items-center gap-1 rounded-pill bg-ok/15 px-2 py-0.5 text-xs text-ok"><Check size={12} /> {t("Dipakai", "In use")}</span>
              : <Button size="sm" variant="soft" onClick={() => choose("")} disabled={busy === "use-"}>{t("Guna ini", "Use this")}</Button>}
          </span>
        </li>
        {styles.map((s) => (
          <StyleRow key={s.id} s={s} L={L} t={t} inUse={current === s.id} open={open === s.id} sure={sure === s.id} busy={busy}
            onOpen={() => setOpen(open === s.id ? "" : s.id)} onUse={() => choose(s.id)} onRetry={() => retry(s)} onDelete={() => remove(s)}
            onSaved={() => { rows.reload?.(); onToast(t("Gaya disimpan.", "Style saved."), "ok"); }} onError={(m) => onToast(m, "danger")} onWarn={(m) => onToast(m, "warn")} />
        ))}
        {!styles.length && !rows.loading && <li className="text-xs text-muted" data-hook-empty>{t("Belum ada gaya anda. Tambah satu di bawah.", "No styles of yours yet. Add one below.")}</li>}
      </ul>

      <div className="space-y-2 rounded-tile border border-dashed border-line p-3" data-hook-add>
        <p className="text-sm font-medium">{t("Tambah gaya", "Add a style")}</p>
        <label className="block"><Label hint={t("pilihan: bot beri nama jika kosong", "optional: the bot names it if empty")}>{t("Nama", "Name")}</Label>
          <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={60} placeholder={t("Cth: Pengakuan santai", "E.g. Casual admission")} /></label>
        <label className="block"><Label hint={t(`sehingga ${MAX_IMAGES}; PNG, JPG, WEBP`, `up to ${MAX_IMAGES}; PNG, JPG, WEBP`)}>{t("Tangkapan skrin hook", "Hook screenshots")}</Label>
          <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp,image/gif" multiple data-hook-files
            onChange={(e) => setFiles(Array.from(e.target.files || []).slice(0, MAX_IMAGES + 1))} className="block w-full text-xs" /></label>
        {files.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {files.map((f, i) => (
              <span key={`${f.name}-${i}`} className="relative">
                <img src={previewOf(f)} alt={f.name} className="h-16 w-16 rounded-tile border border-line object-cover" />
                <button type="button" aria-label={t("Buang", "Remove")} onClick={() => setFiles(files.filter((_, j) => j !== i))}
                  className="absolute -right-1 -top-1 rounded-full bg-surface p-0.5 shadow"><X size={12} /></button>
              </span>
            ))}
          </div>
        )}
        <Button size="sm" onClick={add} disabled={busy === "add" || !files.length}>
          {busy === "add" ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />} {t("Analisis dan buat gaya", "Analyse and make the style")}
        </Button>
        <p className="flex items-start gap-1 text-[11.5px] text-muted"><Upload size={12} className="mt-0.5 shrink-0" /> {t("Bentuk hook ialah corak, bukan ayat orang lain: bot menggantikan setiap butiran dengan ___ dan tidak menyalin ayat contoh. Tangkapan skrin disimpan dalam folder anda sahaja.", "A shape is a pattern, not somebody else's sentence: the bot turns every specific into ___ and never copies an example. The screenshots stay in your own folder only.")}</p>
      </div>
    </Card>
  );
}

function StyleRow({ s, L, t, inUse, open, sure, busy, onOpen, onUse, onRetry, onDelete, onSaved, onError, onWarn }) {
  const [name, setName] = useState(s.name || "");
  const [instruction, setInstruction] = useState(s.instruction || "");
  const [shapes, setShapes] = useState(shapesToText(s.shapes));
  const [saving, setSaving] = useState(false);
  // a row the bot has just finished fills the editor; an edit in progress is never overwritten by a poll
  const sig = JSON.stringify([s.name, s.instruction, s.shapes, s.status]);
  const seen = useRef(sig);
  useEffect(() => {
    if (seen.current !== sig && !open) { setName(s.name || ""); setInstruction(s.instruction || ""); setShapes(shapesToText(s.shapes)); }
    seen.current = sig;
  }, [sig]); // eslint-disable-line react-hooks/exhaustive-deps

  async function saveEdit() {
    const parsed = textToShapes(shapes);
    if (parsed.shapes.length < 3) return onWarn(t("Perlu sekurang-kurangnya 3 bentuk, setiap satu dengan ___.", "At least 3 shapes are needed, each with a ___."));
    if (parsed.bad.length) onWarn(t(`${parsed.bad.length} baris tanpa ___ dibuang.`, `${parsed.bad.length} line(s) without a ___ were dropped.`));
    setSaving(true);
    const { error } = await supabase.from(TABLES.hookStyles).update({
      name: name.trim() || s.name, instruction: instruction.trim().slice(0, 2000), shapes: parsed.shapes, updated_at: new Date().toISOString(),
    }).eq("id", s.id);
    setSaving(false);
    if (error) return onError(errText(error));
    setShapes(shapesToText(parsed.shapes));
    onSaved();
  }

  return (
    <li className="rounded-tile border border-line p-3 text-sm" data-hook-style={s.id} data-status={s.status}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{s.name || t("Gaya tanpa nama", "Unnamed style")}</span>
        <span className={`rounded-pill px-2 py-0.5 text-xs ${STATUS_CLS[s.status] || ""}`}>
          {isBusy(s) && <Loader2 size={11} className="mr-1 inline animate-spin" />}{(STATUS_WORDS[s.status] || [s.status, s.status])[L]}
        </span>
        <span className="text-xs text-muted break-words" data-hook-line>{summaryLine(s, t)}</span>
        <span className="ml-auto flex flex-wrap items-center gap-2">
          {inUse && <span className="inline-flex items-center gap-1 rounded-pill bg-ok/15 px-2 py-0.5 text-xs text-ok"><Check size={12} /> {t("Dipakai", "In use")}</span>}
          {isReady(s) && !inUse && <Button size="sm" variant="soft" onClick={onUse} disabled={busy === `use-${s.id}`}>{t("Guna sebagai lalai", "Use as default")}</Button>}
          {s.status === "error" && <Button size="sm" variant="soft" onClick={onRetry} disabled={busy === `retry-${s.id}`}><RefreshCw size={12} /> {t("Cuba lagi", "Try again")}</Button>}
          {s.status === "ready" && <Button size="sm" variant="ghost" onClick={onOpen} aria-label={t("Ubah", "Edit")}>{open ? <ChevronUp size={13} /> : <ChevronDown size={13} />} {t("Ubah", "Edit")}</Button>}
          <Button size="sm" variant="danger" onClick={onDelete} disabled={busy === `del-${s.id}`}><Trash2 size={12} /> {sure ? t("Pasti? Klik lagi", "Sure? Click again") : t("Padam", "Delete")}</Button>
        </span>
      </div>
      {s.status === "ready" && s.summary && !open && <p className="mt-1 text-xs text-muted">{s.summary}</p>}
      {s.status === "ready" && s.error && !open && <p className="mt-1 text-xs text-warn">{s.error}</p>}
      {open && (
        <div className="mt-3 space-y-2" data-hook-editor>
          <label className="block"><Label>{t("Nama", "Name")}</Label><Input value={name} onChange={(e) => setName(e.target.value)} maxLength={60} /></label>
          <label className="block"><Label hint={t("menggantikan panduan lalai penulis", "replaces the writer's default guidance")}>{t("Arahan gaya", "Style instruction")}</Label>
            <TextArea rows={5} value={instruction} onChange={(e) => setInstruction(e.target.value)} maxLength={2000} /></label>
          <label className="block"><Label hint={t("satu bentuk setiap baris, ___ untuk butiran; boleh tulis \"bold | ...\"", "one shape a line, ___ for a specific; you may write \"bold | ...\"")}>{t("Bentuk hook", "Hook shapes")}</Label>
            <TextArea rows={8} value={shapes} onChange={(e) => setShapes(e.target.value)} spellCheck={false} className="font-mono text-xs" /></label>
          <Button size="sm" onClick={saveEdit} disabled={saving}>{saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />} {t("Simpan gaya", "Save style")}</Button>
        </div>
      )}
    </li>
  );
}
