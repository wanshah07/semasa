/* Speaker photos on the event poster: the token rules shared with the worker, and the helpers the editor uses. */
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

// compliance.js imports the rules as JSON, which Node wants an attribute for; inline them (as compliance.test.mjs does) beside photos.js
const here = new URL(".", import.meta.url);
const dir = mkdtempSync(join(tmpdir(), "photos-"));
writeFileSync(join(dir, "compliance.js"), readFileSync(new URL("src/lib/compliance.js", here), "utf8")
  .replace(/^import RULES from .*$/m, `const RULES = ${readFileSync(new URL("../rules/compliance.json", here), "utf8")};`));
writeFileSync(join(dir, "photos.js"), readFileSync(new URL("src/lib/photos.js", here), "utf8"));
const { normaliseSlides, photoTokens } = await import(pathToFileURL(join(dir, "compliance.js")).href);
const { photoAt, photoPath, photoToken, photosFollow, speakersOf, withPhoto } = await import(pathToFileURL(join(dir, "photos.js")).href);

let n = 0;
const t = (name, fn) => { try { fn(); n++; } catch (e) { console.error("FAIL:", name); throw e; } };
const U = "0b1c2d3e-4f50-4a6b-8c7d-9e0f1a2b3c4d";
const A = `ref:${U}/a.jpg`, B = `ref:${U}/b_2.png`, C = `ref:${U}/c.webp`;

t("a token is only ever a file in the reference bucket under a user id", () => {
  assert.deepEqual(photoTokens(`${A},,${B}`), [A, "", B]);
  assert.deepEqual(photoTokens(` ${A} , http://x/y.jpg ,, `), [A]);          // an address, a blank and trailing blanks are dropped
  assert.deepEqual(photoTokens(`ref:nope/a.jpg,${A}`), ["", A]);
  assert.deepEqual(photoTokens(`ref:${U}/../x.jpg`), []);                     // no path tricks
  assert.deepEqual(photoTokens(`${A},${A},${A},${A},${A},${A},${B}`).length, 6);
  assert.deepEqual(photoTokens(null), []);
});

t("a slide keeps well-formed photos only, and a slide without any stores none", () => {
  const s = normaliseSlides([{ title: "x", points: ["Dr A | USA", "Prof B | FR"], photos: `${A},,${B},` }])[0];
  assert.equal(s.photos, `${A},,${B}`);
  assert.equal("photos" in normaliseSlides([{ title: "x", points: ["a"], photos: ", ,http://x" }])[0], false);
});

t("setting, removing and reading a speaker's photo", () => {
  let v = withPhoto("", 2, B);
  assert.equal(v, `,,${B}`);
  v = withPhoto(v, 0, A);
  assert.equal(v, `${A},,${B}`);
  assert.equal(photoAt(v, 0), A); assert.equal(photoAt(v, 1), ""); assert.equal(photoAt(v, 2), B);
  assert.equal(withPhoto(v, 2, ""), A);                                        // trailing blanks go
  assert.equal(withPhoto(v, 9, A), v);                                         // only six speakers have a slot
  assert.equal(photoPath(A), `${U}/a.jpg`); assert.equal(photoToken(`${U}/a.jpg`), A); assert.equal(photoPath("lib:g_x"), "");
});

t("photos follow a speaker who is moved or removed, and stay put while a name is being typed", () => {
  const pts = (...names) => speakersOf(names.map((x) => `${x} | X`).join("\n"));
  const v = `${A},${B},${C}`;
  assert.equal(photosFollow(v, pts("Ann", "Bob", "Cat"), pts("Cat", "Ann", "Bob")), `${C},${A},${B}`);   // reordered
  assert.equal(photosFollow(v, pts("Ann", "Bob", "Cat"), pts("Ann", "Cat")), `${A},${C}`);               // Bob removed
  assert.equal(photosFollow(v, pts("Ann", "Bob", "Cat"), pts("Ann", "Bobby", "Cat")), v);                // a name edited: by position
  assert.equal(photosFollow(v, pts("Ann", "Bob", "Cat"), pts("Ann", "Bob", "Cat", "Dee")), v);           // one added at the end
  assert.equal(photosFollow("", pts("Ann"), pts("Ann", "Bob")), "");
  assert.deepEqual(speakersOf("Dr A | USA\n\n  Prof B  "), [{ name: "Dr A", where: "USA" }, { name: "Prof B", where: "" }]);
});

console.log(`photos: ${n} cases ok`);
