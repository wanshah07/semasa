/* Extra AI providers Wan adds on the API tab (supabase/074): an Anthropic key, a second KiosAPI key, any OpenAI-compatible
   gateway. Each becomes a robot (Wanshah 6, 7, ...) the backend's router, the probe, Telegram and the AI chat can use. The rows
   are semasa_ai_providers (the page may read them, never the key); writes go through semasa_save_ai_provider and
   semasa_delete_ai_provider. Pure helpers, tested in aiProviders.test.mjs; the rules mirror the database's. */

import { stateOf } from "./aiTeam.js";

export const RESERVED = ["rootsys", "mireld", "kiosapi", "gemini", "chatgpt"];
export const DIALECTS = [["openai", ["OpenAI-compatible (KiosAPI, OpenAI, gateway lain)", "OpenAI-compatible (KiosAPI, OpenAI, another gateway)"]],
  ["anthropic", ["Anthropic (Claude)", "Anthropic (Claude)"]]];
// null or an empty list in the database means EVERY job (the edge functions' rule); the form always saves an explicit list
export const JOB_CHOICES = [
  ["chat", ["Sembang AI (termasuk Auto)", "AI chat (Auto included)"]],
  ["reader", ["Kerja penulis: imbasan, Otak AI, resit, bil, CRM, FAQ, reka bentuk", "Writer jobs: scrape, Otak AI, receipts, billing, CRM, FAQ, design"]],
  ["ideas", ["Penulis idea dan pembaca gambar", "Idea writer and picture reader"]],
  ["motion", ["Penulis Motion", "Motion writer"]],
  ["telegram", ["Jawapan pantas Telegram", "Telegram fast answers"]],
];
export const ALL_JOBS = JOB_CHOICES.map(([k]) => k);
export const ID_RE = /^[a-z0-9-]{2,24}$/;
export const MAX_PROVIDERS = 20;

/** The empty form, or one filled from a row for editing (the key is never in a row: the field starts empty = keep). */
export function formOf(row) {
  if (!row) return { id: "", name: "", dialect: "openai", base_url: "", model: "", api_key: "", enabled: true, jobs: [...ALL_JOBS], notes: "" };
  return { id: row.id, name: row.name || "", dialect: row.dialect || "openai", base_url: row.base_url || "", model: row.model || "", api_key: "",
    enabled: row.enabled !== false, jobs: jobsOf(row.jobs), notes: row.notes || "" };
}

/** The jobs a row allows: null or an empty list is every job. */
export function jobsOf(jobs) {
  const list = Array.isArray(jobs) ? jobs.filter((j) => ALL_JOBS.includes(j)) : [];
  return list.length ? ALL_JOBS.filter((j) => list.includes(j)) : [...ALL_JOBS];
}

/** A slug suggested from a name: "KiosAPI 2" -> "kiosapi-2". */
export function slugOf(name) {
  return String(name || "").toLowerCase().normalize("NFKD").replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 24);
}

