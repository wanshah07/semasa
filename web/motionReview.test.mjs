import assert from "node:assert/strict";
import { canContinue, changed, continueFields, decideWords, hasStoryboardColumns, isReview, remakeFields, scenesOf, withEdits, writtenEpoch } from "./src/lib/motionReview.js";
import { STATUS_WORDS, motionTrack } from "./src/lib/motion.js";

// Wan, 7 Nov 2026: "make sure all storyboard appear and approve before proceed for motion creation"
const explainer = { kind: "explainer", note: "Storyboard by Gemini", written_at: "2026-11-07T01:00:00+00:00",
  plan: { title: "PFAS", hook: "Tiga perkara", scenes: [
    { id: "s1", kicker: "Hook", heading: "Tiga perkara", lines: ["satu", "dua"], narration: "Hai.", shot: "A lab bench", hook_shape: 21 },
    { id: "s2", kicker: "Fakta", heading: "PFAS kekal", lines: [], narration: "PFAS kekal lama." },
    { id: "brand-outro", heading: "Ikuti kami", lines: [], narration: "Ikuti kami" }] } };

// every scene appears, the outro is shown but never editable
const sc = scenesOf(explainer);
assert.deepEqual(sc.map((x) => x.heading), ["Tiga perkara", "PFAS kekal", "Ikuti kami"]);
assert.equal(sc[0].hookShape, 21);
assert.deepEqual(sc[2].edit, { heading: false, lines: false, said: false, shot: false });
assert.equal(sc[1].edit.shot, false, "a scene with no shot gets no picture field to invent one");

// edits go back into the same shape the worker reads; everything else is kept as saved
const edited = withEdits(explainer, { e0: { heading: "Tiga perkara baharu", lines: "satu\n\n dua \ntiga" }, e2: { heading: "hack" } });
assert.equal(edited.plan.scenes[0].heading, "Tiga perkara baharu");
assert.equal(edited.plan.hook, "Tiga perkara baharu", "the hook is scene 1's heading");
assert.deepEqual(edited.plan.scenes[0].lines, ["satu", "dua", "tiga"]);
assert.equal(edited.plan.scenes[2].heading, "Ikuti kami", "the outro cannot be edited");
assert.equal(edited.plan.scenes[0].hook_shape, 21);
assert.equal(explainer.plan.scenes[0].heading, "Tiga perkara", "the saved storyboard is not mutated");
assert.equal(changed(explainer, {}), false);
assert.equal(changed(explainer, { e0: { heading: "Tiga perkara" } }), false);
assert.equal(changed(explainer, { e1: { said: "Lain." } }), true);

// a photo story: scene 1's words are the hook, the closing card is title + subtitle
const story = { kind: "story", sb: { title: "Malaysia", subtitle: "Tempat", hook: "Hook satu", hook_shape: 1,
  scenes: [1, 2, 3, 4, 5].map((i) => ({ caption: i === 1 ? "Hook satu" : `Sudut ${i}`, prompt: `forest ${i}`, accent: "#6f8fb8" })) } };
const ss = scenesOf(story);
assert.equal(ss.length, 6);
assert.equal(ss[0].heading, "Hook satu"); assert.equal(ss[5].heading, "Malaysia");
const se = withEdits(story, { s0: { heading: "Hook dua" }, s2: { shot: "beach" }, end: { lines: "Tempat lain" } });
assert.equal(se.sb.hook, "Hook dua"); assert.equal(se.sb.scenes[0].caption, "Hook dua");
assert.equal(se.sb.scenes[2].prompt, "beach"); assert.equal(se.sb.subtitle, "Tempat lain");

// a showcase: intro, one per product, finale
const show = { kind: "showcase", sb: { title: "Serum", hook: "Hook", hook_shape: 1, headline: ["SAINS", "KULIT"], caption: "Tiga pilihan",
  background: "water", products: [{ name: "Satu", benefits: ["Ringan"], accent: "#d0335f" }] } };
assert.deepEqual(scenesOf(show).map((x) => x.key), ["intro", "p0", "finale"]);
const sh = withEdits(show, { p0: { lines: "Ringan\nTidak melekit" }, finale: { lines: "SAINS\nRAMBUT" } });
assert.deepEqual(sh.sb.products[0].benefits, ["Ringan", "Tidak melekit"]); assert.deepEqual(sh.sb.headline, ["SAINS", "RAMBUT"]);
assert.deepEqual(scenesOf(null), []); assert.deepEqual(scenesOf({ kind: "other" }), []);

// the status, the tracker and the buttons
assert.ok(isReview({ status: "review" })); assert.ok(!isReview({ status: "pending" }));
assert.deepEqual(STATUS_WORDS.review, ["Luluskan storyboard", "Approve the storyboard"]);
const track = motionTrack({ status: "review", stage: "storyboard", stage_times: { storyboard: "t1" } }, { L: 1, stamp: (x) => (x ? `@${x}` : "") });
assert.equal(track[1].isActive, true); assert.match(track[1].timestamp, /Waiting for your approval · @t1/);
assert.equal(track[2].isActive, false); assert.equal(track[2].isCompleted, false, "no picture before the approval");

// "Make again" asks for a new storyboard (and a new approval); a failed approved film can carry on from its storyboard
const withCols = { id: "m", status: "done", storyboard: explainer, storyboard_approved_at: "x" };
assert.deepEqual(remakeFields(withCols), { status: "pending", attempts: 0, error: "", storyboard: null, storyboard_approved_at: null, storyboard_approved_by: null, stage: "" });
assert.deepEqual(remakeFields({ id: "m", status: "done" }), { status: "pending", attempts: 0, error: "" }, "before 071 no unknown column is written");
assert.ok(hasStoryboardColumns(withCols) && !hasStoryboardColumns({ id: "m" }));
assert.ok(canContinue({ ...withCols, status: "error" })); assert.ok(!canContinue({ ...withCols, storyboard_approved_at: null, status: "error" }));
assert.ok(!canContinue(withCols));
assert.deepEqual(continueFields(), { status: "pending", attempts: 0, error: "" });
assert.match(decideWords("ok", "approve", 0), /Diluluskan/); assert.match(decideWords("ok", "rewrite", 1), /new storyboard/);
assert.match(decideWords("status:pending", "approve", 1), /no longer waiting/);

// every decision names the storyboard it was made on (071 refuses one made on an older storyboard)
assert.equal(writtenEpoch(explainer), 1794013200); assert.equal(writtenEpoch({}), null); assert.equal(writtenEpoch(null), null);
assert.match(decideWords("changed", "approve", 0), /diganti/);

console.log("motionReview: ok");
