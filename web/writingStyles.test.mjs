import assert from "node:assert/strict";
import { NONE, activeId, addRefusal, isReady, linksFrom, pickOptions, sourcesLine, summaryLine, textToTraits, traitsToText, withWritingStyle } from "./src/lib/writingStyles.js";

const t = (bm) => bm;
const ready = { id: "a", status: "ready", name: "Santai", instruction: "Ayat pendek, nada tenang, tamat dengan soalan." };
const busy = { id: "b", status: "working", name: "Baru" };
const thin = { id: "c", status: "ready", name: "Nipis", instruction: "pendek" };
assert.equal(isReady(ready), true); assert.equal(isReady(busy), false); assert.equal(isReady(thin), false, "an instruction too short to use");
assert.equal(activeId({ id: "a" }, [ready]), "a"); assert.equal(activeId({ id: "b" }, [ready, busy]), NONE); assert.equal(activeId({}, [ready]), NONE);
assert.equal(activeId({ id: "gone" }, [ready]), NONE);
const opts = pickOptions([ready, busy, thin], t, { id: "a" });
assert.deepEqual(opts.map((o) => o[0]), ["", NONE, "a"], "only ready styles can be chosen");
assert.match(opts[0][1], /Santai/);
assert.deepEqual(withWritingStyle({ x: 1 }, "a"), { x: 1, writing_style: "a" });
assert.deepEqual(withWritingStyle({ x: 1, writing_style: "a" }, ""), { x: 1 });
assert.deepEqual(withWritingStyle(undefined, NONE), { writing_style: NONE });

const l = linksFrom("https://www.linkedin.com/posts/a\nhttps://www.linkedin.com/posts/a  javascript:alert(1) ftp://x\nwww.no-scheme.com\nhttps://b.my/p),\nhttp://localhost/x");
assert.deepEqual(l.links, ["https://www.linkedin.com/posts/a", "https://b.my/p"]);
assert.deepEqual(l.bad, ["javascript:alert(1)", "ftp://x", "www.no-scheme.com", "http://localhost/x"]);
const many = linksFrom(Array.from({ length: 10 }, (_, i) => `https://x.com/${i}`).join(" "));
assert.equal(many.links.length, 8); assert.equal(many.over, 2);

assert.match(addRefusal({}, t), /sekurang-kurangnya/);
assert.match(addRefusal({ sample: "pendek" }, t), /80 aksara/);
assert.equal(addRefusal({ sample: "x".repeat(80) }, t), "");
assert.equal(addRefusal({ links: ["https://a.my"] }, t), "");
assert.match(addRefusal({ files: [{ name: "a.pdf", type: "application/pdf" }] }, t), /a\.pdf/);
assert.match(addRefusal({ files: Array.from({ length: 9 }, () => ({ name: "a.png", type: "image/png" })) }, t), /Paling banyak 8/);
assert.match(addRefusal({ sample: "x".repeat(12001) }, t), /terlalu panjang/);

assert.deepEqual(textToTraits("- Ayat pendek\n\n• Nada tenang\nx\n" + "y".repeat(200)), ["Ayat pendek", "Nada tenang", "y".repeat(140)]);
assert.equal(textToTraits(Array.from({ length: 12 }, (_, i) => `ciri ${i}`).join("\n")).length, 8);
assert.equal(traitsToText(["a", "b"]), "a\nb");
assert.equal(summaryLine({ status: "ready", source: "manual" }, t), "Ditulis sendiri");
assert.equal(summaryLine({ status: "ready", traits: [1, 2] }, t), "2 ciri");
assert.equal(summaryLine({ status: "error", error: "x" }, t), "x");
assert.equal(sourcesLine({ links: ["a", "b"], sample: " s ", images: ["i"] }, t), "2 pautan · teks ditampal · 1 tangkapan skrin");
console.log("writingStyles.test.mjs: ok");
