/* ws.regulab Studio's card catalogue in the page: the twelve templates, the mascot poses and Wan's own photographs
   (rules/cards.json, shared with backend/semasa/cards_library.py). The files are in web/public/cards/, served with the
   site and, for the worker, from the same checkout, so the preview and the render load the same bytes. */
import CARDS from "../../../../rules/cards.json";

const BASE = `${import.meta.env.BASE_URL}cards/`;

export const TEMPLATES = CARDS.templates;
export const templateOf = (k) => TEMPLATES.find((x) => x.k === k) || null;
export const MASCOTS = CARDS.mascots.map((m) => ({ ...m, url: BASE + m.file }));
export const GROUNDS = CARDS.grounds.map((g) => ({ ...g, url: BASE + g.file }));
export const groundOf = (k) => GROUNDS.find((g) => g.k === k) || null;

/** Studio's default ground for a post: its domain (ws.regulab) or its angle (LinkedIn). A token for the bg field. */
export function defaultGround(post) {
  if (!post) return "";
  const k = post.stream === "linkedin"
    ? (CARDS.ground_by_angle[String(post.angle || "").trim().toUpperCase()] || CARDS.ground_default_linkedin)
    : CARDS.ground_by_domain[post.domain];
  return k && groundOf(k) ? `lib:${k}` : "";
}

/** What a ground is the default for: the ws.regulab domains and LinkedIn angles that draw it when nobody chose one. */
export function groundUses(k) {
  return {
    domains: Object.entries(CARDS.ground_by_domain).filter(([, g]) => g === k).map(([d]) => d),
    angles: Object.entries(CARDS.ground_by_angle).filter(([, g]) => g === k).map(([a]) => a),
    linkedinDefault: CARDS.ground_default_linkedin === k,
  };
}

/** The note field's label for a template: what that design actually draws (Studio's cardPanel), or "" for none. */
export function noteLabel(k, t) {
  const tpl = templateOf(k);
  if (!tpl || !tpl.uses.includes("note")) return "";
  if (tpl.note) return t(tpl.note, tpl.noteEn);
  const L = CARDS.note_label;
  return CARDS.note_label.bubble_templates.includes(k) ? t(L.bubble, L.bubbleEn) : t(L.default, L.defaultEn);
}

/** A bg token as a drawable address in this page: "lib:g_x" → the photograph, a media id / "post_image" → `media`. */
export function bgUrlOf(token, { mediaUrl = () => "", postImage = "" } = {}) {
  if (!token || token === "none") return "";
  if (token.startsWith("lib:")) return groundOf(token.slice(4))?.url || "";
  if (token === "post_image") return postImage || "";
  return mediaUrl(token) || "";
}
