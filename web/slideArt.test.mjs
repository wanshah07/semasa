// A post's own illustrations in the design picker (src/lib/slideArt.js): the keys are the worker's keys, the cut-out is the worker's rule
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { STYLE_VERSION, artFor, artIndex, artKey, coverArtUrl, coverTitleFor, cutPixels, leadSentence, pageColour, wordsOf } from "./src/lib/slideArt.js";

let n = 0;
const t = async (name, fn) => { try { await fn(); n++; } catch (e) { console.error("FAIL:", name); throw e; } };

await t("STYLE_VERSION is the worker's", () => {
  const py = readFileSync(new URL("../backend/semasa/illustrated.py", import.meta.url), "utf8");
  assert.equal(Number(/^STYLE_VERSION = (\d+)/m.exec(py)[1]), STYLE_VERSION);
});

await t("the key is illustrated.key_of(item, cut): sha1 of version | [cut|] words, first 16 hex (python gave these two)", async () => {
  const s = { title: "Yale tapis", lead: "Pasukan Yale", points: ["Daripada 915"], note: "note" };
  assert.equal(wordsOf(s), "Yale tapis\nPasukan Yale\nDaripada 915\nnote");
  assert.equal(await artKey(s, false), "5f3d9445837c3fc6");
  assert.equal(await artKey(s, true), "035fa63f11f86d84");
  assert.equal(wordsOf({ title: "A" }), "A\n\n", "missing lead and note are empty lines, as in python");
});

await t("the index reads every job's art, the newest job winning, and ignores what has no address", () => {
  const idx = artIndex([{ meta: { art: { k1: { url: "new" }, k2: { url: "" } } } }, { meta: { art: { k1: { url: "old" }, k3: { url: "u3" } } } }, { meta: {} }, null]);
  assert.equal(idx.get("k1"), "new"); assert.equal(idx.get("k3"), "u3"); assert.equal(idx.has("k2"), false);
});

await t("a slide gets its own drawing by its words, cut and page apart", async () => {
  const s = { title: "Yale tapis", lead: "Pasukan Yale", points: ["Daripada 915"], note: "note" };
  const jobs = [{ meta: { art: { "5f3d9445837c3fc6": { url: "page.jpg" }, "035fa63f11f86d84": { url: "cut.png" } } } }];
  assert.deepEqual(await artFor([s, { title: "Other" }], jobs), [{ cut: "cut.png", page: "page.jpg" }, { cut: "", page: "" }]);
  assert.deepEqual(await artFor([s], []), [{ cut: "", page: "" }], "no job, no drawing");
});

await t("the cut-out takes the white page round a drawing away and grows a white border, keeping white INSIDE the drawing", () => {
  const w = 60, h = 40, px = new Uint8ClampedArray(w * h * 4).fill(255);
  const put = (x, y, rgb) => { const i = (y * w + x) * 4; px[i] = rgb[0]; px[i + 1] = rgb[1]; px[i + 2] = rgb[2]; };
  for (let y = 10; y < 30; y++) for (let x = 20; x < 40; x++) put(x, y, (x === 20 || x === 39 || y === 10 || y === 29) ? [20, 20, 20] : [255, 255, 255]);   // a ring, white inside
  assert.equal(cutPixels(px, w, h, 3), true);
  const a = (x, y) => px[(y * w + x) * 4 + 3];
  assert.equal(a(0, 0), 0, "the far page is transparent");
  assert.equal(a(30, 20), 255, "white inside the ring is kept");
  assert.equal(a(18, 20), 255, "a sticker border stands just outside the ink");
  assert.equal(px[(20 * w + 18) * 4], 255, "and it is white");
  assert.equal(a(10, 20), 0, "beyond the border it is transparent again");
  const full = new Uint8ClampedArray(8 * 8 * 4).fill(10); for (let i = 3; i < full.length; i += 4) full[i] = 255;
  assert.equal(cutPixels(full, 8, 8, 2), false, "a picture with no white edge is left alone");
});

await t("the picker is wired: the editor hands its slide jobs over, and a drawn slide shows its own drawing in every tile", () => {
  const picker = readFileSync(new URL("./src/components/LookPicker.jsx", import.meta.url), "utf8");
  const editor = readFileSync(new URL("./src/components/SlidesEditor.jsx", import.meta.url), "utf8");
  assert.match(editor, /<LookPicker[^>]*artJobs=\{jobs\}/);
  assert.match(picker, /useSlideArt\(words, artJobs\)/);
  assert.match(picker, /s\.art_page \? \{ \.\.\.s, art_url: s\.art_page \}/, "Diari's tile takes the whole page");
});

