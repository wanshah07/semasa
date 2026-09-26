// The slide -> Studio card mapping (web/src/lib/cards/studio.js, specsFor). The drawing itself is tested in a real
// browser by backend/tests/test_studio_cards.py; this checks the one rule the mapping owns: every point of every
// slide reaches a card, whatever the look. `npm test`.
import { specsFor, LOOKS, STUDIO_LOOKS } from "./src/lib/cards/studio.js";

let failed = 0;
const ok = (cond, what) => { if (!cond) { failed++; console.error("FAIL", what); } };
const words = (spec) => [spec.title, spec.lead, ...(spec.items || [])].join("\n");
// how many items each template actually draws (Studio slices its lists)
const SHOWN = { e_hook: 3, e_explain: 3, p_fact: 4, g_title: 0, p_title: 0, p_quote: 0 };

const P = (n) => Array.from({ length: n }, (_, i) => `Poin nombor ${i + 1} yang penting.`);
const decks = [
  [{ title: "Kulit", points: [] }, { title: "Satu", points: P(1) }, { title: "Tutup", points: P(2) }],
  [{ title: "Kulit", points: P(5) }, { title: "Lima", points: P(5) }, { title: "Empat", points: P(4) }, { title: "Tutup", points: P(3) }],
  [{ title: "Poster sahaja", points: P(5) }],
];
for (const look of STUDIO_LOOKS) {
  for (const deck of decks) {
    const specs = specsFor(deck, { look, stream: "regulab", eyebrow: "Kosmetik", citation: "NPRA, Garis Panduan" });
    ok(specs.length === deck.length, `${look}: one card per slide`);
    specs.forEach((sp, i) => {
      for (const p of deck[i].points) ok(words(sp).includes(p), `${look} slide ${i + 1} (${sp.template}) keeps "${p}"`);
      ok((sp.items || []).length <= SHOWN[sp.template], `${look} slide ${i + 1}: ${sp.template} draws all ${(sp.items || []).length} items`);
      ok(words(sp).includes(deck[i].title), `${look} slide ${i + 1} keeps its title`);
      const last = i === deck.length - 1;
      ok(last ? sp.footnote === "NPRA, Garis Panduan" && sp.chip_label === "Sumber" : !sp.footnote, `${look} slide ${i + 1}: source on the closing slide only`);
      ok(sp.eyebrow === "Kosmetik", `${look}: eyebrow on every slide`);
    });
  }
}
// the templates Studio's own groups name
const g = (look) => specsFor(decks[0], { look }).map((s) => s.template).join(",");
ok(g("grid") === "g_title,g_title,g_title", "grid is g_title throughout, like Studio's Grid group");
ok(g("era") === "e_hook,e_explain,e_explain", "era: hook cover, explainer after, like Studio's Info ERA group");
ok(g("photo") === "p_title,p_fact,p_quote", "photo: title, fact, quote, like Studio's Photo group");
// LinkedIn: English source label, heavier scrim (Studio's defaults for that stream)
const li = specsFor(decks[0], { look: "grid", stream: "linkedin", citation: "EC 1223/2009" });
ok(li.at(-1).chip_label === "Source" && li[0].scrim === "heavy" && li[0].stream === "linkedin", "linkedin label and scrim");
ok(specsFor(decks[0], { look: "grid", size: [1080, 1920] })[0].size[1] === 1920, "a Design shape reaches the card");
ok(LOOKS.map((l) => l.k).join(",") === "classic,grid,era,photo", "the four looks, Semasa's own first");

if (failed) { console.error(`${failed} card mapping check(s) failed`); process.exit(1); }
console.log("cards: slide -> Studio card mapping keeps every word");
