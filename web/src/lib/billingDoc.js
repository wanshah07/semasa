/* The A4 paper: one HTML template for a quotation, an invoice and a receipt, drawn in the page (preview, print, "view
   online") and in the worker's Chrome (the PDF that is attached to the e-mail), so the two can never differ.
   Pure: a document, the billing settings and a few options in; one HTML string out. No React, no fetch.

   What it corrects from Wan's hand-made papers (7 Oct 2026): one page size (A4, never Letter); a quotation says "Valid
   until" (not "Due date") and "Quotation total" (not "Amount due"); an invoice is a TAX INVOICE only when the company
   carries an SST number, otherwise an INVOICE; a receipt names the invoice it settles and how, when and under what
   reference it was paid; the recipient block carries the contact, e-mail and phone; the items table takes the height it
   needs and the totals follow it, instead of a half-page gap; a paid invoice is stamped PAID, a void one VOID, a draft
   DRAFT; the ws.regulab logo and tagline stay where Wan put them. */
import { calcTotals, fmtDate, kindLabel, lineAmount, money } from "./billing.js";

const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const nl = (s) => esc(s).replace(/\n/g, "<br>");

const WORDS = {
  bm: {
    quotation: "SEBUT HARGA", invoice: "INVOIS", tax_invoice: "INVOIS CUKAI", receipt: "RESIT", issuer: "PENGELUAR", recipient: "PENERIMA",
    bill_to: "DIBIL KEPADA", received_from: "DITERIMA DARIPADA", issue_date: "TARIKH KELUAR", due_date: "TARIKH AKHIR", valid_until: "SAH SEHINGGA",
    payment_date: "TARIKH BAYARAN", description: "KETERANGAN PERKHIDMATAN", qty: "KUANTITI", rate: "KADAR", amount: "JUMLAH", subtotal: "SUBJUMLAH",
    discount: "DISKAUN", tax: "CUKAI", total_quote: "JUMLAH SEBUT HARGA", amount_due: "JUMLAH PERLU DIBAYAR", amount_paid: "JUMLAH DIBAYAR",
    terms: "TERMA & SYARAT", notes: "NOTA", payment_method: "KAEDAH BAYARAN", bank: "NAMA BANK", acct_name: "NAMA AKAUN", acct_no: "NOMBOR AKAUN",
    accept: "DITERIMA DAN DIPERSETUJUI", sign: "Tandatangan & cop syarikat", name_date: "Nama · Tarikh", prepared: "Disediakan oleh",
    payment_received: "BAYARAN DITERIMA", for_invoice: "Untuk invois", method: "Kaedah", reference: "Rujukan", your_ref: "RUJUKAN ANDA",
    attn: "U.P.", project: "Projek", paid: "DIBAYAR", void: "DIBATALKAN", draft: "DRAF", paid_on: "Dibayar pada", sst: "No. SST", tin: "TIN", reg: "No. Pendaftaran",
    page_note: "Dokumen ini dijana oleh sistem dan sah tanpa tandatangan.", scan: "Imbas untuk melihat dalam talian",
  },
  en: {
    quotation: "QUOTATION", invoice: "INVOICE", tax_invoice: "TAX INVOICE", receipt: "RECEIPT", issuer: "ISSUER", recipient: "RECIPIENT",
    bill_to: "BILL TO", received_from: "RECEIVED FROM", issue_date: "ISSUE DATE", due_date: "DUE DATE", valid_until: "VALID UNTIL",
    payment_date: "PAYMENT DATE", description: "DESCRIPTION OF SERVICES", qty: "QTY", rate: "RATE", amount: "AMOUNT", subtotal: "SUBTOTAL",
    discount: "DISCOUNT", tax: "TAX", total_quote: "QUOTATION TOTAL", amount_due: "AMOUNT DUE", amount_paid: "AMOUNT PAID",
    terms: "TERMS & CONDITIONS", notes: "NOTES", payment_method: "PAYMENT METHOD", bank: "BANK NAME", acct_name: "ACCOUNT NAME", acct_no: "ACCOUNT NUMBER",
    accept: "ACCEPTED AND AGREED", sign: "Signature & company stamp", name_date: "Name · Date", prepared: "Prepared by",
    payment_received: "PAYMENT RECEIVED", for_invoice: "For invoice", method: "Method", reference: "Reference", your_ref: "YOUR REFERENCE",
    attn: "Attn.", project: "Project", paid: "PAID", void: "VOID", draft: "DRAFT", paid_on: "Paid on", sst: "SST No.", tin: "TIN", reg: "Reg. No.",
    page_note: "This document is system-generated and valid without a signature.", scan: "Scan to view online",
  },
};

