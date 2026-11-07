import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { Check, ChevronDown, ChevronUp, Link2, Loader2, PenLine, Plus, RefreshCw, Save, Trash2, Upload, X } from "lucide-react";
import { fadeUp } from "../design/motion";
import { TABLES, errText, supabase } from "../lib/SupabaseClient";
import { useTable } from "../lib/hooks";
import { useLang } from "../lib/i18n";
import { removeReference, uploadReference } from "../lib/storage";
import {
  MAX_IMAGES, MAX_LINKS, MAX_SAMPLE, NONE, STATUS_CLS, STATUS_WORDS, activeId, addRefusal, isBusy, isReady, linksFrom, sourcesLine,
  summaryLine, textToTraits, traitsToText,
} from "../lib/writingStyles";
import Card from "../components/ui/Card";
import Button from "../components/ui/Button";
import { Input, Label, TextArea } from "../components/ui/Field";
import { WriterSettings } from "./SettingsTab";

/* Gaya penulisan (Wan, 11 Oct 2026, Phase 4: "writing style bank, asing dan boleh pilih; aku upload link post viral, AI analyse
   dan terjemah jadi gaya penulisan"). Apart from the hook: how the whole caption reads. Wan adds viral posts (links, pasted text,
   screenshots) and the bot writes the style (supabase/067, backend/semasa/writing_styles.py), or he writes one himself. The style
   chosen as the default, or on one idea, is added to the caption writer's prompt (and a Motion film's script) after every rule. */
