/* Import video on the page (Wan, 17 Nov 2026): the endpoint an outside agent sends a finished MP4 to, the keys that agent uses, and
   the list of what came in. The Edge Function is supabase/functions/semasa-import-video, the tables and the two key functions are
   supabase/087_video_import.sql, the worker is backend/semasa/video_import.py. This file is only what the card needs to show it:
   plain functions, so videoImport.test.mjs runs them in Node. Nothing here decides anything the function or the worker does not
   check again, and nothing says an import was approved: it is a DRAFT until Wan's own Approve click. */

export const FUNCTION_NAME = "semasa-import-video";
export const TOKEN_COLUMNS = "id,label,created_at,last_used_at,revoked_at";           // never the hash: the page cannot read it
export const IMPORT_COLUMNS = "id,status,source,token_label,error,note,post_id,created_at,updated_at";

/** The address the agent posts to, from the project's address. */
export const endpointUrl = (base) => `${String(base || "").replace(/\/+$/, "")}/functions/v1/${FUNCTION_NAME}`;

/** A ready curl example for an MP4 on disk. With no token (it is shown once, then gone) the placeholder is <token>. */
export function curlExample(base, token) {
  return [`curl -X POST "${endpointUrl(base)}" \\`,
    `  -H "Authorization: Bearer ${token || "<token>"}" \\`,
    `  -F "file=@film.mp4;type=video/mp4" \\`,
    `  -F "title=Notifikasi kosmetik" \\`,
    `  -F "caption=Satu ayat tentang apa yang filem ini jelaskan." \\`,
    `  -F "source=hermes" \\`,
    `  -F "idempotency_key=hermes-2026-11-18-01"`].join("\n");
}

/** The keys, newest first, each marked active or revoked. */
export function tokenRows(rows) {
  return [...(rows || [])].sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)))
    .map((r) => ({ ...r, active: !r.revoked_at }));
}

/** An import's state in words, BM first then English, and a tone. A finished import is a draft waiting for Wan; it is never said
    to be approved. */
export function importStatus(row) {
  const note = row?.note ? ` (${row.note})` : "";
  switch (row?.status) {
    case "done":
      return { tone: "ok", words: [`Draf post sudah dibuat, menunggu Lulus anda${note}`, `A draft post was made and waits for your Approve${note}`] };
    case "error":
      return { tone: "danger", words: [`Ditolak: ${row.error || "sebab tidak diketahui"}`, `Refused: ${row.error || "no reason given"}`] };
    case "working":
      return { tone: "muted", words: ["Sedang disemak", "Being checked"] };
    default:
      return { tone: "muted", words: ["Diterima, menunggu semakan (dalam beberapa minit)", "Received, waiting to be checked (within minutes)"] };
  }
}
