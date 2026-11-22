// node thumbs.test.mjs: library tiles draw the small copy the worker stores, and fall back to the picture (lib/thumbs.js).
import assert from "node:assert/strict";
import { nextSrc, thumbUrl, tileSrc } from "./src/lib/thumbs.js";

const B = "https://mwaocnbgvbkhovktgods.supabase.co/storage/v1/object/public/semasa-generated/";

// the address is derived the same way backend/semasa/thumbs.py writes it: thumbs/<path>.jpg
assert.equal(thumbUrl(`${B}2026/11/abc.png`), `${B}thumbs/2026/11/abc.png.jpg`);
assert.equal(thumbUrl(`${B}2026/11/abc.JPEG?t=1#x`), `${B}thumbs/2026/11/abc.JPEG.jpg`);
assert.equal(thumbUrl(`${B}2026/11/slide01.webp`), `${B}thumbs/2026/11/slide01.webp.jpg`);

// no copy is made for these, so none is asked for
for (const u of ["", null, undefined, `${B}2026/11/film.mp4`, `${B}motion/storyboard/x/s1.jpg`, `${B}imports/v.jpg`,
  `${B}thumbs/2026/11/a.png.jpg`, "https://images.unsplash.com/photo-1?w=1080", `https://x.supabase.co/storage/v1/object/public/semasa-reference/a.png`,
  `https://x.supabase.co/storage/v1/render/image/public/semasa-generated/a.png`]) {
  assert.equal(thumbUrl(u), "", String(u));
}

// a tile: the copy first, the picture as its fallback; an outside address is drawn as it is
assert.deepEqual(tileSrc(`${B}2026/11/abc.png`), { src: `${B}thumbs/2026/11/abc.png.jpg`, full: `${B}2026/11/abc.png` });
assert.deepEqual(tileSrc("https://images.unsplash.com/p.jpg"), { src: "https://images.unsplash.com/p.jpg", full: "https://images.unsplash.com/p.jpg" });
assert.deepEqual(tileSrc(null), { src: "", full: "" });

// the copy failing (not made yet) falls back to the picture once; the picture failing is the end, as before
const t = tileSrc(`${B}2026/11/abc.png`);
assert.equal(nextSrc(t.src, t.full), t.full);
assert.equal(nextSrc(t.full, t.full), "");
assert.equal(nextSrc("https://images.unsplash.com/p.jpg", "https://images.unsplash.com/p.jpg"), "");
assert.equal(nextSrc("", t.full), "");
assert.equal(nextSrc(t.src, ""), "");

console.log("thumbs: ok");
