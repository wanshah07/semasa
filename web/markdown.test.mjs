/* The chat's Markdown reader (src/lib/markdown.js): what it draws, and what it must never let through. */
import assert from "node:assert/strict";
import { inline, parseMarkdown, plainText } from "./src/lib/markdown.js";

let n = 0;
const t = (name, fn) => { try { fn(); n++; } catch (e) { console.error("FAIL:", name); throw e; } };
const types = (nodes) => nodes.map((x) => x.t);

t("inline marks: bold, italic, code, links, line breaks; a backslash escapes a mark", () => {
  const r = inline("a **b** *c* `d` [e](https://x.my/p?q=1) f\\*g\nh");
  assert.deepEqual(types(r), ["text", "strong", "text", "em", "text", "code", "text", "link", "text", "br", "text"]);
  assert.equal(r[7].href, "https://x.my/p?q=1");
  assert.equal(r[8].s, " f*g");
});

t("a bare https address becomes a link and a full stop after it stays prose; only http(s) and mailto are ever links", () => {
  const r = inline("Lihat https://www.npra.gov.my/index.php/ms. Kemudian [x](javascript:alert(1)) dan [y](mailto:a@b.my).");
  assert.equal(r[1].t, "link"); assert.equal(r[1].href, "https://www.npra.gov.my/index.php/ms");
  assert.ok(!r.some((x) => x.t === "link" && /javascript/.test(x.href)), "a javascript: link is text");
  assert.ok(r.some((x) => x.t === "text" && x.s === "x"));
  assert.ok(r.some((x) => x.t === "link" && x.href === "mailto:a@b.my"));
});

t("HTML is never a node: a tag is text", () => {
  const r = inline("<script>alert(1)</script> <b>x</b>");
  assert.deepEqual(types(r), ["text"]);
  assert.equal(r[0].s, "<script>alert(1)</script> <b>x</b>");
});

t("blocks: headings, paragraphs, fenced code, lists with nesting, quotes, tables, rules", () => {
  const md = ["## Jawapan", "Baris satu", "baris dua", "", "```json", '{"a": 1}', "```", "- satu", "- dua", "  - anak", "1. a", "2. b", "> petikan", "> lagi", "", "| Entri | Had |", "|---|---|", "| 12 | 2% |", "| 13 | 0.1% |", "---", "Akhir"];
  const b = parseMarkdown(md.join("\n"));
  assert.deepEqual(types(b), ["h", "p", "code", "ul", "ol", "quote", "table", "hr", "p"]);
  assert.equal(b[0].n, 2);
  assert.equal(b[2].lang, "json"); assert.equal(b[2].s, '{"a": 1}');
  assert.equal(b[3].items.length, 2);
  assert.equal(b[3].items[1].children[0].t, "ul");
  assert.equal(b[4].items.length, 2);
  assert.equal(b[5].children[0].t, "p");
  assert.deepEqual(b[6].head.map((c) => c[0].s), ["Entri", "Had"]);
  assert.equal(b[6].rows.length, 2);
  assert.equal(b[1].c.filter((x) => x.t === "br").length, 1, "a soft line break inside a paragraph is kept");
});

t("a heading deeper than ### is drawn as ###, and an unclosed fence runs to the end", () => {
  const b = parseMarkdown("###### deep\n```\nx\ny");
  assert.equal(b[0].n, 3);
  assert.equal(b[1].s, "x\ny");
});

t("plain text for the copy button keeps the words and the list shape, drops the marks", () => {
  const p = plainText(parseMarkdown("## T\n**a** and `b`\n- x\n- y\n\n| h |\n|---|\n| v |"));
  assert.equal(p, "T\n\na and b\n\n- x\n- y\n\nh\nv");
});

t("empty and odd input is fine", () => {
  assert.deepEqual(parseMarkdown(""), []);
  assert.deepEqual(parseMarkdown(null), []);
  assert.deepEqual(inline("**"), [{ t: "text", s: "**" }]);
  assert.deepEqual(inline("*"), [{ t: "text", s: "*" }]);
  assert.equal(parseMarkdown("a * b * c")[0].c.length, 1, "spaced asterisks are not emphasis");
});

console.log(`markdown: ${n} ok`);
