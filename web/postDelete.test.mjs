import assert from "node:assert/strict";
import { deleteCheck } from "./src/lib/postDelete.js";

assert.deepEqual(deleteCheck({ status: "draft" }), { ok: true, backToDraft: false });
assert.deepEqual(deleteCheck({ status: "rejected" }), { ok: true, backToDraft: false });
assert.deepEqual(deleteCheck({ status: "approved" }), { ok: true, backToDraft: true }, "an approved post goes back to draft first");
for (const status of ["scheduled", "posted", "archived"]) {
  const r = deleteCheck({ status });
  assert.equal(r.ok, false, status); assert.equal(r.why.length, 2, "a reason in both languages");
}
assert.equal(deleteCheck({ status: "approved", published: { facebook: { at: "x" } } }).ok, false, "a delivered channel keeps its record");
assert.equal(deleteCheck({ status: "draft", published: {} }).ok, true);
assert.equal(deleteCheck(null).ok, false);
assert.equal(deleteCheck({ status: "weird" }).ok, false);
console.log("post delete rules ok");
