/* Expert content as a report (23 Nov 2026): the CSV, the Word file, the printable report, the timeline. `npm test`. */
import assert from "node:assert/strict";
import { BOM, csvCell, docFile, docHtml, fileName, groupByDay, mytParts, mytText, printHtml, rangeOf, rangeText, reportCsv, reportItems, reportMeta } from "./src/lib/expertReport.js";

let n = 0;
const ok = (cond, msg) => { assert.ok(cond, msg); n++; };
const eq = (a, b, msg) => { assert.deepEqual(a, b, msg); n++; };

const row = (id, published_at, extra = {}) => ({ id, published_at, created_at: "2026-11-22T10:00:00.000Z", title: `T${id}`, summary: `S${id}`, why: `W${id}`,
  url: `https://www.threads.com/@a/post/${id}`, section: "expert",
  raw: { category: "ai", category_name: "AI Expert", handle: "ahmad", owner: "Ahmad R", platform: "threads", original: `orig ${id}`, ...(extra.raw || {}) }, ...extra });
const rows = [row("a", "2026-11-20T16:30:00.000Z"), row("b", "2026-11-22T01:05:00.000Z"), row("c", "2026-11-21T03:00:00.000Z"), row("d", null, { created_at: null })];

// time: the Malaysia clock from a real ISO string (UTC 16:30 is 00:30 the next day in Malaysia)
eq(mytParts("2026-11-20T16:30:00.000Z"), { date: "2026-11-21", time: "00:30", ms: Date.UTC(2026, 10, 20, 16, 30) });
eq(mytText("2026-11-22T01:05:00.000Z"), "2026-11-22 09:05 MYT");
eq(mytParts("22 Nov, 14:05 MYT"), null, "a display stamp is not a time and is never guessed");
eq(mytParts(""), null); eq(mytParts(null), null);

// timeline order: newest first, oldest first, an unreadable time always last, numbered in the order shown
const newest = reportItems(rows, { order: "newest" });
eq(newest.map((x) => x.id), ["b", "c", "a", "d"]);
eq(newest.map((x) => x.n), [1, 2, 3, 4]);
const oldest = reportItems(rows, { order: "oldest" });
eq(oldest.map((x) => x.id), ["a", "c", "b", "d"]);
eq(reportItems(rows).map((x) => x.id), newest.map((x) => x.id), "newest is the default");
eq(newest[2].date, "2026-11-21", "the date is the Malaysia day, not the UTC day");
eq(reportItems([row("x", "2026-11-22T01:00:00.000Z"), row("y", "2026-11-22T01:00:00.000Z")]).map((x) => x.id), ["x", "y"], "equal times keep a stable order");
const fallback = reportItems([row("f", null)])[0];
ok(fallback.timeIsCollected && fallback.date === "2026-11-22", "no post time: the collected time is used and flagged, not passed off as the post time");
ok(!newest[0].timeIsCollected);
ok(newest[0].original === "orig b" && newest[0].expert === "Ahmad R" && newest[0].platform === "Threads", "fields carried whole");
const longText = "x".repeat(5000);
ok(reportItems([row("l", "2026-11-22T01:00:00.000Z", { raw: { original: longText, category: "ai", handle: "h" } })])[0].original.length === 5000, "nothing is truncated");

// date range header
eq(rangeOf(newest), { from: "2026-11-21", to: "2026-11-22", unknown: 1 });
eq(rangeText(newest.slice(0, 3), "en"), "2026-11-21 to 2026-11-22");
eq(rangeText(newest.slice(0, 3), "bm"), "2026-11-21 hingga 2026-11-22");
eq(rangeText([newest[0]], "en"), "2026-11-22");
eq(rangeText(newest, "en"), "2026-11-21 to 2026-11-22 (+1 time unknown)");
eq(rangeText([], "en"), "");
eq(groupByDay(newest).map((g) => [g.date, g.items.length]), [["2026-11-22", 1], ["2026-11-21", 2], ["", 1]]);

// meta
const now = new Date("2026-11-23T06:07:00.000Z");
const meta = reportMeta(newest, { category: "AI Expert", order: "newest", account: "@ahmad", q: "gpt", hidden: true, now, lang: "en" });
eq([meta.title, meta.category, meta.count, meta.generated, meta.order], ["Expert content report", "AI Expert", 4, "2026-11-23 14:07 MYT", "Newest first"]);
ok(meta.filters.includes("Account: @ahmad") && meta.filters.includes("gpt") && meta.filters.includes("hidden"), "filters in force are named");
eq(reportMeta(newest, { now, lang: "bm" }).category, "Semua");
eq(fileName(meta, newest, "csv"), "expert-ai-expert-2026-11-21_2026-11-22.csv");
eq(fileName({ category: "" }, [], "doc"), "expert-expert.doc");

