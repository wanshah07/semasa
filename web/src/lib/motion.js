/* Motion (Wan, 23 Oct 2026): a motion-graphics video from an idea or a link, written by the AI as a HyperFrames composition
   and rendered on the runner (backend/semasa/motion.py, semasa_motions). Pure helpers, tested in motion.test.mjs. */

import { styleOf } from "./motionStyles.js";
import { validEffects, assetModeOf } from './motionEffects.js';

export const RESOLUTIONS = {
  portrait: { w: 1080, h: 1920, bm: "Menegak 9:16 (Reels, TikTok, Shorts)", en: "Portrait 9:16 (Reels, TikTok, Shorts)" },
  square: { w: 1080, h: 1080, bm: "Segi empat 1:1 (Instagram, LinkedIn)", en: "Square 1:1 (Instagram, LinkedIn)" },
  landscape: { w: 1920, h: 1080, bm: "Melintang 16:9 (YouTube, LinkedIn)", en: "Landscape 16:9 (YouTube, LinkedIn)" },
};
export const SECONDS = { min: 30, max: 60, default: 30 };
/* the words on screen (Wan, 24 Oct 2026: "choice for english, malay, or english + malay version") */
export const LANGUAGES = [["bm", "Bahasa Malaysia"], ["en", "English"], ["both", "BM + English"]];
/** Current generated explainer default: English for both streams; explicit BM/bilingual remains supported with Edge. */
export const defaultLanguage = () => "en";
const langOf = (v, stream) => (LANGUAGES.some(([k]) => k === v) ? v : defaultLanguage(stream));
/* the voice (Wan, 24 Oct 2026); the talking mascot was removed on 25 Oct 2026: "remove mascot usage" */
export const VOICES = [["kitten", "VoiceStudio KittenTTS (EN)", "VoiceStudio KittenTTS (EN)"], ["male", "Lelaki", "Male"], ["female", "Perempuan", "Female"], ["off", "Tiada suara", "No voice"]];
const voiceOf = (v) => (VOICES.some(([k]) => k === v) ? v : "kitten");
export const designOf = v => v === 'continuous-line' ? v : 'bright-editorial';
export function resolveLanguageVoice(language, voice, stream) {
  const lang = langOf(language, stream);
  const chosen = voiceOf(voice);
  return { language: lang, voice: chosen === 'kitten' && lang !== 'en' ? 'female' : chosen };
}
const evidenceOf = source => ({...Object.fromEntries(['source_url', 'reference_urls', 'source_name', 'angle', 'domain', 'citations', 'source_summary', 'trend_id', 'idea_id', 'id'].filter(k => source?.[k] != null).map(k => [k, source[k]])), ...(source?.brief?.source ? {structured_source:source.brief.source} : {})});
const motionOptions = d => ({ style: styleOf(d.style), mode: modeOf(d.mode), design: designOf(d.design), effects:validEffects(d.effects), effect_mode:d.effectMode === 'manual' ? 'manual' : 'auto', asset_mode:assetModeOf(d.assetMode), assets:d.assets || [], preferred_preview_music: {source:"user-reel", rights_status:"unverified", preview_only:true} });
export function motionVariantMatches(existing, wanted) {
  return !!wanted && ['pending', 'working', 'done'].includes(existing.status) &&
    existing.idea_id === wanted.idea_id && existing.language === wanted.language &&
    designOf(existing.options?.design) === designOf(wanted.options?.design) &&
    styleOf(existing.options?.style) === styleOf(wanted.options?.style) &&
    JSON.stringify(validEffects(existing.options?.effects)) === JSON.stringify(validEffects(wanted.options?.effects)) &&
    (existing.options?.effect_mode || 'auto') === (wanted.options?.effect_mode || 'auto') &&
    assetModeOf(existing.options?.asset_mode) === assetModeOf(wanted.options?.asset_mode) &&
    JSON.stringify(existing.options?.assets || []) === JSON.stringify(wanted.options?.assets || []) &&
    modeOf(existing.options?.mode) === modeOf(wanted.options?.mode) &&
    selectedSeconds(existing.seconds, existing.options?.mode) === wanted.seconds &&
    resolveLanguageVoice(existing.language, existing.voice).voice === wanted.voice;
}
export const STATUS_WORDS = {
  pending: ["Menunggu", "Waiting"], working: ["Sedang dibuat", "Being made"], done: ["Siap", "Done"], error: ["Ralat", "Error"],
};

/** Clamp the seconds a brief asks for to what the table accepts. */
export function clampSeconds(v) {
  if (v === "" || v == null) return SECONDS.default;
  const n = Math.round(Number(v));
  if (!Number.isFinite(n)) return SECONDS.default;
  return n > 30 ? 60 : 30;
}
export const modeOf = (v) => v === "teaser" ? "teaser" : "explainer";
export const selectedSeconds = (seconds, mode) => modeOf(mode) === "teaser" && Number(seconds) === 10 ? 10 : clampSeconds(seconds);

/* Wan's saved way of making a motion video (Wan, 24 Oct 2026: "save the skill to create and apply to all idea if I need"):
   settings.motion.defaults, saved from the Motion form, read whenever an idea or a post draft is made into a video. */
