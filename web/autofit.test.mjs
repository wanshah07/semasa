// Auto-fit (Wan, 16 Nov 2026: "for all poster, single card, comic, image make auto-fit application"): whatever words a card
// is given, it fits by itself. Every card family measures its finished layout and hands the numbers to ONE search
// (web/src/lib/cards/studio.js fitSearch); the drawing is checked in a real browser by backend/tests/test_studio_cards.py.
// Here: the search itself, with layouts whose height is known, and the path a "too full" warning takes to the page. `npm test`.
import { readFileSync } from "node:fs";
import { capFill, fitSearch, FIT_MIN, SKIN_MIN, STUDIO_LOOKS } from "./src/lib/cards/studio.js";

let failed = 0;
const ok = (cond, what) => { if (!cond) { failed++; console.error("FAIL", what); } };

// LinkedIn type grows less than ws.regulab's (Wan, 21 Nov 2026): 60% of the family's own growth limit, never under the template's size
ok(capFill({ stream: "regulab" }, 3.4) === 3.4 && capFill(null, 3) === 3, "ws.regulab type grows as far as it did");
ok(Math.abs(capFill({ stream: "regulab", place: "middle" }, 3) - 1.8) < 1e-9 && capFill({ stream: "regulab", place: "cover" }, 3) === 3
  && capFill({ stream: "regulab", place: "single" }, 3) === 3, "ws.regulab content slides are calmer; the cover and a lone poster stay big");
ok(Math.abs(capFill({ stream: "linkedin" }, 3.4) - 2.04) < 1e-9 && capFill({ stream: "linkedin" }, 1.2) === 1, "LinkedIn type is capped, never below 1");

const ROOM = 1000;
// a paragraph of `chars` characters in a column 900 px wide: the lines get fewer as the type gets smaller, in whole steps
const para = (chars, px = 30) => (f) => Math.ceil((chars * px * f * 0.52) / 900) * Math.round(px * f * 1.35);
const smooth = (h1) => (f) => h1 * f * f;

{ // fuller than the card: the largest size that fits, never under the floor, never over the room
  const at = smooth(1500), f = await fitSearch(async (x) => at(x), at(1), ROOM, 2.2);
  ok(f < 1 && f >= FIT_MIN && at(f) <= ROOM, `a full card shrinks until it fits (${f})`);
  ok(at(f + 0.03) > ROOM, "and no further than it has to");
}
{ // cannot fit at a readable size: the floor comes back, and at the floor it still overflows (the painter then warns)
  const at = smooth(5000), f = await fitSearch(async (x) => at(x), at(1), ROOM, 2.2);
  ok(f === FIT_MIN && at(f) > ROOM, "a card that cannot fit at a readable size is drawn at the floor, to be refused");
}
{ // a sparse card grows, to the target and not past it
  const at = smooth(200), f = await fitSearch(async (x) => at(x), at(1), ROOM, 2.2, 0.72, 0.86);
  ok(f > 1.5 && at(f) <= 0.86 * ROOM + 1, `a sparse card grows to fill its room (${f})`);
  const capped = await fitSearch(async (x) => at(x), at(1), ROOM, 1.3, 0.72, 0.86);
  ok(capped > 1.2 && capped <= 1.3, "but never past its ceiling (the longest word, or the family's own)");
  ok(await fitSearch(async (x) => at(x), at(1), ROOM, 1.02) === 1, "a card whose longest word already fills the line does not grow");
}
{ // a card that already fills its room is not touched, and neither is one whose height does not follow its type
  const at = smooth(800);
  ok(await fitSearch(async (x) => at(x), at(1), ROOM, 2.2) === 1, "a compact card keeps its size");
  ok(await fitSearch(async () => 300, 300, ROOM, 2.2) === 1, "a layout whose height does not follow its text is left as it is");
}
{ // the height is not smooth (one more pixel pushes a word to the next line): whatever comes back really fits
  for (const chars of [400, 900, 1600, 2400, 3300]) {
    const at = para(chars), f = await fitSearch(async (x) => at(x), at(1), ROOM, 2.2);
    ok(f >= FIT_MIN && (at(f) <= ROOM || f === FIT_MIN), `${chars} characters: the size the search lands on holds (${f}, ${at(f)} of ${ROOM})`);
  }
}
ok(FIT_MIN >= 0.6 && FIT_MIN < 1 && SKIN_MIN >= 0.5, "the floors stay readable: a 30u line is never under 18 px on a 1080 px card");

// the warning's path: every family says so in the same words, renderSlides hands it on, the page shows it for whatever look is chosen
const src = readFileSync(new URL("./src/lib/cards/studio.js", import.meta.url), "utf8");
const painters = ["gridCardPaint", "eraCardPaint", "photoCardPaint", "morePaint", "picCardPaint", "handPaint", "skinPaint", "renderAyatCard"];
for (const fn of painters) {
  const at = src.indexOf("function " + fn + "("), end = src.indexOf("\n}\n", at);
  ok(at > 0 && /fuller than the card|FULL \+/.test(src.slice(at, end)), `${fn} warns when its words do not fit`);
}
ok(/out\.push\(\{ url: r\.url, warn: fullWarnFixed\(spec, r\)/.test(src), "renderSlides hands every card's warnings on");
const picker = readFileSync(new URL("./src/components/LookPicker.jsx", import.meta.url), "utf8");
ok(/all\.pics\.map\(\(p, i\) => \(\{ n: i \+ 1,\s*warn: \(p\.warn \|\| \[\]\)/.test(picker), "the page reads the warnings of every slide, whatever the look");
ok(/isStudioLook\(chosen\.look\) && !sample && problems\.length \? "full"/.test(picker) && picker.includes("Terlalu penuh untuk reka bentuk ini"), "and blocks the render with a message naming the slide");
ok(STUDIO_LOOKS.length === 13, "thirteen looks drawn by this renderer, all through the same path");

if (failed) { console.error(`${failed} auto-fit check(s) failed`); process.exit(1); }
console.log("autofit: one search fits every card, and a card that cannot fit says so");
