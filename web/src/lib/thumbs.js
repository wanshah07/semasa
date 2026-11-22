/* Library tiles draw a small copy, not the full picture (Wan, 22 Nov 2026: "Fix what you recommend", after an egress audit: the
   Image and Poster libraries loaded every tile from generated_media_url, often a 2 MB PNG, 0.9 MB on average, for a tile about
   150 px wide).

   The worker writes a JPEG, short side 400 px, beside every picture it stores (backend/semasa/thumbs.py), at an address DERIVED
   from the picture's own, so no row carries it:
     .../object/public/semasa-generated/2026/11/abc.png  ->  .../object/public/semasa-generated/thumbs/2026/11/abc.png.jpg
   A picture stored before that (until the daily housekeeping run has made its copy), or one whose copy failed, has none: the
   tile's <img> then falls back to the full picture, so it shows exactly as before. The full card, the lightbox and every
   download keep the full picture.
   Supabase's render endpoint (/storage/v1/render/image/...) works on this project too, but it is metered per origin image, so
   it is not used. No React and no Supabase import: web/thumbs.test.mjs runs this under Node. */

const MARK = "/storage/v1/object/public/semasa-generated/";
const IMAGE = /\.(png|jpe?g|webp)$/i;
const SKIP = /^(motion\/|imports\/|thumbs\/)/;   // the same rule as thumbs.thumb_path: no copy is made for these

/** The small copy's address for a stored picture's address, or "" when it has none (not in the bucket, not a picture). */
export function thumbUrl(url) {
  const s = String(url || "");
  const at = s.indexOf(MARK);
  if (at < 0) return "";
  const path = s.slice(at + MARK.length).split("?")[0].split("#")[0];
  if (!path || SKIP.test(path) || !IMAGE.test(path)) return "";
  return `${s.slice(0, at + MARK.length)}thumbs/${path}.jpg`;
}

/** What a tile draws for a picture: { src, full }. src is the small copy when there can be one, full is the picture itself
    (the fallback). An address outside the bucket (Unsplash, a reference) is drawn as it is. */
export function tileSrc(url) {
  const full = String(url || "");
  return { src: thumbUrl(full) || full, full };
}

/** After an <img> failed to load `current`: the address to try next, or "" to give up (hide the tile's picture).
    The small copy fails over to the full picture once; the full picture failing is the end, as it was. */
export function nextSrc(current, full) {
  return current && full && current !== full ? full : "";
}
