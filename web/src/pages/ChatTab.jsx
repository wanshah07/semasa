import { useEffect, useRef, useState } from "react";
import { IconBulb, IconFileText, IconPencil, IconShieldCheck } from "@tabler/icons-react";
import Ai04 from "@/components/ui/ai-04";
import { addMemory, askAI, checkAI, deleteMemory, listMemory, loadLatestThread } from "../lib/chat";
import { stampMYT } from "../lib/format";
import { useLang } from "../lib/i18n";

/* AI chat: the page and the conversation, with no model behind it yet (Wan, 29 Sep 2026: "add one segment for AI
   chat, later then I will connect with API, just blank structure"). The composer is components/ui/ai-04.tsx; the one
   place a model gets plugged in is lib/chat.js `askAI`. Until then every message is kept on screen and answered with
   a plain note saying nothing is connected, never with a made-up reply. The conversation lives in this tab only and
   is gone on reload: nothing is written to the database. */
const toolLabel = (n) => ({ fetch_url: "baca laman web", search_web: "cari web", query_semasa: "data Semasa", remember: "nota disimpan" }[n] || n);

export default function ChatTab() {
  const { t } = useLang();
  const [messages, setMessages] = useState([]);
  const [busy, setBusy] = useState(false);
  const end = useRef(null);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [messages]);

  const actions = [
    { id: "caption", icon: IconPencil, label: t("Tulis kapsyen", "Write a caption"),
      prompt: t("Tulis kapsyen ws.regulab (BM) tentang: ", "Write a ws.regulab caption (Malay) about: ") },
    { id: "claim", icon: IconShieldCheck, label: t("Semak dakwaan", "Check a claim"),
      prompt: t("Semak dakwaan label ini terhadap garis panduan NPRA: ", "Check this label claim against the NPRA guidelines: ") },
    { id: "notice", icon: IconFileText, label: t("Ringkaskan notis", "Summarise a notice"),
      prompt: t("Ringkaskan notis pengawal selia ini dalam BM mudah: ", "Summarise this regulator notice in plain Malay: ") },
    { id: "idea", icon: IconBulb, label: t("Idea post", "Post ideas"),
      prompt: t("Beri tiga idea post daripada isu semasa ini: ", "Give three post ideas from this current issue: ") },
  ];

  const [threadId, setThreadId] = useState(null);
  const [notes, setNotes] = useState([]);
  const [showNotes, setShowNotes] = useState(false);
  const [draftNote, setDraftNote] = useState("");

  // The conversation lives in the database: open the newest one, and the pinned notes, when the tab opens.
  useEffect(() => {
    let live = true;
    (async () => {
      const { thread, messages: old } = await loadLatestThread();
      if (live && thread) { setThreadId(thread.id); setMessages(old); }
      const n = await listMemory();
      if (live) setNotes(n);
    })();
    return () => { live = false; };
  }, []);

  async function refreshNotes() { setNotes(await listMemory()); }
  async function pin() {
    try { await addMemory(draftNote); setDraftNote(""); await refreshNotes(); }
    catch (e) { setMessages((m) => [...m, { role: "note", text: String(e?.message || e), at: new Date().toISOString() }]); }
  }
  async function unpin(id) { try { await deleteMemory(id); await refreshNotes(); } catch { /* shown on the next refresh */ } }
  function fresh() { setThreadId(null); setMessages([]); }

  async function send(text, { files }) {
    const mine = { role: "user", text, at: new Date().toISOString(), files: files.map((f) => f.name) };
    setMessages((m) => [...m, mine]);
    setBusy(true);
    try {
      const res = await askAI({ text, files, threadId });
      if (res.threadId) setThreadId(res.threadId);
      const reply = res.connected
        ? { role: "assistant", text: res.text, at: new Date().toISOString(), tools: res.tools }
        : { role: "note", text: t("AI belum disambungkan. Mesej anda disimpan di skrin ini sahaja.",
            "The AI is not connected yet. Your message is kept on this screen only."), at: new Date().toISOString() };
      setMessages((m) => [...m, reply]);
      if (res.memorySaved) refreshNotes();
      if (res.notice === "tools_unsupported") setMessages((m) => [...m, { role: "note", at: new Date().toISOString(),
        text: t("Model ini tidak menerima alat (web, pangkalan data); dijawab tanpa alat.", "This model does not accept tools (web, database); answered without them.") }]);
    } catch (e) {
      setMessages((m) => [...m, { role: "note", text: String(e?.message || e), at: new Date().toISOString() }]);
    } finally {
      setBusy(false);
    }
  }

  // "Semak model": is the model listed at Mireld, and does it really read a picture (it is asked the colour of a red square).
  async function checkModel() {
    setBusy(true);
    const r = await checkAI();
    const now = new Date().toISOString();
    let line;
    if (r.error) line = t(`Semakan gagal: ${r.error}`, `Check failed: ${r.error}`);
    else {
      const l = r.listed || {};
      const listed = !l.read ? t("senarai model tidak dapat dibaca", "the model list could not be read")
        : l.exact ? t("ada dalam senarai", "is in the list")
          : l.spelled_as ? t(`dieja "${l.spelled_as}" di sana, tukar MIRELD_MODEL`, `is spelled "${l.spelled_as}" there, set MIRELD_MODEL to that`)
            : t(`tiada dalam senarai (${(l.related || []).join(", ") || "tiada yang serupa"})`, `is not in the list (${(l.related || []).join(", ") || "nothing similar"})`);
      const im = r.image || {};
      const reads = im.reads === true ? t(`boleh baca gambar (jawab: ${im.answer})`, `reads pictures (answered: ${im.answer})`)
        : im.error ? t(`tidak baca gambar: ${im.error}`, `does not read pictures: ${im.error}`)
          : t(`tidak pasti baca gambar (jawab: ${im.answer || "-"})`, `no proof it reads pictures (answered: ${im.answer || "-"})`);
      const tl = r.tools || {};
      const tools = tl.calls === true ? t("boleh guna alat", "can use tools")
        : tl.error ? t(`tiada alat: ${tl.error}`, `no tools: ${tl.error}`) : t("alat tidak pasti", "tools unclear");
      const search = r.search_configured ? t("carian web aktif", "web search on") : t("carian web belum dipasang (BRAVE_API_KEY)", "web search not installed (BRAVE_API_KEY)");
      line = `${r.model}: ${listed}; ${reads}; ${tools}; ${search}.`;
    }
    setMessages((m) => [...m, { role: "note", text: line, at: now }]);
    setBusy(false);
  }

  const empty = messages.length === 0;
  return (
    <main className="mx-auto flex min-h-[calc(100vh-8rem)] max-w-page flex-col px-4 pb-10 pt-10 sm:px-6">
      <p className="text-center text-xs font-semibold uppercase tracking-[0.2em] text-accent">{t("Sembang AI", "AI chat")}</p>
      <button type="button" onClick={checkModel} disabled={busy}
        className="mx-auto mt-2 text-[11px] text-muted underline decoration-dotted underline-offset-2 hover:text-accent disabled:opacity-50">
        {t("Semak model dan pembaca gambar", "Check the model and its image reader")}
      </button>
      <div className="mx-auto mt-1 flex items-center gap-3 text-[11px] text-muted">
        <button type="button" onClick={() => setShowNotes((v) => !v)} className="underline decoration-dotted underline-offset-2 hover:text-accent">
          {t(`Ingatan kekal (${notes.length})`, `Pinned memory (${notes.length})`)}
        </button>
        <button type="button" onClick={fresh} disabled={busy || messages.length === 0} className="underline decoration-dotted underline-offset-2 hover:text-accent disabled:opacity-50">
          {t("Sembang baharu", "New conversation")}
        </button>
      </div>
      {showNotes && (
        <section className="mx-auto mt-3 w-full max-w-2xl rounded-card border border-line bg-surface p-3 text-xs">
          <p className="mb-2 text-muted">{t("Nota ini dihantar kepada AI pada setiap mesej, dalam semua sembang. Anda juga boleh berkata \"ingat bahawa ...\".",
            "These notes go to the AI with every message, in every conversation. You can also say \"remember that ...\".")}</p>
          <ul className="space-y-1">
            {notes.map((n) => (
              <li key={n.id} className="flex items-start justify-between gap-2">
                <span>{n.note}{n.source === "chat" && <span className="ml-1 opacity-60">({t("disimpan oleh sembang", "saved by chat")})</span>}</span>
                <button type="button" onClick={() => unpin(n.id)} className="shrink-0 text-warn underline" aria-label={t("Padam nota", "Delete note")}>{t("padam", "delete")}</button>
              </li>
            ))}
            {notes.length === 0 && <li className="opacity-60">{t("Belum ada nota.", "No notes yet.")}</li>}
          </ul>
          <div className="mt-2 flex gap-2">
            <input value={draftNote} onChange={(e) => setDraftNote(e.target.value)} maxLength={500} placeholder={t("Nota baharu", "New note")}
              className="min-w-0 flex-1 rounded border border-line bg-bg px-2 py-1" />
            <button type="button" onClick={pin} disabled={draftNote.trim().length < 3} className="rounded bg-ink px-3 py-1 text-bg disabled:opacity-50">{t("Simpan", "Save")}</button>
          </div>
        </section>
      )}
      {!empty && (
        <ol className="mx-auto mt-6 w-full max-w-2xl flex-1 space-y-3" aria-live="polite">
          {messages.map((m, i) => (
            <li key={i} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
              <div className={
                m.role === "user" ? "max-w-[85%] whitespace-pre-wrap rounded-card bg-ink px-4 py-2.5 text-sm text-bg"
                  : m.role === "assistant" ? "max-w-[85%] whitespace-pre-wrap rounded-card border border-line bg-surface px-4 py-2.5 text-sm"
                    : "max-w-[85%] rounded-card bg-warn/10 px-4 py-2 text-xs text-warn"}>
                {m.text}
                {m.files?.length > 0 && <span className="mt-1 block text-[11px] opacity-70">📎 {m.files.join(", ")}</span>}
                {m.role === "assistant" && m.tools?.length > 0 && <span className="mt-1 block text-[11px] opacity-70">🔎 {m.tools.map(toolLabel).join(" · ")}</span>}
                <span className="mt-1 block text-[10px] opacity-60">{stampMYT(m.at)}</span>
              </div>
            </li>
          ))}
          <li ref={end} aria-hidden />
        </ol>
      )}
      <div className={empty ? "my-auto pt-10" : "sticky bottom-0 mt-6 bg-bg/90 pb-2 pt-3 backdrop-blur"}>
        <Ai04 onSubmit={send} busy={busy}
          title={empty ? t("Tanya. Semak. Terbit.", "Ask. Check. Publish.") : null}
          subtitle={empty ? t("Draf, semak dakwaan dan ringkas notis, dalam satu sembang.",
            "Draft, check claims and summarise notices in one conversation.") : null}
          placeholder={t("Tanya apa sahaja", "Ask anything")}
          actions={empty ? actions : []}
          labels={{
            attach: t("Lampirkan fail", "Attach files"), url: t("Import dari URL", "Import from URL"),
            paste: t("Tampal dari papan klip", "Paste from clipboard"), template: t("Guna templat", "Use a template"),
            soon: t("akan datang", "soon"), autoComplete: t("Auto-lengkap", "Auto-complete"),
            streaming: t("Strim jawapan", "Streaming"), showHistory: t("Tunjuk sejarah", "Show history"),
            drop: t("Lepaskan fail di sini untuk dilampirkan", "Drop files here to attach them"),
            send: t("Hantar", "Send"), add: t("Tambah lampiran", "Add attachments"),
            adjust: t("Tetapan sembang", "Chat settings"), remove: t("Buang", "Remove"),
          }} />
      </div>
    </main>
  );
}
