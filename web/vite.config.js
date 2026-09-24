import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Relative asset paths ("./assets/…"), so the SAME build works at
// https://wanshah07.github.io/semasa/ and at a custom domain's root
// (socialmedia.kkmhalalconsultant.com). An absolute base such as "/semasa/"
// loads a blank page the moment the site moves to its own domain. The page has
// no client-side router (tabs are #hash), which is what makes "./" safe here.
// VITE_BASE, still set by pages.yml, is deliberately ignored.
export default defineConfig({
  plugins: [react()],
  base: "./",
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
