import { useEffect, useRef, useState } from "react";
import { IconBulb, IconCheck, IconCopy, IconFileText, IconHistory, IconPencil, IconPlayerStop, IconRefresh, IconShieldCheck, IconTrash } from "@tabler/icons-react";
import Ai04 from "@/components/ui/ai-04";
import Markdown from "../components/Markdown";
import { addMemory, askAI, checkAI, deleteMemory, deleteThread, listMemory, listModels, listThreads, loadLatestThread, loadMessages, renameThread,
  saveModel, saveStream, savedModel, savedStream } from "../lib/chat";
import { parseMarkdown, plainText } from "../lib/markdown";
import { stampMYT, timeAgo } from "../lib/format";
import { useLang } from "../lib/i18n";

/* AI chat (Wan, 29 Sep 2026: "add one segment for AI chat"; 30 Sep: connected to Mireld through supabase/functions/semasa-chat;
   1 Oct: memory, tools, a model picker, and "make sure all features almost similar with claude"). The composer is
   components/ui/ai-04.tsx; the one place a model gets plugged in is lib/chat.js `askAI`.

   What "like Claude" means here, and what each part is for:
   - the answer STREAMS into its bubble as the model writes it, with a Stop button (an AbortController on the fetch);
     the composer's Streaming switch turns it off for a one-piece answer;
   - answers are drawn as Markdown (headings, lists, tables, code) through components/Markdown.jsx, never as HTML;
   - every answer can be copied as plain text, and the last one answered again (the function drops it and re-answers the question);
   - every conversation is kept (supabase/025_chat_memory.sql) and listed in a history panel: open, rename, delete;
   - attachments: pictures, PDF (text pages; scanned pages as pictures), Word, Excel, CSV and text, read in the browser by the
     FAQ bar's readers, and a tool line under each answer says what the model read or looked up. */
const toolLabel = (n, t) => ({ fetch_url: t("baca laman web", "read a web page"), search_web: t("cari web", "web search"),
  query_semasa: t("data Semasa", "Semasa data"), remember: t("nota disimpan", "note saved") }[n] || n);

