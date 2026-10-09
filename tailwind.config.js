/** Every colour maps to a CSS variable from src/theme.css, so the look is changed in ONE file (and a second theme is a
 *  second block of variables). Use bg-bun, text-ink, bg-ketchup … in components; plain CSS in theme.css is fine too. */
const c = (name) => `rgb(var(--c-${name}) / <alpha-value>)`;

export default {
  content: ["./index.html", "./src/**/*.{js,jsx,ts,tsx}"],
  darkMode: ["selector", '[data-theme="night"]'],
  theme: {
    extend: {
      colors: {
        bg: c("bg"), surface: c("surface"), "surface-2": c("surface-2"), line: c("line"), ink: c("ink"), muted: c("muted"),
        ketchup: c("ketchup"), mustard: c("mustard"), lettuce: c("lettuce"), bun: c("bun"), sky: c("sky"), ok: c("ok"), warn: c("warn"), danger: c("danger"),
      },
      fontFamily: { display: ["'Fredoka'", "'Baloo 2'", "system-ui", "sans-serif"], body: ["'Nunito'", "system-ui", "sans-serif"] },
      borderRadius: { card: "1.25rem", tile: "0.9rem", pill: "999px" },
      boxShadow: { card: "0 4px 0 0 rgb(var(--c-ink) / 0.9)", lift: "0 8px 0 0 rgb(var(--c-ink) / 0.9)", soft: "0 10px 30px -12px rgb(var(--c-ink) / 0.35)" },
    },
  },
  plugins: [],
};
