/* Bil (Wan, 7 Oct 2026): quotations, invoices and receipts. The arithmetic and the rules, with no React and no Supabase in
   them, so the page, the worker's Chrome (served as a module next to billingDoc.js) and `node billing.test.mjs` all run the
   SAME file. Money is kept in cents inside a calculation and rounded once per line, the way an accountant checks a total.

   Statuses stored on a document (supabase/028_billing.sql):
     quotation  draft → issued → sent → viewed → accepted | declined | expired | converted
     invoice    draft → issued → sent → viewed → paid | void
     receipt    issued → sent → viewed
   "overdue" and a quotation's "expired" are DERIVED from the due date here (effectiveStatus), never written by the page,
   so a date that passes while nobody has Semasa open still reads right. */

export const KINDS = ["quotation", "invoice", "receipt"];
export const OPEN = ["issued", "sent", "viewed"];                  // issued but not yet settled, one way or the other
export const DEFAULT_OFFSETS = [-3, 1, 7, 14];                      // reminder days relative to the due date

export const KIND_LABEL = {
  quotation: { bm: "Sebut harga", en: "Quotation" },
  invoice: { bm: "Invois", en: "Invoice" },
  receipt: { bm: "Resit", en: "Receipt" },
};
export const STATUS_LABEL = {
  draft: { bm: "Draf", en: "Draft" }, issued: { bm: "Dikeluarkan", en: "Issued" }, sent: { bm: "Dihantar", en: "Sent" },
  viewed: { bm: "Dibuka", en: "Viewed" }, accepted: { bm: "Diterima", en: "Accepted" }, declined: { bm: "Ditolak", en: "Declined" },
  expired: { bm: "Luput", en: "Expired" }, converted: { bm: "Jadi invois", en: "Invoiced" }, paid: { bm: "Dibayar", en: "Paid" },
  void: { bm: "Dibatalkan", en: "Void" }, overdue: { bm: "Lewat", en: "Overdue" },
};
export const kindLabel = (kind, lang = "bm") => (KIND_LABEL[kind] || KIND_LABEL.invoice)[lang === "en" ? "en" : "bm"];
export const statusLabel = (status, lang = "bm") => (STATUS_LABEL[status] || { bm: status, en: status })[lang === "en" ? "en" : "bm"];

export const r2 = (n) => Math.round((Number(n) || 0) * 100 + Number.EPSILON * 100) / 100;

