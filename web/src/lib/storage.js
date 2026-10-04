import { BUCKETS, errText, supabase } from "./SupabaseClient";
import { tr } from "./i18n";
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
