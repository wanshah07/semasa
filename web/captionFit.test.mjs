// Every caption inside its platform's limit (Wan, 22 Nov 2026), the page's twin of backend/tests/test_caption_fit.py.
import assert from "node:assert/strict";
import { copyFileSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { glossarySource } from "./glossaryInline.mjs";

// Node needs an import attribute for JSON that Vite does not: compliance.js is copied with its rules inlined
const here = new URL(".", import.meta.url);
const dir = mkdtempSync(join(tmpdir(), "cf-"));
writeFileSync(join(dir, "compliance.js"), readFileSync(new URL("src/lib/compliance.js", here), "utf8")
  .replace(/^import RULES from .*$/m, `const RULES = ${readFileSync(new URL("../rules/compliance.json", here), "utf8")};`));
writeFileSync(join(dir, "glossary.js"), glossarySource());
for (const f of ["slots.js", "platformFormat.js", "motionQueue.js", "captionFit.js"]) copyFileSync(new URL(`src/lib/${f}`, here), join(dir, f));
const at = (f) => import(pathToFileURL(join(dir, f)).href);
const { fitCaption: fitCaptionTight, fitFor, fitText, limitOf, overLimit } = await at("captionFit.js");
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

// the Definisi paragraph (Wan, 22 Nov 2026) is part of the protected tail, as in backend/tests/test_facts_first.py
const DEF = "Definisi: PIF = Fail maklumat dan bukti keselamatan produk kosmetik; NPRA = Agensi di bawah KKM.";
const withDef = (c) => c.replace(`\n\n${FOLLOW}`, `\n\n${DEF}\n\n${FOLLOW}`);

ok("trimming a caption keeps the Definisi paragraph with the follow line and the tags", () => {
  const out = fitFor(withDef(long(30)), "instagram", "regulab");
  assert.ok(out.length <= 2200 && out.startsWith(HOOK));
  assert.ok(out.endsWith(`${DEF}\n\n${FOLLOW}\n\n${TAGS}`), "the tail survives whole, in order");
  const small = `${HOOK}\n\n${DEF}\n\n${FOLLOW}\n\n${TAGS}`;
  const tight = fitCaptionTight(withDef(long(30)), small.length + 5);
  assert.ok(tight.includes("Definisi:") && tight.endsWith(TAGS) && !tight.includes("1. Fakta"), "so tight that the body goes first and the definitions stay");
  assert.equal(fitFor(`Pendek.\n\n${DEF}`, "instagram", "regulab"), `Pendek.\n\n${DEF}`);
  assert.ok(fitFor(withDef(long(30)).replace("Definisi:", "Definition:"), "linkedin", "linkedin").includes("Definition: PIF"));
});

ok("a Threads chain carries the definitions on its last post", () => {
  const body = ["Hook thread.\n\nApa yang ada.\n\nPerinciannya di bawah.",
    ...Array.from({ length: 6 }, (_, i) => `Label ${i + 1}:\n\n` + Array.from({ length: 5 }, (_, j) => `${j + 1}. Satu perkara penting nombor ${j + 1} dalam thread.`).join("\n"))];
  const cap = `${body.join("\n\n---\n\n")}\n\nDefinisi: PIF = Fail maklumat produk.\n\n${FOLLOW}\n\n#npra`;
  const parts = threadParts(fitFor(cap, "threads", "regulab"));
  assert.ok(parts.length <= 5 && parts.every((x) => x.length <= 500));
  assert.ok(parts[parts.length - 1].includes("Definisi: PIF = Fail maklumat produk.") && parts[parts.length - 1].endsWith("#npra"));
});

console.log(`captionFit: ${n} passed`);
