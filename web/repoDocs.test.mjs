/* Rujukan → Dokumen (src/lib/repoDocs.js, src/lib/repoDocsFiles.js, vite.repoDocs.js): which .md files the page shows, how they are
   grouped, searched and outlined. Run against the repo's real files, so a new folder of documents that the glob misses fails here
   instead of quietly never appearing. `npm test`. */
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { parseMarkdown } from "./src/lib/markdown.js";
import { MAX_BYTES, docTitle, groupDocs, groupOf, isWanted, listDocs, outlineOf, repoPath, searchDocs, snippetOf } from "./src/lib/repoDocs.js";
import { buildMeta, parseGitLog, walkMarkdown } from "./vite.repoDocs.js";

let n = 0;
const t = (name, fn) => { try { fn(); n++; } catch (e) { console.error("FAIL:", name); throw e; } };
const ROOT = fileURLToPath(new URL("..", import.meta.url));

t("installed packages, build output and backup/ are never documents, whatever their names", () => {
  for (const p of ["web/node_modules/react/README.md", "web/dist/x.md", "backup/studio-store-2026-10-11.md", "a/.venv/lib/README.md", ".git/x.md"]) {
    assert.equal(isWanted(p), false, p);
  }
  assert.equal(isWanted("backups/plan.md"), true, "a folder that only looks like backup/ is kept");
  assert.equal(isWanted("ops/API.txt"), false, "Markdown only");
});
t("a file over 400 KB is left out; one whose size is unknown is kept", () => {
  assert.equal(isWanted("ops/BIG.md", MAX_BYTES + 1), false);
  assert.equal(isWanted("ops/BIG.md", MAX_BYTES), true);
  assert.equal(isWanted("ops/BIG.md", null), true);
});
t("glob keys become repo paths", () => {
  assert.equal(repoPath("../../../ops/API.md"), "ops/API.md");
  assert.equal(repoPath("../../../.claude/skills/antislop/SKILL.md"), ".claude/skills/antislop/SKILL.md");
  assert.equal(repoPath("./README.md"), "README.md");
});
t("folders: two segments deep, so every skill shares one heading and every function README another", () => {
  assert.equal(groupOf("CLAUDE.md"), "");
  assert.equal(groupOf("ops/API.md"), "ops");
  assert.equal(groupOf(".claude/skills/antislop-ui/SKILL.md"), ".claude/skills");
  assert.equal(groupOf("supabase/functions/semasa-chat/README.md"), "supabase/functions");
  assert.equal(groupOf("docs/motion/native-effects-roadmap/checklist.md"), "docs/motion");
});
t("SKILL.md and README.md are named after their folder; anything else after the file", () => {
  assert.equal(docTitle(".claude/skills/hook-bank/SKILL.md"), "hook-bank");
  assert.equal(docTitle("supabase/functions/semasa-chat/README.md"), "semasa-chat");
  assert.equal(docTitle("README.md"), "README");
  assert.equal(docTitle("ops/HOOK-LEARNING.md"), "HOOK-LEARNING");
});
t("groups come root first, then rules, ops, docs and skills; a group's own README leads it", () => {
  const docs = listDocs(["../../../ops/B.md", "../../../README.md", "../../../zeta/x.md", "../../../ops/A.md", "../../../CLAUDE.md",
    "../../../rules/motion/designs/README.md", "../../../rules/motion/designs/v16-README.md", "../../../.claude/skills/a/SKILL.md", "../../../README.md"]);
  const g = groupDocs(docs);
  assert.deepEqual(g.map((x) => x.group), ["", "rules/motion", "ops", ".claude/skills", "zeta"]);
  assert.deepEqual(g[0].docs.map((d) => d.path), ["CLAUDE.md", "README.md"], "the same file twice is listed once");
  assert.deepEqual(g[2].docs.map((d) => d.title), ["A", "B"]);
});
t("listDocs takes the size and the date from the plugin and drops what the plugin says is too big", () => {
  const meta = { "ops/A.md": { size: 1200, changed: "2026-11-01T10:00:00+08:00" }, "ops/BIG.md": { size: MAX_BYTES + 5, changed: "" } };
  const out = listDocs(["../../../ops/A.md", "../../../ops/BIG.md"], meta);
  assert.deepEqual(out.map((d) => [d.path, d.size, d.changed]), [["ops/A.md", 1200, "2026-11-01T10:00:00+08:00"]]);
});

