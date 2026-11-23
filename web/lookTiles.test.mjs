import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { LOOKS } from "./src/lib/cards/studio.js";

// Wan, 23 Nov 2026: "why journal not appear". The design picker draws a tile per look from a `tiles` object, and Diari had no entry in
// it, so its square showed a dot. Every look in the catalogue is drawn by studio.js except Semasa's own (a CSS tile) and Threads.
const picker = readFileSync(new URL("./src/components/LookPicker.jsx", import.meta.url), "utf8");
const body = /const tiles = \{([^}]*)\}/.exec(picker)?.[1] || "";
const have = body.split(",").map((x) => x.trim()).filter(Boolean);
const own = new Set(["classic", "threads"]);
const missing = LOOKS.map((l) => l.k).filter((k) => !own.has(k) && !have.includes(k));
assert.deepEqual(missing, [], "these looks have no preview tile in the picker: " + missing.join(", "));
for (const k of have) assert.ok(new RegExp(`const ${k} = usePreview\\(`).test(picker), `${k}'s preview is drawn`);
console.log("lookTiles: ok");
