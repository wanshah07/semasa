import assert from "node:assert/strict";
import { decisionOf, decisionPending, liveLines, modelsFor, pinFor, robotOf, robotsFor, stateOf, teamCards, withPin } from "./src/lib/aiTeam.js";

const NOW = Date.parse("2026-10-23T06:00:00Z");
const row = (slug, over = {}) => ({ slug, key_set: true, reachable: true, key_ok: true, chat_ok: true, checked_at: "2026-10-23T05:00:00Z", models: [], ...over });

// robots: the three named, a guest for any other host
assert.equal(robotOf("rootsys").robot, "W1");
assert.equal(robotOf("kiosapi").tone, "kios");
assert.deepEqual(robotOf("openai", { base_url: "https://api.openai.com/v1", name: "OpenAI" }).does, ["read", "write"]);
assert.deepEqual(robotOf("x", { role: "image" }).does, ["make_image"]);

// state
assert.equal(stateOf(null), "offline");
assert.equal(stateOf(row("rootsys", { key_set: false })), "offline");
assert.equal(stateOf(row("rootsys", { checked_at: "2026-10-22T06:00:00Z" }), [], NOW), "offline", "not checked in 13 h");
assert.equal(stateOf(row("rootsys", { key_ok: false }), [], NOW), "offline");
assert.equal(stateOf(row("rootsys", { chat_ok: false }), [], NOW), "offline");
assert.equal(stateOf(row("rootsys"), [], NOW), "standby");
assert.equal(stateOf(row("rootsys"), [{ gateway: "rootsys", ok: true, area: "scrape", created_at: "2026-10-23T05:30:00Z" }], NOW), "active");
assert.equal(stateOf(row("rootsys"), [{ gateway: "rootsys", ok: true, area: "probe", created_at: "2026-10-23T05:30:00Z" }], NOW), "standby", "a probe is not work");
assert.equal(stateOf(row("rootsys"), [{ gateway: "mireld", ok: true, area: "scrape", created_at: "2026-10-23T05:30:00Z" }], NOW), "standby");
// an image gateway the probe marked up by its model list is standby/active like any other
assert.equal(stateOf(row("kiosapi", { role: "image" }), [], NOW), "standby");

// cards: always the three, in HE's order, plus any guest
const cards = teamCards([row("mireld"), row("openai", { base_url: "https://api.openai.com/v1" })], [], NOW);
assert.deepEqual(cards.map((c) => c.slug), ["rootsys", "kiosapi", "mireld", "openai"]);
assert.equal(cards[0].state, "offline"); assert.equal(cards[0].configured, false);
assert.equal(cards[2].state, "standby");

// the decision
const state = { at: "2026-10-23T05:40:00Z", reader: { chosen: { slug: "mireld", name: "Wanshah 2", model: "m" }, order: [{ slug: "mireld" }], skipped: [{ slug: "kiosapi", why: "paints" }], why: "600 ms" } };
assert.equal(decisionOf(state).chosen.slug, "mireld");
assert.equal(decisionOf(state).at, "2026-10-23T05:40:00Z");
assert.deepEqual(decisionOf(null), { chosen: null, backup: null, order: [], skipped: [], pin: null, why: "", at: "", live: null });
assert.deepEqual(decisionOf(state, "image_gen").order, []);

// pins
assert.equal(pinFor(null, "reader"), null);
assert.deepEqual(pinFor({ pins: { reader: { gateway: "mireld", model: "x" } } }, "reader"), { gateway: "mireld", model: "x" });
assert.equal(pinFor({ pins: { reader: { gateway: "" } } }, "reader"), null);
const team = withPin({ pins: { image_gen: { gateway: "kiosapi", model: "gpt-image-2" } }, other: 1 }, "reader", { gateway: "rootsys" }, new Date("2026-10-31T14:00:00Z"));
assert.deepEqual(team, { pins: { image_gen: { gateway: "kiosapi", model: "gpt-image-2" }, reader: { gateway: "rootsys", model: "" } }, other: 1, changed_at: "2026-10-31T14:00:00.000Z" });
assert.equal(withPin(team, "reader", null).pins.reader, null);
assert.deepEqual(withPin(team, "reader", null).pins.image_gen, { gateway: "kiosapi", model: "gpt-image-2" }, "another job's pin is untouched");

// models offered: text models for the writer, image models for the painter, the configured one first
const kios = row("kiosapi", { model: "gpt-image-2", models: ["gpt-4.1", "flux-pro", "gpt-image-2"] });
assert.deepEqual(modelsFor(kios, "image_gen"), ["gpt-image-2", "flux-pro"]);
assert.deepEqual(modelsFor(kios, "reader"), ["gpt-4.1"]);
assert.deepEqual(modelsFor({ model: "a", models: ["a", "b"] }, "reader"), ["a", "b"]);
assert.deepEqual(modelsFor(null, "reader"), []);

// who may take a job
const three = teamCards([], [], NOW);
assert.deepEqual(robotsFor(three, "reader").map((c) => c.robot), ["W1", "W3", "W2"], "KiosAPI serves chat models too; an image model is refused by name, not by host");
assert.deepEqual(robotsFor(three, "motion").map((c) => c.robot), ["W1", "W3", "W2"]);
assert.deepEqual(robotsFor(three, "image_gen").map((c) => c.robot), ["W3"]);
assert.deepEqual(robotsFor(three, "image_reader").map((c) => c.robot), ["W1", "W3", "W2"]);


// Wan, 31 Oct 2026: "why I cannot change the model": a saved pin says when it changed, and the page waits for a decision made after it
const pinned = withPin({ pins: {} }, "reader", { gateway: "rootsys", model: "glm-5.3" }, new Date("2026-10-31T14:00:00Z"));
assert.equal(pinned.changed_at, "2026-10-31T14:00:00.000Z");
assert.deepEqual(pinFor(pinned, "reader"), { gateway: "rootsys", model: "glm-5.3" });
const at = (m) => Date.parse("2026-10-31T14:00:00Z") + m * 60_000;
assert.equal(decisionPending(pinned, { at: "2026-10-31T13:55:00Z" }, at(1)), true, "decided before the change: still testing");
assert.equal(decisionPending(pinned, { at: "2026-10-31T14:01:00Z" }, at(2)), false, "decided after the change: done");
assert.equal(decisionPending(pinned, {}, at(2)), true, "never decided: testing");
assert.equal(decisionPending(pinned, { at: "2026-10-31T13:55:00Z" }, at(20)), false, "a worker that never woke does not leave 'testing' for ever");
assert.equal(decisionPending({ pins: {} }, { at: "x" }, at(1)), false, "no change recorded: nothing pending");
const lines = liveLines({ answers: { "rootsys|glm-5.3": { ok: true, ms: 910, error: "" }, "rootsys|kimi-k3.1-pro": { ok: false, ms: 40, error: "502 Service temporarily unavailable" } }, found: { rootsys: "glm-5.3" } });
assert.deepEqual(lines.map((l) => l.ok), [true, false, true]);
assert.match(lines[0].text, /glm-5\.3 · rootsys: 910 ms/);
assert.match(lines[1].text, /502/);
assert.equal(lines[2].found, true);
assert.deepEqual(liveLines(null), []);
console.log("aiTeam.test.mjs: ok");
