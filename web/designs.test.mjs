/* My designs in the page: look values, snapshots, and a deleted design never breaking a draft. */
import assert from "node:assert/strict";
import { designToken, lookValueOf, newDesignId, packDesign, resolveLook, tokenId } from "./src/lib/designs.js";

let n = 0;
const t = (name, fn) => { try { fn(); n++; } catch (e) { console.error("FAIL:", name); throw e; } };
const D = [{ id: "ab12cd", name: "Biru", look: "era", cover: "e_hook", middle: "g_check", accent: "#0a7c6e", bg: "lib:g_makmal02", junk: 5 },
  { id: "zz99yy", name: "Bad", look: "classic" }];

t("a look value is a plain look or d:<id>", () => {
  assert.equal(designToken("ab12cd"), "d:ab12cd");
  assert.equal(tokenId("d:ab12cd"), "ab12cd"); assert.equal(tokenId("grid"), ""); assert.equal(tokenId("d:x"), ""); assert.equal(tokenId(null), "");
  assert.match(newDesignId(), /^x[a-z0-9]{3,}$/);
});

t("a snapshot keeps only known string keys of a Studio family", () => {
  const p = packDesign(D[0]);
  assert.deepEqual(p, { look: "era", cover: "e_hook", middle: "g_check", accent: "#0a7c6e", bg: "lib:g_makmal02" });
  assert.equal(packDesign(D[1]), null); assert.equal(packDesign(null), null);
});

t("resolving a design gives its family, the renderer's normalised design and the snapshot; a wrong-family template is dropped there", () => {
  const r = resolveLook("d:ab12cd", D);
  assert.equal(r.look, "era"); assert.equal(r.id, "ab12cd"); assert.equal(r.pack.cover, "e_hook");
  assert.equal(r.design.cover, "e_hook"); assert.ok(!("middle" in r.design));            // g_check is a grid template, the design is ERA
});

t("a plain look is left alone, and a deleted or unusable design is Semasa's own drawing, never an error", () => {
  assert.deepEqual(resolveLook("grid", D), { look: "grid", design: null, pack: null, id: "" });
  assert.equal(resolveLook("d:gone1234", D).look, "classic");
  assert.equal(resolveLook("d:zz99yy", D).look, "classic");
  assert.equal(resolveLook("", D).look, "classic");
});

t("the look value of a drawn job comes back as its design while that design exists", () => {
  assert.equal(lookValueOf({ look: "era", design_id: "ab12cd" }, D), "d:ab12cd");
  assert.equal(lookValueOf({ look: "era", design_id: "gone1234" }, D), "era");
  assert.equal(lookValueOf({ look: "grid" }, D), "grid"); assert.equal(lookValueOf(undefined, D), "classic");
});

console.log(`designs: ${n} cases ok`);
