import assert from "node:assert/strict";
import { breakText, splitRow, renumber, fixFullRows, fixNote } from "./src/lib/fixFull.js";

let n = 0; const ok = (c, m) => { assert.ok(c, m); n += 1; };
const row = (title, points, extra = {}) => ({ title, points, bg: "", ...extra });

// a slide with several points: shared between two halves, every word kept, the design travels
const two = splitRow(row("Pendaftaran", "a\nb\nc\nd\ne", { bg: "lib:x" }));
ok(two.length === 2 && two[0].points === "a\nb\nc" && two[1].points === "d\ne" && two[1].bg === "lib:x", "points shared");
// one long point: broken at a sentence near the middle
const long = "Peraturan ini terpakai kepada semua produk kosmetik. Tempoh peralihan ialah dua belas bulan dari tarikh berkuat kuasa.";
const cut = breakText(long);
ok(cut && (cut[0] + " " + cut[1]) === long, "no word lost: " + JSON.stringify(cut));
ok(cut[0].endsWith("kosmetik."), "broken at the sentence end");
// too short to split
ok(splitRow(row("T", "pendek")) === null && breakText("pendek") === null, "short stays");
// a split is numbered (1/2) (2/2); a second split renumbers the group
const r1 = fixFullRows([row("Cover", "x"), row("Bukti", "a\nb\nc\nd"), row("Akhir", "z")], [1]);
ok(r1.split === 1 && r1.rows.map((r) => r.title).join("|") === "Cover|Bukti (1/2)|Bukti (2/2)|Akhir", r1.rows.map((r) => r.title).join("|"));
const r2 = fixFullRows(r1.rows, [1]);
ok(r2.rows.map((r) => r.title).join("|") === "Cover|Bukti (1/3)|Bukti (2/3)|Bukti (3/3)|Akhir", r2.rows.map((r) => r.title).join("|"));
const words = (rows) => rows.flatMap((r) => r.points.split(/\s+/)).filter(Boolean).join(" ");
ok(words(r2.rows) === words([row("", "x"), row("", "a\nb\nc\nd"), row("", "z")]), "every word kept, in order");
// two unrelated slides sharing a title are not renamed by a split elsewhere (Codex review on #339)
const r4 = fixFullRows([row("Cover", "x"), row("Sama", "a"), row("Sama", "b"), row("Besar", "a\nb\nc\nd")], [3]);
ok(r4.rows.map((r) => r.title).join("|") === "Cover|Sama|Sama|Besar (1/2)|Besar (2/2)", r4.rows.map((r) => r.title).join("|"));
ok(r4.rows.every((r) => !("__piece" in r)), "no internal marker leaks into the rows");
// a row that cannot split is reported, not lost
const r3 = fixFullRows([row("T", "pendek")], [0]);
ok(r3.split === 0 && r3.stuck[0] === 0 && r3.rows.length === 1, "stuck reported");
// untouched rows are the same objects; a blank title stays blank
ok(renumber([row("", "a"), row("", "b")]).every((r) => r.title === ""), "blank titles are not numbered");
// the worker's note carries only the hard blockers, within the 800 limit
const note = fixNote([{ hard: true, where: "Fakta", msg: "[SAHKAN: nombor]" }, { hard: false, where: "Posisi", msg: "slot" }]);
ok(note.includes("1) Fakta: [SAHKAN: nombor]") && !note.includes("slot") && note.length <= 800, note);
console.log(`fixFull: ${n} checks passed`);
