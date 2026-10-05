/* A design from a reference picture, made in one call (Wan, 4-5 Oct 2026): the AI reads the picture's LAYOUT once, the colours are measured
   from its own pixels, and the result is a saved design with no words that every draft pours its words into (see ops/MY-DESIGNS.md).
   Used by the My designs editor and by "Save as my design" in the Design tab's reference box. */
import { cloneLayout } from "./designClone";
import { snapLayout } from "./designFidelity";
import { loadImageFile, readPixels, sizeLike } from "./designPatch";

/** { layout, measured, removed } for a reference file. Throws an Error with a sentence the person can read. */
export async function readReference(file, stream = "regulab") {
  const img = await loadImageFile(file);
  const [w, h] = sizeLike(img.naturalWidth, img.naturalHeight);
  const got = await cloneLayout({ file, width: w, height: h, stream, mode: "clone" });
  const px = await readPixels(file, 900).catch(() => null);
  const snapped = px ? snapLayout(got.layout, px) : null;           // the AI guessed the colours by eye: the picture's pixels know them
  return { layout: snapped ? snapped.layout : got.layout, measured: snapped ? snapped.changes.length : 0, removed: got.removed || [] };
}

/** A name for a design made from a file: its file name without the extension, tidied. */
export const nameFromFile = (file) => String(file?.name || "").replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ").trim().slice(0, 40) || "Reka bentuk rujukan";
