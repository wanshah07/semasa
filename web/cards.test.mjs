// The slide -> Studio card mapping (web/src/lib/cards/studio.js, specsFor). The drawing itself is tested in a real
// browser by backend/tests/test_studio_cards.py; this checks the one rule the mapping owns: every point of every
// slide reaches a card, whatever the look. `npm test`.
import { specsFor, LOOKS, STUDIO_LOOKS, TEMPLATE_KEYS, fitTemplate, eventDate, initialsOf, normDesign, normLayout, placeOf } from "./src/lib/cards/studio.js";
import { canvaBrief } from "./src/lib/canvaBrief.js";
import { readFileSync } from "node:fs";
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

// the catalogue file and the renderer name the same twenty-two templates (4 Oct 2026: nine added, then the event poster)
const cat = JSON.parse(readFileSync(new URL("../rules/cards.json", import.meta.url), "utf8")).templates.map((x) => x.k);
ok(cat.length === 22 && cat.slice().sort().join() === TEMPLATE_KEYS.slice().sort().join(), "rules/cards.json and studio.js list the same templates");
ok(cat.every((k) => /^[gep]_[a-z]{2,8}$/.test(k)), "every template key passes the slide-design pattern the database and the worker check");

// "fit the design to each slide": off, nothing changes; on, only a template that draws every point is chosen
const FIT = [{ title: "Kulit", points: [] }, { title: "Tempoh purata", points: ["14", "hari"] },
  { title: "Mitos dan fakta", points: ["Ada nombor, lulus | Nombor bukan kelulusan", "NPRA uji semua | NPRA semak maklumat"] },
  { title: "Langkah notifikasi", points: ["PIF | Lengkap.", "Hantar | QUEST3+.", "Nombor | Boleh jual."] },
  { title: "Sebelum anda hantar", points: ["INCI", "Label", "Surat"] }, { title: "Tutup", points: ["Satu ayat."] }];
const tpls = (look, fit) => specsFor(FIT, { look, fit }).map((x) => x.template).join(",");
ok(tpls("grid", false) === "g_title,g_title,g_title,g_title,g_title,g_title", "fit off: grid is unchanged");
ok(tpls("grid", true) === "g_title,g_stat,g_myth,g_steps,g_check,g_title", "fit on, grid: figure, myth, steps, checklist; plain slides keep the look's own");
ok(tpls("era", true) === "e_hook,e_stat,e_myth,e_flow,e_check,e_explain", "fit on, era: figure, myth, flow, checklist");
ok(tpls("photo", true).startsWith("p_title,p_stat,p_list,p_list,p_list,"), "fit on, photo: figure, then list panels");
for (const look of STUDIO_LOOKS) {
  specsFor(FIT, { look, fit: true }).forEach((sp, i) => {
    for (const p of FIT[i].points) ok(words(sp).includes(p), `fit ${look} slide ${i + 1} (${sp.template}) keeps "${p}"`);
  });
}
ok(specsFor([{ title: "x", points: ["14", "hari"], template: "g_bars" }], { look: "grid", fit: true })[0].template === "g_bars", "a template chosen on the slide beats fit");
ok(fitTemplate("grid", { title: "Tempoh", lead: "" }, 0, 1, ["14", "hari"]) === "g_stat", "a single card can take the figure design (it is not a cover)");
ok(fitTemplate("grid", { title: "Mitos", lead: "" }, 1, 3, ["a | b | c"]) !== "g_myth", "a myth row needs exactly two cells");
ok(fitTemplate("era", { title: "Langkah", lead: "" }, 1, 3, ["a", "b", "c", "d", "e", "f"]) === "", "too many points for a template that would not draw them all: the look's own rule");

// the Canva brief carries every word and names the stream's rule
const br = canvaBrief({ slides: [{ title: "Notifikasi *bukan* kelulusan", points: ["Satu", "Dua"], lead: "Sokongan" }], urls: ["https://x/1.jpg"],
  stream: "linkedin", size: [1080, 1350], look: "era", citation: "EC 1223/2009" });
