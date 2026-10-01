/* The Design tab's "rebuild this design" (Wan, 1 Oct 2026): send the reference to the function (action design_clone), get its LAYOUT back,
   and lay it out as editable Kanvas layers with new words (lib/designCloneSeed.js). The AI is used once, to read the layout; the words, the
   spelling and the drawing are ours, so the post rules can be checked on every word and every piece stays movable. */
import { explain } from "./chat";
import { supabase } from "./SupabaseClient";

const MAX_SIDE = 1600;

/** The reference as a JPEG data URL no bigger than MAX_SIDE on its longest side (a phone screenshot would otherwise be megabytes). */
export async function shrinkReference(file) {
  const url = URL.createObjectURL(file);
  try {
    const img = await new Promise((resolve, reject) => {
      const i = new Image();
      i.onload = () => resolve(i);
      i.onerror = () => reject(new Error("gambar rujukan tidak boleh dibuka / the reference picture could not be opened"));
      i.src = url;
    });
    const k = Math.min(1, MAX_SIDE / Math.max(img.naturalWidth, img.naturalHeight));
    const c = document.createElement("canvas");
    c.width = Math.max(1, Math.round(img.naturalWidth * k)); c.height = Math.max(1, Math.round(img.naturalHeight * k));
    const ctx = c.getContext("2d");
    ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, c.width, c.height);     // a transparent PNG would turn black in a JPEG
    ctx.drawImage(img, 0, 0, c.width, c.height);
    return c.toDataURL("image/jpeg", 0.88);
  } finally { URL.revokeObjectURL(url); }
}

/** { layout, removed, hasWords } for a reference. Throws an Error with a sentence the person can read. */
export async function cloneLayout({ file, width, height, stream, brief = "" }) {
  if (!supabase) throw new Error("Supabase belum disambung / Supabase is not configured");
  const image = await shrinkReference(file);
  const { data, error } = await supabase.functions.invoke("semasa-chat", {
    body: { action: "design_clone", image, width, height, stream, ...(brief.trim() ? { brief: brief.trim() } : {}) },
  });
  if (error) {
    const why = await explain(error);
    throw new Error(why.missing ? "fungsi belum dipasang: GitHub → Actions → Deploy functions / the function is not deployed yet: GitHub → Actions → Deploy functions" : why.message);
  }
  if (data?.error) throw new Error(String(data.error));
  if (!data?.layout) throw new Error("tiada susun atur dipulangkan / no layout came back");
  return { layout: data.layout, removed: data.removed || [], hasWords: data.has_words === true, model: data.model || "" };
}
