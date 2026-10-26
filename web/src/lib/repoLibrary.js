/* Pustaka repo (Wan, 23 Oct 2026): the library of repositories Wan adds by link, read and filed by the worker
   (backend/semasa/repo_library.py, semasa_repo_library). Pure functions, tested in repoLibrary.test.mjs. */

export const CATEGORIES = ["motion", "video", "suara", "muzik", "imej", "3d", "kemahiran-ai", "agen-ai", "mcp", "scraper", "pelayar", "regulatori", "dokumen",
  "web", "frontend", "api", "data", "analitik", "automasi", "pemasaran", "keselamatan", "devops", "terjemahan", "alatan", "lain"];
export const CATEGORY_WORDS = {
  motion: ["Motion", "Motion"], video: ["Video", "Video"], suara: ["Suara", "Voice"], muzik: ["Muzik", "Music"], imej: ["Imej", "Image"],
  "3d": ["3D", "3D"], "kemahiran-ai": ["Kemahiran AI", "AI skills"], "agen-ai": ["Ejen AI", "AI agents"], mcp: ["MCP", "MCP"],
  scraper: ["Scraper", "Scraper"], pelayar: ["Pelayar", "Browser"], regulatori: ["Regulatori", "Regulatory"], dokumen: ["Dokumen", "Documents"],
  web: ["Web", "Web"], frontend: ["Antara muka", "Front end"], api: ["API", "API"], data: ["Data", "Data"], analitik: ["Analitik", "Analytics"],
  automasi: ["Automasi", "Automation"], pemasaran: ["Pemasaran", "Marketing"], keselamatan: ["Keselamatan", "Security"], devops: ["DevOps", "DevOps"],
  terjemahan: ["Terjemahan", "Translation"], alatan: ["Alatan", "Tooling"], lain: ["Lain", "Other"],
};
export const SAFETY_WORDS = {
  safe: ["Selamat", "Safe"], caution: ["Berhati-hati", "Caution"], avoid: ["Elakkan", "Avoid"], unknown: ["Belum disemak", "Not checked"],
};
export const STATUS_WORDS = {
  pending: ["Menunggu", "Waiting"], working: ["Dibaca", "Reading"], done: ["Siap", "Done"], error: ["Ralat", "Error"],
};
const GITHUB_RE = /^https?:\/\/(?:www\.)?github\.com\/([\w.-]+)\/([\w.-]+?)(?:\.git)?(?:[/#?].*)?$/i;

/** owner/name from a github.com link, or null (the worker reads only GitHub for now). */
export function parseRepoUrl(url) {
  const m = GITHUB_RE.exec(String(url || "").trim());
  return m ? `${m[1]}/${m[2]}` : null;
}

/** The link as the row stores it: the repository root, https, no .git, no trailing path. */
export function canonicalUrl(url) {
  const full = parseRepoUrl(url);
  return full ? `https://github.com/${full}` : "";
}

/** The categories to offer: the settings list, else the defaults, 'lain' always last. */
export function categoriesOf(settings) {
  const list = [...new Set(((settings || {}).repo_library?.categories || CATEGORIES).map((c) => String(c).trim().toLowerCase()).filter(Boolean))];
  const rest = list.filter((c) => c !== "lain");
  return [...rest, "lain"];
}

/** Rows grouped by category, in the categories' order; an empty category is left out. */
export function groupByCategory(rows, cats) {
  const by = {};
  for (const r of rows || []) {
    const c = cats.includes(r.category) ? r.category : "lain";
    (by[c] = by[c] || []).push(r);
  }
  return cats.filter((c) => by[c]).map((c) => ({ category: c, rows: by[c].sort((a, b) => String(b.updated_at || "").localeCompare(String(a.updated_at || ""))) }));
}

/** Rows a search and a category filter keep. */
export function filterRows(rows, { q = "", category = "", safety = "" } = {}) {
  const needle = q.trim().toLowerCase();
  return (rows || []).filter((r) => (!category || r.category === category) && (!safety || r.safety === safety)
    && (!needle || [r.full_name, r.name, r.description, r.summary_bm, r.summary_en, r.use_for, ...(r.tags || [])].join(" ").toLowerCase().includes(needle)));
}

/** The summary line for the counts tile: {total, done, pending, avoid, caution}. */
export function librarySummary(rows) {
  const s = { total: 0, done: 0, pending: 0, avoid: 0, caution: 0 };
  for (const r of rows || []) {
    s.total += 1;
    if (r.status === "done") s.done += 1;
    if (r.status === "pending" || r.status === "working") s.pending += 1;
    if (r.safety === "avoid") s.avoid += 1;
    if (r.safety === "caution") s.caution += 1;
  }
  return s;
}

/** The static flags, worst first, for the card. */
export function flagsOf(row) {
  const order = { avoid: 0, caution: 1, safe: 2, unknown: 3 };
  return [...(row?.safety_flags || [])].sort((a, b) => (order[a.severity] ?? 9) - (order[b.severity] ?? 9));
}
