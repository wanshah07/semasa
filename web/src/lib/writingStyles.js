/* Writing styles (Wan, 11 Oct 2026, Phase 4: "writing style bank, asing dan boleh pilih; aku upload link post viral, AI analyse
   dan terjemah jadi gaya penulisan"). The page adds a style (links, pasted text, screenshots; or one written by hand), the worker
   reads it (backend/semasa/writing_styles.py) and the caption writer follows the style that is chosen, after every rule. Pure
   helpers, tested in writingStyles.test.mjs. */

export const NONE = "none";
export const MAX_LINKS = 8;
export const MAX_IMAGES = 8;
export const MAX_SAMPLE = 12000;
export const MAX_TRAITS = 8;

export const STATUS_WORDS = {
  new: ["Menunggu bot", "Waiting for the bot"],
  working: ["Sedang dibaca", "Reading"],
  ready: ["Sedia", "Ready"],
  error: ["Gagal", "Failed"],
};
export const STATUS_CLS = { new: "bg-warn/15 text-warn", working: "bg-accent/15 text-accent", ready: "bg-ok/15 text-ok", error: "bg-danger/15 text-danger" };

export const isReady = (s) => s?.status === "ready" && String(s.instruction || "").trim().length >= 20;
export const isBusy = (s) => s?.status === "new" || s?.status === "working";

/** The style the writer uses by default: the saved one when it is ready, else none (the house style alone). */
export function activeId(setting, styles) {
  const id = String(setting?.id || "");
  return id && (styles || []).some((s) => s.id === id && isReady(s)) ? id : NONE;
}

/** The choices in an idea's select: [value, label]. "" follows the default chosen on the Gaya penulisan page. */
export function pickOptions(styles, t, setting) {
  const def = activeId(setting, styles);
  const nameOf = (id) => (id === NONE ? t("tiada", "none") : (styles || []).find((s) => s.id === id)?.name || "?");
  return [["", t(`Ikut lalai (${nameOf(def)})`, `Follow the default (${nameOf(def)})`)], [NONE, t("Tiada gaya (gaya rumah sahaja)", "No style (house style only)")],
    ...(styles || []).filter(isReady).map((s) => [s.id, s.name || t("Gaya tanpa nama", "Unnamed style")])];
}

/** The idea's brief with the chosen writing style set, or removed ("" = follow the default). */
export function withWritingStyle(brief, id) {
  const next = { ...(brief || {}) };
  if (id) next.writing_style = id; else delete next.writing_style;
  return next;
}

/** The links box: one per line (or separated by spaces); {links, bad}. Only http(s), each once, at most MAX_LINKS. */
export function linksFrom(text) {
  const links = [], bad = [];
  for (const raw of String(text || "").split(/\s+/)) {
    const s = raw.trim().replace(/[),.;]+$/, "");
    if (!s) continue;
    let ok = false;
    try { const u = new URL(s); ok = (u.protocol === "https:" || u.protocol === "http:") && !!u.hostname && u.hostname.includes("."); } catch { ok = false; }
    if (!ok) { bad.push(raw.trim()); continue; }
    if (!links.includes(s)) links.push(s);
  }
  return { links: links.slice(0, MAX_LINKS), bad, over: Math.max(0, links.length - MAX_LINKS) };
}

/** Why a new style cannot be sent yet, or "" when it can (the database checks the same). */
export function addRefusal({ links = [], sample = "", files = [] }, t) {
  if (files.length > MAX_IMAGES) return t(`Paling banyak ${MAX_IMAGES} tangkapan skrin.`, `At most ${MAX_IMAGES} screenshots.`);
  const bad = files.find((f) => !/^image\/(png|jpe?g|webp|gif)$/.test(f.type || ""));
  if (bad) return t(`${bad.name}: bukan gambar yang disokong (PNG, JPG, WEBP, GIF).`, `${bad.name} is not a supported picture (PNG, JPG, WEBP, GIF).`);
  if (String(sample).length > MAX_SAMPLE) return t(`Teks terlalu panjang (paling banyak ${MAX_SAMPLE} aksara).`, `The text is too long (at most ${MAX_SAMPLE} characters).`);
  if (!links.length && !files.length && String(sample).trim().length < 80)
    return t("Tambah sekurang-kurangnya satu pautan, satu tangkapan skrin, atau tampal teks post (80 aksara ke atas).",
      "Add at least one link, one screenshot, or paste a post's text (80 characters or more).");
  return "";
}

/** One trait a line for the editor, and back (empty lines dropped, at most MAX_TRAITS, each at most 140 characters). */
export const traitsToText = (traits) => (traits || []).join("\n");
export const textToTraits = (text) => String(text || "").split("\n").map((x) => x.trim().replace(/^[-•*]\s*/, "").slice(0, 140)).filter((x) => x.length >= 2).slice(0, MAX_TRAITS);

/** What to tell Wan about a style row, in one line. */
export function summaryLine(s, t) {
  if (!s) return "";
  if (s.status === "ready") return s.source === "manual" ? t("Ditulis sendiri", "Written by hand") : t(`${(s.traits || []).length} ciri`, `${(s.traits || []).length} traits`);
  if (s.status === "error") return s.error || t("Gagal dibaca.", "Could not be read.");
  return t("Bot sedang membaca post.", "The bot is reading the posts.");
}

/** What the style was made from, for the card: "3 pautan · teks · 2 tangkapan skrin". */
export function sourcesLine(s, t) {
  const parts = [];
  if ((s?.links || []).length) parts.push(t(`${s.links.length} pautan`, `${s.links.length} link${s.links.length === 1 ? "" : "s"}`));
  if (String(s?.sample || "").trim()) parts.push(t("teks ditampal", "pasted text"));
  if ((s?.images || []).length) parts.push(t(`${s.images.length} tangkapan skrin`, `${s.images.length} screenshot${s.images.length === 1 ? "" : "s"}`));
  return parts.join(" · ");
}
