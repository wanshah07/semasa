// The slide -> Studio card mapping (web/src/lib/cards/studio.js, specsFor). The drawing itself is tested in a real
// browser by backend/tests/test_studio_cards.py; this checks the one rule the mapping owns: every point of every
// slide reaches a card, whatever the look. `npm test`.
import { specsFor, LOOKS, MASCOTS_ON, STUDIO_LOOKS, TEMPLATE_KEYS, fitTemplate, eventDate, initialsOf, normDesign, normLayout, placeOf, skinTemplate, templateLabel } from "./src/lib/cards/studio.js";
import { canvaBrief } from "./src/lib/canvaBrief.js";
import { readFileSync } from "node:fs";
import { cardFromCaption, headAndRest, isFollow, sameLine, slidesFromCaption } from "./src/lib/cards/fromCaption.js";

let failed = 0;
const ok = (cond, what) => { if (!cond) { failed++; console.error("FAIL", what); } };
const words = (spec) => [spec.title, spec.lead, ...(spec.items || [])].join("\n");
// how many items each template actually draws (Studio slices its lists)
const SHOWN = { e_hook: 3, e_explain: 3, p_fact: 4, g_title: 0, p_title: 0, p_quote: 0, i_title: 8, i_note: 8, i_hero: 8, i_step: 8, h_poster: 8, h_hero: 8, h_note: 8 };   // the image and hand-drawn families draw every point (lines, a pill or a step)

// the four poster looks draw every point, whatever the count: the type comes down in size instead (studio.js SKIN_MIN)
for (const p of ["m", "t", "b", "n", "d", "k", "l", "s"]) for (const part of ["cover", "points", "table", "pick", "close"]) SHOWN[`${p}_${part}`] = Infinity;

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
ok(g("era") === "m_cover,e_explain,e_explain", "era: the poster front page, explainer after");
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
// NO MASCOT ANYWHERE (Wan, 16 Nov 2026: "remove all mascott"): poses on offer, a pose chosen on the slide, a design's pose, none is drawn
ok(MASCOTS_ON === false && !own[1].mascot, "no automatic mascot, even with poses on offer");
ok(own[2].bg === "" && own[2].footnote === "NPRA" && own[2].chip_label === "Sumber", "bg none clears this slide only; the closing slide still carries the source");
// the ERA hook slide is no longer the automatic front page (see THE FRONT PAGE below); chosen on a slide it is drawn without a character
const hook = specsFor([{ title: "Kenapa?", points: ["a", "b"], template: "e_hook" }, { title: "x", points: ["c"] }], { look: "era", mascots: M });
ok(hook[0].template === "m_cover" && hook[0].skin === "kraft" && !hook[0].mascot, "an ERA hook slide with no character is the poster front page in ERA's dress");
ok(words(hook[0]).includes("a") && words(hook[0]).includes("b") && words(hook[0]).includes("Kenapa?"), "and it keeps the hook and both questions");
ok(!specsFor([{ title: "t", points: [] }], { look: "grid" })[0].mascot, "no poses offered, no mascot");
ok(!specsFor([{ title: "t", points: ["a"], template: "e_flow" }], { look: "era", mascots: M })[0].mascot, "e_flow never carries a mascot (Studio)");
ok(!specsFor([{ title: "t", points: [], mascot: "wave", template: "e_vs" }], { mascots: M })[0].mascot, "a pose chosen on an old slide is not drawn either");
ok(!specsFor([{ title: "t", points: ["a"] }], { design: { look: "grid", mascot: "wave" }, mascots: M })[0].mascot, "nor is a saved design's pose");
ok(LOOKS.map((l) => l.k).join(",") === "classic,hand,marker,torn,block,neon,deck,chalk,metro,strip,grid,era,photo,image", "the fourteen looks, Semasa's own first, the eight poster looks after Hand-drawn");

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
  ok(slides.length >= 5, `cover, facts and a closing (${slides.length}); no ceiling`);
  ok(all.includes("pembatalan notifikasi") && all.includes("Pemeriksaan boleh berlaku"), "a long paragraph is packed, not dropped");
  ok(!/Hubungi kami|#NPRA|www\./.test(all), "no ask, no hashtags, no website on the artwork");
  ok(slides.at(-1).title.startsWith("Yang ramai tak sedar") && slides.at(-1).eyebrow === "Yang ramai tak sedar", "the last statement closes");
  ok(over === 0, "nothing is ever over: there is no ceiling");
  ok(slides.every((x) => x.title.length <= 110), "every headline fits");
  // no minimum and no maximum (Wan, 9 Nov 2026): twelve points make twelve slides plus the cover, two make a cover and a closing
  const many = slidesFromCaption({ stream: "regulab", hook: "Tajuk utama yang cukup panjang.", caption: Array.from({ length: 12 }, (_, i) => `Fakta nombor ${i + 1} yang cukup panjang untuk jadi satu slaid.`).join("\n\n") }, promo);
  ok(many.slides.length === 13 && many.over === 0, `twelve points are not cut to eight (${many.slides.length} slides)`);
  const few = slidesFromCaption({ stream: "regulab", hook: "Tajuk utama yang cukup panjang.", caption: "Satu fakta yang cukup panjang untuk jadi slaid.\n\nPenutup yang cukup panjang untuk jadi slaid." }, promo);
  ok(few.slides.length === 3 && few.slides.at(-1).title.startsWith("Penutup"), `two points are not padded to three (${few.slides.length} slides)`);
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
ok(cat.length === 69 && cat.slice().sort().join() === TEMPLATE_KEYS.slice().sort().join(), "rules/cards.json and studio.js list the same templates");
ok(cat.every((k) => /^[gepihmtbndkls]_[a-z]{2,8}$/.test(k)), "every template key passes the slide-design pattern the page and the worker check");
// ... and the check itself keeps every one of them: a slide's own template must survive slideExtras (page) and slide_extras
// (worker). The pattern was [gepi] while the catalogue already had h_ templates, so a Hand-drawn choice on one slide was silently
// dropped. Read from the two sources (compliance.js imports JSON, which Node will not load without an attribute).
{
  const py = readFileSync(new URL("../backend/semasa/compliance.py", import.meta.url), "utf8");
  const js = readFileSync(new URL("./src/lib/compliance.js", import.meta.url), "utf8");
  const pyRe = /"template": re\.compile\(r"([^"]+)"\)/.exec(py)[1], jsRe = /\n  template: \/([^/]+)\//.exec(js)[1];
  ok(pyRe === jsRe, "the worker and the page check a slide's template with the same pattern");
  ok(cat.every((k) => new RegExp(jsRe).test(k)), "the page and the worker keep every catalogue template chosen on a slide");
  ok(!new RegExp(jsRe).test("x_table") && !new RegExp(jsRe).test("c_ref"), "and still refuse a family that does not exist");
}

