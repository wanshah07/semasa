/* Bil: the arithmetic, the rules and the paper, checked where it matters (money, dates, statuses, reminders, the words
   on each kind of paper). `npm test`. */
import assert from "node:assert/strict";
import {
  addDays, afterReminder, billingSettings, calcTotals, clientSnapshot, daysBetween, effectiveStatus, emailFor, fileName, fmtDate,
  invoiceFromQuotation, money, nextReminder, numberPreview, projectSummary, publicLink, receiptFromInvoice, summary, validateDoc,
} from "./src/lib/billing.js";
import { documentHtml, pagesHtml } from "./src/lib/billingDoc.js";

let n = 0;
const t = (name, fn) => { try { fn(); n++; } catch (e) { console.error("FAIL:", name); throw e; } };

const ITEMS = [{ description: "Trustgate token", qty: 1, rate: 480 }, { description: "Notification", qty: 3, rate: 280 }, { description: "Testing", qty: 1, rate: 680 }];
const CLIENT = { name: "Marosia Maison Enterprise", attention: "Puan Aisyah", email: "hello@marosia.my", address: "20, Jalan Setia Villa 2", postcode: "63000", city: "Cyberjaya", state: "Selangor" };
const SETTINGS = billingSettings({ company: { name: "WS Regulab Solutions", reg_no: "202603005218 (MA0341349-M)", email: "info@kkmhalalconsultant.com", signatory: "Wan" },
  bank: { name: "Public Bank Berhad", account_name: "WS Regulab Solutions", account_no: "3246551604" } });

t("totals: cents are exact, discount comes off before tax, tax on the discounted figure", () => {
  const a = calcTotals(ITEMS);
  assert.deepEqual([a.subtotal, a.tax, a.total], [2000, 0, 2000]);
  const b = calcTotals(ITEMS, { tax_rate: 8, discount: 200 });
  assert.deepEqual([b.subtotal, b.discount, b.taxable, b.tax, b.total], [2000, 200, 1800, 144, 1944]);
  const c = calcTotals([{ qty: 3, rate: 0.1 }, { qty: 1, rate: 0.2 }]);
  assert.equal(c.total, 0.5);                                   // 0.30000000000000004 + 0.2 in floating point
  assert.equal(calcTotals(ITEMS, { discount: 99999 }).discount, 2000);   // never below zero
  assert.equal(money(1440), "1,440.00"); assert.equal(money(0.5, { currency: "MYR" }), "MYR 0.50");
});

t("dates: dd/mm/yyyy, calendar arithmetic that no time zone can move", () => {
  assert.equal(fmtDate("2026-06-21"), "21/06/2026");
  assert.equal(addDays("2026-06-21", 30), "2026-07-21");
  assert.equal(addDays("2026-12-31", 1), "2027-01-01");
  assert.equal(daysBetween("2026-09-30", "2026-10-07"), 7);
});

t("status: overdue and expired are derived from the date, nothing else changes", () => {
  const inv = { kind: "invoice", status: "sent", due_date: "2026-10-01" };
  assert.equal(effectiveStatus(inv, "2026-10-07"), "overdue");
  assert.equal(effectiveStatus(inv, "2026-10-01"), "sent");                 // due today is not late
  assert.equal(effectiveStatus({ ...inv, status: "paid" }, "2026-10-07"), "paid");
  assert.equal(effectiveStatus({ kind: "quotation", status: "viewed", due_date: "2026-10-01" }, "2026-10-07"), "expired");
  assert.equal(effectiveStatus({ kind: "receipt", status: "sent" }, "2026-10-07"), "sent");
  assert.equal(effectiveStatus({ kind: "invoice", status: "draft", due_date: "2020-01-01" }, "2026-10-07"), "draft");
});

t("numbering: prefix-year-NNN continues from the counter, and starts at 001 for a new year", () => {
  const counters = [{ prefix: "QT", year: 2026, last: 9 }, { prefix: "INV", year: 2026, last: 14 }];
  assert.equal(numberPreview("quotation", counters, SETTINGS, 2026), "QT-2026-010");
  assert.equal(numberPreview("invoice", counters, SETTINGS, 2026), "INV-2026-015");
  assert.equal(numberPreview("receipt", counters, SETTINGS, 2026), "RPT-2026-001");
  assert.equal(numberPreview("quotation", counters, SETTINGS, 2027), "QT-2027-001");
});

