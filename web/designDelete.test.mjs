import assert from "node:assert/strict";
import { canDeleteDesign, ownsDesign } from "./src/lib/designDelete.js";

const me = { id: "u1" };
assert.equal(canDeleteDesign({ created_by: null }, me), true, "a worker-made picture (in a draft post) can be deleted");
assert.equal(canDeleteDesign({ created_by: "u1" }, me), true);
assert.equal(canDeleteDesign({ created_by: "u2" }, me), false, "another person's picture stays theirs");
assert.equal(canDeleteDesign({ created_by: null }, null), false, "signed out: no");
assert.equal(canDeleteDesign(null, me), false);
assert.equal(ownsDesign({ created_by: null }, me), false, "retry is only for the person who started the job");
assert.equal(ownsDesign({ created_by: "u1" }, me), true);
console.log("designDelete.test.mjs: ok");
