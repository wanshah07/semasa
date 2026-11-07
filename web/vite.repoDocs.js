/* A small Vite plugin for the Dokumen page: `virtual:repo-docs` exports META = { "ops/API.md": { size, changed } } for every
   document the page may show. `size` is read from the disk; `changed` is the date of the last commit that touched the file, read
   from git once per build. pages.yml checks out the whole history (fetch-depth: 0) for this: in a shallow clone every file
   would report the one commit that is there.

   Nothing here can fail a build. No git (a zip download, a sandbox) means no dates, and the page simply leaves the note out. */
import { execFileSync } from "node:child_process";
import { readdirSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { MAX_BYTES, isWanted } from "./src/lib/repoDocs.js";

const ID = "virtual:repo-docs";
const SKIP = new Set(["node_modules", "dist", "backup", ".git", ".venv", "venv", "__pycache__"]);

/** Every .md file under `root`, repo-relative with "/" separators, skipping the folders a document never lives in. */
export function walkMarkdown(root) {
  const out = [];
  const walk = (dir) => {
    let entries = [];
    try { entries = readdirSync(dir, { withFileTypes: true }); } catch { return; }
    for (const e of entries) {
      if (e.isDirectory()) { if (!SKIP.has(e.name)) walk(join(dir, e.name)); continue; }
      if (e.isFile() && /\.md$/i.test(e.name)) out.push(relative(root, join(dir, e.name)).split(sep).join("/"));
    }
  };
  walk(root);
  return out.sort();
}

/** `git log --format=@%cI --name-only` output → { path: ISO date of the newest commit that names it }. Newest first, so the first
    date seen for a path is its last change. */
export function parseGitLog(text) {
  const out = {};
  let at = "";
  for (const line of String(text || "").split("\n")) {
    const l = line.trim();
    if (!l) continue;
    if (l.startsWith("@")) { at = l.slice(1); continue; }
    if (at && !(l in out)) out[l] = at;
  }
  return out;
}

export function buildMeta(root, gitLog = null) {
  const files = walkMarkdown(root);
  let dates = {};
  try {
    const text = gitLog ?? execFileSync("git", ["-C", root, "log", "--format=@%cI", "--name-only", "--", "*.md"],
      { encoding: "utf8", maxBuffer: 64 * 1024 * 1024, stdio: ["ignore", "pipe", "ignore"], timeout: 20000 });
    dates = parseGitLog(text);
  } catch { /* no git here: no dates */ }
  const meta = {};
  for (const f of files) {
    let size = null;
    try { size = statSync(join(root, f)).size; } catch { /* vanished between the walk and the stat */ }
    if (!isWanted(f)) continue;
    meta[f] = { size, changed: dates[f] || "" };
  }
  return meta;
}

export default function repoDocs({ root }) {
  return {
    name: "semasa-repo-docs",
    resolveId(id) { return id === ID ? "\0" + ID : null; },
    load(id) {
      if (id === "\0" + ID) return `export const META = ${JSON.stringify(buildMeta(root))};`;
      // the glob matches by name, so a file over the limit would still become a chunk; it is shipped empty instead (and listed nowhere)
      const m = /^(.*\.md)\?raw$/i.exec(id);
      if (m) { try { if (statSync(m[1]).size > MAX_BYTES) return "export default \"\";"; } catch { /* let Vite load it */ } }
      return null;
    },
  };
}
