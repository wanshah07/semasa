import { BUCKETS, errText, supabase } from "./SupabaseClient";

export const IMAGE_TYPES = ["image/png", "image/jpeg", "image/webp", "image/gif"];
export const MAX_BYTES = 50 * 1024 * 1024;

export function safeName(name) {
  return name.normalize("NFKD").replace(/[^\w.\-]+/g, "-").replace(/-+/g, "-").slice(-80);
}

/** Why a file cannot be a reference, or "" when it can. */
export function refusal(file) {
  if (!IMAGE_TYPES.includes(file.type)) return `Jenis fail ${file.type || "tidak dikenali"} tidak disokong.`;
  if (file.size > MAX_BYTES) return "Fail melebihi 50 MB.";
  return "";
}

/** Upload one reference picture under <uid>/ (the storage policy allows nothing else). */
export async function uploadReference(user, file) {
  const path = `${user.id}/${Date.now()}-${Math.random().toString(36).slice(2, 7)}-${safeName(file.name)}`;
  const up = await supabase.storage.from(BUCKETS.reference).upload(path, file, { contentType: file.type, upsert: false });
  if (up.error) throw new Error(errText(up.error));
  const { data } = supabase.storage.from(BUCKETS.reference).getPublicUrl(path);
  return { url: data.publicUrl, path };
}

export async function removeReference(path) {
  if (path) await supabase.storage.from(BUCKETS.reference).remove([path]);
}
