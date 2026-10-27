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
copyFileSync(new URL("src/lib/platformFormat.js", here), join(dir, "platformFormat.js"));
copyFileSync(new URL("src/lib/motionQueue.js", here), join(dir, "motionQueue.js"));
const { CHANNEL_LABEL, canQueue, channelsFor, filmFormat, fitCaption, inMotionList, pickPosition, postLang, queueArgs, startingCaptions } =
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
  assert.equal(postLang({ language: "bm", stream: "linkedin" }), "en", "LinkedIn is English whatever the film's language");
});

t("a LinkedIn caption that reads as Malay is never offered, so the post starts from English or nothing", () => {
  const MALAY = "Notifikasi kosmetik bukan kelulusan produk. NPRA menyemak dokumen selepas produk dipasarkan dan syarikat akan bertanggungjawab untuk semua tuntutan.";
  const ENGLISH = "A cosmetic notification is not an approval. NPRA reviews the file after the product is on sale.";
  const bmFilm = { stream: "linkedin", language: "bm", title: "Tajuk", captions: { linkedin: MALAY } };
  assert.equal(startingCaptions({ film: bmFilm, post: { text: { bm: { linkedin: MALAY } } }, channels: ["linkedin"] }).linkedin, "");
  assert.equal(startingCaptions({ film: bmFilm, post: { text: { en: { linkedin: ENGLISH } } }, channels: ["linkedin"] }).linkedin, ENGLISH,
    "the idea's own English draft is the start when the film's caption is Malay");
  assert.equal(startingCaptions({ film: { ...bmFilm, captions: { linkedin: ENGLISH } }, post: null, channels: ["linkedin"] }).linkedin, ENGLISH);
  assert.equal(startingCaptions({ film: { ...bmFilm, stream: "regulab", captions: { instagram: MALAY } }, post: null, channels: ["instagram"] }).instagram,
    MALAY, "ws.regulab keeps its Malay");
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

t("approve is Wan's own click and is taken only when nothing blocks", () => {
  const ok = queueArgs({ film, channels: ["instagram"], captions: { instagram: CAP }, date: "2026-10-27", slot: "13:00", brand: BRAND, approve: true });
  assert.equal(ok.p_approve, true);
  assert.equal(queueArgs({ film, channels: ["instagram"], captions: { instagram: CAP }, date: "2026-10-27", slot: "13:00", brand: BRAND }).p_approve, false);
  const blocked = queueArgs({ film, channels: ["threads"], captions: { threads: "" }, date: "2026-10-27", slot: "13:00", brand: BRAND, approve: true });
  assert.equal(blocked.p_hard, 1); assert.equal(blocked.p_approve, false);
});

const LONG = "Senarai ketoksikan memberitahu kita apa yang berlaku. Peta AOP mula memberitahu kita bagaimana ia berlaku.\n\n"
  + "Itulah sebabnya ulasan kritikal ini menarik perhatian saya. Ia menggunakan pendekatan PRISMA-ScR. ".repeat(12) + "\n\n#kosmetik #npra #toksikologi";

t("a caption is fitted to its platform: the 1,553-character caption of 26 Oct no longer lands on Threads", () => {
  for (const [p, [max, tags]] of Object.entries({ instagram: [2200, 8], facebook: [63206, 3], threads: [500, 1] })) {
    const out = fitCaption(LONG, "regulab", p);
    assert.ok(out.length <= max, p);
    assert.ok(out.split(/\s+/).filter((w) => w.startsWith("#")).length <= tags, p);
  }
  const th = fitCaption(LONG, "regulab", "threads");
  assert.ok(th.startsWith("Senarai ketoksikan") && th.split("\n\n")[0].endsWith(".") && th.endsWith("#kosmetik"));
  assert.equal(fitCaption("Pendek sahaja.", "regulab", "threads"), "Pendek sahaja.");
  assert.ok(fitCaption("x".repeat(4000), "linkedin", "linkedin").length <= 3000, "no space to cut at: still inside the limit");
});

t("each platform starts from its own caption: the worker's, else the draft's, always inside the limits", () => {
  const written = { ...film, captions: { instagram: "Satu.\n\n#a", facebook: "Dua.", threads: "Tiga." } };
  assert.deepEqual(startingCaptions({ film: written, post: null, channels: ["instagram", "facebook", "threads"] }),
    { instagram: "Satu.\n\n#a", facebook: "Dua.", threads: "Tiga." });
  const draft = { text: { bm: { instagram: LONG } } };           // an older film: only the draft, one long caption for every platform
  const got = startingCaptions({ film, post: draft, channels: ["instagram", "facebook", "threads"] });
  assert.ok(got.threads.length <= 500 && got.instagram.length <= 2200 && got.facebook.length <= 63206);
  assert.ok(got.threads.length < got.facebook.length || got.threads === got.facebook, "Threads is the shortest");
  const li = startingCaptions({ film: { stream: "linkedin", language: "en", captions: { linkedin: "I read the instrument." } }, post: null, channels: ["linkedin"] });
  assert.deepEqual(li, { linkedin: "I read the instrument." });
});

t("a film is checked against the format of its platform", () => {
  assert.deepEqual(filmFormat({ stream: "regulab", resolution: "portrait" }), { want: "portrait", ok: true });
  assert.deepEqual(filmFormat({ stream: "linkedin", resolution: "portrait" }), { want: "square", ok: false });
  assert.equal(filmFormat({ stream: "linkedin", resolution: "square" }).ok, true);
  assert.equal(filmFormat({ stream: "linkedin" }).ok, true, "a row with no size follows the platform");
});

t("a booked slot can be taken from a draft or an approved post: the queue call carries p_override only when asked", () => {
  const base = { film, channels: ["instagram"], captions: { instagram: CAP }, date: "2026-10-27", slot: "13:00", brand: BRAND };
  assert.equal(queueArgs(base).p_override, false);
  assert.equal(queueArgs({ ...base, override: true }).p_override, true);
  assert.equal(queueArgs({ ...base, override: true, approve: true }).p_approve, true, "overriding a slot is not approving");
});

console.log(`${n} motion queue cases pass`);