ok(["Notifikasi *bukan* kelulusan", "Satu", "Dua", "Sokongan", "https://x/1.jpg", "1080×1350", "#D8232A", "EC 1223/2009"].every((x) => br.includes(x)), "the brief carries the words, picture, size, colours and source");
ok(br.includes("no ws.regulab logo") && !br.includes("website only in the footer"), "LinkedIn: no ws.regulab identity");
ok(canvaBrief({ slides: [{ title: "T", points: [] }], stream: "regulab" }).includes("website only in the footer"), "ws.regulab: logo and website in the footer only");

// the event poster (4 Oct 2026): the date is read, the speakers keep their names, fit picks it, a light ground is told apart
const dt = eventDate("Wednesday 30 Sep 2026 | 16:15 – 17:00 | Room: Hub 2");
ok(dt.weekday === "WEDNESDAY" && dt.day === "30" && dt.month === "SEP" && dt.year === "2026" && dt.lines.join() === "16:15 – 17:00,Room: Hub 2", "an event date is read into weekday, day, month, year and the lines under it");
const dm = eventDate("Rabu 14 Okt 2026 | 10:00");
ok(dm.weekday === "RABU" && dm.month === "OKT" && dm.day === "14", "a Malay date reads too (Okt, Rabu)");
ok(eventDate("Terbuka kepada semua | Percuma").day === "" && eventDate("Terbuka kepada semua | Percuma").lines.length === 2, "a note that is not a date is kept as plain lines, nothing is lost");
ok(eventDate("30 Sep 2026").weekday === "" && eventDate("30 Sep 2026").day === "30", "a date without a weekday reads");
ok(initialsOf("DR SEEMAL DESAI") === "SD" && initialsOf("Prof Thierry Passeron") === "TP" && initialsOf("Dr Cristina Wöhlke Vendruscolo") === "CV" && initialsOf("Ncoza") === "N", "speaker initials skip the title");
const EV = [{ title: "*SAFE & EFFECTIVE* TREATMENT *HYPERPIGMENTATION*", lead: "TOPIC\nSECOND", eyebrow: "SCIENTIFIC SYMPOSIUM",
  points: ["DR A | USA", "PROF B | FRANCE"], note: "Wednesday 30 Sep 2026 | 16:15 – 17:00 | Room: Hub 2", chip: "EADV CONGRESS" }];
const evs = specsFor(EV, { look: "era", fit: true })[0];
ok(evs.template === "e_event" && evs.items.length === 2 && evs.note.includes("Hub 2") && evs.chip_label === "EADV CONGRESS", "fit gives a slide with a date and people the event poster, keeping every word");
ok(specsFor(EV, { look: "grid", fit: true })[0].template === "e_event", "the event poster is chosen under any look when the words are an event");
ok(specsFor(EV, { look: "era", fit: false })[0].template !== "e_event", "fit off: the look decides, as before");
ok(specsFor([{ title: "Tempoh", points: ["14", "hari"], note: "Angka contoh." }], { look: "era", fit: true })[0].template === "e_stat", "a note without a date does not make an event");
ok(specsFor(EV, { look: "era" })[0].auto_scrim === true && specsFor([{ ...EV[0], scrim: "heavy" }], { look: "era" })[0].auto_scrim === false, "a scrim chosen on purpose is remembered, so a light picture does not override it");

// my designs: a saved look with a template per place, two colours, a background, and no words
const SLIDES5 = ["Satu", "Dua", "Tiga", "Empat", "Lima"].map((x) => ({ title: x, points: ["a | b", "c | d"] }));
ok(normDesign(null) === null && normDesign({ look: "classic" }) === null && normDesign({}) === null, "a design needs one of the three Studio families");
const DG = normDesign({ look: "era", cover: "e_hook", middle: "e_check", closing: "g_title", single: "e_stat", accent: "#0A7C6E", paper: "#F3EFE6",
  bg: "lib:g_makmal02", scrim: "light", mascot: "none", eyebrow: " Kosmetik ", junk: 1 });