export default function WritingStylesTab({ settings, save, onToast }) {
  const { t, lang } = useLang();
  const L = lang === "en" ? 1 : 0;
  const rows = useTable(TABLES.writingStyles, { enabled: true, order: "created_at", ascending: false, limit: 50, realtime: true, everyMs: 8000 });
  const styles = rows.rows || [];
  const missing = /writing_styles|PGRST205|42P01|does not exist/i.test(rows.error || "");
  const current = activeId(settings?.writing_style, styles);
  const [uid, setUid] = useState("");
  const [mode, setMode] = useState("analyse");
  const [name, setName] = useState("");
  const [linksText, setLinksText] = useState("");
  const [sample, setSample] = useState("");
  const [files, setFiles] = useState([]);
  const [mInstruction, setMInstruction] = useState("");
  const [mTraits, setMTraits] = useState("");
  const [busy, setBusy] = useState("");
  const [open, setOpen] = useState("");
  const [sure, setSure] = useState("");
  const fileRef = useRef(null);
  const timers = useRef([]);
  const previews = useRef(new Map());
  const previewOf = (f) => { if (!previews.current.has(f)) previews.current.set(f, URL.createObjectURL(f)); return previews.current.get(f); };

  useEffect(() => {
    supabase.auth.getUser().then(({ data }) => setUid(data?.user?.id || "")).catch(() => {});
    const urls = previews.current;
    return () => { timers.current.forEach(clearTimeout); urls.forEach((u) => URL.revokeObjectURL(u)); };
  }, []);

  const parsed = linksFrom(linksText);
  const migrate = t("Jalankan supabase/067_hook_bank_writing_styles.sql sekali dahulu.", "Run supabase/067_hook_bank_writing_styles.sql once first.");

  async function addAnalyse() {
    const why = parsed.bad.length ? t(`Bukan pautan: ${parsed.bad.slice(0, 2).join(", ")}`, `Not a link: ${parsed.bad.slice(0, 2).join(", ")}`)
      : parsed.over ? t(`Paling banyak ${MAX_LINKS} pautan.`, `At most ${MAX_LINKS} links.`) : addRefusal({ links: parsed.links, sample, files }, t);
    if (why) return onToast(why, "warn");
    if (!uid) return onToast(t("Log masuk dahulu.", "Sign in first."), "warn");
    setBusy("add");
    const paths = [];
    try {
      for (const f of files) paths.push((await uploadReference({ id: uid }, f)).path);
      const { error } = await supabase.from(TABLES.writingStyles).insert({ name: name.trim().slice(0, 60), source: "analyse", status: "new",
        links: parsed.links, sample: sample.trim(), images: paths, created_by: uid });
      if (error) throw new Error(errText(error));
      setName(""); setLinksText(""); setSample(""); setFiles([]); if (fileRef.current) fileRef.current.value = "";
      rows.reload?.();
      onToast(t("Dihantar. Bot membaca post: biasanya kurang dua minit.", "Sent. The bot is reading the posts: usually under two minutes."), "ok");
    } catch (e) {
      await Promise.all(paths.map((p) => removeReference(p).catch(() => {})));
      onToast(/writing_styles|PGRST205|42P01/.test(e.message) ? migrate : e.message, "danger");
    }
    setBusy("");
  }

  async function addManual() {
    if (mInstruction.trim().length < 20) return onToast(t("Tulis arahan sekurang-kurangnya 20 aksara.", "Write an instruction of at least 20 characters."), "warn");
    if (!uid) return onToast(t("Log masuk dahulu.", "Sign in first."), "warn");
    setBusy("manual");
    const { error } = await supabase.from(TABLES.writingStyles).insert({ name: name.trim().slice(0, 60) || t("Gaya saya", "My style"), source: "manual", status: "ready",
      instruction: mInstruction.trim().slice(0, 2000), traits: textToTraits(mTraits), created_by: uid });
    setBusy("");
    if (error) return onToast(/writing_styles|PGRST205|42P01/.test(errText(error)) ? migrate : errText(error), "danger");
    setName(""); setMInstruction(""); setMTraits("");
    rows.reload?.();
    onToast(t("Gaya disimpan. Tekan \"Guna sebagai lalai\" untuk memakainya.", "Style saved. Press \"Use as default\" to apply it."), "ok");
  }

  async function choose(id) {
    setBusy(`use-${id}`);
    try {
      await save("writing_style", { id });
      onToast(id ? t("Gaya ini dipakai untuk semua post baharu.", "This style is now used for every new post.") : t("Tiada gaya: gaya rumah sahaja.", "No style: the house style alone."), "ok");
    } catch (e) { onToast(/0 rows/.test(e.message) ? migrate : e.message, "danger"); }
    setBusy("");
  }

  async function retry(s) {
    setBusy(`retry-${s.id}`);
    const { error } = await supabase.from(TABLES.writingStyles).update({ status: "new", error: null, attempts: 0 }).eq("id", s.id);
    setBusy("");
    if (error) return onToast(errText(error), "danger");
    rows.reload?.();
    onToast(t("Bot cuba lagi.", "The bot is trying again."), "ok");
  }

  async function remove(s) {
    if (sure !== s.id) { setSure(s.id); timers.current.push(setTimeout(() => setSure(""), 6000)); return; }
    setBusy(`del-${s.id}`); setSure("");
    const { error } = await supabase.from(TABLES.writingStyles).delete().eq("id", s.id);
    if (error) { setBusy(""); return onToast(errText(error), "danger"); }
    await Promise.all((s.images || []).map((p) => removeReference(p).catch(() => {})));
    if (settings?.writing_style?.id === s.id) await save("writing_style", { id: "" }).catch(() => {});   // the default never points at a deleted style
    setBusy("");
    rows.reload?.();
    onToast(t("Gaya dipadam.", "Style deleted."), "ok");
  }

  return (
    <main className="mx-auto max-w-page space-y-6 px-4 pb-20 pt-10 sm:px-6" data-writing-page>
      <motion.div variants={fadeUp} initial="hidden" animate="show">
        <h1 className="font-display text-3xl">{t("Gaya penulisan", "Writing styles")}</h1>
        <p className="mt-1 max-w-2xl text-sm text-muted">{t("Asing daripada hook: gaya penulisan menentukan bagaimana seluruh kapsyen dibaca (suara, rentak, panjang ayat, struktur, penutup). Tambah post viral yang anda suka dan bot menterjemahkannya menjadi gaya, atau tulis sendiri. Pilih satu sebagai lalai, atau pilih untuk satu idea sahaja.",
          "Apart from the hook: a writing style decides how the whole caption reads (voice, rhythm, sentence length, structure, ending). Add viral posts you like and the bot turns them into a style, or write one yourself. Choose one as the default, or for one idea only.")}</p>
      </motion.div>

      {/* the house style every writer reads (voice, never-list, hashtags, fatwa line), moved here from Tetapan (Wan, 7 Nov 2026) */}
      <WriterSettings settings={settings || {}} save={save} onToast={onToast} />

      {missing ? <Card className="p-5 text-sm text-muted">{migrate}</Card> : (
        <Card className="space-y-4 p-5" data-writing-styles>
          <ul className="space-y-2">
            <li className="flex flex-wrap items-center gap-2 rounded-tile border border-line p-3 text-sm" data-writing-style={NONE}>
              <span className="font-medium">{t("Tiada gaya", "No style")}</span>
              <span className="text-xs text-muted">{t("gaya rumah dan peraturan sahaja", "the house style and the rules only")}</span>
              <span className="ml-auto">{current === NONE
                ? <span className="inline-flex items-center gap-1 rounded-pill bg-ok/15 px-2 py-0.5 text-xs text-ok"><Check size={12} /> {t("Dipakai", "In use")}</span>
                : <Button size="sm" variant="soft" onClick={() => choose("")} disabled={busy === "use-"}>{t("Guna ini", "Use this")}</Button>}</span>
            </li>
            {styles.map((s) => (
              <StyleRow key={s.id} s={s} L={L} t={t} inUse={current === s.id} open={open === s.id} sure={sure === s.id} busy={busy}
                onOpen={() => setOpen(open === s.id ? "" : s.id)} onUse={() => choose(s.id)} onRetry={() => retry(s)} onDelete={() => remove(s)}
                onSaved={() => { rows.reload?.(); onToast(t("Gaya disimpan.", "Style saved."), "ok"); }} onError={(m) => onToast(m, "danger")} onWarn={(m) => onToast(m, "warn")} />
            ))}
            {!styles.length && !rows.loading && <li className="text-xs text-muted" data-writing-empty>{t("Belum ada gaya. Tambah satu di bawah.", "No styles yet. Add one below.")}</li>}
          </ul>

          <div className="space-y-2 rounded-tile border border-dashed border-line p-3" data-writing-add>
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-sm font-medium">{t("Tambah gaya", "Add a style")}</p>
              <div role="tablist" className="ml-auto flex gap-1.5">
                {[["analyse", t("Daripada post viral", "From viral posts"), Link2], ["manual", t("Tulis sendiri", "Write it myself"), PenLine]].map(([id, label, Icon]) => (
                  <button key={id} type="button" role="tab" aria-selected={mode === id} onClick={() => setMode(id)} data-writing-mode={id}
                    className={`inline-flex items-center gap-1 rounded-pill px-3 py-1 text-xs font-medium ${mode === id ? "bg-ink text-bg" : "bg-surface-2 text-muted hover:text-ink"}`}><Icon size={12} /> {label}</button>
                ))}
              </div>
            </div>
            <label className="block"><Label hint={mode === "analyse" ? t("pilihan: bot beri nama jika kosong", "optional: the bot names it if empty") : ""}>{t("Nama", "Name")}</Label>
              <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={60} placeholder={t("Cth: Pembetulan santai", "E.g. Calm correction")} /></label>
            {mode === "analyse" ? (<>
              <label className="block"><Label hint={t(`sehingga ${MAX_LINKS}, satu setiap baris`, `up to ${MAX_LINKS}, one a line`)}>{t("Pautan post viral", "Viral post links")}</Label>
                <TextArea rows={3} value={linksText} onChange={(e) => setLinksText(e.target.value)} spellCheck={false} className="font-mono text-xs" data-writing-links
                  placeholder={"https://www.threads.net/@…/post/…\nhttps://www.facebook.com/…"} /></label>
              {(parsed.links.length > 0 || parsed.bad.length > 0) && (
                <p className="text-[11.5px] text-muted" data-writing-links-count>{t(`${parsed.links.length} pautan`, `${parsed.links.length} link${parsed.links.length === 1 ? "" : "s"}`)}
                  {parsed.bad.length ? <span className="text-warn"> · {t(`bukan pautan: ${parsed.bad.slice(0, 2).join(", ")}`, `not a link: ${parsed.bad.slice(0, 2).join(", ")}`)}</span> : null}
                  {parsed.over ? <span className="text-warn"> · {t(`${parsed.over} lebih had`, `${parsed.over} over the limit`)}</span> : null}</p>
              )}
              <label className="block"><Label hint={t("pilihan; untuk LinkedIn, Instagram dan TikTok yang menyorok post. Pisahkan post dengan baris kosong.", "optional; for LinkedIn, Instagram and TikTok, which hide posts. Separate posts with a blank line.")}>{t("Tampal teks post", "Paste the post text")}</Label>
                <TextArea rows={5} value={sample} onChange={(e) => setSample(e.target.value.slice(0, MAX_SAMPLE))} data-writing-sample /></label>
              <label className="block"><Label hint={t(`pilihan; sehingga ${MAX_IMAGES}; PNG, JPG, WEBP`, `optional; up to ${MAX_IMAGES}; PNG, JPG, WEBP`)}>{t("Tangkapan skrin post", "Post screenshots")}</Label>
                <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp,image/gif" multiple className="block w-full text-xs" data-writing-files
                  onChange={(e) => setFiles(Array.from(e.target.files || []).slice(0, MAX_IMAGES + 1))} /></label>
              {files.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {files.map((f, i) => (
                    <span key={`${f.name}-${i}`} className="relative">
                      <img src={previewOf(f)} alt={f.name} className="h-16 w-16 rounded-tile border border-line object-cover" />
                      <button type="button" aria-label={t("Buang", "Remove")} onClick={() => setFiles(files.filter((_, j) => j !== i))} className="absolute -right-1 -top-1 rounded-full bg-surface p-0.5 shadow"><X size={12} /></button>
                    </span>
                  ))}
                </div>
              )}
              <Button size="sm" onClick={addAnalyse} disabled={busy === "add"} data-writing-analyse>
                {busy === "add" ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />} {t("Analisis dan buat gaya", "Analyse and make the style")}</Button>
              <p className="flex items-start gap-1 text-[11.5px] text-muted"><Upload size={12} className="mt-0.5 shrink-0" />
                {t("Bot menerangkan BAGAIMANA post itu ditulis, bukan apa yang dikatakan: ayat, nama, jenama dan angka post asal tidak disimpan. Tangkapan skrin kekal dalam folder anda sahaja.",
                  "The bot describes HOW the posts are written, not what they say: their sentences, names, brands and figures are never kept. Screenshots stay in your own folder only.")}</p>
            </>) : (<>
              <label className="block"><Label hint={t("sekurang-kurangnya 20 aksara; kepada penulis: suara, rentak, struktur, penutup", "at least 20 characters; to the writer: voice, rhythm, structure, ending")}>{t("Arahan gaya", "Style instruction")}</Label>
                <TextArea rows={5} value={mInstruction} onChange={(e) => setMInstruction(e.target.value)} maxLength={2000} data-writing-manual-instruction /></label>
              <label className="block"><Label hint={t("pilihan; satu setiap baris", "optional; one a line")}>{t("Ciri", "Traits")}</Label>
                <TextArea rows={3} value={mTraits} onChange={(e) => setMTraits(e.target.value)} placeholder={t("Ayat pendek\nNada tenang", "Short sentences\nCalm tone")} /></label>
              <Button size="sm" onClick={addManual} disabled={busy === "manual"} data-writing-manual-save>
                {busy === "manual" ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />} {t("Simpan gaya", "Save the style")}</Button>
            </>)}
          </div>
        </Card>
      )}
    </main>
  );
}

