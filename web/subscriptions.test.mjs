/* Langganan: the date arithmetic and the totals (lib/subscriptions.js). `npm test`. */
import assert from "node:assert/strict";
import {
  addMonths, amountMYR, blankSubscription, markPaid, monthlyEquivalent, nextDate, standing, subsSummary, toRow, upcoming, validateSubscription,
} from "./src/lib/subscriptions.js";

let n = 0;
const t = (name, fn) => { try { fn(); n++; } catch (e) { console.error("FAIL:", name); throw e; } };

t("calendar months clamp to the month's last day", () => {
  assert.equal(addMonths("2026-01-31", 1), "2026-02-28");
  assert.equal(addMonths("2026-10-31", 1), "2026-11-30");
  assert.equal(addMonths("2026-10-09", 12), "2027-10-09");
  assert.equal(addMonths("2024-02-29", 12), "2025-02-28");
});

t("nextDate follows the cycle; a one-off has no next date", () => {
  assert.equal(nextDate("2026-10-09", "daily"), "2026-10-10");
  assert.equal(nextDate("2026-10-09", "weekly"), "2026-10-16");
  assert.equal(nextDate("2026-10-09", "monthly"), "2026-11-09");
  assert.equal(nextDate("2026-10-09", "yearly"), "2027-10-09");
  assert.equal(nextDate("2026-10-09", "one_time"), null);
  assert.equal(nextDate(null, "monthly"), null);
});

t("markPaid steps forward from the due date, past today, keeping the billing day", () => {
  assert.deepEqual(markPaid({ cycle: "monthly", next_payment: "2026-10-12" }, "2026-10-09"), { last_paid: "2026-10-09", next_payment: "2026-11-12" });
  // paid late: the due date was 12 Sep, today is 9 Oct; the next is 12 Oct, not 9 Nov
  assert.deepEqual(markPaid({ cycle: "monthly", next_payment: "2026-09-12" }, "2026-10-09"), { last_paid: "2026-10-09", next_payment: "2026-10-12" });
  // two months late: skips to the first future date
  assert.equal(markPaid({ cycle: "monthly", next_payment: "2026-07-12" }, "2026-10-09").next_payment, "2026-10-12");
  // due today counts as paid for today: next is a month on
  assert.equal(markPaid({ cycle: "monthly", next_payment: "2026-10-09" }, "2026-10-09").next_payment, "2026-11-09");
  assert.equal(markPaid({ cycle: "yearly", next_payment: "2027-01-12" }, "2026-10-09").next_payment, "2028-01-12");   // paid ahead: the next year
  assert.deepEqual(markPaid({ cycle: "one_time", next_payment: "2026-10-12" }, "2026-10-09"), { last_paid: "2026-10-09", next_payment: null, status: "ended" });
  assert.equal(markPaid({ cycle: "monthly", next_payment: null }, "2026-10-09").next_payment, "2026-11-09");            // no date: from today
});

t("the ringgit figure: amount_myr first, MYR amount second, otherwise unknown", () => {
  assert.equal(amountMYR({ amount: 108, currency: "USD", amount_myr: 457.69 }), 457.69);
  assert.equal(amountMYR({ amount: 61.48, currency: "MYR" }), 61.48);
  assert.equal(amountMYR({ amount: 7, currency: "USD" }), null);
  assert.equal(amountMYR({ amount: 7, currency: "usd", amount_myr: "" }), null);
});

t("monthly equivalent", () => {
  assert.equal(monthlyEquivalent(409, "yearly"), 34.08);
  assert.equal(monthlyEquivalent(100, "monthly"), 100);
  assert.equal(monthlyEquivalent(10, "weekly"), 43.33);
  assert.equal(monthlyEquivalent(1000, "one_time"), 0);
});

