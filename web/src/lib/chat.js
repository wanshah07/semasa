/* The AI chat's one door to a model (pages/ChatTab.jsx), connected to supabase/functions/semasa-chat (Wan, 30 Sep
   2026: "for AI chat link to open AI model claude-sonnet-5.5, Base URL https://api.mireld.my/v1").

   The key is NOT in the browser: the page is public and anything under VITE_* is readable by every visitor. The call
   goes to the Edge Function, which holds MIRELD_API_KEY, accepts only a signed-in Semasa user and forwards the
   conversation. Until the function is deployed the page says so plainly (connected:false), never with a made-up reply.

   Memory (supabase/025_chat_memory.sql, 1 Oct 2026): the conversation lives in the database, not in this tab. The page
   sends only the NEW message and a thread id; the function loads the history, Wan's pinned notes and a rolling summary
   itself, so a reload, another device or a long conversation does not lose anything.

   Streaming (1 Oct 2026, "almost similar with claude"): `askAI` with `onDelta` calls the function over fetch with
   {stream:true} and reads its Server-Sent Events, handing each piece of the answer over as it arrives, and can be stopped with
   an AbortSignal. A function that answers one JSON instead (an older deploy) is read as before, so the page never breaks on a
   version gap. Attachments go through the FAQ bar's readers (lib/faqAi.js): pictures, PDF (text pages, scanned pages as pictures),
   Word, Excel, CSV and plain text, all read in the browser. */
import { supabase } from "./SupabaseClient";
import { foldAttachments } from "./chatFiles";
import { prepareInputs } from "./faqAi";
import { explain } from "./fnError";

const FUNCTION = "semasa-chat";

/** Attachments → what the function takes: { name, dataUrl } for a picture, { name, text } for a document, { name, skipped } for the
    rest. A document read as several parts (PDF pages, sheets) is folded into one text per file (lib/chatFiles.js). */
export async function prepareFiles(files, onProgress = () => {}) {
  return foldAttachments(await prepareInputs(files, onProgress));
}

export { explain };

const shape = (data, threadId) => ({ connected: true, text: data.text, threadId: data.thread_id || threadId, tools: data.tools || [], memorySaved: data.memory_saved === true,
  notice: data.notice, model: data.model || "", modelChanged: data.model_changed || null });

/** One turn. `threadId` is null for a new conversation; the function creates it and answers with its id. With `onDelta` the answer is
    streamed (each piece of text as it arrives; `onStatus` names a tool as it runs); `signal` stops it. `regenerate` answers the last
    question of the thread again instead of sending `text`. */
export async function askAI({ text = "", files = [], threadId = null, model = "", regenerate = false, onDelta = null, onStatus = null, signal = null, onProgress = () => {} }) {
  if (!supabase) return { connected: false, text: "" };
  const body = { action: "chat", thread_id: threadId, text, files: regenerate ? [] : await prepareFiles(files, onProgress), ...(model ? { model } : {}), ...(regenerate ? { regenerate: true } : {}) };
  if (onDelta) {
    const streamed = await streamChat(body, { onDelta, onStatus, signal });
    if (streamed) return shape(streamed, threadId);
  }
  const { data, error } = await supabase.functions.invoke(FUNCTION, { body });
  if (error) {
    const why = await explain(error);
    if (why.missing) return { connected: false, text: "" };
    throw new Error(why.message);
  }
  if (!data?.text) throw new Error(data?.error || "Tiada jawapan / no answer");
  return shape(data, threadId);
}

/** The streamed call. Resolves to the done payload, or null when the function did not stream (then the plain call runs). Throws
    on a function error or an abort. */
async function streamChat(body, { onDelta, onStatus, signal }) {
  const url = import.meta.env.VITE_SUPABASE_URL, anon = import.meta.env.VITE_SUPABASE_ANON_KEY;
  const { data: s } = await supabase.auth.getSession();
  const token = s?.session?.access_token;
  if (!url || !anon || !token) return null;
  let res;
  try {
    res = await fetch(`${String(url).replace(/\/+$/, "")}/functions/v1/${FUNCTION}`, {
      method: "POST", signal: signal || undefined,
      headers: { apikey: anon, authorization: `Bearer ${token}`, "content-type": "application/json", accept: "text/event-stream" },
      body: JSON.stringify({ ...body, stream: true }),
    });
  } catch (e) {
    if (e?.name === "AbortError") throw new Error("Dihentikan / stopped");
    return null;                                           // network: the plain call will say what is wrong
  }
  const type = res.headers.get("content-type") || "";
  if (!/event-stream/.test(type)) {
    if (res.status === 404) return { text: "", thread_id: body.thread_id };   // not deployed: the plain call answers connected:false
    let j = null; try { j = await res.json(); } catch { /* not JSON */ }
    if (!res.ok) throw new Error(String(j?.error || `HTTP ${res.status}`));
    if (j?.text) return j;                                  // an older function: one JSON answer
    return null;
  }
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "", done = null;
  for (;;) {
    let step;
    try { step = await reader.read(); } catch (e) { if (e?.name === "AbortError" || signal?.aborted) throw new Error("Dihentikan / stopped"); throw e; }
    if (step.done) break;
    buf += dec.decode(step.value, { stream: true });
    const parts = buf.split("\n\n");
    buf = parts.pop() ?? "";
    for (const block of parts) {
      const data = block.split("\n").filter((l) => l.startsWith("data:")).map((l) => l.slice(5).replace(/^ /, "")).join("\n");
      if (!data) continue;
      let ev; try { ev = JSON.parse(data); } catch { continue; }
      if (ev.type === "delta") onDelta(String(ev.text || ""));
      else if (ev.type === "status") onStatus?.(ev);
      else if (ev.type === "done") done = ev;
      else if (ev.type === "error") throw new Error(String(ev.error || "ralat"));
    }
  }
  if (!done) {
    if (signal?.aborted) throw new Error("Dihentikan / stopped");   // a stream that just closes after Stop is a stop, not a cut
    throw new Error("Jawapan terputus / the answer was cut off");
  }
  return done;
}

