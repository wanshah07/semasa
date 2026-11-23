/* API credit as the page reads it (lib/credit.js, pages/CreditTab.jsx, the Baki kredit API segment). The status rules must stay the
   same as backend/semasa/api_credit.py status_of. `npm test`. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { CARDS, amountOf, compact, countdownOf, countdownText, isoToMytInput, manualEntry, mytInputToIso, mytText, parseAmount, pct, statusOf, viewOf } from "./src/lib/credit.js";

let n = 0;
const t = (name, fn) => { try { fn(); n++; } catch (e) { console.error("FAIL:", name); throw e; } };
const NOW = Date.parse("2026-11-23T15:31:50Z");                       // 23 Nov 2026, 23:31:50 MYT
const en = (bm, e) => e;
const bm = (b) => b;
const MIRELD = { remaining: 89.113109, total: 1275, used: 1185.886891, percent_left: 7, unit: "credit", display_scale: 1000000,
  expires_at: "2026-12-09T15:31:50Z", source: "/dashboard/billing/credit_grants", status: "low", checked_at: "2026-11-23T15:30:00Z" };

t("the three cards are Wan's three gateways, by the slugs the probe writes", () => {
  assert.deepEqual(CARDS.map((c) => c.slug), ["mireld", "rootsys", "kiosapi"]);
});

t("status: the same thresholds as the backend", () => {
  const day = 86400_000;
  assert.equal(statusOf({ remaining: 50, percent_left: 50 }, NOW), "ok");
  assert.equal(statusOf({ remaining: 15, percent_left: 15 }, NOW), "ok");
  assert.equal(statusOf({ remaining: 14.9, percent_left: 14.9 }, NOW), "low");
  assert.equal(statusOf({ remaining: 0, percent_left: 0 }, NOW), "low");
  assert.equal(statusOf({ remaining: 50, percent_left: 50, expires_at: new Date(NOW + 6.9 * day).toISOString() }, NOW), "low");
  assert.equal(statusOf({ remaining: 50, percent_left: 50, expires_at: new Date(NOW + 7.1 * day).toISOString() }, NOW), "ok");
  assert.equal(statusOf({ remaining: 50, percent_left: 50, expires_at: new Date(NOW - 1000).toISOString() }, NOW), "expired");
  assert.equal(statusOf({ remaining: null, expires_at: null }, NOW), "unknown");
  assert.equal(statusOf(null, NOW), "unknown");
  assert.equal(statusOf({ remaining: null, expires_at: new Date(NOW + 30 * day).toISOString() }, NOW), "ok");
  assert.equal(statusOf({ remaining: null, unlimited: true }, NOW), "ok");
  assert.equal(statusOf(MIRELD, NOW), "low");
  assert.equal(statusOf(MIRELD, Date.parse("2026-12-09T15:31:51Z")), "expired", "a stored reading ages into expired by itself");
});

t("countdown: days and hours, as Wan's dashboard counts (16d 0h left on 23 Nov 23:31 for 9 Dec 23:31)", () => {
  const cd = countdownOf(MIRELD.expires_at, NOW);
  assert.deepEqual(cd, { past: false, days: 16, hours: 0, minutes: 0 });
  assert.equal(countdownText(cd, en), "16d 0h remaining");
  assert.equal(countdownText(cd, bm), "16 hari 0 jam lagi");
  assert.equal(countdownText(countdownOf("2026-11-24T04:43:50Z", NOW), en), "13h 12m remaining");
  assert.equal(countdownText(countdownOf("2026-11-23T15:35:50Z", NOW), en), "4m remaining");
  assert.equal(countdownText(countdownOf("2026-11-21T12:31:50Z", NOW), en), "expired 2d 3h ago");
  assert.equal(countdownText(countdownOf("2026-11-21T12:31:50Z", NOW), bm), "tamat 2 hari 3 jam lalu");
  assert.equal(countdownOf(null, NOW), null);
  assert.equal(countdownOf("nonsense", NOW), null);
  assert.equal(countdownText(null, en), "");
});

t("an instant is shown in Malaysia time, whatever the viewer's zone", () => {
  assert.equal(mytText("2026-12-09T15:31:50Z", "en"), "09 Dec 2026, 23:31 MYT");
  assert.equal(mytText("2026-12-09T15:31:50Z", "bm"), "09 Dis 2026, 23:31 MYT");
  assert.equal(mytText("2026-12-09T20:00:00Z", "en"), "10 Dec 2026, 04:00 MYT", "past midnight there is the next day");
  assert.equal(mytText("", "en"), "");
});

t("figures: Mireld's API number is shown the way its dashboard counts, and the raw number stays visible", () => {
  assert.equal(compact(89113109), "89.11M");
  assert.equal(compact(1275000000), "1.27B", "the dashboard also says 1.27B of plan credits");
  assert.equal(compact(8817), "8817");
  assert.equal(compact(191994), "191,994");
  assert.equal(compact(12.5), "12.5");
  assert.equal(compact(null), "");
  const a = amountOf(89.113109, MIRELD);
  assert.deepEqual([a.text, a.raw, a.scaled], ["89.11M", "89.113109", true]);
  assert.equal(amountOf(1275, MIRELD).text, "1.27B");
  const usd = amountOf(12.5, { unit: "USD", display_scale: null });
  assert.deepEqual([usd.text, usd.scaled], ["12.5 USD", false]);
  assert.equal(amountOf(null, MIRELD).text, "");
});

t("percent left", () => {
  assert.equal(pct(89.113109, 1275), 7);
  assert.equal(pct(545.1, 2575.1), 21.2);
  assert.equal(pct(5, 0), null);
  assert.equal(pct(null, 10), null);
  assert.equal(pct(20, 10), 100);
});

t("a typed amount: K/M/B, thousands marks, and Rupiah's dot", () => {
  assert.equal(parseAmount("545.1M"), 545100000);
  assert.equal(parseAmount("1.27B"), 1270000000);
  assert.equal(parseAmount("88,830,000"), 88830000);
  assert.equal(parseAmount("Rp 8.817", "Rp"), 8817, "in Rupiah a dot is a thousands mark");
  assert.equal(parseAmount("191.994", "IDR"), 191994);
  assert.equal(parseAmount("8,5", "Rp"), 8.5);
  assert.equal(parseAmount("12.50", "USD"), 12.5);
  assert.equal(parseAmount("$12.50", "USD"), 12.5);
  assert.equal(parseAmount("12k"), 12000);
  assert.equal(parseAmount(""), null);
  assert.equal(parseAmount("lots"), null);
  assert.equal(parseAmount("12 credits"), null);
  assert.equal(parseAmount(null), null);
});

t("a date typed as Malaysia time becomes UTC and back", () => {
  assert.equal(mytInputToIso("2026-12-09T23:31"), "2026-12-09T15:31:00Z");
  assert.equal(mytInputToIso("2026-12-09"), "2026-12-08T16:00:00Z");
  assert.equal(mytInputToIso(""), null);
  assert.equal(mytInputToIso("9 Dec"), null);
  assert.equal(isoToMytInput("2026-12-09T15:31:00Z"), "2026-12-09T23:31");
  assert.equal(isoToMytInput(""), "");
});

t("a manual entry keeps what was typed, dated, and refuses an empty form", () => {
  const e = manualEntry({ remaining: "545.1M", total: "", unit: "credits", expires: "", note: " from the dashboard " }, NOW);
  assert.deepEqual(e, { remaining: 545100000, total: null, unit: "credits", expires_at: null, note: "from the dashboard", entered_at: "2026-11-23T15:31:50Z" });
  assert.equal(manualEntry({ remaining: "", total: "", unit: "Rp", expires: "", note: "" }, NOW), null);
  assert.equal(manualEntry({ remaining: "x", total: "", unit: "Rp", expires: "nonsense", note: "" }, NOW), null);
  assert.equal(manualEntry({ remaining: "", total: "", unit: "Rp", expires: "2026-12-09T23:31" }, NOW).expires_at, "2026-12-09T15:31:00Z", "a date alone is worth keeping");
});

const row = (credit, extra = {}) => ({ slug: "mireld", key_set: true, balance: { credit, tried: [{ path: "/x", http: 404 }], checked_at: credit?.checked_at }, ...extra });

t("a live reading is shown as live, with its age and the path that answered", () => {
  const v = viewOf(row(MIRELD), null, NOW);
  assert.equal(v.source, "live"); assert.equal(v.status, "low"); assert.equal(v.endpoint, "/dashboard/billing/credit_grants");
  assert.equal(v.expiresAt, MIRELD.expires_at); assert.equal(v.expiryManual, false);
  assert.equal(v.ageMs, 110_000); assert.equal(v.late, false); assert.equal(v.stale, false);
  assert.equal(viewOf(row(MIRELD), null, NOW + 50 * 60_000).late, true, "no reading for 45 minutes: the 15-minute run has missed turns");
});

t("a gateway with no readable balance is unknown, shows what was tried, and a typed figure is labelled manual and never live", () => {
  const unread = { remaining: null, total: null, percent_left: null, expires_at: null, status: "unknown", source: null, checked_at: "2026-11-23T15:30:00Z" };
  const v = viewOf(row(unread, { slug: "rootsys" }), null, NOW);
  assert.equal(v.source, "none"); assert.equal(v.status, "unknown"); assert.equal(v.endpoint, null); assert.equal(v.tried.length, 1);
  const typed = manualEntry({ remaining: "545.1M", total: "2.575B", unit: "credits", expires: "", note: "" }, NOW - 3600_000);
  const m = viewOf(row(unread, { slug: "rootsys" }), typed, NOW);
  assert.equal(m.source, "manual"); assert.equal(m.figure.percent_left, 21.2); assert.equal(m.status, "ok"); assert.equal(m.manualAt, "2026-11-23T14:31:50Z");
  const both = viewOf(row(MIRELD), typed, NOW);
  assert.equal(both.source, "live", "a live reading beats a typed one, and the two are never mixed");
  assert.equal(both.figure.remaining, 89.113109);
});

t("a typed date is used (and labelled) only when the gateway gives none", () => {
  const typed = manualEntry({ remaining: "10", total: "100", unit: "credits", expires: "2026-11-30T12:00" }, NOW);
  const noDate = { ...MIRELD, expires_at: null };
  const v = viewOf(row(noDate), typed, NOW);
  assert.equal(v.source, "live"); assert.equal(v.expiresAt, "2026-11-30T04:00:00Z"); assert.equal(v.expiryManual, true);
  assert.equal(viewOf(row(MIRELD), typed, NOW).expiryManual, false);
});

t("a missing row, a stale reading and a missing key are told apart", () => {
  const none = viewOf(undefined, null, NOW);
  assert.equal(none.hasRow, false); assert.equal(none.status, "unknown"); assert.deepEqual(none.tried, []);
  assert.equal(viewOf(row({ ...MIRELD, stale: true }), null, NOW).stale, true);
  assert.equal(viewOf(row(MIRELD, { key_set: false }), null, NOW).keySet, false);
  assert.equal(viewOf({ slug: "mireld", balance: { path: "/balance", balance: 12.5 } }, null, NOW).source, "none", "the old flat balance has no credit object");
});

t("the page is wired: the segment, the page, the lazy import and the telegram entry exist", () => {
  const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");
  assert.match(read("./src/App.jsx"), /const CreditTab = lazy\(\(\) => import\("\.\/pages\/CreditTab"\)\)/);
  assert.match(read("./src/App.jsx"), /tab === "kredit"/);
  assert.match(read("../rules/telegram_menu.json"), /"tab": "kredit"/);
  assert.match(read("../.github/workflows/api-credit.yml"), /cron: "\*\/15 \* \* \* \*"/);
});

console.log(`credit: ${n} checks passed`);
