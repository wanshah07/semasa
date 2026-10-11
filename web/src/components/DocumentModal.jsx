import { useState } from "react";
import { FileUp, Loader2, X } from "lucide-react";
import { TABLES, errText, supabase } from "../lib/SupabaseClient";
import { useLang } from "../lib/i18n";
import { prepareFile } from "../lib/brainFiles";
import { useTable } from "../lib/hooks";
import { BUILTIN_TYPES, LANG_CHOICES, LIMITS, MARKER, STATUS, assembleSource, requestRow, typeOf, usableTemplates, validateRequest } from "../lib/documents";
import Button from "./ui/Button";
import { Input, Label, Modal, Segmented, Select, TextArea } from "./ui/Field";

/* Ask the bot for a document (supabase/037_brain_docs.sql). The material is what was picked in the tab that opened this
   (Otak entries or FAQs) plus any facts pasted here and any Word / Excel / CSV / text file read here. The worker
   (backend/semasa/brain_docs.py) drafts it in Bahasa Malaysia, English or both; it comes back in the Dokumen list in the Otak
   tab as a Word file. A PDF or a picture is dropped into Otak first and its entries picked here: the page reads only words. */
export default function DocumentModal({ open, onClose, user, onToast, items = [], scope = "", defaultType = "faq_pack", templates, presetTemplate = "", onSent }) {
  const { t, lang } = useLang();
  const L = lang === "en" ? 1 : 0;
  const loaded = useTable(TABLES.docTemplates, { enabled: open && templates === undefined, realtime: false, limit: 100 });
  const tpls = usableTemplates(templates ?? loaded.rows);
  const [via, setVia] = useState(presetTemplate ? "template" : "builtin");      // the structure comes from a built-in type or from one of my templates
  const [templateId, setTemplateId] = useState(presetTemplate || "");
  const [type, setType] = useState(defaultType);
  const [docLang, setDocLang] = useState("ms");
  const [title, setTitle] = useState("");
  const [note, setNote] = useState("");
  const [structure, setStructure] = useState("");
  const [facts, setFacts] = useState("");
  const [files, setFiles] = useState([]);                 // [{ name, text }] read here
  const [busy, setBusy] = useState(false);
  const chosen = via === "template" ? tpls.find((x) => x.id === (templateId || tpls[0]?.id)) || null : null;
  const effType = via === "template" ? "template" : type;
  const spec = via === "template" ? (chosen ? { description: [chosen.description, chosen.description], sections: chosen.structure.map((s) => ({ heading: [s.heading.ms, s.heading.en] })) } : null) : typeOf(type);
  const source = assembleSource({ items: [...items, ...files.map((f) => ({ kind: "file", id: "", title: f.name, text: f.text }))], text: facts });
  const bad = validateRequest({ type: effType, lang: docLang, source, structure, template: chosen });

  const addFiles = async (list) => {
    for (const f of Array.from(list || [])) {
      try {
        const { row, upload } = await prepareFile(f);
        if (upload) throw new Error(t(`${f.name}: PDF atau gambar tidak dibaca di sini. Letak dalam Otak dahulu, kemudian pilih entrinya.`, `${f.name}: a PDF or a picture is not read here. Drop it in the brain first, then pick its entries.`));
        setFiles((cur) => [...cur.filter((c) => c.name !== f.name), { name: f.name, text: row.body || "" }]);
      } catch (e) { onToast(e.message || String(e), "danger"); }
    }
  };

  const send = async () => {
    if (bad.length) return onToast(t("Semak: {f}", "Check: {f}", { f: bad.map((b) => b[L]).join("; ") }), "danger");
    setBusy(true);
    try {
      const { error } = await supabase.from(TABLES.brainDocs).insert(requestRow({ type: effType, lang: docLang, title, note, structure, source, userId: user?.id || null, template: chosen }));
      if (error) throw new Error(/semasa_brain_docs/.test(errText(error)) ? t("Jadual belum ada: jalankan supabase/037_brain_docs.sql sekali.", "The table is not there yet: run supabase/037_brain_docs.sql once.") : errText(error));
      onToast(t("Dihantar. Draf siap dalam seminit dua: lihat Otak AI → Dokumen.", "Sent. The draft is ready in a minute or two: see AI brain → Documents."), "ok");
      setFiles([]); setFacts(""); setNote(""); setTitle("");
      onSent?.(); onClose();
    } catch (e) { onToast(e.message || String(e), "danger"); } finally { setBusy(false); }
  };

  return (
    <Modal open={open} onClose={onClose} title={t("Buat dokumen", "Make a document")}>
      <div className="space-y-3">
        <p className="rounded-tile bg-warn/10 p-3 text-xs text-warn">
          {t(`Setiap dokumen ialah ${STATUS.ms}. AI tidak menentukan status halal, pematuhan atau kelulusan, dan tidak mereka nama, tarikh, nombor, versi, tandatangan atau pemilik. Apa yang tiada dalam bahan ditanda ${MARKER.ms}.`,
            `Every document is a ${STATUS.en}. The AI does not decide halal status, compliance or approval, and invents no name, date, number, version, signature or owner. Whatever the material lacks is marked ${MARKER.en}.`)}
        </p>
        <div>
          <Label>{t("Struktur dokumen", "Document structure")}</Label>
          <Segmented value={via} onChange={setVia} options={[["builtin", t("Jenis siap", "Built-in types")], ["template", t("Templat saya ({n})", "My templates ({n})", { n: tpls.length })]]} />
          {via === "builtin" ? (
            <div className="mt-2">
              <Select className="w-full" value={type} onChange={setType} aria-label={t("Jenis dokumen", "Document type")} options={BUILTIN_TYPES.map((d) => [d.id, d.label[L]])} />
              <p className="mt-1 text-xs text-muted">{spec?.description[L]}</p>
            </div>
          ) : tpls.length ? (
            <div className="mt-2">
              <Select className="w-full" value={chosen?.id || ""} onChange={setTemplateId} aria-label={t("Templat", "Template")} options={tpls.map((x) => [x.id, x.name])} />
              {chosen?.description && <p className="mt-1 text-xs text-muted">{chosen.description}</p>}
            </div>
          ) : <p className="mt-2 text-xs text-warn">{t("Belum ada templat yang siap. Tambah dokumen rujukan di Otak AI → Templat dokumen.", "No template is ready yet. Add a reference document under AI brain → Document templates.")}</p>}
          {spec && spec.sections.length > 0 && <p className="mt-1 text-[11px] text-muted">{spec.sections.map((s) => s.heading[L]).join(" · ")}</p>}
        </div>
        <div>
          <Label>{t("Bahasa dokumen", "Document language")}</Label>
          <Segmented value={docLang} onChange={setDocLang} options={LANG_CHOICES.map(([v, ms, en]) => [v, L ? en : ms])} />
          {docLang === "both" && <p className="mt-1 text-xs text-muted">{t("Dua fail Word: satu BM, satu English, masing-masing ditulis daripada bahan yang sama.", "Two Word files: one BM, one English, each written from the same material.")}</p>}
        </div>
        {via === "builtin" && type === "custom" && (
          <div><Label hint={t("satu bahagian setiap baris; tambah | untuk jadual dan lajurnya", "one section per line; add | for a table and its columns")}>{t("Struktur anda", "Your structure")}</Label>
            <TextArea rows={5} maxLength={LIMITS.structure} value={structure} onChange={(e) => setStructure(e.target.value)} placeholder={"Tujuan\nSkop\nSenarai semak | Item | Status | Catatan"} /></div>
        )}
        <div><Label>{t("Tajuk kerja (pilihan)", "Working title (optional)")}</Label><Input value={title} maxLength={120} onChange={(e) => setTitle(e.target.value)} /></div>
        <div><Label hint={t("pilihan", "optional")}>{t("Apa yang anda mahu", "What you want")}</Label>
          <Input value={note} maxLength={LIMITS.note} onChange={(e) => setNote(e.target.value)} placeholder={t("cth. untuk klien kosmetik, fokus pada pelabelan", "e.g. for a cosmetics client, focus on labelling")} /></div>
        <div>
          <Label hint={`${scope ? `${scope} · ` : ""}${t("{n} bahan, {c} aksara", ["{n} item, {c} characters", "{n} items, {c} characters"], { n: source.refs.length, c: source.chars.toLocaleString() })}`}>{t("Bahan", "Material")}</Label>
          {items.length > 0 && <p className="mb-1 text-xs text-muted">{items.slice(0, 6).map((i) => i.title).join(" · ")}{items.length > 6 ? ` +${items.length - 6}` : ""}</p>}
          <TextArea rows={4} value={facts} onChange={(e) => setFacts(e.target.value)} placeholder={t("Tampal fakta, nota proses atau transkrip di sini. Dokumen hanya ditulis daripada bahan ini.", "Paste facts, process notes or a transcript here. The document is written from this material only.")} />
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-pill border border-line px-3 py-1.5 text-xs text-muted hover:border-accent">
              <FileUp size={13} /> {t("Tambah fail (Word, Excel, CSV, teks)", "Add a file (Word, Excel, CSV, text)")}
              <input type="file" multiple accept=".docx,.xlsx,.csv,.tsv,.txt,.md,.json" className="hidden" onChange={(e) => { addFiles(e.target.files); e.target.value = ""; }} />
            </label>
            {files.map((f) => (
              <span key={f.name} className="inline-flex items-center gap-1 rounded-pill bg-surface-2 px-2.5 py-1 text-[11px]">{f.name}
                <button type="button" aria-label={t("Buang", "Remove")} onClick={() => setFiles((cur) => cur.filter((c) => c.name !== f.name))}><X size={11} /></button></span>
            ))}
          </div>
          {source.over && <p className="mt-2 text-xs text-warn">{t(`Hanya ${LIMITS.read.toLocaleString()} aksara pertama dibaca oleh AI. Kurangkan pilihan supaya semua bahan dibaca.`, `The AI reads only the first ${LIMITS.read.toLocaleString()} characters. Pick fewer items so all of the material is read.`)}</p>}
        </div>
      </div>
      <div className="mt-4 flex justify-end gap-2">
        <Button variant="ghost" size="sm" onClick={onClose}>{t("Batal", "Cancel")}</Button>
        <Button size="sm" disabled={busy || bad.length > 0} onClick={send}>{busy ? <Loader2 size={13} className="animate-spin" /> : null} {t("Buat draf", "Make the draft")}</Button>
      </div>
    </Modal>
  );
}