/** The newest conversation and its turns, read with the person's own login (row-level security shows only theirs). */
export async function loadLatestThread() {
  if (!supabase) return { thread: null, messages: [] };
  const { data: t, error } = await supabase.from("semasa_chat_threads").select("id,title,updated_at").order("updated_at", { ascending: false }).limit(1).maybeSingle();
  if (error || !t) return { thread: null, messages: [], error: error ? String(error.message || error) : "" };
  return { thread: t, messages: await loadMessages(t.id) };
}

export async function loadMessages(threadId) {
  const { data: rows } = await supabase.from("semasa_chat_messages").select("id,role,content,tools,created_at").eq("thread_id", threadId).order("id", { ascending: true }).limit(300);
  return (rows || []).map((r) => ({ id: r.id, role: r.role, text: r.content, at: r.created_at, tools: r.tools || [] }));
}

/** Every conversation of this person, newest first: [{ id, title, updated_at }]. */
export async function listThreads() {
  if (!supabase) return [];
  const { data } = await supabase.from("semasa_chat_threads").select("id,title,updated_at,created_at").order("updated_at", { ascending: false }).limit(100);
  return data || [];
}

export async function renameThread(id, title) {
  const name = String(title || "").replace(/\s+/g, " ").trim().slice(0, 80);
  if (!name) throw new Error("Nama kosong / empty name");
  const { error } = await supabase.from("semasa_chat_threads").update({ title: name }).eq("id", id);
  if (error) throw new Error(error.message);
}

/** Deletes a conversation and, through the database's cascade, every turn in it. */
export async function deleteThread(id) {
  const { error } = await supabase.from("semasa_chat_threads").delete().eq("id", id);
  if (error) throw new Error(error.message);
}

export async function listMemory() {
  if (!supabase) return [];
  const { data } = await supabase.from("semasa_chat_memory").select("id,note,source,created_at").order("created_at", { ascending: true }).limit(100);
  return data || [];
}

export async function addMemory(note) {
  const n = String(note || "").replace(/\s+/g, " ").trim();
  if (n.length < 3 || n.length > 500) throw new Error("Nota mesti 3 hingga 500 aksara / a note is 3 to 500 characters");
  const { data: u } = await supabase.auth.getUser();
  const { error } = await supabase.from("semasa_chat_memory").insert({ user_id: u?.user?.id, note: n, source: "user" });
  if (error) throw new Error(error.message);
}

export async function deleteMemory(id) {
  const { error } = await supabase.from("semasa_chat_memory").delete().eq("id", id);
  if (error) throw new Error(error.message);
}

/** The "check" action: is the model listed, and does it read a picture. Used from the chat tab's check button. */
export async function checkAI(model = "") {
  if (!supabase) return { error: "not configured" };
  const { data, error } = await supabase.functions.invoke(FUNCTION, { body: { action: "check", ...(model ? { model } : {}) } });
  if (error) {
    const why = await explain(error);
    return { error: why.missing ? "function belum dipasang / not deployed" : why.message };
  }
  return data;
}

/** The chat models the function offers, best default first: { models: [{id, recommended, family, note_en, note_bm}], recommended,
    default, listed }. null when the function is not deployed or answers an old shape (the page then hides the picker). */
export async function listModels() {
  if (!supabase) return null;
  const { data, error } = await supabase.functions.invoke(FUNCTION, { body: { action: "models" } });
  if (error || !data || !Array.isArray(data.models)) return null;
  return data;
}

const MODEL_KEY = "semasa.chat.model";
/** The model this browser chose; "" means Auto (the function's own default, the recommended one). */
export const savedModel = () => { try { return localStorage.getItem(MODEL_KEY) || ""; } catch { return ""; } };
export const saveModel = (id) => { try { if (id) localStorage.setItem(MODEL_KEY, id); else localStorage.removeItem(MODEL_KEY); } catch { /* private mode: not remembered */ } };

const STREAM_KEY = "semasa.chat.stream";
/** Whether this browser wants answers streamed (the default) or in one piece. */
export const savedStream = () => { try { return localStorage.getItem(STREAM_KEY) !== "off"; } catch { return true; } };
export const saveStream = (on) => { try { localStorage.setItem(STREAM_KEY, on ? "on" : "off"); } catch { /* not remembered */ } };
