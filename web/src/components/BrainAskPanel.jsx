import { useState } from "react";
import { AlertTriangle, ChevronDown, Clipboard, HelpCircle, Loader2, RefreshCw, Trash2, Wand2 } from "lucide-react";
import { TABLES, errText, supabase } from "../lib/SupabaseClient";
import { useLang } from "../lib/i18n";
import { useTable } from "../lib/hooks";
import { timeAgo } from "../lib/format";
import Markdown from "./Markdown";
import Button from "./ui/Button";
import Card from "./ui/Card";
import { Input, Select, TextArea } from "./ui/Field";

/* Tanya Otak (supabase/078_brain_ask.sql): ask a question of the entries the Otak AI brain already filed; the worker
   (backend/semasa/brain_ask.py) retrieves the most on-topic entries and the AI answers with every claim cited to its
   source, plus the gaps (what the brain does not cover) and any conflict. The answer is what the brain holds, never a
   compliance decision. This panel asks, shows how the question stands, and shows the cited answer. */

const STATUS_TONE = { pending: "bg-accent/10 text-accent", working: "bg-accent/10 text-accent", done: "bg-ok/10 text-ok", empty: "bg-warn/10 text-warn", error: "bg-danger/10 text-danger" };
const STATUS_WORDS = {
  pending: ["Menunggu AI", "Waiting for the AI"], working: ["Sedang dijawab", "Being answered"], done: ["Siap", "Ready"],
  empty: ["Tiada padanan", "Nothing matched"], error: ["Gagal", "Failed"],
};

/** The cited answer as markdown: each inline [n] becomes a bold reference to the source's title. */
export function citedMarkdown(r) {
  const byRef = Object.fromEntries((r?.sources || []).map((s) => [String(s.ref), s]));
  return String(r?.answer || "").replace(/\[(\d+)\]/g, (m, n) => {
    const s = byRef[n];
    return s ? `**[${n}: ${s.title}]**` : m;
  });
}

