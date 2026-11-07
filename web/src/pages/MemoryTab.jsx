import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Check, Loader2, Pencil, Plus, Save, Search, Trash2, X } from "lucide-react";
import { fadeUp } from "../design/motion";
import { useLang } from "../lib/i18n";
import { timeAgo } from "../lib/format";
import { INSTRUCTIONS_KEY, INSTRUCTIONS_MAX, MEMORY_KEY, NOTE_MAX, NOTES_MAX, cleanInstructions, filterNotes, hasRows, instructionsOf,
  instructionsValue, isAuto, memoryOf, noteProblem } from "../lib/aiMemory";
import { addMemory, deleteMemory, listMemory, updateMemory } from "../lib/chat";
import Card from "../components/ui/Card";
import Button from "../components/ui/Button";
import { Input, Segmented, TextArea } from "../components/ui/Field";

/* Memori & Arahan (Wan, 7 Nov 2026: "should I add obsidian or memory base so telegram and AI chat can improve auto and remember",
   with Claude's own settings as the picture). It sits in the Dashboard segment beside Sembang AI, because everything on it changes
   how that chat (and the Telegram bot, which reads the same notes) answers; Tetapan holds the switches of the workers, not this.

   No Obsidian or second store is needed: the memory is the notes table the chat already sends with every call (supabase/025).
   This page is where Wan sees, adds, edits and deletes them, writes the instructions the chat always follows, and holds the two
   switches. The nightly job (backend/semasa/memory_auto.py, memory.yml) adds notes from his own messages while "Generate memory
   from chats" is on; each one is marked auto here. */
