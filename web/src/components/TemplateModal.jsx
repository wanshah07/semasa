import { useState } from "react";
import { FileUp, Loader2, X } from "lucide-react";
import { TABLES, errText, supabase } from "../lib/SupabaseClient";
import { useLang } from "../lib/i18n";
import { LIMITS, templateRow } from "../lib/documents";
import { readReference } from "../lib/templateOutline";
import Button from "./ui/Button";
import { Input, Label, Modal } from "./ui/Field";

/* Add a reference document and the AI makes a template of it (supabase/038_doc_templates.sql). The words of the file are read here
   (a Word form keeps its headings and its table marked); the worker lists the sections and table columns in the reference's own
   words with the other language beside them, and the template shows up under Templat dokumen, ready to edit and to choose. The file
   itself is not stored. A PDF or a picture is not read for a template yet. */
export default function TemplateModal({ open, onClose, user, onToast, onSent }) {
  const { t } = useLang();
  const [refs, setRefs] = useState([]);                 // [{ file, reference }] read here
  const [name, setName] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  const add = async (list) => {
    for (const f of Array.from(list || [])) {
      try {
        const reference = await readReference(f);
        setRefs((cur) => [...cur.filter((c) => c.reference.file !== reference.file), { reference }]);
      } catch (e) { onToast(e.message || String(e), "danger"); }
    }
  };
  const send = async () => {
    if (!refs.length) return onToast(t("Pilih sekurang-kurangnya satu fail rujukan.", "Pick at least one reference file."), "danger");
    setBusy(true);
    try {
      const rows = refs.map((r) => templateRow({ reference: r.reference, name: refs.length === 1 ? name : "", note, userId: user?.id || null }));
      const { error } = await supabase.from(TABLES.docTemplates).insert(rows);
      if (error) throw new Error(/semasa_doc_templates/.test(errText(error)) ? t("Jadual belum ada: jalankan supabase/038_doc_templates.sql sekali (selepas 037).", "The table is not there yet: run supabase/038_doc_templates.sql once (after 037).") : errText(error));
      onToast(t("{n} rujukan dihantar. AI menjadikannya templat dalam seminit dua.", ["{n} reference sent. The AI makes it a template within a minute or two.", "{n} references sent. The AI makes them templates within a minute or two."], { n: rows.length }), "ok");
      setRefs([]); setName(""); setNote(""); onSent?.(); onClose();
    } catch (e) { onToast(e.message || String(e), "danger"); } finally { setBusy(false); }
  };

  return (
    <Modal open={open} onClose={onClose} title={t("Tambah dokumen rujukan", "Add a reference document")}>
      <div className="space-y-3">
        <p className="rounded-tile bg-surface-2 p-3 text-xs text-muted">
          {t("Letak borang kosong, templat SOP atau contoh dokumen (Word, Excel, CSV, teks atau Markdown). AI membaca bahagian dan lajur jadualnya dan menjadikannya templat: tajuk diikut perkataan demi perkataan, dengan BM dan English di sebelah masing-masing. Fail itu tidak disimpan, hanya perkataannya. Jangan gunakan contoh yang sudah diisi dengan data klien sebenar.",
            "Add a blank form, a SOP template or an example document (Word, Excel, CSV, text or Markdown). The AI reads its sections and table columns and makes a template: titles word for word, with BM and English side by side. The file is not stored, only its words. Do not use an example that is filled in with a real client's data.")}
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-pill border border-line px-3 py-1.5 text-xs text-muted hover:border-accent">
            <FileUp size={13} /> {t("Pilih fail rujukan", "Pick reference files")}
            <input type="file" multiple accept=".docx,.xlsx,.csv,.tsv,.txt,.md" className="hidden" onChange={(e) => { add(e.target.files); e.target.value = ""; }} />
          </label>
          {refs.map((r) => (
            <span key={r.reference.file} className="inline-flex items-center gap-1 rounded-pill bg-surface-2 px-2.5 py-1 text-[11px]" title={`${r.reference.text.length.toLocaleString()} ${t("aksara dibaca", "characters read")}${r.reference.cut ? t(" (dipotong)", " (cut)") : ""}`}>
              {r.reference.file}
              <button type="button" aria-label={t("Buang", "Remove")} onClick={() => setRefs((cur) => cur.filter((c) => c !== r))}><X size={11} /></button>
            </span>
          ))}
        </div>
        {refs.length === 1 && <div><Label hint={t("pilihan", "optional")}>{t("Nama templat", "Template name")}</Label><Input value={name} maxLength={120} onChange={(e) => setName(e.target.value)} placeholder={refs[0].reference.name} /></div>}
        <div><Label hint={t("pilihan", "optional")}>{t("Untuk apa dokumen ini", "What this document is for")}</Label>
          <Input value={note} maxLength={LIMITS.note} onChange={(e) => setNote(e.target.value)} placeholder={t("cth. borang NCR untuk pembekal bahan", "e.g. an NCR form for material suppliers")} /></div>
      </div>
      <div className="mt-4 flex justify-end gap-2">
        <Button variant="ghost" size="sm" onClick={onClose}>{t("Batal", "Cancel")}</Button>
        <Button size="sm" disabled={busy || !refs.length} onClick={send}>{busy ? <Loader2 size={13} className="animate-spin" /> : null} {t("Jadikan templat", "Make a template")}</Button>
      </div>
    </Modal>
  );
}
