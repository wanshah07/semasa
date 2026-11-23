/* Expert content as a report (Wan, 23 Nov 2026: "for expert content, can you directly copy and write into report or table, and
   allow me to print or download in pdf/csv/doc format, make sure the report or table ada timeline record").

   Pure: rows in, text out. No React, no i18n import (a Node test cannot load i18n.jsx), so the language comes in as "bm" or "en".
   The page's own words are never cut: the full original post, the full summary and the full takeaway go into every format.

   The TIMELINE is the posting time of each post (`published_at`, a real UTC ISO string), shown on the Malaysia clock, sorted
   newest or oldest first, with the date in its own column, grouped by day in the printed report and the Word file, and the
   exact UTC stamp in the CSV so a spreadsheet can sort on it. A row with no readable time goes last in either order and says
   so; it is never given a time it does not have. Times are read with `new Date(iso)` and Intl, never by cutting a display stamp
   ("22 Nov, 14:05 MYT") apart: that form is for people and is not parseable. */

const TZ = "Asia/Kuala_Lumpur";

export const FORMATS = ["print", "pdf", "csv", "doc"];
export const DOC_MIME = "application/msword";
export const CSV_MIME = "text/csv;charset=utf-8";

const LABELS = {
  bm: {
    title: "Laporan kandungan pakar", category: "Kategori", range: "Tempoh", items: "Bilangan catatan", generated: "Dijana", order: "Susunan",
    newest: "Terbaharu dahulu", oldest: "Terlama dahulu", filters: "Penapis", account: "Akaun", search: "Carian", hidden: "termasuk yang disembunyi",
    all: "Semua", none: "Tiada catatan", noTime: "Masa tidak diketahui", to: "hingga", no: "Bil.", date: "Tarikh", time: "Masa (MYT)",
    utc: "Cap masa (UTC)", expert: "Pakar", handle: "Akaun", platform: "Platform", cat: "Kategori", headline: "Tajuk", summary: "Ringkasan",
    why: "Apa yang boleh diambil", original: "Catatan asal", link: "Pautan", collected: "Dikutip (MYT)", timeline: "Garis masa",
    page: "Halaman", note: "Pandangan seorang pakar sebagai rujukan, bukan fakta yang disahkan.",
  },
  en: {
    title: "Expert content report", category: "Category", range: "Period", items: "Number of posts", generated: "Generated", order: "Order",
    newest: "Newest first", oldest: "Oldest first", filters: "Filters", account: "Account", search: "Search", hidden: "including hidden posts",
    all: "All", none: "No posts", noTime: "Time unknown", to: "to", no: "No.", date: "Date", time: "Time (MYT)",
    utc: "Timestamp (UTC)", expert: "Expert", handle: "Account", platform: "Platform", cat: "Category", headline: "Headline", summary: "Summary",
    why: "What to take from it", original: "Original post", link: "Link", collected: "Collected (MYT)", timeline: "Timeline",
    page: "Page", note: "One expert's view, kept as a reference, not a verified fact.",
  },
};
export const labelsOf = (lang) => LABELS[lang === "en" ? "en" : "bm"];

const PLATFORM = { threads: "Threads", facebook: "Facebook", instagram: "Instagram" };

/* ---- time: always the Malaysia clock, always from a real ISO string ---- */

const partsFmt = new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });

/** { date: "2026-11-22", time: "14:05", ms } on the Malaysia clock, or null when `iso` is not a readable time. */
export function mytParts(iso) {
  if (!iso) return null;
  const ms = new Date(iso).getTime();
  if (!Number.isFinite(ms)) return null;
  const p = Object.fromEntries(partsFmt.formatToParts(new Date(ms)).map((x) => [x.type, x.value]));
  return { date: `${p.year}-${p.month}-${p.day}`, time: `${p.hour}:${p.minute}`, ms };
}

/** "2026-11-22 14:05 MYT", or "" for an unreadable time. */
export function mytText(iso) {
  const p = mytParts(iso);
  return p ? `${p.date} ${p.time} MYT` : "";
}