// THE FRONT PAGE (Wan, 16 Nov 2026: "create more impressive front page to replace current front page based on posters"): a carousel
// in the Image, Info ERA or Hand-drawn look opens with a poster cover, where the hook fills the card
{
  const deck = [{ title: "Kenapa?", lead: "Satu baris.", points: [] }, { title: "x", points: ["c"] }, { title: "y", points: ["d"] }];
  const first = (o, d = deck) => specsFor(d, o)[0];
  for (const fit of [true, false]) {
    ok(first({ look: "image", fit }).template === "b_cover", `image (fit ${fit}): the front page is the poster cover`);
    ok(first({ look: "image", fit, bg: "https://x/p.jpg" }).template === "b_cover" && first({ look: "image", fit, bg: "https://x/p.jpg" }).bg === "https://x/p.jpg",
      `image (fit ${fit}): with a picture it is still the poster cover, and the picture goes with it`);
    ok(first({ look: "hand", fit }).template === "m_cover", `hand (fit ${fit}): the front page is the marker cover`);
    // Info ERA's front page is the poster cover in ERA's own dress, with or without a mascot on offer (Wan, 16 Nov 2026, of the
    // ERA hook slide: "make sure no space excess, make it fill the page, can add image if possible")
    for (const mascots of [undefined, M]) {
      const era = first({ look: "era", fit, mascots, bg: "https://x/p.jpg" });
      ok(era.template === "m_cover" && era.skin === "kraft" && !era.mascot && era.bg === "https://x/p.jpg", `era (fit ${fit}): the front page is the poster cover in ERA's dress, picture with it`);
    }
    ok(first({ look: "hand", fit }).skin === undefined && first({ look: "image", fit }).skin === undefined, `only ERA's front page wears ERA's dress (fit ${fit})`);
    ok(specsFor(deck, { look: "era", fit, mascots: M }).every((x) => !x.mascot), `era (fit ${fit}): no mascot on any slide`);
    ok(first({ look: "grid", fit }).template === "g_title" && first({ look: "photo", fit, bg: "https://x/p.jpg" }).template === "p_title", `grid and photo (fit ${fit}) keep their own cover`);
  }
  ok(first({ look: "image" }).lead === "Satu baris." && first({ look: "image" }).title === "Kenapa?", "the front page keeps the hook and its supporting line");
  // only the first slide of a carousel: a lone card and the slides after the cover are the look's own
  ok(specsFor(deck.slice(0, 1), { look: "image" })[0].template === "i_title" && specsFor(deck.slice(0, 1), { look: "hand" })[0].template === "h_poster", "a single card is not a cover");
  ok(specsFor(deck, { look: "image" }).slice(1).every((x) => x.template[0] === "i"), "the slides after the front page stay in the look");
  // a choice made on the slide, or in a saved design, wins
  ok(first({ look: "image" }, [{ ...deck[0], template: "i_title" }, ...deck.slice(1)]).template === "i_title", "a template chosen on the first slide wins");
  ok(first({ design: { look: "image", cover: "i_hero" }, bg: "https://x/p.jpg" }).template === "i_hero", "a saved design's own cover wins");
}

