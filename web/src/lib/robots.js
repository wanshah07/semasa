// The three Wanshah robots' palette and the colour maths that turns a tone into the six faces of a CSS 3D box. Ported
// from halal-executive src/lib/robots.js (Wan, 23 Oct 2026: "make sure robots appear as attach") so both apps draw the
// same robot for the same AI: W1 green = rootsys (Afiq), W2 blue = Mireld, W3 purple = KiosAPI.
//
// shell is [light, mid, dark] — the three stops of the shell gradient.
export const THEMES = {
  afiq: { shell: ["#2bd18a", "#0b6b3a", "#063d22"], visor: ["#0c2b1d", "#04140c"], eye: "#7dffc4", glow: "#29f0a0", accent: "#c9a227", label: "W1", name: "Wanshah 1" },
  mireld: { shell: ["#7fb2ff", "#2a5fc4", "#15306b"], visor: ["#0f1d3a", "#060c1c"], eye: "#9fe0ff", glow: "#5cc8ff", accent: "#f0b429", label: "W2", name: "Wanshah 2" },
  kios: { shell: ["#c58bff", "#7a3fd1", "#3d1a7a"], visor: ["#25103f", "#10061f"], eye: "#f1d4ff", glow: "#d08cff", accent: "#f0b429", label: "W3", name: "Wanshah 3" },
  // a provider Wan added on the API tab (Wanshah 6, 7, ...): the same robot in copper, so an added robot reads as one family
  provider: { shell: ["#f2a65a", "#b85c1e", "#5a2a0c"], visor: ["#2b1608", "#140903"], eye: "#ffe0b8", glow: "#ffb46b", accent: "#c9a227", label: "W6", name: "Wanshah 6" },
  // Gemini (W4) and ChatGPT (W5) each in a colour of their own (Wan, 24 Nov 2026: "all bot live have their own colors"): both
  // were the guest slate, so two live robots looked like one. Teal and rose: neither is W1's green, W2's blue or W3's purple.
  gemini: { shell: ["#5eead4", "#0f9a8a", "#0a4f47"], visor: ["#06302b", "#021513"], eye: "#c9fff6", glow: "#3df0d8", accent: "#f0b429", label: "W4", name: "Wanshah 4" },
  chatgpt: { shell: ["#ff9ccb", "#d1367f", "#6b1740"], visor: ["#3a0e23", "#1a0610"], eye: "#ffe0ef", glow: "#ff7ab8", accent: "#f0b429", label: "W5", name: "Wanshah 5" },
  // the second, third and fourth provider Wan adds (W7, W8, W9): gold, red and indigo, so no two added robots share a colour either
  provider2: { shell: ["#ffe27a", "#c79a12", "#6b5208"], visor: ["#2e2406", "#161103"], eye: "#fff5c9", glow: "#ffd84a", accent: "#c9a227", label: "W7", name: "Wanshah 7" },
  provider3: { shell: ["#ff9a8f", "#c43a3a", "#6b1d1d"], visor: ["#350f0f", "#190707"], eye: "#ffe0dc", glow: "#ff7466", accent: "#c9a227", label: "W8", name: "Wanshah 8" },
  provider4: { shell: ["#a5a8ff", "#4a4fd1", "#22257a"], visor: ["#12143f", "#08091f"], eye: "#e0e1ff", glow: "#8c90ff", accent: "#c9a227", label: "W9", name: "Wanshah 9" },
  // a gateway nobody named (OpenAI, Anthropic, a host Wan typed in): the same robot in slate
  guest: { shell: ["#b8c2cc", "#5f6b78", "#2e3640"], visor: ["#1e2530", "#0c1016"], eye: "#e6edf3", glow: "#c3ccd6", accent: "#c9a227", label: "W?", name: "Wanshah" },
};

const WHITE = "#ffffff", BLACK = "#000000";
const rgb = (h) => { const s = h.replace("#", ""); return [0, 2, 4].map((i) => parseInt(s.slice(i, i + 2), 16)); };
const hex = (c) => "#" + c.map((n) => Math.max(0, Math.min(255, Math.round(n))).toString(16).padStart(2, "0")).join("");
// a -> b by t (0..1).
export const mix = (a, b, t) => { const x = rgb(a), y = rgb(b); return hex(x.map((v, i) => v + (y[i] - v) * t)); };

// The six faces of the body, lit from the upper front-left: the top catches a white tint, the bottom falls away to
// near-black, and the sides sit between the mid and dark stops so a turning box reads as one solid object.
export function shadeFor(shell) {
  const [lite, mid, dark] = shell;
  const midDark = mix(mid, dark, 0.5);
  return {
    front: `linear-gradient(160deg,${lite},${mid} 60%,${midDark})`,
    back: dark,
    right: `linear-gradient(90deg,${midDark},${dark})`,
    left: `linear-gradient(90deg,${mix(lite, mid, 0.75)},${mix(mid, dark, 0.26)})`,
    top: `linear-gradient(180deg,${mix(lite, WHITE, 0.45)},${mix(lite, mid, 0.25)})`,
    bottom: mix(dark, BLACK, 0.42),
  };
}

// The visor and the chest badge are the same dark glass.
export const glassFor = (visor) => `linear-gradient(180deg,${visor[0]},${visor[1]})`;

// Brushed metal and the dead-grey an offline robot goes: shared, never tinted, because "offline" has to look the same
// whichever AI it is.
export const METAL = { front: "linear-gradient(90deg,#8a96a3,#e8edf2,#6b7785)", back: "#5b6672", right: "#6b7785", left: "#aab4bf", top: "#e8edf2", bottom: "#4b5560" };
export const GREY = { front: "#7b8088", back: "#4b5059", right: "#5a5f68", left: "#8b9098", top: "#a0a5ad", bottom: "#3a3e45" };
export const GREY_GLASS = "linear-gradient(180deg,#3f444c,#23262b)";

/** The theme for a tone, falling back to the guest slate for a tone nobody named; `label` (W6, W7, ...) overrides the badge. */
export function themeFor(tone, label) {
  const t = THEMES[tone] || THEMES.guest;
  return label ? { ...t, label } : t;
}

const PROVIDER_TONES = ["provider", "provider2", "provider3", "provider4"];

/** The tone a robot is drawn in: its own for the built-in five; for a provider Wan added, one of four by its number (W6 copper,
    W7 gold, W8 red, W9 indigo, then round again), so every robot on the page has a colour of its own. */
export function toneFor(card) {
  if (!card) return "guest";
  if (card.added || card.tone === "provider") {
    const n = Number(String(card.robot || "").replace(/\D/g, "")) || 6;
    return PROVIDER_TONES[(((n - 6) % PROVIDER_TONES.length) + PROVIDER_TONES.length) % PROVIDER_TONES.length];
  }
  return THEMES[card.tone] ? card.tone : "guest";
}

/** A robot's own colour as one hex, for a border or a dot beside its name: the bright stop of its shell while it is live, the
    shared dead grey when it is offline ("offline" looks the same whichever AI it is, as on the robot itself). */
export function colourFor(card, live = true) {
  return live ? (THEMES[toneFor(card)] || THEMES.guest).shell[0] : "#7b8088";
}
