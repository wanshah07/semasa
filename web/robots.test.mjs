import assert from "node:assert/strict";
import { THEMES, colourFor, toneFor } from "./src/lib/robots.js";
import { ROBOTS, robotsWith } from "./src/lib/aiTeam.js";

// every built-in robot has a tone of its own, and no two share a colour (Wan, 24 Nov 2026: "all bot live have their own colors")
const builtIn = Object.entries(ROBOTS).map(([slug, r]) => [slug, toneFor(r)]);
assert.deepEqual(builtIn, [["rootsys", "afiq"], ["mireld", "mireld"], ["kiosapi", "kios"], ["gemini", "gemini"], ["chatgpt", "chatgpt"]]);
const providers = Array.from({ length: 5 }, (_, i) => ({ id: `p${i}`, name: `P${i}`, created_at: `2026-11-0${i + 1}T00:00:00Z` }));
const all = robotsWith(providers);
const cards = Object.values(all);
const colours = cards.slice(0, 9).map((c) => colourFor(c));
assert.equal(new Set(colours).size, 9, "the five built-in robots and the first four providers: nine different colours");
assert.deepEqual(["p0", "p1", "p2", "p3", "p4"].map((s) => toneFor(all[s])), ["provider", "provider2", "provider3", "provider4", "provider"]);
for (const c of cards) assert.ok(THEMES[toneFor(c)], `${c.robot} draws with a real theme`);

// offline is the same grey whichever robot it is; an unknown tone is the guest slate
assert.equal(colourFor(all.rootsys, false), colourFor(all.chatgpt, false));
assert.notEqual(colourFor(all.rootsys, true), colourFor(all.rootsys, false));
assert.equal(toneFor({ tone: "nobody", robot: "W?" }), "guest");
assert.equal(toneFor(null), "guest");
assert.equal(toneFor({ tone: "provider", robot: "W6" }), "provider");
console.log("robots: ok");