// THE FOUR POSTER LOOKS (Wan, 16 Nov 2026): marker, torn paper, colour blocks, neon. Each is a single card and a whole carousel.
{
  // and four more the same day (card board, chalkboard, line map, torn strips): the same five slides, so the same rules
  const SK = { marker: "m", torn: "t", block: "b", neon: "n", deck: "d", chalk: "k", metro: "l", strip: "s" };
  ok(Object.keys(SK).every((k) => STUDIO_LOOKS.includes(k)), "the eight poster looks are Studio looks");
  for (const [look, p] of Object.entries(SK)) {
    // a carousel: cover, points, comparison, recommendation, closing
    const deck = [
      { title: "Notifikasi bukan kelulusan", lead: "Tiga perkara." },
      { title: "Apa itu notifikasi", points: ["Pengisytiharan | oleh pemegang", "Bukan penilaian"] },
      { title: "Kosmetik lawan ubat", points: ["Perkara | Kosmetik | Ubat", "Dinilai dahulu | tidak | ya", "Nombor | NOT | MAL"] },
      { title: "Syor: semak PIF dahulu", lead: "Sebelum iklan.", points: ["Semak tuntutan"] },
      { title: "Penutup", points: ["Sah 2 tahun"], note: "Tanggungjawab kekal." },
    ];
    for (const fit of [true, false]) {
      const specs = specsFor(deck, { look, stream: "regulab", citation: "NPRA", fit });
      ok(specs.map((x) => x.template).join() === [`${p}_cover`, `${p}_points`, `${p}_table`, `${p}_pick`, `${p}_close`].join(), `${look} (fit ${fit}): cover, points, comparison, recommendation, closing`);
      ok(specs.every((x) => !x.mascot), `${look}: no mascot on a poster look`);
      ok(specs[4].footnote === "NPRA" && specs[4].note === "Tanggungjawab kekal.", `${look}: the closing slide carries the source and its note`);
      ok(specs[3].lead === "Sebelum iklan." && specs[3].items.join() === "Semak tuntutan", `${look}: the recommendation keeps its reason and its points`);
    }
    // a single card: rows of cells are the comparison, plain points are the points
    ok(specsFor([{ title: "t", points: ["A | ✓ | ✗", "B | ✗ | ✓"] }], { look })[0].template === `${p}_table`, `${look}: a lone card with rows of cells is the comparison`);
    ok(specsFor([{ title: "t", points: ["satu", "dua"] }], { look })[0].template === `${p}_points`, `${look}: a lone card with plain points is the points`);
    // "Heading | detail" pairs are points with a heading, not a table; a yes/no in the second cell makes it a table
    ok(skinTemplate(look, { title: "t" }, 1, 3, ["Tajuk | ayat penuh di bawahnya", "Lagi | satu ayat"]) === `${p}_points`, `${look}: heading | detail pairs stay points`);
    ok(skinTemplate(look, { title: "t" }, 1, 3, ["Wajib notifikasi | ya", "Perlu ujian klinikal | tidak"]) === `${p}_table`, `${look}: a yes/no second cell is a comparison`);
    // a slide's own template wins, and a saved design may name the look's templates per place
    ok(specsFor([{ title: "t", points: ["a"], template: `${p}_pick` }], { look: "grid" })[0].template === `${p}_pick`, `${look}: a template chosen on the slide wins`);
    const D = normDesign({ look, cover: `${p}_cover`, middle: `${p}_table`, closing: "g_title" });
    ok(D && D.cover === `${p}_cover` && D.middle === `${p}_table` && !D.closing, `${look}: a saved design takes this look's templates and no other family's`);
    ok(templateLabel(`${p}_table`).endsWith("· Comparison"), `${look}: the comparison has a readable name`);
    // LinkedIn: the same slides, marked as that stream (the painter draws no ws.regulab mark on it)
    ok(specsFor(deck, { look, stream: "linkedin" }).every((x) => x.stream === "linkedin"), `${look}: LinkedIn specs carry the stream`);
  }
}

