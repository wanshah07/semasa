import { useState } from "react";
import { AlertTriangle, ChevronDown, Clipboard, Download, FileText, Loader2, RefreshCw, Trash2 } from "lucide-react";
import { TABLES, errText, supabase } from "../lib/SupabaseClient";
import { useLang } from "../lib/i18n";
import { useTable } from "../lib/hooks";
import { timeAgo } from "../lib/format";
import { download } from "../lib/faqExport";
import { STATUS_WORDS, docLangs, docToText, docWarnings, typeOf } from "../lib/documents";
import { DOCX_MIME, buildDocx, docFileName } from "../lib/docxWrite";
import Button from "./ui/Button";
import Card from "./ui/Card";

/* The documents the bot has drafted or is drafting (semasa_brain_docs): status, a preview with what to check first, the Word
   file per language, a plain-text copy, draft again, delete. Always a draft for review: the page says so on every one. */
const TONE = { pending: "bg-accent/10 text-accent", working: "bg-accent/10 text-accent", done: "bg-ok/10 text-ok", error: "bg-danger/10 text-danger" };
const MARK = /(\[Perlu pengesahan\]|\[Needs confirmation\])/;
const marked = (text) => String(text ?? "").split(MARK).map((p, i) => (i % 2 ? <mark key={i} className="rounded bg-yellow-200 px-0.5 font-semibold text-ink">{p}</mark> : p));

function Preview({ doc, t }) {
  const w = docWarnings(doc);
  return (
    <div className="mt-3 space-y-3 border-t border-line/60 pt-3 text-sm">
      <div className="flex flex-wrap gap-1.5 text-[11px]">
        <span className="rounded-pill bg-warn/10 px-2 py-0.5 text-warn">{doc.status}</span>
        {w.check > 0 && <span className="rounded-pill bg-danger/10 px-2 py-0.5 text-danger">{t("{n} angka/rujukan tiada dalam bahan", "{n} figures/references not in the material", { n: w.check })}</span>}
        {w.wording > 0 && <span className="rounded-pill bg-warn/10 px-2 py-0.5 text-warn">{t("{n} frasa status/kelulusan untuk disemak", "{n} status/approval phrases to check", { n: w.wording })}</span>}
        {w.confirm > 0 && <span className="rounded-pill bg-surface-2 px-2 py-0.5 text-muted">{t("{n} perlu disahkan", "{n} to confirm", { n: w.confirm })}</span>}
        {w.conflicts > 0 && <span className="rounded-pill bg-surface-2 px-2 py-0.5 text-muted">{t("{n} percanggahan", "{n} conflicts", { n: w.conflicts })}</span>}
        {w.truncated && <span className="rounded-pill bg-warn/10 px-2 py-0.5 text-warn">{t("bahan dipotong", "material cut")}</span>}
      </div>
      <p className="font-display text-lg leading-snug">{doc.title}</p>
      {doc.sections.map((s) => (
        <div key={s.key}>
          <p className="text-xs font-semibold text-muted">{s.heading}</p>
          {s.kind === "table" ? (
            <div className="mt-1 overflow-x-auto"><table className="w-full border-collapse text-xs">
              <thead><tr>{s.columns.map((c) => <th key={c} className="border border-line bg-surface-2 px-2 py-1 text-left">{c}</th>)}</tr></thead>
              <tbody>{s.rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j} className="border border-line px-2 py-1 align-top">{marked(c)}</td>)}</tr>)}</tbody>
            </table></div>
          ) : s.kind === "bullets" ? <ul className="mt-1 list-disc space-y-0.5 pl-5">{s.bullets.map((b, i) => <li key={i}>{marked(b)}</li>)}</ul>
            : s.paragraphs.map((p, i) => <p key={i} className="mt-1 whitespace-pre-line">{marked(p)}</p>)}
        </div>
      ))}
      {[[doc.generic.to_confirm, doc.to_confirm], [doc.generic.conflicts, doc.conflicts], [doc.generic.source_check, doc.source_check?.length ? [doc.source_check.join(", ")] : []], [doc.generic.flags, doc.flags]].map(([h, list]) => list?.length > 0 && (
        <div key={h}><p className="text-xs font-semibold text-muted">{h}</p><ul className="mt-1 list-disc space-y-0.5 pl-5">{list.map((b, i) => <li key={i}>{marked(b)}</li>)}</ul></div>
      ))}
      <p className="text-[11px] text-muted">{doc.disclaimer}</p>
    </div>
  );
}

