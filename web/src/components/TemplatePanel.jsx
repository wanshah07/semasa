import { useState } from "react";
import { AlertTriangle, ChevronDown, FilePlus2, FileText, LayoutTemplate, Loader2, Pencil, Plus, RefreshCw, Trash2 } from "lucide-react";
import { TABLES, errText, supabase } from "../lib/SupabaseClient";
import { useLang } from "../lib/i18n";
import { timeAgo } from "../lib/format";
import { KIND_WORDS, STATUS_WORDS, editProblems, editRows, structureFromEdit } from "../lib/documents";
import Button from "./ui/Button";
import Card from "./ui/Card";
import { Input, Label, Modal, Select, TextArea } from "./ui/Field";

/* Document templates (supabase/038_doc_templates.sql): the references added, what the AI made of each, a place to correct the
   sections and the columns, and the way to use one for a document. A template is its structure: its titles in both languages,
   the kind of each section and its table columns. */
const TONE = { pending: "bg-accent/10 text-accent", working: "bg-accent/10 text-accent", done: "bg-ok/10 text-ok", error: "bg-danger/10 text-danger" };
const BLANK_ROW = { headingMs: "", headingEn: "", kind: "paragraphs", columnsMs: "", columnsEn: "", hint: "", optional: false };

function Editor({ template, onClose, onSaved, onToast }) {
  const { t, lang } = useLang();
  const L = lang === "en" ? 1 : 0;
  const [name, setName] = useState(template.name || "");
  const [description, setDescription] = useState(template.description || "");
  const [rows, setRows] = useState(() => editRows(template));
  const [busy, setBusy] = useState(false);
  const set = (i, k, v) => setRows((cur) => cur.map((r, j) => (j === i ? { ...r, [k]: v } : r)));
  const move = (i, d) => setRows((cur) => { const j = i + d; if (j < 0 || j >= cur.length) return cur; const c = [...cur]; [c[i], c[j]] = [c[j], c[i]]; return c; });
  const save = async () => {
    const bad = editProblems(rows);
    if (!name.trim()) bad.unshift(["nama", "name"]);
    if (bad.length) return onToast(t("Semak: {f}", "Check: {f}", { f: bad.map((b) => b[L]).join("; ") }), "danger");
    setBusy(true);
    try {
      const { error } = await supabase.from(TABLES.docTemplates).update({ name: name.trim().slice(0, 120), description: description.trim().slice(0, 300), structure: structureFromEdit(rows), warnings: [], status: "done", error: "" }).eq("id", template.id);
      if (error) throw new Error(errText(error));
      onToast(t("Templat disimpan.", "Template saved."), "ok"); onSaved(); onClose();
    } catch (e) { onToast(e.message || String(e), "danger"); } finally { setBusy(false); }
  };
  return (
    <Modal open onClose={onClose} title={t("Sunting templat", "Edit template")}>
      <div className="space-y-3">
        <div><Label>{t("Nama", "Name")}</Label><Input aria-label={t("Nama", "Name")} value={name} maxLength={120} onChange={(e) => setName(e.target.value)} /></div>
        <div><Label>{t("Keterangan", "Description")}</Label><Input value={description} maxLength={300} onChange={(e) => setDescription(e.target.value)} /></div>
        <p className="text-xs text-muted">{t(`Bahasa asal rujukan: ${template.source_lang === "en" ? "English" : "BM"}. Tajuk dalam bahasa lain dipaparkan apabila dokumen dibuat dalam bahasa itu. Lajur yang bernama Bil. dinomborkan sendiri; lajur pemilik, tarikh, versi atau tandatangan hanya diisi jika bahan menyebutnya.`,
          `The reference's own language: ${template.source_lang === "en" ? "English" : "BM"}. The other language's titles are used when a document is made in it. A column called No. is numbered automatically; an owner, date, version or signature column is filled only if the material names it.`)}</p>
        {rows.map((r, i) => (
          <div key={i} className="space-y-2 rounded-tile border border-line p-3">
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted">{i + 1}</span>
              <Select value={r.kind} onChange={(v) => set(i, "kind", v)} aria-label={t("Jenis bahagian", "Section kind")} options={Object.entries(KIND_WORDS).map(([k, w]) => [k, w[L]])} />
              <label className="flex items-center gap-1 text-[11px] text-muted"><input type="checkbox" checked={r.optional} disabled={r.kind === "table"} onChange={(e) => set(i, "optional", e.target.checked)} /> {t("pilihan", "optional")}</label>
              <span className="ml-auto flex gap-1">
                <button type="button" aria-label={t("Naik", "Move up")} onClick={() => move(i, -1)} className="rounded-pill px-2 py-1 text-xs text-muted hover:bg-surface-2">↑</button>
                <button type="button" aria-label={t("Turun", "Move down")} onClick={() => move(i, 1)} className="rounded-pill px-2 py-1 text-xs text-muted hover:bg-surface-2">↓</button>
                <button type="button" aria-label={t("Buang bahagian", "Remove section")} onClick={() => setRows((cur) => cur.filter((_, j) => j !== i))} className="rounded-pill p-1.5 text-muted hover:bg-surface-2"><Trash2 size={13} /></button>
              </span>
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              <div><Label>{t("Tajuk BM", "Title BM")}</Label><Input aria-label={`${t("Tajuk BM", "Title BM")} ${i + 1}`} value={r.headingMs} maxLength={120} onChange={(e) => set(i, "headingMs", e.target.value)} /></div>
              <div><Label>{t("Tajuk English", "Title English")}</Label><Input aria-label={`${t("Tajuk English", "Title English")} ${i + 1}`} value={r.headingEn} maxLength={120} onChange={(e) => set(i, "headingEn", e.target.value)} /></div>
            </div>
            {r.kind === "table" && (
              <div className="grid gap-2 sm:grid-cols-2">
                <div><Label hint="a | b | c">{t("Lajur BM", "Columns BM")}</Label><Input aria-label={`${t("Lajur BM", "Columns BM")} ${i + 1}`} value={r.columnsMs} onChange={(e) => set(i, "columnsMs", e.target.value)} /></div>
                <div><Label hint="a | b | c">{t("Lajur English", "Columns English")}</Label><Input aria-label={`${t("Lajur English", "Columns English")} ${i + 1}`} value={r.columnsEn} onChange={(e) => set(i, "columnsEn", e.target.value)} /></div>
              </div>
            )}
            <div><Label hint={t("apa yang patut ada di sini", "what belongs here")}>{t("Panduan untuk AI", "Guidance for the AI")}</Label><TextArea aria-label={`${t("Panduan untuk AI", "Guidance for the AI")} ${i + 1}`} rows={2} value={r.hint} maxLength={300} onChange={(e) => set(i, "hint", e.target.value)} /></div>
          </div>
        ))}
        <Button variant="ghost" size="sm" onClick={() => setRows((cur) => [...cur, { ...BLANK_ROW }])}><Plus size={13} /> {t("Tambah bahagian", "Add a section")}</Button>
      </div>
      <div className="mt-4 flex justify-end gap-2">
        <Button variant="ghost" size="sm" onClick={onClose}>{t("Batal", "Cancel")}</Button>
        <Button size="sm" disabled={busy} onClick={save}>{busy ? <Loader2 size={13} className="animate-spin" /> : null} {t("Simpan", "Save")}</Button>
      </div>
    </Modal>
  );
}

