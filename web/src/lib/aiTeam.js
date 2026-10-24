/* The AI team in the page (Wan, 23 Oct 2026): every gateway is one Wanshah robot, each with a state and the jobs it does.
   Rows are semasa_api_status (the probe) and semasa_api_usage (every AI call); the router's own decision is
   settings.ai_team_state (backend/semasa/ai_team.py), and settings.ai_team holds Wan's pins. Pure functions, tested in
   aiTeam.test.mjs. The ROBOTS table here mirrors the backend's: one slug, one robot, in both. */

export const ROBOTS = {
  rootsys: { robot: "W1", name: "Wanshah 1", tone: "afiq", does: ["read", "write"] },
  mireld: { robot: "W2", name: "Wanshah 2", tone: "mireld", does: ["read", "write"] },
  kiosapi: { robot: "W3", name: "Wanshah 3", tone: "kios", does: ["read", "write", "read_image", "make_image"] },
};
// shown in this order, like halal-executive: Wanshah 1, then 3, then 2
export const ORDER = ["rootsys", "kiosapi", "mireld"];
export const DOES = {
  read: ["Baca", "Read"], write: ["Tulis", "Write"], read_image: ["Baca gambar", "Read image"], make_image: ["Buat gambar", "Make image"],
};
export const JOBS = {
  reader: ["Penulis teks", "Text writer"], motion: ["Penulis motion", "Motion writer"], image_reader: ["Pembaca gambar", "Picture reader"], image_gen: ["Pelukis", "Picture maker"],
};
const ACTIVE_MS = 3 * 3600_000;
const STALE_MS = 13 * 3600_000;

/** A robot for a status row's slug: the named three, else a guest robot named after the host. */
export function robotOf(slug, row) {
  if (ROBOTS[slug]) return { slug, ...ROBOTS[slug] };
  const host = (row?.base_url || slug || "").replace(/^https?:\/\//, "").split("/")[0];
  return { slug, robot: "W?", name: row?.name || host || slug, tone: "guest", does: row?.role === "image" ? ["make_image"] : ["read", "write"] };
}

/** active = did real work in the last 3 h (a usage row that was ok) or the probe just answered; standby = reachable but idle;
    offline = unreachable, key refused, no key, or not checked in 13 h. */
export function stateOf(row, usageRows = [], now = Date.now()) {
  if (!row || !row.key_set) return "offline";
  if (row.checked_at && now - new Date(row.checked_at).getTime() > STALE_MS) return "offline";
  if (!row.reachable || row.key_ok === false) return "offline";
  if (row.chat_ok === false) return "offline";
  const last = (usageRows || []).reduce((m, u) => (u.gateway === row.slug && u.ok && u.area !== "probe" ? Math.max(m, new Date(u.created_at).getTime()) : m), 0);
  return now - last < ACTIVE_MS ? "active" : "standby";
}

/** Every robot the page should draw: the three named ones always (a missing row is an offline robot with no key), plus any
    other gateway the probe wrote. */
export function teamCards(statusRows, usageRows = [], now = Date.now()) {
  const bySlug = Object.fromEntries((statusRows || []).map((r) => [r.slug, r]));
  const slugs = [...ORDER, ...Object.keys(bySlug).filter((s) => !ORDER.includes(s)).sort()];
  return slugs.map((slug) => {
    const row = bySlug[slug] || null;
    const r = robotOf(slug, row);
    return { ...r, row, state: stateOf(row, usageRows, now), configured: !!row?.key_set };
  });
}

/** What the router decided, from settings.ai_team_state: {chosen, backup, order, skipped, pin, why, at} for a job. */
export function decisionOf(state, job = "reader") {
  const s = (state || {})[job] || {};
  return { chosen: s.chosen || null, backup: s.backup || null, order: s.order || [], skipped: s.skipped || [], pin: s.pin || null, why: s.why || "", at: (state || {}).at || "" };
}

/** The pin to save for a job, or null for auto. */
export function pinFor(team, job) {
  const p = (team || {}).pins?.[job];
  return p && p.gateway ? { gateway: p.gateway, model: p.model || "" } : null;
}

/** settings.ai_team with one job's pin changed; everything else untouched. */
export function withPin(team, job, pin) {
  const pins = { ...((team || {}).pins || {}) };
  pins[job] = pin && pin.gateway ? { gateway: pin.gateway, model: pin.model || "" } : null;
  return { ...(team || {}), pins };
}

/** The models a robot may be pinned to for a job: what its probe listed, the configured one first; image models for the
    painter, text models for the writer (the router refuses an image model on a text job, so the page does not offer it). */
const IMAGE_RE = /image|dall-?e|flux|stable-?diffusion|sdxl|imagen|seedream|sora|veo|kling|wan2|hunyuan/i;
export function modelsFor(row, job) {
  const list = [...new Set([row?.model, ...(row?.models || [])].filter(Boolean))];
  const want = job === "image_gen" ? (m) => IMAGE_RE.test(m) : (m) => !IMAGE_RE.test(m);   // reader, motion, image_reader: chat models
  const ok = list.filter(want);
  return ok.length ? ok : list;
}

/** Which robots may take a job at all (the text jobs, reader and motion, take any robot that writes). */
export function robotsFor(cards, job) {
  const need = job === "image_gen" ? "make_image" : job === "image_reader" ? "read_image" : "write";
  return cards.filter((c) => c.does.includes(need) || (job === "image_reader" && c.does.includes("read")));
}

export const fmtMs = (ms) => (ms == null ? "—" : ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${ms} ms`);
