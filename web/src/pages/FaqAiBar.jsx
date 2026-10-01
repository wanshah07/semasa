import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Bot, Check, FileText, Loader2, Paperclip, Sparkles, X } from "lucide-react";
import { TABLES, errText, supabase } from "../lib/SupabaseClient";
import { useLang } from "../lib/i18n";
import { acceptKind, extractFaqs, prepareInputs } from "../lib/faqAi";
import { AI_LIMITS, faqRow, markExisting } from "../lib/faqAiLogic";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import { Input, TextArea } from "../components/ui/Field";

const AUTO_KEY = "semasa.faqAi.auto";
const readAuto = () => { try { return localStorage.getItem(AUTO_KEY) === "1"; } catch { return false; } };

/* The AI bar (Wan, 1 Oct 2026): paste a screenshot, drop a picture or a PDF, or type a note; the AI lists the question
   and answer pairs it finds; Wan keeps the ones he wants. Each kept pair is inserted as a `new` FAQ row, exactly like
   Add FAQ, so the worker rewrites it in BM and English, anonymises it and picks the category. Nothing is published here. */
export default function FaqAiBar({ rows, user, onToast, onDone }) {
  const { t } = useLang();
  const [files, setFiles] = useState([]);          // File objects waiting to be read
  const [note, setNote] = useState("");
  const [phase, setPhase] = useState("");           // "" | "prep" | "read" | "add"
  const [progress, setProgress] = useState("");
  const [result, setResult] = useState(null);       // { items: [{...pair, keep, exists}], notRead, errors, label }
  const [drag, setDrag] = useState(false);
  const [auto, setAuto] = useState(readAuto);
  const pick = useRef(null);
  const previews = useRef(new Map());

  useEffect(() => () => { for (const u of previews.current.values()) URL.revokeObjectURL(u); }, []);

  const busy = phase !== "";
  function addFiles(list) {
    const take = [], refused = [];
    for (const f of Array.from(list || [])) (acceptKind(f) ? take : refused).push(f);
    if (refused.length) onToast(t("Hanya gambar, PDF dan fail teks boleh dibaca: {n}", "Only pictures, PDFs and text files can be read: {n}", { n: refused.map((f) => f.name || f.type).join(", ") }), "warn");
    if (take.length) setFiles((cur) => [...cur, ...take].slice(0, AI_LIMITS.files));
  }
  function onPaste(e) {
    const got = Array.from(e.clipboardData?.files || []);
    if (got.length) { e.preventDefault(); addFiles(got); }       // text still pastes into the note as usual
  }
  const previewOf = (f) => {
    if (!previews.current.has(f)) previews.current.set(f, URL.createObjectURL(f));
    return previews.current.get(f);
  };
  const dropFile = (f) => { const u = previews.current.get(f); if (u) { URL.revokeObjectURL(u); previews.current.delete(f); } setFiles((cur) => cur.filter((x) => x !== f)); };

  async function insert(items, label) {
    const out = items.map((it) => faqRow(it, { userId: user?.id, sourceLabel: label }));
    const { error } = await supabase.from(TABLES.faqs).insert(out);
    if (error) throw new Error(/semasa_faqs/.test(errText(error)) ? t("Jalankan supabase/007_faq.sql dahulu.", "Run supabase/007_faq.sql first.") : errText(error));
    return out.length;
  }

  async function analyse() {
    if (busy) return;
    if (!files.length && !note.trim()) return onToast(t("Tampal gambar, tambah PDF atau taip sesuatu dahulu.", "Paste a picture, add a PDF or type something first."), "warn");
    setResult(null); setPhase("prep");
    try {
      const inputs = files.length ? await prepareInputs(files, (s) => setProgress(s)) : [];
      setPhase("read");
      const found = await extractFaqs({ note, inputs, onProgress: setProgress });
      const label = files.length ? files.slice(0, 2).map((f) => f.name || t("gambar tampal", "pasted picture")).join(", ") + (files.length > 2 ? ` +${files.length - 2}` : "") : t("teks ditaip", "typed text");
      const marked = markExisting(found.items, rows).map((it) => ({ ...it, keep: !it.exists }));
      if (auto && marked.some((m) => m.keep) && !found.errors.length) {
        setPhase("add");
        const n = await insert(marked.filter((m) => m.keep), label);
        onToast(t("{n} soalan dihantar ke AI untuk ditulis semula.", ["{n} question sent to the AI to be rewritten.", "{n} questions sent to the AI to be rewritten."], { n }), "ok");
        setResult({ items: marked.filter((m) => !m.keep), notRead: found.notRead, errors: found.errors, label, added: n });
        reset(); onDone?.();
        return;
      }
      setResult({ items: marked, notRead: found.notRead, errors: found.errors, missing: found.missing, label });
    } catch (e) {
      setResult({ items: [], notRead: [], errors: [String(e?.message || e)], label: "" });
    } finally { setPhase(""); setProgress(""); }
  }

  function reset() {
    for (const u of previews.current.values()) URL.revokeObjectURL(u);
    previews.current.clear();
    setFiles([]); setNote("");
  }

  async function addKept() {
    const kept = (result?.items || []).filter((i) => i.keep && i.question.trim());
    if (!kept.length) return onToast(t("Tiada soalan dipilih.", "No question is ticked."), "warn");
    setPhase("add");
    try {
      const n = await insert(kept, result.label);
      onToast(t("{n} soalan dihantar ke AI untuk ditulis semula dan dikategorikan.", ["{n} question sent to the AI to be rewritten and categorised.", "{n} questions sent to the AI to be rewritten and categorised."], { n }), "ok");
      setResult(null); reset(); onDone?.();
    } catch (e) { onToast(String(e?.message || e), "danger"); } finally { setPhase(""); }
  }
  const edit = (i, patch) => setResult((r) => ({ ...r, items: r.items.map((x, k) => (k === i ? { ...x, ...patch } : x)) }));
  const keptCount = (result?.items || []).filter((i) => i.keep).length;
  const toggleAuto = (v) => { setAuto(v); try { localStorage.setItem(AUTO_KEY, v ? "1" : "0"); } catch { /* private mode: it just will not be remembered */ } };

  return (
    <Card className={`mt-5 p-4 ${drag ? "ring-2 ring-accent" : ""}`}
      onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
      onDrop={(e) => { e.preventDefault(); setDrag(false); addFiles(e.dataTransfer?.files); }}>
      <div className="flex flex-wrap items-center gap-2">
        <Sparkles size={14} className="text-accent" />
        <h2 className="text-sm font-semibold">{t("Bar AI", "AI bar")}</h2>
        <span className="text-[11px] text-muted">{t("tampal tangkapan skrin (Ctrl+V), seret gambar atau PDF; AI mengasingkan soalan dan jawapan", "paste a screenshot (Ctrl+V), drop a picture or PDF; the AI separates the questions and answers")}</span>
      </div>

      <div className="mt-3 flex flex-wrap items-start gap-2" onPaste={onPaste}>
        <label className="min-w-0 flex-1 basis-72">
          <span className="sr-only">{t("Nota untuk AI", "Note for the AI")}</span>
          <TextArea rows={2} value={note} onChange={(e) => setNote(e.target.value)} maxLength={AI_LIMITS.text} disabled={busy}
            placeholder={t("Tampal di sini: gambar akan dilampirkan. Atau taip/tampal teks soal jawab, atau nota seperti “ini WhatsApp pelanggan tentang logo halal”.",
              "Paste here: pictures are attached. Or type or paste Q&A text, or a note like “this is a customer chat about the halal logo”.")} />
        </label>
        <div className="flex flex-col gap-2">
          <input ref={pick} type="file" multiple accept="image/*,application/pdf,.pdf,.txt,.md,.csv" className="hidden"
            onChange={(e) => { addFiles(e.target.files); e.target.value = ""; }} />
          <Button size="sm" variant="soft" disabled={busy} onClick={() => pick.current?.click()}><Paperclip size={12} /> {t("Lampir", "Attach")}</Button>
          <Button size="sm" disabled={busy || (!files.length && !note.trim())} onClick={analyse}>
            {busy ? <Loader2 size={12} className="animate-spin" /> : <Bot size={12} />} {t("Analisis", "Analyse")}</Button>
        </div>
      </div>

      {files.length > 0 && (
        <ul className="mt-3 flex flex-wrap gap-2" aria-label={t("Lampiran", "Attachments")}>
          {files.map((f, i) => (
            <li key={`${f.name}-${i}`} className="group relative flex items-center gap-2 rounded-tile border border-line bg-surface-2/60 p-1.5 pr-7 text-[11px]">
              {acceptKind(f) === "image" ? <img src={previewOf(f)} alt="" className="h-10 w-10 rounded object-cover" />
                : <span className="grid h-10 w-10 place-items-center rounded bg-surface text-muted"><FileText size={16} /></span>}
              <span className="max-w-[10rem] truncate">{f.name || t("gambar tampal", "pasted picture")}</span>
              {!busy && <button type="button" aria-label={t("Buang lampiran", "Remove attachment")} onClick={() => dropFile(f)} className="absolute right-1.5 top-1.5 text-muted hover:text-danger"><X size={12} /></button>}
            </li>
          ))}
        </ul>
      )}

      <label className="mt-3 flex items-center gap-2 text-[11px] text-muted">
        <input type="checkbox" checked={auto} onChange={(e) => toggleAuto(e.target.checked)} />
        {t("Terus tambah tanpa semakan (soalan yang sudah ada tidak ditambah)", "Add straight away without review (questions that already exist are not added)")}
      </label>

      {busy && <p role="status" className="mt-3 flex items-center gap-2 text-[12px] text-muted"><Loader2 size={12} className="animate-spin" /> {phase === "add" ? t("Menghantar ke AI…", "Sending to the AI…") : progress || t("Menyediakan…", "Preparing…")}</p>}

      {result && (
        <div className="mt-4 border-t border-line pt-3">
          {result.errors?.length > 0 && (
            <div className="mb-3 rounded-tile bg-danger/10 p-3 text-[12px] text-danger" role="alert">
              <p className="flex items-center gap-1.5 font-medium"><AlertTriangle size={12} /> {t("Ada yang tidak berjaya", "Something did not work")}</p>
              <ul className="mt-1 list-disc pl-5 [overflow-wrap:anywhere]">{result.errors.map((e, i) => <li key={i}>{e}</li>)}</ul>
              {result.missing && <p className="mt-1 text-ink">{t("Fungsi semasa-chat perlu dipasang semula: GitHub → Actions → Deploy functions → Run workflow.", "The semasa-chat function needs deploying again: GitHub → Actions → Deploy functions → Run workflow.")}</p>}
            </div>
          )}
          {result.notRead?.length > 0 && (
            <p className="mb-3 rounded-tile bg-warn/10 p-3 text-[12px] text-warn [overflow-wrap:anywhere]">{t("Tidak dibaca", "Not read")}: {result.notRead.join(" · ")}</p>
          )}
          {result.added > 0 && <p className="mb-3 text-[12px] text-ok"><Check size={12} className="inline" /> {t("{n} ditambah.", "{n} added.", { n: result.added })}</p>}

          {result.items.length === 0 && !result.errors?.length && !result.added && (
            <p className="text-sm text-muted">{t("AI tidak menjumpai soalan dan jawapan dalam bahan ini. Cuba gambar yang lebih jelas, atau tambah nota tentang apa yang dicari.", "The AI found no questions and answers in this material. Try a clearer picture, or add a note about what to look for.")}</p>
          )}

          {result.items.length > 0 && (
            <>
              <p className="mb-2 text-[12px] text-muted">{t("{n} soalan ditemui. Tanda yang mahu ditambah; sunting jika perlu. AI akan menulis semula dalam BM dan English, membuang nama dan memilih kategori.",
                ["{n} question found. Tick the ones to add; edit if needed. The AI will rewrite them in BM and English, remove names and choose the category.", "{n} questions found. Tick the ones to add; edit if needed. The AI will rewrite them in BM and English, remove names and choose the category."], { n: result.items.length })}</p>
              <ul className="space-y-2">
                {result.items.map((it, i) => (
                  <li key={i} className={`rounded-tile border p-3 ${it.keep ? "border-accent/50 bg-surface" : "border-line bg-surface-2/50"}`}>
                    <div className="flex items-start gap-2">
                      <input type="checkbox" className="mt-1.5" checked={it.keep} onChange={(e) => edit(i, { keep: e.target.checked })} aria-label={t("Tambah soalan ini", "Add this question")} />
                      <div className="min-w-0 flex-1 space-y-2">
                        <Input value={it.question} onChange={(e) => edit(i, { question: e.target.value })} maxLength={600} aria-label={t("Soalan", "Question")} />
                        <TextArea rows={2} value={it.answer} onChange={(e) => edit(i, { answer: e.target.value })} maxLength={3000} aria-label={t("Jawapan", "Answer")}
                          placeholder={t("Tiada jawapan dalam bahan: AI akan menjawab dan menandanya perlu semakan.", "No answer in the material: the AI will answer it and mark it needs check.")} />
                        <div className="flex flex-wrap gap-1.5 text-[11px]">
                          {it.source_hint && <span className="rounded-pill bg-surface-2 px-2 py-0.5 text-muted">{it.source_hint}</span>}
                          {it.instrument && <span className="rounded-pill bg-surface-2 px-2 py-0.5 text-muted">{it.instrument}</span>}
                          {!it.answer && <span className="rounded-pill bg-warn/10 px-2 py-0.5 text-warn">{t("tiada jawapan", "no answer")}</span>}
                          {it.unclear && <span className="inline-flex items-center gap-1 rounded-pill bg-warn/10 px-2 py-0.5 text-warn"><AlertTriangle size={10} /> {t("teks sukar dibaca: semak", "hard to read: check it")}</span>}
                          {it.exists && <span className="rounded-pill bg-warn/10 px-2 py-0.5 text-warn" title={it.exists.question}>{t("serupa sudah ada", "similar one exists")}: {String(it.exists.question || "").slice(0, 60)}</span>}
                        </div>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
              <div className="mt-3 flex flex-wrap items-center justify-end gap-2">
                <Button variant="ghost" size="sm" disabled={busy} onClick={() => setResult(null)}>{t("Buang keputusan", "Discard results")}</Button>
                <Button size="sm" disabled={busy || !keptCount} onClick={addKept}>
                  {phase === "add" ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />} {t("Tambah {n} ke FAQ", "Add {n} to FAQ", { n: keptCount })}</Button>
              </div>
            </>
          )}
        </div>
      )}
    </Card>
  );
}
