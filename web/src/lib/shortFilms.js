/* Short-film categories on the page (Wan, 22 Nov 2026: "Untuk short film ada kan dua kategori - kisah keluarga halal dan cats, dan
   kategori ini boleh ditambah"). The built-in categories are rules/short_films.json, the one file the film scripts read too
   (backend/semasa/short_films.py); Wan's own are the settings row `short_films` ({categories, hidden}), merged over them by id.
   A built-in category is never replaced by one of his (its hand-written script goes with it): it can only be hidden from the list.
   Plain functions, so shortFilms.test.mjs runs them in Node. The film script is the judge: it cleans the row again. */
import RULES from "../../../rules/short_films.json";
import { bi } from "./bi";

export const LIMITS = RULES.limits;
export const VOICES = RULES.voices;
export const BUILT_IN = RULES.categories.map((c) => c.id);
export const OWN_WORKFLOW = "nexabot-cat-film.yml";
const MODES = ["narrator", "in_prompt"];
const ID_RE = /^[a-z0-9][a-z0-9-]{1,39}$/;
const chars = (s) => [...String(s ?? "")].length;
const isObj = (v) => v && typeof v === "object" && !Array.isArray(v);

/** One line of plain text, or "" when it is not text or is over the limit (refused whole, never cut: the worker does the same). */
const line = (value, limit) => {
  if (typeof value !== "string") return "";
  // eslint-disable-next-line no-control-regex
  const text = value.replace(/[\u0000-\u001f\u007f\u2028\u2029]+/g, " ").split(/\s+/).filter(Boolean).join(" ");
  return chars(text) <= limit ? text : "";
};
const pair = (value, limit) => {
  const bm = isObj(value) ? line(value.bm, limit) : line(value, limit);
  const en = isObj(value) ? line(value.en, limit) : bm;
  return { bm: bm || en, en: en || bm };
};

function cleanCast(raw) {
  const people = [];
  for (const c of Array.isArray(raw) ? raw : []) {
    const person = { name: line(c?.name, LIMITS.cast_name), look: line(c?.look, LIMITS.look) };
    if (!person.name || chars(person.look) < 20) return null;
    people.push(person);
  }
  if (people.length < 1 || people.length > LIMITS.cast) return null;
  if (new Set(people.map((p) => p.name.toLowerCase())).size !== people.length) return null;
  return people;
}

const sceneCount = (v) => {
  const n = Number.parseInt(v, 10);
  return Math.max(LIMITS.scenes_min, Math.min(LIMITS.scenes_max, Number.isFinite(n) ? n : 4));
};

/** A whole category, or null (mirrors short_films.clean_category). Wan's own one is always narrated and has no script. */
export function cleanCategory(raw, builtIn = false) {
  if (!isObj(raw) || !ID_RE.test(String(raw.id || ""))) return null;
  const name = pair(raw.name, LIMITS.name);
  const cast = cleanCast(raw.cast);
  const setting = line(raw.setting, LIMITS.setting);
  const style = line(raw.style, LIMITS.style);
  if (!name.bm || !cast || chars(setting) < 10 || chars(style) < 10) return null;
  const v = isObj(raw.voice) ? raw.voice : {};
  const mode = builtIn && MODES.includes(v.mode) ? v.mode : "narrator";
  const voice = { mode, name: VOICES.includes(v.name) ? v.name : (mode === "narrator" ? VOICES[0] : ""), notes: line(v.notes, LIMITS.voice_notes) };
  const out = { id: String(raw.id), name, about: pair(raw.about, LIMITS.about), cast, setting, style, voice,
    scene_count: sceneCount(raw.scene_count), workflow: OWN_WORKFLOW };
  if (builtIn) {
    const scenes = Array.isArray(raw.script?.scenes) ? raw.script.scenes.filter((s) => s && typeof s.prompt === "string" && s.prompt) : [];
    if (typeof raw.script?.sheet_prompt === "string" && scenes.length) { out.script = true; out.scene_count = scenes.length; }
    for (const k of ["workflow", "sheet", "file"]) if (typeof raw[k] === "string" && raw[k]) out[k] = raw[k];
  }
  return out;
}

/** { categories, hidden, defaultId }: the built-in ones (builtIn) then Wan's (own), each with `hidden` (mirrors short_films.library). */
export function shortFilmLibrary(value) {
  const v = isObj(value) ? value : {};
  const hidden = new Set((Array.isArray(v.hidden) ? v.hidden : []).filter((x) => typeof x === "string"));
  const out = RULES.categories.map((c) => cleanCategory(c, true)).filter(Boolean).map((c) => ({ ...c, builtIn: true }));
  let kept = 0;
  for (const raw of Array.isArray(v.categories) ? v.categories : []) {
    const item = cleanCategory(raw);
    if (!item || kept >= LIMITS.own) continue;
    const at = out.findIndex((x) => x.id === item.id);
    if (at >= 0) { if (out[at].own) out[at] = { ...item, own: true }; continue; }
    kept += 1;
    out.push({ ...item, own: true });
  }
  for (const c of out) c.hidden = hidden.has(c.id);
  const defaultId = out.some((c) => c.id === v.default) ? v.default : RULES.default;
  return { categories: out, hidden: [...hidden].sort(), defaultId };
}

