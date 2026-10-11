import animate from "tailwindcss-animate";

/** Every colour, radius, font and shadow maps to a CSS variable from src/design/tokens.css.
 *  A theme is a file that sets those variables; swapping it changes the whole app with
 *  no rebuild and no component edit. Use `bg-surface`, `text-ink`, `rounded-card` … only. */
const c = (name) => `rgb(var(--c-${name}) / <alpha-value>)`;

/** Tailwind's own palette as CSS variables on :root (var(--blue-500), var(--white), var(--transparent) …), which the pasted
 *  aurora background reads. The paste's version published EVERY theme colour; here Semasa's token colours are left out on
 *  purpose: they are `rgb(var(--c-…) / <alpha-value>)` templates, not colours, and three of their names (--brand, --info,
 *  --success) are variables src/index.css already defines, which the paste's plugin would have overwritten with a reference
 *  to themselves. Only plain colour strings pass the filter. */
function paletteVariables({ addBase, theme }) {
  const flat = {};
  const walk = (obj, prefix) => {
    for (const [k, v] of Object.entries(obj || {})) {
      const name = k === "DEFAULT" ? prefix : prefix ? `${prefix}-${k}` : k;
      if (v && typeof v === "object") walk(v, name);
      else if (typeof v === "string" && !v.includes("var(") && !v.includes("<alpha-value>")) flat[`--${name}`] = v;
    }
  };
  walk(theme("colors"), "");
  addBase({ ":root": flat });
}

export default {
  content: ["./index.html", "./src/**/*.{js,jsx,ts,tsx}"],
  darkMode: ["selector", '[data-theme="noir"]'],
  theme: {
    extend: {
      colors: {
        bg: c("bg"),
        surface: c("surface"),
        "surface-2": c("surface-2"),
        line: c("line"),
        ink: c("ink"),
        accent: c("accent"),
        "accent-ink": c("accent-ink"),
        warm: c("warm"),
        gold: c("gold"),
        ok: c("ok"),
        warn: c("warn"),
        danger: c("danger"),
        // shadcn's names, pointed at the SAME tokens, so a pasted shadcn component follows every Semasa theme
        // (bg-card, text-foreground, text-muted-foreground, border-border, bg-primary …)
        background: c("bg"),
        foreground: c("ink"),
        card: { DEFAULT: c("surface"), foreground: c("ink") },
        popover: { DEFAULT: c("surface"), foreground: c("ink") },
        primary: { DEFAULT: c("accent"), foreground: c("accent-ink") },
        secondary: { DEFAULT: c("surface-2"), foreground: c("ink") },
        muted: { DEFAULT: c("muted"), foreground: c("muted") },   // text-muted stays exactly what it was
        border: c("line"),
        input: c("line"),
        ring: c("accent"),
        destructive: { DEFAULT: c("danger"), foreground: c("bg") },
        "accent-foreground": c("accent-ink"),
        // the progress bars' own tokens (src/index.css): a fixed brand/info/success, lighter under the dark theme
        brand: { DEFAULT: "var(--brand)", foreground: "var(--brand-foreground)" },
        info: { DEFAULT: "var(--info)", foreground: "var(--info-foreground)" },
        success: { DEFAULT: "var(--success)", foreground: "var(--success-foreground)" },
      },
      // shadcn's bg-muted is a pale surface, not the grey Semasa writes text in: backgrounds only, so text-muted is
      // exactly what it always was
      backgroundColor: { muted: { DEFAULT: c("surface-2"), foreground: c("muted") } },
      keyframes: {
        "accordion-down": { from: { height: "0" }, to: { height: "var(--radix-accordion-content-height)" } },
        "accordion-up": { from: { height: "var(--radix-accordion-content-height)" }, to: { height: "0" } },
        // the aurora behind the dashboard's hero band (components/ui/aurora-background.tsx)
        aurora: { from: { backgroundPosition: "50% 50%, 50% 50%" }, to: { backgroundPosition: "350% 50%, 350% 50%" } },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
        aurora: "aurora 60s linear infinite",
      },
      fontFamily: {
        display: ["var(--font-display)"],
        body: ["var(--font-body)"],
        sans: ["var(--font-body)"],   // shadcn components say font-sans: the theme's body face
      },
      borderRadius: {
        card: "var(--r-card)",
        tile: "var(--r-tile)",
        pill: "var(--r-pill)",
      },
      boxShadow: {
        card: "var(--shadow-card)",
        lift: "var(--shadow-lift)",
        xs: "0 1px 2px 0 rgb(0 0 0 / 0.05)",
      },
      maxWidth: { page: "var(--page-max)" },
      transitionTimingFunction: { out: "var(--ease-out)" },
    },
  },
  plugins: [animate, paletteVariables],   // animate-in / fade-in / zoom-in-95, as shadcn components use; palette vars for the aurora
};
