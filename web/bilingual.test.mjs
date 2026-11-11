/* Wan, 11 Nov 2026: "if in english version, all must write in english, same goes to malay". A message thrown from a library
   must be in ONE language (lib/bi.js), never "tiada teks / no text in it". This reads every lib file and fails on a string
   literal that carries a Malay phrase and an English one joined by " / ". */
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { bi } from "./src/lib/bi.js";

const MALAY = /\b(tiada|gagal|melebihi|belum|dibaca|sedang|tidak|boleh|simpan|fail|sudah|dan)\b/i;
const ENGLISH = /\b(not|over|could|failed|the|is|no|was|are|read|empty)\b/i;
const bad = [];
for (const name of readdirSync("./src/lib").filter((n) => n.endsWith(".js"))) {
  readFileSync(`./src/lib/${name}`, "utf8").split("\n").forEach((line, i) => {
    for (const m of line.matchAll(/(["`])((?:\\.|(?!\1).)*?)\1/g)) {
      const body = m[2];
      if (!/ \/ /.test(body) || /https?:|\/\/|\.\/|\w\/\w/.test(body.replace(/ \/ /g, ""))) continue;
      const [a, b] = body.split(" / ");
      if (b !== undefined && MALAY.test(a) && ENGLISH.test(b) && /[a-z]{3}/i.test(a)) bad.push(`${name}:${i + 1}: ${body.slice(0, 80)}`);
    }
  });
}
assert.deepEqual(bad, [], `strings carrying both languages: ${bad.join(" | ")}`);

globalThis.__semasaLang = "bm";
assert.equal(bi("tiada teks", "no text"), "tiada teks");
globalThis.__semasaLang = "en";
assert.equal(bi("tiada teks", "no text"), "no text");
delete globalThis.__semasaLang;
console.log("bilingual: ok");
