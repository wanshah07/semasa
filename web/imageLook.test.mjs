import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { STUDIO_LOOKS, TEMPLATE_KEYS, fitTemplate, specsFor } from "./src/lib/cards/studio.js";

// the Image look: a picture ON the slide (Wan, 8 Nov 2026, four references). Four templates, registered everywhere a look is.
const IMG = ["i_title", "i_note", "i_hero", "i_step"];
assert.ok(STUDIO_LOOKS.includes("image"));
for (const k of IMG) assert.ok(TEMPLATE_KEYS.includes(k), k + " is a template");
const cat = JSON.parse(readFileSync(new URL("../rules/cards.json", import.meta.url), "utf8")).templates.filter((t) => t.group === "image");
assert.deepEqual(cat.map((t) => t.k).sort(), IMG.slice().sort(), "the catalogue lists the same four");
for (const t of cat) assert.ok(t.hint && t.hintEn && t.name.startsWith("Gambar") && t.en.startsWith("Image"), t.k + " has both languages");

// a cover with a picture is the poster, without one the calm title; the last slide closes on the title; points are all kept
const deck = [{ title: "Notifikasi bukan kelulusan", points: ["245 hari", "Semak maklumat"] }, { title: "Langkah", points: ["Satu", "Dua", "Tiga"] },
  { title: "Nota", points: ["Satu sahaja"] }, { title: "Tutup", points: ["Satu ayat."] }];
const withPic = specsFor(deck, { look: "image", bg: "https://x/p.jpg" }).map((s) => s.template);
assert.deepEqual(withPic, ["i_hero", "i_step", "i_note", "i_title"]);
const noPic = specsFor(deck, { look: "image" }).map((s) => s.template);
assert.deepEqual(noPic, ["i_title", "i_note", "i_note", "i_title"], "no picture: a step slide has nothing to show, so it is a note");
for (const s of specsFor(deck, { look: "image", bg: "https://x/p.jpg" })) {
  const words = [s.title, s.lead, ...(s.items || [])].join("\n");
  for (const p of deck.find((d) => d.title === s.title).points) assert.ok(words.includes(p), `${s.template} keeps "${p}"`);
}
// a single card is the poster too; fit picks a step slide for steps and the poster for a figure
assert.equal(specsFor([{ title: "Satu kad", points: [] }], { look: "image", bg: "x" })[0].template, "i_hero");
assert.equal(fitTemplate("image", { title: "Tempoh purata" }, 1, 4, ["14", "hari"]), "i_hero");
assert.equal(fitTemplate("image", { title: "Langkah notifikasi" }, 1, 4, ["PIF", "Hantar", "Nombor"]), "i_step");

// the picture is the slide's own, never a ground: the light-ground check that re-dresses Grid and ERA must not touch it
const src = readFileSync(new URL("./src/lib/cards/studio.js", import.meta.url), "utf8");
assert.ok(/spec\.template\[0\] !== "i"/.test(src), "an image slide is not re-dressed as a light ground");
// no ctx.filter (iPhone Safari before 18), and LinkedIn carries no ws.regulab mark: drawBrandMark already stands down for it
assert.ok(!/ctx\.filter\s*=/.test(src));
console.log("imageLook: ok");
