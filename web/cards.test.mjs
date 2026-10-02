// The slide -> Studio card mapping (web/src/lib/cards/studio.js, specsFor). The drawing itself is tested in a real
// browser by backend/tests/test_studio_cards.py; this checks the one rule the mapping owns: every point of every
// slide reaches a card, whatever the look. `npm test`.
import { specsFor, LOOKS, STUDIO_LOOKS } from "./src/lib/cards/studio.js";
import { cardFromCaption, headAndRest, slidesFromCaption } from "./src/lib/cards/fromCaption.js";

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

// Studio's per-slide editor (27 Sep 2026): a slide's own design wins over the look's choice
const M = [{ k: "wave", url: "/m/wave.webp" }, { k: "point", url: "/m/point.webp" }, { k: "confused", url: "/m/confused.webp" }];
const own = specsFor([
  { title: "Had", points: ["Malaysia | 0.5 | 0.5%", "EU | 0.4 | 0.4%"], template: "g_bars", lead: "angka contoh", eyebrow: "ACD",
    chip: "Annex III", footnote: "ACD 2026", note: "Semak dahulu.", scrim: "light", bg_url: "/g/x.jpg", mascot: "none" },
  { title: "Dua", points: ["A"], lead: "Baris sokongan." },
  { title: "Tiga", points: [], bg: "none" },
], { look: "era", stream: "regulab", eyebrow: "Kosmetik", citation: "NPRA", bg: "/g/set.jpg", mascots: M });
ok(own[0].template === "g_bars" && own[0].items.join("|") === "Malaysia | 0.5 | 0.5%|EU | 0.4 | 0.4%", "an explicit template takes the points verbatim as items");
ok(own[0].lead === "angka contoh" && own[0].eyebrow === "ACD" && own[0].chip_label === "Annex III" && own[0].footnote === "ACD 2026"
  && own[0].note === "Semak dahulu." && own[0].scrim === "light", "a slide's own lead, eyebrow, chip, source, note and scrim are used");
ok(own[0].bg === "/g/x.jpg" && !own[0].mascot, "its own background, and mascot none means none");
ok(own[1].template === "e_explain" && words(own[1]).includes("Baris sokongan.") && words(own[1]).includes("A"), "an auto slide keeps the typed lead and its points");
ok(own[1].eyebrow === "Kosmetik" && own[1].bg === "/g/set.jpg", "unset fields fall back to the set's eyebrow and background");
ok(own[1].mascot === "/m/point.webp", "auto mascot: e_explain gets the pointing pose, the template's own hint");
ok(own[2].bg === "" && own[2].footnote === "NPRA" && own[2].chip_label === "Sumber", "bg none clears this slide only; the closing slide still carries the source");
const hook = specsFor([{ title: "Kenapa?", points: ["a", "b"] }, { title: "x", points: ["c"] }], { look: "era", mascots: M });
ok(hook[0].template === "e_hook" && hook[0].mascot === "/m/confused.webp", "the ERA hook gets the confused pose");
ok(!specsFor([{ title: "t", points: [] }], { look: "grid" })[0].mascot, "no poses offered, no mascot");
ok(!specsFor([{ title: "t", points: ["a"], template: "e_flow" }], { look: "era", mascots: M })[0].mascot, "e_flow never carries a mascot (Studio)");
ok(specsFor([{ title: "t", points: [], mascot: "wave", template: "e_vs" }], { mascots: M })[0].mascot === "/m/wave.webp", "a chosen pose wins over the hint");
ok(LOOKS.map((l) => l.k).join(",") === "classic,grid,era,photo", "the four looks, Semasa's own first");

// Studio's "Reset from caption": every paragraph kept, asks and the website never built onto the artwork
{
  const long = "NPRA menyemak dokumen PIF selepas produk dipasarkan, bukan sebelum. Pemeriksaan boleh berlaku bila-bila masa dan syarikat perlu bersedia dengan fail lengkap. Kegagalan boleh membawa kepada pembatalan notifikasi.";
  const cap = ["Notifikasi bukan kelulusan.", "Notifikasi ialah pemberitahuan kepada NPRA, bukan pengesahan keselamatan produk.", long,
    "Label mesti sepadan dengan formula yang dinotifikasi.", "Hubungi kami untuk semakan percuma.",
    "Formula yang berubah perlu dinotifikasi semula.", "Yang ramai tak sedar: tanggungjawab kekal pada pemilik produk.",
    "#NPRA #Kosmetik", "www.kkmhalalconsultant.com"].join("\n\n");
  const post = { stream: "regulab", hook: "Notifikasi bukan kelulusan.", caption: cap };
  const promo = (t) => /hubungi kami|www\.kkmhalalconsultant/i.test(t);    // stands in for compliance.js isPromo
  const { slides, over } = slidesFromCaption(post, promo);
  const all = slides.map((x) => [x.title, x.lead || ""].join(" ")).join(" ");
  ok(slides[0].title === "Notifikasi bukan kelulusan.", "the hook is the cover");
  ok(slides.length >= 5 && slides.length <= 8, `cover, facts and a closing (${slides.length})`);
  ok(all.includes("pembatalan notifikasi") && all.includes("Pemeriksaan boleh berlaku"), "a long paragraph is packed, not dropped");
  ok(!/Hubungi kami|#NPRA|www\./.test(all), "no ask, no hashtags, no website on the artwork");
  ok(slides.at(-1).title.startsWith("Yang ramai tak sedar") && slides.at(-1).eyebrow === "Yang ramai tak sedar", "the last statement closes");
  ok(over === 0, "nothing over the ceiling");
  ok(slides.every((x) => x.title.length <= 110), "every headline fits");
  const card = cardFromCaption(post, promo);
  ok(card.length === 1 && card[0].title === "Notifikasi bukan kelulusan." && card[0].lead.startsWith("Notifikasi ialah"), "a single card: hook and its line");
  const [h, r] = headAndRest("Perintah Perihal Dagangan (Perakuan dan Penandaan Halal) 2011, perenggan 4(1), menetapkan bila perkataan halal boleh digunakan pada produk makanan, kosmetik dan farmaseutikal yang dijual di Malaysia, termasuk yang diimport.");
  ok(h.length <= 110 && (h + " " + r).replace(/\s+/g, " ").length >= 190, "a long first sentence is broken until it fits, nothing lost");
}

// text size, font and the mascot's place and size (Wan, 3 Oct 2026): reach the card spec, and never when invalid
{
  const [s] = specsFor([{ title: "Tajuk", points: ["a"], type_size: "80", font: "sans", mascot_pos: "bl", mascot_size: "130" }], { look: "grid", mascots: M });
  ok(s.type_size === 80 && s.font === "sans" && s.mascot_pos === "bl" && s.mascot_size === 130, "text size, font and mascot choices reach the card");
  const [d] = specsFor([{ title: "Tajuk", points: ["a"] }], { look: "grid", mascots: M });
  ok(d.type_size === undefined && d.font === undefined && d.mascot_pos === undefined && d.mascot_size === undefined, "a slide that chose none keeps the template's own");
  const [bad] = specsFor([{ title: "Tajuk", points: ["a"], font: "comic", mascot_pos: "top" }], { look: "grid", mascots: M });
  ok(bad.font === undefined && bad.mascot_pos === undefined, "an unknown font or place is ignored");
}

if (failed) { console.error(`${failed} card mapping check(s) failed`); process.exit(1); }
console.log("cards: slide -> Studio card mapping keeps every word");