export const MOTION_DEFAULTS = { effectMode:'auto', effects:['B04'], assetMode:'auto', language: "en", voice: "kitten", design: "bright-editorial", previewMusic: "user-reel", style: "bright-education", mode: "explainer", resolution: "portrait", seconds: SECONDS.default, aiBackground: false, styleRepoId: "" };
/** The saved defaults over the built-in ones; an empty language means "the stream's own". */
export function motionDefaults(settings) {
  const d = (settings || {}).motion?.defaults;
  const merged = { ...MOTION_DEFAULTS, ...(d && typeof d === "object" ? d : {}) };
  return { ...merged, ...resolveLanguageVoice(merged.language, merged.voice), design: designOf(merged.design), mode: modeOf(merged.mode), seconds: selectedSeconds(merged.seconds, merged.mode) };
}
/** settings.motion with the form saved as the defaults; everything else in it (the prompt) untouched. */
export function withDefaults(motionSettings, form) {
  const d = { effects:validEffects(form.effects), effectMode:form.effectMode === 'manual' ? 'manual' : 'auto', assetMode:'auto', ...resolveLanguageVoice(form.language, form.voice), design: designOf(form.design), previewMusic: "user-reel", style: styleOf(form.style), mode: modeOf(form.mode), resolution: RESOLUTIONS[form.resolution] ? form.resolution : "portrait",
    seconds: selectedSeconds(form.seconds, form.mode), aiBackground: !!form.aiBackground, styleRepoId: form.styleRepoId || "" };
  return { ...(motionSettings || {}), defaults: d };
}
/** A cache-busting address for a video that was remade under the same path (the browser kept the first MP4 otherwise). */
export const freshUrl = (url, stamp) => (url ? `${url}${url.includes("?") ? "&" : "?"}v=${encodeURIComponent(stamp || "")}` : url);

/** The row to insert from the form, or {error} when the form is not enough: a brief or a link, one of them. */
export function motionRow({ brief = "", url = "", stream = "regulab", resolution = "portrait", seconds = SECONDS.default, styleRepoId = "", aiBackground = false, language = "", voice = "kitten", design = "bright-editorial", style = "bright-education", mode = "explainer", effects=['B04'], effectMode='auto', assetMode='auto', assets=[] } = {}, userId = null) {
  const b = String(brief || "").trim();
  const u = String(url || "").trim();
  if (!b && !u) return { error: "empty" };
  if (u && !/^https?:\/\/\S+$/.test(u)) return { error: "url" };
  const st = stream === "linkedin" ? "linkedin" : "regulab";
  return {
    row: {
      brief: b.slice(0, 2000), source_url: u, stream: st, language: langOf(language, st),
      resolution: RESOLUTIONS[resolution] ? resolution : "portrait", seconds: selectedSeconds(seconds, mode), status: "pending",
      options: motionOptions({style, mode, design, effects, effectMode, assetMode, assets}), style_repo_id: styleRepoId || null, ai_background: !!aiBackground, created_by: userId,
      ...resolveLanguageVoice(language, voice, st), mascot: "",
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
    null for an idea with nothing to say. A vertical explainer, 30 s, is the default: the idea becomes one scroll-stopping clip. */
export function motionFromIdea(idea, userId = null, defaults = null, language = "") {
  const d = { ...MOTION_DEFAULTS, ...(defaults || {}), ...(LANGUAGES.some(([k]) => k === language) ? { language } : {}) };
  const title = String(idea?.source_title || "").trim();
  const note = String(idea?.note || "").trim();
  const summary = String(idea?.source_summary || idea?.brief?.source?.summary || "").trim();
  const brief = [title, note && `Wan: ${note}`, summary].filter(Boolean).join("\n").slice(0, 1900);
  const url = /^https?:\/\/\S+$/.test(String(idea?.source_url || "")) ? idea.source_url : "";
  if (!brief && !url) return null;
  const stream = idea?.stream === "linkedin" ? "linkedin" : "regulab";
  return { brief, source_url: url, stream, language: langOf(d.language, stream), resolution: RESOLUTIONS[d.resolution] ? d.resolution : "portrait",
    seconds: selectedSeconds(d.seconds, d.mode), status: "pending", idea_id: idea.id || null, ai_background: !!d.aiBackground,
    options: { ...motionOptions(d), evidence: evidenceOf(idea) }, style_repo_id: d.styleRepoId || null, ...resolveLanguageVoice(d.language, d.voice, stream), mascot: "", created_by: userId };
}

/** The motion row for a post draft (Wan, 24 Oct 2026: "make sure all draft idea have option to be motion"): the slides' titles and
    points when the post has them, else its caption in the post's own language; the post's language and stream carry over. */
export function motionFromPost(post, userId = null, defaults = null, language = "") {
  const d = { ...MOTION_DEFAULTS, ...(defaults || {}), ...(LANGUAGES.some(([k]) => k === language) ? { language } : {}) };
  const lang = ["en", "bm"].includes(post?.lang) ? post.lang : (post?.text?.en ? "en" : "bm");
  const slides = Array.isArray(post?.slides) ? post.slides : [];
  const fromSlides = slides.map((s) => [String(s?.title || "").trim(), ...(Array.isArray(s?.points) ? s.points : []).map((p) => `- ${String(p || "").trim()}`)]
    .filter(Boolean).join("\n")).filter(Boolean).join("\n\n");
  const text = (post?.text || {})[lang] || post?.text?.en || post?.text?.bm || {};
  const caption = String(text.facebook || text.instagram || text.threads || text.linkedin || Object.values(text)[0] || "").trim();
  const brief = (fromSlides || caption).slice(0, 1900);
  if (!brief) return null;
  const stream = post?.stream === "linkedin" ? "linkedin" : "regulab";
  return { brief, source_url: post?.source_url || "", stream, language: d.language || lang, resolution: RESOLUTIONS[d.resolution] ? d.resolution : "portrait",
    seconds: selectedSeconds(d.seconds, d.mode), status: "pending", idea_id: post?.idea_id || null, ai_background: !!d.aiBackground,
    options: { ...motionOptions(d), evidence: evidenceOf(post) }, style_repo_id: d.styleRepoId || null, ...resolveLanguageVoice(d.language, d.voice, stream), mascot: "", created_by: userId };
}
