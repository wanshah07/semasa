/* Motion (Wan, 23 Oct 2026): a motion-graphics video from an idea or a link, written by the AI as a HyperFrames composition
   and rendered on the runner (backend/semasa/motion.py, semasa_motions). Pure helpers, tested in motion.test.mjs. */

export const RESOLUTIONS = {
  portrait: { w: 1080, h: 1920, bm: "Menegak 9:16 (Reels, TikTok, Shorts)", en: "Portrait 9:16 (Reels, TikTok, Shorts)" },
  square: { w: 1080, h: 1080, bm: "Segi empat 1:1 (Instagram, LinkedIn)", en: "Square 1:1 (Instagram, LinkedIn)" },
  landscape: { w: 1920, h: 1080, bm: "Melintang 16:9 (YouTube, LinkedIn)", en: "Landscape 16:9 (YouTube, LinkedIn)" },
};
export const SECONDS = { min: 3, max: 60, default: 12 };
export const STATUS_WORDS = {
  pending: ["Menunggu", "Waiting"], working: ["Sedang dibuat", "Being made"], done: ["Siap", "Done"], error: ["Ralat", "Error"],
};

/** Clamp the seconds a brief asks for to what the table accepts. */
export function clampSeconds(v) {
  const n = Math.round(Number(v));
  if (!Number.isFinite(n)) return SECONDS.default;
  return Math.min(SECONDS.max, Math.max(SECONDS.min, n));
}

/** The row to insert from the form, or {error} when the form is not enough: a brief or a link, one of them. */
export function motionRow({ brief = "", url = "", stream = "regulab", resolution = "portrait", seconds = SECONDS.default, styleRepoId = "", aiBackground = false } = {}, userId = null) {
  const b = String(brief || "").trim();
  const u = String(url || "").trim();
  if (!b && !u) return { error: "empty" };
  if (u && !/^https?:\/\/\S+$/.test(u)) return { error: "url" };
  return {
    row: {
      brief: b.slice(0, 2000), source_url: u, stream: stream === "linkedin" ? "linkedin" : "regulab",
      resolution: RESOLUTIONS[resolution] ? resolution : "portrait", seconds: clampSeconds(seconds), status: "pending",
      style_repo_id: styleRepoId || null, ai_background: !!aiBackground, created_by: userId,
    },
  };
}

/** What the card shows under the title: the brief, else the link. */
export function motionLabel(r) {
  return (r?.title || r?.brief || r?.source_url || "").trim();
}

/** Errors and warnings from the stored check report, errors first. */
export function checkItems(r) {
  const rep = r?.check_report || {};
  return [...(rep.errors || []).map((e) => ({ ...e, level: "error" })), ...(rep.warnings || []).map((w) => ({ ...w, level: "warning" }))];
}

export const fmtBytes = (n) => (n >= 1_048_576 ? `${(n / 1_048_576).toFixed(1)} MB` : n >= 1024 ? `${Math.round(n / 1024)} KB` : `${n || 0} B`);

/** The motion repos a video may take its look from: library rows filed under motion (Wan's own filing first), read or not. */
export function styleRepos(libraryRows) {
  return (libraryRows || []).filter((r) => r.category === "motion" && r.status !== "error")
    .sort((a, b) => (b.category_by === "wan") - (a.category_by === "wan") || String(a.name || a.full_name).localeCompare(String(b.name || b.full_name)));
}

/** The row to insert into Pustaka repo for a motion repo added from the Motion form: filed under motion by Wan himself. */
export function motionRepoRow(url, userId = null) {
  const m = /^https?:\/\/(?:www\.)?github\.com\/([\w.-]+)\/([\w.-]+?)(?:\.git)?(?:[/#?].*)?$/i.exec(String(url || "").trim());
  if (!m) return null;
  return { url: `https://github.com/${m[1]}/${m[2]}`, full_name: `${m[1]}/${m[2]}`, note: "motion style", category: "motion",
    category_by: "wan", status: "pending", created_by: userId };
}

/** The motion row for an idea: its headline, what Wan wrote on it and what the bot read, in the idea's own voice and size. Returns
    null for an idea with nothing to say. A short vertical video, 12 s, is the default: the idea becomes one scroll-stopping clip. */
export function motionFromIdea(idea, userId = null) {
  const title = String(idea?.source_title || "").trim();
  const note = String(idea?.note || "").trim();
  const summary = String(idea?.source_summary || idea?.brief?.source?.summary || "").trim();
  const brief = [title, note && `Wan: ${note}`, summary].filter(Boolean).join("\n").slice(0, 1900);
  if (!brief) return null;
  const url = /^https?:\/\/\S+$/.test(String(idea?.source_url || "")) ? idea.source_url : "";
  return { brief, source_url: url, stream: idea?.stream === "linkedin" ? "linkedin" : "regulab", resolution: "portrait", seconds: 12,
    status: "pending", idea_id: idea.id, ai_background: false, created_by: userId };
}
