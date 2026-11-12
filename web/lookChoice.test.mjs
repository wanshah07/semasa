import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { BUILTIN_LOOKS, DEFAULT_LOOK, hide, hiddenOf, offered, restore, startLook } from "./src/lib/lookChoice.js";
import { LOOKS } from "./src/lib/cards/studio.js";

// the built-in list is the page's own LOOKS, the same names the worker knows
assert.deepEqual(LOOKS.map((l) => l.k), BUILTIN_LOOKS);
assert.equal(DEFAULT_LOOK, "image");
assert.match(readFileSync(new URL("../backend/semasa/ideas.py", import.meta.url), "utf8"), /DEFAULT_LOOK = "image"/, "the worker's default is the page's");

// hiding: any built-in can go (Semasa and Grid too), it is only hidden, and it comes back
let h = hide([], "classic"); h = hide(h, "grid");
assert.deepEqual(h, ["classic", "grid"]);
assert.deepEqual(offered(LOOKS, h).map((l) => l.k), ["hand", "era", "photo", "image"]);
assert.deepEqual(restore(h, "classic"), ["grid"]);
assert.deepEqual(hide(h, "grid"), h, "hiding twice changes nothing");
assert.deepEqual(hide([], "nonsense"), [], "an unknown name is ignored");

// the picker is never empty: the last design left cannot be hidden
let all = []; for (const k of BUILTIN_LOOKS.filter((x) => x !== "image")) all = hide(all, k);
assert.deepEqual(hide(all, "image"), all);
assert.equal(offered(LOOKS, BUILTIN_LOOKS).length, LOOKS.length, "a list that hides everything shows everything");

// stored junk is cleaned, not trusted
assert.deepEqual(hiddenOf(["grid", "x", 3, null]), ["grid"]); assert.deepEqual(hiddenOf("grid"), []); assert.deepEqual(hiddenOf(undefined), []);

// a new post starts on: the default saved design, else Image, else the first look still offered
assert.equal(startLook({}), "image");
assert.equal(startLook({ designs: [{ id: "ab12" }], defaultId: "ab12" }), "d:ab12");
assert.equal(startLook({ designs: [{ id: "ab12" }], defaultId: "gone" }), "image", "a default that no longer exists is ignored");
assert.equal(startLook({ hidden: ["image"] }), "classic");
assert.equal(startLook({ hidden: ["image", "classic", "grid"] }), "hand");

// the picker offers the remove and restore controls, and the context saves into the existing default_design row (no SQL)
const picker = readFileSync(new URL("./src/components/LookPicker.jsx", import.meta.url), "utf8");
assert.ok(picker.includes("data-remove-look") && picker.includes("data-hidden-looks"));
const app = readFileSync(new URL("./src/App.jsx", import.meta.url), "utf8");
assert.ok(/setHiddenLooks:[^\n]*save\("default_design"/.test(app) && app.includes("delete next.id"), "setDefault keeps the hidden list, hiding keeps the default id");
console.log("lookChoice: ok");
