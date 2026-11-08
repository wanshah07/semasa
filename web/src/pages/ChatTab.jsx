import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { IconArrowDown, IconBulb, IconCheck, IconChevronDown, IconCopy, IconFileText, IconHistory, IconMessagePlus, IconNotes, IconPencil, IconPlayerStop, IconRefresh, IconShieldCheck, IconTrash } from "@tabler/icons-react";
import Ai04 from "@/components/ui/ai-04";
import Sheet from "@/components/ui/Sheet";
import Markdown from "../components/Markdown";
import ImageLightbox, { useLightbox } from "../components/ImageLightbox";
import { addMemory, askAI, checkAI, deleteMemory, deleteThread, listMemory, listModels, listThreads, loadLatestThread, loadMessages, renameThread,
  saveModel, saveStream, savedModel, savedStream, splitChoice } from "../lib/chat";
import { parseMarkdown, plainText } from "../lib/markdown";
import { stampMYT, timeAgo } from "../lib/format";
import { useLang } from "../lib/i18n";
import { useIsPhone, useKeyboardFlag, useVisualViewport } from "../lib/viewport";

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
     FAQ bar's readers, and a tool line under each answer says what the model read or looked up.

   The phone layout (7 Nov 2026; Wan reads this as an iPhone home-screen app). The page used to be one long document with the
   composer `sticky` at its foot: the newest answer slid in UNDER the box, the keyboard pushed the box off the screen, and the
   history panel opened inline and shoved the conversation down. Now the chat is one column sized from the visual viewport
   (lib/viewport.js): a compact top bar (thread, model, history, memory, new), the messages scrolling in their OWN box, and the
   composer at the foot of the column, above the keyboard and the tab bar. The list follows new words only while the reader is
   already at the bottom; otherwise a "newest" pill offers the jump. The model picker, history and memory open as sheets on a
   phone (full screen with Back, or a bottom sheet) and as cards from sm up; history stays beside the conversation from md up. */
const toolLabel = (n, t) => ({ fetch_url: t("baca laman web", "read a web page"), search_web: t("cari web", "web search"),
  query_semasa: t("data Semasa", "Semasa data"), remember: t("nota disimpan", "note saved"),
  switch: t("Auto menukar robot", "Auto switched robot") }[n] || n);

// a robot's live state in words, from the 6-hourly probe (or the ChatGPT login's own check)
const stateWord = (r, t) => ({ ok: t("sihat", "healthy"), down: t("bermasalah", "down"), stale: t("belum disemak 13 jam", "not checked in 13 h"),
  unknown: t("belum diuji", "not tested") }[r.state] || r.state);
const speedOf = (ms) => (ms == null ? "" : ms >= 1000 ? ` · ${(ms / 1000).toFixed(1)} s` : ` · ${ms} ms`);
const STATE_DOT = { ok: "bg-ok", down: "bg-danger", stale: "bg-warn", unknown: "bg-line" };
const StateDot = ({ r }) => <span aria-hidden className={`inline-block h-2 w-2 shrink-0 rounded-full ${!r || !r.enabled ? "bg-line" : STATE_DOT[r.state] || "bg-line"}`} />;
const NEAR_BOTTOM_PX = 96;                                 // this close to the end counts as "reading the newest"

