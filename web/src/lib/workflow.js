/* The post's own record (supabase/021_studio_workflow.sql): `decisions` says who did what and when, `versions` keeps
   the words a post had before each rewrite, so nothing Wan wrote is ever lost to a revise or a restore.
   The worker writes the same shapes (backend/semasa/ideas.py revise_one). No imports: web/workflow.test.mjs. */

const WORDS = ["hook", "text", "citation"];

export function withDecision(post, action, note = "", now = Date.now()) {
  const d = { at: new Date(now).toISOString(), by: "page", action };
  if (String(note || "").trim()) d.note = String(note).trim().slice(0, 400);
  return [...(Array.isArray(post.decisions) ? post.decisions : []), d].slice(-50);
}

export function withVersion(post, why = "", now = Date.now()) {
  const v = Object.fromEntries(WORDS.map((k) => [k, post[k] ?? null]));
  return [...(Array.isArray(post.versions) ? post.versions : []), { ...v, at: new Date(now).toISOString(), why }].slice(-20);
}

/** The patch that puts version i back, keeping the words it replaces as a version of their own. */
export function restoreVersion(post, i, now = Date.now()) {
  const v = (post.versions || [])[i];
  if (!v) return null;
  const patch = Object.fromEntries(WORDS.filter((k) => v[k] !== undefined && v[k] !== null).map((k) => [k, v[k]]));
  return { ...patch, versions: withVersion(post, `before restoring the version of ${String(v.at || "").slice(0, 16)}`, now),
    decisions: withDecision(post, "restored version", String(v.at || ""), now) };
}
