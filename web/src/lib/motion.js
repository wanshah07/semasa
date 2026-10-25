/* Motion (Wan, 23 Oct 2026): a motion-graphics video from an idea or a link, written by the AI as a HyperFrames composition
   and rendered on the runner (backend/semasa/motion.py, semasa_motions). Pure helpers, tested in motion.test.mjs. */

export const RESOLUTIONS = {
  portrait: { w: 1080, h: 1920, bm: "Menegak 9:16 (Reels, TikTok, Shorts)", en: "Portrait 9:16 (Reels, TikTok, Shorts)" },
  square: { w: 1080, h: 1080, bm: "Segi empat 1:1 (Instagram, LinkedIn)", en: "Square 1:1 (Instagram, LinkedIn)" },
  landscape: { w: 1920, h: 1080, bm: "Melintang 16:9 (YouTube, LinkedIn)", en: "Landscape 16:9 (YouTube, LinkedIn)" },
};
export const SECONDS = { min: 3, max: 60, default: 12 };
/* the words on screen (Wan, 24 Oct 2026: "choice for english, malay, or english + malay version") */
export const LANGUAGES = [["bm", "Bahasa Malaysia"], ["en", "English"], ["both", "BM + English"]];
/** The language a stream's film speaks by itself (Wan, 24 Oct 2026: "default in english for linkedin and english + malay
    for ws regulab"): LinkedIn in English, ws.regulab with the Malay line and the English line together. */
export const defaultLanguage = (stream) => (stream === "linkedin" ? "en" : "both");
const langOf = (v, stream) => (LANGUAGES.some(([k]) => k === v) ? v : defaultLanguage(stream));
/* the presenter and the voice (Wan, 24 Oct 2026: "add mascot looks like talking, and make sure got voice or audio") */
export const VOICES = [["male", "Lelaki", "Male"], ["female", "Perempuan", "Female"], ["off", "Tiada suara", "No voice"]];
export const DEFAULT_MASCOT = "wave";
const voiceOf = (v) => (VOICES.some(([k]) => k === v) ? v : "male");
export const STATUS_WORDS = {
  pending: ["Menunggu", "Waiting"], working: ["Sedang dibuat", "Being made"], done: ["Siap", "Done"], error: ["Ralat", "Error"],
};

/** Clamp the seconds a brief asks for to what the table accepts. */
export function clampSeconds(v) {
  const n = Math.round(Number(v));
  if (!Number.isFinite(n)) return SECONDS.default;
  return Math.min(SECONDS.max, Math.max(SECONDS.min, n));
}

/* Wan's saved way of making a motion video (Wan, 24 Oct 2026: "save the skill to create and apply to all idea if I need"):
   settings.motion.defaults, saved from the Motion form, read whenever an idea or a post draft is made into a video. */
export const MOTION_DEFAULTS = { language: "", voice: "male", mascot: true, resolution: "portrait", seconds: SECONDS.default, aiBackground: false, styleRepoId: "" };
/** The saved defaults over the built-in ones; an empty language means "the stream's own". */
export function motionDefaults(settings) {
  const d = (settings || {}).motion?.defaults;
  return { ...MOTION_DEFAULTS, ...(d && typeof d === "object" ? d : {}) };
}
/** settings.motion with the form saved as the defaults; everything else in it (the prompt) untouched. */
export function withDefaults(motionSettings, form) {
  const d = { language: form.language || "", voice: voiceOf(form.voice), mascot: form.mascot !== false, resolution: RESOLUTIONS[form.resolution] ? form.resolution : "portrait",
    seconds: clampSeconds(form.seconds), aiBackground: !!form.aiBackground, styleRepoId: form.styleRepoId || "" };
  return { ...(motionSettings || {}), defaults: d };
}
/** A cache-busting address for a video that was remade under the same path (the browser kept the first MP4 otherwise). */
export const freshUrl = (url, stamp) => (url ? `${url}${url.includes("?") ? "&" : "?"}v=${encodeURIComponent(stamp || "")}` : url);

