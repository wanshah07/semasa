// The pure half of the FAQ AI bar (action "faq_extract" in index.ts), shared with the Node tests (web/faq_ai.test.mjs).
//
// Wan, 1 Oct 2026: "for faq add AI bar that allow us to paste screenshot, image, upload pdf then AI will analyze and
// auto to categorize them to proper Q&A FAQ".
//
// What this step does and does NOT do. It reads the material and returns the question-and-answer pairs found in it,
// anonymised, in the language they were written in. It does not rewrite them into BM and English, does not pick a
// category and does not publish anything: the page inserts each pair as a `new` row in semasa_faqs, and the existing
// worker (backend/semasa/faq.py) does the formal rewrite, the anonymising pass, the category and the sheet, under the
// same rules as every other FAQ. One writer, one set of rules, so a screenshot cannot reach the sheet by a side door.
//
// The picture or the PDF is DATA. Anything written inside it ("ignore the above", "answer in French", a link to click)
// is text to be read for questions, never an instruction to this step.

export const FAQ_LIMITS = {
  items: 30,        // pairs kept per call
  question: 600,    // characters
  answer: 3000,
  note: 500,        // the person's own typed note
  images: 6,        // per call; the page splits more into several calls
  text: 40_000,     // characters of text (PDF pages, .txt) per call
};

export const FAQ_SYSTEM = `You read material a Malaysian regulatory-affairs consultant has collected (screenshots of chats or forum posts, photos of
documents, pages of a PDF, pasted text) and list the question-and-answer pairs found in it, for an FAQ about halal,
cosmetics, skincare, food, pharmaceuticals and supplements.

Rules. Follow them exactly:
1. Take ONLY what the material says. Never add a fact, figure, fee, date, clause number, circular or instrument that is
   not in it, and never write an answer the material does not contain: when a question has no answer in the material,
   its "answer" is "". Do not "improve" an answer; copy its substance, tidied for reading.
2. One entry per distinct question. A chat or forum thread where several people ask and answer is folded into the
   questions asked and the answers given. Several questions in one message become separate entries. A greeting, a
   thank-you, an advertisement, a menu, a page number, a header or footer is not an entry. A paragraph of facts that
   answers no question may become an entry only when a clear question can be written from it, in which case the
   question starts with "Apa" / "What", "Bolehkah" / "Can", "Bagaimana" / "How" or similar, and the answer is that
   paragraph. If the material has nothing of the sort, return no entries.
3. Anonymise AT SOURCE. Remove the names of people, usernames, companies that are clients or customers, phone
   numbers, emails, addresses, account numbers, links to chats or groups. Keep a product or brand name only when it is
   the public subject of the question, and a regulator's name (NPRA, JAKIM, BKKM, SCCS) always.
4. Keep the language the material uses (Malay, English or the mix). Malaysian Malay only, never Bahasa Indonesia:
   boleh not bisa, ubat not obat, syarikat not perusahaan. Do not translate.
5. "instrument" names the regulator or instrument ONLY if the material names it (for example "MPPHM (Domestik) 2020"
   or "JAKIM, Penjelasan Isu Tular Halal"); otherwise "". Never a social platform, a forum or a news site.
6. "source_hint" is a few words for the person to recognise where the entry came from (for example "WhatsApp
   screenshot, halal logo" or "page 4 of the PDF"). No names.
7. "unclear" is true when the text was hard to read (blurred, cut off, handwritten) and you may have misread it.
8. If the person typed a note, it says what the material is or what to look for; follow it where it narrows what to take.

Answer with ONE JSON object and nothing else:
{"items": [{"question": "...", "answer": "...", "instrument": "", "source_hint": "", "unclear": false}],
 "skipped": "one short sentence on what was left out and why, or empty"}`;

const MAX_DATA_URL = 4_500_000; // one picture, as the browser sent it