export default function ChatTab() {
  const { t } = useLang();
  const [messages, setMessages] = useState([]);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");               // what the model is doing right now (a tool, reading a file)
  const abort = useRef(null);
  const end = useRef(null);
  const stick = useRef(true);                              // follow the newest words unless the person scrolled up
  useEffect(() => { if (stick.current) end.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [messages]);

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
  const [threads, setThreads] = useState([]);
  const [showHistory, setShowHistory] = useState(false);
  const [renaming, setRenaming] = useState(null);         // { id, title } while a conversation is being renamed
  const [streaming, setStreaming] = useState(savedStream);
  // the model: "" is Auto, which is the function's default (the recommended one); a name is this browser's own choice
  const [models, setModels] = useState(null);                // { models, recommended, default } | null (picker hidden)
  const [model, setModel] = useState(savedModel);
  useEffect(() => {
    let live = true;
    listModels().then((m) => {
      if (!live || !m) return;
      setModels(m);
      // a model chosen earlier that Mireld no longer lists would only be refused: go back to Auto and say so
      const kept = savedModel();
      const gwn = m.gateway || "Mireld";
      if (kept && m.listed && !m.models.some((x) => x.id === kept)) {
        saveModel(""); setModel("");
        note(t(`Model pilihan anda (${kept}) tiada lagi dalam senarai ${gwn}; guna Auto (${m.default}).`, `Your chosen model (${kept}) is no longer in ${gwn}'s list; using Auto (${m.default}).`));
      }
    });
    return () => { live = false; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const chooseModel = (id) => { setModel(id); saveModel(id); };
  const shownModel = model || models?.default || "";
  const modelNote = models?.models.find((x) => x.id === shownModel);
  const [notes, setNotes] = useState([]);
  const [showNotes, setShowNotes] = useState(false);
  const [draftNote, setDraftNote] = useState("");
  const note = (text) => setMessages((m) => [...m, { role: "note", text, at: new Date().toISOString() }]);

  // The conversation lives in the database: open the newest one, and the pinned notes, when the tab opens.
  useEffect(() => {
    let live = true;
    (async () => {
      const { thread, messages: old } = await loadLatestThread();
      if (live && thread) { setThreadId(thread.id); setMessages(old); }
      const [n, th] = await Promise.all([listMemory(), listThreads()]);
      if (live) { setNotes(n); setThreads(th); }
    })();
    return () => { live = false; };
  }, []);

  async function refreshNotes() { setNotes(await listMemory()); }
  async function refreshThreads() { setThreads(await listThreads()); }
  async function pin() {
    try { await addMemory(draftNote); setDraftNote(""); await refreshNotes(); }
    catch (e) { note(String(e?.message || e)); }
  }
  async function unpin(id) { try { await deleteMemory(id); await refreshNotes(); } catch { /* shown on the next refresh */ } }
  function fresh() { if (busy) return; setThreadId(null); setMessages([]); }
  async function openThread(id) {
    if (busy || id === threadId) return;
    setThreadId(id);
    setMessages(await loadMessages(id));
    stick.current = true;
  }
  async function rename() {
    if (!renaming) return;
    try { await renameThread(renaming.id, renaming.title); setRenaming(null); await refreshThreads(); }
    catch (e) { note(String(e?.message || e)); }
  }
  async function remove(id) {
    if (!window.confirm(t("Padam perbualan ini dan semua mesejnya?", "Delete this conversation and all its messages?"))) return;
    try {
      await deleteThread(id);
      if (id === threadId) { setThreadId(null); setMessages([]); }
      await refreshThreads();
    } catch (e) { note(String(e?.message || e)); }
  }

  // the newest bubble while it fills: every piece of text lands in it, the final answer replaces it
  const grow = (text) => setMessages((m) => {
    const c = m.slice();
    const last = c[c.length - 1];
    if (last?.streaming) c[c.length - 1] = { ...last, text: last.text + text };
    return c;
  });
  const settle = (patch) => setMessages((m) => {
    const c = m.slice();
    const last = c[c.length - 1];
    if (last?.streaming) c[c.length - 1] = { ...last, streaming: false, ...patch };
    return c;
  });

  async function run({ text = "", files = [], regenerate = false }) {
    const now = new Date().toISOString();
    setMessages((m) => [...m, { role: "assistant", text: "", at: now, streaming: true }]);
    setBusy(true); setStatus("");
    stick.current = true;
    abort.current = new AbortController();
    try {
      const res = await askAI({ text, files, threadId, model, regenerate, signal: abort.current.signal,
        onProgress: (p) => setStatus(t(`Membaca lampiran ${p}`, `Reading attachment ${p}`)),
        onDelta: streaming ? (piece) => { setStatus(""); grow(piece); } : null,
        onStatus: (ev) => setStatus(`${toolLabel(ev.tool, t)}${ev.detail ? `: ${ev.detail}` : ""}`) });
      if (!res.connected) {
        settle({ role: "note", text: t("AI belum disambungkan. Mesej anda disimpan di skrin ini sahaja.", "The AI is not connected yet. Your message is kept on this screen only.") });
        return;
      }
      if (res.threadId) setThreadId(res.threadId);
      settle({ text: res.text, tools: res.tools, model: res.model, at: new Date().toISOString() });
      if (res.memorySaved) refreshNotes();
      if (res.modelChanged) note(t(`Model ${res.modelChanged.asked} tidak ada di ${models?.gateway || "Mireld"}; dijawab oleh ${res.modelChanged.used}.`, `Model ${res.modelChanged.asked} is not at ${models?.gateway || "Mireld"}; answered by ${res.modelChanged.used}.`));
      if (res.notice === "tools_unsupported") note(t("Model ini tidak menerima alat (web, pangkalan data); dijawab tanpa alat.", "This model does not accept tools (web, database); answered without them."));
      refreshThreads();
    } catch (e) {
      const msg = String(e?.message || e);
      if (/Dihentikan/.test(msg)) settle({ stopped: true, at: new Date().toISOString() });    // what arrived stays on screen
      else settle({ role: "note", text: msg });
    } finally {
      setBusy(false); setStatus(""); abort.current = null;
    }
  }

  async function send(text, { files, settings }) {
    if (settings && settings.streaming !== streaming) { setStreaming(settings.streaming); saveStream(settings.streaming); }
    setMessages((m) => [...m, { role: "user", text, at: new Date().toISOString(), files: files.map((f) => f.name) }]);
    await run({ text, files });
  }
  async function again() {
    if (busy || !threadId) return;
    setMessages((m) => (m[m.length - 1]?.role === "assistant" ? m.slice(0, -1) : m));
    await run({ regenerate: true });
  }
  function stop() { abort.current?.abort(); }

  // "Semak model": is the model listed at Mireld, and does it really read a picture (it is asked the colour of a red square).
  async function checkModel() {
    setBusy(true);
    const r = await checkAI(model);
    let line;
    if (r.error) line = t(`Semakan gagal: ${r.error}`, `Check failed: ${r.error}`);
    else {
      const l = r.listed || {};
      const listed = !l.read ? t("senarai model tidak dapat dibaca", "the model list could not be read")
        : l.exact ? t("ada dalam senarai", "is in the list")
          : l.spelled_as ? t(`dieja "${l.spelled_as}" di sana, tetapkan rahsia model (AI_MODEL atau MIRELD_MODEL) kepada itu`, `is spelled "${l.spelled_as}" there, set the model secret (AI_MODEL or MIRELD_MODEL) to that`)
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
    note(line);
    setBusy(false);
  }

  const empty = messages.length === 0;
  const lastAssistant = [...messages].reverse().findIndex((m) => m.role === "assistant");
  const lastAssistantIndex = lastAssistant < 0 ? -1 : messages.length - 1 - lastAssistant;
  const panel = showHistory && (
    <aside className="w-full shrink-0 rounded-card border border-line bg-surface p-3 text-xs md:w-64" aria-label={t("Sejarah sembang", "Chat history")}>
      <div className="mb-2 flex items-center justify-between">
        <span className="font-semibold">{t("Perbualan", "Conversations")} ({threads.length})</span>
        <button type="button" onClick={fresh} disabled={busy} className="text-accent underline decoration-dotted underline-offset-2 disabled:opacity-50">{t("+ Baharu", "+ New")}</button>
      </div>
      <ul className="max-h-[60vh] space-y-1 overflow-y-auto">
        {threads.map((th) => (
          <li key={th.id} className={`group rounded-tile px-2 py-1.5 ${th.id === threadId ? "bg-accent/10" : "hover:bg-surface-2"}`}>
            {renaming?.id === th.id ? (
              <form onSubmit={(e) => { e.preventDefault(); rename(); }} className="flex gap-1">
                <input autoFocus value={renaming.title} onChange={(e) => setRenaming({ ...renaming, title: e.target.value })} maxLength={80}
                  onKeyDown={(e) => { if (e.key === "Escape") setRenaming(null); }} className="min-w-0 flex-1 rounded border border-line bg-bg px-1.5 py-0.5" aria-label={t("Nama perbualan", "Conversation name")} />
                <button type="submit" className="text-accent" aria-label={t("Simpan nama", "Save name")}><IconCheck size={14} /></button>
              </form>
            ) : (
              <div className="flex items-start gap-1">
                <button type="button" onClick={() => openThread(th.id)} className="min-w-0 flex-1 text-left">
                  <span className="block truncate">{th.title || t("(tiada tajuk)", "(no title)")}</span>
                  <span className="block text-[10px] text-muted">{timeAgo(th.updated_at)}</span>
                </button>
                <button type="button" onClick={() => setRenaming({ id: th.id, title: th.title || "" })} className="text-muted opacity-0 hover:text-accent group-hover:opacity-100 focus:opacity-100" aria-label={t("Namakan semula", "Rename")}><IconPencil size={13} /></button>
                <button type="button" onClick={() => remove(th.id)} className="text-muted opacity-0 hover:text-danger group-hover:opacity-100 focus:opacity-100" aria-label={t("Padam perbualan", "Delete conversation")}><IconTrash size={13} /></button>
              </div>
            )}
          </li>
        ))}
        {threads.length === 0 && <li className="text-muted">{t("Belum ada perbualan.", "No conversations yet.")}</li>}
      </ul>
    </aside>
  );

  return (
    <main className="mx-auto flex min-h-[calc(100vh-8rem)] max-w-page flex-col px-4 pb-10 pt-10 sm:px-6">
      <p className="text-center text-xs font-semibold uppercase tracking-[0.2em] text-accent">{t("Sembang AI", "AI chat")}</p>
      <button type="button" onClick={checkModel} disabled={busy}
        className="mx-auto mt-2 text-[11px] text-muted underline decoration-dotted underline-offset-2 hover:text-accent disabled:opacity-50">
        {t("Uji model terpilih: baca gambar dan guna alat", "Test the selected model: pictures and tools")}
      </button>
      {models && models.models.length > 0 && (
        <div className="mx-auto mt-2 flex max-w-2xl flex-wrap items-center justify-center gap-x-3 gap-y-1 text-[11px] text-muted">
          <label className="flex items-center gap-1.5">
            <span>{t("Model AI", "AI model")}</span>
            <select value={model} onChange={(e) => chooseModel(e.target.value)} disabled={busy} aria-label={t("Pilih model AI", "Choose the AI model")}
              className="max-w-[16rem] rounded-pill border border-line bg-surface px-2.5 py-1 text-[11px] text-ink outline-none focus:border-accent">
              <option value="">{t("Auto", "Auto")} · {models.default}</option>
              {models.models.map((m) => (
                <option key={m.id} value={m.id}>{m.id}{m.recommended ? ` ★ ${t("disyorkan", "recommended")}` : ""}</option>
              ))}
            </select>
          </label>
          {modelNote && (
            <span className="max-w-md text-center">
              {shownModel === models.recommended ? `★ ${t("Disyorkan", "Recommended")}: ` : ""}{t(modelNote.note_bm, modelNote.note_en)}
            </span>
          )}
        </div>
      )}
      <div className="mx-auto mt-1 flex items-center gap-3 text-[11px] text-muted">
        <button type="button" onClick={() => setShowHistory((v) => !v)} className="inline-flex items-center gap-1 underline decoration-dotted underline-offset-2 hover:text-accent">
          <IconHistory size={12} /> {t(`Sejarah (${threads.length})`, `History (${threads.length})`)}
        </button>
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
      <div className={`mx-auto mt-4 flex w-full gap-4 ${showHistory ? "max-w-5xl" : "max-w-2xl"} flex-1 flex-col md:flex-row`}>
        {panel}
        <div className="flex min-w-0 flex-1 flex-col">
          {!empty && (
            <ol className="w-full flex-1 space-y-3" aria-live="polite" onWheel={() => { const el = end.current; if (!el) return; const r = el.getBoundingClientRect(); stick.current = r.top < window.innerHeight + 80; }}>
              {messages.map((m, i) => (
                <li key={m.id ? `db${m.id}` : `new${i}`} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
                  <div className={
                    m.role === "user" ? "max-w-[85%] whitespace-pre-wrap rounded-card bg-ink px-4 py-2.5 text-sm text-bg [overflow-wrap:anywhere]"
                      : m.role === "assistant" ? "max-w-[92%] rounded-card border border-line bg-surface px-4 py-2.5 text-sm"
                        : "max-w-[85%] rounded-card bg-warn/10 px-4 py-2 text-xs text-warn [overflow-wrap:anywhere]"}>
                    {m.role === "assistant" ? <AnswerBody m={m} status={status} t={t} /> : m.text}
                    {m.files?.length > 0 && <span className="mt-1 block text-[11px] opacity-70">📎 {m.files.join(", ")}</span>}
                    {m.role === "assistant" && !m.streaming && (
                      <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] opacity-70">
                        {m.tools?.length > 0 && <span>🔎 {m.tools.map((x) => toolLabel(x, t)).join(" · ")}</span>}
                        {m.model && <span>{m.model}</span>}
                        {m.stopped && <span className="text-warn">{t("dihentikan", "stopped")}</span>}
                        <span>{stampMYT(m.at)}</span>
                        <span className="ml-auto flex items-center gap-2">
                          <CopyButton text={m.text} t={t} />
                          {i === lastAssistantIndex && threadId && (
                            <button type="button" onClick={again} disabled={busy} className="inline-flex items-center gap-1 hover:text-accent disabled:opacity-50" title={t("Jawab semula", "Answer again")}>
                              <IconRefresh size={12} /> {t("Jawab semula", "Again")}</button>
                          )}
                        </span>
                      </div>
                    )}
                    {m.role !== "assistant" && <span className="mt-1 block text-[10px] opacity-60">{stampMYT(m.at)}</span>}
                  </div>
                </li>
              ))}
              <li ref={end} aria-hidden />
            </ol>
          )}
          <div className={empty ? "my-auto pt-10" : "sticky bottom-0 mt-6 bg-bg/90 pb-2 pt-3 backdrop-blur"}>
            {busy && (
              <div className="mx-auto mb-2 flex max-w-2xl items-center justify-between gap-3 text-[11px] text-muted">
                <span className="truncate">{status || t("Sedang menjawab…", "Answering…")}</span>
                <button type="button" onClick={stop} className="inline-flex shrink-0 items-center gap-1 rounded-pill border border-line px-2.5 py-1 hover:border-accent hover:text-accent">
                  <IconPlayerStop size={12} /> {t("Berhenti", "Stop")}</button>
              </div>
            )}
            <Ai04 onSubmit={send} busy={busy}
              defaultSettings={{ streaming }} onSettingsChange={(s) => { if (s.streaming !== streaming) { setStreaming(s.streaming); saveStream(s.streaming); } if (s.showHistory !== showHistory) setShowHistory(s.showHistory); }}
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
                urlPrompt: t("Tampal alamat laman untuk dibaca", "Paste the address of a page to read"),
              }} />
            <p className="mx-auto mt-1 max-w-2xl text-center text-[10px] text-muted">{t("Lampiran: gambar, PDF, Word, Excel, CSV, teks. AI boleh baca laman web awam dan data Semasa; sebut sumbernya.",
              "Attachments: pictures, PDF, Word, Excel, CSV, text. The AI can read public web pages and Semasa data; it names its sources.")}</p>
          </div>
        </div>
      </div>
    </main>
  );
}

/** An answer: Markdown once it is complete; while it streams, the raw text with a cursor, or the status line when nothing has arrived. */
function AnswerBody({ m, status, t }) {
  if (!m.streaming) return <Markdown text={m.text} />;
  if (!m.text) return <span className="inline-flex items-center gap-2 text-muted"><span className="h-2 w-2 animate-pulse rounded-full bg-accent" /> {status || t("Berfikir…", "Thinking…")}</span>;
  return <div className="whitespace-pre-wrap [overflow-wrap:anywhere]">{m.text}<span className="ml-0.5 inline-block h-[1em] w-[2px] animate-pulse bg-accent align-text-bottom" /></div>;
}

function CopyButton({ text, t }) {
  const [done, setDone] = useState(false);
  async function copy() {
    try { await navigator.clipboard.writeText(plainText(parseMarkdown(text))); setDone(true); setTimeout(() => setDone(false), 1500); }
    catch { /* the browser said no: select and copy by hand */ }
  }
  return (
    <button type="button" onClick={copy} className="inline-flex items-center gap-1 hover:text-accent" title={t("Salin jawapan", "Copy the answer")}>
      {done ? <IconCheck size={12} /> : <IconCopy size={12} />} {done ? t("Disalin", "Copied") : t("Salin", "Copy")}</button>
  );
}
