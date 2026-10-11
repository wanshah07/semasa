/* Every tab in the menu must have a page behind it. App.jsx picks a tab's body with an if/else chain whose last `else` is the
   Current issues page, so a tab with no branch does not fail: it quietly shows Current issues. That is how Resit showed the
   wrong page. Reads the source, so it needs no browser. `npm test`. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { tabsOf } from "./src/lib/tabs.js";

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
  const pages = [...src.matchAll(/^import (\w+Tab) from "\.\/pages\//gm)].map((m) => m[1]);
  assert.ok(pages.length > 10);
  assert.deepEqual(pages.filter((p) => !src.includes(`<${p} `) && !src.includes(`<${p}\n`)), []);
});

console.log(`tabs.test.mjs: ${n} groups OK`);