export default function ChatTab() {
  const { t } = useLang();
  const phone = useIsPhone();
  const [messages, setMessages] = useState([]);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");               // what the model is doing right now (a tool, reading a file)
  const abort = useRef(null);

  // ---- the column: sized from the visual viewport so the composer stays above the keyboard and the bottom bar
  const vv = useVisualViewport();
  const keyboard = phone && vv.keyboard;
  useKeyboardFlag(keyboard);
  const root = useRef(null);
  const [height, setHeight] = useState(null);
  useLayoutEffect(() => {
    const measure = () => {
      const el = root.current;
      if (!el) return;
      const top = el.getBoundingClientRect().top;
      const bar = document.querySelector("[data-mobile-tabbar]");
      const barH = bar && !keyboard ? bar.getBoundingClientRect().height : 0;
      const h = Math.max(240, Math.round(vv.top + vv.height - top - barH));
      setHeight((old) => (old === h ? old : h));
    };
    measure();
    window.addEventListener("scroll", measure, { passive: true });
    return () => window.removeEventListener("scroll", measure);
  }, [vv, keyboard, phone]);

  // ---- the list: follows the newest words only while the reader is at the bottom; otherwise a pill offers the jump
  const scroller = useRef(null);
  const stick = useRef(true);
  const [atBottom, setAtBottom] = useState(true);
  const [unseen, setUnseen] = useState(false);
  const toBottom = useCallback((behavior = "auto") => {
    const el = scroller.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior });
    stick.current = true; setAtBottom(true); setUnseen(false);
  }, []);
  const onScroll = () => {
    const el = scroller.current;
    if (!el) return;
    const near = el.scrollHeight - el.scrollTop - el.clientHeight < NEAR_BOTTOM_PX;
    stick.current = near;
    setAtBottom(near);
    if (near) setUnseen(false);
  };
  useLayoutEffect(() => {
    if (stick.current) toBottom("auto");
    else if (messages.length) setUnseen(true);
  }, [messages, toBottom]);
  // the keyboard opening shrinks the box: keep the newest message in view
  useEffect(() => { if (keyboard && stick.current) toBottom("auto"); }, [keyboard, height, toBottom]);

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
  const [showModels, setShowModels] = useState(false);
  // the model: "" is Auto, which is the function's default (the recommended one); a name is this browser's own choice
  const [models, setModels] = useState(null);                // { models, recommended, default } | null (picker hidden)
  const [model, setModel] = useState(savedModel);
  useEffect(() => {
    let live = true;
    listModels().then((m) => {
      if (!live || !m) return;
      setModels(m);
      // a choice made earlier that its robot no longer offers would only be refused: go back to Auto and say so. A bare model saved
      // before 7 Nov 2026 is moved onto the robot that lists it.
      const kept = savedModel();
      const gwn = m.gateway || "Mireld";
      if (kept && Array.isArray(m.robots)) {
        const c = splitChoice(kept);
        const hit = c.robot ? m.robots.find((r) => r.slug === c.robot && r.enabled && r.models.some((x) => x.id === c.model))
          : m.robots.find((r) => r.enabled && r.models.some((x) => x.id === c.model));
        if (hit && !c.robot) { saveModel(`${hit.slug}|${c.model}`); setModel(`${hit.slug}|${c.model}`); }
        else if (!hit) {
          saveModel(""); setModel("");
          note(t(`Pilihan anda (${c.model || c.robot}) tidak dapat digunakan lagi; guna Auto (${m.auto?.model || m.default}).`, `Your choice (${c.model || c.robot}) can no longer be used; using Auto (${m.auto?.model || m.default}).`));
        }
      } else if (kept && m.listed && !m.models.some((x) => x.id === kept)) {
        saveModel(""); setModel("");
        note(t(`Model pilihan anda (${kept}) tiada lagi dalam senarai ${gwn}; guna Auto (${m.default}).`, `Your chosen model (${kept}) is no longer in ${gwn}'s list; using Auto (${m.default}).`));
      }
    });
    return () => { live = false; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const chooseModel = (id) => { setModel(id); saveModel(id); };
  const robots = Array.isArray(models?.robots) ? models.robots : null;            // null: an older function with one gateway
  const choice = splitChoice(model);
  const chosenRobot = robots ? robots.find((r) => r.slug === (choice.robot || models.auto?.slug)) : null;
  const shownModel = robots ? (choice.robot ? choice.model : models.auto?.model || "") : (model || models?.default || "");
  const modelNote = (chosenRobot ? chosenRobot.models : models?.models || []).find((x) => x.id === shownModel);
  const unusable = robots ? robots.filter((r) => !r.enabled) : [];
  const [notes, setNotes] = useState([]);
  const [notesErr, setNotesErr] = useState("");     // a failed read of the notes, said as such (never shown as "no notes yet")
  const [showNotes, setShowNotes] = useState(false);
  const [draftNote, setDraftNote] = useState("");
  const note = (text) => setMessages((m) => [...m, { role: "note", text, at: new Date().toISOString() }]);

  // The conversation lives in the database: open the newest one, and the pinned notes, when the tab opens.
  useEffect(() => {
    let live = true;
    (async () => {
      const { thread, messages: old } = await loadLatestThread();
      if (live && thread) { setThreadId(thread.id); setMessages(old); }
      const [n, th] = await Promise.all([listMemory().catch((e) => { if (live) setNotesErr(String(e?.message || e)); return null; }), listThreads()]);
      if (live) { if (n) { setNotes(n); setNotesErr(""); } setThreads(th); }
    })();
    return () => { live = false; };
  }, []);

  async function refreshNotes() {
    try { setNotes(await listMemory()); setNotesErr(""); } catch (e) { setNotesErr(String(e?.message || e)); }
  }
  async function refreshThreads() { setThreads(await listThreads()); }
  async function pin() {
    try { await addMemory(draftNote); setDraftNote(""); await refreshNotes(); }
    catch (e) { note(String(e?.message || e)); }
  }
  async function unpin(id) { try { await deleteMemory(id); await refreshNotes(); } catch { /* shown on the next refresh */ } }
  function fresh() { if (busy) return; setThreadId(null); setMessages([]); if (phone) setShowHistory(false); }
  async function openThread(id) {
    if (busy || id === threadId) { if (phone) setShowHistory(false); return; }
    setThreadId(id);
    stick.current = true;
    setMessages(await loadMessages(id));
    if (phone) setShowHistory(false);
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
        // a robot that was not live handed the question on (Auto's chain, or Wan's own pick since 8 Nov 2026): say where and why
        onStatus: (ev) => setStatus(ev.tool === "switch" && ev.reason
          ? t(`Bertukar ke ${ev.detail} kerana ${ev.reason}`, `Switched to ${ev.detail} because ${ev.reason}`)
          : `${toolLabel(ev.tool, t)}${ev.detail ? `: ${ev.detail}` : ""}`) });
      if (!res.connected) {
        settle({ role: "note", text: t("AI belum disambungkan. Mesej anda disimpan di skrin ini sahaja.", "The AI is not connected yet. Your message is kept on this screen only.") });
        return;
      }
      if (res.threadId) setThreadId(res.threadId);
      settle({ text: res.text, tools: res.tools, model: res.robot ? `${res.model} · ${res.robot.name}` : res.model, at: new Date().toISOString() });
      if (res.memorySaved) refreshNotes();
      if (res.modelChanged?.why) note(t(`Pilihan ${res.modelChanged.asked} tidak dapat digunakan (${res.modelChanged.why}); dijawab oleh ${res.modelChanged.used}.`, `${res.modelChanged.asked} could not be used (${res.modelChanged.why}); answered by ${res.modelChanged.used}.`));
      else if (res.modelChanged) note(t(`Model ${res.modelChanged.asked} tidak ada di ${models?.gateway || "Mireld"}; dijawab oleh ${res.modelChanged.used}.`, `Model ${res.modelChanged.asked} is not at ${models?.gateway || "Mireld"}; answered by ${res.modelChanged.used}.`));
      if (res.switched?.length) {
        const to = res.robot ? `${res.robot.name} · ${res.model}` : res.model;
        note(res.auto ? t(`Auto beralih kerana robot pertama gagal: ${res.switched.join("; ")}`, `Auto moved on because the first robot failed: ${res.switched.join("; ")}`)
          : t(`Bertukar ke ${to} kerana robot pilihan anda tidak hidup: ${res.switched.join("; ")}`, `Switched to ${to} because your pick was not live: ${res.switched.join("; ")}`));
      }
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
    // a picture sent is shown in the bubble (an object URL: the bytes never leave the browser twice); other files by name
    const images = files.filter((f) => f.type?.startsWith("image/")).map((f) => ({ url: URL.createObjectURL(f), name: f.name }));
    setMessages((m) => [...m, { role: "user", text, at: new Date().toISOString(), files: files.map((f) => f.name), images }]);
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
    setBusy(true); setShowModels(false);
    const r = await checkAI(robots && !model ? "auto|" : model);         // Auto tests the robot Auto would use
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
      const speed = r.image_ms ? t(`; jawab gambar dalam ${(r.image_ms / 1000).toFixed(1)} s`, `; the picture test took ${(r.image_ms / 1000).toFixed(1)} s`) : "";
      line = `${r.gateway ? `${r.gateway} · ` : ""}${r.model}: ${listed}; ${reads}; ${tools}${speed}; ${search}.`;
    }
    note(line);
    setBusy(false);
  }

  // every picture sent in this conversation, for the viewer
  const pictures = useMemo(() => messages.flatMap((m) => m.images || []).map((p) => ({ url: p.url, title: p.name })), [messages]);
  const zoom = useLightbox(pictures);
  const pictureIndex = (url) => pictures.findIndex((p) => p.url === url);

  const empty = messages.length === 0;
  const lastAssistant = [...messages].reverse().findIndex((m) => m.role === "assistant");
  const lastAssistantIndex = lastAssistant < 0 ? -1 : messages.length - 1 - lastAssistant;
  const currentThread = threads.find((th) => th.id === threadId);
  const modelChip = robots
    ? (choice.robot ? `${choice.model}` : `Auto${models.auto?.model ? ` · ${models.auto.model}` : ""}`)
    : (model || (models?.default ? `Auto · ${models.default}` : ""));
  const hasPicker = Boolean(robots || (models && models.models.length > 0));

  const historyList = (
    <HistoryList threads={threads} threadId={threadId} busy={busy} renaming={renaming} setRenaming={setRenaming} rename={rename}
      remove={remove} openThread={openThread} fresh={fresh} t={t} />
  );
  const notesBody = (
    <>
      <p className="mb-2 text-xs text-muted">{t("Nota ini dihantar kepada AI pada setiap mesej, dalam semua sembang. Anda juga boleh berkata \"ingat bahawa ...\".",
        "These notes go to the AI with every message, in every conversation. You can also say \"remember that ...\".")}</p>
      <ul className="divide-y divide-line text-sm">
        {notes.map((n) => (
          <li key={n.id} className="flex items-start justify-between gap-2 py-2">
            <span className="[overflow-wrap:anywhere]">{n.note}{n.source === "chat" && <span className="ml-1 text-xs opacity-60">({t("disimpan oleh sembang", "saved by chat")})</span>}</span>
            <button type="button" onClick={() => unpin(n.id)} className="-my-1 grid h-10 w-10 shrink-0 place-items-center rounded-full text-muted hover:bg-surface-2 hover:text-danger" aria-label={t("Padam nota", "Delete note")}><IconTrash size={16} /></button>
          </li>
        ))}
        {notesErr && <li className="py-2 text-danger" data-chat-notes-error>{t("Nota tidak dapat dibaca", "The notes could not be read")}: {notesErr}</li>}
        {!notesErr && notes.length === 0 && <li className="py-2 opacity-60">{t("Belum ada nota.", "No notes yet.")}</li>}
      </ul>
    </>
  );
  const notesFooter = (
    <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (draftNote.trim().length >= 3) pin(); }}>
      <input value={draftNote} onChange={(e) => setDraftNote(e.target.value)} maxLength={500} placeholder={t("Nota baharu", "New note")} aria-label={t("Nota baharu", "New note")}
        className="min-h-[44px] min-w-0 flex-1 rounded-tile border border-line bg-bg px-3 text-sm outline-none focus:border-accent" />
      <button type="submit" disabled={draftNote.trim().length < 3} className="min-h-[44px] rounded-tile bg-ink px-4 text-sm font-medium text-bg disabled:opacity-50">{t("Simpan", "Save")}</button>
    </form>
  );

  return (
    <main ref={root} data-chat-root className="mx-auto flex w-full max-w-page flex-col overflow-hidden px-0 sm:px-6" style={{ height: height ? `${height}px` : "calc(100dvh - 8rem)" }}>
      {/* top bar: where you are and which robot answers, in one line, with the panels behind thumb-sized buttons */}
      <div className="flex shrink-0 items-center gap-1 border-b border-line px-2 py-1 sm:px-0 sm:py-2" data-chat-topbar>
        <div className="min-w-0 flex-1 pl-2 sm:pl-0">
          <p className="truncate text-[13px] font-semibold text-accent">{t("Sembang AI", "AI chat")}{currentThread?.title ? <span className="font-normal text-ink"> · {currentThread.title}</span> : ""}</p>
          {hasPicker && (
            <button type="button" onClick={() => setShowModels(true)} disabled={busy} data-chat-model aria-haspopup="dialog" aria-expanded={showModels}
              className="-ml-1 mt-0.5 inline-flex max-w-full items-center gap-1.5 rounded-pill px-1 py-0.5 text-[11px] text-muted hover:bg-surface-2 hover:text-ink disabled:opacity-50"
              title={t("Pilih robot dan model AI", "Choose the AI robot and model")}>
              <StateDot r={chosenRobot} />
              <span className="truncate">{modelChip || t("Model AI", "AI model")}{chosenRobot ? ` (${chosenRobot.name})` : ""}</span>
              <IconChevronDown size={12} className="shrink-0" />
            </button>
          )}
        </div>
        <TopButton onClick={() => setShowHistory((v) => !v)} pressed={showHistory} label={t(`Sejarah (${threads.length})`, `History (${threads.length})`)} badge={threads.length}><IconHistory size={20} /></TopButton>
        <TopButton onClick={() => setShowNotes(true)} pressed={showNotes} label={t(`Ingatan kekal (${notes.length})`, `Pinned memory (${notes.length})`)} badge={notes.length}><IconNotes size={20} /></TopButton>
        <TopButton onClick={fresh} disabled={busy || empty} label={t("Sembang baharu", "New conversation")}><IconMessagePlus size={20} /></TopButton>
      </div>

      <div className="flex min-h-0 flex-1 gap-4">
        {/* from md up the history sits beside the conversation; on a phone it is a sheet (below) */}
        {showHistory && !phone && (
          <aside className="my-3 w-64 shrink-0 overflow-y-auto rounded-card border border-line bg-surface p-3 text-xs" aria-label={t("Sejarah sembang", "Chat history")}>{historyList}</aside>
        )}
        <div className="relative flex min-w-0 flex-1 flex-col">
          {empty ? (
            <div className="flex min-h-0 flex-1 flex-col justify-center overflow-y-auto px-4 py-6 sm:px-0">
              {composer()}
              <p className="mx-auto mt-2 max-w-2xl text-center text-[10px] text-muted">{t("Lampiran: gambar, PDF, Word, Excel, CSV, teks. AI boleh baca laman web awam dan data Semasa; sebut sumbernya.",
                "Attachments: pictures, PDF, Word, Excel, CSV, text. The AI can read public web pages and Semasa data; it names its sources.")}</p>
            </div>
          ) : (
            <>
              <div ref={scroller} data-chat-scroll onScroll={onScroll}
                className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 pt-3 sm:px-0" style={{ WebkitOverflowScrolling: "touch" }}>
                <ol className="mx-auto w-full max-w-2xl space-y-3 pb-3" aria-live="polite">
                  {messages.map((m, i) => (
                    <li key={m.id ? `db${m.id}` : `new${i}`} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
                      <div className={
                        m.role === "user" ? "max-w-[85%] min-w-0 whitespace-pre-wrap rounded-card bg-ink px-4 py-2.5 text-sm text-bg [overflow-wrap:anywhere]"
                          : m.role === "assistant" ? "min-w-0 max-w-[94%] overflow-hidden rounded-card border border-line bg-surface px-3.5 py-2.5 text-sm sm:max-w-[92%] sm:px-4"
                            : "max-w-[85%] rounded-card bg-warn/10 px-4 py-2 text-xs text-warn [overflow-wrap:anywhere]"}>
                        {m.role === "assistant" ? <AnswerBody m={m} status={status} t={t} /> : m.text}
                        {m.images?.length > 0 && (
                          <div className="mt-2 flex flex-wrap gap-2">
                            {m.images.map((p) => (
                              <button type="button" key={p.url} onClick={() => zoom.open(pictureIndex(p.url))} className="overflow-hidden rounded-tile border border-bg/20" aria-label={t(`Buka gambar ${p.name}`, `Open picture ${p.name}`)}>
                                <img src={p.url} alt={p.name} className="max-h-48 max-w-full object-cover" loading="lazy" />
                              </button>
                            ))}
                          </div>
                        )}
                        {m.files?.length > 0 && <span className="mt-1 block text-[11px] opacity-70">📎 {m.files.join(", ")}</span>}
                        {m.role === "assistant" && !m.streaming && (
                          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0 text-[11px] opacity-70">
                            {m.tools?.length > 0 && <span>🔎 {m.tools.map((x) => toolLabel(x, t)).join(" · ")}</span>}
                            {m.model && <span className="truncate">{m.model}</span>}
                            {m.stopped && <span className="text-warn">{t("dihentikan", "stopped")}</span>}
                            <span>{stampMYT(m.at)}</span>
                            <span className="ml-auto flex items-center gap-1">
                              <CopyButton text={m.text} t={t} />
                              {i === lastAssistantIndex && threadId && (
                                <button type="button" onClick={again} disabled={busy} className="inline-flex min-h-[40px] items-center gap-1 rounded-tile px-2 hover:bg-surface-2 hover:text-accent disabled:opacity-50 sm:min-h-0" title={t("Jawab semula", "Answer again")}>
                                  <IconRefresh size={14} /> {t("Jawab semula", "Again")}</button>
                              )}
                            </span>
                          </div>
                        )}
                        {m.role !== "assistant" && <span className="mt-1 block text-[10px] opacity-60">{stampMYT(m.at)}</span>}
                      </div>
                    </li>
                  ))}
                </ol>
              </div>
              <div className="relative shrink-0 border-t border-line bg-bg px-3 pb-2 pt-2 sm:border-0 sm:px-0">
                {!atBottom && (
                  <button type="button" onClick={() => toBottom("smooth")} data-chat-jump
                    className="absolute bottom-full left-1/2 z-10 mb-2 inline-flex min-h-[40px] -translate-x-1/2 items-center gap-1.5 whitespace-nowrap rounded-pill border border-line bg-surface px-4 text-xs font-medium text-ink shadow-lift hover:border-accent">
                    <IconArrowDown size={14} /> {unseen ? t("Mesej baharu", "New message") : t("Ke yang terkini", "Jump to latest")}
                  </button>
                )}
                {composer()}
              </div>
            </>
          )}
        </div>
      </div>

      <Sheet open={Boolean(showHistory && phone)} onClose={() => setShowHistory(false)} title={t("Sejarah sembang", "Chat history")}>{historyList}</Sheet>
      <Sheet open={showNotes} onClose={() => setShowNotes(false)} title={t(`Ingatan kekal (${notes.length})`, `Pinned memory (${notes.length})`)} footer={notesFooter}>{notesBody}</Sheet>
      <Sheet open={showModels} onClose={() => setShowModels(false)} variant="bottom" title={t("Robot dan model AI", "AI robot and model")}
        footer={(
          <div className="flex flex-col gap-1 text-[11px] text-muted">
            {chosenRobot && (
              <span>
                {!choice.robot ? `${t("Auto memilih robot sihat yang pantas dengan model terkuat", "Auto picks a healthy, fast robot with the strongest model")}: ` : ""}
                {chosenRobot.name} ({chosenRobot.provider}): {stateWord(chosenRobot, t)}{speedOf(chosenRobot.speed_ms)}
                {chosenRobot.state_why ? ` · ${chosenRobot.state_why}` : ""}
                {!chosenRobot.tools ? ` · ${t("tanpa alat (web, data Semasa)", "no tools (web, Semasa data)")}` : ""}
                {chosenRobot.private_note ? ` · ${t(chosenRobot.private_note[0], chosenRobot.private_note[1])}` : ""}
                {modelNote ? ` · ${t(modelNote.note_bm, modelNote.note_en)}` : ""}
              </span>
            )}
            {!robots && modelNote && <span>{shownModel === models?.recommended ? `★ ${t("Disyorkan", "Recommended")}: ` : ""}{t(modelNote.note_bm, modelNote.note_en)}</span>}
            <button type="button" onClick={checkModel} disabled={busy}
              className="inline-flex min-h-[44px] items-center justify-center rounded-tile border border-line px-3 text-xs text-ink hover:border-accent hover:text-accent disabled:opacity-50">
              {t("Uji model terpilih: baca gambar dan guna alat", "Test the selected model: pictures and tools")}
            </button>
          </div>
        )}>
        <ModelList models={models} robots={robots} model={model} choose={(id) => { chooseModel(id); setShowModels(false); }} unusable={unusable} t={t} />
      </Sheet>
      <ImageLightbox {...zoom.props} />
    </main>
  );

  // plain JSX, not a component: a component declared inside the page would remount the box (and lose the words) on every render
  function composer() {
    return (
      <>
        {busy && (
          <div className="mx-auto mb-1.5 flex max-w-2xl items-center justify-between gap-3 text-[11px] text-muted" role="status" data-chat-status>
            <span className="inline-flex min-w-0 items-center gap-1.5 truncate"><span className="h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-accent" />{status || t("Sedang menjawab…", "Answering…")}</span>
            <button type="button" onClick={stop} className="inline-flex min-h-[36px] shrink-0 items-center gap-1 rounded-pill border border-line px-3 hover:border-accent hover:text-accent">
              <IconPlayerStop size={12} /> {t("Berhenti", "Stop")}</button>
          </div>
        )}
        <Ai04 onSubmit={send} busy={busy}
          defaultSettings={{ streaming }} onSettingsChange={(s) => { if (s.streaming !== streaming) { setStreaming(s.streaming); saveStream(s.streaming); } if (s.showHistory !== showHistory) setShowHistory(s.showHistory); }}
          onFocusChange={(f) => { if (f && stick.current) setTimeout(() => toBottom("auto"), 300); }}
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
      </>
    );
  }
}