const DOCS = [
  { path: "CLAUDE.md", title: "CLAUDE" }, { path: "ops/HOOK-LEARNING.md", title: "HOOK-LEARNING" }, { path: "ops/API.md", title: "API" },
];
t("an empty search shows everything; words must all match, in the name, the path or the text", () => {
  assert.equal(searchDocs(DOCS, "  ").length, 3);
  assert.deepEqual(searchDocs(DOCS, "hook").map((d) => d.path), ["ops/HOOK-LEARNING.md"]);
  assert.deepEqual(searchDocs(DOCS, "ops api").map((d) => d.path), ["ops/API.md"]);
  const texts = { "CLAUDE.md": "Bank hook dan hook learning.", "ops/API.md": "gateway" };
  const found = searchDocs(DOCS, "hook", texts);
  assert.deepEqual(found.map((d) => d.path), ["ops/HOOK-LEARNING.md", "CLAUDE.md"], "a name match ranks above a text-only match");
  assert.equal(found[1].hits, 2);
  assert.ok(found[1].snippet.includes("Bank hook"));
  assert.deepEqual(searchDocs(DOCS, "hook gateway", texts), [], "every word has to be there");
});
t("search ignores case and accents, and the snippet is one short line", () => {
  const found = searchDocs([{ path: "x.md", title: "x" }], "CAFÉ", { "x.md": "a\n\nlong line about cafe " + "z".repeat(400) });
  assert.equal(found.length, 1);
  assert.ok(!found[0].snippet.includes("\n") && found[0].snippet.length <= 142);
  assert.equal(snippetOf("abc", ["zzz"]), "");
});
t("the outline lists every heading with a unique anchor, and the anchors cannot carry markup", () => {
  const tree = parseMarkdown("# Tajuk\n\n## Bahagian **satu**\n\ntext\n\n## Bahagian satu\n\n### <img src=x onerror=alert(1)>\n\n> # not top level");
  const o = outlineOf(tree);
  assert.deepEqual(o.map((x) => x.level), [1, 2, 2, 3]);
  assert.deepEqual(o.map((x) => x.id), ["doc-tajuk", "doc-bahagian-satu", "doc-bahagian-satu-2", "doc-img-srcx-onerroralert1"]);
  assert.equal(o[1].text, "Bahagian satu");
  assert.ok(o.every((x) => /^doc-[\p{L}\p{N}-]+$/u.test(x.id)));
});

t("the renderer is the chat's: no HTML passes through, and only http(s)/mailto links become links", () => {
  const tree = parseMarkdown("<script>alert(1)</script>\n\n[x](javascript:alert(1)) [y](https://npra.gov.my)");
  const s = JSON.stringify(tree);
  assert.ok(!s.includes('"t":"html"'));
  assert.ok(s.includes("<script>alert(1)</script>"), "a tag is kept as text, drawn as text by React");
  assert.ok(!s.includes("javascript:"), "an unsafe link keeps only its words");
  assert.ok(/"href":"https:\/\/npra.gov.my"/.test(s));
  const page = readFileSync(new URL("./src/pages/DocsTab.jsx", import.meta.url), "utf8");
  assert.ok(!page.includes("dangerouslySetInnerHTML") && page.includes("<Markdown "));
});

t("git log: the newest commit naming a file is its last change", () => {
  const log = "@2026-11-07T10:00:00+08:00\nops/API.md\nCLAUDE.md\n\n@2026-11-01T09:00:00+08:00\nops/API.md\nREADME.md\n";
  assert.deepEqual(parseGitLog(log), { "ops/API.md": "2026-11-07T10:00:00+08:00", "CLAUDE.md": "2026-11-07T10:00:00+08:00", "README.md": "2026-11-01T09:00:00+08:00" });
  assert.deepEqual(parseGitLog(""), {});
});
t("the plugin's list skips node_modules and keeps sizes; with no git it still lists the files, undated", () => {
  const files = walkMarkdown(ROOT);
  assert.ok(files.includes("CLAUDE.md") && files.includes("README.md"));
  assert.ok(!files.some((f) => f.includes("node_modules/")));
  const meta = buildMeta(ROOT, "");
  assert.ok(meta["CLAUDE.md"].size > 1000 && meta["CLAUDE.md"].changed === "");
});

/* Every document isWanted() accepts must be reached by one of the glob patterns in repoDocsFiles.js, or it would never be bundled. */
const src = readFileSync(new URL("./src/lib/repoDocsFiles.js", import.meta.url), "utf8");
const patterns = [...src.matchAll(/^\s*"(!?\.\.\/[^"]*|!\*\*[^"]*)",?$/gm)].map((m) => m[1]);
const toRe = (glob) => new RegExp("^" + glob.replace(/^(\.\.\/)+/, "").replace(/^!/, "").replace(/[.+^${}()|[\]\\]/g, "\\$&")
  .replace(/\*\*\//g, "§").replace(/\*\*/g, "¤").replace(/\*/g, "[^/]*").replace(/§/g, "(?:.*/)?").replace(/¤/g, ".*") + "$");
const yes = patterns.filter((p) => !p.startsWith("!")).map(toRe);
const no = patterns.filter((p) => p.startsWith("!")).map(toRe);
const reached = (p) => yes.some((r) => r.test(p)) && !no.some((r) => r.test(p));

t("the glob reaches every document the repo has, and backup/ is refused by both the glob and the rules", () => {
  let tracked = [];
  try { tracked = execFileSync("git", ["-C", ROOT, "ls-files", "*.md"], { encoding: "utf8" }).split("\n").filter(Boolean); } catch { tracked = walkMarkdown(ROOT); }
  const wanted = tracked.filter((p) => isWanted(p));
  assert.ok(wanted.length >= 40, `only ${wanted.length} documents found`);
  assert.deepEqual(wanted.filter((p) => !reached(p)), []);
  for (const must of ["CLAUDE.md", "README.md", "supabase/functions/semasa-chat/README.md", ".claude/skills/hook-bank/SKILL.md", "ops/API.md", "docs/motion/effect-library.md", "rules/motion/designs/README.md"]) {
    assert.ok(wanted.includes(must) && reached(must), must);
  }
  assert.equal(reached("backup/studio-store.md"), false);
  assert.equal(reached("web/node_modules/x/README.md"), false);
});
t("pages.yml rebuilds the site when any .md file changes, with the history the dates need", () => {
  const yml = readFileSync(new URL("../.github/workflows/pages.yml", import.meta.url), "utf8");
  assert.match(yml, /paths:[^\n]*"\*\*\/\*\.md"/);
  assert.match(yml, /fetch-depth: 0/);
});

console.log(`repoDocs: ${n} checks passed`);