// CSV: BOM, quoting, newlines, formulas
ok(BOM === "﻿");
eq(csvCell("plain"), "plain");
eq(csvCell("a,b"), '"a,b"');
eq(csvCell('say "hi"'), '"say ""hi"""');
eq(csvCell("line1\nline2"), '"line1\nline2"');
eq(csvCell("a\r\nb"), '"a\r\nb"');
eq(csvCell(null), ""); eq(csvCell(0), "0");
eq(csvCell("=HYPERLINK(\"x\")"), '"\'=HYPERLINK(""x"")"', "a formula is defused and still quoted correctly");
eq(csvCell("@who"), "'@who");
eq(csvCell("+60 12"), "'+60 12");
const csv = reportCsv(reportItems([row("q", "2026-11-22T01:05:00.000Z", { title: 'He said "yes", then\nleft', raw: { category: "ai", handle: "h", original: "你好，世界 — Kosmetik, selamat" } })], { lang: "en" }), { lang: "en" });
ok(csv.charCodeAt(0) === 0xfeff, "UTF-8 BOM first, so Excel reads Malay and Chinese");
ok(csv.includes("你好，世界"), "non-Latin text is kept");
ok(csv.includes('"He said ""yes"", then\nleft"'), "commas, quotes and newlines in a cell are quoted");
ok(csv.split("\r\n")[0].startsWith(`${BOM}No.,Date,Time (MYT),Timestamp (UTC),Expert,Account`), "header row with the date columns");
ok(csv.includes("2026-11-22,09:05,2026-11-22T01:05:00.000Z"), "date, Malaysia time and the exact UTC stamp");
ok(csv.endsWith("\r\n"));
const csvAll = reportCsv(newest, { lang: "bm" });
ok(csvAll.includes(",Tarikh,Masa (MYT),"), "the Malay header when the page is in Malay");
eq(csvAll.split("\r\n").length, 1 + 4 + 1, "one line per post plus the header, and the closing newline");

// printable report: header, timeline grouped by day, column heads, escaped text, A4 landscape
const html = printHtml(newest, meta);
ok(html.startsWith("<!doctype html>") && html.includes("@page { size: A4 landscape"), "a print stylesheet for A4 landscape");
ok(html.includes("<h1>Expert content report</h1>") && html.includes("AI Expert") && html.includes("2026-11-21 to 2026-11-22 (+1 time unknown)"), "title, category, range");
ok(html.includes("2026-11-23 14:07 MYT") && html.includes(">4<"), "generated stamp and number of posts");
ok(html.includes("thead { display: table-header-group") , "the column heads repeat on every page");
eq((html.match(/class="day"/g) || []).length, 3, "three day groups");
ok(html.indexOf("Sunday, 22 November 2026") < html.indexOf("Saturday, 21 November 2026"), "days in timeline order, newest first");
ok(html.indexOf("Time unknown") > html.indexOf("Saturday, 21 November 2026"), "unreadable time last");
const oh = printHtml(oldest, { ...meta, order: "Oldest first" });
ok(oh.indexOf("Saturday, 21 November 2026") < oh.indexOf("Sunday, 22 November 2026"), "oldest first reverses the days");
ok(html.includes("orig b") && html.includes('href="https://www.threads.com/@a/post/b"'), "full original and the link");
const evil = printHtml(reportItems([row("e", "2026-11-22T01:05:00.000Z", { title: "<script>alert(1)</script> & co", summary: "a\nb" })]), meta);
ok(!evil.includes("<script>") && evil.includes("&lt;script&gt;") && evil.includes("a<br>b"), "text is escaped, line breaks kept");
ok(printHtml([], reportMeta([], { now, lang: "en" })).includes("No posts"), "an empty report says so");

// Word file
const doc = docHtml(newest, meta);
ok(doc.includes('xmlns:w="urn:schemas-microsoft-com:office:word"') && doc.includes('xmlns:o="urn:schemas-microsoft-com:office:office"'), "Office namespaces");
ok(doc.includes("mso-page-orientation: landscape") && doc.includes("<w:WordDocument>"), "Word page setup");
ok(doc.includes('<meta charset="utf-8">') && docFile(newest, meta).charCodeAt(0) === 0xfeff, "UTF-8 declared and a BOM");
ok(doc.includes("<table class=\"rep\">") && doc.includes("<thead>") && doc.includes("Sunday, 22 November 2026") && doc.includes("2026-11-23 14:07 MYT"), "the table, the day groups and the header survive");
ok(doc.includes("orig b") && doc.includes("W b".replace(" ", "")), "full text in the Word file");
ok(!doc.includes("<script"), "no script in the Word file");

console.log(`expertReport.test.mjs: ${n} checks passed`);