/** The day heading of the grouped report: "Ahad, 22 November 2026" / "Sunday, 22 November 2026" (from the YYYY-MM-DD, no clock involved). */
export function dayHeading(date, lang) {
  const [y, m, d] = String(date).split("-").map(Number);
  if (!y || !m || !d) return String(date);
  return new Intl.DateTimeFormat(lang === "en" ? "en-GB" : "ms-MY", { timeZone: "UTC", weekday: "long", day: "numeric", month: "long", year: "numeric" })
    .format(new Date(Date.UTC(y, m - 1, d)));
}

/* ---- the items ---- */

const one = (v) => String(v ?? "").trim();

/** One normalised row per feed row, in timeline order. `order` is "newest" (default) or "oldest". Rows without a readable time go last. */
export function reportItems(rows, { order = "newest", lang = "bm" } = {}) {
  const items = (rows || []).map((r) => {
    const raw = r.raw || {};
    const at = r.published_at || r.created_at || "";
    const when = mytParts(at);
    const got = mytParts(r.created_at);
    return {
      id: r.id ?? "", at, date: when ? when.date : "", time: when ? when.time : "", ms: when ? when.ms : null,
      expert: one(raw.owner || raw.handle), handle: one(raw.handle), platform: PLATFORM[raw.platform] || one(raw.platform),
      category: one(raw.category_name || raw.category), title: one(r.title), summary: one(r.summary), why: one(r.why),
      original: one(raw.original), link: one(r.url), collected: got ? `${got.date} ${got.time}` : "", parts: Number(raw.parts) || 1,
      // the post's own time is `published_at`; a row that only has the time it was collected says so
      timeIsCollected: Boolean(!r.published_at && r.created_at),
    };
  });
  const dir = order === "oldest" ? 1 : -1;
  items.sort((a, b) => {
    if (a.ms === null || b.ms === null) return a.ms === b.ms ? 0 : a.ms === null ? 1 : -1;     // unreadable times last, whichever way
    return (a.ms - b.ms) * dir || String(a.id).localeCompare(String(b.id));
  });
  return items.map((x, i) => ({ ...x, n: i + 1, lang }));
}

/** First and last day (YYYY-MM-DD, Malaysia) the items cover, and whether any had no readable time. */
export function rangeOf(items) {
  const days = items.filter((x) => x.date).map((x) => x.date).sort();
  return { from: days[0] || "", to: days[days.length - 1] || "", unknown: items.filter((x) => !x.date).length };
}

export function rangeText(items, lang = "bm") {
  const L = labelsOf(lang);
  const r = rangeOf(items);
  if (!r.from) return items.length ? L.noTime : "";
  const base = r.from === r.to ? r.from : `${r.from} ${L.to} ${r.to}`;
  return r.unknown ? `${base} (+${r.unknown} ${L.noTime.toLowerCase()})` : base;
}

/** Consecutive items on one Malaysia day: [{ date, items }]. Items with no readable time are one last group with date "". */
export function groupByDay(items) {
  const groups = [];
  for (const it of items) {
    const last = groups[groups.length - 1];
    if (last && last.date === it.date) last.items.push(it); else groups.push({ date: it.date, items: [it] });
  }
  return groups;
}

/** The facts the header prints: title, category, range, count, when it was made, the order and the filters in force. */
export function reportMeta(items, { category = "", order = "newest", account = "", q = "", hidden = false, now = new Date(), lang = "bm" } = {}) {
  const L = labelsOf(lang);
  const filters = [account && `${L.account}: @${String(account).replace(/^@/, "")}`, q && `${L.search}: “${q}”`, hidden && L.hidden].filter(Boolean);
  return {
    title: L.title, category: category || L.all, range: rangeText(items, lang), count: items.length,
    generated: mytText(now instanceof Date ? now.toISOString() : now), order: order === "oldest" ? L.oldest : L.newest,
    filters: filters.join(" · "), lang,
  };
}