await t("the cover's title is ONE COMPLETE SENTENCE: the worker's own choice when it drew this hook, else the hook's first whole sentence", async () => {
  assert.equal(leadSentence("Aku: esok lah aku fikir pasal mikrobiom kulit kepala. Lepas tu aku: baca kajian 12 minggu ni."), "Aku: esok lah aku fikir pasal mikrobiom kulit kepala");
  assert.equal(leadSentence("Natural boleh lawan UV. Tapi jangan langkau peraturan."), "Natural boleh lawan UV", "a short first sentence is kept whole");
  assert.equal(leadSentence("Satu dua tiga empat lima enam tujuh lapan sembilan, sepuluh sebelas dua belas tiga belas empat belas lima belas enam belas tujuh belas lapan belas sembilan belas dua puluh dua puluh satu dua puluh dua dua puluh tiga"), "Satu dua tiga empat lima enam tujuh lapan sembilan", "a very long sentence is cut at its last comma, never mid-clause");
  const hook = "Soalan yang takde sapa tanya pasal sunblock masa depan yang semua orang patut tahu sebelum beli";
  const jobs = [{ status: "done", meta: { cover_title: "Sunblock masa depan", slides: [{ title: hook }] } }];
  assert.equal(coverTitleFor({ title: hook }, jobs), "Sunblock masa depan");
  assert.equal(coverTitleFor({ title: hook }, []), hook, "no sentence break: the whole hook, never a few words cut off it");
  assert.equal(coverTitleFor({ title: "Perasaan tu bila kau dah submit borang NPRA tapi tak tahu status" }, []), "Perasaan tu bila kau dah submit borang NPRA tapi tak tahu status", "12 words or fewer stays whole");
  assert.equal(coverTitleFor({ title: "Another hook" }, jobs), "Another hook", "a title chosen for another hook is not borrowed");
  const first = { title: hook, points: [] };
  assert.equal(await coverArtUrl(first, [{ meta: { art: { ["cover|" + await artKey(first)]: { url: "cover.png" } } } }]), "cover.png");
  assert.equal(await coverArtUrl(first, []), "");
});

await t("the editor offers Refresh and Build-from-the-caption-and-draw, and a render can be asked fresh", () => {
  const ed = readFileSync(new URL("./src/components/PostEditor.jsx", import.meta.url), "utf8");
  const sl = readFileSync(new URL("./src/components/SlidesEditor.jsx", import.meta.url), "utf8");
  assert.match(ed, /async function renderSlides\(refresh = false\)/);
  assert.match(ed, /onRefresh=\{\(\) => renderSlides\(true\)\}/);
  assert.match(ed, /onBuildAndDraw=\{\(\) => setDrawNext\(Date\.now\(\)\)\}/);
  assert.match(sl, /fromCaption\(false, true\)/);
  assert.match(sl, /onClick=\{onRefresh\}/);
  assert.match(sl, /disabled=\{busy \|\| drawing/, "one drawing at a time");
});

await t("a drawing on CREAM paper (a stored Diari picture) is cut out by its own page colour; a picture that fills its frame is left alone", () => {
  const w = 60, h = 40, cream = [250, 236, 205];
  const px = new Uint8ClampedArray(w * h * 4);
  for (let i = 0; i < w * h; i++) { px[i * 4] = cream[0] + (i % 5); px[i * 4 + 1] = cream[1]; px[i * 4 + 2] = cream[2]; px[i * 4 + 3] = 255; }   // a little paper grain
  for (let y = 10; y < 30; y++) for (let x = 20; x < 40; x++) { const i = (y * w + x) * 4; const edge = x === 20 || x === 39 || y === 10 || y === 29; px[i] = edge ? 30 : cream[0]; px[i + 1] = edge ? 30 : cream[1]; px[i + 2] = edge ? 30 : cream[2]; }
  assert.deepEqual(pageColour(px, w, h).map((v) => Math.round(v / 10)), cream.map((v) => Math.round(v / 10)));
  assert.equal(cutPixels(px, w, h, 3), true);
  const a = (x, y) => px[(y * w + x) * 4 + 3];
  assert.equal(a(0, 0), 0, "the cream page is transparent"); assert.equal(a(30, 20), 255, "the cream inside the ring stays"); assert.equal(a(18, 20), 255, "with a sticker border outside the ink");
  const dark = new Uint8ClampedArray(8 * 8 * 4).fill(40); for (let i = 3; i < dark.length; i += 4) dark[i] = 255;
  assert.equal(pageColour(dark, 8, 8), null); assert.equal(cutPixels(dark, 8, 8, 2), false);
});

console.log(`slideArt: ${n} checks passed`);
