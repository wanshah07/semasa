/* Speaker photos on the event poster (Wan, 4 Oct 2026): a slide keeps them as one comma-joined string of tokens in the order of
   its points ("ref:<user id>/<file>", empty = no photo for that speaker), the same shape lib/compliance.js photoTokens and the
   worker's photo_tokens read. Pure, so Node tests it; the browser parts (resize, upload, address) are in lib/storage.js. */
import { MAX_PHOTOS, photoTokens } from "./compliance.js";

export const photoPath = (token) => (/^ref:/.test(token || "") ? token.slice(4) : "");
export const photoToken = (path) => `ref:${path}`;

/** The token for speaker `idx` (0-based, among the slide's non-empty points), or "". */
export const photoAt = (value, idx) => photoTokens(value)[idx] || "";

/** The `photos` string with speaker `idx` set to `token` ("" removes it); trailing blanks dropped, at most MAX_PHOTOS. */
export function withPhoto(value, idx, token) {
  if (idx < 0 || idx >= MAX_PHOTOS) return String(value ?? "");
  const toks = photoTokens(value);
  while (toks.length <= idx) toks.push("");
  toks[idx] = token || "";
  while (toks.length && !toks[toks.length - 1]) toks.pop();
  return toks.join(",");
}

/** The speakers of a slide's points text: [{ name, where }] for each non-empty line, in order (the same order the photos follow). */
export const speakersOf = (points) => String(points ?? "").split("\n").map((l) => l.trim()).filter(Boolean)
  .map((l) => { const [name, where] = l.split("|").map((x) => x.trim()); return { name: name || "", where: where || "" }; });

/** A photo stays with its speaker when the points are reordered or one is deleted or added. If every speaker after the edit was
    already there (same names, any order, some gone), photos follow the names; otherwise (a name being typed) they stay by position,
    so editing a name never loses its photo. */
export function photosFollow(value, before, after) {
  const toks = photoTokens(value);
  if (!toks.some(Boolean)) return "";
  const named = after.length && after.every((s) => s.name && before.some((b) => b.name === s.name))
    && (after.length !== before.length || after.some((s, i) => s.name !== before[i]?.name));
  const out = named ? after.map((s) => toks[before.findIndex((b) => b.name === s.name)] || "") : after.map((_, i) => toks[i] || "");
  while (out.length && !out[out.length - 1]) out.pop();
  return out.join(",");
}
