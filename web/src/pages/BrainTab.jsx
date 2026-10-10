import { useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import { AlertTriangle, BookOpen, Brain, ChevronDown, Clipboard, Download, FileUp, HelpCircle, ListChecks, Pencil, Pin, PinOff, Plus, RefreshCw, ScrollText, Search, Sparkles, Terminal, Trash2, Wand2 } from "lucide-react";
import { fadeUp } from "../design/motion";
import { TABLES, errText, supabase } from "../lib/SupabaseClient";
import { useLang } from "../lib/i18n";
import { useTable } from "../lib/hooks";
import { timeAgo } from "../lib/format";
import { removeReference, shrinkPhoto, uploadReference } from "../lib/storage";
import { download } from "../lib/faqExport";
import { prepareFile } from "../lib/brainFiles";
import {
  KINDS, KIND_HELP, KIND_WORDS, SOURCE_WORDS, STATUS_WORDS, brainSummary, categoriesOf, copyText, entryRow, exportFiles, filterEntries,
  hostOf, inboxLabel, isWalled, rowsFromPaste, tagCloud, toMarkdown, toSkillMd, validateEntry,
} from "../lib/brain";
import Markdown from "../components/Markdown";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import { Input, Label, Modal, Select, TextArea } from "../components/ui/Field";

/* Otak AI (supabase/036_brain.sql): drop text, a picture, a file, a link or a page to scrape; the worker (backend/semasa/brain.py)
   reads it with the AI gateway (Afiq's rootsys, Mireld as the backup) and files it as notes, FAQs, skills, prompts, references
   and checklists with a category and tags. This page drops things in, shows how the reading stands, and lets Wan search, edit,
   pin, copy and export what was filed. It reads nothing itself and posts nothing. */

const KIND_ICON = { note: ScrollText, faq: HelpCircle, skill: Wand2, prompt: Terminal, reference: BookOpen, checklist: ListChecks };
const KIND_TONE = { note: "bg-surface-2 text-ink", faq: "bg-accent/10 text-accent", skill: "bg-ok/10 text-ok", prompt: "bg-warn/10 text-warn", reference: "bg-surface-2 text-muted", checklist: "bg-surface-2 text-ink" };
const STATUS_TONE = { pending: "bg-accent/10 text-accent", working: "bg-accent/10 text-accent", done: "bg-ok/10 text-ok", needs_text: "bg-warn/10 text-warn", error: "bg-danger/10 text-danger" };
const BLANK = { kind: "note", category: "lain", title: "", summary: "", body: "", question: "", answer: "", tags: "", when: "", steps: "", use: "", items: "" };

export default function BrainTab({ user, settings, save, onToast }) {
  const { t, lang } = useLang();
  const L = lang === "en" ? 1 : 0;
  const w = (map, k) => (map[k] || [k, k])[L];
  const entriesT = useTable(TABLES.brainEntries, { enabled: true, order: "created_at", limit: 3000 });
  const inboxT = useTable(TABLES.brainInbox, { enabled: true, order: "created_at", limit: 300 });
  const [text, setText] = useState("");
  const [note, setNote] = useState("");
  const [hint, setHint] = useState("");
  const [scrape, setScrape] = useState(false);
  const [busy, setBusy] = useState("");
  const [over, setOver] = useState(false);
  const [filter, setFilter] = useState({ kind: "", category: "", tag: "", q: "", pinned: false });
  const [open, setOpen] = useState(null);
  const [editing, setEditing] = useState(null);
  const [catsOpen, setCatsOpen] = useState(false);
  const [catsText, setCatsText] = useState("");
  const fileRef = useRef(null);
  const entries = entriesT.rows;
  const missing = /semasa_brain/.test(entriesT.error || inboxT.error || "");
  const sum = useMemo(() => brainSummary(entries, inboxT.rows), [entries, inboxT.rows]);
  const cats = useMemo(() => categoriesOf(entries, settings?.brain?.categories), [entries, settings]);
  const shown = useMemo(() => filterEntries(entries, filter), [entries, filter]);
  const cloud = useMemo(() => tagCloud(entries), [entries]);
  const inbox = useMemo(() => inboxT.rows.filter((r) => r.status !== "done" || Date.now() - Date.parse(r.updated_at || r.created_at) < 6 * 3600_000).slice(0, 12), [inboxT.rows]);
  const guard = (fn) => async (...a) => { try { await fn(...a); } catch (e) { onToast(e.message || String(e), "danger"); } };
  const noTable = () => t("Jadual belum ada: jalankan supabase/036_brain.sql sekali.", "The tables are not there yet: run supabase/036_brain.sql once.");
  const insertRows = async (rows) => {
    const { error } = await supabase.from(TABLES.brainInbox).insert(rows.map((r) => ({ ...r, status: "pending", created_by: user?.id || null })));
    if (error) throw new Error(/semasa_brain/.test(errText(error)) ? noTable() : errText(error));
  };

  // everything dropped, pasted or picked goes through here: words and links first, then each file by itself
  const drop = guard(async (files = []) => {
    setBusy("drop");
    const rows = [];
    const problems = [];
    try {
      const pasted = rowsFromPaste(text, { scrape, hint, note });
      rows.push(...pasted.rows);
      if (pasted.cut) problems.push(t("Teks terlalu panjang: 60,000 aksara pertama sahaja dihantar.", "The text is too long: only the first 60,000 characters were sent."));
      if (pasted.extra) problems.push(t("{n} pautan lebihan tidak dihantar (had 40 sekali hantar).", "{n} extra links were not sent (40 at a time).", { n: pasted.extra }));
      for (const file of files) {
        try {
          const { row, upload } = await prepareFile(file, { shrink: (f) => shrinkPhoto(f, 1600) });
          const extra = { hint: hint || "", note: note.trim().slice(0, 500) };
          if (upload) {
            const up = await uploadReference(user, upload);
            rows.push({ ...row, ...extra, image_path: up.path, image_url: up.url });
          } else rows.push({ ...row, ...extra });
        } catch (e) { problems.push(e.message || String(e)); }
      }
      if (rows.length) await insertRows(rows);
      if (rows.length) {
        setText(""); setNote("");
        onToast(t("{n} dihantar ke Otak. AI membaca dan memfailkannya dalam seminit dua.", "{n} sent to the brain. The AI reads and files them within a minute or two.", { n: rows.length }), "ok");
        inboxT.reload();
      } else if (!problems.length) onToast(t("Tiada apa untuk dihantar: tampal teks atau pautan, atau pilih fail.", "Nothing to send: paste text or a link, or pick a file."), "info");
      problems.forEach((p) => onToast(p, "danger"));
    } finally { setBusy(""); if (fileRef.current) fileRef.current.value = ""; }
  });
  const onPaste = (e) => {
    const imgs = Array.from(e.clipboardData?.files || []).filter((f) => f.type.startsWith("image/"));
    if (imgs.length) { e.preventDefault(); drop(imgs); }                      // a pasted screenshot is dropped straight away
  };
  const onDrop = (e) => { e.preventDefault(); setOver(false); const fs = Array.from(e.dataTransfer?.files || []); if (fs.length) drop(fs); };

  const reread = guard(async (r) => {
    const { error } = await supabase.from(TABLES.brainInbox).update({ status: "pending", attempts: 0, error: "" }).eq("id", r.id);
    if (error) throw new Error(errText(error));
    inboxT.reload(); onToast(t("Dihantar semula kepada AI. Entri yang anda sunting kekal.", "Sent back to the AI. Entries you edited stay."), "ok");
  });
  const removeInbox = guard(async (r) => {
    if (!window.confirm(t("Padam item ini dari peti masuk? Entri yang sudah difailkan kekal.", "Delete this item from the inbox? Entries already filed stay."))) return;
    const { error } = await supabase.from(TABLES.brainInbox).delete().eq("id", r.id);
    if (error) throw new Error(errText(error));
    if (r.image_path) { try { await removeReference(r.image_path); } catch { /* the bucket copy is not the record */ } }
    inboxT.reload();
  });
  const togglePin = guard(async (e) => {
    const { error } = await supabase.from(TABLES.brainEntries).update({ pinned: !e.pinned }).eq("id", e.id);
    if (error) throw new Error(errText(error));
    entriesT.reload();
  });
  const removeEntry = guard(async (e) => {
    if (!window.confirm(t("Padam entri ini?", "Delete this entry?"))) return;
    const { error } = await supabase.from(TABLES.brainEntries).delete().eq("id", e.id);
    if (error) throw new Error(errText(error));
    entriesT.reload(); onToast(t("Dipadam.", "Deleted."), "info");
  });
  const saveEntry = guard(async (form) => {
    const bad = validateEntry(form);
    if (bad.length) return onToast(t("Semak: {f}", "Check: {f}", { f: bad.join(", ") }), "danger");
    const row = entryRow(form);
    const q = form.id ? supabase.from(TABLES.brainEntries).update(row).eq("id", form.id)
      : supabase.from(TABLES.brainEntries).insert({ ...row, created_by: user?.id || null });
    const { error } = await q;
    if (error) throw new Error(/semasa_brain/.test(errText(error)) ? noTable() : errText(error));
    setEditing(null); entriesT.reload(); onToast(t("Disimpan.", "Saved."), "ok");
  });
  const saveCats = guard(async () => {
    const list = [...new Set(catsText.split(/[\n,]+/).map((c) => c.trim().toLowerCase()).filter(Boolean))];
    if (!list.includes("lain")) list.push("lain");
    await save("brain", { ...(settings?.brain || {}), categories: list });
    setCatsOpen(false); onToast(t("Kategori disimpan. Bacaan seterusnya guna senarai ini.", "Categories saved. The next reading uses this list."), "ok");
  });
  const copy = guard(async (e) => { await navigator.clipboard.writeText(copyText(e)); onToast(t("Disalin.", "Copied."), "ok"); });
  const saveFile = (e) => {
    const skill = e.kind === "skill";
    download(new Blob([skill ? toSkillMd(e) : toMarkdown(e)], { type: "text/markdown" }), skill ? "SKILL.md" : `${(e.title || "entri").replace(/[^\w-]+/g, "-").slice(0, 50)}.md`);
  };
  const exportAll = guard(async () => {
    const files = exportFiles(shown);
    if (!files.length) return onToast(t("Tiada entri untuk dieksport.", "No entries to export."), "info");
    const { zipSync, strToU8 } = await import("fflate");
    download(new Blob([zipSync(Object.fromEntries(files.map((f) => [f.name, strToU8(f.text)])), { level: 6 })], { type: "application/zip" }), "otak-semasa.zip");
    onToast(t("{n} fail dieksport (skill sebagai folder/SKILL.md).", "{n} files exported (skills as folder/SKILL.md).", { n: files.length }), "ok");
  });

  const tiles = [
    { label: t("Entri", "Entries"), value: String(sum.total), icon: Brain, hint: t("{n} dipin", "{n} pinned", { n: sum.pinned }) },
    { label: t("Menunggu AI", "Waiting for the AI"), value: String(sum.waiting), icon: RefreshCw, hint: sum.failed ? t("{n} gagal", "{n} failed", { n: sum.failed }) : t("tiada yang gagal", "none failed"), tone: sum.failed ? "danger" : "" },
    { label: t("Perlu teks", "Needs the text"), value: String(sum.needsText), icon: AlertTriangle, hint: t("pautan atau fail yang mesin tak boleh baca", "links or files a machine cannot read"), tone: sum.needsText ? "warn" : "" },
    { label: t("Perlu semakan", "Needs a look"), value: String(sum.lowConfidence), icon: Sparkles, hint: t("AI kurang pasti", "the AI was unsure"), tone: sum.lowConfidence ? "warn" : "" },
  ];
  const set = (k, v) => setFilter((f) => ({ ...f, [k]: v }));

  return (
    <main className="mx-auto max-w-page px-4 pb-20 pt-10 sm:px-6">
      <motion.div {...fadeUp} className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-3xl">{t("Otak AI", "AI brain")}</h1>
          <p className="mt-1 max-w-2xl text-sm text-muted">{t("Letak apa sahaja: teks, gambar, fail, pautan media sosial atau halaman untuk di-scrape. AI membacanya dan memfailkannya sebagai nota, FAQ, skill, prompt, rujukan atau senarai semak, lengkap dengan kategori dan tag.",
            "Drop anything: text, a picture, a file, a social-media link or a page to scrape. The AI reads it and files it as notes, FAQs, skills, prompts, references or checklists, with a category and tags.")}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="ghost" size="sm" onClick={() => { setCatsText(cats.join("\n")); setCatsOpen(true); }}>{t("Kategori", "Categories")}</Button>
          <Button variant="ghost" size="sm" onClick={exportAll}><Download size={14} /> {t("Eksport ({n})", "Export ({n})", { n: shown.length })}</Button>
          <Button size="sm" onClick={() => setEditing({ ...BLANK })}><Plus size={14} /> {t("Entri baharu", "New entry")}</Button>
        </div>
      </motion.div>

      {missing && <p className="mb-4 rounded-tile bg-warn/10 p-3 text-sm text-warn">{noTable()}</p>}
      {(entriesT.error || inboxT.error) && !missing && <p className="mb-4 rounded-tile bg-danger/10 p-3 text-sm text-danger">{entriesT.error || inboxT.error}</p>}

      <div className="mb-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {tiles.map((s) => (
          <Card key={s.label} className={`p-4 ${s.tone === "danger" ? "border-danger/40" : s.tone === "warn" ? "border-warn/40" : ""}`}>
            <div className="flex items-center justify-between"><span className="text-[11px] uppercase tracking-widest text-muted">{s.label}</span><s.icon size={16} className="text-muted" /></div>
            <p className={`mt-2 font-display text-2xl tabular-nums ${s.tone === "danger" ? "text-danger" : ""}`}>{s.value}</p>
            <p className="mt-0.5 text-xs text-muted">{s.hint}</p>
          </Card>
        ))}
      </div>

      {/* the drop zone */}
      <Card className={`mb-6 p-4 transition ${over ? "border-accent ring-2 ring-accent/30" : ""}`}
        onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)} onDrop={onDrop}>
        <TextArea rows={4} value={text} onChange={(e) => setText(e.target.value)} onPaste={onPaste} disabled={busy === "drop"}
          placeholder={t("Tampal teks atau pautan di sini (satu pautan setiap baris). Anda juga boleh tampal tangkap layar, atau seret fail ke kotak ini.",
            "Paste text or links here (one link per line). You can also paste a screenshot, or drag files onto this box.")} />
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <input ref={fileRef} type="file" multiple accept="image/*,.pdf,.docx,.xlsx,.csv,.tsv,.txt,.md,.json" className="hidden" onChange={(e) => drop(Array.from(e.target.files || []))} />
          <Button variant="ghost" size="sm" disabled={busy === "drop"} onClick={() => fileRef.current?.click()}><FileUp size={14} /> {t("Pilih fail / gambar", "Pick files / pictures")}</Button>
          <Select value={hint} onChange={setHint} aria-label={t("Jadikan", "Make it")}
            options={[["", t("AI tentukan jenis", "AI chooses the kind")], ...KINDS.map((k) => [k, t("Jadikan {k}", "Make it a {k}", { k: w(KIND_WORDS, k) })])]} />
          <label className="flex items-center gap-1.5 text-xs text-muted" title={t("Pautan dibaca seperti pelayar sebenar, termasuk halaman JavaScript, dan senarai pautan di halaman dikumpul.", "Links are read like a real browser, JavaScript pages included, and the links on the page are collected.")}>
            <input type="checkbox" checked={scrape} onChange={(e) => setScrape(e.target.checked)} /> {t("Scrape pautan", "Scrape the links")}
          </label>
          <Input className="min-w-[12rem] flex-1" value={note} maxLength={500} onChange={(e) => setNote(e.target.value)}
            placeholder={t("Nota anda untuk AI (pilihan): untuk klien mana, kenapa penting…", "Your note for the AI (optional): which client, why it matters…")} />
          <Button disabled={busy === "drop" || (!text.trim())} onClick={() => drop([])}><Brain size={14} /> {busy === "drop" ? t("Menghantar…", "Sending…") : t("Hantar ke Otak", "Send to the brain")}</Button>
        </div>
        <p className="mt-2 text-[11px] text-muted">{t("Pautan Instagram, Facebook, Threads, TikTok, LinkedIn dan X selalunya hanya dipaparkan kepada pelayar yang log masuk: jika mesin tak nampak, anda akan diberitahu dan boleh tampal kapsyen atau muat naik tangkap layar. PDF imbasan: muat naik halamannya sebagai gambar.",
          "Instagram, Facebook, Threads, TikTok, LinkedIn and X links usually show only to a signed-in browser: if the machine sees nothing you are told, and can paste the caption or upload a screenshot. Scanned PDFs: upload the pages as pictures.")}</p>
      </Card>

      {/* the inbox: what is being read and what could not be */}
      {inbox.length > 0 && (
        <Card className="mb-6 p-4">
          <p className="mb-2 text-[11px] uppercase tracking-widest text-muted">{t("Peti masuk", "Inbox")}</p>
          <ul className="divide-y divide-line/60">
            {inbox.map((r) => (
              <li key={r.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2 text-sm">
                <span className={`rounded-pill px-2 py-0.5 text-[11px] ${STATUS_TONE[r.status] || ""}`}>{w(STATUS_WORDS, r.status)}</span>
                <span className="text-[11px] uppercase tracking-wide text-muted">{w(SOURCE_WORDS, r.source_kind)}</span>
                <span className="min-w-0 flex-1 truncate">{inboxLabel(r) || "—"}{r.url && isWalled(r.url) ? <span className="ml-1 text-[11px] text-warn">{t("(perlu log masuk)", "(needs a login)")}</span> : null}</span>
                {r.status === "done" && <span className="text-xs text-muted">{t("{n} entri", "{n} entries", { n: r.entries })}{r.model ? ` · ${r.model}` : ""}</span>}
                <span className="text-xs text-muted">{timeAgo(r.updated_at || r.created_at)}</span>
                <span className="flex gap-1">
                  {["needs_text", "error", "done"].includes(r.status) && <button type="button" onClick={() => reread(r)} className="rounded-pill p-1.5 text-muted hover:bg-surface-2" aria-label={t("Baca semula", "Read again")} title={t("Baca semula", "Read again")}><RefreshCw size={14} /></button>}
                  <button type="button" onClick={() => removeInbox(r)} className="rounded-pill p-1.5 text-muted hover:bg-surface-2" aria-label={t("Padam", "Delete")}><Trash2 size={14} /></button>
                </span>
                {r.error && <p className={`basis-full text-xs ${r.status === "needs_text" ? "text-warn" : "text-danger"}`}>{r.error}</p>}
              </li>
            ))}
          </ul>
        </Card>
      )}

      {/* the library */}
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="relative min-w-[14rem] flex-1">
          <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
          <Input className="!pl-9" value={filter.q} onChange={(e) => set("q", e.target.value)} placeholder={t("Cari tajuk, isi, soalan, tag…", "Search title, body, question, tags…")} />
        </div>
        <Select value={filter.category} onChange={(v) => set("category", v)} aria-label={t("Kategori", "Category")} options={[["", t("Semua kategori", "All categories")], ...cats.map((c) => [c, `${c}${sum.byCategory[c] ? ` (${sum.byCategory[c]})` : ""}`])]} />
        <button type="button" aria-pressed={filter.pinned} onClick={() => set("pinned", !filter.pinned)}
          className={`inline-flex items-center gap-1.5 rounded-pill border px-3 py-2 text-xs ${filter.pinned ? "border-accent bg-accent/10 text-accent" : "border-line text-muted"}`}><Pin size={13} /> {t("Dipin", "Pinned")}</button>
      </div>
      <div className="mb-3 flex flex-wrap gap-1.5" role="group" aria-label={t("Jenis", "Kind")}>
        <button type="button" onClick={() => set("kind", "")} aria-pressed={!filter.kind} className={`rounded-pill px-3 py-1.5 text-xs ${!filter.kind ? "bg-ink text-bg" : "bg-surface-2 text-muted"}`}>{t("Semua", "All")} · {sum.total}</button>
        {KINDS.map((k) => {
          const Icon = KIND_ICON[k];
          return <button key={k} type="button" onClick={() => set("kind", filter.kind === k ? "" : k)} aria-pressed={filter.kind === k} title={w(KIND_HELP, k)}
            className={`inline-flex items-center gap-1.5 rounded-pill px-3 py-1.5 text-xs ${filter.kind === k ? "bg-ink text-bg" : "bg-surface-2 text-muted"}`}><Icon size={13} /> {w(KIND_WORDS, k)} · {sum.byKind[k]}</button>;
        })}
      </div>
      {cloud.length > 0 && (
        <div className="mb-4 flex flex-wrap gap-1.5">
          {filter.tag && <button type="button" onClick={() => set("tag", "")} className="rounded-pill bg-accent px-2.5 py-1 text-[11px] text-accent-ink">#{filter.tag} ✕</button>}
          {cloud.filter((c) => c.tag !== filter.tag).map((c) => <button key={c.tag} type="button" onClick={() => set("tag", c.tag)} className="rounded-pill border border-line px-2.5 py-1 text-[11px] text-muted hover:border-accent hover:text-ink">#{c.tag} <span className="opacity-60">{c.count}</span></button>)}
        </div>
      )}

      {!shown.length ? (
        <Card className="p-8 text-center text-sm text-muted">
          <Brain size={28} className="mx-auto mb-2 opacity-60" />
          {entries.length ? t("Tiada entri sepadan dengan tapisan ini.", "No entry matches these filters.") : t("Otak masih kosong. Tampal sesuatu di atas dan tekan Hantar ke Otak.", "The brain is empty. Paste something above and press Send to the brain.")}
        </Card>
      ) : (
        <div className="grid gap-3 lg:grid-cols-2">
          {shown.map((e) => {
            const Icon = KIND_ICON[e.kind] || ScrollText;
            const isOpen = open === e.id;
            return (
              <Card key={e.id} className={`p-4 ${e.pinned ? "border-accent/50" : ""}`}>
                <div className="flex items-start gap-2">
                  <span className={`mt-0.5 inline-flex items-center gap-1 rounded-pill px-2 py-0.5 text-[11px] ${KIND_TONE[e.kind] || ""}`}><Icon size={12} /> {w(KIND_WORDS, e.kind)}</span>
                  <span className="rounded-pill bg-surface-2 px-2 py-0.5 text-[11px] text-muted">{e.category}</span>
                  {e.confidence != null && Number(e.confidence) < 0.6 && !e.edited && <span className="rounded-pill bg-warn/10 px-2 py-0.5 text-[11px] text-warn" title={t("AI kurang pasti: semak sebelum percaya", "The AI was unsure: check before trusting")}>{Math.round(Number(e.confidence) * 100)}%</span>}
                  {e.edited && <span className="text-[11px] text-muted">{t("disunting", "edited")}</span>}
                  <span className="ml-auto flex gap-0.5">
                    <button type="button" onClick={() => togglePin(e)} className="rounded-pill p-1.5 text-muted hover:bg-surface-2" aria-label={e.pinned ? t("Nyahpin", "Unpin") : t("Pin", "Pin")}>{e.pinned ? <PinOff size={14} /> : <Pin size={14} />}</button>
                    <button type="button" onClick={() => copy(e)} className="rounded-pill p-1.5 text-muted hover:bg-surface-2" aria-label={t("Salin", "Copy")}><Clipboard size={14} /></button>
                    <button type="button" onClick={() => saveFile(e)} className="rounded-pill p-1.5 text-muted hover:bg-surface-2" aria-label={t("Muat turun", "Download")} title={e.kind === "skill" ? "SKILL.md" : ".md"}><Download size={14} /></button>
                    <button type="button" onClick={() => setEditing({ ...e, tags: (e.tags || []).join(", "), when: e.data?.when || "", steps: (e.data?.steps || []).join("\n"), use: e.data?.use || "", items: (e.data?.items || []).join("\n") })} className="rounded-pill p-1.5 text-muted hover:bg-surface-2" aria-label={t("Sunting", "Edit")}><Pencil size={14} /></button>
                    <button type="button" onClick={() => removeEntry(e)} className="rounded-pill p-1.5 text-muted hover:bg-surface-2" aria-label={t("Padam", "Delete")}><Trash2 size={14} /></button>
                  </span>
                </div>
                <button type="button" className="mt-2 flex w-full items-start justify-between gap-2 text-left" onClick={() => setOpen(isOpen ? null : e.id)} aria-expanded={isOpen}>
                  <span><span className="block font-display text-lg leading-snug">{e.title}</span><span className="mt-0.5 block text-sm text-muted">{e.summary}</span></span>
                  <ChevronDown size={16} className={`mt-1.5 shrink-0 text-muted transition ${isOpen ? "rotate-180" : ""}`} />
                </button>
                {isOpen && (
                  <div className="mt-3 border-t border-line/60 pt-3 text-sm">
                    {e.kind === "faq" ? (<><p className="font-medium">{e.question}</p><div className="mt-1"><Markdown text={e.answer || e.body} /></div></>)
                      : e.kind === "prompt" ? (<>{e.data?.use && <p className="mb-1 text-xs text-muted">{t("Untuk", "For")}: {e.data.use}</p>}<pre className="whitespace-pre-wrap rounded-tile bg-surface-2 p-3 font-mono text-[12px] leading-relaxed [overflow-wrap:anywhere]">{e.body}</pre></>)
                        : e.kind === "skill" ? (<>{e.data?.when && <p className="mb-1 text-xs text-muted">{t("Bila guna", "When to use")}: {e.data.when}</p>}<Markdown text={e.body} /></>)
                          : <Markdown text={e.body} />}
                    {e.source_url && <p className="mt-2 text-xs text-muted">{t("Sumber", "Source")}: <a className="text-accent underline decoration-dotted [overflow-wrap:anywhere]" href={e.source_url} target="_blank" rel="noopener noreferrer nofollow">{hostOf(e.source_url) || e.source_url}</a></p>}
                  </div>
                )}
                {(e.tags || []).length > 0 && <div className="mt-2 flex flex-wrap gap-1">{e.tags.map((g) => <button key={g} type="button" onClick={() => set("tag", g)} className="text-[11px] text-muted hover:text-accent">#{g}</button>)}</div>}
              </Card>
            );
          })}
        </div>
      )}

      <EditModal editing={editing} onClose={() => setEditing(null)} onSave={saveEntry} cats={cats} t={t} w={w} />
      <Modal open={catsOpen} onClose={() => setCatsOpen(false)} title={t("Kategori", "Categories")}>
        <p className="mb-2 text-xs text-muted">{t("Satu kategori setiap baris. AI memilih daripada senarai ini; \"lain\" sentiasa ada. Entri lama kekal dengan kategori mereka.", "One category per line. The AI chooses from this list; \"lain\" is always there. Older entries keep their category.")}</p>
        <TextArea rows={10} value={catsText} onChange={(e) => setCatsText(e.target.value)} />
        <div className="mt-3 flex justify-end gap-2"><Button variant="ghost" size="sm" onClick={() => setCatsOpen(false)}>{t("Batal", "Cancel")}</Button><Button size="sm" onClick={saveCats}>{t("Simpan", "Save")}</Button></div>
      </Modal>
    </main>
  );
}

/** One form for a new entry and for an edit; the fields shown follow the kind. */
function EditModal({ editing, onClose, onSave, cats, t, w }) {
  const [form, setForm] = useState(null);
  const [seen, setSeen] = useState(null);
  if (editing !== seen) { setSeen(editing); setForm(editing); }            // a new entry to edit resets the form, an edit of it does not
  if (!editing || !form) return null;
  const f = (k) => (e) => setForm((x) => ({ ...x, [k]: e.target.value }));
  return (
    <Modal open onClose={onClose} title={form.id ? t("Sunting entri", "Edit entry") : t("Entri baharu", "New entry")}>
      <div className="space-y-3">
        <div className="flex flex-wrap gap-2">
          <div><Label>{t("Jenis", "Kind")}</Label><Select value={form.kind} onChange={(v) => setForm((x) => ({ ...x, kind: v }))} options={KINDS.map((k) => [k, w(KIND_WORDS, k)])} /></div>
          <div><Label>{t("Kategori", "Category")}</Label><Select value={form.category} onChange={(v) => setForm((x) => ({ ...x, category: v }))} options={cats.map((c) => [c, c])} /></div>
        </div>
        <div><Label>{t("Tajuk", "Title")}</Label><Input value={form.title} onChange={f("title")} maxLength={120} /></div>
        <div><Label>{t("Ringkasan", "Summary")}</Label><Input value={form.summary} onChange={f("summary")} maxLength={300} /></div>
        {form.kind === "faq" ? (<>
          <div><Label>{t("Soalan", "Question")}</Label><Input value={form.question} onChange={f("question")} /></div>
          <div><Label>{t("Jawapan", "Answer")}</Label><TextArea rows={6} value={form.answer} onChange={f("answer")} /></div>
        </>) : form.kind === "skill" ? (<>
          <div><Label>{t("Bila guna", "When to use")}</Label><Input value={form.when} onChange={f("when")} /></div>
          <div><Label hint={t("satu langkah setiap baris", "one step per line")}>{t("Langkah", "Steps")}</Label><TextArea rows={7} value={form.steps} onChange={f("steps")} /></div>
        </>) : form.kind === "checklist" ? (
          <div><Label hint={t("satu item setiap baris", "one item per line")}>{t("Item", "Items")}</Label><TextArea rows={7} value={form.items} onChange={f("items")} /></div>
        ) : (<>
          {form.kind === "prompt" && <div><Label>{t("Untuk apa", "What it is for")}</Label><Input value={form.use} onChange={f("use")} /></div>}
          <div><Label hint={form.kind === "prompt" ? t("bahagian yang berubah: {{nama}}", "the parts that change: {{name}}") : ""}>{form.kind === "prompt" ? "Prompt" : t("Isi (Markdown)", "Body (Markdown)")}</Label><TextArea rows={8} value={form.body} onChange={f("body")} className="font-mono text-[13px]" /></div>
        </>)}
        <div><Label hint={t("dipisah dengan koma", "comma separated")}>Tag</Label><Input value={form.tags} onChange={f("tags")} /></div>
      </div>
      <div className="mt-4 flex justify-end gap-2"><Button variant="ghost" size="sm" onClick={onClose}>{t("Batal", "Cancel")}</Button><Button size="sm" onClick={() => onSave(form)}>{t("Simpan", "Save")}</Button></div>
    </Modal>
  );
}