// "fit the design to each slide": off, nothing changes; on, only a template that draws every point is chosen
const FIT = [{ title: "Kulit", points: [] }, { title: "Tempoh purata", points: ["14", "hari"] },
  { title: "Mitos dan fakta", points: ["Ada nombor, lulus | Nombor bukan kelulusan", "NPRA uji semua | NPRA semak maklumat"] },
  { title: "Langkah notifikasi", points: ["PIF | Lengkap.", "Hantar | QUEST3+.", "Nombor | Boleh jual."] },
  { title: "Sebelum anda hantar", points: ["INCI", "Label", "Surat"] }, { title: "Tutup", points: ["Satu ayat."] }];
const tpls = (look, fit) => specsFor(FIT, { look, fit }).map((x) => x.template).join(",");
ok(tpls("grid", false) === "g_title,g_title,g_title,g_title,g_title,g_title", "fit off: grid is unchanged");
ok(tpls("grid", true) === "g_title,g_stat,g_myth,g_steps,g_check,g_title", "fit on, grid: figure, myth, steps, checklist; plain slides keep the look's own");
ok(tpls("era", true) === "m_cover,e_stat,e_myth,e_flow,e_check,e_explain", "fit on, era: figure, myth, flow, checklist");
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
// a design's ERA hook cover has no character to stand on any more (16 Nov 2026), so it is the poster front page in ERA's dress
ok(ds.map((x) => x.template).join() === "m_cover,e_check,e_check,e_check,e_explain" && ds[0].skin === "kraft" && ds[0].palette.accent === "#0a7c6e", "the design chooses the templates by place and the look fills the closing (auto)");
ok(ds.every((x) => x.palette && x.palette.accent === "#0a7c6e" && x.palette.paper === "#f3efe6" && x.eyebrow === "Kosmetik" && x.scrim === "light" && x.auto_scrim === false), "the design's colours, label and cover reach every slide");
ok(specsFor([SLIDES5[0]], { design: DG })[0].template === "e_stat", "a single card or poster takes the design's single template");
ok(specsFor(SLIDES5, { design: DG }).every((x, i) => (i ? true : x.template === "m_cover")) && specsFor([{ ...SLIDES5[1], template: "e_vs" }, SLIDES5[2], SLIDES5[3]], { design: DG })[0].template === "e_vs", "a template chosen on the slide beats the design");
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

// a design never carries a copy of its reference picture, whatever it is handed
ok(!("refart" in normDesign({ look: "grid", layouts: { main: LAY }, refart: { url: "data:image/jpeg;base64,AAAA", w: 800, h: 1000 } })), "no reference picture is kept");

// Wan, 22 Nov 2026: the caption's first line is the hook, so slide 2 never repeats it; the follow line is never a slide
const hiv = slidesFromCaption({ stream: "regulab", hook: "Sebab sebenar kenapa stigma HIV masih belum hilang sepenuhnya",
  caption: "Sebab sebenar kenapa stigma HIV masih belum hilang sepenuhnya.\n\nBerita terbaru cakap persekitaran yang lebih terbuka boleh bantu hapuskan stigma terhadap HIV dan AIDS.\n\nMaksudnya, bila masyarakat mula bercakap secara jujur dan tanpa rasa janggal, stigma berkurang.\n\nFollow untuk tip regulatori yang senang faham." }, () => false).slides;
ok(hiv.length === 3 && hiv.every((x, i) => i === 0 || !sameLine(x.title, hiv[0].title)), "slide 2 never repeats the hook on slide 1");
ok(!hiv.some((x) => /follow/i.test(`${x.title} ${x.lead || ""}`)), "the follow line is never drawn as a slide");
ok(isFollow("Follow untuk tip regulatori yang senang faham.") && isFollow("Ikuti kami untuk info lanjut") && !isFollow("Pengilang perlu ikut garis panduan NPRA."), "a follow line is told apart from a fact");
ok(sameLine("*Sebab* sebenar kenapa stigma HIV masih belum hilang.", "Sebab sebenar kenapa stigma HIV masih belum hilang") && !sameLine("Satu", "Dua"), "the same line once punctuation and emphasis are set aside");

if (failed) { console.error(`${failed} card mapping check(s) failed`); process.exit(1); }
console.log("cards: slide -> Studio card mapping keeps every word");
