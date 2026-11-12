import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { BUILTIN_FAMILIES, DEFAULT_GUIDANCE, SERIES, builtinCopy, builtinNumbered, quickShape } from "./src/lib/hookBank.js";

// the page's copy of the 25 is the worker's, word for word and in the same order
const py = readFileSync(new URL("../backend/semasa/hook_bank.py", import.meta.url), "utf8").replace(/\r\n/g, "\n");
const block = py.slice(py.indexOf("FAMILIES = {"), py.indexOf("\n}\n", py.indexOf("FAMILIES = {")));
const fromPy = {};
for (const m of block.matchAll(/"(\w+)":\s*\[([\s\S]*?)\]/g)) fromPy[m[1]] = [...m[2].matchAll(/"((?:[^"\\]|\\.)*)"/g)].map((x) => x[1]);
assert.deepEqual(BUILTIN_FAMILIES, fromPy, "web/src/lib/hookBank.js must match backend/semasa/hook_bank.py FAMILIES");
const series = /SERIES = \(([^)]*)\)/.exec(py)[1].match(/"(\w+)"/g).map((x) => x.replace(/"/g, ""));
assert.deepEqual(SERIES, series, "the series order (the shape numbers) must match");
// DEFAULT_GUIDANCE may span several lines and contain ")" inside the text, so take from the opening paren to the line
// that closes the statement (a line ending in `")`).
const gStart = py.indexOf("DEFAULT_GUIDANCE = (");
const gEnd = py.indexOf('")\n', gStart) + 1;   // include the closing quote so the last string literal is a full match
const guidance = py.slice(gStart, gEnd).match(/"(?:[^"\\]|\\.)*"/g).map((x) => x.slice(1, -1)).join("");
assert.equal(DEFAULT_GUIDANCE, guidance, "the copy's starting instruction is the worker's default guidance");

const n = builtinNumbered();
assert.equal(n.length, 25); assert.deepEqual([n[0].n, n[0].family], [1, "curiosity"]); assert.deepEqual([n[15].n, n[15].family], [16, "bold"]);
assert.equal(n[24].text, "Orang lain: ___. Aku: masih pikir ___");

const copy = builtinCopy("  ", "u1");
assert.equal(copy.name, "Bank hook saya"); assert.equal(copy.source, "manual"); assert.equal(copy.status, "ready");
assert.deepEqual(copy.images, []); assert.equal(copy.created_by, "u1"); assert.equal(copy.shapes.length, 25);
assert.deepEqual(copy.shapes[0], { family: "curiosity", text: "Takde sapa cakap pasal ___ tapi ni sebab aku ___" });
assert.equal(builtinCopy("x".repeat(80), "u").name.length, 60);

assert.equal(quickShape("bold | Jangan ___ kalau ___"), "bold | Jangan ___ kalau ___");
assert.equal(quickShape("Kenapa ____ masih ___"), "Kenapa ___ masih ___", "any run of underscores becomes the house blank");
assert.equal(quickShape("other | Semua tentang ___ hari ini"), "Semua tentang ___ hari ini");
assert.equal(quickShape("weird | Tentang ___ lagi"), "weird | Tentang ___ lagi", "an unknown family is kept as text");
assert.equal(quickShape("Tiada tempat kosong"), "", "a line with no blank is not a shape");
assert.equal(quickShape("___ ___"), "", "nothing fixed around the blanks");
assert.equal(quickShape(`${"a".repeat(170)} ___`), "");
console.log("hookBank.test.mjs: ok");
