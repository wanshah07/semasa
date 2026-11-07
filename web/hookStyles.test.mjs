import assert from "node:assert/strict";
import { BUILTIN, activeId, filesRefusal, isBusy, isReady, pickOptions, shapesToText, summaryLine, textToShapes, withHookStyle } from "./src/lib/hookStyles.js";

const t = (bm, en) => en;
const ready = (id, over = {}) => ({ id, name: `Style ${id}`, status: "ready", shapes: [{ family: "bold", text: "Stop buat ___ kalau kau nak ___" }], ...over });

// ready / busy
assert.equal(isReady(ready("a")), true);
assert.equal(isReady(ready("a", { status: "working" })), false);
assert.equal(isReady(ready("a", { shapes: [] })), false);
assert.equal(isReady(ready("a", { shapes: [{ text: "no blank" }] })), false);
assert.equal(isReady(null), false);
assert.deepEqual(["new", "working", "ready", "error"].map((status) => isBusy({ status })), [true, true, false, false]);

// the default: a saved id only counts while that style is ready
const styles = [ready("a"), ready("b", { status: "error" })];
assert.equal(activeId({ id: "a" }, styles), "a");
assert.equal(activeId({ id: "b" }, styles), BUILTIN, "an errored style is not used");
assert.equal(activeId({ id: "gone" }, styles), BUILTIN, "a deleted style is not used");
assert.equal(activeId({}, styles), BUILTIN);
assert.equal(activeId(undefined, []), BUILTIN);

// the select: follow the setting, the built-in, then each ready style
let opts = pickOptions(styles, t, { id: "a" });
assert.deepEqual(opts.map((o) => o[0]), ["", BUILTIN, "a"]);
assert.equal(opts[0][1], "Follow the setting (Style a)");
assert.equal(pickOptions(styles, t, {})[0][1], "Follow the setting (the built-in 25)");

// the idea's brief
assert.deepEqual(withHookStyle({ look: "x" }, "a"), { look: "x", hook_style: "a" });
assert.deepEqual(withHookStyle({ look: "x", hook_style: "a" }, ""), { look: "x" });
assert.deepEqual(withHookStyle(null, BUILTIN), { hook_style: BUILTIN });
assert.deepEqual(withHookStyle(undefined, ""), {});

// the editor
const shapes = [{ family: "bold", text: "Stop buat ___ kalau kau nak ___" }, { family: "other", text: "POV: kau ___ tapi ___" }];
assert.equal(shapesToText(shapes), "bold | Stop buat ___ kalau kau nak ___\nPOV: kau ___ tapi ___");
assert.deepEqual(textToShapes(shapesToText(shapes)), { shapes, bad: [] });
let got = textToShapes("bold | Stop buat ____ kalau kau nak ___\n\nno blank here\nstop buat ___ kalau kau nak ___\nweird | Aku ___ je\n___\n" + "x".repeat(170) + " ___");
assert.deepEqual(got.shapes, [{ family: "bold", text: "Stop buat ___ kalau kau nak ___" }, { family: "other", text: "weird | Aku ___ je" }]);
assert.equal(got.bad.length, 3, "a line with no blank, with nothing fixed, or too long is refused and said");
assert.equal(textToShapes("").shapes.length, 0);
assert.equal(textToShapes(Array.from({ length: 50 }, (_, i) => `Hook nomor ${"abcdefghij"[i % 10]}${i} ___ lagi`).join("\n")).shapes.length, 30);

// one line for a row
assert.equal(summaryLine(ready("a"), t), "1 hook shapes");
assert.equal(summaryLine({ status: "error", error: "no hook could be read" }, t), "no hook could be read");
assert.equal(summaryLine({ status: "working" }, t), "The bot is reading the screenshots.");
assert.equal(summaryLine(null, t), "");

// the files
const png = (name = "a.png") => ({ name, type: "image/png" });
assert.match(filesRefusal([], t), /at least one/);
assert.match(filesRefusal(Array.from({ length: 9 }, () => png()), t), /At most 8/);
assert.match(filesRefusal([png(), { name: "x.pdf", type: "application/pdf" }], t), /x\.pdf/);
assert.equal(filesRefusal([png(), { name: "b.jpg", type: "image/jpeg" }, { name: "c.webp", type: "image/webp" }], t), "");
console.log("hookStyles.test.mjs: ok");
