/* Memori & Arahan (src/lib/aiMemory.js, pages/MemoryTab.jsx): the instructions, the two switches and the notes. `npm test`. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { INSTRUCTIONS_KEY, INSTRUCTIONS_MAX, MEMORY_KEY, NOTES_MAX, cleanInstructions, filterNotes, hasRows, instructionsOf, instructionsValue,
  isAuto, memoryOf, noteProblem, settingsState } from "./src/lib/aiMemory.js";
import { segmentOf } from "./src/lib/tabs.js";

let n = 0;
const t = (name, fn) => { try { fn(); n++; } catch (e) { console.error("FAIL:", name); throw e; } };

t("both switches are on until Wan turns one off, as Claude's are", () => {
  assert.deepEqual(memoryOf({}), { search_chats: true, auto_memory: true });
  assert.deepEqual(memoryOf({ ai_memory: { search_chats: false } }), { search_chats: false, auto_memory: true });
  assert.deepEqual(memoryOf({ ai_memory: "junk" }), { search_chats: true, auto_memory: true });
});
t("the instructions read back as saved, and an empty or odd row is empty", () => {
  assert.deepEqual(instructionsOf({ ai_instructions: { text: "Jawab pendek.", updated_at: "2026-11-07T00:00:00Z" } }), { text: "Jawab pendek.", updated_at: "2026-11-07T00:00:00Z" });
  assert.deepEqual(instructionsOf({ ai_instructions: { text: 5 } }), { text: "", updated_at: "" });
  assert.deepEqual(instructionsOf(null), { text: "", updated_at: "" });
});
t("what is saved is cleaned and stamped, never longer than 4000", () => {
  const v = instructionsValue("  satu\r\n\n\n\ndua  ", new Date("2026-11-07T01:02:03Z"));
  assert.deepEqual(v, { text: "satu\n\ndua", updated_at: "2026-11-07T01:02:03.000Z" });
  assert.equal(cleanInstructions("x".repeat(INSTRUCTIONS_MAX * 2)).length, INSTRUCTIONS_MAX);
});
t("before supabase/070 runs the page knows the rows are missing", () => {
  assert.equal(hasRows({}), false);
  assert.equal(hasRows({ [INSTRUCTIONS_KEY]: {}, [MEMORY_KEY]: {} }), true);
});
t("the page sends Wan to supabase/070 only once the settings were read, without an error, and a row is missing", () => {
  const rows = { [INSTRUCTIONS_KEY]: {}, [MEMORY_KEY]: {} };
  assert.equal(settingsState({}, { loading: true }), "loading", "the first read on its way is not a missing row");
  assert.equal(settingsState({}, { error: "JWT expired" }), "error", "a failed read says nothing about the rows");
  assert.equal(settingsState({}, { loading: false, error: "" }), "missing");
  assert.equal(settingsState({ [INSTRUCTIONS_KEY]: {} }), "missing");
  assert.equal(settingsState(rows, { loading: true }), "ready", "a poll that reloads keeps the switches usable");
  assert.equal(settingsState(rows, { error: "network" }), "ready", "rows already read stay usable when a later poll fails");
  assert.equal(settingsState(null), "missing");
  const page = readFileSync(new URL("./src/pages/MemoryTab.jsx", import.meta.url), "utf8");
  assert.ok(page.includes('state === "missing" &&') && page.includes("data-memory-migrate"), "the 070 notice is shown only when missing");
  assert.ok(/const ready = state === "ready";/.test(page), "the switches and Save follow the same state");
  const app = readFileSync(new URL("./src/App.jsx", import.meta.url), "utf8");
  assert.match(app, /loading: settingsLoading, error: settingsError \} = useSettings\(allowed\)/);
  assert.match(app, /<MemoryTab [^>]*settingsLoading=\{settingsLoading\} settingsError=\{settingsError\}/);
});
t("a failed read of the notes throws, so it is never shown as no notes nor lets a note past the ceiling", () => {
  const chat = readFileSync(new URL("./src/lib/chat.js", import.meta.url), "utf8");
  const body = chat.slice(chat.indexOf("export async function listMemory"), chat.indexOf("export async function addMemory"));
  assert.match(body, /const \{ data, error \} = await supabase\.from\("semasa_chat_memory"\)/);
  assert.match(body, /if \(error\) throw new Error/);
  const page = readFileSync(new URL("./src/pages/MemoryTab.jsx", import.meta.url), "utf8");
  assert.ok(page.includes("notes != null && !noteErr && shown.length === 0"), "the empty message waits for a read that worked");
  assert.ok(!/setNotes\(\[\]\)/.test(page), "a failed read does not empty the list");
  const tab = readFileSync(new URL("./src/pages/ChatTab.jsx", import.meta.url), "utf8");
  assert.match(tab, /listMemory\(\)\.catch\(/, "the chat's first read survives a failed notes read (threads still load)");
  assert.match(tab, /async function refreshNotes\(\) \{\s*try \{ setNotes\(await listMemory\(\)\)/, "refreshNotes never rejects");
  assert.ok(tab.includes("{!notesErr && notes.length === 0"), "the chat's notes panel says a failed read, not no notes");
});
t("one note action at a time, and a duplicate is judged against the database's list, not the page's copy", () => {
  const page = readFileSync(new URL("./src/pages/MemoryTab.jsx", import.meta.url), "utf8");
  assert.match(page, /const lock = useRef\(false\)/);
  assert.match(page, /async function once\(tag, fn\) \{\s*if \(lock\.current\) return;\s*lock\.current = true;/);
  assert.match(page, /finally \{ lock\.current = false; setBusy\(""\); \}/);
  for (const fn of ["add", "saveEdit", "remove"]) {
    const body = page.slice(page.indexOf(`async function ${fn}(`), page.indexOf("\n  }\n", page.indexOf(`async function ${fn}(`)));
    assert.ok(/await once\(/.test(body), `${fn} runs through the lock`);
  }
  for (const fn of ["add", "saveEdit"]) {
    const body = page.slice(page.indexOf(`async function ${fn}(`), page.indexOf("\n  }\n", page.indexOf(`async function ${fn}(`)));
    assert.ok(/noteProblem\([^)]*await freshNotes\(\)/.test(body), `${fn} checks a fresh list`);
  }
  assert.ok(page.includes('e.key === "Enter" && !e.repeat && !busy'), "a held or repeated Enter adds nothing twice");
  // the check itself is case- and space-insensitive against whatever list it is handed
  assert.equal(noteProblem("WAN GUNA  buffer", [{ id: "x", note: "Wan guna Buffer" }]), "same");
});
t("a note must be 3 to 500 characters, new, and fit under the 40 the chat sends", () => {
  assert.equal(noteProblem("ab"), "short");
  assert.equal(noteProblem("x".repeat(501)), "long");
  assert.equal(noteProblem("  Wan  guna Buffer ", [{ id: "1", note: "wan guna buffer" }]), "same");
  const full = Array.from({ length: NOTES_MAX }, (_, i) => ({ id: String(i), note: `nota ${i}` }));
  assert.equal(noteProblem("nota baharu", full), "full");
  assert.equal(noteProblem("nota 3 diubah", full, "3"), null, "changing a note is never blocked by the ceiling");
  assert.equal(noteProblem("nota 3", full, "3"), null, "saving a note unchanged is not a duplicate of itself");
  assert.equal(noteProblem("Wan guna Composio"), null);
});
t("a note typed by Wan is his; anything the chat or the nightly job saved is auto", () => {
  assert.equal(isAuto({ source: "user" }), false);
  assert.equal(isAuto({}), false);
  assert.equal(isAuto({ source: "chat" }), true);
});
t("the list is newest first, filtered by who wrote it and by every word searched", () => {
  const rows = [
    { id: "a", note: "Wan guna Buffer untuk Facebook", source: "user", created_at: "2026-11-01" },
    { id: "b", note: "Wan mahu jadual ringkas", source: "chat", created_at: "2026-11-05" },
    { id: "c", note: "Wan guna Composio untuk LinkedIn", source: "chat", created_at: "2026-11-03" },
  ];
  assert.deepEqual(filterNotes(rows).map((r) => r.id), ["b", "c", "a"]);
  assert.deepEqual(filterNotes(rows, "", "auto").map((r) => r.id), ["b", "c"]);
  assert.deepEqual(filterNotes(rows, "", "user").map((r) => r.id), ["a"]);
  assert.deepEqual(filterNotes(rows, "GUNA untuk").map((r) => r.id), ["c", "a"]);
});
t("the page sits beside the AI chat, writes only its two settings, and edits notes through the chat's own helpers", () => {
  assert.equal(segmentOf((bm) => bm, "memori")?.id, "dashboard");
  assert.equal(segmentOf((bm) => bm, "dokumen")?.id, "reference");
  const page = readFileSync(new URL("./src/pages/MemoryTab.jsx", import.meta.url), "utf8");
  assert.ok(page.includes("save(INSTRUCTIONS_KEY") && page.includes("save(MEMORY_KEY"));
  assert.ok(/updateMemory/.test(page) && /deleteMemory/.test(page) && /addMemory/.test(page));
  assert.ok(!/\u2014/.test(page), "no em dash in what a person reads");
});
t("supabase/070 makes both rows, safe to run again, and never overwrites what Wan saved", () => {
  const sql = readFileSync(new URL("../supabase/070_ai_memory.sql", import.meta.url), "utf8");
  assert.match(sql, /'ai_instructions'/);
  assert.match(sql, /'ai_memory'/);
  assert.match(sql, /"search_chats": true/);
  assert.match(sql, /"auto_memory": true/);
  assert.equal((sql.match(/on conflict \(key\) do nothing/g) || []).length, 2);
  assert.ok(!/\bdrop table\b|\bdelete from\b|\btruncate\b/i.test(sql));
});

console.log(`aiMemory: ${n} checks passed`);