/** A new id from a name: "Arnab di kebun" becomes "arnab-di-kebun", never one already taken (built-in ids included). */
export function newId(name, taken = []) {
  const base = String(name || "").toLowerCase().normalize("NFKD").replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 32) || "filem";
  let id = base.length < 2 ? `${base}-1` : base;
  for (let n = 2; taken.includes(id); n += 1) id = `${base}-${n}`;
  return id;
}

/** "Name: look" lines from the form's text box into a cast; a line without a colon is a name with no look (refused later). */
export function castFromText(text) {
  return String(text || "").split(/\n+/).map((l) => l.trim()).filter(Boolean).map((l) => {
    const at = l.search(/[:：]/);
    return at < 0 ? { name: l, look: "" } : { name: l.slice(0, at).trim(), look: l.slice(at + 1).trim() };
  });
}

/** Why the Add form cannot be saved yet, or "". */
export function categoryProblem(entry) {
  if (!line(entry?.name?.bm ?? entry?.name, LIMITS.name)) return bi("Beri nama kategori (paling banyak {n} aksara).", "Give the category a name (at most {n} characters).").replace("{n}", LIMITS.name);
  if (BUILT_IN.includes(entry?.id)) return bi("Nama itu sudah digunakan oleh kategori terbina.", "That name is already used by a built-in category.");
  const cast = Array.isArray(entry?.cast) ? entry.cast : [];
  if (!cast.length) return bi("Tulis sekurang-kurangnya satu watak, satu baris: Nama: rupanya.", "Write at least one character, one line each: Name: their look.");
  if (cast.length > LIMITS.cast) return bi("Paling banyak {n} watak.", "At most {n} characters.").replace("{n}", LIMITS.cast);
  for (const c of cast) {
    if (!line(c?.name, LIMITS.cast_name)) return bi("Setiap watak perlu nama sebelum tanda titik bertindih.", "Every character needs a name before the colon.");
    const look = String(c?.look || "").trim();
    if (chars(look) < 20) return bi("Terangkan rupa {w} dengan tepat: warna, saiz, pakaian, ciri.", "Describe {w}'s look exactly: colours, size, clothes, features.").replace("{w}", c.name);
    if (chars(look) > LIMITS.look) return bi("Rupa {w} terlalu panjang.", "{w}'s look is too long.").replace("{w}", c.name);
  }
  if (new Set(cast.map((c) => String(c.name).trim().toLowerCase())).size !== cast.length) return bi("Dua watak tidak boleh sama nama.", "Two characters cannot share a name.");
  if (chars(String(entry?.setting || "").trim()) < 10) return bi("Terangkan tempatnya (paling kurang 10 aksara).", "Describe the place (at least 10 characters).");
  if (chars(String(entry?.style || "").trim()) < 10) return bi("Terangkan gaya gambarnya (paling kurang 10 aksara).", "Describe the picture style (at least 10 characters).");
  return cleanCategory(entry) ? "" : bi("Kategori belum lengkap.", "The category is not complete yet.");
}

const valueOf = (value) => (isObj(value) ? value : {});

/** The settings value with one of Wan's categories saved into it. null when the entry is not whole or takes a built-in id. */
export function withCategory(value, entry) {
  const item = cleanCategory(entry);
  if (!item || BUILT_IN.includes(item.id)) return null;
  const v = valueOf(value);
  const list = (Array.isArray(v.categories) ? v.categories : []).filter((x) => x && x.id !== item.id);
  const { workflow, ...stored } = item; // eslint-disable-line no-unused-vars
  return { ...v, categories: [...list, stored] };
}

/** The settings value without Wan's category `id` (a built-in one cannot be removed this way: hide it instead). */
export function withoutCategory(value, id) {
  const v = valueOf(value);
  if (BUILT_IN.includes(id)) return v;
  return { ...v, categories: (Array.isArray(v.categories) ? v.categories : []).filter((x) => x && x.id !== id),
    hidden: (Array.isArray(v.hidden) ? v.hidden : []).filter((x) => x !== id) };
}

/** The settings value with `id` hidden from (or shown again in) the page's list. A hidden category can still be filmed by hand. */
export function withHidden(value, id, hide) {
  const v = valueOf(value);
  const now = (Array.isArray(v.hidden) ? v.hidden : []).filter((x) => typeof x === "string" && x !== id);
  return { ...v, hidden: hide ? [...now, id] : now };
}

/** How a category becomes a film: the workflow to run by hand and the inputs to give it. */
export function howToFilm(cat) {
  const wf = cat?.workflow || OWN_WORKFLOW;
  const inputs = wf === OWN_WORKFLOW ? `category = ${cat?.id}${cat?.script ? "" : ", topic = …"}` : `category = ${cat?.id}`;
  return { workflow: wf, inputs };
}