/** A thumb-sized icon button in the top bar, with a small count. */
function TopButton({ onClick, label, badge = 0, pressed = false, disabled = false, children }) {
  return (
    <button type="button" onClick={onClick} disabled={disabled} aria-label={label} title={label} aria-pressed={pressed}
      className={`relative grid h-11 w-11 shrink-0 place-items-center rounded-full transition hover:bg-surface-2 active:bg-surface-2 disabled:opacity-40 ${pressed ? "bg-accent/10 text-accent" : "text-ink"}`}>
      {children}
      {badge > 0 && <span className="absolute right-1 top-1 min-w-[16px] rounded-full bg-accent px-1 text-center text-[9px] font-semibold leading-4 text-accent-ink">{badge > 99 ? "99+" : badge}</span>}
    </button>
  );
}

/** The conversations: open, rename, delete. The two small buttons are always on screen (a finger cannot hover). */
function HistoryList({ threads, threadId, busy, renaming, setRenaming, rename, remove, openThread, fresh, t }) {
  return (
    <>
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs font-semibold">{t("Perbualan", "Conversations")} ({threads.length})</span>
        <button type="button" onClick={fresh} disabled={busy} className="inline-flex min-h-[40px] items-center gap-1 rounded-tile px-2 text-xs text-accent hover:bg-surface-2 disabled:opacity-50"><IconMessagePlus size={14} /> {t("Baharu", "New")}</button>
      </div>
      <ul className="divide-y divide-line">
        {threads.map((th) => (
          <li key={th.id} className={`-mx-1 rounded-tile px-1 ${th.id === threadId ? "bg-accent/10" : ""}`}>
            {renaming?.id === th.id ? (
              <form onSubmit={(e) => { e.preventDefault(); rename(); }} className="flex items-center gap-1 py-1">
                <input autoFocus value={renaming.title} onChange={(e) => setRenaming({ ...renaming, title: e.target.value })} maxLength={80}
                  onKeyDown={(e) => { if (e.key === "Escape") { e.stopPropagation(); setRenaming(null); } }} className="min-h-[40px] min-w-0 flex-1 rounded-tile border border-line bg-bg px-2 text-sm" aria-label={t("Nama perbualan", "Conversation name")} />
                <button type="submit" className="grid h-10 w-10 place-items-center rounded-full text-accent hover:bg-surface-2" aria-label={t("Simpan nama", "Save name")}><IconCheck size={16} /></button>
              </form>
            ) : (
              <div className="flex items-center gap-0.5">
                <button type="button" onClick={() => openThread(th.id)} className="min-h-[44px] min-w-0 flex-1 py-1.5 text-left">
                  <span className="block truncate text-sm">{th.title || t("(tiada tajuk)", "(no title)")}</span>
                  <span className="block text-[11px] text-muted">{timeAgo(th.updated_at)}</span>
                </button>
                <button type="button" onClick={() => setRenaming({ id: th.id, title: th.title || "" })} className="grid h-10 w-10 shrink-0 place-items-center rounded-full text-muted hover:bg-surface-2 hover:text-accent" aria-label={t("Namakan semula", "Rename")}><IconPencil size={15} /></button>
                <button type="button" onClick={() => remove(th.id)} className="grid h-10 w-10 shrink-0 place-items-center rounded-full text-muted hover:bg-surface-2 hover:text-danger" aria-label={t("Padam perbualan", "Delete conversation")}><IconTrash size={15} /></button>
              </div>
            )}
          </li>
        ))}
        {threads.length === 0 && <li className="py-2 text-xs text-muted">{t("Belum ada perbualan.", "No conversations yet.")}</li>}
      </ul>
    </>
  );
}

