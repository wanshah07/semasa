/* Dokumen (Wan, 7 Nov 2026: ".md files in reference segment so it auto update"). The repo's own Markdown documents, read on the
   Rujukan → Dokumen page. The files are bundled when the site is built (lib/repoDocsFiles.js, import.meta.glob), and pages.yml
   rebuilds the site on every push to main that touches a .md file, so a merged change shows up with nothing else to do.

   This file is the pure half: which paths count, how they are grouped and named, the search and the heading outline. No Vite,
   no browser, so Node tests it (repoDocs.test.mjs). */

import { plainText } from "./markdown.js";

export const MAX_BYTES = 400 * 1024;        // a file this big is a dump or a log, not a document anyone reads on a phone

/* Never shown: installed packages, build output, and backup/ (the Studio store backup carries draft captions, which the rules say
   stay out of every page). Matched on whole path segments, so "backups-plan.md" in a folder of its own is not caught by accident. */
const EXCLUDED_DIRS = new Set(["node_modules", "dist", "backup", ".git", ".venv", "venv", "__pycache__"]);

/** "../../../ops/API.md" (a glob key, relative to src/lib) → "ops/API.md" (relative to the repo root). */
export function repoPath(key) {
  return String(key || "").replace(/\\/g, "/").replace(/^(\.\.\/)+/, "").replace(/^\.\//, "");
}

/** Whether a repo-relative path is one of the documents the page shows. `size` is in bytes; unknown (null) is kept, because a
    build without the size plugin should still list the files rather than none. */
export function isWanted(path, size = null) {
  const p = repoPath(path);
  if (!/\.md$/i.test(p)) return false;
  if (p.split("/").slice(0, -1).some((seg) => EXCLUDED_DIRS.has(seg))) return false;
  if (size != null && Number(size) > MAX_BYTES) return false;
  return true;
}

/** The folder a document is listed under: the first two segments of its directory, so the six antislop skills sit under one
    ".claude/skills" heading and every function's README under "supabase/functions". "" is the repo root. */
export function groupOf(path) {
  const dirs = repoPath(path).split("/").slice(0, -1);
  return dirs.slice(0, 2).join("/");
}

/** A short name for the list. SKILL.md and README.md are named after their folder, since every one of them has the same file name. */
export function docTitle(path) {
  const parts = repoPath(path).split("/");
  const file = parts[parts.length - 1].replace(/\.md$/i, "");
  const folder = parts[parts.length - 2] || "";
  if (/^(skill|readme)$/i.test(file) && folder) return folder;
  return file;
}

const GROUP_ORDER = ["", "rules", "ops", "docs", ".claude/skills", "skills", "supabase/functions"];

/** [{ group, docs: [{ path, title, size, changed }] }] in a fixed order: the root first, then the rules, ops notes, docs and skills,
    then anything else alphabetically. Inside a group: README/CLAUDE first, then by title. */
export function groupDocs(docs) {
  const by = new Map();
  for (const d of docs || []) {
    const g = groupOf(d.path);
    if (!by.has(g)) by.set(g, []);
    by.get(g).push(d);
  }
  // "rules/motion" sorts with "rules": a group takes the place of the entry it is, or sits inside
  const rank = (g) => { const i = GROUP_ORDER.findIndex((o) => g === o || (o && g.startsWith(`${o}/`))); return i < 0 ? GROUP_ORDER.length : i; };
  // a group's own CLAUDE.md / README.md (one sitting at the top of the group, not in a sub-folder) is its front page
  const dirOf = (p) => repoPath(p).split("/").slice(0, -1).join("/");
  const first = (d) => (/^(CLAUDE|README)\.md$/i.test(repoPath(d.path).split("/").pop()) && dirOf(d.path) === groupOf(d.path) ? 0 : 1);
  return [...by.entries()]
    .sort(([a], [b]) => rank(a) - rank(b) || a.localeCompare(b))
    .map(([group, list]) => ({ group, docs: [...list].sort((a, b) => first(a) - first(b) || a.title.localeCompare(b.title) || a.path.localeCompare(b.path)) }));
}

/** The documents a build can show, from the glob's keys and the size/date plugin's META ({ path: { size, changed } }). */
export function listDocs(keys, meta = {}) {
  const seen = new Set();
  const out = [];
  for (const key of keys || []) {
    const path = repoPath(key);
    if (seen.has(path)) continue;
    const m = meta[path] || {};
    if (!isWanted(path, m.size ?? null)) continue;
    seen.add(path);
    out.push({ key, path, title: docTitle(path), size: m.size ?? null, changed: m.changed || "" });
  }
  return out;
}

const fold = (s) => String(s || "").toLowerCase().normalize("NFKD").replace(/[\u0300-\u036f]/g, "");

/** The documents that match `q`. Every word must appear in the name, the path or (when its text is loaded) the text. A match on the
    name or path ranks above one found only in the text. `texts` is { path: text } for the files already read. Each result carries
    `hits` (how often the words occur in the text) and `snippet` (a line around the first one) for the list. */
export function searchDocs(docs, q, texts = {}) {
  const words = fold(q).split(/\s+/).filter(Boolean).slice(0, 8);
  if (!words.length) return (docs || []).map((d) => ({ ...d, hits: 0, snippet: "" }));
  const out = [];
  for (const d of docs || []) {
    const head = fold(`${d.title} ${d.path}`);
    const body = texts[d.path] != null ? fold(texts[d.path]) : "";
    if (!words.every((w) => head.includes(w) || body.includes(w))) continue;
    const inHead = words.every((w) => head.includes(w));
    let hits = 0;
    for (const w of words) { let i = body.indexOf(w); while (i >= 0) { hits++; i = body.indexOf(w, i + w.length); } }
    out.push({ ...d, hits, snippet: body ? snippetOf(texts[d.path], words) : "", score: (inHead ? 1000 : 0) + hits });
  }
  return out.sort((a, b) => b.score - a.score || a.path.localeCompare(b.path)).map(({ score, ...r }) => r);
}

/** About `width` characters around the first word found, on one line. */
export function snippetOf(text, words, width = 140) {
  const src = String(text || "");
  const low = fold(src);
  let at = -1;
  for (const w of words) { const i = low.indexOf(w); if (i >= 0 && (at < 0 || i < at)) at = i; }
  if (at < 0) return "";
  const start = Math.max(0, at - Math.floor(width / 3));
  const cut = src.slice(start, start + width).replace(/\s+/g, " ").trim();
  return (start > 0 ? "…" : "") + cut + (start + width < src.length ? "…" : "");
}

/** A heading's anchor id: lower-case words joined by "-", made unique within the document by a counter. */
export function slugify(text, used) {
  const base = fold(text).replace(/[^\p{L}\p{N}\s-]/gu, "").trim().replace(/\s+/g, "-").slice(0, 60) || "bahagian";
  let id = `doc-${base}`;
  for (let n = 2; used.has(id); n++) id = `doc-${base}-${n}`;
  used.add(id);
  return id;
}

/** The outline of a parsed document (lib/markdown.js blocks): [{ id, level, text }] for every heading, in order. The same ids are
    handed to the renderer, so a click on the outline lands on its heading. */
export function outlineOf(blocks) {
  const used = new Set();
  return (blocks || []).filter((b) => b.t === "h").map((b) => {
    const text = plainText([b]).trim();
    return { id: slugify(text, used), level: b.n, text };
  });
}

/** "Diubah 3 hari lalu"-style words are the page's job; this gives the date part. "" when there is nothing to say. */
export function changedDate(iso, lang = "bm") {
  const d = new Date(iso);
  if (!iso || Number.isNaN(d.getTime())) return "";
  return new Intl.DateTimeFormat(lang === "en" ? "en-GB" : "ms-MY", { timeZone: "Asia/Kuala_Lumpur", day: "numeric", month: "short", year: "numeric" }).format(d);
}

export function sizeText(bytes) {
  const n = Number(bytes);
  if (!Number.isFinite(n) || n <= 0) return "";
  return n < 1024 ? `${n} B` : `${(n / 1024).toFixed(n < 10240 ? 1 : 0)} KB`;
}