export const PAPER = { w: 210, h: 297 };     // mm

/** The colours of Wan's own papers: deep green brand, navy table head, pale green recipient card. */
export const INK = { green: "#0B4D3C", greenDeep: "#083B2E", navy: "#0F1E2E", paper: "#FFFFFF", pale: "#F3FAF7", line: "#D9E6E0",
  text: "#10222F", muted: "#6B7A86", soft: "#F4F7FA" };

function badge(words, status, number) {
  if (!number) return `<div class="stamp draft">${words.draft}</div>`;
  if (status === "paid") return `<div class="stamp paid">${words.paid}</div>`;
  if (status === "void") return `<div class="stamp void">${words.void}</div>`;
  return "";
}

/**
 * @param {object} doc      the document (items, totals, client snapshot, dates, status, payment, parent_number)
 * @param {object} settings billing settings (company, bank, terms); see billing.js billingSettings
 * @param {object} opts     { lang, logoUrl, qr (data URL of the QR code), fontsCss (a URL for @import), link }
 */
export function documentHtml(doc, settings = {}, opts = {}) {
  const lang = (opts.lang || doc?.lang) === "en" ? "en" : "bm";
  const W = WORDS[lang];
  const co = settings.company || {};
  const bank = settings.bank || {};
  const kind = doc?.kind || "invoice";
  const totals = calcTotals(doc?.items || [], { tax_rate: doc?.tax_rate, discount: doc?.discount });
  const cur = doc?.currency || "MYR";
  const c = doc?.client || {};
  const isTax = kind === "invoice" && !!co.sst_no;
  const title = kind === "invoice" ? (isTax ? W.tax_invoice : W.invoice) : W[kind];
  const number = doc?.number || "";
  const status = doc?.status || "draft";
  const parent = doc?.parent_number || (doc?.reference && kind === "receipt" ? doc.reference : "");
  const dateChips = [[W.issue_date, fmtDate(doc?.issue_date)]];
  if (kind === "quotation") dateChips.push([W.valid_until, fmtDate(doc?.due_date)]);
  if (kind === "invoice") dateChips.push([W.due_date, fmtDate(doc?.due_date)]);
  if (kind === "receipt") dateChips.push([W.payment_date, fmtDate(doc?.payment?.date || doc?.issue_date)]);
  if (doc?.reference && kind !== "receipt") dateChips.push([W.your_ref, doc.reference]);
  const recipientLabel = kind === "receipt" ? W.received_from : kind === "invoice" ? W.bill_to : W.recipient;
  const totalLabel = kind === "quotation" ? W.total_quote : kind === "receipt" || status === "paid" ? W.amount_paid : W.amount_due;
  const showTax = totals.tax_rate > 0 || isTax;
  const items = (doc?.items || []).map((it, i) => `
      <tr>
        <td class="n">${i + 1}</td>
        <td class="d"><div class="t">${esc(it.description)}</div>${it.detail ? `<div class="s">${nl(it.detail)}</div>` : ""}</td>
        <td class="q">${esc(it.qty)}${it.unit ? ` <span class="u">${esc(it.unit)}</span>` : ""}</td>
        <td class="r">${money(it.rate)}</td>
        <td class="a">${money(lineAmount(it))}</td>
      </tr>`).join("");
  const addr = [c.address, [c.postcode, c.city].filter(Boolean).join(" ")].filter(Boolean);
  const contact = [c.email, c.phone].filter(Boolean).join(" · ");
  const paidLine = kind === "invoice" && status === "paid" && (doc.payment?.date || doc.paid_at)
    ? `<div class="paidline">${W.paid_on} ${esc(fmtDate(doc.payment?.date || String(doc.paid_at).slice(0, 10)))}${doc.payment?.method ? ` · ${esc(doc.payment.method)}` : ""}${doc.payment?.reference ? ` · ${esc(doc.payment.reference)}` : ""}</div>` : "";

  const leftBlocks = [];
  if (kind === "receipt") {
    leftBlocks.push(`<div class="card">
        <div class="lbl">${W.payment_received}</div>
        <div class="kv"><span>${W.for_invoice}</span><b>${esc(parent || "—")}</b></div>
        <div class="kv"><span>${W.payment_date}</span><b>${esc(fmtDate(doc?.payment?.date || doc?.issue_date))}</b></div>
        <div class="kv"><span>${W.method}</span><b>${esc(doc?.payment?.method || "—")}</b></div>
        ${doc?.payment?.reference ? `<div class="kv"><span>${W.reference}</span><b>${esc(doc.payment.reference)}</b></div>` : ""}
      </div>`);
  }
  if (kind === "invoice" && status !== "paid" && (bank.account_no || bank.name)) {
    leftBlocks.push(`<div class="card">
        <div class="lbl">${W.payment_method}</div>
        <div class="bank"><span>${W.bank}</span><b>${esc(bank.name)}</b></div>
        <div class="bank"><span>${W.acct_name}</span><b>${esc(bank.account_name)}</b></div>
        <div class="bank"><span>${W.acct_no}</span><b class="big">${esc(bank.account_no)}</b></div>
      </div>`);
  }
  if (doc?.terms) leftBlocks.push(`<div class="block"><div class="lbl">${W.terms}</div><div class="small">${nl(doc.terms)}</div></div>`);
  if (doc?.notes) leftBlocks.push(`<div class="block"><div class="lbl">${W.notes}</div><div class="small">${nl(doc.notes)}</div></div>`);
  if (kind === "quotation") {
    leftBlocks.push(`<div class="block accept"><div class="lbl">${W.accept}</div>
        <div class="sig"><div class="line"></div><div class="cap">${W.sign}</div></div>
        <div class="sig"><div class="line"></div><div class="cap">${W.name_date}</div></div></div>`);
  }

  const fonts = opts.fontsCss ? `@import url("${esc(opts.fontsCss)}");` : "";
  const logo = opts.logoUrl ? `<img class="logo" src="${esc(opts.logoUrl)}" alt="${esc(co.name || "")}">` : `<div class="wordmark">${esc(co.name || "")}</div>`;
  const qr = opts.qr ? `<div class="qr"><img src="${esc(opts.qr)}" alt="QR"><div>${W.scan}</div></div>` : "";

  return `<!doctype html><html lang="${lang === "en" ? "en" : "ms"}"><head><meta charset="utf-8"><title>${esc(title)} ${esc(number)}</title>
<style>
${fonts}
@page { size: A4; margin: 0; }
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; background: #e9eef2; }
body { font-family: "Instrument Sans", "Inter", -apple-system, "Segoe UI", Roboto, Arial, sans-serif; color: ${INK.text}; font-size: 10.5pt; line-height: 1.4;
  -webkit-print-color-adjust: exact; print-color-adjust: exact; }
.page { position: relative; width: ${PAPER.w}mm; min-height: ${PAPER.h}mm; margin: 0 auto; background: ${INK.paper}; padding: 14mm 14mm 24mm; display: flex; flex-direction: column; }
@media print { html, body { background: #fff; } .page { margin: 0; box-shadow: none; } }
@media screen { .page { box-shadow: 0 10px 40px rgba(16,34,47,.15); margin: 12px auto; } }
.top { display: flex; align-items: flex-start; justify-content: space-between; gap: 8mm; }
.brand { display: flex; align-items: center; gap: 6mm; }
.logo { height: 9mm; width: auto; display: block; }        /* logo-ink.png: the mark trimmed to its ink (230×35), so 9mm IS 9mm */
.wordmark { font-weight: 800; font-size: 16pt; color: ${INK.green}; letter-spacing: .02em; }
.qr { text-align: center; font-size: 6.5pt; color: ${INK.muted}; }
.qr img { width: 18mm; height: 18mm; display: block; margin: 0 auto 1mm; border: 1px solid ${INK.line}; border-radius: 1.5mm; padding: 1mm; background: #fff; }
.titlebox { background: ${INK.green}; color: #fff; border-radius: 0 0 4mm 4mm; padding: 4mm 7mm 4.5mm; min-width: 62mm; text-align: right; box-shadow: 0 6px 14px rgba(11,77,60,.25); }
.titlebox .k { font-size: 7.5pt; letter-spacing: .22em; opacity: .85; font-weight: 600; }
.titlebox .num { font-size: 20pt; font-weight: 800; letter-spacing: .02em; line-height: 1.1; margin-top: 1mm; }
.rule { height: 1.2mm; background: ${INK.green}; margin: 5mm 0 6mm; border-radius: 1mm; }
.parties { display: grid; grid-template-columns: 1fr 1fr; gap: 8mm; align-items: start; }
.lbl { font-size: 7pt; letter-spacing: .2em; font-weight: 700; color: ${INK.green}; margin-bottom: 1.5mm; }
.issuer .name { font-weight: 800; font-size: 11pt; }
.issuer .reg { color: ${INK.muted}; font-size: 8.5pt; }
.issuer .tag { font-style: italic; color: ${INK.muted}; font-size: 8.5pt; margin-top: .5mm; }
.chips { display: flex; flex-wrap: wrap; gap: 3mm; margin-top: 4mm; }
.chip { background: ${INK.soft}; border: 1px solid ${INK.line}; border-radius: 2.5mm; padding: 2mm 4mm; min-width: 36mm; }
.chip .k { font-size: 6.5pt; letter-spacing: .15em; color: ${INK.muted}; font-weight: 700; }
.chip .v { font-weight: 700; font-size: 10pt; margin-top: .5mm; }
.recipient { background: ${INK.pale}; border: 1px solid ${INK.line}; border-radius: 3mm; padding: 4mm 5mm; }
.recipient .name { font-weight: 800; font-size: 12.5pt; margin-bottom: 1mm; }
.recipient .attn { font-size: 9pt; color: ${INK.text}; }
.recipient .addr { font-size: 9pt; color: ${INK.text}; }
.recipient .state { font-size: 8pt; letter-spacing: .12em; font-weight: 700; color: ${INK.green}; margin-top: 1.5mm; }
.recipient .contact { font-size: 8.5pt; color: ${INK.muted}; margin-top: 1mm; }
table.items { width: 100%; border-collapse: collapse; margin-top: 7mm; }
table.items thead th { background: ${INK.navy}; color: #fff; font-size: 7pt; letter-spacing: .18em; font-weight: 700; text-align: left; padding: 3.2mm 3mm; }
table.items thead th:first-child { border-radius: 2mm 0 0 0; } table.items thead th:last-child { border-radius: 0 2mm 0 0; }
table.items th.q, table.items th.r, table.items th.a, td.q, td.r, td.a { text-align: right; }
table.items th.n, td.n { width: 8mm; color: ${INK.muted}; }
td { padding: 3.2mm 3mm; border-bottom: 1px solid ${INK.line}; vertical-align: top; font-size: 10pt; }
td.d .t { font-weight: 700; } td.d .s { color: ${INK.muted}; font-size: 8.5pt; margin-top: .8mm; }
td.q { white-space: nowrap; color: ${INK.muted}; } td.q .u { font-size: 8pt; } td.r { color: ${INK.muted}; white-space: nowrap; }
td.a { font-weight: 800; color: ${INK.green}; font-size: 11.5pt; white-space: nowrap; }
.below { display: grid; grid-template-columns: 1fr 78mm; gap: 8mm; margin-top: 7mm; align-items: start; }
.totals .row { display: flex; justify-content: space-between; padding: 1.6mm 0; border-bottom: 1px solid ${INK.line}; font-size: 9pt; color: ${INK.muted}; letter-spacing: .08em; }
.totals .row b { color: ${INK.text}; letter-spacing: 0; }
.totals .grand { margin-top: 4mm; background: ${INK.green}; color: #fff; border-radius: 3mm; padding: 4mm 5mm; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 6px 14px rgba(11,77,60,.25); }
.totals .grand .k { font-size: 7pt; letter-spacing: .2em; opacity: .85; font-weight: 700; } .totals .grand .k b { display: block; font-size: 9pt; letter-spacing: .1em; opacity: 1; margin-top: .5mm; }
.totals .grand .v { font-size: 22pt; font-weight: 800; letter-spacing: -.01em; }
.paidline { margin-top: 2.5mm; font-size: 8.5pt; color: ${INK.green}; font-weight: 700; text-align: right; }
.card { background: ${INK.soft}; border: 1px solid ${INK.line}; border-radius: 3mm; padding: 3.5mm 4.5mm; margin-bottom: 4mm; }
.bank, .kv { display: flex; flex-direction: column; margin-top: 1.5mm; } .bank span, .kv span { font-size: 6.5pt; letter-spacing: .15em; color: ${INK.muted}; font-weight: 700; }
.bank b, .kv b { font-size: 9.5pt; } .bank b.big { font-size: 14pt; color: ${INK.green}; letter-spacing: .04em; }
.block { margin-bottom: 4mm; } .small { font-size: 8pt; color: ${INK.muted}; line-height: 1.45; }
.accept .sig { display: inline-block; width: 46%; margin-right: 4%; margin-top: 9mm; vertical-align: top; }
.accept .line { border-bottom: 1px solid ${INK.text}; height: 1px; } .accept .cap { font-size: 7pt; color: ${INK.muted}; margin-top: 1.5mm; letter-spacing: .08em; }
.prepared { margin-top: 5mm; font-size: 8.5pt; color: ${INK.muted}; } .prepared b { color: ${INK.text}; }
.foot { position: absolute; left: 0; right: 0; bottom: 0; background: ${INK.soft}; border-top: 1px solid ${INK.line}; padding: 4mm 14mm; display: flex; justify-content: space-between; align-items: center; gap: 6mm; }
.foot .co { font-weight: 700; font-size: 8.5pt; } .foot .sub { color: ${INK.muted}; font-size: 7.5pt; }
.foot .tag { font-size: 7.5pt; letter-spacing: .2em; color: ${INK.muted}; font-weight: 700; font-style: italic; text-align: right; }
.foot .note { color: ${INK.muted}; font-size: 6.5pt; }
.stamp { position: absolute; top: 36.5mm; right: 15mm; transform: rotate(-6deg); border: 0.9mm solid; border-radius: 2.5mm; padding: 1mm 4mm; font-size: 12pt; font-weight: 900; letter-spacing: .25em; opacity: .9; pointer-events: none; }
.stamp.paid { color: ${INK.green}; border-color: ${INK.green}; background: rgba(243,250,247,.85); }
.stamp.void { color: #B42318; border-color: #B42318; background: rgba(255,245,244,.9); }
.stamp.draft { color: ${INK.muted}; border-color: ${INK.muted}; background: rgba(244,247,250,.9); }
.grow { flex: 1; }
</style></head><body><div class="page">
  <div class="top">
    <div class="brand">${logo}${qr}</div>
    <div class="titlebox"><div class="k">${title}</div><div class="num">${esc(number || "—")}</div></div>
  </div>
  <div class="rule"></div>
  <div class="parties">
    <div class="issuer">
      <div class="lbl">${W.issuer}</div>
      <div class="name">${esc(co.name || "")}</div>
      <div class="reg">${[co.reg_no ? `${W.reg} ${co.reg_no}` : "", co.sst_no ? `${W.sst} ${co.sst_no}` : "", co.tin ? `${W.tin} ${co.tin}` : ""].filter(Boolean).map(esc).join(" · ")}</div>
      ${co.address ? `<div class="reg">${nl(co.address)}</div>` : ""}
      ${co.tagline ? `<div class="tag">${esc(co.tagline)}</div>` : ""}
      <div class="chips">${dateChips.filter(([, v]) => v).map(([k, v]) => `<div class="chip"><div class="k">${k}</div><div class="v">${esc(v)}</div></div>`).join("")}</div>
    </div>
    <div class="recipient">
      <div class="lbl">${recipientLabel}</div>
      <div class="name">${esc(c.name || "")}</div>
      ${c.reg_no ? `<div class="attn">${W.reg} ${esc(c.reg_no)}</div>` : ""}
      ${doc?.project ? `<div class="attn"><b>${W.project}:</b> ${esc(doc.project)}</div>` : ""}
      ${c.attention ? `<div class="attn">${W.attn} ${esc(c.attention)}</div>` : ""}
      ${addr.map((l) => `<div class="addr">${nl(l)}</div>`).join("")}
      ${c.state ? `<div class="state">${esc(String(c.state).toUpperCase())}${c.country && !/malaysia/i.test(c.country) ? ` · ${esc(String(c.country).toUpperCase())}` : ""}</div>` : ""}
      ${contact ? `<div class="contact">${esc(contact)}</div>` : ""}
    </div>
  </div>
  <table class="items"><thead><tr><th class="n">#</th><th>${W.description}</th><th class="q">${W.qty}</th><th class="r">${W.rate} (${esc(cur)})</th><th class="a">${W.amount}</th></tr></thead>
    <tbody>${items || `<tr><td colspan="5" class="d" style="color:${INK.muted}">—</td></tr>`}</tbody></table>
  <div class="below">
    <div class="left">${leftBlocks.join("")}${co.signatory ? `<div class="prepared">${W.prepared}: <b>${esc(co.signatory)}</b></div>` : ""}</div>
    <div class="totals">
      <div class="row"><span>${W.subtotal}</span><b>${esc(cur)} ${money(totals.subtotal)}</b></div>
      ${totals.discount > 0 ? `<div class="row"><span>${W.discount}</span><b>− ${esc(cur)} ${money(totals.discount)}</b></div>` : ""}
      ${showTax ? `<div class="row"><span>${W.tax} (${totals.tax_rate}%)</span><b>${esc(cur)} ${money(totals.tax)}</b></div>` : ""}
      <div class="grand"><div class="k">${lang === "en" ? "FINAL TOTAL" : "JUMLAH AKHIR"}<b>${totalLabel} (${esc(cur)})</b></div><div class="v">${money(totals.total)}</div></div>
      ${paidLine}
    </div>
  </div>
  <div class="grow"></div>
  ${badge(W, status, number)}
  <div class="foot">
    <div><div class="co">${esc(co.name || "")}${co.reg_no ? ` ${esc(co.reg_no)}` : ""}</div><div class="sub">${[co.footer, co.website, co.email, co.phone].filter(Boolean).map(esc).join(" · ")}</div></div>
    <div><div class="tag">${esc(co.tagline || "")}</div><div class="note">${W.page_note}</div></div>
  </div>
</div></body></html>`;
}

/** Several documents as one printable file (one A4 page each): the bulk download of the table. */
export function pagesHtml(list, settings = {}, optsFor = () => ({})) {
  const htmls = (list || []).map((d) => documentHtml(d, settings, optsFor(d)));
  if (!htmls.length) return "";
  const page = (h) => { const a = h.indexOf('<div class="page">'); const b = h.lastIndexOf("</div></body>"); return a >= 0 && b > a ? h.slice(a, b + 6) : ""; };
  const head = htmls[0].slice(0, htmls[0].indexOf("<body>") + 6);
  return head + htmls.map(page).map((p) => p.replace('<div class="page">', '<div class="page" style="page-break-after:always;break-after:page">')).join("") + "</body></html>";
}
