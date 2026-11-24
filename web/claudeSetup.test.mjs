import assert from "node:assert/strict";
import { applyPlan, claudeFacts, claudeRow, pictureTest, planState, resolveModel, suggestModel, withProviderModel } from "./src/lib/claudeSetup.js";

const LISTED = ["claude-opus-5-5", "claude-sonnet-5-5", "claude-sonnet-4-5-20250929", "claude-haiku-4-5-20251001", "gpt-5.6-sol", "gpt-5.6-sol-mini"];

// the name Wan saved became the id Anthropic lists, and the rule matches the backend's (ai_providers.resolve_model)
assert.equal(resolveModel("Claude Opus 5.5", LISTED), "claude-opus-5-5");
assert.equal(resolveModel("claude-opus-5-5", LISTED), "claude-opus-5-5");
assert.equal(resolveModel("Sonnet 5.5", LISTED), "claude-sonnet-5-5");
assert.equal(resolveModel("claude-sonnet-4-5", LISTED), "claude-sonnet-4-5-20250929");
assert.equal(resolveModel("gpt-5.6", LISTED), "gpt-5.6");                 // a model that merely starts with it is not taken
assert.equal(resolveModel("Claude Fable 9", LISTED), "Claude Fable 9");   // nothing close: unchanged
assert.equal(resolveModel("Claude Opus 5.5", []), "Claude Opus 5.5");

// the provider and what is wrong with it
const row = { id: "claude", dialect: "anthropic", enabled: true, key_hint: "…ZQAA", model: "Claude Opus 5.5" };
assert.equal(claudeRow([{ id: "x", dialect: "openai" }, row]).id, "claude");
assert.equal(claudeRow([{ id: "mine", dialect: "anthropic" }]).id, "mine");
assert.equal(claudeRow([]), null);
const probe = { key_ok: true, reachable: true, chat_ok: false, models: LISTED, error: "404 not_found_error", chat_ms: 191 };
const f = claudeFacts(row, probe);
assert.equal(f.verdict, "fixable");                                      // the model name, not the key, is what failed
assert.equal(f.fixedTo, "claude-opus-5-5");
assert.equal(f.needsFix, true);
assert.equal(claudeFacts({ ...row, model: "claude-opus-5-5" }, { ...probe, chat_ok: true }).verdict, "ok");
assert.equal(claudeFacts({ ...row, model: "claude-opus-5-5" }, { ...probe, chat_ok: false }).verdict, "failing");
assert.equal(claudeFacts({ ...row, model: "Claude Fable 9" }, probe).verdict, "nomodel");
assert.equal(claudeFacts(row, { ...probe, key_ok: false }).verdict, "keyrefused");
assert.equal(claudeFacts(row, null).verdict, "unchecked");
assert.equal(claudeFacts({ ...row, enabled: false }, probe).verdict, "off");
assert.equal(claudeFacts({ ...row, key_hint: "" }, probe).verdict, "nokey");
assert.equal(claudeFacts(null, null).verdict, "none");
assert.equal(suggestModel(LISTED), "claude-opus-5-5");
assert.equal(suggestModel(["gpt-1"]), "");

// the plan: Claude first for the text, ChatGPT for the pictures, nothing else lost
const team = { pins: { reader: { gateway: "rootsys", model: "glm-5.4" }, motion: null, image_gen: { gateway: "kiosapi", model: "gpt-image-2" } },
  efforts: { "rootsys|glm-5.4": "xhigh" }, models: { mireld: "gpt-6.1-sol" } };
const now = new Date("2026-11-24T10:00:00Z");
const next = applyPlan(team, row, "claude-opus-5-5", now);
assert.equal(next.prefer, "claude");
assert.deepEqual(next.pins.reader, { gateway: "claude", model: "claude-opus-5-5" });
assert.deepEqual(next.pins.image_gen, { gateway: "chatgpt", model: "" });   // another gateway's model is not carried to ChatGPT
assert.deepEqual(next.efforts, team.efforts);
assert.deepEqual(next.models, team.models);
assert.equal(next.changed_at, "2026-11-24T10:00:00.000Z");
assert.deepEqual(planState(team, row), { text: false, pictures: false });
assert.deepEqual(planState(next, row), { text: true, pictures: true });
assert.equal(applyPlan({ pins: { image_gen: { gateway: "chatgpt", model: "gpt-6.2-sol" } } }, row, "x", now).pins.image_gen.model, "gpt-6.2-sol");
assert.equal(applyPlan(undefined, row, "", now).pins.reader.model, "Claude Opus 5.5");

// the picture test: asked after the last answer means running, then passed or failed with the steps that failed
const t0 = Date.parse("2026-11-24T10:00:00Z");
assert.equal(pictureTest({}, {}, t0).state, "none");
assert.equal(pictureTest({ at: "2026-11-24T10:00:00Z" }, { at: "2026-11-24T09:00:00Z", ok: true }, t0 + 60_000).state, "running");
assert.equal(pictureTest({ at: "2026-11-24T10:00:00Z" }, { at: "2026-11-24T09:00:00Z", ok: true }, t0 + 13 * 60_000).state, "lost");
assert.equal(pictureTest({ at: "2026-11-24T10:00:00Z" }, { at: "2026-11-24T10:03:00Z", ok: true, model: "m" }, t0 + 240_000).state, "ok");
const bad = pictureTest({}, { at: "2026-11-24T10:03:00Z", ok: false, steps: { write: { ok: true }, draw: { ok: false, detail: "HTTP 402" } } });
assert.equal(bad.state, "failed");
assert.equal(pictureTest({}, { at: "2026-11-24T10:03:00Z", ok: true, model: "gpt-6.2-sol", draw_model: "gpt-6-astra" }).model, "gpt-6-astra");   // the model that drew
assert.deepEqual(bad.bad, [{ step: "draw", detail: "HTTP 402" }]);
assert.equal(pictureTest({}, { at: "2026-11-24T10:03:00Z", ok: false, not_connected: true }).state, "notconnected");
// clicking a model on a provider's card: the pins that name it follow, the rest stay
const clicked = withProviderModel({ pins: { reader: { gateway: "claude", model: "claude-opus-5-5" }, motion: null, image_gen: { gateway: "chatgpt", model: "" } }, prefer: "claude" },
  "claude", "claude-sonnet-5-5", now);
assert.deepEqual(clicked.pins.reader, { gateway: "claude", model: "claude-sonnet-5-5" });
assert.deepEqual(clicked.pins.image_gen, { gateway: "chatgpt", model: "" });
assert.equal(clicked.pins.motion, null);
assert.equal(clicked.prefer, "claude");
assert.equal(clicked.changed_at, "2026-11-24T10:00:00.000Z");
assert.deepEqual(withProviderModel(undefined, "claude", "m", now).pins, {});
console.log("claudeSetup: ok");
