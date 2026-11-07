/* Gemini with several API keys, picked automatically (Wan, 6 Nov 2026). The keys live in semasa_gemini_keys (supabase/061), which the
   page can never read: it adds, switches, renames and deletes through functions and sees a hint, a status and the last error. The
   switches are settings.gemini. The worker (backend/semasa/gemini_keys.py) picks the key; this file only says what each looks like.
   Pure helpers, tested in geminiKeys.test.mjs; DEFAULTS mirror the backend's. */

export const DEFAULTS = { enabled: true, model: "gemini-2.5-flash", image_model: "gemini-2.5-flash-image", images: true, max_images: 6, jobs: ["motion", "ideas"] };
export const MAX_KEYS = 10;
export const JOB_CHOICES = [
  ["motion", ["Skrip dan penulis Motion", "Motion script and writer"]],
  ["ideas", ["Penulis idea dan pembaca gambar", "Idea writer and picture reader"]],
  ["reader", ["Semua kerja lain (Otak AI, resit, bil, CRM, imbasan)", "Every other job (Otak AI, receipts, billing, CRM, scrape)"]],
];

/** settings.gemini over the defaults, as the worker reads it. */
export function settingsOf(raw) {
  const v = raw && typeof raw === "object" ? raw : {};
  const jobs = Array.isArray(v.jobs) ? v.jobs.filter((j) => JOB_CHOICES.some(([k]) => k === j)) : DEFAULTS.jobs;
  const text = (x, d) => (typeof x === "string" && x.trim() ? x.trim() : d);
  return {
    enabled: v.enabled !== false, model: text(v.model, DEFAULTS.model), image_model: text(v.image_model, DEFAULTS.image_model),
    images: v.images !== false, max_images: Math.max(1, Math.min(8, Number(v.max_images) || DEFAULTS.max_images)), jobs,
  };
}

/** The job list with one job switched on or off, in a steady order. */
export const toggleJob = (jobs, job, on) => JOB_CHOICES.map(([k]) => k).filter((k) => (k === job ? on : (jobs || []).includes(k)));

/** The same rule the database applies to a pasted key (062: Google's newer keys can hold a dot). */
export const KEY_RE = /^[A-Za-z0-9._~-]{20,200}$/;
export const validKey = (s) => KEY_RE.test(String(s || "").trim());

/** Why a pasted key is refused, as [BM, EN]; null when it is fine. The page says this, the database says the same in its own words. */
export function keyProblem(raw) {
  const s = String(raw || "").trim();
  if (!s) return ["Tampal kunci API dahulu.", "Paste the API key first."];
  if (/\s/.test(s)) return ["Kunci ada ruang atau baris baharu di tengah: tampal hanya kunci itu, satu baris.", "The key has a space or a line break inside: paste only the key, on one line."];
  if (s.length < 20) return [`Kunci terlalu pendek (${s.length} huruf, sekurang-kurangnya 20): salin semua kunci.`, `The key is too short (${s.length} characters, at least 20): copy all of it.`];
  if (s.length > 200) return [`Kunci terlalu panjang (${s.length} huruf, paling banyak 200): tampal kunci sahaja.`, `The key is too long (${s.length} characters, at most 200): paste the key only.`];
  if (!KEY_RE.test(s)) {
    const bad = [...new Set(s.replace(/[A-Za-z0-9._~-]/g, "").split(""))].slice(0, 4).join(" ");
    return [`Ada aksara yang tidak boleh ada dalam kunci: ${bad}`, `The key holds characters a key never has: ${bad}`];
  }
  return null;
}

/** off | bad | resting | ok | new. */
export function keyState(row, now = Date.now()) {
  if (!row || row.enabled === false) return "off";
  if (row.status === "bad") return "bad";
  const rest = Date.parse(row.cooldown_until || "");
  if (Number.isFinite(rest) && rest > now) return "resting";
  return row.status === "ok" ? "ok" : "new";
}

export const STATE_WORDS = {
  off: ["Dimatikan", "Switched off"], bad: ["Ditolak Google", "Refused by Google"], resting: ["Berehat (had kadar)", "Resting (rate limit)"],
  ok: ["Berfungsi", "Working"], new: ["Belum diuji", "Not tried yet"],
};
export const STATE_CLS = { off: "bg-surface-2 text-muted", bad: "bg-danger/15 text-danger", resting: "bg-warn/15 text-warn", ok: "bg-ok/15 text-ok", new: "bg-accent/15 text-accent" };

/** Whole minutes a resting key has left (at least 1), or 0. */
export function restMinutes(row, now = Date.now()) {
  const rest = Date.parse(row?.cooldown_until || "");
  return Number.isFinite(rest) && rest > now ? Math.max(1, Math.ceil((rest - now) / 60000)) : 0;
}

/** The keys Semasa can use right now (on, not refused, not resting). */
export const usableCount = (rows, now = Date.now()) => (rows || []).filter((r) => ["ok", "new"].includes(keyState(r, now))).length;
