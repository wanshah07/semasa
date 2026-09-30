/* web/src/lib/ownSources.js: what a card for Wan's own sources (Reddit, YouTube, OneDrive, MYRA) may open and say. */
import assert from "node:assert/strict";
import { OWN_SECTIONS, linkOf, ownLine, ownSummary } from "./src/lib/ownSources.js";

const t = (bm, en, vars = {}) => Object.entries(vars).reduce((s, [k, v]) => s.replace(`{${k}}`, v), bm);
let n = 0;
const test = (name, fn) => { fn(); n++; };

test("four own sections, none of them the news ones", () => {
  assert.deepEqual(OWN_SECTIONS, ["reddit", "youtube", "folder", "myra"]);
});
test("a card opens a web address only: a OneDrive key or a link-less MYRA finding opens nothing", () => {
  assert.equal(linkOf({ url: "https://www.reddit.com/r/malaysia/comments/a1/x" }), "https://www.reddit.com/r/malaysia/comments/a1/x");
  assert.equal(linkOf({ url: "onedrive://f1#2", raw: { web_url: "https://my.microsoftpersonalcontent.com/x" } }), "https://my.microsoftpersonalcontent.com/x");
  assert.equal(linkOf({ url: "onedrive://f1#2", raw: {} }), null);
  assert.equal(linkOf({ url: "myra://2026-09-28-1", raw: { link: null } }), null);
  assert.equal(linkOf({ url: "myra://2026-09-28-1", raw: { link: "https://ec.europa.eu/a" } }), "https://ec.europa.eu/a");
});
test("the line under a card says only what the source returned", () => {
  assert.equal(ownLine({ section: "reddit", raw: { metrics: "260 komen" } }, t), "260 komen");
  assert.equal(ownLine({ section: "youtube", raw: {} }, t), "");
  assert.equal(ownLine({ section: "folder", raw: { cite: "hlm 12", urgent_for: "2026-10-01" } }, t), "Segera untuk 2026-10-01 · Rujukan: hlm 12");
  assert.match(ownLine({ section: "myra", raw: { ref_no: "SR/1", markets: "EU", link_shared: true } }, t), /Rujukan: SR\/1 · EU · pautan dikongsi/);
  assert.equal(ownLine({ section: "regulatory", raw: {} }, t), "");
});
test("the header reads the last run per tab and names a YouTube quota answer", () => {
  const s = { last_run: "2026-09-30T01:00:00Z", report: {
    community: { ok: true, shown: { reddit: 3, youtube: 0 }, youtube_error: "quota", reddit_error: null },
    folders: { ok: true, angles: 8 }, myra: { ok: false, error: "the sheet could not be read" } } };
  assert.equal(ownSummary("reddit", s).new, 3);
  assert.deepEqual(ownSummary("reddit", s).failing, []);
  assert.equal(ownSummary("youtube", s).failing.length, 1);
  assert.match(ownSummary("youtube", s).failing[0].error, /kuota/);
  assert.equal(ownSummary("folder", s).new, 8);
  assert.equal(ownSummary("myra", s).failing[0].error, "the sheet could not be read");
  assert.equal(ownSummary("myra", undefined).new, 0);
});
console.log(`${n}/${n} own-source tests pass`);
