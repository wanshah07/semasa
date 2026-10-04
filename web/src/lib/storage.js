import { BUCKETS, errText, supabase } from "./SupabaseClient";
import { tr } from "./i18n";
import { photoPath, photoToken } from "./photos";
import { transient } from "./upstream";

export const IMAGE_TYPES = ["image/png", "image/jpeg", "image/webp", "image/gif"];
export const MAX_BYTES = 50 * 1024 * 1024;

export function safeName(name) {
  return name.normalize("NFKD").replace(/[^\w.\-]+/g, "-").replace(/-+/g, "-").slice(-80);
}

/** Why a file cannot be a reference, or "" when it can. */
export function refusal(file) {
  if (!IMAGE_TYPES.includes(file.type)) {
    return tr("Jenis fail {type} tidak disokong.", "File type {type} is not supported.",
      { type: file.type || tr("tidak dikenali", "unknown") });
  }
  if (file.size > MAX_BYTES) return tr("Fail melebihi 50 MB.", "The file is over 50 MB.");
  return "";
}

/** Upload one reference picture under <uid>/ (the storage policy allows nothing else). A transient failure is retried
    (3 tries, 0.8 s then 2 s apart): the 520 Wan hit on 4 Oct was Supabase's edge blinking, and the same file went through a moment later. */
export async function uploadReference(user, file, { waits = [800, 2000] } = {}) {
  const path = `${user.id}/${Date.now()}-${Math.random().toString(36).slice(2, 7)}-${safeName(file.name)}`;
  let up;
  for (let i = 0; ; i++) {
    try {
      up = await supabase.storage.from(BUCKETS.reference).upload(path, file, { contentType: file.type, upsert: false });
    } catch (e) { up = { error: e }; }
    if (!up.error || !transient(up.error) || i >= waits.length) break;
    await new Promise((r) => setTimeout(r, waits[i]));
  }
  if (up.error) throw new Error(errText(up.error));
  const { data } = supabase.storage.from(BUCKETS.reference).getPublicUrl(path);
  return { url: data.publicUrl, path };
}

export async function removeReference(path) {
  if (path) await supabase.storage.from(BUCKETS.reference).remove([path]);
}

/* ---- speaker photos for the event poster ---- */

/** Any picture shrunk to a square-friendly JPEG no longer than `edge` on its long side: a phone photo is megabytes, a round slot of
    a few hundred pixels needs none of it. Falls back to the file as it is when the browser cannot decode it. */
export async function shrinkPhoto(file, edge = 720) {
  try {
    const bmp = await createImageBitmap(file, { imageOrientation: "from-image" });
    const k = Math.min(1, edge / Math.max(bmp.width, bmp.height));
    const c = document.createElement("canvas");
    c.width = Math.max(1, Math.round(bmp.width * k)); c.height = Math.max(1, Math.round(bmp.height * k));
    c.getContext("2d").drawImage(bmp, 0, 0, c.width, c.height);
    const blob = await new Promise((res) => c.toBlob(res, "image/jpeg", 0.88));
    return blob ? new File([blob], `${file.name.replace(/\.[^.]+$/, "") || "speaker"}.jpg`, { type: "image/jpeg" }) : file;
  } catch { return file; }
}

/** Upload one speaker's photo (shrunk) and return its slide token. */
export async function uploadSpeakerPhoto(user, file) {
  const why = refusal(file);
  if (why) throw new Error(why);
  const up = await uploadReference(user, await shrinkPhoto(file));
  return photoToken(up.path);
}

/** A token's address in the public reference bucket, for the editor's preview and thumbnails. */
export const photoUrl = (token) => (photoPath(token) ? supabase.storage.from(BUCKETS.reference).getPublicUrl(photoPath(token)).data.publicUrl : "");
