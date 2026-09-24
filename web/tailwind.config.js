/** Every colour, radius, font and shadow maps to a CSS variable from src/design/tokens.css.
 *  A theme is a file that sets those variables; swapping it changes the whole app with
 *  no rebuild and no component edit. Use `bg-surface`, `text-ink`, `rounded-card` … only. */
const c = (name) => `rgb(var(--c-${name}) / <alpha-value>)`;

export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  darkMode: ["selector", '[data-theme="noir"]'],
  theme: {
    extend: {
      colors: {
        bg: c("bg"),
        surface: c("surface"),
        "surface-2": c("surface-2"),
        line: c("line"),
        ink: c("ink"),
        muted: c("muted"),
        accent: c("accent"),
        "accent-ink": c("accent-ink"),
        warm: c("warm"),
        gold: c("gold"),
        ok: c("ok"),
        warn: c("warn"),
        danger: c("danger"),
      },
      fontFamily: {
        display: ["var(--font-display)"],
        body: ["var(--font-body)"],
      },
      borderRadius: {
        card: "var(--r-card)",
        tile: "var(--r-tile)",
        pill: "var(--r-pill)",
      },
      boxShadow: {
        card: "var(--shadow-card)",
        lift: "var(--shadow-lift)",
      },
      maxWidth: { page: "var(--page-max)" },
      transitionTimingFunction: { out: "var(--ease-out)" },
    },
  },
  plugins: [],
};