/** "1,440.00" (no currency), the way the figure sits in a column. */
export function money(n, { currency = "" } = {}) {
  const v = r2(n);
  const s = new Intl.NumberFormat("en-MY", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(v);
  return currency ? `${currency} ${s}` : s;
}

/** One line: qty × rate, rounded to the cent. */
export const lineAmount = (it) => r2((Number(it?.qty) || 0) * (Number(it?.rate) || 0));

/** Subtotal, discount (an amount, never a percentage), tax on the discounted figure, total. */
export function calcTotals(items, { tax_rate = 0, discount = 0 } = {}) {
  const subtotal = r2((items || []).reduce((s, it) => s + lineAmount(it), 0));
  const disc = Math.min(subtotal, Math.max(0, r2(discount)));
  const taxable = r2(subtotal - disc);
  const rate = Math.max(0, Number(tax_rate) || 0);
  const tax = r2(taxable * rate / 100);
  return { subtotal, discount: disc, taxable, tax_rate: rate, tax, total: r2(taxable + tax) };
}

/** YYYY-MM-DD of a Date in Malaysia (the page's dates are civil dates, never instants). */
export function isoDate(d = new Date()) {
  if (typeof d === "string") return d.slice(0, 10);
  const p = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kuala_Lumpur", year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(d);
  const g = (k) => p.find((x) => x.type === k).value;
  return `${g("year")}-${g("month")}-${g("day")}`;
}
/** "21/06/2026" from "2026-06-21": the form on Wan's own documents. */
export const fmtDate = (iso) => (iso && /^\d{4}-\d{2}-\d{2}/.test(iso) ? `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}` : iso || "");
/** ISO date plus n days (calendar arithmetic on the string; no time zone can move it). */
export function addDays(iso, n) {
  const [y, m, d] = String(iso).slice(0, 10).split("-").map(Number);
  const t = new Date(Date.UTC(y, m - 1, d + Number(n || 0)));
  return t.toISOString().slice(0, 10);
}
/** Whole days from a to b (b − a), both ISO dates. */
export const daysBetween = (a, b) => Math.round((Date.UTC(...splitIso(b)) - Date.UTC(...splitIso(a))) / 86400000);
const splitIso = (iso) => { const [y, m, d] = String(iso).slice(0, 10).split("-").map(Number); return [y, m - 1, d]; };

/** What the document IS today: the stored status, or the derived overdue/expired once its date has passed. */
export function effectiveStatus(doc, today = isoDate()) {
  const s = doc?.status || "draft";
  if (!OPEN.includes(s) || !doc?.due_date) return s;
  const late = String(doc.due_date).slice(0, 10) < today;
  if (!late) return s;
  if (doc.kind === "invoice") return "overdue";
  if (doc.kind === "quotation") return "expired";
  return s;
}
export const isOpenInvoice = (d, today) => d.kind === "invoice" && (OPEN.includes(d.status) || effectiveStatus(d, today) === "overdue");

/** The next document number, as the database will allocate it (semasa_billing_issue): PREFIX-YEAR-NNN. */
export function numberPreview(kind, counters, settings, year = Number(isoDate().slice(0, 4))) {
  const prefix = settings?.prefix?.[kind] || { quotation: "QT", invoice: "INV", receipt: "RPT" }[kind];
  const row = (counters || []).find((c) => c.prefix === prefix && Number(c.year) === Number(year));
  return `${prefix}-${year}-${String((row ? Number(row.last) : 0) + 1).padStart(3, "0")}`;
}

/** The client's details as the document will carry them (a copy: editing the client later never rewrites an issued paper). */
export function clientSnapshot(c) {
  if (!c) return {};
  const keep = ["name", "reg_no", "attention", "email", "phone", "address", "postcode", "city", "state", "country"];
  return Object.fromEntries(keep.map((k) => [k, String(c[k] ?? "").trim()]).filter(([, v]) => v));
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
export const validEmail = (s) => EMAIL_RE.test(String(s || "").trim());

/** What stops a draft being issued, in the person's words. [] = ready. */
export function validateDoc(doc, lang = "bm") {
  const en = lang === "en";
  const out = [];
  if (!KINDS.includes(doc?.kind)) out.push(en ? "Unknown document kind." : "Jenis dokumen tidak dikenali.");
  if (!doc?.client?.name) out.push(en ? "Choose or add the client." : "Pilih atau tambah pelanggan.");
  const items = Array.isArray(doc?.items) ? doc.items : [];
  if (!items.length) out.push(en ? "Add at least one line." : "Tambah sekurang-kurangnya satu baris.");
  items.forEach((it, i) => {
    if (!String(it.description || "").trim()) out.push(en ? `Line ${i + 1} has no description.` : `Baris ${i + 1} tiada keterangan.`);
    if (!(Number(it.qty) > 0)) out.push(en ? `Line ${i + 1}: quantity must be above 0.` : `Baris ${i + 1}: kuantiti mesti lebih daripada 0.`);
    if (Number(it.rate) < 0 || Number.isNaN(Number(it.rate))) out.push(en ? `Line ${i + 1}: rate is not a number.` : `Baris ${i + 1}: kadar bukan nombor.`);
  });
  if (doc?.issue_date && doc?.due_date && doc.due_date < doc.issue_date) {
    out.push(en ? "The due date is before the issue date." : "Tarikh akhir lebih awal daripada tarikh keluar.");
  }
  if (doc?.kind === "receipt" && !doc?.payment?.date) out.push(en ? "A receipt needs the payment date." : "Resit perlukan tarikh bayaran.");
  return out;
}

/* ---- reminders -------------------------------------------------------------------------------------------------------------
   Offsets are days relative to the due date: -3 = three days before, 1 = the day after, 14 = two weeks late. A reminder is
   due when today has reached due + offset and that offset is not in doc.reminders.sent. If several are due at once (the
   worker was down a week), ONE e-mail goes, for the latest offset, and every earlier one is marked sent with it. */
export function nextReminder(doc, offsets = DEFAULT_OFFSETS, today = isoDate()) {
  if (!doc || doc.kind !== "invoice" || !doc.due_date) return null;
  if (!["sent", "viewed"].includes(doc.status)) return null;            // never e-mailed: nothing to remind about
  const sent = new Set((doc.reminders?.sent || []).map(Number));
  const due = [...new Set((offsets || []).map(Number).filter(Number.isFinite))].sort((a, b) => a - b)
    .filter((o) => !sent.has(o) && today >= addDays(doc.due_date, o));
  return due.length ? due[due.length - 1] : null;
}
export function afterReminder(doc, offset, offsets = DEFAULT_OFFSETS) {
  const sent = new Set((doc.reminders?.sent || []).map(Number));
  for (const o of offsets.map(Number)) if (o <= offset) sent.add(o);
  return { ...(doc.reminders || {}), sent: [...sent].sort((a, b) => a - b), last_at: new Date().toISOString() };
}

/* ---- the dashboard ------------------------------------------------------------------------------------------------------- */
export function summary(docs, today = isoDate()) {
  const month = today.slice(0, 7);
  const inv = (docs || []).filter((d) => d.kind === "invoice");
  const open = inv.filter((d) => isOpenInvoice(d, today));
  const overdue = open.filter((d) => effectiveStatus(d, today) === "overdue");
  const sum = (xs) => r2(xs.reduce((s, d) => s + (Number(d.total) || 0), 0));
  const paid = inv.filter((d) => d.status === "paid" && String(d.paid_at || "").slice(0, 7) === month);
  const quotes = (docs || []).filter((d) => d.kind === "quotation");
  const openQ = quotes.filter((d) => OPEN.includes(effectiveStatus(d, today)));
  const won = quotes.filter((d) => ["accepted", "converted"].includes(d.status)).length;
  const lost = quotes.filter((d) => ["declined", "expired"].includes(effectiveStatus(d, today))).length;
  const aging = { current: 0, d30: 0, d60: 0, d90: 0, older: 0 };
  for (const d of open) {
    const late = daysBetween(d.due_date, today);
    const k = late <= 0 ? "current" : late <= 30 ? "d30" : late <= 60 ? "d60" : late <= 90 ? "d90" : "older";
    aging[k] = r2(aging[k] + (Number(d.total) || 0));
  }
  return {
    outstanding: sum(open), outstandingCount: open.length, overdue: sum(overdue), overdueCount: overdue.length,
    paidMonth: sum(paid), paidMonthCount: paid.length, openQuotes: sum(openQ), openQuotesCount: openQ.length,
    winRate: won + lost ? Math.round((100 * won) / (won + lost)) : null, aging,
  };
}

/** A project's money, from the documents that name it: quoted (every quotation but voids), invoiced (every invoice but
    voids), paid, outstanding, overdue. A receipt is never counted (it is the invoice's payment, already in `paid`). */
export function projectSummary(projectId, docs, today = isoDate()) {
  const mine = (docs || []).filter((d) => d.project_id === projectId && d.status !== "void");
  const sum = (xs) => r2(xs.reduce((s, d) => s + (Number(d.total) || 0), 0));
  const inv = mine.filter((d) => d.kind === "invoice");
  const open = inv.filter((d) => isOpenInvoice(d, today));
  return { quoted: sum(mine.filter((d) => d.kind === "quotation")), invoiced: sum(inv), paid: sum(inv.filter((d) => d.status === "paid")),
    outstanding: sum(open), overdue: sum(open.filter((d) => effectiveStatus(d, today) === "overdue")), count: mine.length };
}
export const PROJECT_STATUS = {
  lead: { bm: "Prospek", en: "Lead" }, active: { bm: "Aktif", en: "Active" }, on_hold: { bm: "Ditangguh", en: "On hold" },
  done: { bm: "Selesai", en: "Done" }, cancelled: { bm: "Dibatalkan", en: "Cancelled" },
};

/* ---- e-mail --------------------------------------------------------------------------------------------------------------- */
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

/** The address a document's e-mail goes to: the snapshot on the paper first, then the client record. */
export const emailOf = (doc, client) => String(doc?.client?.email || client?.email || "").trim();

/** Subject and body for a send or a reminder, in the document's language. The PDF is attached by the worker; the link
    opens the live view (status, bank details, download). No URL of ours but that one; no call to action beyond paying. */
export function emailFor({ doc, action = "send", settings = {}, link = "", lang }) {
  const L = (lang || doc?.lang) === "en" ? "en" : "bm";
  const co = settings.company || {};
  const bank = settings.bank || {};
  const kind = kindLabel(doc.kind, L);
  const who = doc.client?.attention || doc.client?.name || "";
  const total = money(doc.total, { currency: doc.currency || "MYR" });
  const due = fmtDate(doc.due_date);
  const late = doc.due_date ? daysBetween(doc.due_date, isoDate()) : 0;
  const T = L === "en" ? {
    hi: `Dear ${who},`,
    send: {
      quotation: [`Quotation ${doc.number} from ${co.name || "WS Regulab Solutions"}`,
        `Please find attached our quotation <b>${esc(doc.number)}</b> for <b>${esc(total)}</b>, valid until <b>${esc(due)}</b>.`,
        "Reply to this e-mail to accept, or let us know if anything should change."],
      invoice: [`Invoice ${doc.number} from ${co.name || "WS Regulab Solutions"}`,
        `Please find attached invoice <b>${esc(doc.number)}</b> for <b>${esc(total)}</b>, due on <b>${esc(due)}</b>.`,
        bank.account_no ? `Payment by bank transfer to ${esc(bank.name)} · ${esc(bank.account_name)} · <b>${esc(bank.account_no)}</b>, quoting the invoice number.` : ""],
      receipt: [`Receipt ${doc.number} from ${co.name || "WS Regulab Solutions"}`,
        `Thank you for your payment. Receipt <b>${esc(doc.number)}</b> for <b>${esc(total)}</b> is attached.`, ""],
    },
    reminder: [late > 0 ? `Reminder: invoice ${doc.number} is ${late} day${late === 1 ? "" : "s"} overdue` : `Reminder: invoice ${doc.number} is due on ${due}`,
      late > 0 ? `A gentle reminder that invoice <b>${esc(doc.number)}</b> for <b>${esc(total)}</b> was due on <b>${esc(due)}</b> and remains unpaid.`
        : `A gentle reminder that invoice <b>${esc(doc.number)}</b> for <b>${esc(total)}</b> is due on <b>${esc(due)}</b>.`,
      bank.account_no ? `Bank transfer: ${esc(bank.name)} · ${esc(bank.account_name)} · <b>${esc(bank.account_no)}</b>. If payment has already been made, please ignore this message.` : "If payment has already been made, please ignore this message."],
    view: "View online", regards: "Kind regards,",
  } : {
    hi: `Salam sejahtera ${who},`,
    send: {
      quotation: [`Sebut harga ${doc.number} daripada ${co.name || "WS Regulab Solutions"}`,
        `Dilampirkan sebut harga <b>${esc(doc.number)}</b> berjumlah <b>${esc(total)}</b>, sah sehingga <b>${esc(due)}</b>.`,
        "Balas e-mel ini untuk menerima, atau maklumkan jika ada yang perlu diubah."],
      invoice: [`Invois ${doc.number} daripada ${co.name || "WS Regulab Solutions"}`,
        `Dilampirkan invois <b>${esc(doc.number)}</b> berjumlah <b>${esc(total)}</b>, perlu dijelaskan sebelum <b>${esc(due)}</b>.`,
        bank.account_no ? `Bayaran melalui pindahan bank ke ${esc(bank.name)} · ${esc(bank.account_name)} · <b>${esc(bank.account_no)}</b>, dengan nombor invois sebagai rujukan.` : ""],
      receipt: [`Resit ${doc.number} daripada ${co.name || "WS Regulab Solutions"}`,
        `Terima kasih atas bayaran anda. Resit <b>${esc(doc.number)}</b> berjumlah <b>${esc(total)}</b> dilampirkan.`, ""],
    },
    reminder: [late > 0 ? `Peringatan: invois ${doc.number} lewat ${late} hari` : `Peringatan: invois ${doc.number} perlu dijelaskan sebelum ${due}`,
      late > 0 ? `Peringatan mesra bahawa invois <b>${esc(doc.number)}</b> berjumlah <b>${esc(total)}</b> sepatutnya dijelaskan pada <b>${esc(due)}</b> dan masih belum diterima.`
        : `Peringatan mesra bahawa invois <b>${esc(doc.number)}</b> berjumlah <b>${esc(total)}</b> perlu dijelaskan sebelum <b>${esc(due)}</b>.`,
      bank.account_no ? `Pindahan bank: ${esc(bank.name)} · ${esc(bank.account_name)} · <b>${esc(bank.account_no)}</b>. Jika bayaran sudah dibuat, abaikan mesej ini.` : "Jika bayaran sudah dibuat, abaikan mesej ini."],
    view: "Lihat dalam talian", regards: "Sekian, terima kasih.",
  };
  const [subject, lead, extra] = action === "reminder" ? T.reminder : (T.send[doc.kind] || T.send.invoice);
  const paras = [T.hi, lead, extra, link ? `<a href="${esc(link)}">${T.view}</a>` : "", T.regards,
    `<b>${esc(co.signatory || "")}</b><br>${esc(co.name || "")}${co.reg_no ? ` · ${esc(co.reg_no)}` : ""}<br>${esc(co.email || "")}${co.phone ? ` · ${esc(co.phone)}` : ""}`]
    .filter(Boolean);
  const html = `<div style="font:14px/1.5 -apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#10222f">${paras.map((p) => `<p>${p}</p>`).join("")}</div>`;
  const text = paras.map((p) => p.replace(/<br>/g, "\n").replace(/<[^>]+>/g, "")).join("\n\n");
  return { subject, html, text, kind };
}

/** The "view online" address for a token, on the site the page is served from (or the one the worker is told). */
export const publicLink = (token, site = "") => `${String(site || "").replace(/\/+$/, "")}/#bil/${token}`;

/** The file name a PDF is saved as: QT-2026-010-Marosia-Maison.pdf. */
export function fileName(doc) {
  const who = String(doc?.client?.name || "").replace(/[^\p{L}\p{N}]+/gu, "-").replace(/^-|-$/g, "").slice(0, 40);
  return `${doc?.number || "draft"}${who ? "-" + who : ""}.pdf`;
}

/** The invoice a quotation becomes: same client, lines, reference and language; a fresh draft with its own dates. */
export function invoiceFromQuotation(q, settings = {}, today = isoDate()) {
  return {
    kind: "invoice", status: "draft", client_id: q.client_id || null, project_id: q.project_id || null, client: q.client || {}, items: q.items || [],
    currency: q.currency || "MYR", tax_rate: q.tax_rate || 0, discount: q.discount || 0, subtotal: q.subtotal, tax: q.tax, total: q.total,
    issue_date: today, due_date: addDays(today, Number(settings?.days?.invoice_due) || 30),
    terms: settings?.terms?.invoice || "", notes: q.notes || "", reference: q.reference || q.number || "", parent_id: q.id, lang: q.lang || "bm",
  };
}

/** The receipt an invoice becomes once paid: its lines and total, the payment's method, date and reference. */
export function receiptFromInvoice(inv, payment, settings = {}, today = isoDate()) {
  return {
    kind: "receipt", status: "draft", client_id: inv.client_id || null, project_id: inv.project_id || null, client: inv.client || {}, items: inv.items || [],
    currency: inv.currency || "MYR", tax_rate: inv.tax_rate || 0, discount: inv.discount || 0, subtotal: inv.subtotal, tax: inv.tax, total: inv.total,
    issue_date: payment?.date || today, due_date: null, terms: settings?.terms?.receipt || "", notes: "", reference: inv.number || "",
    parent_id: inv.id, lang: inv.lang || "bm",
    payment: { method: payment?.method || "", date: payment?.date || today, reference: payment?.reference || "" },
  };
}

/** The default settings row (supabase/028 writes the same shape); a missing key reads from here. */
export const DEFAULT_BILLING = {
  lang: "en",      // the language a new client and a new paper start in (Wan, 7 Oct 2026: "make the receipt, invoice and quotation in english")
  company: { name: "WS Regulab Solutions", reg_no: "", tagline: "", footer: "", website: "", email: "", phone: "", address: "", sst_no: "", tin: "", signatory: "" },
  bank: { name: "", account_name: "", account_no: "" },
  prefix: { quotation: "QT", invoice: "INV", receipt: "RPT" },
  days: { quotation_valid: 30, invoice_due: 30 },
  tax_rate: 0,
  terms: { quotation: "", invoice: "", receipt: "" },
  email: { auto_send: false, auto_reminders: true, reminder_days: DEFAULT_OFFSETS, cc_self: true, reply_to: "" },
};
export function billingSettings(raw) {
  const b = raw && typeof raw === "object" ? raw : {};
  const merge = (k) => ({ ...DEFAULT_BILLING[k], ...(b[k] && typeof b[k] === "object" ? b[k] : {}) });
  return { company: merge("company"), bank: merge("bank"), prefix: merge("prefix"), days: merge("days"), terms: merge("terms"),
    email: merge("email"), tax_rate: Number(b.tax_rate) || 0, lang: b.lang === "bm" ? "bm" : "en" };
}