t("standing: overdue, due within 7 days, ok, paused, ended", () => {
  const today = "2026-10-09";
  assert.equal(standing({ status: "active", next_payment: "2026-10-08" }, today), "overdue");
  assert.equal(standing({ status: "active", next_payment: "2026-10-09" }, today), "due");
  assert.equal(standing({ status: "active", next_payment: "2026-10-16" }, today), "due");
  assert.equal(standing({ status: "active", next_payment: "2026-10-17" }, today), "ok");
  assert.equal(standing({ status: "paused", next_payment: "2026-11-01" }, today), "paused");
  assert.equal(standing({ status: "paused", next_payment: "2026-10-01" }, today), "overdue");   // a paused plan's final bill still falls due
  assert.equal(standing({ status: "ended", next_payment: "2026-10-01" }, today), "ended");
  assert.equal(standing({ status: "active", next_payment: null }, today), "ok");
});

const ROWS = [
  { id: 1, vendor: "CelcomDigi", name: "Mobile", amount: 61.48, currency: "MYR", cycle: "monthly", next_payment: "2026-10-12", status: "active" },
  { id: 2, vendor: "Anthropic", name: "Max", amount: 108, currency: "USD", amount_myr: 457.69, cycle: "monthly", next_payment: "2026-11-03", status: "active" },
  { id: 3, vendor: "Render", name: "Servers", amount: 7, currency: "USD", cycle: "monthly", next_payment: "2026-10-01", status: "active" },
  { id: 4, vendor: "Microsoft", name: "365", amount: 409, currency: "MYR", cycle: "yearly", next_payment: "2027-07-16", status: "active" },
  { id: 5, vendor: "BudgetPixel", name: "Starter", amount: 5, currency: "USD", amount_myr: 21, cycle: "monthly", next_payment: null, status: "ended" },
  { id: 6, vendor: "Unifi", name: "Home", amount: 148, currency: "MYR", cycle: "monthly", next_payment: "2026-11-01", status: "paused" },
];

t("upcoming: within the window, overdue first, ended never, paused included", () => {
  const u = upcoming(ROWS, "2026-10-09", 30);
  assert.deepEqual(u.map((s) => s.id), [3, 1, 6, 2]);
  assert.deepEqual(upcoming(ROWS, "2026-10-09", 7).map((s) => s.id), [3, 1]);
});

t("summary: monthly in MYR skips the unpriced row and says how many; due30 and overdue sum only what is priced", () => {
  const s = subsSummary(ROWS, "2026-10-09");
  assert.equal(s.activeCount, 4);
  assert.equal(s.monthly, 61.48 + 457.69 + 34.08);        // Render has no MYR figure
  assert.equal(s.unpriced, 1);
  assert.equal(s.due30Count, 4);
  assert.equal(s.due30, 61.48 + 457.69 + 148);             // Render counted as 0, not invented
  assert.equal(s.overdueCount, 1);
  assert.equal(s.overdue, 0);
  assert.equal(s.soon, 1);                                  // CelcomDigi on the 12th
});

t("validate and toRow", () => {
  const b = blankSubscription("2026-10-09");
  assert.deepEqual(validateSubscription(b), ["name", "vendor", "amount"]);
  const ok = { ...b, name: "Max", vendor: "Anthropic", amount: "108", currency: "usd", amount_myr: "457.69" };
  assert.deepEqual(validateSubscription(ok), []);
  assert.deepEqual(validateSubscription({ ...ok, next_payment: "" }), ["next_payment"]);
  assert.deepEqual(validateSubscription({ ...ok, next_payment: "", cycle: "one_time" }), []);
  assert.deepEqual(validateSubscription({ ...ok, next_payment: "", status: "ended" }), []);
  assert.deepEqual(validateSubscription({ ...ok, amount: "-1" }), ["amount"]);
  const r = toRow(ok);
  assert.equal(r.currency, "USD"); assert.equal(r.amount, 108); assert.equal(r.amount_myr, 457.69);
  assert.equal(r.last_paid, null); assert.equal(r.source, "manual"); assert.equal(r.category, "software");
  assert.equal(toRow({ ...ok, category: "nonsense" }).category, "other");
});

console.log(`subscriptions: ${n} checks passed`);