/** The row to insert from the form, or {error} when the form is not enough: a brief or a link, one of them. */
export function motionRow({ brief = "", url = "", stream = "regulab", resolution = "portrait", seconds = SECONDS.default, styleRepoId = "", aiBackground = false, language = "", voice = "male", mascot = true } = {}, userId = null) {
  const b = String(brief || "").trim();
  const u = String(url || "").trim();
  if (!b && !u) return { error: "empty" };
  if (u && !/^https?:\/\/\S+$/.test(u)) return { error: "url" };
  const st = stream === "linkedin" ? "linkedin" : "regulab";
  return {
    row: {
      brief: b.slice(0, 2000), source_url: u, stream: st, language: langOf(language, st),
      resolution: RESOLUTIONS[resolution] ? resolution : "portrait", seconds: clampSeconds(seconds), status: "pending",
      style_repo_id: styleRepoId || null, ai_background: !!aiBackground, created_by: userId,
      voice: voiceOf(voice), mascot: mascot ? DEFAULT_MASCOT : "",
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
export function motionFromIdea(idea, userId = null, defaults = null, language = "") {
  const d = { ...MOTION_DEFAULTS, ...(defaults || {}), ...(LANGUAGES.some(([k]) => k === language) ? { language } : {}) };
  const title = String(idea?.source_title || "").trim();
  const note = String(idea?.note || "").trim();
  const summary = String(idea?.source_summary || idea?.brief?.source?.summary || "").trim();
  const brief = [title, note && `Wan: ${note}`, summary].filter(Boolean).join("\n").slice(0, 1900);
  if (!brief) return null;
  const url = /^https?:\/\/\S+$/.test(String(idea?.source_url || "")) ? idea.source_url : "";
  const stream = idea?.stream === "linkedin" ? "linkedin" : "regulab";
  return { brief, source_url: url, stream, language: langOf(d.language, stream), resolution: RESOLUTIONS[d.resolution] ? d.resolution : "portrait",
    seconds: clampSeconds(d.seconds), status: "pending", idea_id: idea.id, ai_background: !!d.aiBackground,
    style_repo_id: d.styleRepoId || null, voice: voiceOf(d.voice), mascot: d.mascot !== false ? DEFAULT_MASCOT : "", created_by: userId };
}

/** The motion row for a post draft (Wan, 24 Oct 2026: "make sure all draft idea have option to be motion"): the slides' titles and
    points when the post has them, else its caption in the post's own language; the post's language and stream carry over. */
export function motionFromPost(post, userId = null, defaults = null, language = "") {
  const d = { ...MOTION_DEFAULTS, ...(defaults || {}), ...(LANGUAGES.some(([k]) => k === language) ? { language } : {}) };
  const lang = post?.lang === "en" ? "en" : "bm";
  const slides = Array.isArray(post?.slides) ? post.slides : [];
  const fromSlides = slides.map((s) => [String(s?.title || "").trim(), ...(Array.isArray(s?.points) ? s.points : []).map((p) => `- ${String(p || "").trim()}`)]
    .filter(Boolean).join("\n")).filter(Boolean).join("\n\n");
  const text = (post?.text || {})[lang] || {};
  const caption = String(text.facebook || text.instagram || text.threads || text.linkedin || Object.values(text)[0] || "").trim();
  const brief = (fromSlides || caption).slice(0, 1900);
  if (!brief) return null;
  const stream = post?.stream === "linkedin" ? "linkedin" : "regulab";
  return { brief, source_url: "", stream, language: d.language || lang, resolution: RESOLUTIONS[d.resolution] ? d.resolution : "portrait",
    seconds: clampSeconds(d.seconds), status: "pending", idea_id: post?.idea_id || null, ai_background: !!d.aiBackground,
    style_repo_id: d.styleRepoId || null, voice: voiceOf(d.voice), mascot: d.mascot !== false ? DEFAULT_MASCOT : "", created_by: userId };
}
