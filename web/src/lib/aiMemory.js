/* Memori & Arahan (Wan, 7 Nov 2026, from Claude's own settings: Instructions, "Search and reference chats", "Generate memory
   from chats", "Your memory"). Pure helpers for pages/MemoryTab.jsx, tested by aiMemory.test.mjs.

   Where each thing lives:
     settings.ai_instructions  {text, updated_at}   sent by the AI chat after its own rules (supabase/functions/semasa-chat/logic.js)
     settings.ai_memory        {search_chats, auto_memory}, both on when absent
     semasa_chat_memory        the notes (supabase/025): source 'user' = typed by Wan, 'chat' = saved by the chat when he asked,
                               or written by the nightly memory job (backend/semasa/memory_auto.py)
   The two settings rows are made by supabase/070_ai_memory.sql: the browser may change a setting but never add one. */

export const INSTRUCTIONS_KEY = "ai_instructions";
export const MEMORY_KEY = "ai_memory";
export const INSTRUCTIONS_MAX = 4000;        // the same limit as the function's (chat.test.mjs checks the two agree)
export const NOTE_MIN = 3;
export const NOTE_MAX = 500;                 // the table's own check
export const NOTES_MAX = 40;                 // the chat sends at most this many, and its "remember" stops here too

/** The same cleaning the function does before it sends them, so what is saved is what the model reads. */
export function cleanInstructions(text) {
  return String(text ?? "").replace(/\r\n?/g, "\n").replace(/[\u0000-\u0008\u000b-\u001f\u007f]/g, "")
    .replace(/[ \t]+\n/g, "\n").replace(/\n{3,}/g, "\n\n").trim().slice(0, INSTRUCTIONS_MAX);
}

const obj = (v) => (v && typeof v === "object" && !Array.isArray(v) ? v : {});

export function instructionsOf(settings) {
  const v = obj(settings?.[INSTRUCTIONS_KEY]);
  return { text: typeof v.text === "string" ? v.text : "", updated_at: typeof v.updated_at === "string" ? v.updated_at : "" };
}

/** Both switches, on unless Wan turned one off (an absent row is "on", as the function and the job read it). */
export function memoryOf(settings) {
  const v = obj(settings?.[MEMORY_KEY]);
  return { search_chats: v.search_chats !== false, auto_memory: v.auto_memory !== false };
}

/** Whether the settings rows exist yet: before supabase/070 runs a save finds no row, and the page says which file to run. */
export const hasRows = (settings) => !!settings && INSTRUCTIONS_KEY in settings && MEMORY_KEY in settings;

export function instructionsValue(text, now = new Date()) {
  return { text: cleanInstructions(text), updated_at: now.toISOString() };
}

export function cleanNote(note) {
  return String(note ?? "").replace(/\s+/g, " ").trim();
}

/** null when the note may be saved, else why not ("short" | "long" | "full" | "same"). `notes` are the rows already kept;
    `editing` is the id being changed, which is not counted against the ceiling or compared with itself. */
export function noteProblem(note, notes = [], editing = null) {
  const n = cleanNote(note);
  if (n.length < NOTE_MIN) return "short";
  if (n.length > NOTE_MAX) return "long";
  const others = (notes || []).filter((r) => r && r.id !== editing);
  if (others.some((r) => cleanNote(r.note).toLowerCase() === n.toLowerCase())) return "same";
  if (!editing && others.length >= NOTES_MAX) return "full";
  return null;
}

/** 'user' notes are Wan's own; every other source was written by the chat or the nightly job, shown as "auto". */
export const isAuto = (row) => (row?.source || "user") !== "user";

/** The notes the list shows: newest first, narrowed by `who` ("all" | "user" | "auto") and by the words of `q`. */
export function filterNotes(rows, q = "", who = "all") {
  const words = String(q || "").toLowerCase().split(/\s+/).filter(Boolean);
  return [...(rows || [])]
    .filter((r) => (who === "all" ? true : who === "auto" ? isAuto(r) : !isAuto(r)))
    .filter((r) => words.every((w) => String(r.note || "").toLowerCase().includes(w)))
    .sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")));
}
