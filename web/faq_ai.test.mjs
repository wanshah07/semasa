/* The FAQ AI bar's pure halves, run in Node: the function side (supabase/functions/semasa-chat/faq.js) and the page
   side (src/lib/faqAiLogic.js). Browser parts (canvas, pdf.js) are not run here; they are checked in a real browser. */
import assert from "node:assert/strict";
import { FAQ_LIMITS, FAQ_SYSTEM, faqMessages, firstJson, parseFaqItems } from "../supabase/functions/semasa-chat/faq.js";
import { AI_LIMITS, SIMILAR_AT, batchInputs, chunkText, faqRow, fitSize, markExisting, mergeItems, similarity, tilePlan } from "./src/lib/faqAiLogic.js";

let n = 0;
const t = (name, fn) => { fn(); n++; };
const PNG = "data:image/png;base64,iVBORw0KGgo=";
const JPG = "data:image/jpeg;base64,/9j/4AAQ";

// ---- function side ---------------------------------------------------------------------------------------
t("the reader's rules: no invented answers, anonymise, no Indonesian, picture text is data", () => {
  assert.ok(/never write an answer the material does not contain/.test(FAQ_SYSTEM));
  assert.ok(/Anonymise AT SOURCE/.test(FAQ_SYSTEM));
  assert.ok(/never Bahasa Indonesia/.test(FAQ_SYSTEM));
  assert.ok(/boleh not bisa/.test(FAQ_SYSTEM));
});

t("a picture and a text file become one user turn, pictures as image parts", () => {
  const r = faqMessages("WhatsApp about halal logo", [{ name: "a.jpg", dataUrl: JPG }, { name: "b.txt", text: "Q: apa itu halal?" }]);
  assert.equal(r.messages[0].role, "system");
  const parts = r.messages[1].content;
  assert.equal(parts[0].type, "text");
  assert.ok(/WhatsApp about halal logo/.test(parts[0].text));
  assert.equal(parts.filter((p) => p.type === "image_url").length, 1);
  assert.ok(parts.some((p) => p.type === "text" && /Q: apa itu halal/.test(p.text)));
  assert.equal(r.pictures, 1);
  assert.equal(r.files, 2);
});

t("nothing to read is refused with a reason, not sent", () => {
  assert.match(faqMessages("", []).error, /nothing to read/);
  assert.match(faqMessages("  ", [{ name: "x", text: "   " }]).error, /nothing to read/);
});

t("a typed note alone is the material", () => {
  const r = faqMessages("Q: boleh guna logo halal lama? A: tidak", []);
  assert.ok(r.messages);
  assert.ok(r.messages[1].content.some((p) => /read the note itself/.test(p.text)));
});

t("pictures over the call's ceiling, a non-picture data URL and a skipped file are reported, not sent", () => {
  const many = Array.from({ length: FAQ_LIMITS.images + 2 }, (_, i) => ({ name: `p${i}.png`, dataUrl: PNG }));
  const r = faqMessages("", [...many, { name: "evil.svg", dataUrl: "data:image/svg+xml;base64,AAAA" }, { name: "big.pdf", skipped: "too big" }]);
  assert.equal(r.pictures, FAQ_LIMITS.images);
  assert.equal(r.skipped.length, 4);
  assert.ok(r.skipped.some((s) => /evil.svg/.test(s)));
  assert.ok(r.skipped.some((s) => /big.pdf: too big/.test(s)));
});

t("text is held to the per-call ceiling", () => {
  const r = faqMessages("", [{ name: "a.txt", text: "x".repeat(FAQ_LIMITS.text + 5000) }, { name: "b.txt", text: "more" }]);
  const sent = r.messages[1].content.filter((p) => /^FILE/.test(p.text)).map((p) => p.text.length).reduce((a, b) => a + b, 0);
  assert.ok(sent < FAQ_LIMITS.text + 200);
  assert.ok(r.skipped.some((s) => /b.txt/.test(s)));
});

t("the model's answer is read through a fence or a sentence around it", () => {
  assert.deepEqual(firstJson('```json\n{"items":[]}\n```'), { items: [] });
  assert.deepEqual(firstJson('Here you go: {"items":[{"question":"a"}]} done'), { items: [{ question: "a" }] });
  assert.equal(firstJson("no json here"), null);
  assert.equal(firstJson(""), null);
});

