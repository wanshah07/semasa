/* Ringkasan wang (Wan, 7 Nov 2026: the glass money dashboard, "Ringkasan wang (Disyorkan)"). The page's arithmetic, with no
   reads and no React, so web/money.test.mjs runs it under Node. Every figure comes from a table Semasa already keeps:
   - money IN is an invoice marked PAID, on the day it was paid (a receipt document is that payment's paper and is never
     counted twice; lib/billing.js projectSummary follows the same rule). An invoice still open is shown as pending, never summed;
   - money OUT is a purchase receipt that has been read (semasa_receipts), on its own date, plus a subscription's last payment
     when no receipt was filed for it that month (so a bill is never counted twice). The next 30 days of subscriptions are pending;
   - only ringgit is summed: a foreign figure with no ringgit amount is left out rather than converted at a guessed rate.
   The page (pages/MoneyTab.jsx) hands in only the rows of the business it shows (supabase/066 business_id). */
import { isOpenInvoice } from "./billing.js";
import { amountMYR as receiptMYR } from "./receipts.js";
import { amountMYR as subMYR } from "./subscriptions.js";

const MYT_MS = 8 * 3600_000;
const r2 = (n) => Math.round((Number(n) || 0) * 100) / 100;
const isMYR = (c) => !c || String(c).toUpperCase() === "MYR";

/** An ISO time or a bare date as its Malaysia date. */
export function mytDate(v) {
  if (!v) return "";
  if (/^\d{4}-\d{2}-\d{2}$/.test(v)) return v;
  const ms = Date.parse(v);
  return Number.isNaN(ms) ? "" : new Date(ms + MYT_MS).toISOString().slice(0, 10);
}
export const addDays = (d, n) => new Date(Date.parse(`${d}T00:00:00Z`) + n * 86400_000).toISOString().slice(0, 10);
const addMonths = (ym, n) => { const [y, m] = ym.split("-").map(Number); const t = y * 12 + (m - 1) + n; return `${Math.floor(t / 12)}-${String((t % 12) + 1).padStart(2, "0")}`; };

/** Every movement of money, newest first: {id, name, kind: "in"|"out", category, date, amount (signed), status, source}. */
export function moneyMovements({ docs = [], receipts = [], subs = [] } = {}, today) {
  const out = [];
  for (const d of docs || []) {
    if (d.kind !== "invoice" || !isMYR(d.currency)) continue;
    const name = d.client?.name || d.number || "Invois";
    if (d.status === "paid") {
      const date = mytDate(d.paid_at) || d.issue_date || "";
      if (date) out.push({ id: `inv-${d.id}`, name, kind: "in", category: "income", date, amount: r2(d.total), status: "Completed", source: "invoice" });
    } else if (today && isOpenInvoice(d, today)) {
      out.push({ id: `inv-${d.id}`, name, kind: "in", category: "income", date: d.due_date || d.issue_date || today, amount: r2(d.total), status: "Pending", source: "invoice" });
    }
  }
  const filed = new Set();                               // subscription + month a receipt already covers
  for (const r of receipts || []) {
    if (r.status === "error") continue;
    const amt = receiptMYR(r);
    const date = r.doc_date || mytDate(r.taken_at || r.created_at);
    if (amt == null || !date) continue;
    if (r.subscription_id) filed.add(`${r.subscription_id}:${date.slice(0, 7)}`);
    out.push({ id: `rct-${r.id}`, name: r.vendor || "Resit", kind: "out", category: r.category || "lain", date, amount: -r2(amt), status: "Completed", source: "receipt" });
  }
  for (const s of subs || []) {
    const amt = subMYR(s);
    if (amt == null || !amt) continue;
    const name = [s.vendor, s.name].filter(Boolean).join(" · ") || "Langganan";
    if (s.last_paid && !filed.has(`${s.id}:${s.last_paid.slice(0, 7)}`)) {
      out.push({ id: `sub-${s.id}-${s.last_paid}`, name, kind: "out", category: "langganan", date: s.last_paid, amount: -r2(amt), status: "Completed", source: "subscription" });
    }
    if (today && s.status === "active" && s.next_payment && s.next_payment >= today && s.next_payment <= addDays(today, 30)) {
      out.push({ id: `sub-${s.id}-${s.next_payment}`, name, kind: "out", category: "langganan", date: s.next_payment, amount: -r2(amt), status: "Pending", source: "subscription" });
    }
  }
  return out.sort((a, b) => (b.date || "").localeCompare(a.date || "") || a.id.localeCompare(b.id));
}

const settled = (moves) => moves.filter((m) => m.status === "Completed");
const sums = (moves) => ({
  income: r2(moves.filter((m) => m.amount > 0).reduce((s, m) => s + m.amount, 0)),
  expenses: r2(moves.filter((m) => m.amount < 0).reduce((s, m) => s - m.amount, 0)),
});

/** The chart's three windows, settled money only: the last 7 days by day, the last 30 days by day, the last 12 months by month.
    `words` = {week, month, year, months: [12 short names], day: (iso) => label}. */
export function cashFlowPeriods(moves, today, words) {
  const done = settled(moves || []);
  const days = (n) => Array.from({ length: n }, (_, i) => addDays(today, i - (n - 1))).map((d) => ({ label: words.day(d), ...sums(done.filter((m) => m.date === d)) }));
  const ym = today.slice(0, 7);
  const months = Array.from({ length: 12 }, (_, i) => addMonths(ym, i - 11))
    .map((m) => ({ label: words.months[Number(m.slice(5, 7)) - 1], ...sums(done.filter((x) => x.date.slice(0, 7) === m)) }));
  return [
    { id: "week", label: words.week, points: days(7) },
    { id: "month", label: words.month, points: days(30) },
    { id: "year", label: words.year, points: months },
  ];
}

/** This month's net (money in − money out, settled) and how it compares with last month's, in percent. The percent is null
    unless last month's net was above zero: against a loss or a near-empty month it reads as "+4603%", which is arithmetic, not
    information. */
export function monthNet(moves, today) {
  const done = settled(moves || []);
  const ym = today.slice(0, 7);
  const prev = addMonths(ym, -1);
  const net = (m) => { const s = sums(done.filter((x) => x.date.slice(0, 7) === m)); return r2(s.income - s.expenses); };
  const now = net(ym), before = net(prev);
  return { net: now, previous: before, change: before > 0 ? Math.round(((now - before) / before) * 1000) / 10 : null };
}