/** A file name safe on every system: expert-<category>-<from>_<to>.<ext>. */
export function fileName(meta, items, ext) {
  const slug = String(meta.category || "expert").toLowerCase().normalize("NFKD").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 40) || "expert";
  const r = rangeOf(items);
  const span = r.from ? (r.from === r.to ? r.from : `${r.from}_${r.to}`) : "";
  return `expert-${slug}${span ? `-${span}` : ""}.${ext}`;
}

/* ---- CSV: UTF-8 with a BOM so Excel reads Malay and Chinese; commas, quotes and newlines are quoted ---- */

export const BOM = "﻿";

/** One CSV cell. A cell Excel would run as a formula (leading = + - @, tab or CR) gets a leading apostrophe, so a post can never execute. */
export function csvCell(v) {
  let s = String(v ?? "");
  if (/^[=+\-@\t\r]/.test(s)) s = `'${s}`;
  return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export function csvColumns(lang = "bm") {
  const L = labelsOf(lang);
  return [L.no, L.date, L.time, L.utc, L.expert, L.handle, L.platform, L.cat, L.headline, L.summary, L.why, L.original, L.link, L.collected];
}

export function csvRows(items) {
  return items.map((x) => [x.n, x.date, x.time, x.ms === null ? "" : new Date(x.ms).toISOString(), x.expert, x.handle, x.platform, x.category,
    x.title, x.summary, x.why, x.original, x.link, x.collected]);
}

/** The whole file as text: BOM, a header row, one row per post in timeline order, CRLF line ends. */
export function reportCsv(items, { lang = "bm" } = {}) {
  return BOM + [csvColumns(lang), ...csvRows(items)].map((row) => row.map(csvCell).join(",")).join("\r\n") + "\r\n";
}

/* ---- HTML: one table for the screen-free print view and for Word ---- */

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const para = (s) => esc(s).replace(/\r?\n/g, "<br>");

const CSS = `
body { font: 9.5pt/1.45 "Segoe UI", Calibri, Arial, "Noto Sans", "Noto Sans CJK SC", "Microsoft YaHei", sans-serif; color: #1c1917; margin: 0; }
h1 { font-size: 18pt; margin: 0 0 4pt; }
.meta { border-collapse: collapse; margin: 0 0 10pt; }
.meta td { padding: 1pt 10pt 1pt 0; font-size: 9pt; vertical-align: top; }
.meta td.k { color: #78716c; white-space: nowrap; }
table.rep { border-collapse: collapse; width: 100%; }
table.rep th { background: #f1ece3; text-align: left; font-size: 8.5pt; padding: 4pt 5pt; border: 1px solid #c9bfae; }
table.rep td { padding: 4pt 5pt; border: 1px solid #d9d1c2; vertical-align: top; font-size: 8.5pt; }
tr.day td { background: #e9e1d1; font-weight: bold; font-size: 9.5pt; border: 1px solid #c9bfae; }
td.no, td.when { white-space: nowrap; }
td.when b { font-size: 9pt; }
.t { font-weight: bold; margin: 0 0 2pt; }
.muted { color: #78716c; }
.link { word-break: break-all; }
.foot { color: #78716c; font-size: 8pt; margin-top: 8pt; }
`;

const PRINT_CSS = `
@page { size: A4 landscape; margin: 12mm 10mm 14mm; }
table.rep thead { display: table-header-group; }
table.rep tr { break-inside: auto; }
tr.day { break-after: avoid; }
table.rep th, tr.day td { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
`;

function headerHtml(meta) {
  const L = labelsOf(meta.lang);
  const rows = [[L.category, meta.category], [L.range, meta.range || "-"], [L.items, meta.count], [L.order, `${meta.order} (${L.timeline.toLowerCase()})`],
    meta.filters && [L.filters, meta.filters], [L.generated, meta.generated]].filter(Boolean);
  return `<h1>${esc(meta.title)}</h1><table class="meta">${rows.map(([k, v]) => `<tr><td class="k">${esc(k)}</td><td>${esc(v)}</td></tr>`).join("")}</table>`;
}

function tableHtml(items, meta) {
  const L = labelsOf(meta.lang);
  const head = [L.no, L.date, L.expert, L.platform, L.cat, `${L.headline} / ${L.summary}`, L.why, L.original, L.link];
  const cols = head.length;
  const body = items.length ? groupByDay(items).map((g) => `<tr class="day"><td colspan="${cols}">${esc(g.date ? dayHeading(g.date, meta.lang) : L.noTime)} · ${g.items.length}</td></tr>`
    + g.items.map((x) => `<tr>
<td class="no">${x.n}</td>
<td class="when"><b>${esc(x.date || "-")}</b><br>${esc(x.time ? `${x.time} MYT` : "")}${x.timeIsCollected ? `<br><span class="muted">${esc(L.collected)}</span>` : ""}</td>
<td><b>${esc(x.expert)}</b>${x.handle ? `<br><span class="muted">@${esc(x.handle)}</span>` : ""}</td>
<td>${esc(x.platform)}</td>
<td>${esc(x.category)}</td>
<td><p class="t">${para(x.title)}</p>${para(x.summary)}</td>
<td>${para(x.why)}</td>
<td>${para(x.original)}</td>
<td class="link">${x.link ? `<a href="${esc(x.link)}">${esc(x.link)}</a>` : ""}</td>
</tr>`).join("")).join("")
    : `<tr><td colspan="${cols}">${esc(L.none)}</td></tr>`;
  return `<table class="rep"><thead><tr>${head.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>${body}</tbody></table><p class="foot">${esc(L.note)}</p>`;
}

/** The report for the browser's print dialog (and "Save as PDF" from it): A4 landscape, the header on page one, the column heads repeated on every page. */
export function printHtml(items, meta) {
  return `<!doctype html><html lang="${meta.lang === "en" ? "en" : "ms"}"><head><meta charset="utf-8"><title>${esc(meta.title)} · ${esc(meta.category)}</title>
<style>${CSS}${PRINT_CSS}</style></head><body>${headerHtml(meta)}${tableHtml(items, meta)}</body></html>`;
}

/** A Word file: HTML with the Office namespaces, which Word opens as a document with the table intact. Landscape A4 through the MSO page rule. */
export function docHtml(items, meta) {
  return `<html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:w="urn:schemas-microsoft-com:office:word" xmlns="http://www.w3.org/TR/REC-html40" lang="${meta.lang === "en" ? "en" : "ms"}"><head><meta charset="utf-8"><meta name="ProgId" content="Word.Document">
<title>${esc(meta.title)} · ${esc(meta.category)}</title>
<!--[if gte mso 9]><xml><w:WordDocument><w:View>Print</w:View><w:Zoom>100</w:Zoom><w:DoNotOptimizeForBrowser/></w:WordDocument></xml><![endif]-->
<style>@page Section1 { size: 841.9pt 595.3pt; mso-page-orientation: landscape; margin: 36pt 30pt 36pt 30pt; } div.Section1 { page: Section1; }${CSS}</style></head>
<body><div class="Section1">${headerHtml(meta)}${tableHtml(items, meta)}</div></body></html>`;
}

/** The bytes of the Word file as text: a BOM first so every Word reads the UTF-8. */
export const docFile = (items, meta) => BOM + docHtml(items, meta);

/* ---- browser side (not run by the test) ---- */

/** Open the browser's print dialog on a report, from a hidden frame; "Save as PDF" in that dialog makes the PDF. */
export function printReport(html) {
  const frame = document.createElement("iframe");
  frame.setAttribute("aria-hidden", "true");
  frame.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0";
  document.body.appendChild(frame);
  const doc = frame.contentWindow.document;
  doc.open(); doc.write(html); doc.close();
  const go = () => { frame.contentWindow.focus(); frame.contentWindow.print(); setTimeout(() => frame.remove(), 60_000); };
  if (doc.readyState === "complete") setTimeout(go, 200); else frame.onload = () => setTimeout(go, 200);
}
