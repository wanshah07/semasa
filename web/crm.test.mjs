/* CRM: the audience rule (mirror of semasa_crm_queue), merge fields, validation, summary. `npm test`. */
import assert from "node:assert/strict";
import { audienceOf, campaignRow, contactRow, crmSummary, mailable, merge, parseTags, validateCampaign, validateContact } from "./src/lib/crm.js";

let n = 0;
const t = (name, fn) => { try { fn(); n++; } catch (e) { console.error("FAIL:", name); throw e; } };

const K = [
  { id: 1, name: "Aisyah Rahman", company: "Marosia", email: "a@m.my", stage: "client", tags: ["kosmetik"], lang: "bm", consent: true },
  { id: 2, name: "Ben", company: "Benco", email: "b@b.my", stage: "lead", tags: ["halal"], lang: "en", consent: true },
  { id: 3, name: "Cik C", company: "", email: "c@c.my", stage: "lead", tags: [], lang: "bm", consent: false },
  { id: 4, name: "Dee", company: "", email: "d@d.my", stage: "prospect", tags: ["kosmetik"], lang: "bm", consent: true, unsubscribed_at: "2026-10-01T00:00:00Z" },
  { id: 5, name: "Encik E", company: "", email: "", stage: "lead", tags: [], lang: "bm", consent: true },
];

t("mailable: address + consent + not unsubscribed", () => {
  assert.deepEqual(K.map(mailable), [true, true, false, false, false]);
});

t("audience: empty means everyone consenting; stages/tags/lang narrow; skipped carry a reason", () => {
  const all = audienceOf({ audience: {} }, K);
  assert.deepEqual(all.send.map((k) => k.id), [1, 2]);
  assert.deepEqual(all.skipped.map((k) => [k.id, k.why]), [[3, "no_consent"], [4, "unsubscribed"], [5, "no_email"]]);
  assert.deepEqual(audienceOf({ audience: { stages: ["lead"] } }, K).send.map((k) => k.id), [2]);
  assert.deepEqual(audienceOf({ audience: { tags: ["kosmetik"] } }, K).send.map((k) => k.id), [1]);
  assert.deepEqual(audienceOf({ audience: { lang: "en" } }, K).send.map((k) => k.id), [2]);
  assert.deepEqual(audienceOf({ audience: { stages: ["client"], lang: "en" } }, K).named, []);
});

t("merge fills name and company, nothing else", () => {
  assert.equal(merge("Hai {{name}} dari {{company}}, {{other}}", K[0]), "Hai Aisyah Rahman dari Marosia, {{other}}");
  assert.equal(merge("{{company}}", { name: "x" }), "");
});

t("validation", () => {
  assert.deepEqual(validateCampaign({ name: "", subject: "", body: "" }), ["name", "subject", "body"]);
  assert.deepEqual(validateCampaign({ name: "a", subject: "b", body: "c", kind: "broadcast", send_at: "nonsense" }), ["send_at"]);
  assert.deepEqual(validateCampaign({ name: "a", subject: "b", body: "c", kind: "broadcast", send_at: "2026-10-10T09:00" }), []);
  assert.deepEqual(validateContact({ name: "", email: "x", stage: "lead" }), ["name", "email"]);
  assert.deepEqual(validateContact({ name: "A", email: "", stage: "lead", consent: true, consent_source: "" }), ["consent_source"]);
  assert.deepEqual(validateContact({ name: "A", email: "a@b.my", stage: "client", consent: true, consent_source: "form" }), []);
});

t("tags and rows", () => {
  assert.deepEqual(parseTags("Kosmetik, halal; Halal\nfood"), ["kosmetik", "halal", "food"]);
  const r = contactRow({ name: " A ", email: "A@B.MY", stage: "nonsense", tags: "x, y", lang: "en", consent: "yes", next_action_at: "" });
  assert.equal(r.email, "a@b.my"); assert.equal(r.stage, "lead"); assert.deepEqual(r.tags, ["x", "y"]); assert.equal(r.consent, true); assert.equal(r.next_action_at, null);
  const c = campaignRow({ name: "P", kind: "welcome", subject: "s", body: "b", audience: { stages: ["lead", "bogus"] }, send_at: "2026-10-10T09:00" });
  assert.equal(c.send_at, null); assert.deepEqual(c.audience.stages, ["lead"]);
  assert.equal(campaignRow({ name: "P", kind: "broadcast", send_at: "2026-10-10T09:00:00+08:00" }).send_at, "2026-10-10T01:00:00.000Z");
  assert.equal(campaignRow({ name: "P", kind: "broadcast", send_at: "2026-10-10T09:00" }).send_at, "2026-10-10T01:00:00.000Z");   // the picker's value is MYT
  assert.equal(campaignRow({ name: "P", kind: "broadcast", send_at: "" }).send_at, null);
});

t("summary", () => {
  const out = [{ status: "sent", is_test: false, sent_at: "2026-10-01T00:00:00Z" }, { status: "sent", is_test: true, sent_at: "2026-10-01T00:00:00Z" },
    { status: "sent", is_test: false, sent_at: "2026-08-01T00:00:00Z" }, { status: "error" }];
  const s = crmSummary([...K, { id: 6, name: "F", stage: "lead", next_action_at: "2026-10-08" }], out, "2026-10-09");
  assert.equal(s.total, 6); assert.equal(s.byStage.lead, 4); assert.equal(s.consenting, 2); assert.equal(s.unsubscribed, 1);
  assert.equal(s.actionsDue, 1); assert.equal(s.sent30, 1); assert.equal(s.failed, 1);
});

console.log(`crm: ${n} checks passed`);
