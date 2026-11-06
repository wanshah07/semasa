/* The theme follows the device until someone picks one (Wan, 6 Nov 2026: "follow the phone setting"). Checks the rule in
   src/design/themeChoice.js, and runs the inline script from index.html against the same cases so the first paint and
   the app cannot disagree. No browser. `npm test`. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import { AUTO, OLD_KEY, PICK_KEY, readPick, resolveTheme, writePick } from "./src/design/themeChoice.js";

let n = 0;
const t = (name, fn) => { try { fn(); n++; } catch (e) { console.error("FAIL:", name); throw e; } };
const mem = (init = {}) => {
  const m = new Map(Object.entries(init));
  return { m, getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), removeItem: (k) => m.delete(k) };
};

t("no pick follows the device", () => {
  assert.equal(resolveTheme(AUTO, true), "noir");
  assert.equal(resolveTheme(AUTO, false), "facerinna");
  assert.equal(resolveTheme("junk", true), "noir");
});
t("a pick beats the device, Regulab included", () => {
  assert.equal(resolveTheme("facerinna", true), "facerinna");
  assert.equal(resolveTheme("noir", false), "noir");
  assert.equal(resolveTheme("regulab", true), "regulab");
});
t("a fresh profile reads as no pick", () => assert.equal(readPick(mem()), AUTO));
t("the old key's facerinna was written on every visit, so it is no pick, and the old key goes", () => {
  const s = mem({ [OLD_KEY]: "facerinna" });
  assert.equal(readPick(s), AUTO);
  assert.equal(s.m.has(OLD_KEY), false);
});
t("the old key's noir or regulab was a real choice and carries over", () => {
  for (const v of ["noir", "regulab"]) {
    const s = mem({ [OLD_KEY]: v });
    assert.equal(readPick(s), v);
    assert.equal(s.getItem(PICK_KEY), v);
    assert.equal(s.m.has(OLD_KEY), false);
  }
});
t("writing a pick keeps it; writing auto clears it", () => {
  const s = mem();
  writePick(s, "regulab");
  assert.equal(readPick(s), "regulab");
  writePick(s, AUTO);
  assert.equal(s.m.has(PICK_KEY), false);
  assert.equal(readPick(s), AUTO);
});
t("storage that throws follows the device", () => {
  const bad = { getItem() { throw new Error("blocked"); }, setItem() { throw new Error("blocked"); }, removeItem() { throw new Error("blocked"); } };
  assert.equal(readPick(bad), AUTO);
  writePick(bad, "noir");
});

const html = readFileSync(new URL("./index.html", import.meta.url), "utf8");
const inline = /<script>([\s\S]*?)<\/script>/.exec(html)[1];
const firstPaint = (store, dark, throwStore = false) => {
  let attr = null;
  const ls = throwStore ? { getItem() { throw new Error("blocked"); } } : store;
  const ctx = {
    localStorage: ls,
    window: { matchMedia: (q) => ({ matches: q === "(prefers-color-scheme: dark)" && dark }) },
    document: { documentElement: { setAttribute: (k, v) => { if (k === "data-theme") attr = v; } } },
  };
  vm.runInNewContext(inline, ctx);
  return attr;
};
t("the inline script gives the same answer as the app for every stored state and device setting", () => {
  const states = [{}, { [OLD_KEY]: "facerinna" }, { [OLD_KEY]: "noir" }, { [OLD_KEY]: "regulab" },
    { [PICK_KEY]: "facerinna" }, { [PICK_KEY]: "noir" }, { [PICK_KEY]: "regulab" }, { [PICK_KEY]: "junk" }];
  for (const init of states) for (const dark of [true, false]) {
    const want = resolveTheme(readPick(mem(init)), dark);
    assert.equal(firstPaint(mem(init), dark), want, `${JSON.stringify(init)} dark=${dark}`);
  }
});
t("the inline script still follows the device when storage is blocked", () => {
  assert.equal(firstPaint(null, true, true), "noir");
  assert.equal(firstPaint(null, false, true), "facerinna");
});

console.log(`theme.test.mjs: ${n} groups OK`);