t("reminders: the latest due offset goes, earlier ones are marked with it, nothing for an invoice never e-mailed", () => {
  const inv = { kind: "invoice", status: "sent", due_date: "2026-09-30", reminders: { sent: [] } };
  assert.equal(nextReminder(inv, [-3, 1, 7, 14], "2026-09-26"), null);
  assert.equal(nextReminder(inv, [-3, 1, 7, 14], "2026-09-27"), -3);
  assert.equal(nextReminder(inv, [-3, 1, 7, 14], "2026-10-08"), 7);      // -3 and 1 were missed: one e-mail, for 7
  const after = afterReminder(inv, 7, [-3, 1, 7, 14]);
  assert.deepEqual(after.sent, [-3, 1, 7]);
  assert.equal(nextReminder({ ...inv, reminders: after }, [-3, 1, 7, 14], "2026-10-13"), null);
  assert.equal(nextReminder({ ...inv, reminders: after }, [-3, 1, 7, 14], "2026-10-14"), 14);
  assert.equal(nextReminder({ ...inv, status: "issued" }, [-3, 1, 7, 14], "2026-10-08"), null);
  assert.equal(nextReminder({ ...inv, status: "paid" }, [-3, 1, 7, 14], "2026-10-08"), null);
});

t("validation names what is missing, in the asked language", () => {
  const p = validateDoc({ kind: "invoice", client: {}, items: [{ description: "", qty: 0, rate: "x" }], issue_date: "2026-10-07", due_date: "2026-10-01" }, "en");
  assert.ok(p.some((x) => /client/.test(x)) && p.some((x) => /description/.test(x)) && p.some((x) => /quantity/.test(x)) && p.some((x) => /rate/.test(x)) && p.some((x) => /before the issue/.test(x)));
  assert.deepEqual(validateDoc({ kind: "quotation", client: CLIENT, items: ITEMS }, "bm"), []);
  assert.ok(validateDoc({ kind: "receipt", client: CLIENT, items: ITEMS, payment: {} }, "bm")[0].includes("tarikh bayaran"));
});

t("the dashboard: outstanding, overdue, paid this month, open quotations, win rate, aging", () => {
  const docs = [
    { kind: "invoice", status: "sent", due_date: "2026-09-20", total: 1000 },          // 17 days late → d30
    { kind: "invoice", status: "viewed", due_date: "2026-07-01", total: 500 },         // 98 days late → older
    { kind: "invoice", status: "issued", due_date: "2026-11-01", total: 300 },         // not yet due
    { kind: "invoice", status: "paid", paid_at: "2026-10-02T04:00:00Z", total: 800 },
    { kind: "invoice", status: "paid", paid_at: "2026-09-02T04:00:00Z", total: 999 },  // last month
    { kind: "quotation", status: "sent", due_date: "2026-10-30", total: 2000 },
    { kind: "quotation", status: "converted", total: 1 }, { kind: "quotation", status: "declined", total: 1 }, { kind: "quotation", status: "accepted", total: 1 },
    { kind: "receipt", status: "issued", total: 800 },
  ];
  const s = summary(docs, "2026-10-07");
  assert.deepEqual([s.outstanding, s.outstandingCount, s.overdue, s.overdueCount, s.paidMonth, s.paidMonthCount, s.openQuotes, s.openQuotesCount, s.winRate],
    [1800, 3, 1500, 2, 800, 1, 2000, 1, 67]);
  assert.deepEqual(s.aging, { current: 300, d30: 1000, d60: 0, d90: 0, older: 500 });
});

t("a project's money: quoted, invoiced, paid, outstanding, from its documents", () => {
  const docs = [
    { project_id: "p1", kind: "quotation", status: "converted", total: 2000 }, { project_id: "p1", kind: "quotation", status: "declined", total: 50 },
    { project_id: "p1", kind: "invoice", status: "paid", total: 1200 }, { project_id: "p1", kind: "invoice", status: "sent", due_date: "2026-09-01", total: 800 },
    { project_id: "p1", kind: "invoice", status: "void", total: 999 }, { project_id: "p2", kind: "invoice", status: "sent", total: 5 },
  ];
  assert.deepEqual(projectSummary("p1", docs, "2026-10-07"), { quoted: 2050, invoiced: 2000, paid: 1200, outstanding: 800, overdue: 800, count: 4 });
});

t("conversions carry the lines and the client, with fresh dates and a parent", () => {
  const q = { id: "q1", kind: "quotation", number: "QT-2026-010", client_id: "c1", project_id: "p1", client: CLIENT, items: ITEMS, ...calcTotals(ITEMS), lang: "en" };
  const inv = invoiceFromQuotation(q, SETTINGS, "2026-10-07");
  assert.deepEqual([inv.kind, inv.status, inv.parent_id, inv.reference, inv.issue_date, inv.due_date, inv.total, inv.lang, inv.project_id],
    ["invoice", "draft", "q1", "QT-2026-010", "2026-10-07", "2026-11-06", 2000, "en", "p1"]);
  const r = receiptFromInvoice({ ...inv, id: "i1", number: "INV-2026-015" }, { method: "DuitNow", date: "2026-10-20", reference: "88213" }, SETTINGS, "2026-10-21");
  assert.deepEqual([r.kind, r.parent_id, r.reference, r.issue_date, r.due_date, r.payment.method, r.project_id], ["receipt", "i1", "INV-2026-015", "2026-10-20", null, "DuitNow", "p1"]);
  assert.deepEqual(clientSnapshot({ name: " A ", email: "", reg_no: "1", extra: "x" }), { name: "A", reg_no: "1" });
});

