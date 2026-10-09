import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Relative asset paths so the same build serves at wanshah07.github.io/bernardtan/ and at bernardtan.kkmhalalconsultant.com.
// Tabs are #hash, no client router, which is what makes "./" safe.
export default defineConfig({
  plugins: [react()],
  base: "./",
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  build: { outDir: "dist", sourcemap: false, target: "es2020" },
});
