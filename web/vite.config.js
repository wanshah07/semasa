import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// VITE_BASE is "/<repo>/" on GitHub Pages (set by .github/workflows/pages.yml) and "/" locally.
export default defineConfig({
  plugins: [react()],
  base: process.env.VITE_BASE || "/",
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
