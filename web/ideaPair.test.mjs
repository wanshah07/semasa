import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { BOTH, ideaRows, otherStreamRow, pairedIdea, streamOptions, streamsOf } from "./src/lib/ideaPair.js";

const common = { source_title: "NPRA notice", source_url: "https://example.org/n", note: "focus on SMEs", make_media: "image", reference_urls: ["u1"], status: "new", created_by: "u" };

// one stream stays one row, exactly as before: no pair marker
let rows = ideaRows(common, { choice: "regulab", domain: "kosmetik", angle: "B" });
assert.equal(rows.length, 1);
assert.deepEqual([rows[0].stream, rows[0].domain, rows[0].angle, rows[0].brief], ["regulab", "kosmetik", null, undefined]);
rows = ideaRows(common, { choice: "linkedin", domain: "kosmetik", angle: "B" });
assert.deepEqual([rows.length, rows[0].stream, rows[0].domain, rows[0].angle], [1, "linkedin", null, "B"]);

// both: two rows, each with only its own stream's field, sharing the issue and nothing else
rows = ideaRows(common, { choice: BOTH, domain: "kosmetik", angle: "B", pairId: "p1", brief: { look: "classic" } });
assert.equal(rows.length, 2);
const [r, l] = rows;
assert.deepEqual([r.stream, r.domain, r.angle], ["regulab", "kosmetik", null]);
assert.deepEqual([l.stream, l.domain, l.angle], ["linkedin", null, "B"]);
for (const x of rows) {
  assert.equal(x.source_title, "NPRA notice"); assert.equal(x.note, "focus on SMEs"); assert.deepEqual(x.reference_urls, ["u1"]);
  assert.equal(x.brief.pair, "p1"); assert.equal(x.brief.look, "classic");
}
assert.equal(r.brief.pair_stream, "linkedin"); assert.equal(l.brief.pair_stream, "regulab");
// the rows do not share one brief object: editing one must not edit the other
r.brief.look = "x"; assert.equal(l.brief.look, "classic");

// a slot asked for in the Schedule goes to its own stream only; the other stream is placed by the worker
rows = ideaRows(common, { choice: BOTH, pairId: "p2", position: { stream: "linkedin", date: "2026-11-10", slot: "06:00" } });
assert.equal(rows[0].brief.position, undefined);
assert.deepEqual(rows[1].brief.position, { date: "2026-11-10", slot: "06:00" });
// a slot for the other stream is not kept on a single-stream idea
rows = ideaRows(common, { choice: "regulab", position: { stream: "linkedin", date: "2026-11-10", slot: "06:00" } });
assert.equal(rows[0].brief, undefined);

// unknown choices fall back to ws.regulab, never to both
assert.deepEqual(streamsOf("nonsense"), ["regulab"]); assert.deepEqual(streamsOf(BOTH), ["regulab", "linkedin"]);
assert.deepEqual(streamOptions("Both").map((o) => o[0]), ["regulab", "linkedin", "both"]);

// the pair is found from either side; an idea without a pair, or whose partner is not loaded, finds none
const list = [{ id: "a", brief: { pair: "p" } }, { id: "b", brief: { pair: "p" } }, { id: "c", brief: {} }];
assert.equal(pairedIdea(list[0], list).id, "b"); assert.equal(pairedIdea(list[1], list).id, "a");
assert.equal(pairedIdea(list[2], list), null); assert.equal(pairedIdea(list[0], [list[0]]), null);

// the composer uses the helper and inserts both rows in ONE statement, so a failure leaves neither half behind
const src = readFileSync(new URL("./src/components/IdeaComposer.jsx", import.meta.url), "utf8");
assert.ok(src.includes("ideaRows(") && src.includes("insert(rows)"), "the composer inserts the rows together");
const tab = readFileSync(new URL("./src/pages/IdeasTab.jsx", import.meta.url), "utf8");
assert.ok(tab.includes("data-idea-pair"), "the Ideas list shows which idea a pair belongs with");
console.log("ideaPair: ok");

// the other stream of an existing post (the "For" switch in the post editor): a new idea in that voice, never the post converted
{
  const post = { id: "p9", stream: "regulab", hook: "Notifikasi bukan kelulusan", slides: [{ title: "a" }, { title: "b" }] };
  const idea = { source_title: "NPRA notice", source_url: "https://example.org/n", note: "SMEs", reference_urls: ["u1"], make_media: "image",
    brief: { look: "era", position: { date: "2026-11-12", slot: "08:00" }, pair: "old", pair_stream: "linkedin" } };
  const row = otherStreamRow(post, idea, { userId: "u", pairId: "p7" });
  assert.equal(row.stream, "linkedin"); assert.equal(row.domain, null); assert.equal(row.angle, null);
  assert.equal(row.source_title, "NPRA notice"); assert.deepEqual(row.reference_urls, ["u1"]); assert.equal(row.status, "new");
  assert.equal(row.make_slides, true);                                    // it was a carousel, so is the other version
  assert.deepEqual(row.brief, { look: "era", from_post: "p9", pair: "p7", pair_stream: "regulab" });   // the old slot and pair are not carried
  assert.equal(idea.brief.position.slot, "08:00");                        // the source idea is untouched
  // a hand-written post with no idea: the hook is the title; LinkedIn to ws.regulab goes the other way
  const back = otherStreamRow({ id: "p1", stream: "linkedin", hook: "A hook", slides: [] }, null, { userId: "u" });
  assert.equal(back.stream, "regulab"); assert.equal(back.source_title, "A hook"); assert.equal(back.make_slides, undefined);
  assert.deepEqual(back.brief, { from_post: "p1" });
}
console.log("ideaPair ok");