/** The host of an https:// endpoint, lower-cased, or "". */
export function hostOf(url) {
  const m = /^https:\/\/([^/:?#\s]+)/i.exec(String(url || "").trim());
  return m ? m[1].toLowerCase() : "";
}

/** The job list with one job switched on or off, in a steady order. */
export const toggleJob = (jobs, job, on) => ALL_JOBS.filter((k) => (k === job ? on : (jobs || []).includes(k)));

/** Why the form cannot be saved, as [BM, EN]; null when it can. `existing` is the row being edited (null for a new one);
    `rows` every provider, so a new id is not a duplicate. The database says the same in its own words. */
export function formProblem(f, { existing = null, rows = [] } = {}) {
  const id = String(f.id || "").trim().toLowerCase();
  if (!ID_RE.test(id)) return ["ID: 2 hingga 24 huruf kecil, digit dan sengkang (ia menamakan robot di mana-mana).", "ID: 2 to 24 small letters, digits and dashes (it names the robot everywhere)."];
  if (RESERVED.includes(id)) return [`"${id}" ialah robot sedia ada: ia ada kad sendiri.`, `"${id}" is a built-in robot: it has its own card.`];
  if (!existing && rows.some((r) => r.id === id)) return [`"${id}" sudah ada: sunting yang itu.`, `"${id}" already exists: edit that one.`];
  if (!String(f.name || "").trim()) return ["Beri nama kepada penyedia ini.", "Give the provider a name."];
  if (f.dialect === "gemini") return ["Kunci Gemini diletakkan pada kad Gemini, tempat beberapa kunci dipilih automatik.", "A Gemini key goes on the Gemini card, where several keys are picked automatically."];
  if (!["openai", "anthropic"].includes(f.dialect)) return ["Dialek: openai atau anthropic.", "Dialect: openai or anthropic."];
  if (!hostOf(f.base_url)) return ["Endpoint mesti bermula dengan https://", "The endpoint must start with https://"];
  if (hostOf(f.base_url) === "generativelanguage.googleapis.com") return ["Itu hos Gemini: gunakan kad Gemini.", "That is Gemini's host: use the Gemini card."];
  const key = String(f.api_key || "").trim();
  if (key) {
    if (/\s/.test(key) || key.length < 8) return ["Itu tidak kelihatan seperti kunci API (tiada ruang, sekurang-kurangnya 8 aksara).", "That does not look like an API key (no spaces, at least 8 characters)."];
    if (!String(f.model || "").trim()) return ["Namakan model bersama kunci.", "Name the model together with the key."];
  } else if (!existing) {
    return ["Tampal kunci API: penyedia baharu tanpa kunci bukan robot.", "Paste the API key: a new provider without a key is not a robot."];
  }
  if (!(f.jobs || []).length) return ["Tanda sekurang-kurangnya satu kerja.", "Tick at least one job."];
  return null;
}

/** The host move that drops the key (the database does it; the page says so before the save). */
export function keyWillDrop(f, existing) {
  return !!(existing && existing.key_host && !String(f.api_key || "").trim() && hostOf(f.base_url) !== String(existing.key_host).toLowerCase());
}

/** The arguments for semasa_save_ai_provider. An empty key means "keep the saved one". */
export function rpcArgs(f) {
  return {
    p_id: String(f.id || "").trim().toLowerCase(), p_name: String(f.name || "").trim(), p_dialect: f.dialect, p_base_url: String(f.base_url || "").trim().replace(/\/+$/, ""),
    p_model: String(f.model || "").trim(), p_api_key: String(f.api_key || "").trim() || null, p_enabled: f.enabled !== false,
    p_jobs: ALL_JOBS.filter((j) => (f.jobs || []).includes(j)), p_notes: String(f.notes || "").trim() || null,
  };
}

/** off | nokey | active | standby | offline | unchecked: the provider's own switch and key first, then the probe's row. */
export function providerState(row, statusRow, usageRows = [], now = Date.now()) {
  if (!row || row.enabled === false) return "off";
  if (!row.key_host || !row.key_hint) return "nokey";
  if (hostOf(row.base_url) !== String(row.key_host).toLowerCase()) return "nokey";     // the key is bound to another host
  if (!statusRow) return "unchecked";
  return stateOf(statusRow, usageRows, now);
}

export const STATE_WORDS = {
  off: ["Dimatikan", "Switched off"], nokey: ["Tiada kunci", "No key"], unchecked: ["Belum disemak", "Not checked yet"],
  active: ["Aktif", "Active"], standby: ["Sedia", "Standby"], offline: ["Luar talian", "Offline"],
};
export const STATE_CLS = {
  off: "bg-surface-2 text-muted", nokey: "bg-warn/15 text-warn", unchecked: "bg-accent/15 text-accent",
  active: "bg-ok/15 text-ok", standby: "bg-warn/15 text-warn", offline: "bg-danger/15 text-danger",
};
export const DOT_CLS = { off: "bg-muted", nokey: "bg-warn", unchecked: "bg-accent", active: "bg-ok", standby: "bg-warn", offline: "bg-danger" };

/** The providers in the order the backend numbers them (oldest first), each with its robot label. */
export function numbered(rows) {
  return [...(rows || [])].sort((a, b) => `${a.created_at || ""}${a.id}`.localeCompare(`${b.created_at || ""}${b.id}`))
    .map((r, n) => ({ ...r, robot: `W${6 + n}` }));
}