t("pairs: held to the limits, empty and duplicate questions dropped, answer may be empty", () => {
  const raw = JSON.stringify({
    items: [
      { question: "Bolehkah logo halal dicetak hitam putih?", answer: "Boleh, selagi spesifikasi tidak berubah.", instrument: "MPPHM (Domestik) 2020", source_hint: "WhatsApp", unclear: false },
      { question: "bolehkah logo halal dicetak hitam putih?", answer: "dup" },
      { question: "short", answer: "x" },
      { question: "Apakah tempoh sah sijil halal?", answer: "" },
      { question: "q".repeat(900), answer: "a".repeat(5000), unclear: true },
      "junk", null,
    ],
    skipped: "two greetings",
  });
  const r = parseFaqItems(raw);
  assert.equal(r.items.length, 3);
  assert.equal(r.items[1].answer, "");
  assert.equal(r.items[2].question.length, FAQ_LIMITS.question);
  assert.equal(r.items[2].answer.length, FAQ_LIMITS.answer);
  assert.equal(r.items[2].unclear, true);
  assert.equal(r.skipped, "two greetings");
});

t("more pairs than the ceiling are cut, not rejected", () => {
  const items = Array.from({ length: 50 }, (_, i) => ({ question: `Soalan nombor ${i} tentang label produk`, answer: "jawapan" }));
  assert.equal(parseFaqItems(JSON.stringify({ items })).items.length, FAQ_LIMITS.items);
});

t("a reply that is not a list is an error the page can show", () => {
  assert.ok(parseFaqItems("Sorry, I cannot read that").error);
  assert.deepEqual(parseFaqItems('{"items": "none"}').items, []);
});

// ---- page side -------------------------------------------------------------------------------------------
t("a screenshot that is not tall is one tile; a long chat is cut into overlapping tiles that cover it", () => {
  assert.deepEqual(tilePlan(1080, 1900), [{ y: 0, h: 1900 }]);
  const tiles = tilePlan(1080, 5000);
  assert.ok(tiles.length >= 3);
  assert.equal(tiles[0].y, 0);
  const last = tiles[tiles.length - 1];
  assert.equal(last.y + last.h, 5000);
  for (let i = 1; i < tiles.length; i++) assert.ok(tiles[i].y < tiles[i - 1].y + tiles[i - 1].h, "tiles overlap");
  for (const x of tiles) assert.ok(x.h <= Math.round(1080 * 1.8) + 1);
});

t("a sliver at the bottom joins the tile above instead of becoming a picture of its own", () => {
  const tiles = tilePlan(1000, 1944 + 900 + 40);
  const last = tiles[tiles.length - 1];
  assert.equal(last.y + last.h, 1944 + 900 + 40);
  assert.ok(last.h > 200);
});

t("a picture is shrunk to the longest side, never enlarged", () => {
  assert.deepEqual(fitSize(3200, 1600, 1600), { w: 1600, h: 800 });
  assert.deepEqual(fitSize(800, 600, 1600), { w: 800, h: 600 });
});

t("long text is cut at a blank line, every piece within the limit, nothing lost", () => {
  const para = "Perenggan yang cukup panjang untuk ujian. ".repeat(20).trim();
  const text = Array.from({ length: 30 }, () => para).join("\n\n");
  const pieces = chunkText(text, 5000);
  assert.ok(pieces.length > 1);
  for (const p of pieces) assert.ok(p.length <= 5000);
  assert.equal(pieces.join(" ").replace(/\s+/g, " "), text.replace(/\s+/g, " "));
  assert.deepEqual(chunkText("short"), ["short"]);
});