t("e-mail: the right words for each kind and action, the link, the bank line, no HTML in the text copy", () => {
  const doc = { kind: "invoice", number: "INV-2026-015", total: 1320, currency: "MYR", due_date: "2026-11-06", client: CLIENT, lang: "en" };
  const e = emailFor({ doc, settings: SETTINGS, link: "https://x/#bil/abc" });
  assert.equal(e.subject, "Invoice INV-2026-015 from WS Regulab Solutions");
  assert.ok(e.html.includes("3246551604") && e.html.includes('href="https://x/#bil/abc"') && e.html.includes("Dear Puan Aisyah"));
  assert.ok(!/<[^>]+>/.test(e.text) && e.text.includes("MYR 1,320.00"));
  const bm = emailFor({ doc: { ...doc, lang: "bm", kind: "quotation", number: "QT-2026-010" }, settings: SETTINGS });
  assert.ok(bm.subject.startsWith("Sebut harga QT-2026-010 daripada") && bm.html.includes("sah sehingga"));
  const r = emailFor({ doc: { ...doc, due_date: "2026-09-30" }, action: "reminder", settings: SETTINGS });
  assert.ok(/overdue/.test(r.subject) && r.html.includes("remains unpaid"));
  assert.equal(publicLink("abc", "https://site.my/"), "https://site.my/#bil/abc");
  assert.equal(fileName({ number: "INV-2026-015", client: { name: "Marosia Maison Enterprise" } }), "INV-2026-015-Marosia-Maison-Enterprise.pdf");
});

t("the paper: labels per kind, TAX INVOICE only with an SST number, the receipt names its invoice and payment, stamps", () => {
  const base = { number: "INV-2026-015", status: "sent", client: CLIENT, items: ITEMS, ...calcTotals(ITEMS), currency: "MYR", issue_date: "2026-10-07", due_date: "2026-11-06", lang: "en" };
  const inv = documentHtml({ ...base, kind: "invoice" }, SETTINGS);
  assert.ok(inv.includes(">INVOICE<") && !inv.includes("TAX INVOICE") && inv.includes("DUE DATE") && inv.includes("AMOUNT DUE") && inv.includes("3246551604") && inv.includes("BILL TO"));
  const taxed = documentHtml({ ...base, kind: "invoice" }, billingSettings({ ...SETTINGS, company: { ...SETTINGS.company, sst_no: "W10-1808-32000123" } }));
  assert.ok(taxed.includes("TAX INVOICE") && taxed.includes("SST No."));
  const q = documentHtml({ ...base, kind: "quotation", number: "QT-2026-010" }, SETTINGS);
  assert.ok(q.includes("VALID UNTIL") && q.includes("QUOTATION TOTAL") && q.includes("ACCEPTED AND AGREED") && !q.includes("DUE DATE") && !q.includes("3246551604"));
  const r = documentHtml({ ...base, kind: "receipt", number: "RPT-2026-017", parent_number: "INV-2026-015", payment: { method: "DuitNow", date: "2026-10-20", reference: "88213" }, lang: "bm" }, SETTINGS);
  assert.ok(r.includes("RESIT") && r.includes("BAYARAN DITERIMA") && r.includes("INV-2026-015") && r.includes("DuitNow") && r.includes("JUMLAH DIBAYAR") && r.includes("DITERIMA DARIPADA"));
  assert.ok(documentHtml({ ...base, kind: "invoice", status: "paid" }, SETTINGS).includes('class="stamp paid"'));
  assert.ok(documentHtml({ ...base, kind: "invoice", status: "void" }, SETTINGS).includes('class="stamp void"'));
  assert.ok(documentHtml({ ...base, kind: "invoice", number: "", status: "draft" }, SETTINGS).includes('class="stamp draft"'));
  assert.ok(documentHtml({ ...base, kind: "invoice", project: "Notifikasi 3 produk" }, SETTINGS).includes("Notifikasi 3 produk"));
  assert.ok(inv.includes("@page { size: A4"));                                 // never Letter again
  const esc = documentHtml({ ...base, kind: "invoice", client: { ...CLIENT, name: "<script>alert(1)</script>" } }, SETTINGS);
  assert.ok(!esc.includes("<script>alert") && esc.includes("&lt;script&gt;"));
  const two = pagesHtml([{ ...base, kind: "invoice" }, { ...base, kind: "quotation", number: "QT-2026-010" }], SETTINGS);
  assert.equal((two.match(/class="page"/g) || []).length, 2);
});

console.log(`billing: ${n} cases ok`);
