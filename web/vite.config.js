import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import repoDocs from "./vite.repoDocs.js";

// Relative asset paths ("./assets/…"), so the SAME build works at
// https://wanshah07.github.io/semasa/ and at a custom domain's root
// (socialmedia.kkmhalalconsultant.com). An absolute base such as "/semasa/"
// loads a blank page the moment the site moves to its own domain. The page has
// no client-side router (tabs are #hash), which is what makes "./" safe here.
// VITE_BASE, still set by pages.yml, is deliberately ignored.
/* The installed iPhone app's service worker (pwa/sw.js, registered by src/lib/pwa.js in production only). It is written
   here rather than copied from public/ for two reasons: its BUILD line must change on every deploy, or a phone keeps the
   old worker; and its PRECACHE list must name this build's hashed shell files, which only exist once Rollup has named
   them. Every path is relative ("./", "assets/…"), like `base` below, so the same sw.js works at /semasa/ and at the
   custom domain's root: the worker's scope is the folder it is served from. */
function semasaServiceWorker() {
  return {
    name: "semasa-service-worker",
    apply: "build",
    generateBundle(_opts, bundle) {
      const files = Object.values(bundle);
      const entry = files.filter((f) => f.type === "chunk" && f.isEntry);
      const shell = new Set(["./", "manifest.webmanifest", "favicon.svg", "icons/icon-192.png", "icons/apple-touch-icon.png"]);
      const seen = new Set();
      const add = (name) => {
        const f = bundle[name];
        if (!f || seen.has(name)) return;
        seen.add(name);
        shell.add(name);
        if (f.type === "chunk") {
          (f.viteMetadata?.importedCss || []).forEach((css) => shell.add(css));
          f.imports.forEach(add);        // the vendor chunks the entry imports statically (react, supabase…), never the lazy tabs
        }
      };
      entry.forEach((f) => add(f.fileName));
      const build = createHash("sha256").update(files.map((f) => f.fileName).sort().join("\n")).digest("hex").slice(0, 12);
      const src = readFileSync(new URL("./pwa/sw.js", import.meta.url), "utf8")
        .replace('const BUILD = "dev";', `const BUILD = ${JSON.stringify(build)};`)
        .replace("const PRECACHE = [];", `const PRECACHE = ${JSON.stringify([...shell])};`);
      if (src.includes('const BUILD = "dev";') || src.includes("const PRECACHE = [];")) this.error("pwa/sw.js: the BUILD or PRECACHE line moved");
      this.emitFile({ type: "asset", fileName: "sw.js", source: src });
    },
  };
}

export default defineConfig({
  // repoDocs: size and last-changed date of the repo's .md files, for Rujukan → Dokumen (src/lib/repoDocsFiles.js)
  plugins: [react(), semasaServiceWorker(), repoDocs({ root: fileURLToPath(new URL("..", import.meta.url)) })],
  base: "./",
  // "@/components/ui/…": the path a shadcn component is written against (components.json)
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  // rules/compliance.json lives at the repo root, shared with the Python publisher
  server: { fs: { allow: [".."] } },
  build: {
    outDir: "dist",
    sourcemap: false,
    target: "es2020",
    rollupOptions: {
      output: {
        manualChunks: { react: ["react", "react-dom"], motion: ["framer-motion"], supabase: ["@supabase/supabase-js"] },
      },
    },
  },
});
