/* web/src/lib/slotCheck.js: the four colours of the post-slot check (Wan, 11 Nov 2026). */
import assert from "node:assert/strict";
import { channelState, channelsOf, postState, slotRows, tally } from "./src/lib/slotCheck.js";

const NOW = Date.parse("2026-11-11T05:30:00Z");       // 13:30 MYT: the 13:00 slot was 30 minutes ago
let n = 0;
const t = (name, fn) => { fn(); n++; };
const post = (o = {}) => ({ id: "p", stream: "regulab", status: "scheduled", date: "2026-11-11", slot: "13:00", channels: ["threads"],
  published: {}, errors: {}, ...o });
const rec = (status) => ({ id: "z1", route: "zernio", status });

t("green: the platform has it, and the link comes with it", () => {
  const c = channelState(post({ published: { threads: { ...rec("sent"), url: "https://www.threads.com/@x/post/1" } } }), "threads", NOW);
  assert.equal(c.state, "passed");
  assert.equal(c.url, "https://www.threads.com/@x/post/1");
});
t("yellow: handed to Zernio and not yet due, or approved and waiting to be handed over", () => {
  assert.equal(channelState(post({ slot: "21:00", published: { threads: rec("scheduled") } }), "threads", NOW).state, "queued");
  assert.equal(channelState(post({ status: "approved", slot: "21:00" }), "threads", NOW).state, "queued");
});
t("red: refused, with the platform's own words", () => {
  const c = channelState(post({ status: "approved", published: { threads: rec("error") },
    errors: { threads: { message: "threads: The parameter text is required" } } }), "threads", NOW);
  assert.equal(c.state, "failed");
  assert.match(c.detail, /parameter text is required/);
});
t("red: still not sent 20 minutes after its slot (stuck), but not at 10", () => {
  assert.equal(channelState(post({ published: { threads: rec("scheduled") } }), "threads", NOW).state, "failed");
  const early = Date.parse("2026-11-11T05:10:00Z");
  assert.equal(channelState(post({ published: { threads: rec("scheduled") } }), "threads", early).state, "queued");
});
t("red: approved, its slot passed more than 45 minutes ago and never handed over (missed); blocked by the scan", () => {
  assert.equal(channelState(post({ status: "approved", slot: "08:00" }), "threads", NOW).state, "failed");
  const b = channelState(post({ status: "approved", slot: "21:00", errors: { scan: ["Caption (threads): empty"] } }), "threads", NOW);
  assert.equal(b.state, "failed");
  assert.match(b.detail, /empty/);
});
t("magenta: a draft waits for approval, whatever else it holds", () => {
  assert.equal(channelState(post({ status: "draft" }), "threads", NOW).state, "waiting");
  assert.equal(channelState(post({ status: "draft", slot: "08:00" }), "threads", NOW).state, "waiting");
});
t("a channel of a posted post that holds no record is not shown as a problem", () => {
  assert.equal(channelState(post({ status: "posted" }), "threads", NOW).state, "off");
});
t("channels: the ones queued to, plus any that hold a record (TikTok rides with a film); LinkedIn has itself", () => {
  assert.deepEqual(channelsOf(post({ channels: ["instagram", "threads"], published: { tiktok: rec("scheduled") } })).sort(),
    ["instagram", "threads", "tiktok"]);
  assert.deepEqual(channelsOf({ stream: "linkedin", published: {} }), ["linkedin"]);
  assert.deepEqual(channelsOf({ stream: "regulab" }).sort(), ["facebook", "instagram", "threads"]);
});
t("a post is its worst channel: red over magenta over yellow over green", () => {
  const cells = (...s) => s.map((state) => ({ state }));
  assert.equal(postState(cells("passed", "queued", "failed")), "failed");
  assert.equal(postState(cells("passed", "queued")), "queued");
  assert.equal(postState(cells("passed", "passed")), "passed");
  assert.equal(postState(cells("waiting", "queued")), "waiting");
  assert.equal(postState(cells("off")), "off");
});
t("rows: today onward, oldest first, rejected and archived left out, counted by colour", () => {
  const posts = [
    post({ id: "a", slot: "21:00", published: { threads: rec("scheduled") } }),
    post({ id: "b", slot: "08:00", status: "posted", published: { threads: { ...rec("sent"), url: "https://x" } } }),
    post({ id: "c", slot: "16:00", status: "draft" }),
    post({ id: "d", date: "2026-11-10", status: "posted", published: { threads: rec("sent") } }),
    post({ id: "e", status: "rejected" }),
    post({ id: "f", status: "posted", archived_at: "2026-11-11T00:00:00Z", published: { threads: rec("sent") } }),
    post({ id: "g", date: "2026-11-20", slot: "08:00", published: { threads: rec("scheduled") } }),
  ];
  const rows = slotRows(posts, { from: "2026-11-11", days: 7, now: NOW });
  assert.deepEqual(rows.map((r) => r.post.id), ["b", "c", "a"]);
  assert.deepEqual(tally(rows), { passed: 1, queued: 1, failed: 0, waiting: 1 });
  assert.deepEqual(slotRows(posts, { from: "2026-11-11", days: 400, now: NOW }).map((r) => r.post.id), ["b", "c", "a", "g"]);
});
console.log(`slotCheck: ${n} checks passed`);
