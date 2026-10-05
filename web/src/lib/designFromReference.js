/* A design from a reference picture (Wan, 4-5 Oct 2026): "render the design until it has a similar background and text layout with the
   reference". The AI reads the picture's LAYOUT once; the colours are measured from its own pixels; then the layout is DRAWN the way
   a draft would draw it (on the reference picture itself, the old words and logos covered by patches, words as long as the reference's
   poured in), the drawing is SCORED against the reference, and the AI is asked to correct the layout, up to three times, keeping a pass
   only if it scores better. What is left is saved with no words: the layout, the patches and the picture, for every draft to fill.
   Used by the My designs editor and by "Save as my design" in the Design tab's reference box. */
import { cloneLayout, refineLayout } from "./designClone";
import { compareImages, fillerSlide, judgePass, snapLayout } from "./designFidelity";
import { loadImageFile, readPixels, samplePatches, sizeLike } from "./designPatch";
import { patchBoxes } from "./designCloneSeed";
import { ensureFonts, renderSlides, setLogo } from "./cards/studio";
import { uploadReference } from "./storage";

const BASE = `${import.meta.env.BASE_URL}cards/`;
export const GOAL = 90, MAX_PASSES = 3;

/** A name for a design made from a file: its file name without the extension, tidied. */
export const nameFromFile = (file) => String(file?.name || "").replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ").trim().slice(0, 40) || "Reka bentuk rujukan";

/** { layout, measured, removed, image } for a reference file (one AI read). Throws an Error with a sentence the person can read. */
export async function readReference(file, stream = "regulab") {
  const img = await loadImageFile(file);
  const [w, h] = sizeLike(img.naturalWidth, img.naturalHeight);
  const got = await cloneLayout({ file, width: w, height: h, stream, mode: "clone" });
  const px = await readPixels(file, 900).catch(() => null);
  const snapped = px ? snapLayout(got.layout, px) : null;           // the AI guessed the colours by eye: the picture's pixels know them
  return { layout: snapped ? snapped.layout : got.layout, measured: snapped ? snapped.changes.length : 0, removed: got.removed || [], image: got.image };
}

/**
 * Read, draw, score, correct: the design a reference makes. `onStep(text)` reports progress in the person's words.
 * Returns { layout, patches, score, first, size: [w, h], image (the shrunk reference as a data URL), render (the best drawing as a data URL),
 * measured, removed }. Nothing is uploaded here.
 */
export async function buildDesignFromReference(file, { stream = "regulab", onStep = () => {}, t = (bm, en) => en } = {}) {
  const [w, h] = await loadImageFile(file).then((im) => sizeLike(im.naturalWidth, im.naturalHeight));
  setLogo(`${BASE}logo.png`);
  await ensureFonts(BASE);
  onStep(t("AI membaca susun atur rujukan…", "The AI is reading the reference's layout…"));
  const first = await readReference(file, stream);
  const refPx = await readPixels(file, 900);
  if (!refPx) throw new Error(t("Gambar rujukan tidak boleh dibaca oleh pelayar (disekat). Cuba fail PNG/JPEG lain.", "The browser could not read the reference's pixels (blocked). Try another PNG or JPEG file."));

  // one drawing of a layout, as a draft would draw it, compared with the reference
  async function evaluate(layout) {
    const patches = (await samplePatches(file, patchBoxes(layout))).filter(Boolean);
    const design = { look: "grid", layouts: { main: layout }, refart: { url: first.image, w, h, patches } };
    const [card] = await renderSlides([fillerSlide(layout)], { design, size: [w, h], stream });
    const px = await readPixels(card.url, 900);
    const fit = compareImages(refPx, px);
    return { layout, patches, score: fit.score, render: card.url, worst: fit.worst };
  }
  onStep(t("Melukis dan membandingkan dengan rujukan…", "Drawing it and comparing with the reference…"));
  let best = await evaluate(first.layout);
  const firstScore = best.score;
  onStep(t("Padanan {n}%", "Match {n}%", { n: Math.round(best.score) }));
  for (let pass = 1; pass <= MAX_PASSES && best.score < GOAL; pass++) {
    onStep(t("Pusingan {p}: AI membetulkan kedudukan ({n}%)…", "Pass {p}: the AI corrects the placing ({n}%)…", { p: pass, n: Math.round(best.score) }));
    let next;
    try { next = await refineLayout({ image: first.image, render: best.render, layout: best.layout, width: w, height: h }); } catch { break; }
    const cand = await evaluate(snapLayout(next.layout, refPx).layout);
    const v = judgePass({ score: best.score }, { score: cand.score });
    if (v.accepted) best = cand;
    onStep(v.accepted ? t("Diterima: {n}%", "Accepted: {n}%", { n: Math.round(cand.score) }) : t("Tidak lebih hampir ({n}%): dikekalkan {m}%", "Not closer ({n}%): keeping {m}%", { n: Math.round(cand.score), m: Math.round(best.score) }));
    if (v.stop) break;
  }
  return { layout: best.layout, patches: best.patches, score: best.score, first: firstScore, size: [w, h], image: first.image, render: best.render,
    measured: first.measured, removed: first.removed };
}

/** The saved form of a build: the reference picture is stored (a file in the reference bucket) and the design keeps its path, size and patches. */
export async function uploadReferenceArt(user, built) {
  const blob = await (await fetch(built.image)).blob();
  const up = await uploadReference(user, new File([blob], "reference-art.jpg", { type: "image/jpeg" }));
  return { path: up.path, w: built.size[0], h: built.size[1], patches: built.patches };
}