function StyleRow({ s, L, t, inUse, open, sure, busy, onOpen, onUse, onRetry, onDelete, onSaved, onError, onWarn }) {
  const [name, setName] = useState(s.name || "");
  const [instruction, setInstruction] = useState(s.instruction || "");
  const [traits, setTraits] = useState(traitsToText(s.traits));
  const [saving, setSaving] = useState(false);
  const sig = JSON.stringify([s.name, s.instruction, s.traits, s.status]);
  const seen = useRef(sig);
  useEffect(() => {
    if (seen.current !== sig && !open) { setName(s.name || ""); setInstruction(s.instruction || ""); setTraits(traitsToText(s.traits)); }
    seen.current = sig;
  }, [sig]); // eslint-disable-line react-hooks/exhaustive-deps

  async function saveEdit() {
    if (instruction.trim().length < 20) return onWarn(t("Arahan perlu sekurang-kurangnya 20 aksara.", "The instruction needs at least 20 characters."));
    setSaving(true);
    const { error } = await supabase.from(TABLES.writingStyles).update({ name: name.trim().slice(0, 60) || s.name, instruction: instruction.trim().slice(0, 2000),
      traits: textToTraits(traits) }).eq("id", s.id);
    setSaving(false);
    if (error) return onError(errText(error));
    onSaved();
  }

  const from = sourcesLine(s, t);
  return (
    <li className="rounded-tile border border-line p-3 text-sm" data-writing-style={s.id} data-status={s.status}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{s.name || t("Gaya tanpa nama", "Unnamed style")}</span>
        <span className="rounded-pill bg-surface-2 px-2 py-0.5 text-[11px] text-muted">{s.source === "manual" ? t("tulis sendiri", "hand-written") : from || t("post viral", "viral posts")}</span>
        <span className={`rounded-pill px-2 py-0.5 text-xs ${STATUS_CLS[s.status] || ""}`}>
          {isBusy(s) && <Loader2 size={11} className="mr-1 inline animate-spin" />}{(STATUS_WORDS[s.status] || [s.status, s.status])[L]}</span>
        <span className="break-words text-xs text-muted" data-writing-line>{summaryLine(s, t)}</span>
        <span className="ml-auto flex flex-wrap items-center gap-2">
          {inUse && <span className="inline-flex items-center gap-1 rounded-pill bg-ok/15 px-2 py-0.5 text-xs text-ok"><Check size={12} /> {t("Dipakai", "In use")}</span>}
          {isReady(s) && !inUse && <Button size="sm" variant="soft" onClick={onUse} disabled={busy === `use-${s.id}`} data-writing-use>{t("Guna sebagai lalai", "Use as default")}</Button>}
          {s.status === "error" && s.source !== "manual" && <Button size="sm" variant="soft" onClick={onRetry} disabled={busy === `retry-${s.id}`}><RefreshCw size={12} /> {t("Cuba lagi", "Try again")}</Button>}
          {s.status === "ready" && <Button size="sm" variant="ghost" onClick={onOpen}>{open ? <ChevronUp size={13} /> : <ChevronDown size={13} />} {t("Ubah", "Edit")}</Button>}
          <Button size="sm" variant="danger" onClick={onDelete} disabled={busy === `del-${s.id}`}><Trash2 size={12} /> {sure ? t("Pasti? Klik lagi", "Sure? Click again") : t("Padam", "Delete")}</Button>
        </span>
      </div>
      {s.status === "ready" && !open && (
        <div className="mt-1 space-y-1">
          {s.summary && <p className="text-xs text-muted">{s.summary}</p>}
          {(s.traits || []).length > 0 && <div className="flex flex-wrap gap-1.5">{s.traits.map((x, i) => <span key={i} className="rounded-pill bg-surface-2 px-2 py-0.5 text-[11px]">{x}</span>)}</div>}
          {s.error && <p className="text-xs text-warn">{s.error}</p>}
        </div>
      )}
      {open && (
        <div className="mt-3 space-y-2" data-writing-editor>
          <label className="block"><Label>{t("Nama", "Name")}</Label><Input value={name} onChange={(e) => setName(e.target.value)} maxLength={60} /></label>
          <label className="block"><Label hint={t("diberi kepada penulis kapsyen selepas semua peraturan", "given to the caption writer after every rule")}>{t("Arahan gaya", "Style instruction")}</Label>
            <TextArea rows={6} value={instruction} onChange={(e) => setInstruction(e.target.value)} maxLength={2000} /></label>
          <label className="block"><Label hint={t("satu setiap baris", "one a line")}>{t("Ciri", "Traits")}</Label>
            <TextArea rows={4} value={traits} onChange={(e) => setTraits(e.target.value)} /></label>
          <Button size="sm" onClick={saveEdit} disabled={saving}>{saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />} {t("Simpan gaya", "Save style")}</Button>
        </div>
      )}
    </li>
  );
}
