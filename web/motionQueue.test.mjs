/* web/src/lib/motionQueue.js: a finished Motion film queued to the platforms Wan picks. */
import assert from "node:assert/strict";
import { copyFileSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

// Node needs an import attribute for JSON that Vite does not: compliance.js is copied with its rules inlined (as compliance.test.mjs does)
const here = new URL(".", import.meta.url);
const dir = mkdtempSync(join(tmpdir(), "mq-"));
const rules = readFileSync(new URL("../rules/compliance.json", here), "utf8");
writeFileSync(join(dir, "compliance.js"), readFileSync(new URL("src/lib/compliance.js", here), "utf8")
  .replace(/^import RULES from .*$/m, `const RULES = ${rules};`));
copyFileSync(new URL("src/lib/slots.js", here), join(dir, "slots.js"));
copyFileSync(new URL("src/lib/motionQueue.js", here), join(dir, "motionQueue.js"));
const { CHANNEL_LABEL, canQueue, channelsFor, inMotionList, pickPosition, postLang, queueArgs, startingCaptions } =
  await import(pathToFileURL(join(dir, "motionQueue.js")).href);

const BRAND = { regulab: { slots: ["08:00", "13:00", "21:00"], schedule: {} }, linkedin: { slots: ["06:00"] } };
const NOW = Date.parse("2026-10-26T05:00:00Z");           // 13:00 MYT
const CAP = "Notifikasi kosmetik bukan kelulusan produk. NPRA menyemak dokumen selepas produk dipasarkan.";
const film = { id: "f1", status: "done", video_url: "https://x/f.mp4", stream: "regulab", language: "bm", title: "Notifikasi bukan kelulusan" };
let n = 0;
const t = (name, fn) => { fn(); n++; };

t("a film is offered only the platforms of its own stream", () => {
  assert.deepEqual(channelsFor(film), ["instagram", "facebook", "threads"]);
  assert.deepEqual(channelsFor({ stream: "linkedin" }), ["linkedin"]);
  assert.deepEqual(Object.keys(CHANNEL_LABEL), ["facebook", "instagram", "threads", "linkedin"]);
});

t("the post's language follows the film, and a bilingual film the stream", () => {
  assert.equal(postLang(film), "bm");
  assert.equal(postLang({ language: "en", stream: "regulab" }), "en");
  assert.equal(postLang({ language: "both", stream: "regulab" }), "bm");
  assert.equal(postLang({ language: "both", stream: "linkedin" }), "en");
});

t("only a finished film that has not been queued can be queued, and a queued film leaves the Motion list", () => {
  assert.equal(canQueue(film), true);
  assert.equal(canQueue({ ...film, status: "working" }), false);
  assert.equal(canQueue({ ...film, video_url: "" }), false);
  assert.equal(canQueue({ ...film, queued_post_id: "p1" }), false);
  assert.equal(inMotionList(film), true);
  assert.equal(inMotionList({ ...film, queued_post_id: "p1" }), false);
});

t("captions start from the idea's own draft, platform by platform, else any of its words, else the title", () => {
  const post = { text: { bm: { instagram: CAP, threads: "Pendek." } } };
  assert.deepEqual(startingCaptions({ film, post, channels: ["instagram", "threads", "facebook"] }),
    { instagram: CAP, threads: "Pendek.", facebook: CAP });
  assert.deepEqual(startingCaptions({ film, post: null, channels: ["instagram"] }), { instagram: "Notifikasi bukan kelulusan" });
  assert.deepEqual(startingCaptions({ film: { ...film, language: "en" }, post: { text: { bm: { instagram: CAP } } }, channels: ["threads"] }),
    { threads: CAP });
});

t("the position is the next free one of the film's stream, never one already held", () => {
  const posts = [{ id: "a", stream: "regulab", status: "draft", date: "2026-10-26", slot: "21:00" },
    { id: "b", stream: "regulab", status: "approved", date: "2026-10-27", slot: "08:00" }];
  assert.deepEqual(pickPosition({ film, posts, brand: BRAND, now: NOW }), { date: "2026-10-27", slot: "13:00" });
  assert.deepEqual(pickPosition({ film, posts: [], brand: BRAND, now: NOW }), { date: "2026-10-26", slot: "21:00" });
});

t("the queue arguments carry the chosen platforms, one caption each, and the page's own scan", () => {
  const args = queueArgs({ film, channels: ["instagram", "threads"], captions: { instagram: CAP, threads: CAP }, date: "2026-10-27",
    slot: "13:00", brand: BRAND, post: { domain: "kosmetik", citation: "NPRA" } });
  assert.deepEqual(args.p_channels, ["instagram", "threads"]);
  assert.deepEqual(args.p_text, { bm: { instagram: CAP, threads: CAP } });
  assert.equal(args.p_motion, "f1"); assert.equal(args.p_lang, "bm"); assert.equal(args.p_citation, "NPRA");
  assert.equal(args.p_date, "2026-10-27"); assert.equal(args.p_slot, "13:00");
  assert.equal(args.p_hard, 0, "a clean caption on a film with its video has nothing blocking");
});

t("an empty caption or one over a platform's limit blocks approval, and only on the platforms chosen", () => {
  const long = "Perkataan ".repeat(60);                                  // 600 chars: over Threads' 500
  const blocked = queueArgs({ film, channels: ["threads"], captions: { threads: long }, date: "2026-10-27", slot: "13:00", brand: BRAND });
  assert.equal(blocked.p_hard, 1);
  assert.ok(blocked.p_flags.some((f) => f.hard && /threads/.test(f.where)));
  const empty = queueArgs({ film, channels: ["instagram", "threads"], captions: { instagram: CAP, threads: "" }, date: "2026-10-27", slot: "13:00", brand: BRAND });
  assert.equal(empty.p_hard, 1, "threads is empty, facebook is not on this post and is not asked for");
  const ig = queueArgs({ film, channels: ["instagram"], captions: { instagram: CAP }, date: "2026-10-27", slot: "13:00", brand: BRAND });
  assert.equal(ig.p_hard, 0);
});

console.log(`${n} motion queue cases pass`);