export default function TemplatePanel({ templates, onAdd, onUse, onToast }) {
  const { t, lang } = useLang();
  const L = lang === "en" ? 1 : 0;
  const [open, setOpen] = useState("");
  const [editing, setEditing] = useState(null);
  const [busy, setBusy] = useState("");
  const missing = /semasa_doc_templates/.test(templates.error || "");
  const guard = (id, fn) => async () => { setBusy(id); try { await fn(); } catch (e) { onToast(e.message || String(e), "danger"); } finally { setBusy(""); } };
  const reread = (r) => guard(r.id, async () => {
    if (r.status === "done" && !window.confirm(t("Baca semula rujukan? Struktur semasa (termasuk sunting anda) diganti.", "Read the reference again? The current structure, including your edits, is replaced."))) return;
    const { error } = await supabase.from(TABLES.docTemplates).update({ status: "pending", attempts: 0, error: "" }).eq("id", r.id);
    if (error) throw new Error(errText(error));
    templates.reload(); onToast(t("Dihantar semula kepada AI.", "Sent to the AI again."), "ok");
  });
  const remove = (r) => guard(r.id, async () => {
    if (!window.confirm(t("Padam templat ini? Dokumen yang sudah dibuat kekal.", "Delete this template? Documents already made stay."))) return;
    const { error } = await supabase.from(TABLES.docTemplates).delete().eq("id", r.id);
    if (error) throw new Error(errText(error));
    templates.reload();
  });

  return (
    <Card className="mb-6 p-4">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <p className="flex items-center gap-1.5 text-xs font-medium text-muted"><LayoutTemplate size={13} /> {t("Templat dokumen", "Document templates")} · {templates.rows.length}</p>
        <Button size="sm" variant="soft" className="ml-auto" onClick={onAdd}><FilePlus2 size={13} /> {t("Tambah rujukan", "Add a reference")}</Button>
      </div>
      {missing && <p className="mb-2 rounded-tile bg-warn/10 p-3 text-sm text-warn">{t("Jadual templat belum ada: jalankan supabase/038_doc_templates.sql sekali (selepas 037).", "The templates table is not there yet: run supabase/038_doc_templates.sql once (after 037).")}</p>}
      {!templates.rows.length && !missing && <p className="text-sm text-muted">{t("Belum ada templat. Tambah borang, templat SOP atau contoh dokumen anda; AI menjadikannya templat dan anda boleh memilihnya apabila membuat dokumen.", "No templates yet. Add your form, SOP template or an example document; the AI makes it a template and you can choose it when making a document.")}</p>}
      <ul className="divide-y divide-line/60">
        {templates.rows.map((r) => {
          const isOpen = open === r.id;
          const done = r.status === "done";
          return (
            <li key={r.id} className="py-2.5 text-sm">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <span className={`rounded-pill px-2 py-0.5 text-[11px] ${TONE[r.status] || ""}`}>{(STATUS_WORDS[r.status] || [r.status, r.status])[L]}</span>
                <span className="min-w-0 flex-1 truncate font-medium">{r.name}</span>
                {done && <span className="text-xs text-muted">{t("{n} bahagian", ["{n} section", "{n} sections"], { n: (r.structure || []).length })} · {r.source_lang === "en" ? "EN" : "BM"}{r.source_file ? ` · ${r.source_file}` : ""}</span>}
                <span className="text-xs text-muted">{timeAgo(r.updated_at || r.created_at)}</span>
                <span className="flex flex-wrap gap-1">
                  {done && <Button size="sm" variant="soft" onClick={() => onUse(r)}><FileText size={12} /> {t("Guna", "Use")}</Button>}
                  {done && <button type="button" onClick={() => setOpen(isOpen ? "" : r.id)} aria-expanded={isOpen} aria-label={t("Lihat bahagian", "See the sections")} className="rounded-pill p-1.5 text-muted hover:bg-surface-2"><ChevronDown size={14} className={isOpen ? "rotate-180" : ""} /></button>}
                  {done && <button type="button" onClick={() => setEditing(r)} aria-label={t("Sunting templat", "Edit template")} className="rounded-pill p-1.5 text-muted hover:bg-surface-2"><Pencil size={14} /></button>}
                  {["done", "error"].includes(r.status) && <button type="button" onClick={reread(r)} aria-label={t("Baca semula", "Read again")} title={t("Baca semula", "Read again")} className="rounded-pill p-1.5 text-muted hover:bg-surface-2">{busy === r.id ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}</button>}
                  <button type="button" onClick={remove(r)} aria-label={t("Padam templat", "Delete template")} className="rounded-pill p-1.5 text-muted hover:bg-surface-2"><Trash2 size={14} /></button>
                </span>
              </div>
              {r.description && done && <p className="mt-0.5 text-xs text-muted">{r.description}</p>}
              {r.error && <p className={`mt-1 flex items-center gap-1 text-xs ${r.status === "error" ? "text-danger" : "text-warn"}`}><AlertTriangle size={12} /> {r.error}</p>}
              {done && (r.warnings || []).length > 0 && (
                <p className="mt-1 flex items-start gap-1 text-xs text-warn"><AlertTriangle size={12} className="mt-0.5 shrink-0" />
                  <span>{t("Tidak ditemui dalam rujukan (semak atau sunting): ", "Not found in the reference (check or edit): ")}{r.warnings.join("; ")}</span></p>
              )}
              {isOpen && done && (
                <ol className="mt-2 space-y-1 border-t border-line/60 pt-2 text-xs">
                  {r.structure.map((s) => (
                    <li key={s.key} className="flex flex-wrap items-baseline gap-x-2">
                      <span className="font-medium">{s.heading?.[lang === "en" ? "en" : "ms"]}</span>
                      <span className="rounded-pill bg-surface-2 px-2 py-0.5 text-[10px] text-muted">{(KIND_WORDS[s.kind] || [s.kind, s.kind])[L]}{s.optional ? ` · ${t("pilihan", "optional")}` : ""}</span>
                      {s.columns?.length > 0 && <span className="text-muted">{s.columns.map((c) => c[lang === "en" ? "en" : "ms"]).join(" | ")}</span>}
                    </li>
                  ))}
                </ol>
              )}
            </li>
          );
        })}
      </ul>
      {editing && <Editor template={editing} onClose={() => setEditing(null)} onSaved={templates.reload} onToast={onToast} />}
    </Card>
  );
}
