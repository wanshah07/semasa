/* Resit (supabase/033_receipts.sql): the page's arithmetic. Plain functions with no imports so web/receipts.test.mjs
   runs them under Node. The worker (backend/semasa/receipts.py) reads and files; this groups, sums and validates. */

export const CATEGORIES = ["makan", "pengangkutan", "bekalan", "langganan", "utiliti", "perjalanan", "pejabat", "klien", "lain"];
export const CATEGORY_WORDS = {
  makan: ["Makan & minum", "Food & drink"], pengangkutan: ["Pengangkutan", "Transport"], bekalan: ["Bekalan", "Supplies"],
  langganan: ["Langganan", "Subscriptions"], utiliti: ["Utiliti", "Utilities"], perjalanan: ["Perjalanan", "Travel"],
  pejabat: ["Pejabat & pos", "Office & post"], klien: ["Untuk klien", "For a client"], lain: ["Lain", "Other"],
};
export const STATUS_WORDS = {
  pending: ["Menunggu pembaca", "Waiting for the reader"], working: ["Sedang dibaca", "Being read"], done: ["Selesai", "Done"], error: ["Gagal", "Failed"],
};

/** "2026-10": the receipt's own month when read, else the month it was snapped (MYT). */
export function monthOf(r) {
  if (r?.doc_date && /^\d{4}-\d{2}/.test(r.doc_date)) return r.doc_date.slice(0, 7);
  const ms = Date.parse(r?.taken_at || r?.created_at || "");
  if (Number.isNaN(ms)) return "";
  return new Date(ms + 8 * 3600_000).toISOString().slice(0, 7);
}

/** The ringgit figure a receipt contributes: its total when the currency is MYR, else null (never a guessed rate). */
export const amountMYR = (r) => ((r?.currency || "MYR").toUpperCase() === "MYR" && r?.total != null ? Number(r.total) || 0 : null);

const r2 = (n) => Math.round(n * 100) / 100;

/** Receipts grouped by month, newest first, each with its ringgit total, a per-category split and the foreign count. */
export function byMonth(rows) {
  const map = new Map();
  for (const r of rows || []) {
    const k = monthOf(r) || "—";
    if (!map.has(k)) map.set(k, { month: k, rows: [], total: 0, byCategory: {}, foreign: 0, unread: 0 });
    const g = map.get(k);
    g.rows.push(r);
    if (r.status !== "done") g.unread++;
    const myr = amountMYR(r);
    if (myr == null) { if (r.total != null) g.foreign++; continue; }
    g.total = r2(g.total + myr);
    g.byCategory[r.category || "lain"] = r2((g.byCategory[r.category || "lain"] || 0) + myr);
  }
  return [...map.values()].sort((a, b) => b.month.localeCompare(a.month))
    .map((g) => ({ ...g, rows: g.rows.slice().sort((a, b) => String(b.doc_date || b.taken_at).localeCompare(String(a.doc_date || a.taken_at))) }));
}

/** The tiles: this month's ringgit, its count, how many are still unread / failed, how many not yet filed. */
export function receiptsSummary(rows, today) {
  const month = (today || "").slice(0, 7);
  const mine = (rows || []).filter((r) => monthOf(r) === month);
  const sum = mine.reduce((t, r) => t + (amountMYR(r) ?? 0), 0);
  return {
    monthTotal: r2(sum), monthCount: mine.length,
    pending: (rows || []).filter((r) => ["pending", "working"].includes(r.status)).length,
    failed: (rows || []).filter((r) => r.status === "error").length,
    unfiled: (rows || []).filter((r) => r.status === "done" && !r.drive_file_id).length,
    lowConfidence: (rows || []).filter((r) => r.status === "done" && r.confidence != null && r.confidence < 0.6).length,
  };
}

/** What stops a correction being saved. */
export function validateReceipt(r) {
  const bad = [];
  if (r.doc_date && !/^\d{4}-\d{2}-\d{2}$/.test(r.doc_date)) bad.push("doc_date");
  if (r.total !== "" && r.total != null && (Number.isNaN(Number(r.total)) || Number(r.total) < 0)) bad.push("total");
  if (r.category && !CATEGORIES.includes(r.category)) bad.push("category");
  return bad;
}

/** The corrected fields as the database takes them (numbers as numbers, blanks as null). */
export function receiptRow(r) {
  const num = (v) => (v === "" || v == null ? null : Number(v));
  return {
    vendor: String(r.vendor || "").trim(), doc_date: r.doc_date || null, total: num(r.total), tax: num(r.tax),
    currency: (String(r.currency || "MYR").trim().toUpperCase() || "MYR").slice(0, 3), category: CATEGORIES.includes(r.category) ? r.category : "lain",
    payment_method: String(r.payment_method || "").trim(), summary: String(r.summary || "").trim(), notes: String(r.notes || "").trim(),
    subscription_id: r.subscription_id || null,
  };
}

/** A receipt file name the page can show before the worker names the Drive copy. */
export const fileLabel = (r) => [r.doc_date, r.vendor, r.total != null ? `${r.currency === "MYR" ? "RM" : r.currency} ${Number(r.total).toFixed(2)}` : ""].filter(Boolean).join(" · ") || "Resit";
