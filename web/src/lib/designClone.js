/* The Design tab's "rebuild this design" (Wan, 1 Oct 2026): send the reference to the function (action design_clone), get its LAYOUT back,
   and lay it out as editable Kanvas layers with new words (lib/designCloneSeed.js). The AI is used once to read the layout, and once more
   per refine pass (action design_refine: the reference and our own rendering side by side, a corrected layout back); the words, the
   spelling and the drawing are ours, so the post rules can be checked on every word and every piece stays movable. */
import { explain } from "./chat";
import { supabase } from "./SupabaseClient";
import { loadImageFile } from "./designPatch";

const MAX_SIDE = 1600;

/** The reference as a JPEG data URL no bigger than MAX_SIDE on its longest side (a phone screenshot would otherwise be megabytes),
    with its natural size. */
export async function shrinkReference(file) {
  const img = await loadImageFile(file);
  const k = Math.min(1, MAX_SIDE / Math.max(img.naturalWidth, img.naturalHeight));
  const c = document.createElement("canvas");
  c.width = Math.max(1, Math.round(img.naturalWidth * k)); c.height = Math.max(1, Math.round(img.naturalHeight * k));
  const ctx = c.getContext("2d");
  ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, c.width, c.height);     // a transparent PNG would turn black in a JPEG
  ctx.drawImage(img, 0, 0, c.width, c.height);
  return { dataUrl: c.toDataURL("image/jpeg", 0.88), width: img.naturalWidth, height: img.naturalHeight };
}

async function call(body) {
  if (!supabase) throw new Error("Supabase belum disambung / Supabase is not configured");
  const { data, error } = await supabase.functions.invoke("semasa-chat", { body });
  if (error) {
    const why = await explain(error);
    throw new Error(why.missing ? "fungsi belum dipasang: GitHub → Actions → Deploy functions / the function is not deployed yet: GitHub → Actions → Deploy functions" : why.message);
  }
  if (data?.error) throw new Error(String(data.error));
  if (!data?.layout) throw new Error("tiada susun atur dipulangkan / no layout came back");
  return data;
}

/** { layout, removed, hasWords, image } for a reference. `mode` is "clone" (the same arrangement) or "inspire" (an original one in its
    visual language). `image` is the shrunk reference, kept for the refine pass. Throws an Error with a sentence the person can read. */
export async function cloneLayout({ file, width, height, stream, brief = "", mode = "clone" }) {
  const { dataUrl } = await shrinkReference(file);
  const data = await call({ action: "design_clone", image: dataUrl, width, height, stream, mode, ...(brief.trim() ? { brief: brief.trim() } : {}) });
  return { layout: data.layout, removed: data.removed || [], hasWords: data.has_words === true, model: data.model || "", image: dataUrl };
}

/** One refine pass: the reference (`image`, a data URL), our rendering of the current layout (`render`, a data URL) and that layout. */
export async function refineLayout({ image, render, layout, width, height }) {
  const data = await call({ action: "design_refine", image, render, layout, width, height });
  return { layout: data.layout, removed: data.removed || [], model: data.model || "" };
}