ok(DG.cover === "e_hook" && DG.middle === "e_check" && !("closing" in DG) && DG.single === "e_stat", "templates of another family are dropped");
ok(DG.accent === "#0a7c6e" && DG.paper === "#f3efe6" && DG.bg === "lib:g_makmal02" && DG.scrim === "light" && DG.mascot === "none" && DG.eyebrow === "Kosmetik" && !("junk" in DG), "a design keeps only what it understands");
ok(!("accent" in normDesign({ look: "grid", accent: "red" })) && !("bg" in normDesign({ look: "grid", bg: "none" })), "a bad colour and an empty background are dropped");
ok([0, 1, 4].map((i) => placeOf(i, 5)).join() === "cover,middle,closing" && placeOf(0, 1) === "single", "a slide's place in its set");
const ds = specsFor(SLIDES5, { design: DG, look: "grid" });
ok(ds.map((x) => x.template).join() === "e_hook,e_check,e_check,e_check,e_explain", "the design chooses the templates by place and the look fills the closing (auto)");
ok(ds.every((x) => x.palette && x.palette.accent === "#0a7c6e" && x.palette.paper === "#f3efe6" && x.eyebrow === "Kosmetik" && x.scrim === "light" && x.auto_scrim === false), "the design's colours, label and cover reach every slide");
ok(specsFor([SLIDES5[0]], { design: DG })[0].template === "e_stat", "a single card or poster takes the design's single template");
ok(specsFor(SLIDES5, { design: DG }).every((x, i) => (i ? true : x.template === "e_hook")) && specsFor([{ ...SLIDES5[1], template: "e_vs" }, SLIDES5[2], SLIDES5[3]], { design: DG })[0].template === "e_vs", "a template chosen on the slide beats the design");
ok(specsFor(SLIDES5, { look: "grid" }).every((x) => !x.palette), "without a design nothing changes");
ok(specsFor(SLIDES5, { design: { look: "photo" }, fit: true }).every((x) => x.template[0] === "p"), "a design with no templates falls back to the family and fit");

// a design made from a reference: its layout is trusted only as far as the painter understands it
const LAY = { background: { color: "#e6dfec", gradient: null }, covers: [{ kind: "logo", x: 0.7, y: 0.03, w: 0.2, h: 0.04 }, { kind: "face", x: 0, y: 0, w: 1, h: 1 }],
  elements: [{ type: "text", role: "headline", x: 0.06, y: 0.2, w: 0.8, h: 0.14, text: "x".repeat(900), size: 0.06 }, { type: "logo", x: 0, y: 0, w: 1, h: 1 },
    { type: "rect", x: "0.1", y: 0.1, w: 0.3, h: 0.05, fill: "#e0d4e6" }] };
const NL = normLayout(LAY);
ok(NL.elements.length === 2 && NL.elements[0].text.length === 400 && NL.elements[1].x === 0.1 && NL.covers.length === 1, "a layout keeps known elements and covers, caps long text, coerces numbers");
ok(normLayout(null) === null && normLayout({ elements: [] }) === null && normLayout({ elements: [{ type: "logo" }] }) === null && normLayout({ elements: "x" }) === null, "nothing usable is no layout");
ok(normLayout({ elements: Array.from({ length: 200 }, () => ({ type: "rect", x: 0, y: 0, w: 1, h: 1 })) }).elements.length === 60, "at most 60 elements");
const RD = normDesign({ look: "grid", layouts: { main: LAY, middle: { elements: [] }, bogus: LAY } });
ok(RD.layouts && Object.keys(RD.layouts).join() === "main", "a design keeps the layouts it understands, in the places it knows");
const rs = specsFor(SLIDES5, { design: { look: "grid", layouts: { main: LAY, closing: { ...LAY, background: { color: "#000000", gradient: null } } } } });
ok(rs.every((x) => x.template === "c_ref" && x.layout), "every slide is drawn in the reference's layout");
ok(rs[4].layout.background.color === "#000000" && rs[0].layout.background.color === "#e6dfec", "a layout for one place is used there; the main layout elsewhere");
ok(rs.every((x, i) => x.title === SLIDES5[i].title && x.items.join() === SLIDES5[i].points.join()), "the words travel on the spec");
ok(specsFor([{ ...SLIDES5[0], template: "g_stat" }], { design: { look: "grid", layouts: { main: LAY } } })[0].template === "g_stat", "a template chosen on the slide beats the reference layout");

if (failed) { console.error(`${failed} card mapping check(s) failed`); process.exit(1); }
console.log("cards: slide -> Studio card mapping keeps every word");
