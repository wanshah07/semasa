/* Langganan (supabase/030_subscriptions.sql): the arithmetic for recurring bills. Plain functions with no imports so
   web/subscriptions.test.mjs runs them under Node as they are. Dates are "YYYY-MM-DD" calendar strings, never Date
   objects, so no time zone can move a renewal by a day. */

export const CYCLES = ["daily", "weekly", "monthly", "yearly", "one_time"];
export const STATUSES = ["active", "paused", "ended"];
export const CATEGORIES = ["software", "telco", "utilities", "membership", "insurance", "finance", "other"];

/** Months a cycle spans, for the monthly equivalent (a yearly bill is a twelfth a month; a one-off is nothing a month). */
const PER_MONTH = { daily: 365 / 12, weekly: 52 / 12, monthly: 1, yearly: 1 / 12, one_time: 0 };

export function addDays(iso, n) {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}
/** Calendar months, clamped to the month's last day (31 Jan + 1 month = 28 Feb, never 3 Mar). */
export function addMonths(iso, n) {
  const [y, m, day] = iso.split("-").map(Number);
  const first = new Date(Date.UTC(y, m - 1 + n, 1));
  const last = new Date(Date.UTC(first.getUTCFullYear(), first.getUTCMonth() + 1, 0)).getUTCDate();
  first.setUTCDate(Math.min(day, last));
  return first.toISOString().slice(0, 10);
}
export const daysBetween = (a, b) => Math.round((Date.parse(`${b}T00:00:00Z`) - Date.parse(`${a}T00:00:00Z`)) / 86400_000);

/** The date after `from` on which the cycle next bills; null for a one-off (nothing more is charged). */
export function nextDate(from, cycle) {
  if (!from) return null;
  switch (cycle) {
    case "daily": return addDays(from, 1);
    case "weekly": return addDays(from, 7);
    case "monthly": return addMonths(from, 1);
    case "yearly": return addMonths(from, 12);
    default: return null;
  }
}

/** The patch for "I paid this": last_paid is today and next_payment steps one cycle on from the date that was due (not
    from today, so a bill paid late or early keeps its billing day), then keeps stepping until it is after today, so a
    bill two months behind lands on the first date still ahead; a one-off is paid and ends. */
export function markPaid(sub, today) {
  if (sub.cycle === "one_time") return { last_paid: today, next_payment: null, status: "ended" };
  let next = nextDate(sub.next_payment || today, sub.cycle);
  let guard = 0;
  while (next <= today && guard++ < 400) next = nextDate(next, sub.cycle);
  return { last_paid: today, next_payment: next };
}

/** The ringgit figure a row contributes to a total: what the bank took for a foreign bill, the amount for a MYR one,
    null when neither is known (the page says how many rows are left out rather than inventing a rate). */
export function amountMYR(sub) {
  if (sub.amount_myr != null && sub.amount_myr !== "") return Number(sub.amount_myr) || 0;
  if ((sub.currency || "MYR").toUpperCase() === "MYR") return Number(sub.amount) || 0;
  return null;
}
export const monthlyEquivalent = (amount, cycle) => Math.round((Number(amount) || 0) * (PER_MONTH[cycle] ?? 0) * 100) / 100;

/** How a row stands today: ended | paused | overdue | due (within `soonDays`) | ok. */
export function standing(sub, today, soonDays = 7) {
  if (sub.status === "ended") return "ended";
  if (!sub.next_payment) return sub.status === "paused" ? "paused" : "ok";
  const d = daysBetween(today, sub.next_payment);
  if (d < 0) return "overdue";
  if (d <= soonDays) return "due";
  return sub.status === "paused" ? "paused" : "ok";
}

/** Rows due between today and today + days (overdue ones first), ended rows never. */
export function upcoming(rows, today, days = 30) {
  const until = addDays(today, days);
  return (rows || [])
    .filter((s) => s.status !== "ended" && s.next_payment && s.next_payment <= until)
    .sort((a, b) => a.next_payment.localeCompare(b.next_payment) || a.vendor.localeCompare(b.vendor));
}

/** The numbers on the cards: monthly equivalent in MYR of every active row, what is due in 30 days, what is overdue,
    and how many rows could not be put in ringgit. */
export function subsSummary(rows, today) {
  const active = (rows || []).filter((s) => s.status === "active");
  let monthly = 0, unpriced = 0;
  for (const s of active) {
    const myr = amountMYR(s);
    if (myr == null) unpriced++;
    else monthly += monthlyEquivalent(myr, s.cycle);
  }
  const due = upcoming(rows, today, 30);
  const sum = (xs) => Math.round(xs.reduce((t, s) => t + (amountMYR(s) ?? 0), 0) * 100) / 100;
  const overdue = due.filter((s) => s.next_payment < today);
  return {
    activeCount: active.length, monthly: Math.round(monthly * 100) / 100, unpriced,
    due30: sum(due), due30Count: due.length, overdue: sum(overdue), overdueCount: overdue.length,
    soon: due.filter((s) => s.next_payment >= today && daysBetween(today, s.next_payment) <= 7).length,
  };
}

/** A blank row for the form. */
export function blankSubscription(today) {
  return { name: "", vendor: "", amount: "", currency: "MYR", amount_myr: "", cycle: "monthly", next_payment: today, last_paid: "",
    status: "active", auto_pay: false, payment_method: "", category: "software", account_ref: "", url: "", notes: "", source: "manual" };
}

/** What stops a row being saved, as a list of field names; empty means it can go. */
export function validateSubscription(s) {
  const bad = [];
  if (!String(s.name || "").trim()) bad.push("name");
  if (!String(s.vendor || "").trim()) bad.push("vendor");
  if (s.amount === "" || s.amount == null || Number.isNaN(Number(s.amount)) || Number(s.amount) < 0) bad.push("amount");
  if (!CYCLES.includes(s.cycle)) bad.push("cycle");
  if (!STATUSES.includes(s.status)) bad.push("status");
  if (s.next_payment && !/^\d{4}-\d{2}-\d{2}$/.test(s.next_payment)) bad.push("next_payment");
  if (s.status === "active" && s.cycle !== "one_time" && !s.next_payment) bad.push("next_payment");
  return bad;
}

/** The row as the database takes it (numbers as numbers, empty dates as null). */
export function toRow(s) {
  const num = (v) => (v === "" || v == null ? null : Number(v));
  return {
    name: String(s.name || "").trim(), vendor: String(s.vendor || "").trim(), amount: Number(s.amount) || 0,
    currency: String(s.currency || "MYR").trim().toUpperCase() || "MYR", amount_myr: num(s.amount_myr), cycle: s.cycle,
    next_payment: s.next_payment || null, last_paid: s.last_paid || null, status: s.status, auto_pay: Boolean(s.auto_pay),
    payment_method: String(s.payment_method || "").trim(), category: CATEGORIES.includes(s.category) ? s.category : "other",
    account_ref: String(s.account_ref || "").trim(), url: String(s.url || "").trim(), notes: String(s.notes || "").trim(),
    source: String(s.source || "manual").trim() || "manual",
  };
}
