/* Ringkasan wang (lib/money.js): what counts as money in and out, and the chart's windows. `npm test`. */
import assert from "node:assert/strict";
import { cashFlowPeriods, moneyMovements, monthNet, mytDate } from "./src/lib/money.js";

let n = 0;
const t = (name, fn) => { try { fn(); n++; } catch (e) { console.error("FAIL:", name); throw e; } };
const today = "2026-11-07";
const docs = [
  { id: "1", kind: "invoice", status: "paid", total: 1000, currency: "MYR", paid_at: "2026-11-06T17:30:00Z", client: { name: "Klien A" } },   // MYT 7 Nov
  { id: "2", kind: "invoice", status: "sent", total: 500, currency: "MYR", due_date: "2026-11-20", client: { name: "Klien B" } },
  { id: "3", kind: "receipt", status: "issued", total: 1000, currency: "MYR" },                  // the paper for invoice 1: never counted
  { id: "4", kind: "invoice", status: "paid", total: 300, currency: "USD", paid_at: "2026-11-01T00:00:00Z" },   // not ringgit: left out
  { id: "5", kind: "quotation", status: "accepted", total: 9000, currency: "MYR" },
  { id: "6", kind: "invoice", status: "paid", total: 400, currency: "MYR", paid_at: "2026-10-15T02:00:00Z", number: "INV-2026-0003" },
];
const receipts = [
  { id: "a", status: "done", vendor: "Kedai Kopi", total: 12.5, currency: "MYR", doc_date: "2026-11-05", category: "makan" },
  { id: "b", status: "done", vendor: "Anthropic", total: 457.69, currency: "MYR", doc_date: "2026-11-02", category: "langganan", subscription_id: "s1" },
  { id: "c", status: "error", vendor: "x", total: 99, currency: "MYR", doc_date: "2026-11-01" },
  { id: "d", status: "done", vendor: "Hotel", total: 80, currency: "SGD", doc_date: "2026-11-03" },
  { id: "e", status: "pending", total: null },
];
const subs = [
  { id: "s1", vendor: "Anthropic", name: "Max", amount: 108, currency: "USD", amount_myr: 457.69, last_paid: "2026-11-02", next_payment: "2026-12-02", status: "active" },
  { id: "s2", vendor: "CelcomDigi", name: "Mobile", amount: 61.48, currency: "MYR", last_paid: "2026-10-12", next_payment: "2026-11-12", status: "active" },
  { id: "s3", vendor: "Old", amount: 10, currency: "MYR", next_payment: "2026-11-10", status: "ended" },
];
const moves = moneyMovements({ docs, receipts, subs }, today);

t("money in is a paid invoice on its Malaysia payment day; an open one is pending; receipts, quotations and foreign money are not summed", () => {
  const ins = moves.filter((m) => m.kind === "in");
  assert.deepEqual(ins.map((m) => [m.id, m.date, m.amount, m.status]),
    [["inv-2", "2026-11-20", 500, "Pending"], ["inv-1", "2026-11-07", 1000, "Completed"], ["inv-6", "2026-10-15", 400, "Completed"]]);
  assert.equal(mytDate("2026-11-06T17:30:00Z"), "2026-11-07");
});
t("money out: read receipts in ringgit, a subscription's last payment only when no receipt covers that month, and the next 30 days pending", () => {
  const outs = moves.filter((m) => m.kind === "out").map((m) => [m.id, m.amount, m.status]);
  assert.deepEqual(outs, [
    ["sub-s1-2026-12-02", -457.69, "Pending"],                    // 2 Dec is inside the next 30 days from 7 Nov
    ["sub-s2-2026-11-12", -61.48, "Pending"],
    ["rct-a", -12.5, "Completed"],
    ["rct-b", -457.69, "Completed"],
    ["sub-s2-2026-10-12", -61.48, "Completed"],
  ]);
  assert.ok(!outs.some(([id]) => id === "sub-s1-2026-11-02"), "Anthropic's receipt already covers November: not twice");
  assert.ok(!outs.some(([id]) => id.startsWith("sub-s3")), "an ended subscription is not upcoming");
});
t("the chart counts settled money only, by day and by month", () => {
  const words = { week: "W", month: "M", year: "Y", months: ["J", "F", "Mc", "A", "Me", "Jn", "Jl", "O", "S", "Ok", "N", "D"], day: (d) => d.slice(5) };
  const [week, month, year] = cashFlowPeriods(moves, today, words);
  assert.equal(week.points.length, 7);
  assert.equal(month.points.length, 30);
  assert.equal(year.points.length, 12);
  assert.deepEqual(week.points.at(-1), { label: "11-07", income: 1000, expenses: 0 });
  assert.deepEqual(week.points.find((p) => p.label === "11-05"), { label: "11-05", income: 0, expenses: 12.5 });
  assert.deepEqual(year.points.at(-1), { label: "N", income: 1000, expenses: 470.19 });
  assert.deepEqual(year.points.at(-2), { label: "Ok", income: 400, expenses: 61.48 });
  assert.equal(week.points.reduce((s, p) => s + p.income, 0), 1000, "the open invoice (pending) is not in the chart");
});
t("this month's net against last month's", () => {
  assert.deepEqual(monthNet(moves, today), { net: 529.81, previous: 338.52, change: 56.5 });
  assert.equal(monthNet([], today).change, null);
  const loss = [{ id: "x", amount: -50, date: "2026-10-03", status: "Completed" }, { id: "y", amount: 900, date: "2026-11-03", status: "Completed" }];
  assert.deepEqual(monthNet(loss, today), { net: 900, previous: -50, change: null }, "no percent against a month that lost money");
});

console.log(`money: ${n} checks passed`);
