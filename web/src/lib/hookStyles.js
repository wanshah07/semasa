/* Hook styles made from screenshots (Wan, 6 Nov 2026: "add style hook bank, I can add screenshot and bot can analyze and create the
   hook and instruction to replace current instruction when select"). The page adds a style (a name and screenshots), the worker
   reads them (backend/semasa/hook_styles.py) and the writer is held to the style's shapes while it is selected, the way it is held
   to the built-in 25 (hook_bank.py). Pure helpers, tested in hookStyles.test.mjs. */

export const BUILTIN = "builtin";
export const MAX_IMAGES = 8;
export const MAX_SHAPES = 30;
export const FAMILIES = ["curiosity", "transform", "vulnerable", "bold", "relatable", "other"];

export const STATUS_WORDS = {
  new: ["Menunggu bot", "Waiting for the bot"],
  working: ["Sedang dibaca", "Reading"],
  ready: ["Sedia", "Ready"],
  error: ["Gagal", "Failed"],
};
export const STATUS_CLS = { new: "bg-warn/15 text-warn", working: "bg-accent/15 text-accent", ready: "bg-ok/15 text-ok", error: "bg-danger/15 text-danger" };

/** A style the writer can use: read, with at least one shape. */
export const isReady = (s) => s?.status === "ready" && Array.isArray(s.shapes) && s.shapes.some((x) => /___/.test(x?.text || ""));
/** A style still being made, which the page keeps asking about. */
export const isBusy = (s) => s?.status === "new" || s?.status === "working";

/** The id the writer will use by default: the saved one when that style is ready, else the built-in 25. */
export function activeId(setting, styles) {
  const id = String(setting?.id || "");
  return id && styles.some((s) => s.id === id && isReady(s)) ? id : BUILTIN;
}

/** The choices in a select: [value, label]. The first, "", means follow the default chosen in Tetapan. */
export function pickOptions(styles, t, setting) {
  const def = activeId(setting, styles);
  const nameOf = (id) => (id === BUILTIN ? t("25 bentuk terbina", "the built-in 25") : styles.find((s) => s.id === id)?.name || "?");
  return [["", t(`Ikut tetapan (${nameOf(def)})`, `Follow the setting (${nameOf(def)})`)], [BUILTIN, t("25 bentuk terbina", "The built-in 25")],
    ...styles.filter(isReady).map((s) => [s.id, s.name || t("Gaya tanpa nama", "Unnamed style")])];
}

/** The idea's brief with the chosen style set, or removed (nothing, or "" = follow the setting). */
export function withHookStyle(brief, id) {
  const next = { ...(brief || {}) };
  if (id) next.hook_style = id; else delete next.hook_style;
  return next;
}

/** One shape per line for the editor: "family | text", or just the text. */
export const shapesToText = (shapes) => (shapes || []).map((s) => (s.family && s.family !== "other" ? `${s.family} | ${s.text}` : s.text)).join("\n");

/** The editor's text back to shapes: [{shapes}, {bad}]: a line with no ___ is `bad` and is not kept. */
export function textToShapes(text) {
  const shapes = [], bad = [], seen = new Set();
  for (const raw of String(text || "").split("\n")) {
    const line = raw.trim();
    if (!line) continue;
    const m = /^([a-z]+)\s*\|\s*(.+)$/i.exec(line);
    const family = m && FAMILIES.includes(m[1].toLowerCase()) ? m[1].toLowerCase() : "other";
    const body = (m && FAMILIES.includes(m[1].toLowerCase()) ? m[2] : line).replace(/_{2,}/g, "___").trim();
    const key = body.toLowerCase().replace(/\W+/g, "");
    if (!/___/.test(body) || body.length > 160 || body.replace(/___/g, "").replace(/\W+/g, "").length < 3) { bad.push(line); continue; }
    if (seen.has(key)) continue;
    seen.add(key);
    shapes.push({ family, text: body });
  }
  return { shapes: shapes.slice(0, MAX_SHAPES), bad };
}

/** What to tell Wan about a style row, in one line. */
export function summaryLine(s, t) {
  if (!s) return "";
  if (s.status === "ready") return t(`${(s.shapes || []).length} bentuk hook`, `${(s.shapes || []).length} hook shapes`);
  if (s.status === "error") return s.error || t("Gagal dibaca.", "Could not be read.");
  return t("Bot sedang membaca tangkapan skrin.", "The bot is reading the screenshots.");
}

/** Whether the files chosen can be added: how many and which kinds. "" when they can. */
export function filesRefusal(files, t) {
  if (!files.length) return t("Pilih sekurang-kurangnya satu tangkapan skrin.", "Choose at least one screenshot.");
  if (files.length > MAX_IMAGES) return t(`Paling banyak ${MAX_IMAGES} tangkapan skrin.`, `At most ${MAX_IMAGES} screenshots.`);
  const bad = files.find((f) => !/^image\/(png|jpe?g|webp|gif)$/.test(f.type || ""));
  return bad ? t(`${bad.name}: bukan gambar yang disokong (PNG, JPG, WEBP, GIF).`, `${bad.name} is not a supported picture (PNG, JPG, WEBP, GIF).`) : "";
}
