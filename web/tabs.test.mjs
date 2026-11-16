/* Every tab in the menu must have a page behind it. App.jsx picks a tab's body with an if/else chain whose last `else` is the
   Current issues page, so a tab with no branch does not fail: it quietly shows Current issues. That is how Resit showed the
   wrong page. Reads the source, so it needs no browser. `npm test`. */
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { segmentOf, segmentsOf, tabsOf } from "./src/lib/tabs.js";

let n = 0;
const t = (name, fn) => { try { fn(); n++; } catch (e) { console.error("FAIL:", name); throw e; } };
const src = readFileSync(new URL("./src/App.jsx", import.meta.url), "utf8");
const ids = JSON.parse(`[${/const TAB_IDS = \[([^\]]*)\]/.exec(src)[1]}]`);
const menu = tabsOf((bm) => bm).map((x) => x.id);

t("the menu and the route list name the same tabs", () => {
  assert.deepEqual([...menu].sort(), [...ids].sort());
});
t("every tab except the default (isu) has its own branch, so none falls through to Current issues", () => {
  const missing = ids.filter((id) => id !== "isu" && !src.includes(`tab === "${id}"`));
  assert.deepEqual(missing, []);
});
t("every page component that is imported is used", () => {
  // a page is imported with the first chunk, or lazily (loaded when its tab is first shown); both count
  const pages = [...src.matchAll(/^(?:import (\w+Tab) from "|const (\w+Tab) = lazy\(\(\) => import\(")\.\/pages\//gm)].map((m) => m[1] || m[2]);
  assert.ok(pages.length > 10);
  assert.deepEqual(pages.filter((p) => !src.includes(`<${p} `) && !src.includes(`<${p}\n`)), []);
});

t("every page except Settings sits in exactly one segment, and every segment page exists", () => {
  const segs = segmentsOf((bm) => bm);
  const inSeg = segs.flatMap((s) => s.pages.map((p) => p.id));
  assert.equal(new Set(inSeg).size, inSeg.length, "a page is in two segments");
  assert.deepEqual([...inSeg].sort(), menu.filter((id) => id !== "tetapan").sort());
  assert.ok(segs.every((s) => s.pages.length > 0), "an empty segment would be a dead sidebar row");
});
t("Wan's layout of 11 Oct 2026: which pages sit together", () => {
  const where = (id) => segmentOf((bm) => bm, id)?.id;
  assert.deepEqual(["papan", "chat", "otak"].map(where), ["dashboard", "dashboard", "dashboard"]);
  assert.deepEqual(["isu", "idea", "post", "hooks", "gaya"].map(where), ["content", "content", "content", "content", "content"]);
  assert.deepEqual(["li-idea", "li-post", "li-sumber"].map(where), ["linkedin", "linkedin", "linkedin"]);
  assert.equal(where("prestasi"), "performance");
  assert.equal(where("pakar"), "expert", "Expert content is its own segment (Wan, 14 Nov 2026); its categories are sub-tabs inside the page");
  assert.deepEqual(["media", "media-lib"].map(where), ["image", "image"]);
  assert.deepEqual(["video", "video-lib", "motion-skills"].map(where), ["video", "video", "video"]);
  assert.deepEqual(["design", "design-lib"].map(where), ["poster", "poster"]);
  assert.deepEqual(["wangian", "bil-valorith"].map(where), ["valorith", "valorith"]);
  assert.deepEqual(["wang", "bil", "crm", "syarikat"].map(where), ["business", "business", "business", "business"]);
  assert.deepEqual(["tech", "office", "repo", "api", "stack"].map(where), ["technology", "technology", "technology", "technology", "technology"]);
  assert.deepEqual(["resit", "langganan"].map(where), ["personal", "personal"]);
  assert.equal(where("tetapan"), undefined);
});
t("LinkedIn is its own segment, right after Content, with its own idea and post pages (Wan, 16 Nov 2026)", () => {
  const segs = segmentsOf((bm) => bm);
  const at = segs.findIndex((x) => x.id === "linkedin");
  assert.equal(segs[at - 1].id, "content", "it sits under Content in the sidebar");
  assert.deepEqual(segs[at].pages.map((p) => p.id), ["li-idea", "li-post", "li-sumber"]);
  assert.deepEqual(segmentsOf((bm, en) => en)[at].pages.map((p) => p.label), ["LinkedIn ideas", "LinkedIn posts", "LinkedIn sources"]);
  // the pages are the idea and post pages again, each fixed to one stream, with their own state
  assert.match(src, /<IdeasTab key=\{tab\} stream=\{tab === "li-idea" \? "linkedin" : "regulab"\}/);
  assert.match(src, /<PostsTab key=\{tab\} stream=\{tab === "li-post" \? "linkedin" : "regulab"\}/);
  assert.match(src, /go\(tab === "li-idea" \? "li-post" : "post"\)/, "a LinkedIn idea opens its draft on the LinkedIn post page");
  // the badges are one stream each: a LinkedIn draft never adds to Bank post's number
  assert.match(src, /post: posts\.rows\.filter\(\(r\) => r\.status === "draft" && !isLi\(r\)\)\.length/);
  assert.match(src, /"li-post": posts\.rows\.filter\(\(r\) => r\.status === "draft" && isLi\(r\)\)\.length/);
  assert.match(src, /idea: ideas\.rows\.filter\(\(r\) => r\.status === "new" && !isLi\(r\)\)\.length/);
  assert.match(src, /"li-idea": ideas\.rows\.filter\(\(r\) => r\.status === "new" && isLi\(r\)\)\.length/);
  assert.match(src, /postTabOf = \(id\) => \(posts\.rows\.find\(\(p\) => p\.id === id\)\?\.stream === "linkedin" \? "li-post" : "post"\)/);
});
t("a page fixed to a stream reads that stream's rows only, everywhere on the page, and offers no stream to choose", () => {
  const posts = readFileSync(new URL("./src/pages/PostsTab.jsx", import.meta.url), "utf8");
  const ideas = readFileSync(new URL("./src/pages/IdeasTab.jsx", import.meta.url), "utf8");
  assert.match(posts, /const rows = useMemo\(\(\) => \(stream \? posts\.rows\.filter\(\(p\) => \(p\.stream \|\| "regulab"\) === stream\) : posts\.rows\)/);
  assert.match(ideas, /const rows = useMemo\(\(\) => \(stream \? ideas\.rows\.filter\(\(r\) => \(r\.stream \|\| "regulab"\) === stream\) : ideas\.rows\)/);
  // the counts, the list, the Schedule and the slot check all start from `rows`, never from the whole table
  assert.match(posts, /for \(const p of rows\) c\[bucketOf\(p\)\]/);
  assert.match(posts, /const shown = rows\.filter/);
  assert.match(posts, /<ScheduleView posts=\{rows\}[\s\S]{0,160}lockStream=\{stream\}/);
  assert.match(posts, /<SlotCheck posts=\{rows\}[\s\S]{0,160}lockStream=\{stream\}/);
  assert.match(ideas, /const shown = rows\.filter/);
  assert.match(ideas, /const count = \(k\) => rows\.filter/);
  for (const f of [posts, ideas]) assert.match(f, /\{!stream && \(\s*<select value=\{streamF\}/, "the stream chooser is hidden on a fixed page");
  // the editor still gets every post: a slot clash is checked against the whole table
  assert.match(posts, /<PostEditor post=\{p\} posts=\{posts\.rows\}/);
  assert.match(readFileSync(new URL("./src/components/ScheduleMap.jsx", import.meta.url), "utf8"), /only !== "linkedin" && lane\("regulab"\)[\s\S]*only !== "regulab" && lane\("linkedin"\)/);
  assert.match(readFileSync(new URL("./src/components/IdeaComposer.jsx", import.meta.url), "utf8"), /trend\.stream \|\| "regulab" : defaultStream\)/, "a new idea starts on the page's stream");
});
t("Kanvas is gone from the menu, the routes and the app", () => {
  assert.ok(!menu.includes("kanvas") && !ids.includes("kanvas"));
  assert.ok(!/CanvasTab|canvasSeed|kanvas"/.test(src));
});
t("Office repos and Repo library are two pages", () => {
  assert.ok(menu.includes("office") && menu.includes("repo"));
  const office = readFileSync(new URL("./src/pages/OfficeTab.jsx", import.meta.url), "utf8");
  const repo = readFileSync(new URL("./src/pages/RepoTab.jsx", import.meta.url), "utf8");
  assert.ok(!office.includes("RepoLibrary") && repo.includes("RepoLibrary") && !repo.includes("officeSummary"));
});

t("Create phase 2 (11 Oct 2026): the three libraries are compact tiles, 8 across, and the motion skills are one page", () => {
  const tile = readFileSync(new URL("./src/components/TileGrid.jsx", import.meta.url), "utf8");
  assert.match(tile, /TILES_PER_ROW = "[^"]*xl:grid-cols-8"/);
  for (const f of ["ImageLibraryTab", "VideoLibraryTab"]) assert.ok(readFileSync(new URL(`./src/pages/${f}.jsx`, import.meta.url), "utf8").includes("<TileGrid"), f);
  assert.ok(readFileSync(new URL("./src/pages/DesignTab.jsx", import.meta.url), "utf8").includes("<TileGrid"));
  assert.ok(readFileSync(new URL("./src/components/MotionLab.jsx", import.meta.url), "utf8").includes("<TileGrid"));
  const skills = readFileSync(new URL("./src/pages/MotionSkillsTab.jsx", import.meta.url), "utf8");
  assert.ok(skills.includes("<MotionSkill ") && skills.includes('view="skills"'));
  assert.ok(!readFileSync(new URL("./src/pages/SettingsTab.jsx", import.meta.url), "utf8").includes("MotionPrompt"), "the skill box lives in one place");
});
t("image and video generation are apart: each page fixes its own kind", () => {
  assert.ok(src.includes('only="image"'));
  assert.ok(readFileSync(new URL("./src/pages/VideoTab.jsx", import.meta.url), "utf8").includes('only="video"'));
});

t("no page spreads a variants object onto an element: {...fadeUp} passes hidden={…} and the browser hides the header", () => {
  const dir = new URL("./src/pages/", import.meta.url);
  const bad = readdirSync(dir).filter((f) => readFileSync(new URL(f, dir), "utf8").includes("{...fadeUp}"));
  assert.deepEqual(bad, []);
});

t("every Isu semasa segment has a button in the sub-tab row (Threads had a page, copy and data and no button, 13 Nov 2026)", () => {
  const segments = JSON.parse(`[${/const SEGMENTS = \[([^\]]*)\]/.exec(src)[1]}]`);
  const row = /const segTabs = \([\s\S]*?\.map\(/.exec(src)[0];
  const missing = segments.filter((id) => !row.includes(`["${id}",`));
  assert.deepEqual(missing, []);
});

console.log(`tabs.test.mjs: ${n} groups OK`);