export default function DocumentsPanel({ onToast }) {
  const { t, lang } = useLang();
  const L = lang === "en" ? 1 : 0;
  const docs = useTable(TABLES.brainDocs, { enabled: true, order: "created_at", limit: 60 });
  const [open, setOpen] = useState("");
  const [showLang, setShowLang] = useState({});
  const [busy, setBusy] = useState("");
  const missing = /semasa_brain_docs/.test(docs.error || "");
  const typeLabel = (r) => (r.doc_type === "template" ? `${t("Templat", "Template")}: ${r.template_snapshot?.name || ""}` : typeOf(r.doc_type)?.label[L]);
  const guard = (id, fn) => async () => { setBusy(id); try { await fn(); } catch (e) { onToast(e.message || String(e), "danger"); } finally { setBusy(""); } };

  const save = (doc) => {
    const bytes = buildDocx(doc);
    download(new Blob([bytes], { type: DOCX_MIME }), docFileName(doc));
    onToast(t("Fail Word dimuat turun (DRAF UNTUK SEMAKAN).", "Word file downloaded (DRAFT FOR REVIEW)."), "ok");
  };
  const again = (r) => guard(r.id, async () => {
    const { error } = await supabase.from(TABLES.brainDocs).update({ status: "pending", result: {}, error: "", attempts: 0 }).eq("id", r.id);
    if (error) throw new Error(errText(error));
    docs.reload(); onToast(t("Dihantar semula kepada AI.", "Sent to the AI again."), "ok");
  });
  const remove = (r) => guard(r.id, async () => {
    if (!window.confirm(t("Padam dokumen ini?", "Delete this document?"))) return;
    const { error } = await supabase.from(TABLES.brainDocs).delete().eq("id", r.id);
    if (error) throw new Error(errText(error));
    docs.reload();
  });

  if (missing) return <p className="mb-4 rounded-tile bg-warn/10 p-3 text-sm text-warn">{t("Jadual dokumen belum ada: jalankan supabase/037_brain_docs.sql sekali.", "The documents table is not there yet: run supabase/037_brain_docs.sql once.")}</p>;
  if (!docs.rows.length) return null;
  return (
    <Card className="mb-6 p-4">
      <p className="mb-2 flex items-center gap-1.5 text-xs font-medium text-muted"><FileText size={13} /> {t("Dokumen", "Documents")} · {docs.rows.length}</p>
      <ul className="divide-y divide-line/60">
        {docs.rows.map((r) => {
          const langs = docLangs(r);
          const cur = showLang[r.id] && langs.includes(showLang[r.id]) ? showLang[r.id] : langs[0];
          const doc = r.result?.[cur];
          const isOpen = open === r.id;
          return (
            <li key={r.id} className="py-2.5 text-sm">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <span className={`rounded-pill px-2 py-0.5 text-[11px] ${TONE[r.status] || ""}`}>{(STATUS_WORDS[r.status] || [r.status, r.status])[L]}</span>
                <span className="min-w-0 flex-1 truncate font-medium">{(r.title || doc?.title || typeLabel(r) || r.doc_type)}</span>
                <span className="text-xs text-muted">{typeLabel(r)} · {r.lang === "both" ? "BM + EN" : r.lang === "en" ? "EN" : "BM"} · {t("{n} bahan", ["{n} item", "{n} items"], { n: (r.source_refs || []).length })}</span>
                <span className="text-xs text-muted">{timeAgo(r.updated_at || r.created_at)}</span>
                <span className="flex flex-wrap gap-1">
                  {r.status === "done" && langs.filter((l) => r.result?.[l]).map((l) => (
                    <Button key={l} size="sm" variant="soft" onClick={() => save(r.result[l])}><Download size={12} /> {l === "en" ? "English" : "BM"} .docx</Button>
                  ))}
                  {r.status === "done" && <button type="button" onClick={() => setOpen(isOpen ? "" : r.id)} aria-expanded={isOpen} aria-label={t("Pratonton", "Preview")} className="rounded-pill p-1.5 text-muted hover:bg-surface-2"><ChevronDown size={14} className={isOpen ? "rotate-180" : ""} /></button>}
                  {r.status === "done" && doc && <button type="button" aria-label={t("Salin teks", "Copy the text")} onClick={guard(r.id, async () => { await navigator.clipboard.writeText(docToText(doc)); onToast(t("Disalin.", "Copied."), "ok"); })} className="rounded-pill p-1.5 text-muted hover:bg-surface-2"><Clipboard size={14} /></button>}
                  {["done", "error"].includes(r.status) && <button type="button" aria-label={t("Jana semula", "Draft again")} title={t("Jana semula", "Draft again")} onClick={again(r)} className="rounded-pill p-1.5 text-muted hover:bg-surface-2">{busy === r.id ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}</button>}
                  <button type="button" aria-label={t("Padam", "Delete")} onClick={remove(r)} className="rounded-pill p-1.5 text-muted hover:bg-surface-2"><Trash2 size={14} /></button>
                </span>
              </div>
              {r.error && <p className={`mt-1 flex items-center gap-1 text-xs ${r.status === "error" ? "text-danger" : "text-warn"}`}><AlertTriangle size={12} /> {r.error}</p>}
              {isOpen && doc && (
                <>
                  {langs.length > 1 && <div className="mt-2 flex gap-1.5 text-xs">{langs.map((l) => <button key={l} type="button" onClick={() => setShowLang((s) => ({ ...s, [r.id]: l }))} aria-pressed={cur === l} className={`rounded-pill px-3 py-1 ${cur === l ? "bg-ink text-bg" : "bg-surface-2 text-muted"}`}>{l === "en" ? "English" : "BM"}</button>)}</div>}
                  <Preview doc={doc} t={t} />
                </>
              )}
            </li>
          );
        })}
      </ul>
    </Card>
  );
}
