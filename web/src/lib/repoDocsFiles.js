/* The Markdown files the Dokumen page can open, gathered by Vite when the site is built. Each entry is a loader: a file's text is a
   chunk of its own and is fetched only when it is opened (or searched), so the page itself stays small. The repo is public, so
   bundling these into the public site shows nothing that GitHub does not already show.

   Patterns, not a list of names: a new file under any of these folders appears on the next build by itself. repoDocs.test.mjs checks
   that every .md file isWanted() accepts is reached by one of them, so the list and the rules cannot drift apart. backup/ and the
   installed packages are never matched (isWanted refuses them as well). Size and last-changed come from vite.repoDocs.js. */
import { META } from "virtual:repo-docs";

export const LOADERS = import.meta.glob([
  "../../../*.md",
  "../../../rules/**/*.md",
  "../../../ops/**/*.md",
  "../../../docs/**/*.md",
  "../../../.claude/skills/**/*.md",
  "../../../skills/**/*.md",
  "../../../supabase/**/*.md",
  "../../../backend/**/*.md",
  "../../../apps-script/**/*.md",
  "../../../web/*.md",
  "!**/node_modules/**",
  "!**/dist/**",
  "!**/backup/**",
  "!**/.venv/**",
], { query: "?raw", import: "default", eager: false });

export { META };
