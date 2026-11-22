// Every caption inside its platform's limit (Wan, 22 Nov 2026), the page's twin of backend/tests/test_caption_fit.py.
import assert from "node:assert/strict";
import { copyFileSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

// Node needs an import attribute for JSON that Vite does not: compliance.js is copied with its rules inlined
const here = new URL(".", import.meta.url);
const dir = mkdtempSync(join(tmpdir(), "cf-"));
writeFileSync(join(dir, "compliance.js"), readFileSync(new URL("src/lib/compliance.js", here), "utf8")
  .replace(/^import RULES from .*$/m, `const RULES = ${readFileSync(new URL("../rules/compliance.json", here), "utf8")};`));
for (const f of ["slots.js", "platformFormat.js", "motionQueue.js", "captionFit.js"]) copyFileSync(new URL(`src/lib/${f}`, here), join(dir, f));
const at = (f) => import(pathToFileURL(join(dir, f)).href);
const { fitFor, fitText, limitOf, overLimit } = await at("captionFit.js");
const { hardCount, scan, threadParts } = await at("compliance.js");
const { queueArgs } = await at("motionQueue.js");

const HOOK = "Notifikasi kosmetik bukan kelulusan produk.";
const FOLLOW = "Follow untuk tip regulatori yang senang faham.";
const TAGS = "#halal #npra #kosmetik";
const long = (n) => `${HOOK}\n\n${Array.from({ length: n }, (_, i) => `${i + 1}. Fakta ${i + 1}. ${"Ayat penuh di sini. ".repeat(15).trim()}`).join("\n\n")}\n\n${FOLLOW}\n\n${TAGS}`;
let n = 0;
const ok = (name, fn) => { fn(); n += 1; console.log(`ok - ${name}`); };

ok("a caption inside its limit is returned exactly", () => {
  for (const p of ["instagram", "facebook", "threads"]) assert.equal(fitFor(HOOK, p, "regulab"), HOOK);
  assert.equal(fitFor("Short.", "linkedin", "linkedin"), "Short.");
});

ok("every platform ends inside its limit, keeping the hook, the follow line and the tags", () => {
  const cap = long(20);
  for (const [stream, plats] of [["regulab", ["instagram", "threads", "tiktok"]], ["linkedin", ["linkedin"]]]) {
    for (const p of plats) {
      const lim = limitOf(stream, p);
      const out = fitFor(cap, p, stream);
      const parts = lim.parts ? threadParts(out) : [out];
      assert.ok(parts.length <= (lim.parts || 1), p);
      assert.ok(parts.every((x) => x.length <= lim.max), p);
      assert.ok(out.startsWith(HOOK) && out.endsWith("#kosmetik"), p);
      const lg = stream === "linkedin" ? "en" : "bm";
      const flags = scan({ stream, lang: lg, text: { [lg]: { [p]: out } }, channels: [p] }, {}, {}).filter((f) => /limit/.test(f.msg));
      assert.equal(hardCount(flags), 0, p);
    }
  }
});

ok("whole paragraphs come out, never half a sentence", () => {
  const cap = long(12);
  const out = fitFor(cap, "instagram", "regulab");
  assert.ok(out.length <= 2200 && out.split("\n\n").every((p) => cap.includes(p)) && out.includes(FOLLOW));
});

ok("emoji count as the platforms count them", () => {
  assert.ok(fitFor("🔥".repeat(1500), "instagram", "regulab").length <= 2200);
});

ok("a long thread becomes a chain of at most 5 posts of 500 with the hook alone on the first", () => {
  const out = fitFor(long(10), "threads", "regulab");
  const parts = threadParts(out);
  assert.ok(parts.length > 1 && parts.length <= 5 && parts.every((x) => x.length <= 500));
  assert.equal(parts[0], HOOK);
  assert.ok(!/^(?:\s*#[^\s#]+)+\s*$/.test(parts[parts.length - 1]), "tags never stand alone");
});

ok("a channel a platform already holds is kept, and overLimit names the rest", () => {
  const cap = long(20);
  const text = { bm: { instagram: cap, facebook: HOOK, threads: cap } };
  const out = fitText(text, "regulab", ["instagram"]);
  assert.equal(out.bm.instagram, cap);
  assert.notEqual(out.bm.threads, cap);
  assert.deepEqual(overLimit(text.bm, "regulab").sort(), ["instagram", "threads"]);
});

ok("a Motion film's captions are fitted before they are queued", () => {
  const film = { id: "f1", stream: "regulab", language: "bm", title: "T" };
  const args = queueArgs({ film, channels: ["instagram", "threads"], captions: { instagram: long(20), threads: long(20) },
    date: "2026-12-01", slot: "08:00", brand: {}, post: null });
  assert.ok(args.p_text.bm.instagram.length <= 2200);
  assert.ok(threadParts(args.p_text.bm.threads).every((x) => x.length <= 500));
});

console.log(`captionFit: ${n} passed`);
