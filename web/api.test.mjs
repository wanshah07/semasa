import assert from "node:assert/strict";
import { fmtTokens, mytDay, orderedModels, usageByArea, usageByDay, usageByGateway, verdictOf } from "./src/lib/api.js";

const NOW = Date.parse("2026-10-09T06:00:00Z");
assert.equal(verdictOf(null), "none");
assert.equal(verdictOf({ key_set: false }), "nokey");
assert.equal(verdictOf({ key_set: true, checked_at: "2026-10-08T06:00:00Z", reachable: true, chat_ok: true }, NOW), "stale");
assert.equal(verdictOf({ key_set: true, checked_at: "2026-10-09T05:00:00Z", reachable: false }, NOW), "down");
assert.equal(verdictOf({ key_set: true, checked_at: "2026-10-09T05:00:00Z", reachable: true, key_ok: false }, NOW), "key");
assert.equal(verdictOf({ key_set: true, checked_at: "2026-10-09T05:00:00Z", reachable: true, key_ok: true, chat_ok: true }, NOW), "up");
assert.equal(verdictOf({ key_set: true, checked_at: "2026-10-09T05:00:00Z", reachable: true, key_ok: true, chat_ok: false }, NOW), "models");

// 23:30 UTC on the 8th is already the 9th in Malaysia
assert.equal(mytDay("2026-10-08T23:30:00Z"), "2026-10-09");

const rows = [
  { gateway: "rootsys", model: "gpt-4.1-mini", area: "scrape", total_tokens: 1000, prompt_tokens: 800, completion_tokens: 200, ms: 500, ok: true, created_at: "2026-10-09T01:00:00Z" },
  { gateway: "rootsys", model: "gpt-4.1-mini", area: "scrape", total_tokens: 0, prompt_tokens: 0, completion_tokens: 0, ms: 60000, ok: false, created_at: "2026-10-09T02:00:00Z" },
  { gateway: "mireld", model: "claude-sonnet-5.5", area: "media", total_tokens: 300, prompt_tokens: 250, completion_tokens: 50, ms: 900, ok: true, created_at: "2026-10-08T23:30:00Z" },
  { gateway: "mireld", model: "claude-sonnet-5.5", area: "media", total_tokens: 9999, ok: true, created_at: "2026-08-01T00:00:00Z" },   // outside the window
];
const g = usageByGateway(rows, 7, "2026-10-09");
assert.equal(g.rootsys.calls, 2); assert.equal(g.rootsys.failed, 1); assert.equal(g.rootsys.tokens, 1000); assert.equal(g.rootsys.ms, 60500);
assert.equal(g.mireld.calls, 1); assert.equal(g.mireld.tokens, 300); assert.deepEqual(g.mireld.models, { "claude-sonnet-5.5": 300 });
assert.equal(g.mireld.tokens, 300, "the August row is out of the window");

const d = usageByDay(rows, 3, "2026-10-09");
assert.deepEqual(d.gateways, ["mireld", "rootsys"]);
assert.equal(d.series.length, 3);
assert.deepEqual(d.series[2], { date: "2026-10-09", calls: 3, mireld: 300, rootsys: 1000 });
assert.deepEqual(d.series[0], { date: "2026-10-07", calls: 0, mireld: 0, rootsys: 0 });

assert.deepEqual(usageByArea(rows, 7, "2026-10-09"), [{ area: "scrape", tokens: 1000 }, { area: "media", tokens: 300 }]);

assert.deepEqual(orderedModels({ model: "claude-sonnet-5.5", models: ["zeta-embed", "gpt-4.1", "claude-sonnet-5.5", "alpha-tts"] }),
  ["claude-sonnet-5.5", "gpt-4.1", "alpha-tts", "zeta-embed"]);
assert.deepEqual(orderedModels(null), []);

assert.equal(fmtTokens(999), "999"); assert.equal(fmtTokens(12345), "12.3k"); assert.equal(fmtTokens(2_500_000), "2.50M"); assert.equal(fmtTokens(undefined), "0");

console.log("api.test.mjs: 24 checks OK");