export default function BrainAskPanel({ onToast }) {
  const { t, lang } = useLang();
  const L = lang === "en" ? 1 : 0;
  const w = (map, k) => (map[k] || [k, k])[L];
  const asks = useTable(TABLES.brainAsks, { enabled: true, order: "created_at", limit: 40 });
  const [question, setQuestion] = useState("");
  const [note, setNote] = useState("");
  const [qlang, setQlang] = useState("ms");
  const [busy, setBusy] = useState("");
  const [open, setOpen] = useState("");
  const missing = /semasa_brain_asks/.test(asks.error || "");
  const guard = (fn) => async (...a) => { try { await fn(...a); } catch (e) { onToast(e.message || String(e), "danger"); } };

  const ask = guard(async () => {
    const q = question.trim();
    if (!q) return onToast(t("Tulis soalan dahulu.", "Write a question first."), "info");
    setBusy("ask");
    try {
      const { error } = await supabase.from(TABLES.brainAsks)
        .insert({ status: "pending", question: q, lang: qlang, note: note.trim().slice(0, 500), created_by: null });
      if (error) throw new Error(/semasa_brain_asks/.test(errText(error)) ? t("Jadual belum ada: jalankan supabase/078_brain_ask.sql sekali.", "The table is not there yet: run supabase/078_brain_ask.sql once.") : errText(error));
      setQuestion(""); setNote("");
      asks.reload();
      onToast(t("Soalan dihantar. AI menjawab dalam seminit dua, dengan sumber.", "Question sent. The AI answers within a minute or two, with sources."), "ok");
    } finally { setBusy(""); }
  });

  const again = guard(async (r) => {
    const { error } = await supabase.from(TABLES.brainAsks).update({ status: "pending", result: {}, error: "", attempts: 0 }).eq("id", r.id);
    if (error) throw new Error(errText(error));
    asks.reload();
  });
  const remove = guard(async (r) => {
    if (!window.confirm(t("Padam soalan ini?", "Delete this question?"))) return;
    const { error } = await supabase.from(TABLES.brainAsks).delete().eq("id", r.id);
    if (error) throw new Error(errText(error));
    asks.reload();
  });

  if (missing) return <p className="mb-4 rounded-tile bg-warn/10 p-3 text-sm text-warn">{t("Jadual Tanya Otak belum ada: jalankan supabase/078_brain_ask.sql sekali.", "The ask table is not there yet: run supabase/078_brain_ask.sql once.")}</p>;

  return (
    <Card className="mb-6 p-4">
      <p className="mb-2 flex items-center gap-1.5 text-xs font-medium text-muted"><Wand2 size={13} /> {t("Tanya Otak", "Ask the brain")}</p>
      <p className="mb-3 text-xs text-muted">{t("Tanya satu soalan; AI menjawab daripada entri Otak sahaja, dengan setiap dakwaan dirujuk kepada sumbernya, dan menyebut apa yang Otak tidak ada.", "Ask a question; the AI answers from the brain entries only, citing each claim to its source, and says what the brain is missing.")}</p>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start">
        <TextArea rows={2} value={question} onChange={(e) => setQuestion(e.target.value)} className="min-w-0 flex-1"
          aria-label={t("Soalan", "Question")} placeholder={t("cth: Bolehkah jual produk yang notifikasinya dibatalkan?", "e.g. Can I sell a product whose notification is cancelled?")} />
        <div className="flex shrink-0 flex-row gap-2 sm:flex-col">
          <Select value={qlang} onChange={setQlang} aria-label={t("Bahasa jawapan", "Answer language")} options={[["ms", "BM"], ["en", "EN"]]} />
          <Button disabled={busy === "ask"} onClick={ask}>{busy === "ask" ? <Loader2 size={14} className="animate-spin" /> : <HelpCircle size={14} />} {t("Tanya", "Ask")}</Button>
        </div>
      </div>
      <Input className="mt-2" value={note} maxLength={500} onChange={(e) => setNote(e.target.value)}
        placeholder={t("Nota (pilihan): untuk klien mana, kenapa penting…", "Note (optional): which client, why it matters…")}
        aria-label={t("Nota", "Note")} />

      {asks.rows.length > 0 && (
        <ul className="mt-4 divide-y divide-line/60">
          {asks.rows.map((r) => {
            const res = r.result && r.result.answer ? r.result : null;
            const isOpen = open === r.id;
            return (
              <li key={r.id} className="py-2.5 text-sm">
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                  <span className={`rounded-pill px-2 py-0.5 text-[11px] ${STATUS_TONE[r.status] || ""}`}>{w(STATUS_WORDS, r.status)}</span>
                  <span className="min-w-0 flex-1 truncate font-medium">{r.question}</span>
                  <span className="text-xs text-muted">{r.lang === "en" ? "EN" : "BM"} · {timeAgo(r.updated_at || r.created_at)}</span>
                  <span className="flex gap-1">
                    {r.status === "done" && <button type="button" onClick={() => setOpen(isOpen ? "" : r.id)} aria-expanded={isOpen} aria-label={t("Pratonton", "Preview")} className="rounded-pill p-1.5 text-muted hover:bg-surface-2"><ChevronDown size={14} className={isOpen ? "rotate-180" : ""} /></button>}
                    {r.status === "done" && <button type="button" aria-label={t("Salin teks", "Copy the text")} onClick={guard(async () => { await navigator.clipboard.writeText(citedMarkdown(r)); onToast(t("Disalin.", "Copied."), "ok"); })} className="rounded-pill p-1.5 text-muted hover:bg-surface-2"><Clipboard size={14} /></button>}
                    {["done", "empty", "error"].includes(r.status) && <button type="button" aria-label={t("Tanya semula", "Ask again")} onClick={() => again(r)} className="rounded-pill p-1.5 text-muted hover:bg-surface-2">{busy === r.id ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}</button>}
                    <button type="button" aria-label={t("Padam", "Delete")} onClick={() => remove(r)} className="rounded-pill p-1.5 text-muted hover:bg-surface-2"><Trash2 size={14} /></button>
                  </span>
                </div>
                {r.error && <p className={`mt-1 flex items-center gap-1 text-xs ${r.status === "error" ? "text-danger" : "text-warn"}`}><AlertTriangle size={12} /> {r.error}</p>}
                {isOpen && res && (
                  <div className="mt-3 border-t border-line/60 pt-3 text-sm">
                    <Markdown text={citedMarkdown(r)} />
                    {res.sources?.length > 0 && (
                      <div className="mt-3 space-y-1 border-t border-line/40 pt-2">
                        <p className="text-xs font-semibold text-muted">{t("Sumber", "Sources")}</p>
                        {res.sources.map((s) => (
                          <p key={s.ref} className="text-xs text-muted"><span className="font-semibold text-accent">[{s.ref}]</span> {s.title} <span className="text-muted/70">· {s.kind}</span>{s.why ? <> — {s.why}</> : null}</p>
                        ))}
                      </div>
                    )}
                    {res.gaps?.length > 0 && (
                      <div className="mt-2"><p className="text-xs font-semibold text-warn">{t("Otak tidak ada", "The brain does not cover")}</p>
                        <ul className="mt-1 list-disc space-y-0.5 pl-5 text-xs text-muted">{res.gaps.map((g, i) => <li key={i}>{g}</li>)}</ul>
                      </div>
                    )}
                    {res.conflicts?.length > 0 && (
                      <div className="mt-2"><p className="text-xs font-semibold text-warn">{t("Percanggahan", "Conflicts")}</p>
                        <ul className="mt-1 list-disc space-y-0.5 pl-5 text-xs text-muted">{res.conflicts.map((g, i) => <li key={i}>{g}</li>)}</ul>
                      </div>
                    )}
                    {res.uncited_sources?.length > 0 && <p className="mt-2 text-[11px] text-warn">{t("Sumber yang disebut tapi tidak dirujuk dalam jawapan: semak.", "Sources named but not cited inline: check.")}</p>}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
