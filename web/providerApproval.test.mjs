import test from "node:test";
import assert from "node:assert/strict";
import { webcrypto } from "node:crypto";
if (!globalThis.crypto) globalThis.crypto = webcrypto;
const { approvalToken, providerFor } = await import("./src/lib/providerApproval.js");

const post = { id: "p1", provider: "postiz", stream: "linkedin", lang: "en", text: { en: { linkedin: "hello" } },
  citation: "NPRA", media_ids: ["m1"], date: "2026-11-02", slot: "08:00", channels: ["linkedin"] };
const media = [{ id: "m1", type: "video", generated_media_url: "https://cdn/film.mp4", meta: { sha256: "a".repeat(64), bytes: 12, mime: "video/mp4", seconds: 8 } }];

test("approval matches backend and binds media/accounts", async () => {
  const token = await approvalToken(post, media, { linkedin: "personal-1" });
  assert.match(token, /^[a-f0-9]{64}$/);
  assert.notEqual(token, await approvalToken(post, media, { linkedin: "other" }));
  assert.notEqual(token, await approvalToken({ ...post, slot: "09:00" }, media, { linkedin: "personal-1" }));
});
test("legacy routes remain backups until staged cutover", () => {
  assert.equal(providerFor({ stream: "regulab" }, {}), "buffer");
  assert.equal(providerFor({ stream: "linkedin" }, {}), "composio");
  assert.equal(providerFor({ stream: "regulab" }, { publishing: { default_provider: "postiz" }, channels: { postiz: { enabled: true } } }), "postiz");
});