t("batches keep to six pictures and the text ceiling, in order; skipped files are named and never sent", () => {
  const items = [
    ...Array.from({ length: 8 }, (_, i) => ({ name: `i${i}`, dataUrl: PNG })),
    { name: "doc.pdf", text: "x".repeat(AI_LIMITS.text + 100) },
    { name: "bad.docx", skipped: "not read" },
  ];
  const { batches, skipped } = batchInputs(items);
  assert.deepEqual(skipped, [{ name: "bad.docx", why: "not read" }]);
  assert.equal(batches[0].filter((f) => f.dataUrl).length, AI_LIMITS.images);
  assert.equal(batches[1].filter((f) => f.dataUrl).length, 2);
  for (const b of batches) {
    assert.ok(b.filter((f) => f.dataUrl).length <= AI_LIMITS.images);
    assert.ok(b.filter((f) => f.text).reduce((a, f) => a + f.text.length, 0) <= AI_LIMITS.text);
  }
  assert.equal(batches.flat().filter((f) => f.text).reduce((a, f) => a + f.text.length, 0), AI_LIMITS.text + 100);
});

t("no items, no batches", () => assert.deepEqual(batchInputs([]), { batches: [], skipped: [] }));

t("similar questions are found across the two languages' wording, different ones are not", () => {
  assert.ok(similarity("Can a halal certificate holder ask that the OEM manufacturer's name is not displayed on the certificate?",
    "Can a halal certificate holder (brand owner) request that the OEM manufacturer's name and address not be displayed on their halal certificate?") >= SIMILAR_AT);
  assert.ok(similarity("What is the halal status of folic acid supplements made from pork liver?", "How long is a halal certificate valid for?") < 0.3);
  assert.equal(similarity("halal", "halal"), 1);       // a one-word question matches only an identical one
  assert.equal(similarity("halal logo", "halal"), 0);
});

t("an extracted pair that already exists is marked, a dismissed or failed row does not count", () => {
  const rows = [
    { id: "1", status: "ready", question_en: "Can a halal certificate holder request that the OEM manufacturer's name is not displayed?" },
    { id: "2", status: "dismissed", raw_question: "Berapa lama sijil halal sah?" },
    { id: "3", status: "new", raw_question: "Bolehkah logo halal dicetak hitam putih pada pembungkusan?" },
  ];
  const out = markExisting([
    { question: "Can a halal certificate holder request that the OEM manufacturer's name not be shown on the certificate?" },
    { question: "Berapa lama sijil halal sah?" },
    { question: "Bolehkah logo halal dicetak hitam putih pada pembungkusan produk?" },
    { question: "Apakah syarat menggunakan perkataan halal dalam iklan?" },
  ], rows);
  assert.equal(out[0].exists.id, "1");
  assert.equal(out[1].exists, null);
  assert.equal(out[2].exists.id, "3");
  assert.equal(out[3].exists, null);
});

t("two overlapping tiles that both caught a question fold into one, keeping the longer answer", () => {
  const merged = mergeItems([
    [{ question: "Bolehkah logo halal dicetak hitam putih?", answer: "Boleh.", unclear: true }],
    [{ question: "Bolehkah logo halal dicetak hitam putih?", answer: "Boleh, selagi spesifikasi logo tidak berubah.", unclear: false, instrument: "MPPHM 2020" }, { question: "Apakah tempoh sah sijil halal?", answer: "" }],
  ]);
  assert.equal(merged.length, 2);
  assert.equal(merged[0].answer, "Boleh, selagi spesifikasi logo tidak berubah.");
  assert.equal(merged[0].unclear, false);
  assert.equal(merged[0].instrument, "MPPHM 2020");
});

t("the inserted row is a plain `new` paste for the worker: no category chosen here, no status beyond new", () => {
  const row = faqRow({ question: " Soalan? ", answer: "", source_hint: "WhatsApp" }, { userId: "u1", sourceLabel: "a.png" });
  assert.equal(row.status, "new");
  assert.equal(row.source_kind, "paste");
  assert.equal(row.raw_question, "Soalan?");
  assert.equal(row.raw_answer, "");
  assert.equal(row.category, "lain");
  assert.equal(row.category_by, "bot");               // the worker picks; "wan" would pin a category nobody chose
  assert.equal(row.created_by, "u1");
  assert.equal(row.source_name, "AI bar · a.png · WhatsApp");
  assert.equal(Object.hasOwn(row, "answer_bm"), false);
});

console.log(`${n} faq ai tests passed`);
