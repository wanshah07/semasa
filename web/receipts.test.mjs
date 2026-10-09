/* Resit: grouping, sums, validation (lib/receipts.js). `npm test`. */
import assert from "node:assert/strict";
import { amountMYR, byMonth, fileLabel, monthOf, receiptRow, receiptsSummary, validateReceipt } from "./src/lib/receipts.js";

let n = 0;
const t = (name, fn) => { try { fn(); n++; } catch (e) { console.error("FAIL:", name); throw e; } };

const R = [
  { id: 1, status: "done", doc_date: "2026-10-09", total: 45, currency: "MYR", category: "pengangkutan", drive_file_id: "f", confidence: 0.9, taken_at: "2026-10-09T01:00:00Z" },
  { id: 2, status: "done", doc_date: "2026-10-05", total: 104.95, currency: "MYR", category: "utiliti", drive_file_id: "", confidence: 0.5, taken_at: "2026-10-05T01:00:00Z" },
  { id: 3, status: "done", doc_date: "2026-10-02", total: 7, currency: "USD", category: "langganan", drive_file_id: "f", taken_at: "2026-10-02T01:00:00Z" },
  { id: 4, status: "pending", doc_date: null, total: null, currency: "MYR", taken_at: "2026-09-30T23:30:00Z" },   // 1 Oct MYT
  { id: 5, status: "error", doc_date: "2026-09-12", total: 12.9, currency: "MYR", category: "makan", taken_at: "2026-09-12T01:00:00Z" },
];

t("month: the receipt's date, else the snap month in Malaysia time", () => {
  assert.equal(monthOf(R[0]), "2026-10"); assert.equal(monthOf(R[3]), "2026-10"); assert.equal(monthOf(R[4]), "2026-09"); assert.equal(monthOf({}), "");
});

t("ringgit only: a USD receipt is counted as foreign, never converted", () => {
  assert.equal(amountMYR(R[0]), 45); assert.equal(amountMYR(R[2]), null); assert.equal(amountMYR(R[3]), null);
});

t("byMonth: newest month first, totals and category split, foreign and unread counted", () => {
  const g = byMonth(R);
  assert.deepEqual(g.map((x) => x.month), ["2026-10", "2026-09"]);
  assert.equal(g[0].total, 149.95); assert.deepEqual(g[0].byCategory, { pengangkutan: 45, utiliti: 104.95 });
  assert.equal(g[0].foreign, 1); assert.equal(g[0].unread, 1); assert.deepEqual(g[0].rows.map((r) => r.id), [1, 2, 3, 4]);
  assert.equal(g[1].total, 12.9);
});

t("summary tiles", () => {
  const s = receiptsSummary(R, "2026-10-09");
  assert.deepEqual(s, { monthTotal: 149.95, monthCount: 4, pending: 1, failed: 1, unfiled: 1, lowConfidence: 1 });
});

t("validate and row", () => {
  assert.deepEqual(validateReceipt({ doc_date: "9/10/2026", total: "x", category: "nope" }), ["doc_date", "total", "category"]);
  assert.deepEqual(validateReceipt({ doc_date: "2026-10-09", total: "45.00", category: "makan" }), []);
  const r = receiptRow({ vendor: " ZUS ", doc_date: "", total: "12.90", tax: "", currency: "rm", category: "makan", subscription_id: "" });
  assert.equal(r.vendor, "ZUS"); assert.equal(r.doc_date, null); assert.equal(r.total, 12.9); assert.equal(r.tax, null); assert.equal(r.currency, "RM"); assert.equal(r.subscription_id, null);
  assert.equal(fileLabel(R[0]), "2026-10-09 · RM 45.00"); assert.equal(fileLabel({}), "Resit");
});

console.log(`receipts: ${n} checks passed`);
