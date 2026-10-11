/* A drafted document (backend/semasa/brain_docs.py `build_doc`) as a Word file, built in the browser with fflate: a title, a
   status line, the document-control table, one heading per section (paragraphs, bullets or a table with a repeating header
   row), then the lists a reviewer needs (to confirm, conflicts, source check, wording to look at). Every unfilled place shows
   the marker with a yellow highlight, the header says DRAFT FOR REVIEW on every page, the footer carries the disclaimer and
   the page number. A table with five or more columns turns the page to landscape. Pure: no DOM, so it runs under node. */
import { strToU8, zipSync } from "fflate";

export const DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
const NS = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"';
const MARKERS = ["[Perlu pengesahan]", "[Needs confirmation]"];
const INK = "1F2A44";
const HEAD_FILL = "DCE6F2";
const META_FILL = "F1F4F9";
const RED = "B3261E";
const PORTRAIT = { w: 11906, h: 16838, margin: 1080 };       // A4, 0.75 inch margins, in twips
const bad = /[\u0000-\u0008\u000B\u000C\u000E-\u001F￾￿]/g;      // characters XML 1.0 cannot carry
const esc = (s) => String(s ?? "").replace(bad, "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const MARKER_SPLIT = new RegExp(`(${MARKERS.map((m) => m.replace(/[[\]]/g, "\\$&")).join("|")})`);

function rpr(o = {}) {
  const inner = `${o.b ? "<w:b/>" : ""}${o.i ? "<w:i/>" : ""}${o.color ? `<w:color w:val="${o.color}"/>` : ""}${o.sz ? `<w:sz w:val="${o.sz}"/><w:szCs w:val="${o.sz}"/>` : ""}${o.hl ? `<w:highlight w:val="${o.hl}"/>` : ""}`;
  return inner ? `<w:rPr>${inner}</w:rPr>` : "";
}

/** Runs for a text: line breaks kept, the marker highlighted wherever it stands. */
function runs(text, o = {}) {
  const out = [];
  String(text ?? "").split(MARKER_SPLIT).forEach((part, i) => {
    if (!part) return;
    const mark = i % 2 === 1;
    const opts = mark ? { ...o, hl: "yellow", b: true } : o;
    const lines = part.split(/\r?\n/);
    out.push(`<w:r>${rpr(opts)}${lines.map((l, k) => `${k ? "<w:br/>" : ""}<w:t xml:space="preserve">${esc(l)}</w:t>`).join("")}</w:r>`);
  });
  return out.join("");
}

function para(text, { style = "", o = {}, keepNext = false, ind = "", jc = "", after = "" } = {}) {
  const pr = `${style ? `<w:pStyle w:val="${style}"/>` : ""}${keepNext ? "<w:keepNext/>" : ""}${after ? `<w:spacing w:after="${after}"/>` : ""}${ind}${jc ? `<w:jc w:val="${jc}"/>` : ""}`;
  return `<w:p>${pr ? `<w:pPr>${pr}</w:pPr>` : ""}${runs(text, o)}</w:p>`;
}
const bullet = (text) => para(`• ${text}`, { ind: '<w:ind w:left="360" w:hanging="360"/>', after: "60" });

function widths(columns, rows, total) {
  const weight = columns.map((c, i) => {
    const lens = rows.map((r) => String(r[i] ?? "").length);
    const avg = lens.length ? lens.reduce((a, b) => a + b, 0) / lens.length : 0;
    return Math.min(70, Math.max(6, avg, String(c).length * 0.7));
  });
  const sum = weight.reduce((a, b) => a + b, 0);
  const w = weight.map((x) => Math.max(640, Math.round((total * x) / sum)));
  const diff = total - w.reduce((a, b) => a + b, 0);
  w[w.indexOf(Math.max(...w))] += diff;
  return w;
}

function table(columns, rows, total, { head = true, firstFill = false } = {}) {
  const w = widths(columns, rows, total);
  const cell = (text, i, o = {}, fill = "") => `<w:tc><w:tcPr><w:tcW w:w="${w[i]}" w:type="dxa"/>${fill ? `<w:shd w:val="clear" w:color="auto" w:fill="${fill}"/>` : ""}</w:tcPr>${para(text, { o, after: "40" })}</w:tc>`;
  const header = head ? `<w:tr><w:trPr><w:cantSplit/><w:tblHeader/></w:trPr>${columns.map((c, i) => cell(c, i, { b: true, color: INK }, HEAD_FILL)).join("")}</w:tr>` : "";
  const body = rows.map((r) => `<w:tr><w:trPr><w:cantSplit/></w:trPr>${columns.map((_, i) => cell(r[i], i, firstFill && i === 0 ? { b: true } : {}, firstFill && i === 0 ? META_FILL : "")).join("")}</w:tr>`).join("");
  return `<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/><w:tblW w:w="${total}" w:type="dxa"/><w:tblLayout w:type="fixed"/><w:tblLook w:val="04A0"/></w:tblPr>`
    + `<w:tblGrid>${w.map((x) => `<w:gridCol w:w="${x}"/>`).join("")}</w:tblGrid>${header}${body}</w:tbl>${para("", { after: "60" })}`;
}

/** The body of the document as WordprocessingML, plus whether any table is wide enough to need a landscape page. */
function bodyXml(doc, total) {
  const g = doc.generic || {};
  const out = [para(doc.title, { style: "Title" }), para(doc.status, { o: { b: true, color: RED, sz: 24 }, after: "120" })];
  out.push(table(["", ""], doc.meta || [], total, { head: false, firstFill: true }));
  for (const s of doc.sections || []) {
    out.push(para(s.heading, { style: "Heading1", keepNext: true }));
    if (s.kind === "table") out.push(table(s.columns, s.rows, total));
    else if (s.kind === "bullets") out.push(...(s.bullets || []).map(bullet));
    else out.push(...(s.paragraphs || []).map((p) => para(p)));
  }
  const list = (heading, items) => { if (items?.length) out.push(para(heading, { style: "Heading1", keepNext: true }), ...items.map(bullet)); };
  list(g.to_confirm, doc.to_confirm);
  list(g.conflicts, doc.conflicts);
  if (doc.source_check?.length) out.push(para(g.source_check, { style: "Heading1", keepNext: true }), para(doc.source_check.join("  ·  ")));
  list(g.flags, doc.flags);
  if (doc.truncated && g.truncated) out.push(para(g.truncated, { o: { i: true, color: RED } }));
  return out.join("");
}

const STYLES = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles ${NS}>`
  + `<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Calibri" w:eastAsia="Calibri"/><w:sz w:val="21"/><w:szCs w:val="21"/><w:lang w:val="ms-MY" w:eastAsia="en-US" w:bidi="ar-SA"/></w:rPr></w:rPrDefault>`
  + `<w:pPrDefault><w:pPr><w:spacing w:after="100" w:line="264" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>`
  + `<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>`
  + `<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:spacing w:before="0" w:after="80"/></w:pPr><w:rPr><w:b/><w:color w:val="${INK}"/><w:sz w:val="40"/><w:szCs w:val="40"/></w:rPr></w:style>`
  + `<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:spacing w:before="240" w:after="80"/><w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:b/><w:color w:val="${INK}"/><w:sz w:val="26"/><w:szCs w:val="26"/></w:rPr></w:style>`
  + `<w:style w:type="paragraph" w:styleId="Header"><w:name w:val="header"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:after="0"/></w:pPr><w:rPr><w:sz w:val="18"/><w:szCs w:val="18"/></w:rPr></w:style>`
  + `<w:style w:type="paragraph" w:styleId="Footer"><w:name w:val="footer"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:after="0"/></w:pPr><w:rPr><w:color w:val="595959"/><w:sz w:val="16"/><w:szCs w:val="16"/></w:rPr></w:style>`
  + `<w:style w:type="table" w:default="1" w:styleId="TableNormal"><w:name w:val="Normal Table"/><w:uiPriority w:val="99"/><w:semiHidden/><w:tblPr><w:tblInd w:w="0" w:type="dxa"/><w:tblCellMar><w:top w:w="0" w:type="dxa"/><w:left w:w="108" w:type="dxa"/><w:bottom w:w="0" w:type="dxa"/><w:right w:w="108" w:type="dxa"/></w:tblCellMar></w:tblPr></w:style>`
  + `<w:style w:type="table" w:styleId="TableGrid"><w:name w:val="Table Grid"/><w:basedOn w:val="TableNormal"/><w:uiPriority w:val="39"/><w:tblPr><w:tblBorders>`
  + ["top", "left", "bottom", "right", "insideH", "insideV"].map((e) => `<w:${e} w:val="single" w:sz="4" w:space="0" w:color="9AA5B8"/>`).join("")
  + `</w:tblBorders><w:tblCellMar><w:top w:w="40" w:type="dxa"/><w:left w:w="100" w:type="dxa"/><w:bottom w:w="40" w:type="dxa"/><w:right w:w="100" w:type="dxa"/></w:tblCellMar></w:tblPr></w:style></w:styles>`;

const CONTENT_TYPES = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">`
  + `<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>`
  + `<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>`
  + `<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>`
  + `<Override PartName="/word/header1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>`
  + `<Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>`
  + `<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/></Types>`;
const ROOT_RELS = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">`
  + `<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>`
  + `<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/></Relationships>`;
const DOC_RELS = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">`
  + `<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>`
  + `<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header1.xml"/>`
  + `<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/></Relationships>`;

/** The Word file of a drafted document, as bytes. */
export function buildDocx(doc, { now = new Date() } = {}) {
  if (!doc || !Array.isArray(doc.sections)) throw new Error("not a drafted document");
  const wide = (doc.sections || []).some((s) => s.kind === "table" && (s.columns || []).length >= 5);
  const pageW = wide ? PORTRAIT.h : PORTRAIT.w;
  const pageH = wide ? PORTRAIT.w : PORTRAIT.h;
  const total = pageW - 2 * PORTRAIT.margin;
  const sect = `<w:sectPr><w:headerReference w:type="default" r:id="rId2"/><w:footerReference w:type="default" r:id="rId3"/>`
    + `<w:pgSz w:w="${pageW}" w:h="${pageH}"${wide ? ' w:orient="landscape"' : ""}/><w:pgMar w:top="1200" w:right="${PORTRAIT.margin}" w:bottom="1100" w:left="${PORTRAIT.margin}" w:header="560" w:footer="480" w:gutter="0"/></w:sectPr>`;
  const document = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document ${NS}><w:body>${bodyXml(doc, total)}${sect}</w:body></w:document>`;
  const g = doc.generic || {};
  const header = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:hdr ${NS}>${para(`${doc.status}  ·  ${doc.title}`, { style: "Header", o: { b: true, color: RED, sz: 18 }, jc: "right" })}</w:hdr>`;
  const footer = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:ftr ${NS}>${para(doc.disclaimer, { style: "Footer" })}`
    + `<w:p><w:pPr><w:pStyle w:val="Footer"/><w:jc w:val="right"/></w:pPr><w:r><w:t xml:space="preserve">${esc(g.page || "Page")} </w:t></w:r><w:fldSimple w:instr=" PAGE "><w:r><w:t>1</w:t></w:r></w:fldSimple></w:p></w:ftr>`;
  const iso = now.toISOString().replace(/\.\d+Z$/, "Z");
  const core = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">`
    + `<dc:title>${esc(doc.title)}</dc:title><dc:creator>Semasa (AI draft)</dc:creator><dc:language>${doc.lang === "en" ? "en-MY" : "ms-MY"}</dc:language>`
    + `<dcterms:created xsi:type="dcterms:W3CDTF">${iso}</dcterms:created></cp:coreProperties>`;
  return zipSync({
    "[Content_Types].xml": strToU8(CONTENT_TYPES), "_rels/.rels": strToU8(ROOT_RELS), "docProps/core.xml": strToU8(core),
    "word/document.xml": strToU8(document), "word/styles.xml": strToU8(STYLES), "word/_rels/document.xml.rels": strToU8(DOC_RELS),
    "word/header1.xml": strToU8(header), "word/footer1.xml": strToU8(footer),
  }, { level: 6 });
}

// the date in Malaysia: toISOString() is UTC, so from 00:00 to 07:59 MYT a file would be named yesterday
const myDate = (d) => new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kuala_Lumpur" }).format(d);

/** A safe file name: the title, the language, the word draft and the date (Malaysia). */
export function docFileName(doc, date = new Date()) {
  const slug = String(doc?.title || doc?.type || "dokumen").normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase()
    .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 60) || "dokumen";
  return `${slug}-${doc?.lang === "en" ? "en-draft" : "ms-draf"}-${myDate(date)}.docx`;
}