export default function MemoryTab({ settings, save, onToast }) {
  const { t } = useLang();
  const saved = instructionsOf(settings);
  const sw = memoryOf(settings);
  const ready = hasRows(settings);
  const [text, setText] = useState(saved.text);
  const [busy, setBusy] = useState("");
  const [notes, setNotes] = useState(null);       // null while the first read is on its way
  const [noteErr, setNoteErr] = useState("");
  const [draft, setDraft] = useState("");
  const [edit, setEdit] = useState(null);         // { id, note } while a note is being changed
  const [sure, setSure] = useState("");
  const [q, setQ] = useState("");
  const [who, setWho] = useState("all");

  useEffect(() => { setText(saved.text); }, [saved.text]);
  useEffect(() => { refresh(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function refresh() {
    try { setNotes(await listMemory()); setNoteErr(""); } catch (e) { setNoteErr(String(e?.message || e)); setNotes([]); }
  }

  const migrate = t("Jalankan supabase/070_ai_memory.sql sekali dahulu.", "Run supabase/070_ai_memory.sql once first.");
  const why = (p) => ({
    short: t("Nota mesti sekurang-kurangnya 3 aksara.", "A note needs at least 3 characters."),
    long: t(`Nota paling panjang ${NOTE_MAX} aksara.`, `A note is at most ${NOTE_MAX} characters.`),
    same: t("Nota yang sama sudah ada.", "The same note is already there."),
    full: t(`Sudah ada ${NOTES_MAX} nota: padam yang lama dahulu.`, `There are already ${NOTES_MAX} notes: delete an old one first.`),
  }[p]);

  async function saveInstructions() {
    setBusy("ins");
    try {
      await save(INSTRUCTIONS_KEY, instructionsValue(text));
      onToast(t("Arahan disimpan. Sembang AI mengikutnya mulai mesej seterusnya.", "Instructions saved. The AI chat follows them from the next message."), "ok");
    } catch (e) {
      onToast(/not found/.test(String(e?.message)) ? migrate : String(e?.message || e), "danger");
    }
    setBusy("");
  }

  async function flip(key) {
    setBusy(key);
    try { await save(MEMORY_KEY, { ...sw, [key]: !sw[key] }); }
    catch (e) { onToast(/not found/.test(String(e?.message)) ? migrate : String(e?.message || e), "danger"); }
    setBusy("");
  }

  async function add() {
    const p = noteProblem(draft, notes || []);
    if (p) return onToast(why(p), "warn");
    setBusy("add");
    try { await addMemory(draft); setDraft(""); await refresh(); onToast(t("Nota disimpan.", "Note saved."), "ok"); }
    catch (e) { onToast(String(e?.message || e), "danger"); }
    setBusy("");
  }

  async function saveEdit() {
    const p = noteProblem(edit.note, notes || [], edit.id);
    if (p) return onToast(why(p), "warn");
    setBusy(`edit-${edit.id}`);
    try { await updateMemory(edit.id, edit.note); setEdit(null); await refresh(); }
    catch (e) { onToast(String(e?.message || e), "danger"); }
    setBusy("");
  }

  async function remove(id) {
    if (sure !== id) { setSure(id); setTimeout(() => setSure((s) => (s === id ? "" : s)), 6000); return; }
    setSure(""); setBusy(`del-${id}`);
    try { await deleteMemory(id); await refresh(); }
    catch (e) { onToast(String(e?.message || e), "danger"); }
    setBusy("");
  }

  const shown = useMemo(() => filterNotes(notes || [], q, who), [notes, q, who]);
  const autoCount = (notes || []).filter(isAuto).length;
  const changed = cleanInstructions(text) !== cleanInstructions(saved.text);

  return (
    <main className="mx-auto max-w-page px-4 pb-20 pt-10 sm:px-6" data-memory>
      <motion.div variants={fadeUp} initial="hidden" animate="show" className="mb-6">
        <h1 className="font-display text-3xl">{t("Memori & Arahan", "Memory & instructions")}</h1>
        <p className="mt-1 max-w-2xl text-sm text-muted">{t(
          "Apa yang Sembang AI dan bot Telegram sentiasa tahu tentang anda, dan cara anda mahu mereka menjawab. Peraturan Semasa (fakta bersumber, BM Malaysia, peraturan post) sentiasa didahulukan.",
          "What the AI chat and the Telegram bot always know about you, and how you want them to answer. Semasa's own rules (sourced facts, Malaysian Malay, the post rules) always come first.")}</p>
      </motion.div>
      {!ready && <p className="mb-4 rounded-tile bg-warn/10 p-3 text-sm text-warn" data-memory-migrate>{migrate} {t("Sehingga itu, kedua-dua suis dikira hidup dan arahan tidak dapat disimpan.", "Until then both switches count as on and the instructions cannot be saved.")}</p>}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="space-y-3 p-4" data-memory-instructions>
          <div>
            <h2 className="text-base font-semibold">{t("Arahan", "Instructions")}</h2>
            <p className="text-xs text-muted">{t("Diikut dalam setiap jawapan Sembang AI, selepas peraturan Semasa: nada, bentuk jawapan, perkara yang sentiasa perlu disebut. Arahan yang bercanggah dengan peraturan tidak diikut.",
              "Followed in every AI chat answer, after Semasa's rules: tone, the shape of an answer, what to always mention. An instruction that clashes with a rule is not followed.")}</p>
          </div>
          <TextArea rows={10} value={text} maxLength={INSTRUCTIONS_MAX + 200} onChange={(e) => setText(e.target.value)} data-memory-instructions-text
            placeholder={t("Contoh: Jawab dalam BM dahulu, Inggeris di bawah. Beri jadual ringkas untuk perbandingan. Sebut instrumen dan entri tepat.",
              "For example: answer in Malay first, English below. Give a short table for comparisons. Name the exact instrument and entry.")} />
          <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-muted">
            <span className={cleanInstructions(text).length >= INSTRUCTIONS_MAX ? "text-warn" : ""}>{cleanInstructions(text).length}/{INSTRUCTIONS_MAX}</span>
            {saved.updated_at && <span>{t("Disimpan", "Saved")} {timeAgo(saved.updated_at)}</span>}
            <Button size="sm" onClick={saveInstructions} disabled={!changed || !!busy || !ready} data-memory-instructions-save>
              {busy === "ins" ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />} {t("Simpan arahan", "Save instructions")}
            </Button>
          </div>
        </Card>

        <Card className="space-y-4 p-4" data-memory-switches>
          <h2 className="text-base font-semibold">{t("Memori", "Memory")}</h2>
          <Toggle on={sw.search_chats} busy={busy === "search_chats"} disabled={!ready} onFlip={() => flip("search_chats")} data="search"
            title={t("Cari dan rujuk sembang", "Search and reference chats")}
            hint={t("Sembang AI boleh mencari perbualan anda yang lain (termasuk Telegram) apabila anda merujuk sesuatu yang pernah dibincangkan. Dimatikan, ia hanya nampak perbualan semasa.",
              "The AI chat may search your other conversations (Telegram included) when you refer to something discussed before. Off, it sees only the conversation it is in.")} />
          <Toggle on={sw.auto_memory} busy={busy === "auto_memory"} disabled={!ready} onFlip={() => flip("auto_memory")} data="auto"
            title={t("Jana memori daripada sembang", "Generate memory from chats")}
            hint={t("Setiap malam (00:35), Semasa membaca mesej anda sendiri hari itu dan menyimpan paling banyak 5 fakta atau pilihan yang kekal sebagai nota auto. Tiada kata laluan, kunci atau butiran orang lain. Semak dan padam di bawah.",
              "Every night (00:35), Semasa reads your own messages of the day and keeps at most 5 lasting facts or preferences as auto notes. Never a password, a key or someone else's details. Check and delete them below.")} />
        </Card>
      </div>

      <Card className="mt-4 space-y-3 p-4" data-memory-notes>
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <div>
            <h2 className="text-base font-semibold">{t("Memori anda", "Your memory")} <span className="text-sm font-normal text-muted">({(notes || []).length}/{NOTES_MAX})</span></h2>
            <p className="text-xs text-muted">{t("Setiap nota dihantar kepada AI pada setiap mesej, dalam semua perbualan. Anda juga boleh berkata \"ingat bahawa ...\" dalam sembang.",
              "Every note goes to the AI with every message, in every conversation. You can also say \"remember that ...\" in the chat.")}</p>
          </div>
          <Segmented value={who} onChange={setWho} options={[["all", t("Semua", "All")], ["user", t("Anda", "Yours")], ["auto", `Auto (${autoCount})`]]} />
        </div>
        <div className="flex flex-col gap-2 sm:flex-row">
          <label className="relative block flex-1">
            <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" aria-hidden />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("Cari nota", "Search notes")} className="pl-8" aria-label={t("Cari nota", "Search notes")} />
          </label>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row" data-memory-add>
          <Input value={draft} onChange={(e) => setDraft(e.target.value)} maxLength={NOTE_MAX} onKeyDown={(e) => { if (e.key === "Enter") add(); }}
            placeholder={t("Nota baharu, contoh: Wan mahu rujukan NPRA ditulis penuh.", "A new note, e.g. Wan wants NPRA references written out in full.")} />
          <Button size="sm" onClick={add} disabled={draft.trim().length < 3 || !!busy} className="shrink-0 justify-center">
            {busy === "add" ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />} {t("Tambah", "Add")}
          </Button>
        </div>
        {noteErr && <p className="rounded-tile bg-danger/10 p-3 text-sm text-danger">{noteErr}</p>}
        {notes == null && <p className="flex items-center gap-2 text-sm text-muted"><Loader2 size={14} className="animate-spin" /> {t("Membaca…", "Reading…")}</p>}
        {notes != null && shown.length === 0 && <p className="text-sm text-muted">{(notes || []).length ? t("Tiada nota sepadan.", "No note matches.") : t("Belum ada nota.", "No notes yet.")}</p>}
        <ul className="divide-y divide-line/60">
          {shown.map((r) => (
            <li key={r.id} className="flex flex-col gap-2 py-2 sm:flex-row sm:items-start" data-memory-note>
              {edit?.id === r.id ? (
                <TextArea rows={2} value={edit.note} maxLength={NOTE_MAX} onChange={(e) => setEdit({ ...edit, note: e.target.value })} className="flex-1" autoFocus />
              ) : (
                <p className="min-w-0 flex-1 text-sm [overflow-wrap:anywhere]">{r.note}</p>
              )}
              <div className="flex shrink-0 items-center gap-2 text-[11px] text-muted">
                <span className={`rounded-pill px-2 py-0.5 ${isAuto(r) ? "bg-accent/15 text-accent" : "bg-surface-2"}`} data-memory-source>
                  {isAuto(r) ? "auto" : t("anda", "you")}
                </span>
                {r.created_at && <span>{timeAgo(r.created_at)}</span>}
                {edit?.id === r.id ? (
                  <>
                    <button type="button" onClick={saveEdit} disabled={!!busy} className="inline-flex items-center gap-0.5 text-ok underline" aria-label={t("Simpan nota", "Save note")}><Check size={13} /> {t("simpan", "save")}</button>
                    <button type="button" onClick={() => setEdit(null)} className="inline-flex items-center gap-0.5 underline" aria-label={t("Batal", "Cancel")}><X size={13} /></button>
                  </>
                ) : (
                  <button type="button" onClick={() => setEdit({ id: r.id, note: r.note })} disabled={!!busy} className="inline-flex items-center gap-0.5 underline" aria-label={t("Ubah nota", "Edit note")}><Pencil size={12} /> {t("ubah", "edit")}</button>
                )}
                <button type="button" onClick={() => remove(r.id)} disabled={busy === `del-${r.id}`} className="inline-flex items-center gap-0.5 text-warn underline" aria-label={t("Padam nota", "Delete note")}>
                  <Trash2 size={12} /> {sure === r.id ? t("pasti?", "sure?") : t("padam", "delete")}
                </button>
              </div>
            </li>
          ))}
        </ul>
      </Card>
    </main>
  );
}

function Toggle({ on, busy, disabled, onFlip, title, hint, data }) {
  return (
    <label className={`flex items-start justify-between gap-4 ${disabled ? "opacity-60" : "cursor-pointer"}`} data-memory-toggle={data}>
      <span>
        <span className="block text-sm font-medium">{title}</span>
        <span className="block text-xs text-muted">{hint}</span>
      </span>
      <span className="flex shrink-0 items-center gap-2 pt-0.5">
        {busy && <Loader2 size={14} className="animate-spin text-muted" />}
        <input type="checkbox" role="switch" checked={on} disabled={disabled || busy} onChange={onFlip} className="h-4 w-4" />
      </span>
    </label>
  );
}