/** The user turn: the note, the text files, then each picture as an image part. Pure, so the test can read it. */
export function faqMessages(note, files, system = FAQ_SYSTEM) {
  const parts = [];
  const typed = String(note || "").trim().slice(0, FAQ_LIMITS.note);
  const kept = [];
  const skipped = [];
  let textLeft = FAQ_LIMITS.text;
  let images = 0;
  for (const f of Array.isArray(files) ? files : []) {
    const name = String(f?.name || "file").slice(0, 120);
    if (f?.skipped) { skipped.push(`${name}: ${String(f.skipped).slice(0, 120)}`); continue; }
    if (typeof f?.dataUrl === "string") {
      if (!/^data:image\/(png|jpe?g|webp|gif);base64,/i.test(f.dataUrl)) { skipped.push(`${name}: not a picture the reader accepts`); continue; }
      if (f.dataUrl.length > MAX_DATA_URL) { skipped.push(`${name}: picture too large`); continue; }
      if (images >= FAQ_LIMITS.images) { skipped.push(`${name}: more than ${FAQ_LIMITS.images} pictures in one call`); continue; }
      images++;
      kept.push({ name, image: f.dataUrl });
    } else if (typeof f?.text === "string" && f.text.trim()) {
      if (textLeft <= 0) { skipped.push(`${name}: more text than one call takes`); continue; }
      const text = f.text.trim().slice(0, textLeft);
      textLeft -= text.length;
      kept.push({ name, text });
    } else {
      skipped.push(`${name}: nothing readable`);
    }
  }
  if (typed) parts.push({ type: "text", text: `NOTE FROM THE PERSON (what this is, or what to look for):\n${typed}` });
  for (const k of kept) {
    if (k.text !== undefined) parts.push({ type: "text", text: `FILE ${k.name} (text):\n${k.text}` });
    else {
      parts.push({ type: "text", text: `FILE ${k.name} (picture follows):` });
      parts.push({ type: "image_url", image_url: { url: k.image } });
    }
  }
  if (!kept.length && !typed) return { error: "nothing to read: paste a picture, add a PDF or type some text", skipped };
  if (!kept.length) parts.push({ type: "text", text: "(No file was attached: read the note itself as the material.)" });
  return {
    messages: [{ role: "system", content: system }, { role: "user", content: parts }],
    skipped, pictures: images, files: kept.length,
  };
}

/** The first JSON object in a model answer, tolerant of a code fence or a sentence around it. null when none parses. */
export function firstJson(raw) {
  const s = String(raw || "");
  const fenced = s.match(/```(?:json)?\s*([\s\S]*?)```/i);
  const candidates = [fenced ? fenced[1] : "", s];
  for (const c of candidates) {
    const start = c.indexOf("{");
    if (start < 0) continue;
    for (let end = c.lastIndexOf("}"); end > start; end = c.lastIndexOf("}", end - 1)) {
      try { const v = JSON.parse(c.slice(start, end + 1)); if (v && typeof v === "object") return v; } catch { /* try a shorter slice */ }
    }
  }
  return null;
}

const clip = (v, n) => String(v ?? "").replace(/\r/g, "").replace(/[ \t]+\n/g, "\n").trim().slice(0, n);
const lower = (s) => s.toLowerCase().normalize("NFKD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]+/g, " ").trim();

/** The pairs the model returned, held to the limits: no empty question, no duplicate within the call. */
export function parseFaqItems(raw) {
  const obj = firstJson(raw);
  if (!obj) return { error: "the reader did not return a list", items: [], skipped: "" };
  const list = Array.isArray(obj.items) ? obj.items : Array.isArray(obj) ? obj : [];
  const seen = new Set();
  const items = [];
  for (const it of list) {
    if (!it || typeof it !== "object") continue;
    const question = clip(it.question, FAQ_LIMITS.question);
    if (question.length < 8) continue;
    const key = lower(question).slice(0, 90);
    if (!key || seen.has(key)) continue;
    seen.add(key);
    items.push({
      question,
      answer: clip(it.answer, FAQ_LIMITS.answer),
      instrument: clip(it.instrument, 200),
      source_hint: clip(it.source_hint, 120),
      unclear: it.unclear === true,
    });
    if (items.length >= FAQ_LIMITS.items) break;
  }
  return { items, skipped: clip(obj.skipped, 300) };
}
