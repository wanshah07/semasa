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
  assert.deepEqual(["isu", "idea", "post"].map(where), ["content", "content", "content"]);
  assert.equal(where("prestasi"), "performance");
  assert.deepEqual(["media", "media-lib"].map(where), ["image", "image"]);
  assert.deepEqual(["video", "video-lib", "motion-skills"].map(where), ["video", "video", "video"]);
  assert.deepEqual(["design", "design-lib"].map(where), ["poster", "poster"]);
  assert.deepEqual(["wangian", "bil-valorith"].map(where), ["valorith", "valorith"]);
  assert.deepEqual(["wang", "bil", "crm", "syarikat"].map(where), ["business", "business", "business", "business"]);
  assert.deepEqual(["tech", "office", "repo", "api"].map(where), ["technology", "technology", "technology", "technology"]);
  assert.deepEqual(["resit", "langganan"].map(where), ["personal", "personal"]);
  assert.equal(where("tetapan"), undefined);
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

console.log(`tabs.test.mjs: ${n} groups OK`);