/** Auto, then each robot with its live state and its models as rows a thumb can hit; a robot that cannot be used says why. */
function ModelList({ models, robots, model, choose, unusable, t }) {
  const Row = ({ value, title, sub, star = false, disabled = false }) => {
    const on = model === value;
    return (
      <li>
        <button type="button" onClick={() => choose(value)} disabled={disabled} role="radio" aria-checked={on}
          className={`flex min-h-[44px] w-full items-center gap-3 rounded-tile px-2 py-1.5 text-left hover:bg-surface-2 disabled:opacity-50 ${on ? "bg-accent/10" : ""}`}>
          <span className={`grid h-5 w-5 shrink-0 place-items-center rounded-full border ${on ? "border-accent bg-accent text-accent-ink" : "border-line"}`}>{on && <IconCheck size={12} />}</span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm">{title}{star ? <span className="ml-1 text-[11px] text-accent">★ {t("disyorkan", "recommended")}</span> : ""}</span>
            {sub && <span className="block truncate text-[11px] text-muted">{sub}</span>}
          </span>
        </button>
      </li>
    );
  };
  if (!models) return null;
  if (!robots) {
    return (
      <ul role="radiogroup" className="space-y-0.5">
        <Row value="" title={t("Auto", "Auto")} sub={models.default} />
        {models.models.map((m) => <Row key={m.id} value={m.id} title={m.id} star={m.recommended} sub={m.note_bm ? t(m.note_bm, m.note_en) : ""} />)}
      </ul>
    );
  }
  return (
    <div className="space-y-3" role="radiogroup">
      <ul className="space-y-0.5">
        <Row value="" title={t("Auto", "Auto")} sub={models.auto?.model ? `${models.auto.model} (${models.auto.name}) · ${t("robot sihat paling pantas, model terkuat", "the fastest healthy robot, strongest model")}` : t("tiada robot sedia", "no robot ready")} />
      </ul>
      {robots.map((r) => (
        <section key={r.slug} aria-label={r.name}>
          <h4 className="mb-0.5 flex items-center gap-2 px-2 text-[11px] font-semibold uppercase tracking-wide text-muted">
            <StateDot r={r} />
            <span className="truncate">{r.name} · {r.provider}</span>
            <span className="ml-auto shrink-0 font-normal normal-case">{r.enabled ? `${stateWord(r, t)}${speedOf(r.speed_ms)}` : t("tidak boleh digunakan", "cannot be used")}</span>
          </h4>
          {r.enabled ? (
            <ul className="space-y-0.5">
              {r.models.map((m) => <Row key={m.id} value={`${r.slug}|${m.id}`} title={m.id} star={m.id === r.default_model}
                sub={[r.state_why, !r.tools ? t("tanpa alat (web, data Semasa)", "no tools (web, Semasa data)") : "", m.note_bm && m.id === r.default_model ? t(m.note_bm, m.note_en) : ""].filter(Boolean).join(" · ")} />)}
            </ul>
          ) : <p className="px-2 py-1 text-[11px] text-muted">{r.why}</p>}
        </section>
      ))}
      {unusable.length > 0 && <p className="sr-only">{t("Tidak tersedia", "Not available")}: {unusable.map((r) => r.name).join(", ")}</p>}
    </div>
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
    <button type="button" onClick={copy} className="inline-flex min-h-[40px] items-center gap-1 rounded-tile px-2 hover:bg-surface-2 hover:text-accent sm:min-h-0" title={t("Salin jawapan", "Copy the answer")} data-chat-copy>
      {done ? <IconCheck size={14} /> : <IconCopy size={14} />} {done ? t("Disalin", "Copied") : t("Salin", "Copy")}</button>
  );
}
