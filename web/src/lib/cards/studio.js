/* ws.regulab Studio's card designs, copied into Semasa (Wan, 26 Sep 2026: "for post and idea carousel, copy the
   code design that already in ws.regulab studio, so we can choose the design").

   Everything between the two COPIED FROM STUDIO markers is Studio's own renderer, taken VERBATIM from
   wanshah07/argus studio/part2.html (commit e16db45): the Grid, Info ERA and Photo families, their palettes, fonts,
   helpers and every comment that explains why a line is the way it is. Four edits only, each marked SEMASA:
     1. the card size comes from sizeOf(spec), so the Design tab's portrait and story shapes work;
     2. loadImg asks for CORS, so a picture from Supabase storage does not taint the canvas;
     3. LOGO is set by setLogo() instead of being pasted into the page at build time;
     4. nothing else of Studio's page (the store, the drafts, the mascot library) comes with it.
   The retired designs (statement, stat, list, ...) are not copied: Studio itself no longer offers them.

   The same file draws in two places, so what Wan picks is what the post gets:
     - the page imports it for the live preview (web/src/components/LookPicker.jsx);
     - the worker loads it in headless Chrome (backend/semasa/studio_cards.py) for the real render.
   Below the copied block is Semasa's own part: how a Semasa slide ({title, points}) becomes a Studio card spec. */

import { gradientCoords, layoutToSeed } from "../designCloneSeed.js";

/* SEMASA: set by setLogo(); Studio pasted its logo in here at build time. */
let LOGO = "";
export function setLogo(src) { LOGO = src || ""; _logoInk = null; }
/* SEMASA: Studio sized every card by stream; the Design tab also draws a 4:5 poster and a 9:16 story. */
function sizeOf(spec) {
  if (Array.isArray(spec.size) && spec.size.length === 2) return [spec.size[0], spec.size[1]];
  return CARD_SIZES[spec.stream === "linkedin" ? "linkedin" : "regulab"];
}

/* SEMASA (Wan, 3 Oct 2026: "make sure we can choose to compact the text on card - smaller font size, font type, and
   move the mascot"). Four optional fields on a slide, all empty by default so every card drawn before today is drawn
   exactly as before:
     type_size   60..120  percent of the template's own text sizes (headline, lead, items), line height included
     font        sans | round | hand   which face the words use (the template's own pairing when empty)
     mascot_pos  bl | bc | br          which of the three bottom spots the character stands in
     mascot_size 50..160  percent of the character's own height
   The type sizes stay fixed for a given choice (no size follows how much text there is), so the carousel rule that a
   deleted line never changes the type still holds: the person chooses the size, the text never does. */
export const TYPE_SIZES = [60, 70, 80, 90, 100, 110, 120];
export const MASCOT_SIZES = [60, 80, 100, 130, 160];
export const FONT_CHOICES = ["sans", "round", "hand"];
const FONT_SWAP = {
  sans: { family: '"Instrument Sans", system-ui, sans-serif', maxWeight: 600 },     // narrower: more words per line
  round: { family: 'Poppins, "Instrument Sans", system-ui, sans-serif', maxWeight: 800 },
  hand: { family: 'Caveat, "Instrument Sans", cursive', maxWeight: 700, only: 700 },
};
const pct = (v, lo, hi) => { const n = Number(v); return Number.isFinite(n) && n >= lo && n <= hi ? n / 100 : 1; };
/* AUTO-FIT (Wan, 16 Nov 2026: "for all poster, single card, comic, image make auto-fit application"). Whatever words a card is
   given, it fits by itself: a card with little to say grows its type until the card is full, a card with too much shrinks it
   until every word is above the source line, and only a card that does not fit at FIT_MIN (the smallest size that still reads
   on a phone) says so with the "fuller than the card" warning. One number does it, `_fill`: it is never stored, it is found
   by measuring the finished layout (fillScale), and every size on the card moves with it. A text size the person chose on a
   slide (`type_size`) is theirs: the card is then drawn at that size and only warns.
   A layout that takes part must (1) draw every line through a wrapper, so nothing runs off the side, (2) size its containers
   from the lines in them, so nothing runs out of a box, and (3) report where its content ends, including a note. */
export const FIT_MIN = 0.62;
const fillOf = (spec) => { const f = Number(spec && spec._fill); return Number.isFinite(f) && f >= FIT_MIN - 0.001 && f <= 3 ? f : 1; };
function textScale(spec) { return pct(spec && spec.type_size, 60, 120) * fillOf(spec); }
function mascotScale(spec) { return pct(spec && spec.mascot_size, 50, 160); }
/* The canvas context with its `font` rewritten on the way in: only a font that names Poppins or Instrument Sans (the
   words) is touched; the handwritten bubble note and the monospace table keep their own faces. */
function styleCtx(ctx, spec) {
  const f = FONT_SWAP[spec && spec.font];
  if (!f) return ctx;
  const swap = (v) => {
    const m = /^(\d{3})\s+(\d+(?:\.\d+)?px)\s+(.*)$/.exec(v);
    if (!m || !/Poppins|Instrument Sans/.test(m[3])) return v;
    return `${f.only || Math.min(Number(m[1]), f.maxWeight)} ${m[2]} ${f.family}`;
  };
  return new Proxy(ctx, {
    get(t, k) { const v = t[k]; return typeof v === "function" ? v.bind(t) : v; },
    set(t, k, v) { t[k] = k === "font" ? swap(String(v)) : v; return true; },
  });
}

/* ======================= COPIED FROM STUDIO (begin) ======================= */
/* ---------- card templates: rendered in-page to a real PNG ---------- */
// ws.regulab posts go to Instagram, Facebook and Threads; Instagram's grid is portrait now and cut the square cards at the
// sides (Wan, 24 Oct 2026, with a screenshot of the feed): every card is 4:5, the same shape as the LinkedIn carousel
const CARD_SIZES = { regulab: [1080, 1350], linkedin: [1080, 1350] };

const GRID_TPL = { g_title: 1, g_stat: 1, g_bars: 1, g_rows: 1, g_table: 1 };
const GRID_DARK = { g_stat: 1, g_table: 1 };
const ERA_TPL = { e_hook: 1, e_explain: 1, e_flow: 1, e_vs: 1 };
const PHOTO_TPL = { p_title: 1, p_fact: 1, p_quote: 1 };
const HAND_TPL = { h_poster: 1, h_hero: 1, h_note: 1 };
/* THREE LOOKS, AND EACH HAS TO WORK AS A SINGLE CARD *AND* AS A WHOLE CAROUSEL (Wan,
   19 Sep 2026: "make this as second choice of carousel and single card, previous design as
   first group carousel/single card, image background as third group"). A group names the
   template its cover, its middle slides and its closing slide use, so choosing a group
   re-dresses the entire post instead of one slide -- which is the only reading of "choice
   of carousel" that means anything. The grid family stays FIRST and stays the default, so
   no draft that exists today changes by having these added. */
const CARD_GROUPS = [
  { k: "grid", name: "Grid", hint: "Cream graph paper, ultra-bold headline, raised panels. The calm house look.", cover: "g_title", fact: "g_title", close: "g_title" },
  { k: "era", name: "Info ERA", hint: "Kraft paper, marker highlights, red alert blocks, hand-drawn arrows. Loud explainer.", cover: "e_hook", fact: "e_explain", close: "e_explain" },
  { k: "photo", name: "Photo", hint: "Your own photograph behind the words, on every slide.", cover: "p_title", fact: "p_fact", close: "p_quote" },
  { k: "image", name: "Image", hint: "Your picture ON the slide: a panel, a taped print, a tipped poster or a phone screen.", cover: "i_hero", fact: "i_note", close: "i_title" },
];
function groupOf(tpl) { return ERA_TPL[tpl] ? "era" : PHOTO_TPL[tpl] ? "photo" : PIC_TPL[tpl] ? "image" : HAND_TPL[tpl] ? "hand" : SKIN_TPL[tpl] ? SKIN_OF[tpl[0]] : "grid"; }
function groupDef(k) { return CARD_GROUPS.find(g => g.k === k) || CARD_GROUPS[0]; }

/* Which templates can carry the character. g_table stays "no character" -- it is the dark
   structured data table the reference prompt itself never puts one on. g_stat joined the
   rest on 19 Sep 2026 (Wan: "for dark slide adapt the mascot") for its advice/hint branch
   only (no figure given -- see the giant-number branch in renderGridCard, which still gets
   no character, since a mascot has nothing to point at there). */
const MASCOT_TPL = { g_title: 1, g_bars: 1, g_rows: 1, g_stat: 1, e_hook: 1, e_explain: 1, e_vs: 1 };
/* NO MASCOT ON ANY CARD (Wan, 16 Nov 2026, of an Info ERA slide with the character in a half-empty card: "REMOVE ALL MASCOTT").
   One switch, read by the renderer (mascotUrl), by the slide editor (takesMascot) and by the Design pages, so no card draws
   one and no control offers one. The poses, the per-template hints and the painters' mascot code are left in place: turning
   this back on brings them all back, and a slide that stored a pose keeps the choice without drawing it. */
export const MASCOTS_ON = false;
/* A slide's template hints at which pose actually fits it -- a title wants a welcome, a
   comparison wants a point (Wan, 19 Sep 2026: "different gesture, depends on the idea and
   context"). Matched against each mascot's own name; unmatched or only one pose in the
   store, it just falls back to whatever is available, so this never blocks on having a
   full pose library -- it only makes one more useful once it exists.
   The ERA family is where this earns its keep: its hook slide is a character who does not
   understand what just happened, and its versus slide is one looking at a number she cannot
   believe. Drawing a cheerful wave on either would undo the whole slide, which is why two
   more poses were generated (confused, shocked) rather than the map being pointed at the
   two that already existed. e_flow is deliberately absent -- the step chain fills the card
   and a character standing in it has nothing to stand on. */
const MASCOT_HINT = {
  g_title: "wav", g_rows: "wav", g_bars: "point", g_stat: "point",
  e_hook: "confus", e_explain: "point", e_vs: "shock",
};
function pickMascotFor(template, mascots) {
  if (!mascots || !mascots.length) return null;
  const hint = MASCOT_HINT[template];
  if (hint) { const m = mascots.find(x => String(x.name || "").toLowerCase().includes(hint)); if (m) return m; }
  return mascots[0];
}
/* Wan, 19 Sep 2026, against a reference set where the character sits in a different
   corner on nearly every slide and is a supporting detail, not a headline-width figure:
   "mascot no need at the same place, make the mascot smaller and randomly place". Three
   bottom-anchored spots instead of one fixed corner, picked deterministically from the
   post's own title when a slide doesn't say otherwise -- the same draft always renders
   the same way (so re-rendering never shuffles it), but different posts in one carousel
   land in different corners the way the reference set does. */
const MASCOT_POS = ["br", "bl", "bc"];
function pickMascotPos(spec) {
  if (spec.mascot_pos && MASCOT_POS.includes(spec.mascot_pos)) return spec.mascot_pos;
  const s = String(spec.title || spec.mascot || "");
  let h = 0; for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  return MASCOT_POS[h % MASCOT_POS.length];
}
/* Every design a picker may OFFER. Legacy designs stay fully renderable (renderCard,
   scanInner, TPL[...].uses all still read the full CARD_TEMPLATES list) -- this is only

/* The grid family's own palette. It is deliberately NOT CARD_PAL: that one is the teal
   house scheme for the older designs, and these slides are a separate look Wan chose on
   19 Sep 2026 \u2014 cream graph paper, near-black ink, one vivid orange. */
const GRID_PAL = {
  cream: "#F7F2E8", grid: "#E2DACA", panel: "#FFFDF8", panelLine: "#E4DCCA",
  ink: "#15171B", muted: "#5B6068", orange: "#E24B1A",
  dark: "#14171C", darkGrid: "#232830", purple: "#C6B6F2", yellow: "#F6E77E",
};
const CARD_PAL = { ink: "#11333D", deep: "#1C4753", teal: "#2E7D8C", cream: "#F4F1EC", paper: "#FFFFFF", amber: "#A8701F", line: "#DCD5C8", mute: "#6B7F86" };
const _imgCache = new Map();
function loadImg(src) {
  if (!src) return Promise.resolve(null);
  if (_imgCache.has(src)) return _imgCache.get(src);
  /* SEMASA: a picture from Supabase storage is another origin. Without crossOrigin it taints the
     canvas and toDataURL throws, so every card drawn on the post's picture would fail to export. */
  const p = new Promise((res) => {
    const im = new Image();
    if (!/^(data|blob):/.test(src)) im.crossOrigin = "anonymous";
    im.onload = () => res(im); im.onerror = () => res(null); im.src = src;
  });
  _imgCache.set(src, p); return p;
}
/* The brand mark, measured rather than assumed.
   The logo file is 240x170 but its INK is only 230x35, sitting between y 77 and y 112 --
   the artwork occupies a fifth of the file's height and the rest is transparent padding.
   So drawing it into a box sized by the file makes the visible mark about a fifth of the
   size the box suggests, which is why the footer mark reads small. Trimming to the alpha
   bounding box means a height asked for here is the height of the mark you actually see.
   The bbox is computed from the pixels, not written down, so replacing the logo file needs
   no numbers changed anywhere. */
let _logoInk = null;
async function logoInk() {
  if (_logoInk) return _logoInk;
  const im = await loadImg(LOGO);
  if (!im) return (_logoInk = { im: null });
  try {
    const c = document.createElement("canvas");
    c.width = im.width; c.height = im.height;
    const x = c.getContext("2d", { willReadFrequently: true });
    x.drawImage(im, 0, 0);
    const d = x.getImageData(0, 0, c.width, c.height).data;
    let x0 = c.width, y0 = c.height, x1 = -1, y1 = -1;
    for (let py = 0; py < c.height; py++) for (let px = 0; px < c.width; px++) {
      if (d[(py * c.width + px) * 4 + 3] > 8) {
        if (px < x0) x0 = px; if (px > x1) x1 = px;
        if (py < y0) y0 = py; if (py > y1) y1 = py;
      }
    }
    if (x1 < 0) return (_logoInk = { im, sx: 0, sy: 0, sw: im.width, sh: im.height });
    return (_logoInk = { im, sx: x0, sy: y0, sw: x1 - x0 + 1, sh: y1 - y0 + 1 });
  } catch (e) {
    /* A tainted or unreadable canvas is not a reason to lose the mark: fall back to the
       whole file, which draws correctly, just with its original padding. */
    return (_logoInk = { im, sx: 0, sy: 0, sw: im.width, sh: im.height });
  }
}
/* The top-left mark. Wan, 19 Sep 2026: "replace @ws.regulab with ws.regulab actual logo and
   make it bigger a bit not too big" -- so the handle text goes and the mark takes its place
   at 34u tall against the old text's 24u, with the width following the ink's real 6.57:1.
   Rule 7 is absolute here: LinkedIn carries NO ws.regulab identity, so that stream draws
   nothing unless a draft names its own handle, and a named handle stays text. Over a
   photograph or a dark slide the mark is knocked out in white with a shadow, the same
   treatment the footer already uses, because its own dark green disappears into a scrim. */
async function drawBrandMark(ctx, spec, W, u, M, opts) {
  const o = opts || {};
  const custom = spec.handle && spec.handle !== "@ws.regulab" ? spec.handle : "";
  const top = Math.round((o.top || 58) * u);
  if (custom) {
    ctx.font = "700 " + Math.round(24 * u) + "px " + G_MONO;
    ctx.fillStyle = o.textFill || "rgba(21,23,27,.5)";
    ctx.textBaseline = "top"; ctx.fillText(custom, M, top);
    return;
  }
  if (spec.stream === "linkedin") return;
  const ink = await logoInk();
  if (!ink || !ink.im) return;
  // top right on every ws.regulab card (Wan, 11 Nov 2026: "logo actual ws regulab dekat top right slide"); a caller may still say right:false
  const right = o.right !== false;
  const h = Math.round((o.h || 34) * 1.2 * u), w = Math.round(h * (ink.sw / ink.sh));
  if (o.knockout) {
    const oc = document.createElement("canvas");
    oc.width = Math.max(1, w); oc.height = Math.max(1, h);
    const octx = oc.getContext("2d");
    octx.drawImage(ink.im, ink.sx, ink.sy, ink.sw, ink.sh, 0, 0, w, h);
    octx.globalCompositeOperation = "source-in";
    octx.fillStyle = "#FFFFFF"; octx.fillRect(0, 0, w, h);
    ctx.save();
    ctx.shadowColor = "rgba(0,0,0,.45)"; ctx.shadowBlur = Math.round(10 * u);
    ctx.drawImage(oc, right ? W - M - w : M, top, w, h);
    ctx.restore();
  } else {
    ctx.drawImage(ink.im, ink.sx, ink.sy, ink.sw, ink.sh, right ? W - M - w : M, top, w, h);
  }
}
/* A TOKEN WIDER THAN THE COLUMN IS DRAWN PAST THE EDGE AND CLIPPED, silently. Every wrapper
   in this file breaks on whitespace only, so anything with no space in it -- a reference like
   NPRA.600-1/9/13(13)Jld.2), a DOI, a long registration number -- overflows the card with no
   error anywhere. y9bs3cciyb's slide 5 lost the tail of its NPRA reference exactly that way,
   on a card whose whole job is to carry that reference. Split it character by character: a
   reference wrapped mid-run is readable, a reference cut off is a wrong fact. The check is
   cheap and a token that fits returns untouched, so nothing that renders today moves. */
function hardSplit(ctx, word, maxW) {
  if (!word || ctx.measureText(word).width <= maxW) return [word];
  const out = []; let cur = "";
  for (const ch of word) {
    const t = cur + ch;
    if (cur && ctx.measureText(t).width > maxW) { out.push(cur); cur = ch; } else cur = t;
  }
  if (cur) out.push(cur);
  return out;
}
function wrapLines(ctx, text, maxW) {
  const out = [];
  for (const para of stripEmph(text).split("\n")) {
    const words = para.split(/\s+/).filter(Boolean).flatMap(w => hardSplit(ctx, w, maxW)); let line = "";
    if (!words.length) { out.push(""); continue; }
    for (const w of words) { const t = line ? line + " " + w : w; if (ctx.measureText(t).width > maxW && line) { out.push(line); line = w; } else line = t; }
    out.push(line);
  }
  return out;
}
function fitText(ctx, text, maxW, maxH, { family, weight = 600, max = 96, min = 30, lh = 1.16 }) {
  for (let size = max; size >= min; size -= 2) {
    ctx.font = `${weight} ${size}px ${family}`;
    const lines = wrapLines(ctx, text, maxW);
    if (lines.length * size * lh <= maxH) return { lines, size, lh, clipped: 0 };
  }
  ctx.font = `${weight} ${min}px ${family}`;
  const all = wrapLines(ctx, text, maxW);
  const lines = all.slice(0, Math.max(1, Math.floor(maxH / (min * lh))));
  const clipped = all.length - lines.length;
  if (clipped > 0) lines[lines.length - 1] = lines[lines.length - 1].replace(/[\s,;:.\u2013\u2014-]+$/, "") + "\u2026";
  return { lines, size: min, lh, clipped };
}
/* renderCard returns {url, warn}. The warnings used to live in a module-level array, which
   the template-catalogue thumbnails would have clobbered mid-flight: they render while the
   live preview is still awaiting its fonts. Each render now carries its own. */
function warnClip(warn, fit, what) { if (fit.clipped) warn.push(what + " is too long for this card \u2014 it was cut with an ellipsis. Shorten it, or move the detail to the caption."); }
function drawEyebrow(ctx, text, M, y, W, family, warn) {
  const maxW = W - M * 2, sp = Math.round(W * 0.004);
  let chars = [...String(text).toUpperCase()], size = Math.round(W * 0.026);
  const width = () => { ctx.font = `600 ${size}px ${family}`; let t = -sp; for (const ch of chars) t += ctx.measureText(ch).width + sp; return t; };
  while (size > Math.round(W * 0.018) && width() > maxW) size -= 1;
  if (width() > maxW) {
    while (chars.length > 5 && width() > maxW) chars.pop();
    chars[chars.length - 1] = "\u2026";
    if (warn) warn.push("The eyebrow is too long for the card and was shortened. Two or three words read best.");
  }
  ctx.font = `600 ${size}px ${family}`;
  let x = M; for (const ch of chars) { ctx.fillText(ch, x, y + size); x += ctx.measureText(ch).width + sp; }
}
function roundRect(ctx, x, y, w, h, r) { ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r); ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath(); }
function coverDraw(ctx, im, W, H) {
  const s = Math.max(W / im.width, H / im.height), w = im.width * s, h = im.height * s;
  ctx.drawImage(im, (W - w) / 2, (H - h) / 2, w, h);
}
/* A photograph used as a BACKGROUND is softened before the words go on it (Wan, 8 Nov 2026: "for any slide design which using photo
   as background, make the photo blur or less contrast so the wording still clear to read"). A sharp, contrasty photo under a
   scrim still fights the type: edges and highlights cross the letters. Two cheap changes: blur it, and pull it toward a flat
   tone (a veil: mid-grey over a dark ground, white over a light one), which lowers its contrast without a filter API.
   The blur is made by drawing the picture small and back up in halving steps with smoothing on, NOT with ctx.filter, which
   iPhone Safari before 18 does not have. It only runs where a photo is the ground UNDER words; the hero photo of p_fact and
   p_split (words sit below it, not on it) is a design choice and stays sharp: those two call paintBg/photo with a shorter height. Pure canvas, so web/cards.test.mjs can see it. */
export const SOFT = { blurDivisor: 50, veilDark: "rgba(118,124,130,.34)", veilLight: "rgba(255,255,255,.22)" };
function coverSoft(ctx, im, w, h, light) {
  const f = Math.max(2, Math.round(Math.min(w, h) / SOFT.blurDivisor));      // 1080 px → 12: a blur radius of roughly a hundredth of the card
  const tw = Math.max(8, Math.round(w / f)), th = Math.max(8, Math.round(h / f));
  const mk = (cw, ch) => { const c = document.createElement("canvas"); c.width = cw; c.height = ch; return c; };
  let cur = mk(tw, th);
  const g0 = cur.getContext("2d"); g0.imageSmoothingEnabled = true; g0.imageSmoothingQuality = "high";
  coverDraw(g0, im, tw, th);                                                  // cover-crop straight to the small size
  // back up in doubling steps: each step smooths again, so the result is a soft blur and not visible blocks
  let cw = tw, ch = th;
  while (cw < w) {
    const nw = Math.min(w, cw * 2), nh = Math.min(h, ch * 2);
    const nxt = mk(nw, nh), g = nxt.getContext("2d");
    g.imageSmoothingEnabled = true; g.imageSmoothingQuality = "high";
    g.drawImage(cur, 0, 0, cw, ch, 0, 0, nw, nh);
    cur = nxt; cw = nw; ch = nh;
  }
  ctx.save(); ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = "high";
  ctx.drawImage(cur, 0, 0, cw, ch, 0, 0, w, h);
  ctx.fillStyle = light ? SOFT.veilLight : SOFT.veilDark; ctx.fillRect(0, 0, w, h);
  ctx.restore();
}
/* How much of the ground the words are allowed to cover. Light keeps a design readable as a
   design; heavy is the old behaviour, for a busy photograph. */
/* The ramp used to start at .10-.44 and only get dark at the foot, which is where a photo
   card puts its source line, not its headline. The headline sits in the top half, so the top
   stop now carries real weight at every level. Set from the ground's measured brightness. */
/* ===================== the grid family =====================================
   Wan, 19 Sep 2026, from a reference carousel he sent: cream graph paper for the
   content slides, a charcoal grid for the summary ones, an ultra-bold display face
   with one word in the accent, raised panels with dashed rules, marker sticky notes,
   and a chip where a reference deck would put an agency logo.
   The chip is typographic ON PURPOSE. A regulator's mark on our own artwork reads as
   that regulator endorsing the post, and the same "impression of endorsement" principle
   that governs Annex I Part 8 s4.1 is a bad thing to model for an audience of
   notification holders. The chip names the instrument instead, which is the useful half.
   Swap in a real mark only from a logo file Wan puts in the store himself.

   These draw through renderGridCard and share nothing with the older layout but the
   canvas. Put *asterisks* round a word in the headline to give it the accent colour. */
const G_HEAD = 'Poppins, "Instrument Sans", system-ui, sans-serif';
const G_BODY = '"Instrument Sans", system-ui, sans-serif';
const G_MONO = '"JetBrains Mono", ui-monospace, monospace';
const G_MARK = 'Caveat, "Instrument Sans", cursive';

/* Draw a photograph as the card's ground, with the same scrim the photo family uses.
   **Grid and ERA ignored `spec.bg` entirely until 22 Sep 2026**, and that is what Wan hit:
   *"use this background on all 8 slides not function"*. The button was never the fault. It
   set `bg_media_id` on all eight slides correctly, the toast said so, `renderAndUse` carried
   every slide's own spec into `storeCard`, and `storeCard` resolved the bytes — and then
   `renderGridCard` and `renderEraCard` painted their opaque paper over the top without ever
   reading `spec.bg`. Only `renderPhotoCard` drew a ground. So the Background select and the
   all-slides button were live controls wired to nothing for two of the three families, which
   is also why rule 4's "one ground per domain, on EVERY slide" never looked like it worked.
   Proved by rendering the same spec with and without a ground and comparing the pixels:
   `g_title`, `g_rows` and `e_explain` came back IDENTICAL, `p_title` and `p_fact` differed.
   A card with NO ground must still paint exactly as it did before, which is why this is an
   `else` around the existing `gPaper`/`eraPaper` call rather than a change to either. */
/* A LIGHT GROUND keeps dark ink and no scrim (Wan, 4 Oct 2026, from a pink glass-sphere event poster: "make sure the AI can
   generate the same background as per attached"). A ground used to be a photograph under a dark scrim with white ink, so a
   pale, airy background came out grey and heavy. Now the ground's own brightness decides, unless a scrim was chosen on
   purpose (`auto_scrim` false): scrim "none" forces it, and the Photo family keeps its dark treatment always. */
const toneCache = new Map();
async function groundIsLight(spec) {
  if (!spec || !spec.bg) return false;
  if (spec.scrim === "none") return true;
  if (spec.auto_scrim === false) return false;
  const key = String(spec.bg).length + ":" + String(spec.bg).slice(-96);
  if (toneCache.has(key)) return toneCache.get(key);
  let light = false;
  try {
    const img = await loadImg(spec.bg);
    if (img) {
      const c = document.createElement("canvas"); c.width = 32; c.height = 32;
      const g = c.getContext("2d", { willReadFrequently: true });
      coverDraw(g, img, 32, 32);
      const d = g.getImageData(0, 0, 32, 32).data, lum = [];
      for (let i = 0; i < d.length; i += 4) lum.push(0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2]);
      lum.sort((a, b) => a - b);
      light = lum[Math.floor(lum.length * 0.4)] >= 168;        // the 40th percentile: a bright subject on a dark ground stays dark
    }
  } catch (e) { light = false; }
  toneCache.set(key, light);
  return light;
}
/* White ink and a knocked-out logo: over a ground that is dark (a scrim, or a dark picture), never over a light one. */
const inkWhite = (spec) => !!(spec && spec.bg && !spec._light);

async function drawGround(ctx, spec, W, H) {
  if (!spec || !spec.bg) return false;
  let img = null;
  try { img = await loadImg(spec.bg); } catch (e) { return false; }
  if (!img) return false;
  coverSoft(ctx, img, W, H, !!spec._light);
  const sc = SCRIM[spec.scrim] || SCRIM.medium;
  const g = ctx.createLinearGradient(0, 0, 0, H);
  g.addColorStop(0, `rgba(9,24,30,${sc[0]})`); g.addColorStop(0.42, `rgba(9,24,30,${sc[1]})`); g.addColorStop(1, `rgba(9,24,30,${sc[2]})`);
  ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
  return true;
}
function gPaper(ctx, W, H, dark) {
  ctx.fillStyle = dark ? GRID_PAL.dark : GRID_PAL.cream; ctx.fillRect(0, 0, W, H);
  ctx.strokeStyle = dark ? GRID_PAL.darkGrid : GRID_PAL.grid; ctx.lineWidth = 1;
  const step = Math.round(W / 32);
  ctx.beginPath();
  for (let x = 0; x <= W; x += step) { ctx.moveTo(x + 0.5, 0); ctx.lineTo(x + 0.5, H); }
  for (let y = 0; y <= H; y += step) { ctx.moveTo(0, y + 0.5); ctx.lineTo(W, y + 0.5); }
  ctx.stroke();
  if (dark) {
    const g = ctx.createRadialGradient(W * 0.5, H * 1.02, 60, W * 0.5, H * 1.02, W * 0.85);
    g.addColorStop(0, "rgba(74,58,210,.5)"); g.addColorStop(1, "rgba(20,23,28,0)");
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
  }
}
function gRound(ctx, x, y, w, h, r) {
  ctx.beginPath(); ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
}
function gPanel(ctx, x, y, w, h, o) {
  o = o || {};
  const r = o.r == null ? 26 : o.r;
  ctx.save();
  if (o.shadow !== false) { ctx.shadowColor = "rgba(21,23,27,.13)"; ctx.shadowBlur = 26; ctx.shadowOffsetY = 8; }
  ctx.fillStyle = o.fill || GRID_PAL.panel; gRound(ctx, x, y, w, h, r); ctx.fill();
  ctx.restore();
  if (o.stroke) { ctx.strokeStyle = o.stroke; ctx.lineWidth = 3; gRound(ctx, x, y, w, h, r); ctx.stroke(); }
}
/* `*word*` is the authoring convention for emphasis, and only gHeadline and eraMark can
   actually colour it -- both tokenise through gTokens and never come through here. Every
   OTHER text helper was printing the asterisks on the artwork: e_explain's red band read
   "Notifikasi *bukan* kelulusan", and the same leaked into leads, bubbles, stickies, chips
   and bullets. The marker is syntax, not content, so a helper that cannot colour it must
   still never show it. Stripping in the two wrap functions fixes all seven at once, because
   every non-parsing helper wraps through one of them and neither parser does. A lone
   asterisk is left alone; only a matched pair on one line is a marker. */
function stripEmph(t) { return String(t == null ? "" : t).replace(/\*([^*\n]+)\*/g, "$1"); }
function gWrap(ctx, text, maxW) {
  const out = [];
  for (const para of stripEmph(text).split("\n")) {
    const words = para.split(/\s+/).filter(Boolean).flatMap(w => hardSplit(ctx, w, maxW));
    if (!words.length) { continue; }
    let line = "";
    for (const w of words) {
      const t = line ? line + " " + w : w;
      if (ctx.measureText(t).width > maxW && line) { out.push(line); line = w; } else line = t;
    }
    if (line) out.push(line);
  }
  return out;
}
function gPara(ctx, text, x, y, maxW, px, lh, colour, weight) {
  ctx.font = (weight || 500) + " " + px + "px " + G_BODY;
  ctx.fillStyle = colour; ctx.textBaseline = "top";
  for (const l of gWrap(ctx, text, maxW)) { ctx.fillText(l, x, y); y += lh; }
  return y;
}
/* *word* takes the accent. Everything else takes the base colour. */
function gTokens(text, base, accent) {
  const out = [];
  for (const part of String(text || "").split(/(\*[^*]+\*)/)) {
    if (!part) continue;
    if (part.length > 2 && part[0] === "*" && part[part.length - 1] === "*") out.push({ t: part.slice(1, -1), c: accent });
    else out.push({ t: part, c: base });
  }
  return out.length ? out : [{ t: "", c: base }];
}
function gHeadline(ctx, text, x, y, maxW, px, lh, base, accent) {
  ctx.font = "800 " + px + "px " + G_HEAD; ctx.textBaseline = "top";
  const words = [];
  for (const tk of gTokens(text, base, accent)) {
    for (const w of tk.t.split(/(\s+)/)) {
      if (w === "") continue;
      if (/^\s+$/.test(w)) { words.push({ w: w, c: tk.c }); continue; }
      // hardSplit needs the font already set, which both callers do on the line above.
      for (const piece of hardSplit(ctx, w, maxW)) words.push({ w: piece, c: tk.c });
    }
  }
  let line = [], lw = 0, yy = y;
  const flush = () => {
    let xx = x;
    for (const it of line) { ctx.fillStyle = it.c; ctx.fillText(it.w, xx, yy); xx += ctx.measureText(it.w).width; }
    yy += lh; line = []; lw = 0;
  };
  for (const it of words) {
    const w = ctx.measureText(it.w).width;
    if (/^\s+$/.test(it.w) && lw === 0) continue;
    if (lw + w > maxW && lw > 0) { flush(); if (/^\s+$/.test(it.w)) continue; }
    line.push(it); lw += w;
  }
  if (line.length) flush();
  return yy;
}
/* The small label over the headline. It comes down in size until it fits between the two side margins (a long domain name such
   as "Sains kosmetik (penerbitan terkini)" used to run under the logo and off the card), and wraps when even that is not enough.
   A label that fits is drawn exactly as before and takes the same height. */
function gEyebrow(ctx, text, x, y, colour, px) {
  if (!text) return y;
  const label = stripEmph(text).toUpperCase(), room = (ctx.canvas ? ctx.canvas.width : 1080) - x * 2, px0 = px;
  ctx.save(); ctx.textBaseline = "top";
  const set = () => { ctx.font = "700 " + px + "px " + G_HEAD; try { ctx.letterSpacing = Math.round(px * 0.17) + "px"; } catch (e) { } };
  set();
  while (px > Math.round(px0 * 0.7) && ctx.measureText(label).width > room) { px -= 1; set(); }
  const lines = ctx.measureText(label).width > room ? gWrap(ctx, label, room) : [label];
  ctx.fillStyle = colour;
  lines.forEach((l, i) => ctx.fillText(l, x, y + i * Math.round(px * 1.35)));
  try { ctx.letterSpacing = "0px"; } catch (e) { }
  ctx.restore();
  return y + Math.round(px0 * 2.2) + (lines.length - 1) * Math.round(px * 1.35);
}
/* The source line (Wan, 19 Sep 2026: "can the source be small text at the bottom not in the
   box"). It was a raised chip -- a panel, an accent bar, its own background -- and he wanted
   what the old cards always had instead: a plain small line pinned to the card's own bottom
   margin, the same place a footnote sits, never a box. Label and reference share one line
   where they fit and wrap to two when they do not; the label carries the accent colour so
   the instrument still reads at a glance, without anything drawn around it. */
function gSourceLine(ctx, W, H, M, u, label, ref, dark) {
  if (!label && !ref) return;
  const px = Math.round(21 * u), gap = Math.round(px * 0.55);
  const muted = dark ? "rgba(255,255,255,.5)" : GRID_PAL.muted;
  ctx.textBaseline = "top";
  ctx.font = "500 " + px + "px " + G_MONO;
  const labelW = label ? ctx.measureText(label + (ref ? " ·" : "")).width : 0;
  const refLines = ref ? gWrap(ctx, ref, W - M * 2 - (label ? labelW + gap : 0)) : [];
  // Two lines are enough for a citation this small; a longer one wraps past the card's own
  // bottom margin, which the "slide is fuller than the card" warning already catches.
  const lineCount = Math.max(1, refLines.length);
  let y = H - M - lineCount * Math.round(px * 1.4);
  if (label) {
    ctx.fillStyle = GRID_PAL.orange;
    ctx.fillText(label + (ref ? " ·" : ""), M, y);
  }
  if (ref) {
    ctx.font = "400 " + px + "px " + G_MONO; ctx.fillStyle = muted;
    let rx = M + (label ? labelW + gap : 0), ry = y;
    refLines.forEach((l, i) => {
      ctx.fillText(l, i === 0 ? rx : M, ry);
      ry += Math.round(px * 1.4);
    });
  }
}
function gSticky(ctx, x, y, w, text, fill, rot, px) {
  ctx.save(); ctx.font = "700 " + px + "px " + G_MARK;
  const lines = gWrap(ctx, text, w - px);
  const h = lines.length * Math.round(px * 1.1) + Math.round(px * 1.1);
  ctx.translate(x + w / 2, y + h / 2); ctx.rotate(rot); ctx.translate(-w / 2, -h / 2);
  ctx.shadowColor = "rgba(21,23,27,.2)"; ctx.shadowBlur = 22; ctx.shadowOffsetY = 8;
  ctx.fillStyle = fill; ctx.fillRect(0, 0, w, h); ctx.shadowColor = "transparent";
  ctx.fillStyle = "#2A2340"; ctx.textBaseline = "top";
  let yy = Math.round(px * 0.55);
  for (const l of lines) { ctx.fillText(l, Math.round(px * 0.55), yy); yy += Math.round(px * 1.1); }
  ctx.restore();
  return h;
}
function gSparks(ctx, cx, cy, n, colour, len, rad) {
  ctx.save(); ctx.strokeStyle = colour; ctx.lineWidth = Math.max(4, Math.round(len * 0.3)); ctx.lineCap = "round";
  for (let i = 0; i < n; i++) {
    const a = -0.9 + i * (1.9 / Math.max(1, n - 1));
    ctx.beginPath();
    ctx.moveTo(cx + Math.cos(a) * rad, cy + Math.sin(a) * rad);
    ctx.lineTo(cx + Math.cos(a) * (rad + len), cy + Math.sin(a) * (rad + len));
    ctx.stroke();
  }
  ctx.restore();
}
function gBubble(ctx, x, y, w, text, px) {
  ctx.font = "600 " + px + "px " + G_BODY;
  const lines = gWrap(ctx, text, w - px * 1.9);
  const h = lines.length * Math.round(px * 1.4) + Math.round(px * 1.6);
  gPanel(ctx, x, y, w, h, { fill: GRID_PAL.panel, r: 24 });
  const tx = x + Math.round(w * 0.22);
  ctx.fillStyle = GRID_PAL.panel;
  ctx.beginPath(); ctx.moveTo(tx, y + h - 2); ctx.lineTo(tx + Math.round(px * 1.1), y + h - 2);
  ctx.lineTo(tx + Math.round(px * 0.3), y + h + Math.round(px)); ctx.closePath(); ctx.fill();
  ctx.fillStyle = GRID_PAL.ink; ctx.textBaseline = "top";
  let yy = y + Math.round(px * 0.8);
  for (const l of lines) { ctx.fillText(l, x + Math.round(px * 0.95), yy); yy += Math.round(px * 1.4); }
  return y + h + Math.round(px);
}
/* Split "a | b | c" and keep empty cells out of the way. */
function gCells(line) { return String(line || "").split("|").map(t => t.trim()); }

/* A context that measures but never paints.
   Vertical centring needs the height of the content BEFORE the content is drawn, and the
   layout is a single downward pass through the same code that paints. Rather than keep a
   parallel measuring copy of every template -- which would drift the first time one of
   them changed -- the painter runs twice: once against this proxy to learn where it ends,
   then for real with the block shifted. Text metrics come from the real context, so
   measureText and the font property are the only things that pass through. Gradient
   factories return a stub because callers immediately call addColorStop on the result. */
const MEASURE_PROPS = ["font", "textBaseline", "textAlign", "direction", "fontKerning", "textRendering"];
function measureProxy(ctx) {
  const noop = () => { };
  const stubGrad = () => ({ addColorStop: noop });
  return new Proxy(ctx, {
    get(t, k) {
      if (k === "measureText") return t.measureText.bind(t);
      if (k === "createLinearGradient" || k === "createRadialGradient" || k === "createConicGradient") return stubGrad;
      if (k === "createPattern") return () => null;
      const v = t[k];
      return typeof v === "function" ? noop : v;
    },
    /* SEMASA: only what measureText reads is carried out of a measuring pass. save() and restore() are no-ops here, so
       any other property a painter sets and later puts back that way (letterSpacing in gEyebrow, globalAlpha in
       eraPaper) stayed set on the real context: the first pass left 4px of tracking on every word the second pass drew
       and, through ERA's paper, drew the whole card at half strength. */
    set(t, k, v) { if (MEASURE_PROPS.includes(k)) { try { t[k] = v; } catch (e) { } } return true; },
  });
}
/* Where the words sit between the handle at the top and the source line pinned to the
   bottom margin. Both are drawn outside the content block and must not be centred into. */
function cardZone(H, u, topU, floor) {
  return { top: Math.round((topU || 150) * u), bottom: floor || H - Math.round(150 * u) };
}
/* Where the words must stop. 150u above the bottom edge clears a source line of one or two lines; a long citation wraps to
   more, and the floor then rises with it, so the words can never sit on the source (it is drawn last, pinned to the bottom
   margin, whatever is above it). Measured with the same wrapping gSourceLine draws with. */
function cardFloor(ctx, spec, W, H, M, u) {
  return Math.min(H - Math.round(150 * u), sourceTop(ctx, spec, W, H, M, u) - Math.round(22 * u));
}
/** The top of the source line as gSourceLine will draw it (the card's own height when there is none). */
function sourceTop(ctx, spec, W, H, M, u) {
  const label = spec.chip_label || (spec.footnote ? "Sumber" : ""), ref = spec.footnote || "";
  if (!ref) return H;
  const px = Math.round(21 * u), gap = Math.round(px * 0.55);
  ctx.font = "500 " + px + "px " + G_MONO;
  const labelW = label ? ctx.measureText(label + " ·").width : 0;
  ctx.font = "400 " + px + "px " + G_MONO;
  const n = Math.max(1, gWrap(ctx, ref, W - M * 2 - (label ? labelW + gap : 0)).length);
  return H - M - n * Math.round(px * 1.4);
}
function centreShift(H, u, contentEndY, topU, floor) {
  const z = cardZone(H, u, topU, floor);
  const slack = (z.bottom - z.top) - Math.max(0, contentEndY - z.top);
  /* Never pull content upward past its own start, and never centre a block that already
     fills the card -- a negative shift would push the last line under the source line. */
  return slack > 0 ? Math.round(slack / 2) : 0;
}
async function renderGridCard(spec) {
  const [W, H] = sizeOf(spec);
  const c = document.createElement("canvas"); c.width = W; c.height = H;
  const ctx = styleCtx(c.getContext("2d"), spec);                  // SEMASA: the slide's own face, when it chose one
  try { await document.fonts.ready; } catch (e) { }
  const u = W / 1080;
  /* Wan, 19 Sep 2026: "make sure the design and render ensure the text is middle of card".
     The type scale is fixed on purpose (a short lead must not grow the headline), so a
     slide with little text used to sit high with a dead band beneath it. Measuring first
     and shifting the whole block keeps every size exactly as it is and moves the words. */
  const M = Math.round(72 * u), floor = cardFloor(ctx, spec, W, H, M, u);
  const measure = (sp) => gridCardPaint(measureProxy(ctx), sp, W, H, 0);
  const probe = await measure(spec);
  /* Wan, 9 Nov 2026: "make sure each carousel page is compact, not looks empty". A slide with a headline and a line or two used to
     sit in the middle of a card that was half blank. The type now grows to fill the card: the largest scale (at most FILL_MAX) at
     which the content still ends inside FILL_TARGET of the room between the handle and the source line, found by measuring, never
     by guessing. A person's own text size is respected and a slide with a mascot already fills its space with the character.
     16 Nov 2026 (auto-fit): the same search now runs the other way too. A slide that is fuller than the card shrinks until every
     word is above the source line, and the growth stops before the longest word would be cut in two (wordCap). */
  const max = Math.min(HOOK_TPL[spec.template] ? FILL_MAX : FILL_BODY_MAX, gridWordCap(ctx, spec, W));
  const fill = spec.type_size || spec.mascot ? 1 : await fillScale(spec, H, u, 150, probe.y, measure, max, FILL_FROM, FILL_TARGET, floor);
  const drawn = fill !== 1 ? { ...spec, _fill: fill } : spec;
  const end = fill !== 1 ? (await measure(drawn)).y : probe.y;
  return gridCardPaint(ctx, drawn, W, H, centreShift(H, u, end, 150, floor), c);
}
/* How far a card may grow before one of its words no longer fits its column: every wrapper breaks an over-wide word letter by
   letter (hardSplit), and a headline cut as "NOTIFIKAS / I" is worse than a smaller one. parts = [text, size in 1080-wide units,
   weight, family, column width in pixels]. A token that is already wider than its column at the template's own size (a long
   reference) is split whatever the scale, so it does not hold the rest of the card back. */
function wordCap(ctx, u, parts) {
  let cap = Infinity;
  for (const [text, px, weight, fam, colW] of parts) {
    if (!text || !(colW > 0)) continue;
    ctx.font = weight + " " + Math.round(px * u) + "px " + fam;
    for (const w of stripEmph(String(text)).split(/\s+/).filter(Boolean)) {
      const ww = ctx.measureText(w).width;
      if (ww > 0 && ww <= colW) cap = Math.min(cap, (colW / ww) * 0.97);
    }
  }
  return cap;
}
function gridWordCap(ctx, spec, W) {
  const u = W / 1080, maxW = W - Math.round(72 * u) * 2, t = spec.template;
  const rows = (spec.items || []).map((x) => String(x || "").trim()).filter(Boolean).map(gCells);
  const figure = t === "g_stat" && rows.length;
  const parts = [[spec.title, figure ? 58 : 80, 800, G_HEAD, maxW], [t === "g_bars" ? "" : spec.lead, 34, 500, G_BODY, Math.round(maxW * 0.92)]];
  if (t === "g_rows") for (const r of rows) parts.push([r[0], 36, 700, G_HEAD, maxW - Math.round(160 * u)], [r.slice(1).join(" "), 30, 500, G_BODY, maxW - Math.round(160 * u)]);
  if (t === "g_table") for (const r of rows) parts.push([r[1], 34, 700, G_HEAD, maxW - Math.round(180 * u)], [r[2], 27, 500, G_BODY, maxW - Math.round(180 * u)]);
  if (t === "g_bars") for (const r of rows) parts.push([r[0], 30, 600, G_BODY, maxW - Math.round(76 * u)]);
  return wordCap(ctx, u, parts);
}
/* A hook (the cover, the closing line) is drawn very large; every other slide only grows a little, so it still reads as the full card
   Wan asked for (headline, lead, numbered panels) and a slide with little to say is not blown up into a poster. */
/* 16 Nov 2026 (auto-fit: "no card left half empty with small text"): a body slide may now grow to 2.2 (it stopped at 1.35, which
   left a slide of one short point as a small block in the upper third of the card). A slide with a lead and three or four points
   already fills its card and is not touched; the ceiling only decides how a sparse one looks. */
const FILL_MAX = 3, FILL_BODY_MAX = 2.2, FILL_FROM = 0.72, FILL_TARGET = 0.86;
const HOOK_TPL = { g_title: 1, p_title: 1, p_quote: 1 };
/* The scale (1 to FILL_MAX) at which a slide's content fills its card. `measure(spec)` runs the family's own painter against the
   measuring proxy and returns where the content ends; `topU` is where the content starts, in 1080-wide units. */
async function fillScale(spec, H, u, topU, endY, measure, max = FILL_MAX, from = FILL_FROM, target = FILL_TARGET, floor = 0) {
  const z = cardZone(H, u, topU, floor);
  const room = z.bottom - z.top;
  const used = (y) => Math.max(0, y - z.top);
  if (room <= 0) return 1;
  const at = async (f) => used((await measure({ ...spec, _fill: f })).y);
  return fitSearch(at, used(endY), room, max, from, target);
}
/* The one search behind every family's fit. `at(f)` is how much of the room the content takes at scale f (measured, never
   guessed), `used1` what it takes at 1. Fuller than the room: the largest scale down to FIT_MIN at which it fits, and FIT_MIN
   itself when nothing fits (the painter then warns). Under `from` of the room: the largest scale up to `max` at which it
   stays inside `target` of it. The height is not a smooth function of the size (one more pixel can push a word to the next
   line), so whatever the search lands on is checked and stepped down until the card really holds it. */
async function fitSearch(at, used1, room, max = FILL_MAX, from = FILL_FROM, target = FILL_TARGET, min = FIT_MIN) {
  let f = 1;
  if (used1 > room) {
    if ((await at(min)) > room) return min;
    let lo = min, hi = 1;
    for (let i = 0; i < 7; i++) { const mid = (lo + hi) / 2; if ((await at(mid)) <= room) lo = mid; else hi = mid; }
    f = Math.floor(lo * 100) / 100;
    for (let i = 0; i < 20 && f > min && (await at(f)) > room; i++) f = Math.round((f - 0.01) * 100) / 100;
    return Math.max(min, f);
  }
  if (used1 >= from * room || max <= 1.03) return 1;                      // already compact, or nothing may grow
  if ((await at(max)) < used1 * 1.12) return 1;                           // this layout's height does not follow its text
  let lo = 1, hi = max;
  for (let i = 0; i < 7; i++) { const mid = (lo + hi) / 2; if ((await at(mid)) <= target * room) lo = mid; else hi = mid; }
  f = Math.floor(lo * 100) / 100;
  for (let i = 0; i < 20 && f > 1 && (await at(f)) > room; i++) f = Math.round((f - 0.02) * 100) / 100;
  return f > 1.03 ? f : 1;
}
async function gridCardPaint(ctx, spec, W, H, yShift, canvasOut) {
  const warn = [];
  const t = spec.template;
  const dark = !!GRID_DARK[t] || inkWhite(spec);   // a photograph is always a dark card
  const u = W / 1080;                    // every measurement below is in 1080-wide units
  const M = Math.round(72 * u);
  const maxW = W - M * 2;
  const accent = GRID_PAL.orange;
  const ink = dark ? "#FFFFFF" : GRID_PAL.ink;
  const muted = dark ? "rgba(255,255,255,.66)" : GRID_PAL.muted;
  const items = (spec.items || []).filter(x => String(x || "").trim());
  /* One fixed type scale for the whole carousel (Wan, 19 Sep 2026: "make sure text font
     size is standardize across the carousel... no font size change if we delete the
     text"). Every template's headline, body and item-heading text now share these three
     sizes rather than each template picking its own, and nothing here scales with how
     much text a field actually holds -- an empty lead just leaves blank space, it never
     grows the headline to fill it. (9 Nov 2026, Wan: "each carousel page is compact, not looks
     empty": renderGridCard now MEASURES the finished slide and, only when it fills too little of
     the card, runs the same layout at a larger scale -- see fillScale. The scale is one number
     for the slide, applied through TS, so every size on it still moves together.) g_stat's giant figure and its own subhead stay a
     deliberately separate, smaller tier: they are numerals, not the slide's headline. */
  const TS = textScale(spec);              // SEMASA: the person's own text size for this slide (100% = the template's)
  const HEAD_PX = Math.round(80 * u * TS), HEAD_LH = Math.round(90 * u * TS);
  const LEAD_PX = Math.round(34 * u * TS), LEAD_LH = Math.round(48 * u * TS);
  const ITEM_HEAD_PX = Math.round(36 * u * TS), ITEM_BODY_PX = Math.round(30 * u * TS), ITEM_BODY_LH = Math.round(40 * u * TS);
  const us = u * TS;                       // what sits inside a row or a panel (its padding, its number, its bar) moves with its words
  const noteK = Math.min(1, TS);           // a sticky note or a bubble never grows, but it shrinks with a full card

  if (!await drawGround(ctx, spec, W, H)) gPaper(ctx, W, H, dark);

  /* The handle. On ws.regulab it is the brand; on LinkedIn it is Wan's own byline, and
     rule 7 keeps every trace of the consultancy off that stream, so nothing is drawn
     there unless a handle was given. */
  await drawBrandMark(ctx, spec, W, u, M, {
    top: 56, h: 34, knockout: dark,
    textFill: dark ? "rgba(255,255,255,.62)" : "rgba(21,23,27,.5)",
  });

  let y = Math.round(150 * u) + (yShift || 0);
  y = gEyebrow(ctx, spec.eyebrow, M, y, accent, Math.round(24 * u));

  /* The mascot, when one is placed. It is drawn before the words on the dark slides and
     after them on the light ones, so it never sits on top of a headline. */
  const mascot = spec.mascot ? await loadImg(spec.mascot) : null;
  /* Small and bottom-anchored, not a headline-width figure (Wan, 19 Sep 2026: "make the
     mascot smaller and randomly place"). At 30% of the card's height it sits clear of the
     text column in every one of the three spots without needing to narrow it, which is
     also why headW below is just maxW again -- the earlier per-mascot narrowing existed
     only because the character used to take up half the card. */
  const mascotPos = mascot ? pickMascotPos(spec) : "br";
  const mascotMh = mascot ? Math.round(H * 0.30 * mascotScale(spec)) : 0;
  const mascotMw = mascot ? mascot.width * (mascotMh / mascot.height) : 0;
  const headW = maxW;
  const mascotX = mascotPos === "bl" ? M - Math.round(6 * u)
    : mascotPos === "bc" ? Math.round((W - mascotMw) / 2)
    : W - mascotMw - Math.round(20 * u);
  /* Docks just under the content, never past the reserved bottom margin (clear of the
     source line, drawn last regardless). Docking it to a fixed offset from H alone read
     fine on the square ws.regulab card but stranded it far below the text with a dead gap
     between on LinkedIn's taller one (Wan, 19 Sep 2026: "suitability for each... platform
     including linkedin") -- afterY lets it follow the actual content instead. */
  const mascotFloor = H - Math.round(90 * u);
  /* On dark, the character floated with no ground to stand on -- a soft warm glow behind
     it grounds it the way the light paper texture already does for free on the cream
     slides (Wan, 19 Sep 2026: "for dark slide adapt the mascot"). Light slides skip this
     entirely; the graph paper already does that job. */
  const drawMascotGlow = (cx, cy, r) => {
    const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, r);
    g.addColorStop(0, "rgba(255,255,255,.14)"); g.addColorStop(1, "rgba(255,255,255,0)");
    ctx.fillStyle = g; ctx.beginPath(); ctx.ellipse(cx, cy, r, r * 0.55, 0, 0, Math.PI * 2); ctx.fill();
  };
  const drawMascot = (afterY) => {
    if (!mascot) return;
    /* Stands down rather than sitting on the words: the items are never trimmed for it. */
    if ((afterY || 0) + Math.round(30 * u) + mascotMh > mascotFloor) return;
    const top = Math.min(mascotFloor - mascotMh, (afterY || 0) + Math.round(30 * u));
    if (dark) drawMascotGlow(mascotX + mascotMw / 2, top + mascotMh * 0.72, mascotMw * 0.62);
    ctx.drawImage(mascot, mascotX, top, mascotMw, mascotMh);
    return top + mascotMh;
  };
  /* The speech bubble sits opposite a bottom-left mascot so the two never overlap; every
     other position leaves the left side clear the way it always has. Its vertical position
     is passed at each call site instead of pinned near H, for the same reason as the
     mascot above. */
  const bubbleX = mascotPos === "bl" ? Math.max(M, W - M - Math.round(470 * u)) : M;

  if (t === "g_title") {
    y = gHeadline(ctx, spec.title || "", M, y, headW, HEAD_PX, HEAD_LH, ink, accent);
    y += Math.round(20 * u);
    if (spec.lead) y = gPara(ctx, spec.lead, M, y, Math.round(maxW * 0.92), LEAD_PX, LEAD_LH, muted);
    gSparks(ctx, W - Math.round(84 * u), Math.round(196 * u), 3, accent, Math.round(22 * u), Math.round(26 * u));
    /* Bubble and mascot both key off the same content-end y, so they land side by side at
       roughly one height rather than one stacking under the other. */
    const afterY = y;
    drawMascot(afterY);
    if (spec.note) y = Math.max(y, gBubble(ctx, bubbleX, afterY + Math.round(24 * u), Math.round(470 * u), spec.note, Math.round(30 * u * noteK)));
  } else if (t === "g_stat") {
    /* No figure given (items empty): this is the dark advice/hint slide, not a number
       slide (Wan, 19 Sep 2026: "make CTA as advice or hint what normally we miss" --
       the summary slide carries a substantive tip, never a growth-hack "comment X for
       the guide"). Same headline and body sizes as every other template, just on dark. */
    if (!items[0]) {
      y = gHeadline(ctx, spec.title || "", M, y, maxW, HEAD_PX, HEAD_LH, ink, accent);
      y += Math.round(20 * u);
      if (spec.lead) y = gPara(ctx, spec.lead, M, y, Math.round(maxW * 0.92), LEAD_PX, LEAD_LH, muted);
      gSparks(ctx, W - Math.round(84 * u), Math.round(196 * u), 3, accent, Math.round(22 * u), Math.round(26 * u));
      const statAfterY = y;
      drawMascot(statAfterY);
      if (spec.note) y = Math.max(y, gBubble(ctx, bubbleX, statAfterY + Math.round(24 * u), Math.round(470 * u), spec.note, Math.round(30 * u * noteK)));
    } else {
      const figure = items[0] || spec.title || "";
      const unit = items[1] || "";
      /* The figure is as large as the column allows, up to 300u: "RM240,000" at the full size ran off the right edge. Its unit
         sits beside it when there is room and under it, wrapped, when there is not. */
      const fpx = fitFigure(ctx, figure, maxW, Math.round(300 * us), G_HEAD);
      ctx.font = "800 " + fpx + "px " + G_HEAD; ctx.textBaseline = "top";
      ctx.fillStyle = ink; ctx.fillText(figure, M, y);
      const fw = ctx.measureText(figure).width, upx = Math.round(54 * us);
      ctx.font = "700 " + upx + "px " + G_HEAD;
      const beside = unit && fw + Math.round(28 * u) + ctx.measureText(unit).width <= maxW;
      if (beside) { ctx.fillStyle = accent; ctx.fillText(unit, M + fw + Math.round(28 * u), y + Math.round(fpx * 0.5)); }
      y += Math.round(fpx * 1.1);
      if (unit && !beside) {
        ctx.fillStyle = accent;
        for (const l of gWrap(ctx, unit, maxW)) { ctx.fillText(l, M, y); y += Math.round(upx * 1.22); }
        y += Math.round(16 * us);
      }
      /* This subhead sits under a giant numeral -- a deliberately smaller tier than the
         carousel's main headline, the same way it was before standardisation; only the
         body text below it joins the shared LEAD size. */
      if (spec.title) y = gHeadline(ctx, spec.title, M, y, maxW, Math.round(58 * u * TS), Math.round(70 * u * TS), ink, accent);
      y += Math.round(34 * u);
      if (spec.lead) y = gPara(ctx, spec.lead, M, y, Math.round(maxW * 0.95), LEAD_PX, LEAD_LH, muted);
      gSparks(ctx, W - Math.round(84 * u), Math.round(220 * u), 3, accent, Math.round(22 * u), Math.round(26 * u));
    }
  } else if (t === "g_bars") {
    y = gHeadline(ctx, spec.title || "", M, y, headW, HEAD_PX, HEAD_LH, ink, accent);
    y += Math.round(18 * us);
    if (spec.lead) {
      ctx.font = "700 " + Math.round(40 * us) + "px " + G_MARK; ctx.fillStyle = muted; ctx.textBaseline = "top";
      for (const l of gWrap(ctx, spec.lead, maxW)) { ctx.fillText(l, M, y); y += Math.round(46 * us); }
      y += Math.round(14 * us);
    }
    /* Every row is drawn and every label is wrapped (auto-fit, 16 Nov 2026): a long label used to run through the value and off
       the panel. The value column is as wide as the widest value, and the track takes what is left. */
    const rows = items.map(l => { const c2 = gCells(l); return { label: c2[0] || "", v: parseFloat(c2[1]) || 0, show: c2[2] || c2[1] || "" }; });
    const max = Math.max(1e-9, ...rows.map(r => r.v));
    const padX = Math.round(38 * us), bh = Math.round(26 * us), labelLh = Math.round(ITEM_BODY_PX * 1.3);
    ctx.font = "700 " + ITEM_BODY_PX + "px " + G_HEAD;
    const valW = Math.min(Math.round(maxW * 0.42), Math.ceil(Math.max(0, ...rows.map(r => ctx.measureText(r.show).width))));
    const trackX = M + padX, trackW = Math.min(Math.round(maxW * 0.72), maxW - padX * 2 - valW - Math.round(24 * us));
    const lay = rows.map(r => {
      ctx.font = "600 " + ITEM_BODY_PX + "px " + G_BODY; const ll = gWrap(ctx, r.label, maxW - padX * 2);
      ctx.font = "700 " + ITEM_BODY_PX + "px " + G_HEAD; const vl = gWrap(ctx, r.show, valW + 2);
      return { r, ll, vl, h: ll.length * labelLh + Math.round(5 * us) + Math.max(bh, vl.length * labelLh - Math.round(8 * us)) + Math.round(34 * us) };
    });
    const total = lay.reduce((a, L) => a + L.h, 0) + Math.round(50 * us);
    gPanel(ctx, M, y, maxW, total);
    let by = y + Math.round(38 * us);
    lay.forEach((L, i) => {
      ctx.font = "600 " + ITEM_BODY_PX + "px " + G_BODY; ctx.fillStyle = GRID_PAL.ink; ctx.textBaseline = "top";
      L.ll.forEach((l, n) => ctx.fillText(l, trackX, by + n * labelLh));
      const barY = by + L.ll.length * labelLh + Math.round(5 * us);
      ctx.fillStyle = "#EDE6D6"; gRound(ctx, trackX, barY, trackW, bh, bh / 2); ctx.fill();
      ctx.fillStyle = i === 0 ? accent : "#2A2E34";
      gRound(ctx, trackX, barY, Math.max(bh, (L.r.v / max) * trackW), bh, bh / 2); ctx.fill();
      ctx.font = "700 " + ITEM_BODY_PX + "px " + G_HEAD; ctx.fillStyle = GRID_PAL.ink;
      ctx.textAlign = "right"; L.vl.forEach((l, n) => ctx.fillText(l, M + maxW - padX, barY - Math.round(4 * us) + n * labelLh)); ctx.textAlign = "left";
      by += L.h;
    });
    y += total + Math.round(32 * us);
    const barsAfterY = y;
    drawMascot(barsAfterY);
    if (spec.note) y = Math.max(y, gBubble(ctx, bubbleX, barsAfterY + Math.round(24 * u), Math.round(470 * u), spec.note, Math.round(30 * u * noteK)));
  } else if (t === "g_rows") {
    y = gHeadline(ctx, spec.title || "", M, y, headW, HEAD_PX, HEAD_LH, ink, accent);
    y += Math.round(30 * us);
    /* EVERY ROW, AND EVERY ROW AS TALL AS ITS WORDS (auto-fit, 16 Nov 2026). The panels were a fixed 168u and the list stopped at
       four: a heading longer than the panel ran off its right edge, a detail of three lines ran out of its foot onto the next
       panel, and a fifth point was dropped without a word. Now the heading wraps, the panel grows with its lines, and when the
       card is too full the whole slide's type comes down together (renderGridCard). */
    const rows = items.map(gCells);
    const gap = Math.round(28 * us), padT = Math.round(38 * us), padB = Math.round(34 * us), textX = M + Math.round(110 * us);
    const textW = maxW - Math.round(160 * us), headLh = Math.round(ITEM_HEAD_PX * 1.25);
    rows.forEach((r, i) => {
      ctx.font = "700 " + ITEM_HEAD_PX + "px " + G_HEAD; const hl = gWrap(ctx, r[0] || "", textW);
      const detail = r.slice(1).filter(Boolean).join(" · ");
      ctx.font = "500 " + ITEM_BODY_PX + "px " + G_BODY; const bl = detail ? gWrap(ctx, detail, textW) : [];
      const rowH = Math.max(Math.round(168 * us), padT + hl.length * headLh + (bl.length ? Math.round(7 * us) + bl.length * ITEM_BODY_LH : 0) + padB);
      gPanel(ctx, M, y, maxW, rowH);
      ctx.font = "800 " + Math.round(44 * us) + "px " + G_HEAD; ctx.fillStyle = accent; ctx.textBaseline = "top";
      ctx.fillText(String(i + 1), M + Math.round(38 * us), y + Math.round(54 * us));
      ctx.font = "700 " + ITEM_HEAD_PX + "px " + G_HEAD; ctx.fillStyle = GRID_PAL.ink;
      let ty = y + padT;
      for (const l of hl) { ctx.fillText(l, textX, ty); ty += headLh; }
      if (bl.length) { ty += Math.round(7 * us); ctx.font = "500 " + ITEM_BODY_PX + "px " + G_BODY; ctx.fillStyle = GRID_PAL.muted; for (const l of bl) { ctx.fillText(l, textX, ty); ty += ITEM_BODY_LH; } }
      y += rowH + gap;
    });
    const rowsAfterY = y;
    drawMascot(rowsAfterY);
    /* The note is part of the slide's height now. It used to be clamped inside the card, which on a full slide put it ON the
       last panel's words; it sits under the rows and the fit makes the room. With a mascot it is a speech bubble at its side. */
    if (spec.note && mascot) y = Math.max(y, gBubble(ctx, bubbleX, rowsAfterY + Math.round(6 * u), Math.round(470 * u), spec.note, Math.round(30 * u * noteK)));
    else if (spec.note) y += Math.round(6 * u) + gSticky(ctx, W - M - Math.round(410 * u), y + Math.round(6 * u), Math.round(410 * u), spec.note, GRID_PAL.yellow, 0.03, Math.round(46 * u * noteK)) + Math.round(14 * u);
  } else if (t === "g_table") {
    y = gHeadline(ctx, spec.title || "", M, y, maxW, HEAD_PX, HEAD_LH, ink, accent);
    y += Math.round(40 * us);
    // every row, as tall as its words; the mark comes down in size until it fits its own narrow column
    const rows = items.map(gCells);
    const padX = Math.round(42 * us), textX = M + Math.round(126 * us), textW = maxW - Math.round(180 * us);
    const headPx = Math.round(34 * us), headLh = Math.round(48 * us), detPx = Math.round(27 * us), detLh = Math.round(36 * us);
    const lay = rows.map((r) => {
      ctx.font = "700 " + headPx + "px " + G_HEAD; const hl = gWrap(ctx, r[1] || "", textW);
      const detail = r.slice(2).filter(Boolean).join(" · ");
      ctx.font = "500 " + detPx + "px " + G_BODY; const dl = detail ? gWrap(ctx, detail, textW) : [];
      let mpx = Math.round(28 * us); ctx.font = "500 " + mpx + "px " + G_MONO;
      while (mpx > Math.round(13 * u) && ctx.measureText(r[0] || "").width > Math.round(74 * us)) { mpx -= 1; ctx.font = "500 " + mpx + "px " + G_MONO; }
      return { r, hl, dl, mpx, h: Math.max(Math.round(128 * us), hl.length * headLh + dl.length * detLh + Math.round(44 * us)) };
    });
    const total = lay.reduce((a, L) => a + L.h, 0) + Math.round(40 * us);
    gPanel(ctx, M, y, maxW, total, { fill: "rgba(255,255,255,.055)", shadow: false, stroke: "rgba(255,255,255,.12)" });
    let ry = y + Math.round(34 * us);
    lay.forEach((L, i) => {
      ctx.textBaseline = "top";
      ctx.font = "500 " + L.mpx + "px " + G_MONO; ctx.fillStyle = accent;
      ctx.fillText(L.r[0] || "", M + padX, ry + Math.round(6 * us));
      ctx.font = "700 " + headPx + "px " + G_HEAD; ctx.fillStyle = "#fff";
      let ty = ry;
      for (const l of L.hl) { ctx.fillText(l, textX, ty); ty += headLh; }
      ctx.font = "500 " + detPx + "px " + G_BODY; ctx.fillStyle = "rgba(255,255,255,.6)";
      for (const l of L.dl) { ctx.fillText(l, textX, ty); ty += detLh; }
      if (i < lay.length - 1) {
        ctx.save(); ctx.strokeStyle = "rgba(255,255,255,.12)"; ctx.lineWidth = 2; ctx.setLineDash([8, 8]);
        ctx.beginPath(); ctx.moveTo(M + padX, ry + L.h - Math.round(20 * us)); ctx.lineTo(W - M - padX, ry + L.h - Math.round(20 * us)); ctx.stroke(); ctx.restore();
      }
      ry += L.h;
    });
    y += total + Math.round(40 * us);
    // the note sits under the table and counts toward the slide's height (it used to be clamped onto the last rows)
    if (spec.note) y += gSticky(ctx, W - M - Math.round(410 * u), y, Math.round(410 * u), spec.note, GRID_PAL.purple, 0.028, Math.round(46 * u * noteK)) + Math.round(14 * u);
  }

  /* One source line, pinned to the card's own bottom margin, drawn last so nothing else
     overlaps it -- see gSourceLine. */
  gSourceLine(ctx, W, H, M, u, spec.chip_label || (spec.footnote ? "Sumber" : ""), spec.footnote || "", dark);

  /* Reserve room for the source line drawn just below this check -- it is pinned to the
     card's own bottom margin regardless of how far the content above it flowed, so a
     bubble or panel that merely cleared the canvas could still run into it unseen. */
  if (y > cardFloor(ctx, spec, W, H, M, u) + 1) warn.push("The slide is fuller than the card: shorten a line.");
  /* The measuring pass wants the layout, not a picture: it is handed no canvas and returns
     only where the content ended, which is what centreShift needs. */
  return canvasOut ? { url: canvasOut.toDataURL("image/jpeg", 0.88), warn, y } : { warn, y };
}
const SCRIM = { none: [0, 0, 0], light: [0.28, 0.38, 0.56], medium: [0.46, 0.54, 0.72], heavy: [0.62, 0.70, 0.86] };

/* ===================== the Info ERA family ==================================
   Wan, 19 Sep 2026, from a KTM "Info ERA" reference set: kraft paper with a faint
   technical drawing behind it, a black badge in the top corner, headings struck through
   with a highlighter, solid red blocks for anything alarming, hand-drawn red arrows
   pointing at what matters, and white paper notes tipped a degree or two off level.

   What deliberately does NOT carry over is the subject matter. The reference draws
   railway gantries because it is about railways; ws.regulab writes about cosmetics,
   halal and pharmaceuticals, so the backdrop here is abstract blueprint linework --
   uprights, cross-members and two long curves -- which reads as "technical document"
   without claiming to be any particular machine. Draw a train behind a notification
   post and the card is lying about what it is. */
const ERA_PAL = {
  paper: "#EFE8DC", grain: "#D7CEBE", ink: "#151515", muted: "#5C574E",
  red: "#D8232A", yellow: "#FFE24D", note: "#FFFFFF",
};
function eraPaper(ctx, W, H) {
  ctx.fillStyle = ERA_PAL.paper; ctx.fillRect(0, 0, W, H);
  ctx.save();
  ctx.globalAlpha = 0.45; ctx.strokeStyle = ERA_PAL.grain; ctx.lineWidth = 1;
  const step = Math.round(W / 44);
  ctx.beginPath();
  for (let x = 0; x <= W; x += step) { ctx.moveTo(x + 0.5, 0); ctx.lineTo(x + 0.5, H); }
  for (let y = 0; y <= H; y += step) { ctx.moveTo(0, y + 0.5); ctx.lineTo(W, y + 0.5); }
  ctx.stroke();
  ctx.globalAlpha = 0.5; ctx.lineWidth = Math.max(2, Math.round(W / 460));
  for (let i = 0; i < 5; i++) {
    const x = Math.round(W * (0.09 + i * 0.205));
    ctx.beginPath(); ctx.moveTo(x, Math.round(H * 0.02)); ctx.lineTo(x, Math.round(H * 0.44)); ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(x - Math.round(W * 0.055), Math.round(H * 0.09));
    ctx.lineTo(x + Math.round(W * 0.055), Math.round(H * 0.085)); ctx.stroke();
  }
  for (const pair of [[0.17, 0.15, 0.27], [0.25, 0.23, 0.35]]) {
    ctx.beginPath(); ctx.moveTo(0, Math.round(H * pair[0]));
    ctx.quadraticCurveTo(W * 0.5, Math.round(H * pair[2]), W, Math.round(H * pair[1])); ctx.stroke();
  }
  ctx.restore();
}
/* The black pill in the top corner. It carries the eyebrow, which is where the reference
   puts its section name -- so on a ws.regulab card it names the domain and on LinkedIn the
   pillar, exactly as the eyebrow already did everywhere else. */
function eraBadge(ctx, W, u, M, text, spec) {
  if (!text) return;
  let px = Math.round(23 * u);
  ctx.save();
  ctx.font = "700 " + px + "px " + G_HEAD; ctx.textBaseline = "top"; ctx.textAlign = "left";
  const label = stripEmph(text).toUpperCase();
  // the ws.regulab logo owns the top right (Wan, 11 Nov 2026), so on its cards the badge sits at the top left; LinkedIn has no logo
  const logoRight = !!spec && spec.stream !== "linkedin" && !(spec.handle && spec.handle !== "@ws.regulab");
  /* The pill is as wide as its label, up to the room it has (beside the logo, or most of the card on LinkedIn), and a label
     longer than that comes down in size until it fits: the pill used to stop at 56% of the card while the words ran on past it. */
  const room = logoRight ? W - M * 2 - Math.round(300 * u) : Math.round(W * 0.7);
  while (px > Math.round(13 * u) && ctx.measureText(label).width + Math.round(px * 0.8) * 2 > room) { px -= 1; ctx.font = "700 " + px + "px " + G_HEAD; }
  const padX = Math.round(px * 0.8), h = Math.round(Math.round(23 * u) * 2);
  const w = Math.min(ctx.measureText(label).width + padX * 2, room);
  const x = logoRight ? M : W - M - w, y = Math.round(50 * u);
  ctx.fillStyle = ERA_PAL.ink; gRound(ctx, x, y, w, h, Math.round(px * 0.4)); ctx.fill();
  ctx.fillStyle = "#FFFFFF";
  ctx.fillText(label, x + padX, y + Math.round((h - px) / 2) - Math.round(px * 0.06));
  ctx.restore();
}
/* A highlighter stroke, not a neat rectangle: it overshoots at both ends and rides a little
   off-level, which is the single detail that makes this family read as marker on paper
   rather than as a web page. *Asterisks* still take the accent, the same as everywhere. */
function eraMark(ctx, text, x, y, maxW, px, lh, base, accent, fill) {
  ctx.font = "800 " + px + "px " + G_HEAD; ctx.textBaseline = "top";
  const words = [];
  for (const tk of gTokens(text, base, accent)) {
    for (const w of tk.t.split(/(\s+)/)) {
      if (w === "") continue;
      if (/^\s+$/.test(w)) { words.push({ w: w, c: tk.c }); continue; }
      // hardSplit needs the font already set, which both callers do on the line above.
      for (const piece of hardSplit(ctx, w, maxW)) words.push({ w: piece, c: tk.c });
    }
  }
  const lines = []; let line = [], lw = 0;
  for (const it of words) {
    const w = ctx.measureText(it.w).width;
    if (/^\s+$/.test(it.w) && lw === 0) continue;
    if (lw + w > maxW && lw > 0) { lines.push({ items: line, w: lw }); line = []; lw = 0; if (/^\s+$/.test(it.w)) continue; }
    line.push(it); lw += w;
  }
  if (line.length) lines.push({ items: line, w: lw });
  for (const L of lines) {
    const bh = Math.round(px * 0.86), by = y + Math.round(px * 0.3);
    ctx.fillStyle = fill || ERA_PAL.yellow;
    ctx.beginPath();
    ctx.moveTo(x - px * 0.15, by + bh * 0.10);
    ctx.lineTo(x + L.w + px * 0.19, by - bh * 0.07);
    ctx.lineTo(x + L.w + px * 0.15, by + bh);
    ctx.lineTo(x - px * 0.11, by + bh * 0.90);
    ctx.closePath(); ctx.fill();
    let xx = x;
    for (const it of L.items) { ctx.fillStyle = it.c; ctx.fillText(it.w, xx, y); xx += ctx.measureText(it.w).width; }
    y += lh;
  }
  return y;
}
/* A solid block, white on red, hugging its own text rather than running the full column --
   a full-width bar reads as a navigation strip, a hugged one reads as a stamp. */
function eraBand(ctx, x, y, w, text, px, fill, colour) {
  ctx.font = "800 " + px + "px " + G_HEAD; ctx.textBaseline = "top";
  const padX = Math.round(px * 0.52), padY = Math.round(px * 0.4), lh = Math.round(px * 1.16);
  const lines = gWrap(ctx, text, w - padX * 2);
  let widest = 0;
  for (const l of lines) widest = Math.max(widest, ctx.measureText(l).width);
  const bw = Math.min(w, widest + padX * 2), bh = lines.length * lh + padY * 2;
  ctx.fillStyle = fill || ERA_PAL.red;
  gRound(ctx, x, y, bw, bh, Math.round(px * 0.16)); ctx.fill();
  ctx.fillStyle = colour || "#FFFFFF";
  let yy = y + padY;
  for (const l of lines) { ctx.fillText(l, x + padX, yy); yy += lh; }
  return y + bh;
}
/* A white paper note, tipped slightly. The caller works out the height and paints into the
   note's own coordinates, so nothing has to reason about the rotation. */
function eraCard(ctx, x, y, w, h, rot, paint) {
  ctx.save();
  ctx.translate(x + w / 2, y + h / 2); ctx.rotate(rot || 0); ctx.translate(-w / 2, -h / 2);
  ctx.shadowColor = "rgba(20,20,20,.22)"; ctx.shadowBlur = Math.round(w * 0.05); ctx.shadowOffsetY = Math.round(w * 0.018);
  ctx.fillStyle = ERA_PAL.note; ctx.fillRect(0, 0, w, h);
  ctx.shadowColor = "transparent";
  if (paint) paint(ctx, w, h);
  ctx.restore();
}
function eraArrow(ctx, x1, y1, x2, y2, bend, colour, wpx) {
  const mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
  const dx = x2 - x1, dy = y2 - y1, len = Math.hypot(dx, dy) || 1;
  const cx = mx - (dy / len) * bend, cy = my + (dx / len) * bend;
  ctx.save();
  ctx.strokeStyle = colour; ctx.lineWidth = wpx; ctx.lineCap = "round";
  ctx.beginPath(); ctx.moveTo(x1, y1); ctx.quadraticCurveTo(cx, cy, x2, y2); ctx.stroke();
  const ax = x2 - cx, ay = y2 - cy, al = Math.hypot(ax, ay) || 1;
  const ux = ax / al, uy = ay / al, hl = wpx * 3.2, hw = wpx * 1.8;
  ctx.fillStyle = colour;
  ctx.beginPath(); ctx.moveTo(x2, y2);
  ctx.lineTo(x2 - ux * hl - uy * hw, y2 - uy * hl + ux * hw);
  ctx.lineTo(x2 - ux * hl + uy * hw, y2 - uy * hl - ux * hw);
  ctx.closePath(); ctx.fill();
  ctx.restore();
}
/* One floating question, marker-struck and tipped. Returns its height so the caller can
   stack the next one under it. */
function eraChipH(ctx, text, maxW, px) {
  ctx.font = "800 " + px + "px " + G_HEAD;
  return gWrap(ctx, text, maxW).length * Math.round(px * 1.2);
}
function eraChip(ctx, text, x, y, maxW, px, rot) {
  ctx.save();
  ctx.font = "800 " + px + "px " + G_HEAD; ctx.textBaseline = "top";
  const lines = gWrap(ctx, text, maxW);
  let widest = 0; for (const l of lines) widest = Math.max(widest, ctx.measureText(l).width);
  const lh = Math.round(px * 1.2), h = lines.length * lh;
  ctx.translate(x + widest / 2, y + h / 2); ctx.rotate(rot || 0); ctx.translate(-widest / 2, -h / 2);
  let yy = 0;
  for (const l of lines) {
    const lw = ctx.measureText(l).width, bh = Math.round(px * 0.9), by = yy + Math.round(px * 0.26);
    ctx.fillStyle = ERA_PAL.yellow;
    ctx.beginPath();
    ctx.moveTo(-px * 0.16, by + bh * 0.1); ctx.lineTo(lw + px * 0.2, by - bh * 0.07);
    ctx.lineTo(lw + px * 0.16, by + bh); ctx.lineTo(-px * 0.12, by + bh * 0.9);
    ctx.closePath(); ctx.fill();
    ctx.fillStyle = ERA_PAL.ink; ctx.fillText(l, 0, yy);
    yy += lh;
  }
  ctx.restore();
  return h;
}
function eraBullet(ctx, text, x, y, maxW, px, lh) {
  const r = Math.round(px * 0.64);
  ctx.save();
  ctx.fillStyle = ERA_PAL.ink;
  ctx.beginPath(); ctx.arc(x + r, y + r + Math.round(px * 0.1), r, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = "#FFFFFF"; ctx.font = "800 " + Math.round(px * 0.88) + "px " + G_HEAD;
  ctx.textAlign = "center"; ctx.textBaseline = "middle";
  ctx.fillText("$", x + r, y + r + Math.round(px * 0.14));
  ctx.restore();
  return gPara(ctx, text, x + r * 2 + Math.round(px * 0.62), y, maxW - r * 2 - Math.round(px * 0.62), px, lh, ERA_PAL.ink, 700);
}
async function renderEraCard(spec) {
  const [W, H] = sizeOf(spec);
  const c = document.createElement("canvas"); c.width = W; c.height = H;
  const ctx = styleCtx(c.getContext("2d"), spec);                  // SEMASA: the slide's own face, when it chose one
  try { await document.fonts.ready; } catch (e) { }
  /* THIS FAMILY IS NEVER CENTRED, and the attempt on 19 Sep made it visibly worse.
     ERA already distributes itself across the whole card, from the top and from the bottom
     at once: the character is FLOORED (`drawMascot(0, true)` against `mascotFloor`) and its
     SIZE is computed from the room the words leave --
     `sizeMascot(min(H*0.44, max(H*0.26, mascotFloor - y - 215u)))` -- with the floating
     questions then placed against the top of that character. So there is no slack to centre
     into; the mascot is the slack.
     Shifting y down did three things at once. It shrank the character, because
     `mascotFloor - y` got smaller. It pushed the headline into the questions. And worst, it
     broke the measurement itself: the probe pass runs at yShift 0 and the paint pass at
     yShift > 0, and because the layout SIZES off y, those two passes compute different
     layouts -- so the shift was derived from a card that was never drawn.
     The general rule, worth more than this one fix: **two-pass centring is only valid for a
     layout whose geometry does not depend on where it starts.** The grid family qualifies
     (its mascot is a fixed H*0.30 and only its POSITION follows the content). ERA does not.
     Before centring any future family, check whether anything in it sizes off `y`. */
  if (spec.mascot || spec.template === "e_hook") return eraCardPaint(ctx, spec, W, H, 0, c);
  /* WITHOUT A CHARACTER THE RULE ABOVE NO LONGER BITES (Wan, 16 Nov 2026, of an explainer slide whose lower half was empty:
     "this poster and any poster like this can improve or remove, remove all mascott"). The character was the only thing that
     sized off where the words started. With none, the room it used to take is simply blank, so the slide is measured first,
     its type grown until the words fill the card (ERA_FILL_MAX at most, a chosen text size respected) and the block centred
     between the label and the source line, exactly as the grid family does. e_hook is left alone: it spreads its own chips. */
  const u = W / 1080, floor = cardFloor(ctx, spec, W, H, Math.round(72 * u), u);
  /* A measuring pass carries textAlign and textBaseline to the real context (measureProxy: measureText reads them) while its
     save() and restore() do nothing, so a painter that centres one glyph inside a save/restore (the "$" of an e_vs bullet)
     would leave every later word centred on its x. The real context is saved and restored round each pass instead. */
  const measure = async (sp) => { ctx.save(); try { return await eraCardPaint(measureProxy(ctx), sp, W, H, 0); } finally { ctx.restore(); } };
  const probe = await measure(spec);
  // the same search shrinks a slide that is fuller than the card (auto-fit, 16 Nov 2026); growth still stops at the longest word
  const max = Math.max(1, Math.min(ERA_FILL_MAX, eraWordCap(ctx, spec, W)));
  const fill = spec.type_size ? 1 : await fillScale(spec, H, u, ERA_TOP, probe.y, measure, max, ERA_FILL_FROM, ERA_FILL_TARGET, floor);
  const filled = fill !== 1 ? { ...spec, _fill: fill } : spec;
  const end = fill !== 1 ? (await measure(filled)).y : probe.y;
  return eraCardPaint(ctx, filled, W, H, centreShift(H, u, end, ERA_TOP, floor), c);
}
/* An ERA slide with no character grows further than a grid body slide: it has no numbered panels to keep in proportion, and a
   slide that says little is better as a few large lines than as a small block in a bare card. */
const ERA_TOP = 138, ERA_FILL_MAX = 3, ERA_MORE_MAX = 2.4, ERA_FILL_FROM = 0.84, ERA_FILL_TARGET = 0.93;
/* How far an ERA body slide may grow before its longest word no longer fits its column: a wrapper breaks an over-wide word
   letter by letter (hardSplit), and a heading cut as "bertanggungjawa / b" is worse than a smaller one. Each heading is
   measured at the size and in the column its template draws it. */
function eraWordCap(ctx, spec, W) {
  const u = W / 1080, maxW = W - Math.round(72 * u) * 2, t = spec.template;
  const wide = (text, px, weight, fam) => {
    ctx.font = weight + " " + Math.round(px * u) + "px " + fam;
    return Math.max(0, ...stripEmph(String(text || "")).split(/\s+/).filter(Boolean).map((x) => ctx.measureText(x).width));
  };
  const rows = (spec.items || []).map((x) => String(x || "").trim()).filter(Boolean).map(gCells);
  const caps = [];
  const cap = (w0, room, pad) => { if (w0 > 0) caps.push(room / (w0 + pad)); };
  if (t === "e_vs") {
    // two notes side by side: a label and a figure in each, in a column of fixed width whose inner margin grows with the type
    const colW = Math.round((maxW - Math.round(30 * u)) / 2);
    cap(wide(spec.title, 56, 800, G_HEAD), maxW, 0);
    rows.slice(0, 2).forEach((r, i) => { cap(wide(r[0], 25, 600, G_BODY), colW, Math.round(44 * u)); cap(wide(r[1], i ? 60 : 50, 800, G_HEAD), colW, Math.round(36 * u)); });
    for (const r of rows.slice(2)) cap(wide(r.join(" "), 27, 700, G_BODY), Math.round(maxW * 0.92), Math.round(27 * u * 1.9));
    cap(wide(spec.note, 34, 800, G_HEAD), maxW, Math.round(34 * u * 1.04));
    return caps.length ? Math.min(...caps) * 0.97 : Infinity;
  }
  const inset = t === "e_flow" ? Math.round(150 * u) : 0, col = t === "e_flow" ? maxW : Math.round(maxW * 0.9);
  if (rows.length || t === "e_flow") cap(wide(spec.title, 44, 800, G_HEAD), maxW, Math.round(44 * u * 1.04));    // the red band and its padding
  else { cap(wide(spec.title, 62, 800, G_HEAD), maxW, 0); cap(wide(spec.lead, 33, 500, G_BODY), col, 0); }
  for (const r of rows) { cap(wide(r[0], 40, 800, G_HEAD), col, inset); cap(wide(r[1], 29, 500, G_BODY), col, inset); }
  cap(wide(spec.note, 32, 800, G_HEAD), maxW, Math.round(32 * u * 1.04));
  return caps.length ? Math.min(...caps) * 0.97 : Infinity;
}
/* A CHARACTER NEVER COSTS A FACT.
   Four templates used to shrink their own item list when a mascot was present --
   e_explain 3 to 2, e_vs 5 to 4, g_bars 5 to 3, g_rows 4 to 3. None of it ever fired,
   because until 19 Sep 2026 no mascot was ever loaded into S.media, so `mascot` was always
   null and the full list always drew. The moment mascots started loading, every one of
   these began silently removing a point from the artwork while the draft still claimed it.
   On a card whose whole purpose is to carry a regulatory fact accurately, that is the wrong
   way round. The items are kept in full and the MASCOT gives way instead: drawMascot skips
   itself when the content leaves no room for it (see the room check there). Losing the
   cartoon is visible and harmless; losing the third point is invisible and is not. */
async function eraCardPaint(ctx, spec, W, H, yShift, canvasOut) {
  const warn = [];
  const t = spec.template, u = W / 1080, M = Math.round(72 * u), maxW = W - M * 2;
  /* ERA paints dark ink on its own light paper, which is unreadable over a photograph's
     scrim — so a ground flips the ink to white, exactly as the grid family's `dark` does.
     The red stays: it is the family's signal colour and it holds against a dark scrim. */
  const onGround = inkWhite(spec);
  const ink = onGround ? "#FFFFFF" : ERA_PAL.ink,
        muted = onGround ? "rgba(255,255,255,.72)" : ERA_PAL.muted,
        red = ERA_PAL.red;
  const items = (spec.items || []).filter(x => String(x || "").trim());
  /* One fixed type scale for the whole family, for the same reason the grid family has one
     (Wan, 19 Sep 2026: "no font size change if we delete the text"). */
  const TS = textScale(spec);              // SEMASA: the person's own text size for this slide (100% = the template's)
  const HEAD_PX = Math.round(76 * u * TS), HEAD_LH = Math.round(90 * u * TS);
  const LEAD_PX = Math.round(33 * u * TS), LEAD_LH = Math.round(46 * u * TS);
  const ITEM_HEAD_PX = Math.round(40 * u * TS), ITEM_BODY_PX = Math.round(29 * u * TS), ITEM_BODY_LH = Math.round(39 * u * TS);
  const MS = mascotScale(spec);            // SEMASA: the person's own character size (100% = the template's)
  const F = fillOf(spec), uf = u * F;      // the automatic fill: headings and gaps grow with the words, the frame does not

  if (!await drawGround(ctx, spec, W, H)) eraPaper(ctx, W, H);
  /* Rule 7 again: the mark is the consultancy's and LinkedIn carries none of it. */
  /* SEMASA: over a ground the mark is knocked out in white (its own dark green vanished into the scrim) */
  await drawBrandMark(ctx, spec, W, u, M, { top: 54, h: 34, knockout: onGround, textFill: onGround ? "rgba(255,255,255,.7)" : "rgba(21,21,21,.6)" });
  eraBadge(ctx, W, u, M, spec.eyebrow, spec);

  const mascot = spec.mascot && MASCOT_TPL[t] ? await loadImg(spec.mascot) : null;
  /* On the hook slide the character IS the slide -- centred and larger, with the questions
     floating round it. Everywhere else it is a small figure in a corner, exactly as in the
     grid family, and picked by the same deterministic hash so a re-render never shuffles it. */
  const hero = t === "e_hook";
  const mascotPos = mascot ? (hero ? "bc" : pickMascotPos(spec)) : "br";
  const mascotFloor = H - Math.round(88 * u);
  let mascotMh = 0, mascotMw = 0, mascotX = 0;
  /* Sizing is a function rather than a constant because the hook slide works out how big its
     character should be only once it knows how much room the words left. A fixed fraction of
     the height looked right on the square card and stranded the character at the foot of the
     LinkedIn one with a hole above it -- the same dead-gap bug the grid family had, and the
     same cause: a figure pinned to the canvas instead of to the content. */
  const sizeMascot = (mh) => {
    mascotMh = mascot ? Math.round(mh) : 0;
    mascotMw = mascot ? mascot.width * (mascotMh / mascot.height) : 0;
    mascotX = mascotPos === "bl" ? M - Math.round(6 * u)
      : mascotPos === "bc" ? Math.round((W - mascotMw) / 2)
        : W - mascotMw - Math.round(18 * u);
  };
  sizeMascot(H * (hero ? 0.36 : 0.27) * MS);
  const drawMascot = (afterY, floorIt) => {
    if (!mascot) return 0;
    /* The hero on e_hook is floored and SIZED from the slack, so it always fits by
       construction. Everywhere else the figure follows the content, and if the content
       reaches far enough down there is nowhere for it to go: it would sit on the words or
       on the source line. It stands down instead -- the items already drew in full. */
    if (!floorIt && (afterY || 0) + Math.round(26 * u) + mascotMh > mascotFloor) return 0;
    const top = floorIt ? mascotFloor - mascotMh
      : Math.min(mascotFloor - mascotMh, (afterY || 0) + Math.round(26 * u));
    ctx.drawImage(mascot, mascotX, top, mascotMw, mascotMh);
    return top;
  };
  const bubbleX = mascotPos === "bl" ? Math.max(M, W - M - Math.round(470 * u)) : M;
  let y = Math.round(138 * u) + (yShift || 0);

  if (t === "e_hook") {
    y = gHeadline(ctx, spec.title || "", M, y, maxW, HEAD_PX, HEAD_LH, ink, red);
    y += Math.round(16 * u);
    if (spec.lead) y = eraBand(ctx, M, y, maxW, spec.lead, Math.round(36 * u));
    /* The character takes whatever the words leave, inside sane bounds, with room reserved
       for the questions. That is what keeps the square and the portrait card both full. */
    // the hero is sized from the room the words left, so it may only be made smaller, never past that room
    sizeMascot(Math.min(H * 0.44, Math.max(H * 0.26, mascotFloor - y - Math.round(215 * u))) * Math.min(MS, 1));
    /* Character first, questions over it: a sticker that clips a shoulder reads as
       intentional layering, which is what the reference does. */
    const mTop = drawMascot(0, true);
    const chipW = Math.round(W * 0.43), chipPx = Math.round(33 * u);
    const chips = items.slice(0, 3);
    /* Spread down the gap between the words and the character's head instead of stacking
       tight under the headline -- on the taller LinkedIn card a tight stack left a hole. */
    const zoneTop = y + Math.round(30 * u);
    const zoneBot = (mascot ? mTop : H - Math.round(190 * u)) - Math.round(18 * u);
    const hs = chips.map(q => eraChipH(ctx, q, chipW, chipPx));
    const total = hs.reduce((a, b) => a + b, 0);
    const gap = chips.length > 1
      ? Math.max(Math.round(24 * u), Math.round((zoneBot - zoneTop - total) / (chips.length - 1)))
      : 0;
    let cy = zoneTop;
    chips.forEach((q, i) => {
      const cx = i !== 1 ? M - Math.round(8 * u) : W - M - chipW + Math.round(8 * u);
      eraChip(ctx, q, cx, cy, chipW, chipPx, i === 0 ? -0.035 : i === 1 ? 0.03 : 0.028);
      cy += hs[i] + gap;
    });
    if (chips.length) cy -= gap;                 // where the last question ends, not one gap below it
    /* The two big query marks the reference hangs either side of the character. Placed off
       the mascot's own box so they follow it wherever it lands instead of guessing. */
    if (mascot) {
      ctx.save();
      ctx.font = "800 " + Math.round(84 * u) + "px " + G_HEAD; ctx.fillStyle = red;
      ctx.textBaseline = "top"; ctx.textAlign = "center";
      ctx.fillText("?", mascotX - Math.round(36 * u), mTop + Math.round(34 * u));
      ctx.fillText("?", mascotX + mascotMw + Math.round(36 * u), mTop + Math.round(6 * u));
      ctx.restore();
    }
    y = cy;
  } else if (t === "e_explain") {
    const blocks = items.map(gCells);                // every point: a full slide shrinks its type, it never drops a block
    /* With blocks under it the title is a section heading and takes the red stamp; with
       nothing under it the slide IS the title, so it takes the marker instead. A three-line
       red block is a wall, and a wall is exactly what an auto-built carousel slide -- which
       has a headline and no items at all -- would have produced every single time. */
    if (blocks.length) { y = eraBand(ctx, M, y, maxW, spec.title || "", Math.round(44 * uf)); y += Math.round(32 * uf); }
    else { y = eraMark(ctx, spec.title || "", M, y, maxW, Math.round(62 * uf), Math.round(76 * uf), ink, red); y += Math.round(26 * uf); }
    if (blocks.length) {
      for (const cells of blocks) {
        y = eraMark(ctx, cells[0] || "", M, y, Math.round(maxW * 0.9), ITEM_HEAD_PX, Math.round(ITEM_HEAD_PX * 1.26), ink, red);
        y += Math.round(14 * uf);
        if (cells[1]) y = gPara(ctx, cells[1], M, y, Math.round(maxW * (mascot ? 0.78 : 0.9)), ITEM_BODY_PX, ITEM_BODY_LH, muted);
        y += Math.round(30 * uf);
      }
    } else if (spec.lead) {
      y = gPara(ctx, spec.lead, M, y, Math.round(maxW * 0.9), LEAD_PX, LEAD_LH, muted);
    }
    const afterY = y;
    drawMascot(afterY);
    if (spec.note) y = Math.max(y, gBubble(ctx, bubbleX, afterY + Math.round(20 * uf), Math.round(470 * uf), spec.note, Math.round(30 * uf)));
  } else if (t === "e_flow") {
    y = eraBand(ctx, M, y, maxW, spec.title || "", Math.round(44 * uf));
    y += Math.round(34 * uf);
    const steps = items.map(gCells);
    steps.forEach((s, i) => {
      const inset = Math.round(150 * uf);
      ctx.font = "800 " + ITEM_HEAD_PX + "px " + G_HEAD;
      const headLines = gWrap(ctx, s[0] || "", maxW - inset);
      ctx.font = "500 " + ITEM_BODY_PX + "px " + G_BODY;
      const bodyLines = s[1] ? gWrap(ctx, s[1], maxW - inset) : [];
      const h = Math.round(30 * uf) + headLines.length * Math.round(ITEM_HEAD_PX * 1.2)
        + bodyLines.length * ITEM_BODY_LH + Math.round(22 * uf);
      eraCard(ctx, M, y, maxW, h, i % 2 ? 0.006 : -0.006, (k, cw) => {
        const r = Math.round(30 * uf);
        k.fillStyle = ERA_PAL.red;
        k.beginPath(); k.arc(Math.round(50 * uf) + r, Math.round(32 * uf) + r, r, 0, Math.PI * 2); k.fill();
        k.fillStyle = "#FFFFFF"; k.font = "800 " + Math.round(32 * uf) + "px " + G_HEAD;
        k.textAlign = "center"; k.textBaseline = "middle";
        k.fillText(String(i + 1), Math.round(50 * uf) + r, Math.round(32 * uf) + r + Math.round(2 * uf));
        k.textAlign = "left"; k.textBaseline = "top";
        let ty = Math.round(32 * uf);
        k.font = "800 " + ITEM_HEAD_PX + "px " + G_HEAD; k.fillStyle = ERA_PAL.ink;
        for (const l of headLines) { k.fillText(l, Math.round(128 * uf), ty); ty += Math.round(ITEM_HEAD_PX * 1.2); }
        if (bodyLines.length) {
          k.font = "500 " + ITEM_BODY_PX + "px " + G_BODY; k.fillStyle = ERA_PAL.muted;
          for (const l of bodyLines) { k.fillText(l, Math.round(128 * uf), ty); ty += ITEM_BODY_LH; }
        }
      });
      y += h;
      if (i < steps.length - 1) {
        /* The arrow needs a shaft long enough to read as one. At a 32px drop the head alone
           filled it and the result was a wedge, not an arrow. */
        const ax = M + Math.round(maxW * 0.5);
        eraArrow(ctx, ax, y + Math.round(10 * uf), ax, y + Math.round(54 * uf), Math.round(12 * uf), red, Math.max(3, Math.round(6 * uf)));
        y += Math.round(66 * uf);
      }
    });
    y += Math.round(20 * uf);
    if (spec.note) y = eraBand(ctx, M, y, maxW, spec.note, Math.round(32 * uf));
  } else if (t === "e_vs") {
    y = eraMark(ctx, spec.title || "", M, y, maxW, Math.round(56 * uf), Math.round(70 * uf), ink, red);
    y += Math.round(58 * uf);
    const gap = Math.round(30 * uf), colW = Math.round((maxW - gap) / 2);
    const pairs = [items[0] || "", items[1] || ""].map(gCells);
    /* Both notes take the height the taller one needs. A fixed height left whichever side had
       the shorter label as a mostly-empty white box, which reads as a mistake rather than as
       a design. */
    const colHof = (p, i) => {
      ctx.font = "600 " + Math.round(25 * uf) + "px " + G_BODY;
      const lab = gWrap(ctx, p[0] || "", colW - Math.round(44 * uf)).length * Math.round(32 * uf);
      const fpx = Math.round((i ? 60 : 50) * uf);
      ctx.font = "800 " + fpx + "px " + G_HEAD;
      const fig = gWrap(ctx, p[1] || "", colW - Math.round(36 * uf)).length * Math.round(fpx * 1.14);
      return Math.round(26 * uf) + lab + Math.round(14 * uf) + fig + Math.round(26 * uf);
    };
    const colH = Math.max(colHof(pairs[0], 0), colHof(pairs[1], 1), Math.round(150 * uf));
    pairs.forEach((p, i) => {
      const x = M + i * (colW + gap);
      /* The arrow lands in the gap the headline leaves above each note, so it never has to
         know how many lines the headline ran to. */
      eraArrow(ctx, x + colW * (i ? 0.84 : 0.16), y - Math.round(46 * uf),
        x + colW * (i ? 0.64 : 0.36), y - Math.round(8 * uf),
        i ? -Math.round(14 * uf) : Math.round(14 * uf), red, Math.max(3, Math.round(6 * uf)));
      eraCard(ctx, x, y, colW, colH, i ? 0.012 : -0.012, (k, cw) => {
        k.textBaseline = "top"; k.textAlign = "left";
        k.font = "600 " + Math.round(25 * uf) + "px " + G_BODY; k.fillStyle = ERA_PAL.muted;
        let ty = Math.round(26 * uf);
        for (const l of gWrap(k, p[0] || "", cw - Math.round(44 * uf))) { k.fillText(l, Math.round(24 * uf), ty); ty += Math.round(32 * uf); }
        ty += Math.round(14 * uf);
        const fpx = Math.round((i ? 60 : 50) * uf);
        k.font = "800 " + fpx + "px " + G_HEAD; k.fillStyle = i ? ERA_PAL.red : ERA_PAL.ink;
        for (const l of gWrap(k, p[1] || "", cw - Math.round(36 * uf))) { k.fillText(l, Math.round(24 * uf), ty); ty += Math.round(fpx * 1.14); }
      });
    });
    y += colH + Math.round(34 * uf);
    if (spec.note) { y = eraBand(ctx, M, y, maxW, spec.note, Math.round(34 * uf)); y += Math.round(22 * uf); }
    for (const b of items.slice(2)) {
      y = eraBullet(ctx, b, M, y, Math.round(maxW * (mascot ? 0.68 : 0.92)), Math.round(27 * uf), Math.round(36 * uf));
      y += Math.round(16 * uf);
    }
    drawMascot(Math.round(H * 0.6));
  }

  gSourceLine(ctx, W, H, M, u, spec.chip_label || (spec.footnote ? "Sumber" : ""), spec.footnote || "", false);
  if (y > cardFloor(ctx, spec, W, H, M, u) + 1) warn.push("The slide is fuller than the card: shorten a line.");
  return canvasOut ? { url: canvasOut.toDataURL("image/jpeg", 0.9), warn, y } : { warn, y };
}

/* ===================== the photo family =====================================
   Wan, 19 Sep 2026: "image background as third group carousel/single card". Until now the
   only way to put your own picture behind a post was the retired `photo` template, which
   the picker was still quietly routing every chosen design through -- so the one path a
   person reaches by clicking their own photograph was the one running on a layout that had
   been taken off the menu. These three make the photograph the design. */
/* Only p_fact is centred here, and the other two are left alone on purpose.
   p_quote already centres its own block at (H - blockH) / 2, and p_title is DELIBERATELY
   bottom-anchored: a full-bleed photograph with the headline sitting low is the look, not
   a layout accident, and centring it would be a design regression dressed up as a fix.
   p_fact is the one with the real gap -- its words live in the cream panel under the
   photograph and flowed from the top of it, so a short fact left dead cream beneath. */
async function renderPhotoCard(spec) {
  const [W, H] = sizeOf(spec);
  const c = document.createElement("canvas"); c.width = W; c.height = H;
  const ctx = styleCtx(c.getContext("2d"), spec);                  // SEMASA: the slide's own face, when it chose one
  try { await document.fonts.ready; } catch (e) { }
  const u = W / 1080, M = Math.round(74 * u), maxW = W - M * 2;
  const measure = async (sp) => { ctx.save(); try { return await photoCardPaint(measureProxy(ctx), sp, W, H, 0); } finally { ctx.restore(); } };
  const probe = await measure(spec);
  if (spec.template === "p_fact") {
    /* The words live in the cream panel under the photograph. They are fitted to it like any other card (auto-fit, 16 Nov 2026):
       a long fact shrinks until it clears the source line, a short one grows, and the block is centred in the panel. */
    const floor = cardFloor(ctx, spec, W, H, M, u), topU = (Math.round(H * 0.46) + Math.round(58 * u)) / u;
    const rows = (spec.items || []).map((x) => [x, 28, 600, G_BODY, maxW - Math.round(34 * u)]);
    const max = Math.min(FILL_BODY_MAX, wordCap(ctx, u, [[spec.title, 56, 800, G_HEAD, maxW], [spec.lead, 32, 500, G_BODY, Math.round(maxW * 0.92)], ...rows]));
    const fill = spec.type_size ? 1 : await fillScale(spec, H, u, topU, probe.y, measure, max, FILL_FROM, FILL_TARGET, floor);
    const drawn = fill !== 1 ? { ...spec, _fill: fill } : spec;
    const end = fill !== 1 ? (await measure(drawn)).y : probe.y;
    return photoCardPaint(ctx, drawn, W, H, centreShift(H, u, end, topU, floor), c);
  }
  /* A photo cover or quote is a headline on a picture: when it is short it used to sit small on a mostly bare card (Wan, 9 Nov 2026: "make
     sure takde carousel or card yang empty ... Hook make sure besar"). Its type grows until the block takes up to 70% of the room it
     may use, measured the same way as the grid family; a chosen text size is respected. A block taller than its room shrinks (16 Nov
     2026): a long headline used to be pushed against the top clamp and run under the source line. */
  const quote = spec.template === "p_quote";
  const cap = wordCap(ctx, u, [[quote ? "“" + String(spec.title || "") + "”" : spec.title, quote ? 62 : 72, 800, G_HEAD, maxW], [spec.lead, 32, 500, G_BODY, Math.round(maxW * 0.86)]]);
  const fill = spec.type_size ? 1
    : await fitSearch(async (f) => (await measure({ ...spec, _fill: f })).block, probe.block, probe.room, Math.min(FILL_MAX, cap), 0.6, 0.8);
  return photoCardPaint(ctx, fill !== 1 ? { ...spec, _fill: fill } : spec, W, H, 0, c);
}
async function photoCardPaint(ctx, spec, W, H, yShift, canvasOut) {
  const warn = [];
  const t = spec.template, u = W / 1080, M = Math.round(74 * u), maxW = W - M * 2;
  const items = (spec.items || []).filter(x => String(x || "").trim());
  const bg = spec.bg ? await loadImg(spec.bg) : null;
  if (!bg) warn.push("This design is built on a picture and none is chosen: pick one under Background.");
  const TS = textScale(spec);              // SEMASA: the person's own text size for this slide (100% = the template's)
  const HEAD_PX = Math.round(72 * u * TS), HEAD_LH = Math.round(84 * u * TS);
  const LEAD_PX = Math.round(32 * u * TS), LEAD_LH = Math.round(45 * u * TS);
  const paintBg = (x, y, w, h) => {
    ctx.save(); ctx.beginPath(); ctx.rect(x, y, w, h); ctx.clip(); ctx.translate(x, y);
    if (bg) { if (h >= H) coverSoft(ctx, bg, w, h, false); else coverDraw(ctx, bg, w, h); }   // full-bleed = a background under words: softened; a hero panel (words below it) stays sharp
    else {
      const g = ctx.createLinearGradient(0, 0, 0, h);
      g.addColorStop(0, "#2B323A"); g.addColorStop(1, "#11151A");
      ctx.fillStyle = g; ctx.fillRect(0, 0, w, h);
    }
    ctx.restore();
  };
  const scrim = (x, y, w, h, level) => {
    const s = SCRIM[level] || SCRIM.medium;
    const g = ctx.createLinearGradient(x, y, x, y + h);
    g.addColorStop(0, "rgba(8,10,12," + s[0] + ")");
    g.addColorStop(0.55, "rgba(8,10,12," + s[1] + ")");
    g.addColorStop(1, "rgba(8,10,12," + s[2] + ")");
    ctx.fillStyle = g; ctx.fillRect(x, y, w, h);
  };
  let y = 0, block = 0, room = 0, bottomY = cardFloor(ctx, spec, W, H, M, u);
  const quote = t === "p_quote";
  if (t === "p_fact") {
    const photoH = Math.round(H * 0.46);
    paintBg(0, 0, W, photoH);
    scrim(0, 0, W, photoH, "light");
    ctx.fillStyle = GRID_PAL.cream; ctx.fillRect(0, photoH, W, H - photoH);
    y = photoH + Math.round(58 * u) + (yShift || 0);
    if (spec.eyebrow) y = gEyebrow(ctx, spec.eyebrow, M, y, GRID_PAL.orange, Math.round(23 * u));
    y = gHeadline(ctx, spec.title || "", M, y, maxW, Math.round(56 * u * TS), Math.round(68 * u * TS), GRID_PAL.ink, GRID_PAL.orange);
    y += Math.round(18 * u);
    if (spec.lead) y = gPara(ctx, spec.lead, M, y, Math.round(maxW * 0.92), LEAD_PX, LEAD_LH, GRID_PAL.muted);
    if (items.length) {
      y += Math.round(16 * u);
      for (const it of items) {                        // every point: the type follows the room, no point is dropped
        ctx.fillStyle = GRID_PAL.orange;
        ctx.beginPath(); ctx.arc(M + Math.round(9 * u * TS), y + Math.round(15 * u * TS), Math.round(8 * u * TS), 0, Math.PI * 2); ctx.fill();
        y = gPara(ctx, it, M + Math.round(34 * u), y, maxW - Math.round(34 * u), Math.round(28 * u * TS), Math.round(38 * u * TS), GRID_PAL.ink, 600);
        y += Math.round(10 * u);
      }
    }
  } else {
    paintBg(0, 0, W, H);
    scrim(0, 0, W, H, spec.scrim || (spec.stream === "linkedin" ? "heavy" : "medium"));
    const hp = quote ? Math.round(62 * u * TS) : HEAD_PX, hl = quote ? Math.round(78 * u * TS) : HEAD_LH;
    const headText = quote ? "“" + String(spec.title || "") + "”" : String(spec.title || "");
    ctx.font = "800 " + hp + "px " + G_HEAD;
    const hLines = gWrap(ctx, headText, maxW);
    ctx.font = "500 " + LEAD_PX + "px " + G_BODY;
    const lLines = spec.lead ? gWrap(ctx, spec.lead, Math.round(maxW * 0.86)) : [];
    const blockH = hLines.length * hl + (lLines.length ? Math.round(22 * u) + lLines.length * LEAD_LH : 0);
    block = blockH;
    /* Room for the source line, which is pinned to the bottom margin and drawn last. */
    const reserve = Math.round((spec.footnote || spec.chip_label ? 96 : 46) * u);
    // where the block must end, and how tall it may be: a title hangs from that line, a quote is centred on the card
    bottomY = Math.min(H - M - reserve, spec.footnote ? bottomY : H);
    room = quote ? Math.min(2 * bottomY - H, H - 2 * Math.round(190 * u)) : bottomY - Math.round(190 * u);
    y = Math.max(Math.round(190 * u), quote ? Math.round((H - blockH) / 2) : bottomY - blockH);
    if (spec.eyebrow && !quote) gEyebrow(ctx, spec.eyebrow, M, y - Math.round(54 * u), "#FFFFFF", Math.round(23 * u));
    y = gHeadline(ctx, headText, M, y, maxW, hp, hl, "#FFFFFF", GRID_PAL.yellow);
    if (lLines.length) {
      y += Math.round(22 * u);
      y = gPara(ctx, spec.lead, M, y, Math.round(maxW * 0.86), LEAD_PX, LEAD_LH, "rgba(255,255,255,.84)");
    }
  }
  /* Always over a photograph here, so the mark is always knocked out. */
  await drawBrandMark(ctx, spec, W, u, M, { top: 56, h: 34, knockout: true, textFill: "rgba(255,255,255,.88)" });
  gSourceLine(ctx, W, H, M, u, spec.chip_label || (spec.footnote ? "Sumber" : ""), spec.footnote || "", t !== "p_fact");
  if (y > bottomY + 1) warn.push("The slide is fuller than the card: shorten a line.");
  return canvasOut ? { url: canvasOut.toDataURL("image/jpeg", 0.9), warn, y, block, room } : { warn, y, block, room };
}
/* ======================= COPIED FROM STUDIO (end) ========================= */

/* ======================= SEMASA: nine more designs ========================== */
/* Wan, 4 Oct 2026: "I want to have more design like ERA, grid, photo". Three new templates in each of Studio's three
   families, drawn with the family's own palette and helpers above, so a post can mix them freely:
     Grid   g_check  checklist panel        g_myth     myth | fact, side by side     g_steps  numbered timeline
     ERA    e_myth   struck myth, red fact  e_check  tipped notes with ticks        e_stat   one big red figure
     Photo  p_stat   figure over the photo  p_list   glass panels over the photo    p_split  photo above, dark panel below
   Same rules as the older templates: nothing is sliced to fit (a slide that is fuller than the card says so and the
   worker refuses it, so a point is never silently dropped), `*word*` takes the accent, and a ground (`spec.bg`) works
   under every one of them. All but p_split are centred between the handle and the source line the way the Grid family is
   (measure first, then shift). That is safe for the ERA ones too, unlike the older ERA templates: none of these carries a
   character, so nothing in them sizes off where they start (the rule in renderEraCard). */
const MORE_TPL = { g_check: 1, g_myth: 1, g_steps: 1, e_myth: 1, e_check: 1, e_stat: 1, e_event: 1, p_stat: 1, p_list: 1, p_split: 1 };
const MORE_CENTRED = { g_check: 1, g_myth: 1, g_steps: 1, e_myth: 1, e_check: 1, e_stat: 1, p_stat: 1, p_list: 1 };
const moreLabels = (spec) => (spec.stream === "linkedin" ? { myth: "MYTH", fact: "FACT" } : { myth: "MITOS", fact: "FAKTA" });

async function renderMoreCard(spec) {
  const [W, H] = sizeOf(spec);
  const c = document.createElement("canvas"); c.width = W; c.height = H;
  const ctx = styleCtx(c.getContext("2d"), spec);
  try { await document.fonts.ready; } catch (e) { }
  const u = W / 1080, t = spec.template, era = t[0] === "e";
  const measure = async (sp) => { ctx.save(); try { return await morePaint(measureProxy(ctx), sp, W, H, 0); } finally { ctx.restore(); } };
  if (t === "e_event") {
    /* The event poster is anchored top and bottom, so there is nothing to centre; when the headline and the speakers do not fit
       together its type comes down until they do (auto-fit, 16 Nov 2026), and it warns only when FIT_MIN is not enough. */
    const full = async (f) => (await measure(f === 1 ? spec : { ...spec, _fill: f })).warn.some((w) => w.includes("fuller than the card"));
    let f = 1;
    if (!spec.type_size && await full(1)) {
      f = FIT_MIN;
      if (!(await full(FIT_MIN))) { let lo = FIT_MIN, hi = 1; for (let i = 0; i < 6; i++) { const mid = (lo + hi) / 2; if (await full(mid)) hi = mid; else lo = mid; } f = Math.floor(lo * 100) / 100; }
    }
    return morePaint(ctx, f !== 1 ? { ...spec, _fill: f } : spec, W, H, 0, c);
  }
  /* Measured, fitted and centred like the grid family (9 Nov 2026: "each carousel page is compact, not looks empty"): the type grows
     to fill the card, and since 16 Nov 2026 (auto-fit) shrinks when the card is too full. The ERA ones grow as far as the other ERA
     slides do: none of them carries a character, so nothing in them sizes off the room the words leave. p_split is fitted to its
     dark panel, the lower half of the card: its photograph does not move. */
  const topU = t === "p_split" ? Math.round(H * 0.5) / u + 44 : era ? 138 : 150;
  const floor = cardFloor(ctx, spec, W, H, Math.round(72 * u), u);
  const probe = await measure(spec);
  const max = Math.max(1, Math.min(era ? ERA_MORE_MAX : HOOK_TPL[t] ? FILL_MAX : FILL_BODY_MAX, moreWordCap(ctx, spec, W)));
  const fill = spec.type_size || spec.mascot ? 1
    : await fillScale(spec, H, u, topU, probe.y, measure, max, era ? ERA_FILL_FROM : FILL_FROM, era ? ERA_FILL_TARGET : FILL_TARGET, floor);
  const drawn = fill !== 1 ? { ...spec, _fill: fill } : spec;
  const end = fill !== 1 ? (await measure(drawn)).y : probe.y;
  return morePaint(ctx, drawn, W, H, centreShift(H, u, end, topU, floor), c);
}
function moreWordCap(ctx, spec, W) {
  const u = W / 1080, maxW = W - Math.round(72 * u) * 2, t = spec.template;
  const rows = (spec.items || []).map((x) => String(x || "").trim()).filter(Boolean).map(gCells);
  const headPx = t[0] === "e" ? 56 : t === "p_stat" ? 58 : t === "p_list" ? 66 : t === "p_split" ? 54 : 74;
  const parts = [[spec.title, headPx, 800, G_HEAD, maxW], [spec.lead, 32, 500, G_BODY, Math.round(maxW * 0.9)]];
  const half = Math.round((maxW - Math.round(24 * u)) / 2) - Math.round(56 * u), col = maxW - Math.round(170 * u);
  for (const r of rows) {
    if (t === "g_myth") parts.push([r[0], 28, 600, G_BODY, half], [r[1], 28, 700, G_BODY, half]);
    else if (t === "e_myth") parts.push([r[0], 34, 600, G_BODY, maxW - Math.round(64 * u)], [r[1], 38, 800, G_HEAD, maxW - Math.round(64 * u)]);
    else if (t === "p_split") parts.push([r.join(" "), 28, 600, G_BODY, maxW - Math.round(34 * u)]);
    else if (t !== "e_stat" && t !== "p_stat") parts.push([r[0], 34, 800, G_HEAD, col], [r.slice(1).join(" "), 28, 500, G_BODY, col]);
  }
  return wordCap(ctx, u, parts);
}

/* A figure sized to the column: the largest size up to maxPx that fits, never below 40. */
function fitFigure(ctx, text, maxW, maxPx, family) {
  let px = maxPx;
  ctx.font = "800 " + px + "px " + family;
  while (px > 40 && ctx.measureText(text).width > maxW) { px -= 4; ctx.font = "800 " + px + "px " + family; }
  return px;
}
/* A tick or a cross, drawn as strokes so it needs no font. */
function moreMark(ctx, kind, x, y, s, colour, lw) {
  ctx.save(); ctx.strokeStyle = colour; ctx.lineWidth = lw; ctx.lineCap = "round"; ctx.lineJoin = "round";
  ctx.beginPath();
  if (kind === "tick") { ctx.moveTo(x + s * 0.2, y + s * 0.54); ctx.lineTo(x + s * 0.42, y + s * 0.76); ctx.lineTo(x + s * 0.82, y + s * 0.26); }
  else { ctx.moveTo(x + s * 0.24, y + s * 0.24); ctx.lineTo(x + s * 0.76, y + s * 0.76); ctx.moveTo(x + s * 0.76, y + s * 0.24); ctx.lineTo(x + s * 0.24, y + s * 0.76); }
  ctx.stroke(); ctx.restore();
}
/* A coloured block tipped a degree, the red twin of eraCard (which is always white paper). */
function eraBlock(ctx, x, y, w, h, rot, fill, paint) {
  ctx.save();
  ctx.translate(x + w / 2, y + h / 2); ctx.rotate(rot || 0); ctx.translate(-w / 2, -h / 2);
  ctx.shadowColor = "rgba(20,20,20,.22)"; ctx.shadowBlur = Math.round(w * 0.04); ctx.shadowOffsetY = Math.round(w * 0.014);
  ctx.fillStyle = fill; ctx.fillRect(0, 0, w, h);
  ctx.shadowColor = "transparent";
  if (paint) paint(ctx, w, h);
  ctx.restore();
}
/* A small black label stuck on a note ("MITOS", "FAKTA"). Returns its height. */
function eraTag(ctx, text, x, y, px, fill, colour) {
  ctx.font = "800 " + px + "px " + G_HEAD; ctx.textBaseline = "top";
  const padX = Math.round(px * 0.6), h = Math.round(px * 1.7), w = ctx.measureText(text).width + padX * 2;
  ctx.fillStyle = fill || ERA_PAL.ink; gRound(ctx, x, y, w, h, Math.round(px * 0.3)); ctx.fill();
  ctx.fillStyle = colour || "#FFFFFF"; ctx.fillText(text, x + padX, y + Math.round((h - px) / 2) - Math.round(px * 0.05));
  return h;
}


/* ---- e_event: an event poster (Wan, 4 Oct 2026, from a symposium poster: "make sure semasa can render and design based on
   this attached, same like info ERA"). The words arrive in the slide's usual fields:
     eyebrow  the small spaced label on top ("SCIENTIFIC SYMPOSIUM")      lead   the boxed topic, one or two lines
     title    the headline: *bold* phrases on their own lines, the rest light ("*SAFE & EFFECTIVE* TREATMENT ... *HYPERPIGMENTATION*")
     points   one speaker each, "Name | Country", with a round picture slot      note   "Wednesday 30 Sep 2026 | 16:15 - 17:00 | Room: Hub 2"
     chip     the organiser under the date ("EADV CONGRESS")                       footnote  an optional source line, drawn as everywhere else
   The date is read into the big day, the month, the year and the lines under them; a note that is not a date is drawn as plain
   bold lines, so nothing typed is ever lost. Sits on a ground, light or dark, or on the ERA paper. */
const MONTHS = { jan: "JAN", feb: "FEB", mar: "MAR", apr: "APR", may: "MAY", mei: "MEI", jun: "JUN", jul: "JUL", aug: "AUG", ogo: "OGO", sep: "SEP",
  oct: "OCT", okt: "OKT", nov: "NOV", dec: "DEC", dis: "DIS" };
export function eventDate(note) {
  const parts = String(note || "").split("|").map((x) => x.trim()).filter(Boolean);
  const m = /^(?:([A-Za-zÀ-ÿ']{3,})\.?,?\s+)?(\d{1,2})\s+([A-Za-zÀ-ÿ]{3,})\.?\s+(\d{4})$/.exec(parts[0] || "");
  if (!m) return { day: "", weekday: "", month: "", year: "", lines: parts };
  return { weekday: (m[1] || "").toUpperCase(), day: m[2], month: MONTHS[m[3].slice(0, 3).toLowerCase()] || m[3].toUpperCase().slice(0, 4), year: m[4], lines: parts.slice(1) };
}
const TITLE_RE = /^(assoc\.?\s*prof\.?|prof\.?|dr\.?|ts\.?|dato'?|datin|datuk|puan|encik|cik|mr\.?|ms\.?|mrs\.?)\s+/i;
export function initialsOf(name) {
  const words = String(name || "").replace(TITLE_RE, "").replace(TITLE_RE, "").split(/\s+/).filter(Boolean);
  return ((words[0] || "")[0] || "") + ((words.length > 1 ? words[words.length - 1] : "")[0] || "");
}
/* The headline in two weights. Every *bold* phrase takes its own line(s); the words between wrap freely in the light face. */
function eventHeadline(ctx, text, x, y, maxW, px, lh, ink) {
  const bold = "800 " + px + "px " + G_HEAD, light = "400 " + Math.round(px * 1.04) + "px " + G_BODY;
  ctx.textBaseline = "top"; ctx.fillStyle = ink;
  const groups = [];
  for (const tk of gTokens(String(text || "").toUpperCase(), 0, 1)) {
    for (const seg of tk.t.split("\n")) if (seg.trim()) groups.push({ t: seg.trim(), b: tk.c === 1 });
  }
  for (const g of groups) {
    ctx.font = g.b ? bold : light;
    const words = g.t.split(/\s+/).flatMap((w) => hardSplit(ctx, w, maxW));
    let line = "";
    for (const w of words) {
      const next = line ? line + " " + w : w;
      if (line && ctx.measureText(next).width > maxW) { ctx.fillText(line, x, y); y += lh; line = w; } else line = next;
    }
    if (line) { ctx.fillText(line, x, y); y += lh; }
  }
  return y;
}
/* The four small corner brackets round the topic box (the reference's way of framing it). */
function cornerBrackets(ctx, x, y, w, h, len, off, colour, lw) {
  ctx.save(); ctx.strokeStyle = colour; ctx.lineWidth = lw; ctx.lineCap = "butt"; ctx.beginPath();
  const x0 = x - off, y0 = y - off, x1 = x + w + off, y1 = y + h + off;
  ctx.moveTo(x0, y0 + len); ctx.lineTo(x0, y0); ctx.lineTo(x0 + len, y0);
  ctx.moveTo(x1 - len, y0); ctx.lineTo(x1, y0); ctx.lineTo(x1, y0 + len);
  ctx.moveTo(x0, y1 - len); ctx.lineTo(x0, y1); ctx.lineTo(x0 + len, y1);
  ctx.stroke(); ctx.restore();
}

async function morePaint(ctx, spec, W, H, yShift, canvasOut) {
  const warn = [];
  const t = spec.template, u = W / 1080, M = Math.round(72 * u), maxW = W - M * 2;
  const fam = t[0];                                                // g | e | p
  const items = (spec.items || []).filter((x) => String(x || "").trim());
  const TS = textScale(spec);
  const HEAD_PX = Math.round(74 * u * TS), HEAD_LH = Math.round(86 * u * TS);
  const LEAD_PX = Math.round(32 * u * TS), LEAD_LH = Math.round(45 * u * TS);
  const IH = Math.round(34 * u * TS), IB = Math.round(28 * u * TS), IBL = Math.round(38 * u * TS);
  const us = u * TS;                       // inside a design's own layout every gap, box and number moves with its words (auto-fit)
  const accent = GRID_PAL.orange, red = ERA_PAL.red;
  let dark = false, ink = GRID_PAL.ink, muted = GRID_PAL.muted;
  let bg = null;
  if (fam === "p") {
    bg = spec.bg ? await loadImg(spec.bg) : null;
    if (!bg) warn.push("This design is built on a picture and none is chosen: pick one under Background.");
    dark = true; ink = "#FFFFFF"; muted = "rgba(255,255,255,.78)";
  } else if (fam === "g") {
    dark = inkWhite(spec);
    if (dark) { ink = "#FFFFFF"; muted = "rgba(255,255,255,.66)"; }
    if (!await drawGround(ctx, spec, W, H)) gPaper(ctx, W, H, false);
  } else {
    const onGround = inkWhite(spec);
    if (onGround) { ink = "#FFFFFF"; muted = "rgba(255,255,255,.72)"; }
    if (!await drawGround(ctx, spec, W, H)) eraPaper(ctx, W, H);
    ink = onGround ? "#FFFFFF" : ERA_PAL.ink; muted = onGround ? "rgba(255,255,255,.72)" : ERA_PAL.muted;
  }
  const photo = (x, y, w, h) => {
    ctx.save(); ctx.beginPath(); ctx.rect(x, y, w, h); ctx.clip(); ctx.translate(x, y);
    if (bg) { if (h >= H) coverSoft(ctx, bg, w, h, false); else coverDraw(ctx, bg, w, h); }
    else { const g = ctx.createLinearGradient(0, 0, 0, h); g.addColorStop(0, "#2B323A"); g.addColorStop(1, "#11151A"); ctx.fillStyle = g; ctx.fillRect(0, 0, w, h); }
    ctx.restore();
  };
  const scrim = (x, y, w, h, level) => {
    const s = SCRIM[level] || SCRIM.medium, g = ctx.createLinearGradient(x, y, x, y + h);
    g.addColorStop(0, "rgba(8,10,12," + s[0] + ")"); g.addColorStop(0.55, "rgba(8,10,12," + s[1] + ")"); g.addColorStop(1, "rgba(8,10,12," + s[2] + ")");
    ctx.fillStyle = g; ctx.fillRect(x, y, w, h);
  };
  const panel = (x, y, w, h) => (dark
    ? gPanel(ctx, x, y, w, h, { fill: "rgba(255,255,255,.08)", shadow: false, stroke: "rgba(255,255,255,.16)" })
    : gPanel(ctx, x, y, w, h));
  const sticky = (y) => {
    if (!spec.note) return y;
    const h = gSticky(ctx, W - M - Math.round(410 * u), y + Math.round(26 * u), Math.round(410 * u), spec.note, GRID_PAL.yellow, 0.03, Math.round(46 * u * Math.min(1, TS)));
    return y + Math.round(26 * u) + h + Math.round(10 * u);
  };
  let y = Math.round((fam === "e" ? 138 : 150) * u) + (yShift || 0);
  const scrimLevel = spec.scrim || (spec.stream === "linkedin" ? "heavy" : "medium");

  if (t === "g_check") {
    y = gEyebrow(ctx, spec.eyebrow, M, y, accent, Math.round(24 * u));
    y = gHeadline(ctx, spec.title || "", M, y, maxW, HEAD_PX, HEAD_LH, ink, accent);
    y += Math.round(18 * us);
    if (spec.lead) y = gPara(ctx, spec.lead, M, y, Math.round(maxW * 0.92), LEAD_PX, LEAD_LH, muted);
    y += Math.round(22 * us);
    const box = Math.round(46 * us), padX = Math.round(38 * us), textX = M + padX + box + Math.round(26 * us), textW = M + maxW - padX - textX;
    const gap = Math.round(30 * us);
    const lay = items.map(gCells).map((r) => {
      ctx.font = "700 " + IH + "px " + G_HEAD; const hl = gWrap(ctx, r[0] || "", textW);
      ctx.font = "500 " + IB + "px " + G_BODY; const bl = r[1] ? gWrap(ctx, r[1], textW) : [];
      return { hl, bl, h: Math.max(box, hl.length * Math.round(IH * 1.2) + (bl.length ? Math.round(6 * us) + bl.length * IBL : 0)) };
    });
    const total = lay.reduce((s, r) => s + r.h, 0) + gap * Math.max(0, lay.length - 1) + Math.round(76 * us);
    panel(M, y, maxW, total);
    let ry = y + Math.round(38 * us);
    lay.forEach((r, i) => {
      ctx.fillStyle = accent; gRound(ctx, M + padX, ry, box, box, Math.round(12 * us)); ctx.fill();
      moreMark(ctx, "tick", M + padX, ry, box, "#FFFFFF", Math.max(4, Math.round(7 * us)));
      let ty = ry; ctx.textBaseline = "top";
      ctx.font = "700 " + IH + "px " + G_HEAD; ctx.fillStyle = ink;
      for (const l of r.hl) { ctx.fillText(l, textX, ty); ty += Math.round(IH * 1.2); }
      if (r.bl.length) { ty += Math.round(6 * us); ctx.font = "500 " + IB + "px " + G_BODY; ctx.fillStyle = muted; for (const l of r.bl) { ctx.fillText(l, textX, ty); ty += IBL; } }
      if (i < lay.length - 1) {
        ctx.save(); ctx.strokeStyle = dark ? "rgba(255,255,255,.14)" : GRID_PAL.panelLine; ctx.lineWidth = 2; ctx.setLineDash([8, 8]);
        const ly = ry + r.h + Math.round(gap / 2); ctx.beginPath(); ctx.moveTo(M + padX, ly); ctx.lineTo(M + maxW - padX, ly); ctx.stroke(); ctx.restore();
      }
      ry += r.h + gap;
    });
    y = sticky(y + total);
  } else if (t === "g_myth") {
    const L = moreLabels(spec);
    y = gEyebrow(ctx, spec.eyebrow, M, y, accent, Math.round(24 * u));
    y = gHeadline(ctx, spec.title || "", M, y, maxW, HEAD_PX, HEAD_LH, ink, accent);
    y += Math.round(18 * us);
    if (spec.lead) y = gPara(ctx, spec.lead, M, y, Math.round(maxW * 0.92), LEAD_PX, LEAD_LH, muted);
    y += Math.round(24 * us);
    const gap = Math.round(24 * us), colW = Math.round((maxW - gap) / 2), pad = Math.round(28 * us);
    // the two column labels, each with its own mark
    const lp = Math.round(26 * us), ic = Math.round(38 * us);
    [[M, L.myth, "cross", muted], [M + colW + gap, L.fact, "tick", accent]].forEach(([x, label, kind, col]) => {
      ctx.fillStyle = kind === "tick" ? accent : (dark ? "rgba(255,255,255,.22)" : "#CFC6B2");
      ctx.beginPath(); ctx.arc(x + ic / 2, y + ic / 2, ic / 2, 0, Math.PI * 2); ctx.fill();
      moreMark(ctx, kind, x + ic * 0.12, y + ic * 0.12, ic * 0.76, kind === "tick" ? "#FFFFFF" : ink, Math.max(3, Math.round(5 * us)));
      ctx.font = "800 " + lp + "px " + G_HEAD; ctx.fillStyle = col; ctx.textBaseline = "top";
      try { ctx.letterSpacing = Math.round(lp * 0.14) + "px"; } catch (e) { }
      ctx.fillText(label, x + ic + Math.round(14 * us), y + Math.round((ic - lp) / 2));
      try { ctx.letterSpacing = "0px"; } catch (e) { }
    });
    y += ic + Math.round(18 * us);
    for (const r of items.map(gCells)) {
      ctx.font = "600 " + IB + "px " + G_BODY; const ml = gWrap(ctx, r[0] || "", colW - pad * 2);
      ctx.font = "700 " + IB + "px " + G_BODY; const fl = gWrap(ctx, r[1] || "", colW - pad * 2);
      const h = Math.max(ml.length, fl.length) * IBL + pad * 2;
      gPanel(ctx, M, y, colW, h, { fill: dark ? "rgba(255,255,255,.05)" : "#EDE6D6", shadow: false, stroke: dark ? "rgba(255,255,255,.1)" : GRID_PAL.panelLine, r: 22 });
      panel(M + colW + gap, y, colW, h);
      ctx.textBaseline = "top";
      ctx.font = "600 " + IB + "px " + G_BODY; ctx.fillStyle = muted;
      ml.forEach((l, i) => {
        const ly = y + pad + i * IBL; ctx.fillText(l, M + pad, ly);
        ctx.save(); ctx.strokeStyle = dark ? "rgba(255,255,255,.55)" : "#8A6F5A"; ctx.lineWidth = Math.max(2, Math.round(3 * us));
        ctx.beginPath(); ctx.moveTo(M + pad, ly + Math.round(IB * 0.58)); ctx.lineTo(M + pad + ctx.measureText(l).width, ly + Math.round(IB * 0.58)); ctx.stroke(); ctx.restore();
      });
      ctx.font = "700 " + IB + "px " + G_BODY; ctx.fillStyle = ink;
      fl.forEach((l, i) => ctx.fillText(l, M + colW + gap + pad, y + pad + i * IBL));
      y += h + Math.round(18 * us);
    }
    y = sticky(y);
  } else if (t === "g_steps") {
    y = gEyebrow(ctx, spec.eyebrow, M, y, accent, Math.round(24 * u));
    y = gHeadline(ctx, spec.title || "", M, y, maxW, HEAD_PX, HEAD_LH, ink, accent);
    y += Math.round(18 * us);
    if (spec.lead) y = gPara(ctx, spec.lead, M, y, Math.round(maxW * 0.92), LEAD_PX, LEAD_LH, muted);
    y += Math.round(30 * us);
    const r0 = Math.round(32 * us), textX = M + r0 * 2 + Math.round(30 * us), textW = M + maxW - textX, gap = Math.round(30 * us);
    const lay = items.map(gCells).map((r) => {
      ctx.font = "700 " + IH + "px " + G_HEAD; const hl = gWrap(ctx, r[0] || "", textW);
      ctx.font = "500 " + IB + "px " + G_BODY; const bl = r[1] ? gWrap(ctx, r[1], textW) : [];
      return { hl, bl, h: Math.max(r0 * 2, hl.length * Math.round(IH * 1.2) + (bl.length ? Math.round(6 * us) + bl.length * IBL : 0)) };
    });
    if (lay.length > 1) {                                           // the rail the numbers sit on
      const top = y + r0, bottom = y + lay.slice(0, -1).reduce((s, r) => s + r.h + gap, 0) + r0;
      ctx.save(); ctx.strokeStyle = dark ? "rgba(255,255,255,.28)" : "#D9CFBA"; ctx.lineWidth = Math.max(4, Math.round(6 * us)); ctx.lineCap = "round";
      ctx.beginPath(); ctx.moveTo(M + r0, top); ctx.lineTo(M + r0, bottom); ctx.stroke(); ctx.restore();
    }
    lay.forEach((r, i) => {
      ctx.fillStyle = accent; ctx.beginPath(); ctx.arc(M + r0, y + r0, r0, 0, Math.PI * 2); ctx.fill();
      ctx.font = "800 " + Math.round(34 * us) + "px " + G_HEAD; ctx.fillStyle = "#FFFFFF"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.fillText(String(i + 1), M + r0, y + r0 + Math.round(2 * us)); ctx.textAlign = "left"; ctx.textBaseline = "top";
      let ty = y; ctx.font = "700 " + IH + "px " + G_HEAD; ctx.fillStyle = ink;
      for (const l of r.hl) { ctx.fillText(l, textX, ty); ty += Math.round(IH * 1.2); }
      if (r.bl.length) { ty += Math.round(6 * us); ctx.font = "500 " + IB + "px " + G_BODY; ctx.fillStyle = muted; for (const l of r.bl) { ctx.fillText(l, textX, ty); ty += IBL; } }
      y += r.h + gap;
    });
    y = sticky(y - gap);
  } else if (t === "e_myth") {
    const L = moreLabels(spec);
    await drawBrandMark(ctx, spec, W, u, M, { top: 54, h: 34, knockout: inkWhite(spec), textFill: inkWhite(spec) ? "rgba(255,255,255,.7)" : "rgba(21,21,21,.6)" });
    eraBadge(ctx, W, u, M, spec.eyebrow, spec);
    y = eraMark(ctx, spec.title || "", M, y, maxW, Math.round(56 * u * TS), Math.round(70 * u * TS), ink, red);
    y += Math.round(30 * us);
    if (spec.lead) { y = gPara(ctx, spec.lead, M, y, Math.round(maxW * 0.92), LEAD_PX, LEAD_LH, muted); y += Math.round(10 * us); }
    const pad = Math.round(32 * us), tagPx = Math.round(24 * us), textW = maxW - pad * 2;
    items.map(gCells).forEach((p, i, all) => {
      ctx.font = "600 " + IH + "px " + G_BODY; const ml = gWrap(ctx, p[0] || "", textW);
      ctx.font = "800 " + Math.round(38 * u * TS) + "px " + G_HEAD; const fl = gWrap(ctx, p[1] || "", textW);
      const fh = Math.round(38 * u * TS * 1.2), tagH = Math.round(tagPx * 1.7);
      const h1 = pad + tagH + Math.round(14 * us) + ml.length * Math.round(IH * 1.3) + pad;
      eraCard(ctx, M, y, maxW, h1, -0.007, (k) => {
        eraTag(k, L.myth, pad, pad, tagPx);
        k.textBaseline = "top"; k.font = "600 " + IH + "px " + G_BODY; k.fillStyle = ERA_PAL.muted;
        let ty = pad + tagH + Math.round(14 * us);
        for (const l of ml) {
          k.fillText(l, pad, ty);
          k.save(); k.strokeStyle = red; k.lineWidth = Math.max(3, Math.round(5 * us));
          const ly = ty + Math.round(IH * 0.6); k.beginPath(); k.moveTo(pad - 6, ly + 1); k.lineTo(pad + k.measureText(l).width + 6, ly - 2); k.stroke(); k.restore();
          ty += Math.round(IH * 1.3);
        }
      });
      y += h1 + Math.round(10 * us);
      eraArrow(ctx, M + Math.round(maxW * 0.5), y, M + Math.round(maxW * 0.5), y + Math.round(44 * us), Math.round(12 * us), red, Math.max(3, Math.round(6 * us)));
      y += Math.round(58 * us);
      const h2 = pad + tagH + Math.round(14 * us) + fl.length * fh + pad;
      eraBlock(ctx, M, y, maxW, h2, 0.006, red, (k) => {
        eraTag(k, L.fact, pad, pad, tagPx, ERA_PAL.yellow, ERA_PAL.ink);
        k.textBaseline = "top"; k.font = "800 " + Math.round(38 * u * TS) + "px " + G_HEAD; k.fillStyle = "#FFFFFF";
        let ty = pad + tagH + Math.round(14 * us);
        for (const l of fl) { k.fillText(l, pad, ty); ty += fh; }
      });
      y += h2 + Math.round((i < all.length - 1 ? 34 : 24) * u);
    });
    if (spec.note) y = eraBand(ctx, M, y, maxW, spec.note, Math.round(32 * us));
  } else if (t === "e_check") {
    await drawBrandMark(ctx, spec, W, u, M, { top: 54, h: 34, knockout: inkWhite(spec), textFill: inkWhite(spec) ? "rgba(255,255,255,.7)" : "rgba(21,21,21,.6)" });
    eraBadge(ctx, W, u, M, spec.eyebrow, spec);
    y = eraMark(ctx, spec.title || "", M, y, maxW, Math.round(56 * u * TS), Math.round(70 * u * TS), ink, red);
    y += Math.round(30 * us);
    if (spec.lead) { y = gPara(ctx, spec.lead, M, y, Math.round(maxW * 0.92), LEAD_PX, LEAD_LH, muted); y += Math.round(10 * us); }
    const box = Math.round(52 * us), inset = Math.round(40 * us) + box + Math.round(26 * us), textW = maxW - inset - Math.round(30 * us);
    items.map(gCells).forEach((r, i) => {
      ctx.font = "800 " + IH + "px " + G_HEAD; const hl = gWrap(ctx, r[0] || "", textW);
      ctx.font = "500 " + IB + "px " + G_BODY; const bl = r[1] ? gWrap(ctx, r[1], textW) : [];
      const h = Math.round(30 * us) + hl.length * Math.round(IH * 1.2) + bl.length * IBL + Math.round(22 * us);
      eraCard(ctx, M, y, maxW, h, i % 2 ? 0.006 : -0.006, (k) => {
        const bx = Math.round(40 * us), by = Math.round(28 * us);
        k.strokeStyle = ERA_PAL.ink; k.lineWidth = Math.max(3, Math.round(5 * us)); k.strokeRect(bx, by, box, box);
        moreMark(k, "tick", bx - Math.round(2 * us), by - Math.round(14 * us), box * 1.15, red, Math.max(5, Math.round(9 * us)));
        k.textBaseline = "top"; let ty = Math.round(30 * us);
        k.font = "800 " + IH + "px " + G_HEAD; k.fillStyle = ERA_PAL.ink;
        for (const l of hl) { k.fillText(l, inset, ty); ty += Math.round(IH * 1.2); }
        k.font = "500 " + IB + "px " + G_BODY; k.fillStyle = ERA_PAL.muted;
        for (const l of bl) { k.fillText(l, inset, ty); ty += IBL; }
      });
      y += h + Math.round(26 * us);
    });
    if (spec.note) y = eraBand(ctx, M, y, maxW, spec.note, Math.round(32 * us));
  } else if (t === "e_event") {
    const white = inkWhite(spec), line = white ? "rgba(255,255,255,.9)" : ink;
    const speakers = items.map(gCells).map((r) => ({ name: r[0] || "", where: r[1] || "" })).filter((r) => r.name);
    const top = Math.round(50 * u);
    ctx.textBaseline = "top"; ctx.fillStyle = ink;
    try { ctx.letterSpacing = Math.round(3 * u) + "px"; } catch (e) { }
    if (spec.eyebrow) {
      // the label stays clear of the logo at the top right: it comes down in size, then takes a second line
      const label = stripEmph(spec.eyebrow).toUpperCase(), room = maxW - (spec.stream === "linkedin" ? 0 : Math.round(300 * u));
      let ep = Math.round(25 * u); ctx.font = "700 " + ep + "px " + G_HEAD;
      while (ep > Math.round(17 * u) && ctx.measureText(label).width > room) { ep -= 1; ctx.font = "700 " + ep + "px " + G_HEAD; }
      gWrap(ctx, label, room).slice(0, 2).forEach((l, i) => ctx.fillText(l, M, top + Math.round(4 * u) + i * Math.round(ep * 1.25) - (i ? 0 : 0)));
    }
    try { ctx.letterSpacing = "0px"; } catch (e) { }
    await drawBrandMark(ctx, spec, W, u, M, { top: 48, h: 34, right: true, knockout: white, textFill: white ? "rgba(255,255,255,.7)" : "rgba(21,21,21,.6)" });
    y = top + Math.round(70 * u);
    // the boxed topic
    if (spec.lead) {
      const lp = Math.round(27 * u * TS), lines = String(spec.lead).split("\n").map((x) => x.trim()).filter(Boolean);
      ctx.font = "700 " + lp + "px " + G_HEAD;
      const wrapped = lines.flatMap((l, i) => { ctx.font = (i === 0 ? "700 " : "500 ") + lp + "px " + (i === 0 ? G_HEAD : G_BODY); return gWrap(ctx, stripEmph(l).toUpperCase(), Math.round(maxW * 0.8)).map((t2) => ({ t: t2, b: i === 0 })); });
      const padX = Math.round(26 * u), padY = Math.round(18 * u), lh = Math.round(lp * 1.3);
      let tw = 0;
      for (const w2 of wrapped) { ctx.font = (w2.b ? "700 " : "500 ") + lp + "px " + (w2.b ? G_HEAD : G_BODY); tw = Math.max(tw, ctx.measureText(w2.t).width); }
      const bw = Math.round(tw + padX * 2), bh = wrapped.length * lh + padY * 2;
      ctx.save(); ctx.fillStyle = white ? "rgba(255,255,255,.16)" : "rgba(214,200,226,.55)"; gRound(ctx, M, y, bw, bh, Math.round(10 * u)); ctx.fill(); ctx.restore();
      cornerBrackets(ctx, M, y, bw, bh, Math.round(26 * u), Math.round(8 * u), line, Math.max(2, Math.round(3 * u)));
      ctx.textBaseline = "top"; ctx.fillStyle = ink;
      wrapped.forEach((w2, i) => { ctx.font = (w2.b ? "700 " : "500 ") + lp + "px " + (w2.b ? G_HEAD : G_BODY); ctx.fillText(w2.t, M + padX, y + padY + i * lh + Math.round(lp * 0.06)); });
      y += bh + Math.round(46 * u);
    }
    y = eventHeadline(ctx, spec.title || "", M, y, maxW, Math.round(60 * u * TS), Math.round(70 * u * TS), ink);
    const topEnd = y;
    // the foot: speakers on the left, the date on the right, both anchored to the bottom
    const foot = spec.footnote ? Math.min(H - Math.round(130 * u), sourceTop(ctx, spec, W, H, M, u) - Math.round(14 * u)) : H - Math.round(78 * u);
    // the closing slide of a set is handed "Sumber"/"Source" as its chip (specsFor): that is the source line's label, not an organiser
    const organiser = spec.chip_label && !/^(sumber|source)$/i.test(String(spec.chip_label).trim()) ? spec.chip_label : "";
    const colR = Math.round(W * 0.655);
    const dt = eventDate(spec.note);
    const dayPx = Math.round(128 * u), monPx = Math.round(70 * u), yrPx = Math.round(118 * u), dPx = Math.round(31 * u);
    const faces = await Promise.all((spec.avatars || []).map(async (u2) => { try { return u2 ? await loadImg(u2) : null; } catch (e) { return null; } }));
    if (speakers.length) {
      const room = foot - (topEnd + Math.round(34 * u));
      const pitch = Math.min(Math.round(112 * u), Math.floor(room / speakers.length));
      const d = Math.round(pitch * 0.84), namePx = Math.min(Math.round(27 * u * TS), Math.round(pitch * 0.3)), whPx = Math.round(namePx * 0.96);
      const tx = M + d + Math.round(26 * u), tw = colR - tx - Math.round(30 * u);
      if (pitch < Math.round(66 * u)) warn.push("The speakers are fuller than the card: use fewer speakers or a taller card.");
      const y0 = foot - pitch * speakers.length;
      speakers.forEach((sp, i) => {
        const ry = y0 + i * pitch, cy = ry + d / 2;
        const face = faces[i] || null;                   // the speaker's own photo, cropped to the circle; else a tint with initials
        ctx.save(); ctx.fillStyle = white ? "rgba(255,255,255,.22)" : "rgba(196,186,210,.55)";
        ctx.beginPath(); ctx.arc(M + d / 2, cy, d / 2, 0, Math.PI * 2); ctx.fill();
        if (face) {
          ctx.clip(); ctx.translate(M, cy - d / 2); coverDraw(ctx, face, d, d);
        }
        ctx.restore();
        if (face) {
          ctx.save(); ctx.strokeStyle = white ? "rgba(255,255,255,.85)" : "rgba(255,255,255,.9)"; ctx.lineWidth = Math.max(2, Math.round(3 * u));
          ctx.beginPath(); ctx.arc(M + d / 2, cy, d / 2 - ctx.lineWidth / 2, 0, Math.PI * 2); ctx.stroke(); ctx.restore();
        } else {
          ctx.font = "700 " + Math.round(d * 0.3) + "px " + G_HEAD; ctx.fillStyle = muted; ctx.textAlign = "center"; ctx.textBaseline = "middle";
          ctx.fillText(initialsOf(sp.name).toUpperCase(), M + d / 2, cy + Math.round(d * 0.02));
        }
        ctx.textAlign = "left"; ctx.textBaseline = "top";
        ctx.font = "700 " + namePx + "px " + G_HEAD;
        const nl = gWrap(ctx, stripEmph(sp.name).toUpperCase(), tw);
        const lhN = Math.round(namePx * 1.22), blockH = nl.length * lhN + (sp.where ? whPx + Math.round(6 * u) : 0);
        let ty = cy - blockH / 2;
        ctx.fillStyle = ink; nl.forEach((l) => { ctx.fillText(l, tx, ty); ty += lhN; });
        if (sp.where) { ctx.font = "400 " + whPx + "px " + G_BODY; ctx.fillStyle = ink; ctx.fillText(gWrap(ctx, stripEmph(sp.where).toUpperCase(), tw)[0] || "", tx, ty + Math.round(4 * u)); }
      });
      if (y0 < topEnd + Math.round(20 * u)) warn.push("The slide is fuller than the card: shorten the headline or the topic.");
    }
    if (dt.day || dt.lines.length || organiser) {
      const w = W - M - colR;
      // the lines under the date and the organiser are wrapped to the column before the block is placed, so it ends on the foot
      ctx.font = "700 " + dPx + "px " + G_HEAD;
      const dLines = dt.lines.flatMap((l) => gWrap(ctx, stripEmph(l).toUpperCase(), w));
      ctx.font = "600 " + Math.round(dPx * 0.92) + "px " + G_HEAD;
      const chipLines = organiser ? gWrap(ctx, stripEmph(organiser).toUpperCase(), w) : [];
      const tall = (dt.day ? Math.round(dayPx * 0.92) + Math.round(yrPx * 0.9) + Math.round(22 * u) : 0) + dLines.length * Math.round(dPx * 1.35)
        + (chipLines.length ? Math.round(dPx * 0.5) + chipLines.length * Math.round(dPx * 1.2) : 0);
      let dy = foot - tall;
      if (dy < topEnd + Math.round(20 * u)) warn.push("The slide is fuller than the card: shorten the headline or the topic.");
      if (dt.day) {
        ctx.font = "800 " + dayPx + "px " + G_HEAD; ctx.textBaseline = "top"; ctx.fillStyle = ink;
        const dayW = ctx.measureText(dt.day).width;
        ctx.fillText(dt.day, colR, dy);
        const mx = colR + dayW + Math.round(14 * u);
        if (dt.weekday) { ctx.font = "500 " + Math.round(21 * u) + "px " + G_BODY; ctx.fillStyle = ink; ctx.fillText(dt.weekday, mx, dy + Math.round(8 * u)); }
        ctx.font = "400 " + monPx + "px " + G_BODY; ctx.fillStyle = ink; ctx.fillText(dt.month, mx, dy + Math.round(dayPx * 0.38));
        dy += Math.round(dayPx * 0.92);
        ctx.font = "400 " + yrPx + "px " + G_BODY; ctx.fillText(dt.year, colR, dy);
        dy += Math.round(yrPx * 0.9) + Math.round(22 * u);
      }
      ctx.font = "700 " + dPx + "px " + G_HEAD; ctx.fillStyle = ink; ctx.textBaseline = "top";
      for (const piece of dLines) { ctx.fillText(piece, colR, dy); dy += Math.round(dPx * 1.35); }
      if (chipLines.length) { ctx.font = "600 " + Math.round(dPx * 0.92) + "px " + G_HEAD; ctx.fillStyle = muted; dy += Math.round(dPx * 0.5); for (const l of chipLines) { ctx.fillText(l, colR, dy); dy += Math.round(dPx * 1.2); } }
    }
    y = warn.length ? H : Math.min(topEnd, H - Math.round(160 * u));
  } else if (t === "e_stat") {
    await drawBrandMark(ctx, spec, W, u, M, { top: 54, h: 34, knockout: inkWhite(spec), textFill: inkWhite(spec) ? "rgba(255,255,255,.7)" : "rgba(21,21,21,.6)" });
    eraBadge(ctx, W, u, M, spec.eyebrow, spec);
    y = eraMark(ctx, spec.title || "", M, y, maxW, Math.round(56 * u * TS), Math.round(70 * u * TS), ink, red);
    y += Math.round(30 * us);
    const figure = items[0] || "", unit = items[1] || "";
    if (figure) {
      const px = fitFigure(ctx, figure, maxW, Math.round(330 * u * TS), G_HEAD);
      ctx.font = "800 " + px + "px " + G_HEAD; ctx.textBaseline = "top"; ctx.fillStyle = red; ctx.fillText(figure, M, y);
      const fw = ctx.measureText(figure).width;
      eraArrow(ctx, M + Math.min(fw, maxW - Math.round(60 * us)) + Math.round(34 * us), y + Math.round(px * 1.18), M + Math.min(fw, maxW - Math.round(60 * us)) - Math.round(6 * us), y + Math.round(px * 0.9), -Math.round(16 * us), ERA_PAL.ink, Math.max(3, Math.round(6 * us)));
      y += Math.round(px * 1.12) + Math.round(8 * us);
      if (unit) y = eraMark(ctx, unit, M, y, maxW, Math.round(54 * u * TS), Math.round(66 * u * TS), ink, red);
      y += Math.round(20 * us);
    }
    if (spec.lead) { y = gPara(ctx, spec.lead, M, y, Math.round(maxW * 0.92), LEAD_PX, LEAD_LH, muted); y += Math.round(18 * us); }
    if (spec.note) y = eraBand(ctx, M, y, maxW, spec.note, Math.round(34 * us));
  } else if (t === "p_stat") {
    photo(0, 0, W, H); scrim(0, 0, W, H, scrimLevel);
    y = gEyebrow(ctx, spec.eyebrow, M, y, "#FFFFFF", Math.round(24 * u));
    const figure = items[0] || "", unit = items[1] || "";
    if (figure) {
      const px = fitFigure(ctx, figure, maxW, Math.round(320 * u * TS), G_HEAD);
      ctx.font = "800 " + px + "px " + G_HEAD; ctx.textBaseline = "top"; ctx.fillStyle = "#FFFFFF"; ctx.fillText(figure, M, y);
      const fw = ctx.measureText(figure).width, upx = Math.round(54 * u * TS);
      if (unit) {
        ctx.font = "700 " + upx + "px " + G_HEAD;
        if (fw + Math.round(28 * us) + ctx.measureText(unit).width <= maxW) { ctx.fillStyle = GRID_PAL.yellow; ctx.fillText(unit, M + fw + Math.round(28 * us), y + Math.round(px * 0.5)); y += Math.round(px * 1.12); }
        else { y += Math.round(px * 1.08); ctx.fillStyle = GRID_PAL.yellow; for (const l of gWrap(ctx, unit, maxW)) { ctx.fillText(l, M, y); y += Math.round(upx * 1.22); } y += Math.round(upx * 0.1); }
      } else y += Math.round(px * 1.12);
      y += Math.round(14 * us);
    }
    y = gHeadline(ctx, spec.title || "", M, y, maxW, Math.round(58 * u * TS), Math.round(70 * u * TS), "#FFFFFF", GRID_PAL.yellow);
    if (spec.lead) { y += Math.round(18 * us); y = gPara(ctx, spec.lead, M, y, Math.round(maxW * 0.9), LEAD_PX, LEAD_LH, "rgba(255,255,255,.84)"); }
  } else if (t === "p_list") {
    photo(0, 0, W, H); scrim(0, 0, W, H, spec.scrim || "heavy");
    y = gEyebrow(ctx, spec.eyebrow, M, y, "#FFFFFF", Math.round(24 * u));
    y = gHeadline(ctx, spec.title || "", M, y, maxW, Math.round(66 * u * TS), Math.round(78 * u * TS), "#FFFFFF", GRID_PAL.yellow);
    if (spec.lead) { y += Math.round(14 * us); y = gPara(ctx, spec.lead, M, y, Math.round(maxW * 0.9), LEAD_PX, LEAD_LH, "rgba(255,255,255,.84)"); }
    y += Math.round(26 * us);
    const numW = Math.round(76 * us), textX = M + Math.round(34 * us) + numW, textW = M + maxW - Math.round(34 * us) - textX, gap = Math.round(20 * us);
    for (const [i, r] of items.map(gCells).entries()) {
      ctx.font = "700 " + IH + "px " + G_HEAD; const hl = gWrap(ctx, r[0] || "", textW);
      ctx.font = "500 " + IB + "px " + G_BODY; const bl = r[1] ? gWrap(ctx, r[1], textW) : [];
      const h = Math.max(Math.round(110 * us), Math.round(36 * us) + hl.length * Math.round(IH * 1.2) + (bl.length ? Math.round(4 * us) + bl.length * IBL : 0));
      gPanel(ctx, M, y, maxW, h, { fill: "rgba(255,255,255,.11)", shadow: false, stroke: "rgba(255,255,255,.2)", r: 22 });
      ctx.font = "800 " + Math.round(48 * us) + "px " + G_HEAD; ctx.fillStyle = GRID_PAL.yellow; ctx.textBaseline = "top";
      ctx.fillText(String(i + 1), M + Math.round(34 * us), y + Math.round((h - 48 * us) / 2 - 4 * us));
      let ty = y + Math.round(18 * us); ctx.font = "700 " + IH + "px " + G_HEAD; ctx.fillStyle = "#FFFFFF";
      for (const l of hl) { ctx.fillText(l, textX, ty); ty += Math.round(IH * 1.2); }
      if (bl.length) { ty += Math.round(4 * us); ctx.font = "500 " + IB + "px " + G_BODY; ctx.fillStyle = "rgba(255,255,255,.8)"; for (const l of bl) { ctx.fillText(l, textX, ty); ty += IBL; } }
      y += h + gap;
    }
    y -= gap;
  } else if (t === "p_split") {
    const photoH = Math.round(H * 0.5);
    photo(0, 0, W, photoH); scrim(0, 0, W, photoH, "light");
    ctx.fillStyle = GRID_PAL.dark; ctx.fillRect(0, photoH, W, H - photoH);
    ctx.fillStyle = accent; ctx.fillRect(0, photoH, W, Math.round(10 * u));
    y = photoH + Math.round(52 * u) + (yShift || 0);
    if (spec.eyebrow) y = gEyebrow(ctx, spec.eyebrow, M, y, accent, Math.round(23 * u));
    y = gHeadline(ctx, spec.title || "", M, y, maxW, Math.round(54 * u * TS), Math.round(66 * u * TS), "#FFFFFF", GRID_PAL.yellow);
    if (spec.lead) { y += Math.round(14 * us); y = gPara(ctx, spec.lead, M, y, Math.round(maxW * 0.92), Math.round(29 * u * TS), Math.round(40 * u * TS), "rgba(255,255,255,.78)"); }
    if (items.length) {
      y += Math.round(14 * us);
      for (const it of items) {
        ctx.fillStyle = accent; ctx.beginPath(); ctx.arc(M + Math.round(9 * us), y + Math.round(15 * us), Math.round(8 * us), 0, Math.PI * 2); ctx.fill();
        y = gPara(ctx, it, M + Math.round(34 * us), y, maxW - Math.round(34 * us), Math.round(28 * u * TS), Math.round(38 * u * TS), "#FFFFFF", 600);
        y += Math.round(8 * us);
      }
    }
  }

  if (fam !== "e") await drawBrandMark(ctx, spec, W, u, M, { top: 56, h: 34, knockout: dark, textFill: dark ? "rgba(255,255,255,.62)" : "rgba(21,23,27,.5)" });
  gSourceLine(ctx, W, H, M, u, t === "e_event" ? (spec.footnote ? "Sumber" : "") : (spec.chip_label || (spec.footnote ? "Sumber" : "")), spec.footnote || "", fam === "e" ? inkWhite(spec) : dark || t === "p_split");
  if (y > cardFloor(ctx, spec, W, H, M, u) + 1) warn.push("The slide is fuller than the card: shorten a line.");
  return canvasOut ? { url: canvasOut.toDataURL("image/jpeg", 0.9), warn, y } : { warn, y };
}

/* ======================= SEMASA: slides -> Studio cards ===================== */

/* The looks Wan chooses from. "classic" is Semasa's own Pillow drawing (backend/semasa/slides.py); the other three
   are Studio's groups above, in Studio's own order: Grid first, as the house look. */
/* ===================== the Picture family ====================================
   Wan, 8 Nov 2026, with four reference slides: "create another separate slide design which have image on the slide, and create
   more slide like attached". Grid, ERA and Photo draw a picture only as a GROUND behind the words; here the picture is part of
   the slide, placed the way each reference places it, and Semasa and Grid stay as they are. Four templates, one per reference:
     i_title  a calm cream title slide: serif headline centred, a small blue label, a hand-drawn arrow to the next slide; the
              picture (when there is one) is a rounded panel above the headline
     i_note   crumpled paper and monospaced capitals, paragraph by paragraph, with the picture taped on as a small print
     i_hero   a product poster: the picture tipped on the left, a big two-tone headline on the right, a stat pill under it
     i_step   a how-to step on graph paper: "step 5" in handwriting, the picture inside a phone, the same picture again as a
              tilted before print, hand-lettered labels and arrows
   The picture is the slide's own (spec.bg, the post's picture or the one chosen): a slide with no picture is still complete,
   it simply has no panel. Words keep the ordinary fields (eyebrow, title, lead, items, note, footnote) so nothing about the
   writer changes. Fonts are the ones already loaded for the other families (Poppins, Instrument Sans, JetBrains Mono, Caveat,
   Playfair Display). No ctx.filter anywhere (iPhone Safari before 18 has none). */
const PIC_TPL = { i_title: 1, i_note: 1, i_hero: 1, i_step: 1 };
const PIC_NOTE_MAX = 84, PIC_NOTE_PHOTO = 0.62, PIC_NOTE_PRINTS = [0.36, 0.24], PIC_NOTE_READ = 40;
const PIC_PAL = { cream: "#F3ECE0", ink: "#15110E", muted: "#5F574D", blue: "#2F6BE0", mono: "#2E4B47", orange: "#F28A24", paper: "#F4F4F2" };
const PIC_SERIF = '"Playfair Display", Georgia, "Times New Roman", serif';

function picRng(seed) { let a = seed >>> 0; return () => { a = (a + 0x6D2B79F5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
/* Crumpled paper without an image file: a pale base, many faint triangular facets in slightly lighter and darker greys, and a few
   long creases. Seeded, so the same slide always draws the same paper. */
function picCrumple(ctx, W, H) {
  ctx.fillStyle = PIC_PAL.paper; ctx.fillRect(0, 0, W, H);
  const rnd = picRng(7), step = Math.round(W / 7);
  for (let gy = -1; gy < H / step + 1; gy++) for (let gx = -1; gx < W / step + 1; gx++) {
    const x = gx * step + (rnd() - 0.5) * step * 0.6, y = gy * step + (rnd() - 0.5) * step * 0.6;
    const p = (dx, dy) => [x + dx * step * (0.7 + rnd() * 0.6), y + dy * step * (0.7 + rnd() * 0.6)];
    const a = p(0, 0), b = p(1, 0.2), c = p(0.3, 1);
    ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.lineTo(c[0], c[1]); ctx.closePath();
    const light = rnd() > 0.5;
    ctx.fillStyle = light ? "rgba(255,255,255," + (0.18 + rnd() * 0.22) + ")" : "rgba(120,124,128," + (0.04 + rnd() * 0.07) + ")";
    ctx.fill();
  }
  ctx.lineCap = "round";
  for (let i = 0; i < 9; i++) {
    const x1 = rnd() * W, y1 = rnd() * H, a = rnd() * Math.PI, len = (0.3 + rnd() * 0.5) * W;
    ctx.strokeStyle = "rgba(90,94,98," + (0.07 + rnd() * 0.07) + ")"; ctx.lineWidth = 2 + rnd() * 2;
    ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x1 + Math.cos(a) * len, y1 + Math.sin(a) * len); ctx.stroke();
    ctx.strokeStyle = "rgba(255,255,255,.5)"; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(x1 + 3, y1 + 3); ctx.lineTo(x1 + 3 + Math.cos(a) * len, y1 + 3 + Math.sin(a) * len); ctx.stroke();
  }
}
/* A picture cropped to a rounded box. zoom > 1 and fx/fy (0..1) choose a different part of the same picture, so "before" is not
   a copy of "after". */
function picInBox(ctx, im, x, y, w, h, r, zoom, fx, fy) {
  ctx.save(); gRound(ctx, x, y, w, h, r); ctx.clip();
  const z = zoom || 1, s = Math.max(w / im.width, h / im.height) * z, dw = im.width * s, dh = im.height * s;
  const ox = Math.min(0, Math.max(w - dw, (w - dw) * (fx == null ? 0.5 : fx))), oy = Math.min(0, Math.max(h - dh, (h - dh) * (fy == null ? 0.5 : fy)));
  ctx.drawImage(im, x + ox, y + oy, dw, dh); ctx.restore();
}
/* A hand-drawn arrow: a marker line that wobbles a little, drawn twice, with an open head. Pointing along (x1,y1) -> (x2,y2). */
function picArrow(ctx, x1, y1, x2, y2, colour, lw, bend) {
  ctx.save(); ctx.strokeStyle = colour; ctx.lineCap = "round"; ctx.lineJoin = "round";
  const mx = (x1 + x2) / 2, my = (y1 + y2) / 2, dx = x2 - x1, dy = y2 - y1, len = Math.hypot(dx, dy) || 1;
  const nx = -dy / len, ny = dx / len, b = (bend == null ? 0.12 : bend) * len;
  for (let k = 0; k < 2; k++) {
    ctx.lineWidth = lw * (k ? 0.6 : 1); const o = k ? lw * 0.7 : 0;
    ctx.beginPath(); ctx.moveTo(x1 + nx * o, y1 + ny * o);
    ctx.quadraticCurveTo(mx + nx * (b + o), my + ny * (b + o), x2 + nx * o, y2 + ny * o); ctx.stroke();
  }
  const ang = Math.atan2(y2 - (my + ny * b), x2 - (mx + nx * b)), hl = lw * 4.2;
  ctx.lineWidth = lw; ctx.beginPath();
  ctx.moveTo(x2 - Math.cos(ang - 0.5) * hl, y2 - Math.sin(ang - 0.5) * hl); ctx.lineTo(x2, y2);
  ctx.lineTo(x2 - Math.cos(ang + 0.5) * hl, y2 - Math.sin(ang + 0.5) * hl); ctx.stroke();
  ctx.restore();
}
/* A white print with a wider foot, tipped by `rot`, picture inside. */
function picPolaroid(ctx, im, x, y, w, rot, zoom, fx, fy) {
  const pad = Math.round(w * 0.05), foot = Math.round(w * 0.16), h = w + foot - pad;
  ctx.save(); ctx.translate(x + w / 2, y + h / 2); ctx.rotate(rot); ctx.translate(-w / 2, -h / 2);
  ctx.shadowColor = "rgba(20,16,12,.28)"; ctx.shadowBlur = Math.round(w * 0.06); ctx.shadowOffsetY = Math.round(w * 0.025);
  ctx.fillStyle = "#FFFFFF"; ctx.fillRect(0, 0, w, h); ctx.shadowColor = "transparent";
  if (im) picInBox(ctx, im, pad, pad, w - pad * 2, w - pad * 2, 0, zoom, fx, fy);
  else { ctx.fillStyle = "#E4DED3"; ctx.fillRect(pad, pad, w - pad * 2, w - pad * 2); }
  ctx.restore();
  return h;
}
/* A strip of translucent tape across a corner. */
function picTape(ctx, cx, cy, w, h, rot) {
  ctx.save(); ctx.translate(cx, cy); ctx.rotate(rot);
  ctx.fillStyle = "rgba(246,231,126,.72)"; ctx.fillRect(-w / 2, -h / 2, w, h);
  ctx.strokeStyle = "rgba(120,100,20,.18)"; ctx.lineWidth = 1.5; ctx.strokeRect(-w / 2, -h / 2, w, h);
  ctx.restore();
}
/* A phone outline with the picture as its screen. */
function picPhone(ctx, im, x, y, w, h) {
  const r = Math.round(w * 0.14), b = Math.max(6, Math.round(w * 0.028));
  ctx.save();
  ctx.shadowColor = "rgba(20,16,12,.25)"; ctx.shadowBlur = Math.round(w * 0.07); ctx.shadowOffsetY = Math.round(w * 0.03);
  ctx.fillStyle = "#FFFFFF"; gRound(ctx, x, y, w, h, r); ctx.fill(); ctx.shadowColor = "transparent";
  if (im) picInBox(ctx, im, x + b, y + b, w - b * 2, h - b * 2, r - b, 1, 0.5, 0.35);
  else { ctx.fillStyle = "#ECE7DD"; gRound(ctx, x + b, y + b, w - b * 2, h - b * 2, r - b); ctx.fill(); }
  ctx.strokeStyle = "#15110E"; ctx.lineWidth = b; gRound(ctx, x + b / 2, y + b / 2, w - b, h - b, r - b / 2); ctx.stroke();
  ctx.fillStyle = "#15110E"; gRound(ctx, x + w * 0.36, y + b * 1.8, w * 0.28, b * 2.4, b * 1.2); ctx.fill();
  ctx.restore();
}
function picBolt(ctx, x, y, s, colour) {
  ctx.save(); ctx.fillStyle = colour; ctx.beginPath();
  ctx.moveTo(x + s * 0.62, y); ctx.lineTo(x + s * 0.12, y + s * 0.58); ctx.lineTo(x + s * 0.44, y + s * 0.58);
  ctx.lineTo(x + s * 0.3, y + s); ctx.lineTo(x + s * 0.9, y + s * 0.38); ctx.lineTo(x + s * 0.56, y + s * 0.38); ctx.closePath(); ctx.fill(); ctx.restore();
}
/* The largest size, down from px0 in steps of 4 and never below pxMin, at which `text` wraps to a block no taller than maxH. */
function picFit(ctx, text, maxW, maxH, px0, pxMin, lhK, weight, family) {
  let px = px0, lines = [];
  for (; ; px -= 4) {
    ctx.font = weight + " " + px + "px " + family; lines = gWrap(ctx, text, maxW);
    if (lines.length * Math.round(px * lhK) <= maxH || px <= pxMin) break;
  }
  return { px, lh: Math.round(px * lhK), lines, h: lines.length * Math.round(px * lhK) };
}
function picCentered(ctx, lines, cx, y, lh) { ctx.textAlign = "center"; ctx.textBaseline = "top"; for (const l of lines) { ctx.fillText(l, cx, y); y += lh; } ctx.textAlign = "left"; return y; }

async function renderPicCard(spec) {
  const [W, H] = sizeOf(spec);
  const c = document.createElement("canvas"); c.width = W; c.height = H;
  const ctx = styleCtx(c.getContext("2d"), spec);
  try { await document.fonts.ready; } catch (e) { }
  return picCardPaint(ctx, spec, W, H, c);
}
async function picCardPaint(ctx, spec, W, H, canvasOut) {
  const warn = [];
  const t = spec.template, u = W / 1080, M = Math.round(74 * u), maxW = W - M * 2, TS = textScale(spec);
  const im = spec.bg ? await loadImg(spec.bg) : null;
  const foot = Math.round((spec.footnote || spec.chip_label ? 96 : 46) * u), floor = H - M - foot;
  const title = stripEmph(spec.title || ""), lead = String(spec.lead || "").trim();
  // "Label | detail" is the writer's way of pairing two things; this family has no table, so the pair is drawn as "Label: detail"
  const items = (spec.items || []).map((x) => stripEmph(x).trim().replace(/\s*\|\s*/g, ": ")).filter(Boolean);
  let y = 0;
  ctx.textBaseline = "top";
  if (t === "i_title") {
    ctx.fillStyle = PIC_PAL.cream; ctx.fillRect(0, 0, W, H);
    await drawBrandMark(ctx, spec, W, u, M, { top: 56, h: 34, textFill: "rgba(21,17,14,.6)" });
    let top = Math.round(150 * u);
    if (im) { const ph = Math.round(H * 0.3); picInBox(ctx, im, M, top, maxW, ph, Math.round(40 * u), 1, 0.5, 0.45); top += ph + Math.round(56 * u); }
    const arrowRoom = spec.footnote ? 0 : Math.round(130 * u);
    const label = String(spec.eyebrow || "").toUpperCase(), labelH = label ? Math.round(56 * u) : 0;
    const head = picFit(ctx, title, maxW * 0.92, (floor - arrowRoom - top - labelH) * 0.62, Math.round(104 * u * TS), Math.round(56 * u), 1.08, 700, PIC_SERIF);
    const leadPx = Math.round(38 * u * TS); ctx.font = "500 " + leadPx + "px " + G_BODY;
    const leadText = [lead, ...items].filter(Boolean).join("\n");
    // The body shares the same room as the headline and must never run past the card's floor: it is fitted and clipped
    // with an ellipsis the way the headline is, so a long point reads "…" instead of silently running off the bottom.
    const bodyRoom = Math.max(Math.round(60 * u), floor - arrowRoom - top - labelH - head.h - Math.round(34 * u));
    const body = leadText ? picFit(ctx, leadText, maxW * 0.8, bodyRoom, leadPx, Math.round(26 * u), 1.32, 500, G_BODY) : null;
    const block = labelH + head.h + (body ? Math.round(34 * u) + body.h : 0);
    y = im ? top : top + Math.max(0, Math.round((floor - arrowRoom - top - block) / 2));
    if (label) {
      ctx.save(); ctx.font = "700 " + Math.round(23 * u) + "px " + G_HEAD; try { ctx.letterSpacing = Math.round(4 * u) + "px"; } catch (e) { }
      ctx.fillStyle = PIC_PAL.blue; ctx.textAlign = "center"; ctx.fillText(label, W / 2, y); ctx.restore(); y += labelH;
    }
    ctx.font = "700 " + head.px + "px " + PIC_SERIF; ctx.fillStyle = PIC_PAL.ink; y = picCentered(ctx, head.lines, W / 2, y, head.lh);
    if (body) { y += Math.round(34 * u); ctx.font = "500 " + body.px + "px " + G_BODY; ctx.fillStyle = PIC_PAL.ink; y = picCentered(ctx, body.lines, W / 2, y, body.lh); }
    if (arrowRoom) picArrow(ctx, W / 2 - Math.round(120 * u), floor - Math.round(30 * u), W / 2 + Math.round(120 * u), floor - Math.round(44 * u), PIC_PAL.blue, Math.round(7 * u), -0.06);
  } else if (t === "i_note") {
    picCrumple(ctx, W, H);
    await drawBrandMark(ctx, spec, W, u, M, { top: 64, h: 40, textFill: "rgba(46,75,71,.8)" });
    const paras = [title, lead, ...items].filter(Boolean).map((p) => p.toUpperCase());
    /* THE WORDS COME FIRST, the print takes what they leave. The words are fitted beside a print of PIC_NOTE_PRINTS[0] of the
       width; if that would push the type under a comfortable reading size (PIC_NOTE_READ) they are fitted beside a smaller
       print, and then with no print at all. The print is then as large as the leftover room allows, up to PIC_NOTE_PHOTO, and
       the two are centred together between the mark and the source line. A print is never drawn over a line. */
    const bottom = Math.min(floor, H - Math.round(150 * u)), photoGap = Math.round(40 * u), top = Math.round(210 * u);
    /* The type is the largest that fits the room (16 Nov 2026: a note with two short lines sat small at the top of a bare card).
       It starts well above the old 44 and comes down until every paragraph fits; a chosen text size starts where it always did. */
    const px00 = Math.round((spec.type_size ? 44 : PIC_NOTE_MAX) * u * TS);
    const longest = (size) => { ctx.font = "500 " + size + "px " + G_MONO; try { ctx.letterSpacing = Math.round(size * 0.06) + "px"; } catch (e) { }
      return Math.max(0, ...paras.join(" ").split(/\s+/).map((x) => ctx.measureText(x).width)); };
    let pxTop = px00;
    while (pxTop > Math.round(44 * u) && longest(pxTop) > maxW) pxTop -= 2;          // never so large that a word is cut in two
    let px = pxTop, lines = [], lh = 0, gap = 0, noteH = 0, photoW = 0, photoH = 0;
    const fitWords = (roomH) => {
      for (px = pxTop; ; px -= 2) {
        ctx.font = "500 " + px + "px " + G_MONO; try { ctx.letterSpacing = Math.round(px * 0.06) + "px"; } catch (e) { }
        lh = Math.round(px * 1.5); gap = Math.round(px * 0.9); lines = paras.map((p) => gWrap(ctx, p, maxW));
        noteH = lines.reduce((a, l) => a + l.length * lh, 0) + gap * Math.max(0, lines.length - 1);
        if (noteH <= roomH || px <= Math.round(28 * u)) return;
      }
    };
    for (const share of (im ? PIC_NOTE_PRINTS : []).concat(0)) {
      photoW = Math.round(W * share); photoH = photoW ? photoW + Math.round(photoW * 0.12) : 0;
      fitWords(bottom - top - (photoW ? photoH + photoGap : 0));
      if (px >= Math.min(pxTop, Math.round(PIC_NOTE_READ * u)) && noteH <= bottom - top - (photoW ? photoH + photoGap : 0)) break;
    }
    y = top + noteH;
    const printRoom = (bottom - top - noteH - photoGap) / 1.12, showPrint = !!im && photoW > 0 && printRoom >= photoW;
    if (showPrint) { photoW = Math.round(Math.min(W * PIC_NOTE_PHOTO, printRoom)); photoH = photoW + Math.round(photoW * 0.12); }
    const noteShift = Math.max(0, Math.round((bottom - top - noteH - (showPrint ? photoGap + photoH : 0)) / 2));
    y += noteShift;
    ctx.fillStyle = PIC_PAL.mono; let yy = top + noteShift;
    for (const block of lines) { for (const l of block) { ctx.fillText(l, M, yy); yy += lh; } yy += gap; }
    try { ctx.letterSpacing = "0px"; } catch (e) { }
    if (showPrint) {
      const px0 = W - M - photoW - Math.round(10 * u), py0 = Math.min(bottom - photoH, y + photoGap);
      picPolaroid(ctx, im, px0, py0, photoW, 0.045, 1, 0.5, 0.5);
      picTape(ctx, px0 + photoW * 0.5, py0 + Math.round(8 * u), Math.round(photoW * 0.34), Math.round(30 * u), -0.05);
      y = Math.max(y, Math.min(py0 + photoH, H - Math.round(150 * u)));
    }
  } else if (t === "i_hero") {
    const g = ctx.createLinearGradient(0, 0, 0, H); g.addColorStop(0, "#FFFFFF"); g.addColorStop(0.55, "#FCF6EE"); g.addColorStop(1, "#FBE8D2");
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
    ctx.save(); ctx.strokeStyle = PIC_PAL.orange; ctx.lineWidth = Math.round(86 * u);
    ctx.beginPath(); ctx.arc(W * 0.62, H + Math.round(40 * u), Math.round(330 * u), Math.PI, Math.PI * 2); ctx.stroke(); ctx.restore();
    // the picture, tipped, bleeding off the left edge
    const pw = Math.round(W * 0.5), ph = Math.round(H * 0.6), px0 = -Math.round(W * 0.07), py0 = Math.round(H * 0.22);
    ctx.save(); ctx.translate(px0 + pw / 2, py0 + ph / 2); ctx.rotate(-0.1); ctx.translate(-pw / 2, -ph / 2);
    ctx.shadowColor = "rgba(40,20,0,.3)"; ctx.shadowBlur = Math.round(40 * u); ctx.shadowOffsetY = Math.round(16 * u);
    if (im) { ctx.fillStyle = "#fff"; gRound(ctx, 0, 0, pw, ph, Math.round(46 * u)); ctx.fill(); ctx.shadowColor = "transparent"; picInBox(ctx, im, 0, 0, pw, ph, Math.round(46 * u), 1, 0.5, 0.5); }
    else { ctx.fillStyle = "rgba(242,138,36,.18)"; gRound(ctx, 0, 0, pw, ph, Math.round(46 * u)); ctx.fill(); }
    ctx.restore();
    await drawBrandMark(ctx, spec, W, u, M, { top: 58, h: 36, textFill: "rgba(21,17,14,.6)" });
    if (spec.eyebrow && spec.stream === "linkedin") { ctx.font = "700 " + Math.round(24 * u) + "px " + G_MONO; ctx.fillStyle = PIC_PAL.muted; ctx.fillText(String(spec.eyebrow), M, Math.round(58 * u)); }
    if (spec.note) { ctx.font = "500 " + Math.round(24 * u) + "px " + G_MONO; ctx.fillStyle = PIC_PAL.muted; ctx.textAlign = "right"; ctx.fillText(String(spec.note).split("\n")[0], W - M, Math.round(58 * u)); ctx.textAlign = "left"; }
    const x0 = Math.round(W * 0.51), colW = W - M - x0;
    const accentTitle = /\*[^*]+\*/.test(spec.title || "") ? String(spec.title) : String(spec.title || "").replace(/^(\S+(?:\s+\S+)?)/, "*$1*");
    let hpx = Math.round(112 * u * TS), lines;
    for (; ; hpx -= 4) {
      ctx.font = "800 " + hpx + "px " + G_HEAD; lines = gWrap(ctx, stripEmph(accentTitle), colW);
      const widest = Math.max(0, ...stripEmph(accentTitle).split(/\s+/).map((w) => ctx.measureText(w).width));      // never break a word in two
      if ((widest <= colW && lines.length * Math.round(hpx * 1.0) <= Math.round(H * 0.4)) || hpx <= Math.round(40 * u)) break;
    }
    y = Math.round(160 * u);
    y = gHeadline(ctx, accentTitle, x0, y, colW, hpx, Math.round(hpx * 1.02), PIC_PAL.ink, PIC_PAL.orange);
    const stat = items.length && items[0].length <= 14 && /\d/.test(items[0]) ? items[0] : "";
    const heroText = [lead, ...(stat ? items.slice(1) : items)].filter(Boolean).join("\n");
    if (heroText) { y += Math.round(28 * u); y = gPara(ctx, heroText, x0, y, colW, Math.round(34 * u * TS), Math.round(46 * u * TS), PIC_PAL.ink, 500); }
    if (stat) {
      const spx = Math.round(40 * u); ctx.font = "800 " + spx + "px " + G_HEAD;
      const pw2 = Math.min(colW, Math.round(ctx.measureText(stat).width + 150 * u)), ph2 = Math.round(88 * u), py2 = Math.max(y + Math.round(44 * u), Math.round(H * 0.7));
      ctx.save(); ctx.shadowColor = "rgba(150,70,0,.25)"; ctx.shadowBlur = Math.round(18 * u); ctx.shadowOffsetY = Math.round(8 * u);
      ctx.fillStyle = PIC_PAL.orange; gRound(ctx, x0, py2, pw2, ph2, Math.round(20 * u)); ctx.fill(); ctx.restore();
      ctx.fillStyle = "#FFFFFF"; ctx.font = "800 " + spx + "px " + G_HEAD; ctx.fillText(stat, x0 + Math.round(26 * u), py2 + Math.round((ph2 - spx) / 2) - Math.round(spx * 0.06));
      picBolt(ctx, x0 + pw2 - Math.round(96 * u), py2 - Math.round(20 * u), Math.round(110 * u), "#2A1606");
      y = Math.max(y, py2 + ph2);
    }
  } else { // i_step
    gPaper(ctx, W, H, false);
    const label = String(spec.eyebrow || "").trim() || (spec.stream === "linkedin" ? "step" : "langkah");
    const phW = Math.round(W * 0.46), labelMax = W - M - phW - M;           // the label stays left of the phone
    let lpx = Math.round(130 * u); ctx.font = "700 italic " + lpx + "px " + G_MARK;
    while (ctx.measureText(label).width > labelMax && lpx > Math.round(60 * u)) { lpx -= 4; ctx.font = "700 italic " + lpx + "px " + G_MARK; }
    ctx.fillStyle = PIC_PAL.ink; ctx.fillText(label, M, Math.round(96 * u));
    const colW = Math.round(W * 0.4), ty = Math.round(250 * u);
    const head = picFit(ctx, title, colW, Math.round(H * 0.3), Math.round(44 * u * TS), Math.round(28 * u), 1.28, 700, G_BODY);
    ctx.font = "700 " + head.px + "px " + G_BODY; ctx.fillStyle = PIC_PAL.ink; ctx.textAlign = "left";
    y = ty; for (const l of head.lines) { ctx.fillText(l, M, y); y += head.lh; }
    const stepText = [lead, ...items].filter(Boolean).join("\n");
    if (stepText) { y += Math.round(16 * u); y = gPara(ctx, stepText, M, y, colW, Math.round(28 * u * TS), Math.round(38 * u * TS), PIC_PAL.muted, 500); }
    const phw = Math.round(W * 0.46), phh = Math.round(H * 0.66), phx = W - M - phw + Math.round(20 * u), phy = Math.round(H * 0.05);
    picPhone(ctx, im, phx, phy, phw, phh);
    const after = spec.stream === "linkedin" ? "after" : "selepas", before = spec.stream === "linkedin" ? "before" : "sebelum";
    const lx = M + Math.round(colW * 0.35), ly = Math.max(y + Math.round(40 * u), Math.round(H * 0.4));
    ctx.font = "700 italic " + Math.round(58 * u) + "px " + G_MARK; ctx.fillStyle = PIC_PAL.ink; ctx.fillText(after, lx, ly);
    picArrow(ctx, lx + Math.round(150 * u), ly + Math.round(30 * u), phx - Math.round(10 * u), ly + Math.round(80 * u), PIC_PAL.ink, Math.round(4 * u), 0.2);
    const polW = Math.round(W * 0.3), polY = Math.min(floor - Math.round(polW * 1.25), Math.round(H * 0.56));
    const polH = picPolaroid(ctx, im, M, polY, polW, -0.05, 1.8, 0.2, 0.4);
    ctx.font = "700 italic " + Math.round(54 * u) + "px " + G_MARK; ctx.fillStyle = PIC_PAL.ink; ctx.fillText(before, M + Math.round(polW * 0.3), polY + polH + Math.round(14 * u));
    y = Math.max(y, polY + polH + Math.round(70 * u));
  }
  gSourceLine(ctx, W, H, M, u, spec.chip_label || (spec.footnote ? "Sumber" : ""), spec.footnote || "", false);
  if (y > H - Math.round(150 * u)) warn.push("The slide is fuller than the card: shorten a line.");
  return canvasOut ? { url: canvasOut.toDataURL("image/jpeg", 0.9), warn, y } : { warn, y };
}

/* ===================== the hand-drawn family =================================
   Wan, 13 Nov 2026: the Excalidraw look he approved for posters — grey-blue board, a white card with wobbly
   hand-drawn borders, Permanent Marker headings with a yellow highlighter phrase, Open Sans body, a
   "HEAD TO HEAD" ✓/✗ table and a green RECOMMENDED box. It draws with canvas (no ctx.filter — iPhone Safari
   before 18 has none), reusing the fonts.css faces (Permanent Marker + Open Sans added for this family).
   Three templates:
     h_poster  the one-card 4:5 poster: hook headline (marker, highlighted key phrase), a wobbly card of points,
               a "HEAD TO HEAD" two-column ✓/✗ table when the points are "Label | detail" pairs, and a green
               takeaway box. Every point is drawn; a point longer than the column wraps and the type shrinks.
     h_hero    the cover of a carousel: the same board and marker headline, one big point.
     h_note    a middle slide: the board, a marker title and the points as numbered lines.
   A slide with no picture is still complete (this family does not use spec.bg). */
const HAND_PAL = { board: "#dbe4eb", card: "#ffffff", ink: "#111111", muted: "#4a4a4a", hl: "#f1c40f", hlEdge: "#e0b50c",
  navy: "#2c3e50", blue: "#2980b9", green: "#27ae60", orange: "#d35400", purple: "#8e44ad", red: "#c0392b", line: "#bdc3c7" };
const HAND_HEAD = '"Permanent Marker", "Caveat", cursive';
const HAND_BODY = '"Open Sans", "Instrument Sans", sans-serif';

/* A hand-drawn wobbly rounded rectangle: two passes, the second offset, so the border reads as marker ink. */
function handCard(ctx, x, y, w, h, colour, lw) {
  const r = Math.round(0.06 * Math.min(w, h));
  ctx.save(); ctx.lineCap = "round"; ctx.lineJoin = "round";
  for (let k = 0; k < 2; k++) {
    ctx.strokeStyle = k ? "rgba(255,255,255,.5)" : colour; ctx.lineWidth = k ? Math.max(1, lw - 1) : lw;
    ctx.beginPath();
    const rx = r + (k ? 1.5 : 0), ry = r - (k ? 1.5 : 0);
    ctx.moveTo(x + rx, y); ctx.lineTo(x + w - rx, y + Math.round(2 * Math.random() - 1));
    ctx.quadraticCurveTo(x + w, y, x + w, y + ry);
    ctx.lineTo(x + w, y + h - ry); ctx.quadraticCurveTo(x + w, y + h, x + w - rx, y + h);
    ctx.lineTo(x + rx, y + h); ctx.quadraticCurveTo(x, y + h, x, y + h - ry);
    ctx.lineTo(x, y + ry); ctx.quadraticCurveTo(x, y, x + rx, y); ctx.stroke();
  }
  ctx.restore();
}
/* A yellow highlighter stroke behind text: two soft overlapping rects, slightly rotated, overshooting the edges. */
function handHl(ctx, x, y, w, h) {
  ctx.save(); ctx.fillStyle = HAND_PAL.hl; ctx.globalAlpha = 0.95;
  ctx.beginPath(); ctx.rect(x - 3, y - 1, w + 6, h + 2); ctx.fill();
  ctx.restore();
}
/* The title with one key phrase highlighted. *word* is emphasis here as elsewhere; the last emphasised
   phrase (or the first two words when none is marked) gets the marker block. */
function handTitle(ctx, title, x, y, maxW, px, centre) {
  const t = stripEmph(title || "").trim();
  if (!t) return y;
  ctx.font = "400 " + px + "px " + HAND_HEAD; ctx.textBaseline = "top";
  const words = t.split(/\s+/).filter(Boolean);
  // find the phrase the writer marked with *asterisks*, else highlight the first two words
  let hlSpan = [0, 0];
  const m = /^\*([^*]+)\*/.exec(title || "") || /\s\*([^*]+)\*/.exec(title || "");
  if (m) { const phrase = m[1]; const idx = t.indexOf(phrase); if (idx >= 0) { let before = t.slice(0, idx).trim(); hlSpan = [before ? before.split(/\s+/).length : 0, phrase.split(/\s+/).length]; } }
  else hlSpan = [0, Math.min(2, words.length)];
  let lines = [], line = "";
  for (const w of words) { const next = line ? line + " " + w : w; if (line && ctx.measureText(next).width > maxW) { lines.push(line); line = w; } else line = next; }
  if (line) lines.push(line);
  let yy = y;
  for (const ln of lines) {
    const lw = ln.split(/\s+/), lc = lines.indexOf(ln), start = lines.slice(0, lc).reduce((a, s) => a + s.split(/\s+/).length, 0);
    const ox = centre ? Math.max(0, Math.round((maxW - ctx.measureText(ln).width) / 2)) : 0;      // Wan, 13 Nov 2026: centred
    // highlight the words of this line that fall in the span
    for (let i = 0; i < lw.length; i++) {
      const gi = start + i;
      if (gi >= hlSpan[0] && gi < hlSpan[0] + hlSpan[1]) {
        const before = lw.slice(0, i).join(" ") + (i ? " " : "");
        const tw = ctx.measureText(lw[i]).width;
        handHl(ctx, x + ox + ctx.measureText(before).width, yy - 2, tw, px * 1.15);
      }
    }
    ctx.fillStyle = HAND_PAL.ink; ctx.fillText(ln, x + ox, yy); yy += Math.round(px * 1.2);
  }
  ctx.textBaseline = "alphabetic"; return yy;
}
/* Body text: Open Sans, wraps to the width, shrinks a step until it fits maxH, never cut. */
function handBody(ctx, text, x, y, maxW, maxH, px0, pxMin, weight, colour, lh, centre) {
  const t = String(text || "").trim(); if (!t) return y;
  let px = px0, lines = [];
  for (; ; px -= 2) {
    ctx.font = weight + " " + px + "px " + HAND_BODY; lines = gWrap(ctx, t, maxW);
    if (lines.length * Math.round(px * lh) <= maxH || px <= pxMin) break;
  }
  const lhpx = Math.round(px * lh); ctx.fillStyle = colour; ctx.textBaseline = "top";
  if (centre) ctx.textAlign = "center";
  for (const l of lines) { ctx.fillText(l, centre ? x + maxW / 2 : x, y); y += lhpx; }
  ctx.textAlign = "left"; ctx.textBaseline = "alphabetic"; return y;
}
/* A "HEAD TO HEAD" table from "Label | detail" point pairs: label column bold, ✓ green / ✗ red on the "Wajib ke?" row. */
function handTable(ctx, title, items, x, y, maxW, maxH, u, f = 1) {
  const t = stripEmph(title || "").trim();
  const rows = (items || []).map((s) => String(s || "").trim()).filter(Boolean);
  const pairs = rows.filter((s) => s.includes("|")).map((s) => { const [a, b] = s.split("|"); return [a.trim(), b.trim()]; });
  if (pairs.length < 2 || !pairs.some(([, b]) => skMarkOf(b))) return y;      // not a yes/no table: the caller draws heading + detail
  ctx.save();
  ctx.font = "400 " + Math.round(30 * u * f) + "px " + HAND_HEAD; ctx.fillStyle = HAND_PAL.ink; ctx.textBaseline = "top";
  ctx.textAlign = "center"; ctx.fillText(t, x + maxW / 2, y); ctx.textAlign = "left"; y += Math.round(44 * u * f);
  const labs = pairs.map(([a]) => (a[0] === "*" ? stripEmph(a) : a));
  // a tick or a cross only where the cell IS a yes or a no (16 Nov 2026: "NPRA tidak menilai keselamatan" was getting a cross)
  const dets = pairs.map(([, b]) => { const m = skMarkOf(b); return (m === "yes" ? "\u2713 " : m === "no" ? "\u2717 " : "") + b; });
  // the type is as large as the rows allow AND still fits the card: the widest label and the widest detail side by side
  const gapX = Math.round(28 * u);
  let px = Math.round(24 * u * f);
  const widest = (font, list) => { ctx.font = font; return Math.max(...list.map((l) => ctx.measureText(l).width)); };
  for (; px > Math.round(16 * u); px -= 2) {
    const lw = widest("700 " + px + "px " + HAND_BODY, labs), dw = widest("700 " + px + "px " + HAND_BODY, dets);
    if (lw + gapX + dw <= maxW) break;
  }
  const lw = widest("700 " + px + "px " + HAND_BODY, labs), dw = widest("700 " + px + "px " + HAND_BODY, dets);
  const tableW = Math.min(maxW, lw + gapX + dw), x0 = x + Math.round((maxW - tableW) / 2);   // the table block is centred
  const rowH = Math.round(Math.max(px * 1.8, 44 * u * f));
  pairs.forEach(([a, b], k) => {
    const isWajib = /wajib/i.test(a);
    ctx.font = "700 " + px + "px " + HAND_BODY;
    ctx.fillStyle = HAND_PAL.navy; ctx.fillText(labs[k], x0, y + 4);
    ctx.fillStyle = isWajib ? HAND_PAL.green : HAND_PAL.ink;
    ctx.fillText(dets[k], x0 + lw + gapX, y + 4);
    y += rowH;
  });
  ctx.restore(); return y;
}
/* The hand-drawn card is painted twice, as the grid cards are: once against measureProxy to learn how tall the words
   are, then for real. Wan, 13 Nov 2026: "make sure all text in the poster align centre / fill the space in the poster" --
   the words were left-aligned at the top and the lower half of the card stayed empty. Now every line is centred, the
   type grows (up to HAND_FILL_MAX, by the same search the grid cards use) until the words fill the card, and the
   block is centred between the eyebrow and the source line. Never past the room: a card already full keeps its size. */
const HAND_FILL_MAX = 2.6;
function handZone(H, u) { return { top: Math.round(112 * u), bottom: H - Math.round(180 * u) }; }
function handPaint(ctx, spec, W, H, fill, shift) {
  const warn = [];
  const u = W / 1080, M = Math.round(56 * u), pad = Math.round(44 * u);
  const title = String(spec.title || "").trim();
  const items = (spec.items || []).map((x) => String(x || "").trim()).filter(Boolean);
  const lead = String(spec.lead || "").trim();
  const footnote = String(spec.footnote || "").trim();
  const linkedin = spec.stream === "linkedin";
  const f = fill > 1 ? fill : 1;
  ctx.fillStyle = HAND_PAL.board; ctx.fillRect(0, 0, W, H);
  const cardX = M, cardY = Math.round(30 * u), cardW = W - M * 2, cardH = H - Math.round(60 * u);
  ctx.fillStyle = HAND_PAL.card; ctx.fillRect(cardX, cardY, cardW, cardH);
  handCard(ctx, cardX, cardY, cardW, cardH, HAND_PAL.navy, Math.round(5 * u));
  const innerW = cardW - pad * 2;
  const z = handZone(H, u);
  if (spec.eyebrow) {
    ctx.font = "700 " + Math.round(19 * u) + "px " + HAND_BODY; ctx.fillStyle = HAND_PAL.muted; ctx.textBaseline = "top";
    ctx.textAlign = "center"; ctx.fillText(String(spec.eyebrow).toUpperCase(), cardX + cardW / 2, cardY + pad); ctx.textAlign = "left";
  }
  let y = z.top + shift;
  ctx.textBaseline = "top";
  // the headline grows with the rest, but never past the size at which its longest word still fits (its wrapper does not cut
  // a word, so "BERTANGGUNGJAWAB" would run off the card); the points keep growing without it
  ctx.font = "400 " + Math.round(48 * u) + "px " + HAND_HEAD;
  const wordW = Math.max(0, ...stripEmph(title).split(/\s+/).filter(Boolean).map((x) => ctx.measureText(x).width));
  const tf = Math.max(1, Math.min(f, wordW > 0 ? (innerW / wordW) * 0.97 : f));
  y = handTitle(ctx, title, cardX + pad, y, innerW, Math.round(48 * u * tf), true);
  y += Math.round(20 * u * f);
  ctx.textBaseline = "alphabetic";
  const piped = items.length >= 2 && items.every((s) => s.includes("|"));
  const bodyRoom = z.bottom - z.top - Math.round(60 * u);        // what the points may take when nothing has grown
  const maxH = f > 1 ? Infinity : bodyRoom;
  const gap = Math.round(14 * u * f);
  if (piped) {
    const was = y;
    y = handTable(ctx, "HEAD TO HEAD", items, cardX + pad, y, innerW, maxH, u, f);
    if (y === was) {
      // "Label | detail" that is not a yes/no table: the label as a bold line, its detail under it, never a bare "|"
      for (const it of items) {
        const [a, ...rest] = it.split("|").map((x) => stripEmph(x).trim());
        y = handBody(ctx, a, cardX + pad, y, innerW, maxH, Math.round(30 * u * f), Math.round(20 * u), 700, HAND_PAL.navy, 1.3, true);
        if (rest.join(" ").trim()) { y += Math.round(4 * u * f); y = handBody(ctx, rest.filter(Boolean).join(", "), cardX + pad, y, innerW, maxH, Math.round(26 * u * f), Math.round(18 * u), 400, HAND_PAL.ink, 1.4, true); }
        y += Math.round(gap * 1.4);
      }
    }
  } else {
    for (const it of [lead, ...items].filter(Boolean)) {
      y = handBody(ctx, it, cardX + pad, y, innerW, maxH, Math.round(27 * u * f), Math.round(18 * u), 400, HAND_PAL.ink, 1.4, true); y += gap;
    }
  }
  if (footnote) {
    ctx.font = "400 " + Math.round(20 * u) + "px " + HAND_BODY; ctx.fillStyle = HAND_PAL.muted; ctx.textBaseline = "top";
    const label = linkedin ? "Source: " : "Sumber: ";
    const fl = gWrap(ctx, label + footnote, innerW);
    const fy = cardY + cardH - pad - fl.length * Math.round(28 * u);
    ctx.textAlign = "center";
    fl.forEach((l, i) => ctx.fillText(l, cardX + cardW / 2, fy + i * Math.round(28 * u)));
    ctx.textAlign = "left";
  }
  if (y > z.bottom + Math.round(30 * u)) warn.push("The slide is fuller than the card: shorten a line.");
  return { warn, y };
}
async function renderHandCard(spec) {
  const [W, H] = sizeOf(spec);
  const c = document.createElement("canvas"); c.width = W; c.height = H;
  const ctx = styleCtx(c.getContext("2d"), spec);
  try { await document.fonts.ready; } catch (e) { }
  const u = W / 1080, z = handZone(H, u);
  const probe = handPaint(measureProxy(ctx), spec, W, H, 1, 0);
  // grow the type until the words fill the card (the grid cards' own search), but only when they leave it mostly empty
  let fill = 1;
  const used = (y) => Math.max(0, y - z.top), room = z.bottom - z.top;
  if (!spec.type_size && room > 0 && used(probe.y) < FILL_FROM * room) {
    const at = (f) => used(handPaint(measureProxy(ctx), spec, W, H, f, 0).y);
    if (at(HAND_FILL_MAX) >= used(probe.y) * 1.12) {
      let lo = 1, hi = HAND_FILL_MAX;
      for (let i = 0; i < 7; i++) { const mid = (lo + hi) / 2; if (at(mid) <= FILL_TARGET * room) lo = mid; else hi = mid; }
      fill = lo > 1.03 ? Math.round(lo * 100) / 100 : 1;
    }
  }
  const end = handPaint(measureProxy(ctx), spec, W, H, fill, 0).y;
  const slack = room - used(end);
  const shift = slack > 0 ? Math.round(slack / 2) : 0;           // centred between the eyebrow and the source line
  const out = handPaint(ctx, spec, W, H, fill, shift);
  if (spec.stream !== "linkedin") await drawBrandMark(ctx, spec, W, u, Math.round(56 * u), { top: 40, h: 28, textFill: "rgba(21,23,27,.5)" });
  return { url: c.toDataURL("image/jpeg", 0.9), warn: out.warn, y: out.y };
}

/* ---- FOUR POSTER LOOKS: MARKER, TORN PAPER, COLOUR BLOCKS, NEON (Wan, 16 Nov 2026: four pictures of one comparison poster,
   "masukkan semua jenis style design sebagai single card, carousel"). The four pictures are ONE layout in four dresses, so this
   is one layout engine with four skins, not four painters that would drift apart:
     marker  cream paper, Permanent Marker headline, red rings and ruled rows, a solid red block for the pick;
     torn    beige ground, each point on its own torn strip of pastel paper, a dark green strip for the pick;
     block   cream ground, solid rounded colour blocks with white type, white pills for the ticks, a yellow pick;
     neon    a dark ground, glowing outlined boxes in white, blue, green and orange, a pink pick.
   Each look has the five slides a post needs, so it works as a single card AND as a whole carousel:
     x_cover   the opening slide: the headline at its largest, one supporting line;
     x_points  the points, numbered, each in the look's own container ("Heading | detail" puts the heading in bold);
     x_table   a comparison: one row per point, cells split on "|", a cell that says yes or no drawn as a tick or a cross,
               and a first row with no ticks in it read as the column headings;
     x_pick    the recommendation: the headline and its reason inside the look's highlight block, the points under it;
     x_close   the closing slide: the headline, the points as plain strips, the source line.
   On any of them the slide's `note` is drawn in the highlight block (on x_pick, where the block is already the headline, as a
   line in the accent). A lone card with rows of cells is the table, else the points: the reference poster is title, table,
   highlight block, source, and that is exactly x_table with a note.
   EVERY WORD IS DRAWN. Nothing is sliced: a long list makes the type smaller (down to SKIN_MIN), a short one makes it larger
   (up to SKIN_MAX), by the same two-pass search the hand-drawn cards use; only a slide that does not fit at SKIN_MIN warns.
   The torn edges and the paper grain come from a generator seeded by the slide's own words, so the measuring pass and the
   painting pass draw the same card and a re-render is the same picture.
   THE COVER IS THE FRONT PAGE (Wan, 16 Nov 2026: "create more impressive front page to replace current front page based on
   posters", and "the text for first page no need to big, but hook make bigger"). On x_cover the hook alone grows to fill the
   card and the line under it stays at reading size. When the slide has a picture it is framed at the top in the look's own
   way (a block, a taped print, a glowing frame) and the hook fills what is left; with no picture the hook has the whole card.
   The Image, Info ERA and Hand-drawn looks now open a carousel with one of these covers too (POSTER_COVER in specsFor): their
   own first slide left the hook small in a mostly empty card. Info ERA's keeps ERA's paper, label and red block (SKINS.kraft).
   No other slide uses a picture, there is no mascot, and a LinkedIn card carries no ws.regulab mark, as everywhere. */
const SKIN_OF = { m: "marker", t: "torn", b: "block", n: "neon", d: "deck", k: "chalk", l: "metro", s: "strip" };
const SKIN_PARTS = ["cover", "points", "table", "pick", "close"];
const SKIN_LOOKS = Object.values(SKIN_OF);
const SKIN_TPL = Object.fromEntries(Object.keys(SKIN_OF).flatMap((p) => SKIN_PARTS.map((s) => [p + "_" + s, 1])));
const SK_MARK = '"Permanent Marker", Caveat, cursive';
const SK_HAND = 'Caveat, "Permanent Marker", cursive';
const SK_SANS = 'Poppins, "Instrument Sans", system-ui, sans-serif';
const SK_TEXT = '"Open Sans", "Instrument Sans", sans-serif';
/* headK / bodyK: Caveat is drawn small for its size, so a Caveat line is set this much larger to read as large as the others */
const SKINS = {
  marker: { ground: "#F5EFE2", ink: "#171717", muted: "#4E4A44", accent: "#D7263D", yes: "#171717", no: "#D7263D",
    head: SK_MARK, headW: 400, headK: 1, body: SK_HAND, bodyW: 700, bodyK: 1.24, caps: true,
    fills: null, onFill: "#171717", pick: { fill: "#D7263D", ink: "#FFFFFF" } },
  torn: { ground: "#E9DFCB", ink: "#1E2A24", muted: "#55584F", accent: "#C8553D", yes: "#2E7D4F", no: "#C8553D",
    head: SK_HAND, headW: 700, headK: 1.2, body: SK_HAND, bodyW: 700, bodyK: 1.24, caps: true,
    fills: ["#F7C8C2", "#BFD9EE", "#CBE3C3", "#F6E3A1", "#D9CBEA"], onFill: "#1E2A24", pick: { fill: "#23473A", ink: "#FFFFFF" } },
  block: { ground: "#F4EDE1", ink: "#14213D", muted: "#4B5568", accent: "#F26B21", yes: "#1E9E5A", no: "#D7263D",
    head: SK_SANS, headW: 800, headK: 0.9, body: SK_SANS, bodyW: 600, bodyK: 0.94,
    fills: ["#14213D", "#2F6FDE", "#1E9E5A", "#F26B21"], onFill: "#FFFFFF", pill: "#FFFFFF", pick: { fill: "#FFC93C", ink: "#14213D" } },
  neon: { ground: "#0B0E17", ink: "#F4F7FF", muted: "#A9B4CC", accent: "#FF4FA3", yes: "#4DFFA1", no: "#FF5C7A",
    head: SK_HAND, headW: 700, headK: 1.2, body: SK_SANS, bodyW: 600, bodyK: 0.94, glow: true, dark: true,
    fills: ["#F4F7FF", "#4DB8FF", "#4DFFA1", "#FFA63D"], pick: { fill: "#FF4FA3", ink: "#FFD3E8" } },
  /* FOUR MORE (Wan, 16 Nov 2026, four further posters: "add these poster design also"). The same five slides, four more dresses:
       deck   a white card on a grey-blue board; each point an outlined card in its own colour with a marker heading (two to a
              row when there are four or more), a yellow highlighter on the marked words, a green outlined box for the pick;
       chalk  a green chalkboard in a wooden frame; chalk handwriting, outlined boxes in chalk colours, dashed rules under the
              rows of a comparison, a yellow outlined box for the pick;
       metro  a line map: the points are stations on one line down the left, each with its own coloured block; in a comparison
              every row is a line running through its columns, a big ringed tick where the answer is yes and a small grey
              cross where it is no; a dark green block for the pick (the terminus);
       strip  torn strips again, but a comparison is ONE strip per row: the name, a value at the right, the details, and the
              yes and no answers in a line as "tick, column name". */
  deck: { ground: "#DCE3EB", ink: "#2C3E50", muted: "#66727F", accent: "#2C3E50", hilite: "#F4D03F", yes: "#27AE60", no: "#C0392B",
    head: SK_MARK, headW: 400, headK: 0.96, body: SK_TEXT, bodyW: 400, boldW: 700, bodyK: 0.92, caps: true, itemHead: SK_MARK, headFromBox: true, grid: true,
    fills: ["#2C3E50", "#2E86C1", "#27AE60", "#D35400", "#8E44AD"], onFill: "#2C3E50", rowRule: "line", tableHead: { face: SK_MARK, w: 400, k: 1.05 },
    pick: { fill: "#27AE60", ink: "#2C3E50", head: "#1E8E4E" } },
  chalk: { ground: "#2F4A3D", ink: "#F4F1E6", muted: "#C5D0C2", accent: "#F2DC7A", yes: "#9FE0A6", no: "#F29AA6",
    head: SK_HAND, headW: 700, headK: 1.2, body: SK_HAND, bodyW: 700, bodyK: 1.24, dark: true, headFromBox: true,
    fills: ["#F4F1E6", "#8EC5F0", "#9FE0A6", "#F2B880"], onFill: "#F4F1E6", rowRule: "dash", tableHead: { face: SK_HAND, w: 700, k: 1.4 },
    pick: { fill: "#F2DC7A", ink: "#F4F1E6", head: "#9FE0A6" } },
  metro: { ground: "#FAF8F2", ink: "#1F2A33", muted: "#56616B", accent: "#1F7A3E", yes: "#1F7A3E", no: "#C0392B",
    head: SK_HAND, headW: 700, headK: 1.25, body: SK_HAND, bodyW: 700, bodyK: 1.24, rail: true,
    fills: ["#1F2A33", "#2D62E0", "#1F7A3E", "#C2410C"], onFill: "#FFFFFF", pick: { fill: "#17502F", ink: "#FFFFFF", head: "#FFFFFF" } },
  strip: { ground: "#E4D6BA", ink: "#3A2A22", muted: "#6A5A4A", accent: "#9A4F2A", yes: "#2E7D4F", no: "#C0392B",
    head: SK_HAND, headW: 700, headK: 1.25, body: SK_HAND, bodyW: 700, bodyK: 1.24, inline: true,
    fills: ["#F1E9DB", "#A9C8E8", "#A9D29B", "#EDB58B"], onFill: "#3A2A22", pick: { fill: "#2B5F3F", ink: "#FFFFFF" } },
};
/* Not a look of its own: the dress the poster cover wears as the front page of an Info ERA carousel (Wan, 16 Nov 2026, of the ERA
   hook slide: "make sure no space excess, make it fill the page, can add image if possible"). ERA's own paper, its black
   label, its red, and the supporting line in the red block, so the page still opens the ERA slides that follow it. */
SKINS.kraft = { ground: "#EFE8DC", ink: "#151515", muted: "#5C574E", accent: "#D8232A", yes: "#151515", no: "#D8232A",
  head: SK_SANS, headW: 800, headK: 0.9, body: SK_SANS, bodyW: 700, bodyK: 0.94, fills: null, onFill: "#151515",
  pick: { fill: "#D8232A", ink: "#FFFFFF" }, eraPaper: true, badge: true, leadBlock: true };
/** The skin a spec is drawn in: its own override (the ERA front page), else the look its template belongs to. */
const skinOf = (spec) => (spec.skin && SKINS[spec.skin] ? spec.skin : SKIN_OF[spec.template[0]]);
export const SKIN_MIN = 0.56, SKIN_MAX = 1.7;
/* The first page is the hook (Wan, 16 Nov 2026: "the text for first page no need to big, but hook make bigger"): on a cover the
   headline alone grows, up to SKIN_COVER_MAX, and everything under it stays at reading size (at most SKIN_COVER_REST). */
export const SKIN_COVER_MAX = 2.6, SKIN_COVER_REST = 1.05;
/* A poster is meant to be full: the type grows whenever the words leave more than a seventh of the card empty (the hand-drawn
   cards wait until a quarter is empty, which left these with a wide band above and below a table). */
const SKIN_FROM = 0.86, SKIN_TARGET = 0.94;
const SK_YES = /^(✓|✔|☑|ya|yes|y|ada|true|betul|boleh)$/i;
const SK_NO = /^(✗|✘|✕|x|×|tidak|tak|tiada|no|n|false|salah|-|–|—)$/i;
const skMarkOf = (cell) => (SK_YES.test(String(cell || "").trim()) ? "yes" : SK_NO.test(String(cell || "").trim()) ? "no" : "");
const RE_PICK = /disyor|syor|cadangan|pilihan (kami|terbaik|saya)|terbaik|kesimpulan|recommend|our pick|best (choice|pick|option)|verdict|bottom line|conclusion/i;
/* The poster cover each older look opens a carousel with: the one whose paper and type sit beside that look's own slides. */
const POSTER_COVER = { image: "b_cover", era: "m_cover", hand: "m_cover" };
const SKIN_NAMES = { marker: "Marker", torn: "Torn paper", block: "Blocks", neon: "Neon", deck: "Card board", chalk: "Chalkboard", metro: "Line map", strip: "Torn strips" };
const SKIN_PART_NAMES = { cover: "Cover", points: "Points", table: "Comparison", pick: "Recommendation", close: "Closing" };
const skinPrefix = (look) => Object.keys(SKIN_OF).find((p) => SKIN_OF[p] === look) || "m";
/** The letter a look's templates begin with. It is the look's own first letter for the older families; the poster looks have
    theirs in SKIN_OF, because "chalk" is k_ (c_ is a design made from a reference) and "metro" is l_ (m_ is the marker poster). */
export const lookLetter = (look) => Object.keys(SKIN_OF).find((p) => SKIN_OF[p] === look) || String(look || "")[0] || "";

/* Which of the five slides a slide is, from where it sits and what its points look like. Used with and without `fit`: the look
   has no other way to dress a slide, so a set is always complete. */
export function skinTemplate(look, s, i, n, pts) {
  const p = skinPrefix(look);
  const rows = (pts || []).map(gCells);
  const table = rows.length >= 2 && rows.every((r) => r.length >= 2) && rows.some((r) => r.length >= 3 || skMarkOf(r[1]));
  if (table) return p + "_table";
  if (n > 1 && i === 0) return p + "_cover";
  if (RE_PICK.test(String((s && s.title) || "")) && (rows.length || String((s && s.lead) || "").trim())) return p + "_pick";
  if (n > 1 && i === n - 1) return p + "_close";
  return p + "_points";
}

function skSeed(spec) {
  const s = String(spec.template || "") + "|" + String(spec.title || "") + "|" + (spec.items || []).length;
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
  return h >>> 0;
}
function skHexA(hex, a) {
  const n = parseInt(String(hex).slice(1), 16);
  return "rgba(" + ((n >> 16) & 255) + "," + ((n >> 8) & 255) + "," + (n & 255) + "," + a + ")";
}
/* The ground: flat colour plus what makes each look itself. Decoration stays in the corners and the margins, never under a line
   of text, so nothing here can cost legibility. */
function skGround(ctx, S, look, W, H, u, rnd) {
  if (S.eraPaper) { eraPaper(ctx, W, H); return; }
  ctx.fillStyle = S.ground; ctx.fillRect(0, 0, W, H);
  if (look === "deck") {
    // the board, and the white card the poster is written on
    const m = Math.round(26 * u);
    ctx.save(); ctx.shadowColor = "rgba(30,45,60,.16)"; ctx.shadowBlur = Math.round(20 * u); ctx.shadowOffsetY = Math.round(6 * u);
    ctx.fillStyle = "#FFFFFF"; roundRect(ctx, m, m, W - m * 2, H - m * 2, Math.round(20 * u)); ctx.fill(); ctx.restore();
  }
  if (look === "chalk") {
    // a wooden frame round the board, and chalk dust: faint specks, the same ones on every render of this slide
    const fw = Math.round(20 * u);
    ctx.save(); ctx.fillStyle = "#9A6B45"; ctx.fillRect(0, 0, W, H);
    ctx.fillStyle = "#7E5536"; ctx.fillRect(fw - Math.round(4 * u), fw - Math.round(4 * u), W - (fw - Math.round(4 * u)) * 2, H - (fw - Math.round(4 * u)) * 2);
    ctx.fillStyle = S.ground; ctx.fillRect(fw, fw, W - fw * 2, H - fw * 2);
    const g = ctx.createRadialGradient(W / 2, H / 2, H * 0.2, W / 2, H / 2, H * 0.8);
    g.addColorStop(0, "rgba(255,255,255,.05)"); g.addColorStop(1, "rgba(0,0,0,.16)");
    ctx.fillStyle = g; ctx.fillRect(fw, fw, W - fw * 2, H - fw * 2);
    ctx.fillStyle = "rgba(255,255,255,.045)";
    for (let i = 0; i < 420; i++) { const x = fw + rnd() * (W - fw * 2), y = fw + rnd() * (H - fw * 2), r = (0.6 + rnd() * 1.8) * u; ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill(); }
    ctx.restore();
  }
  if (look === "marker" || look === "torn" || look === "strip" || look === "metro") {
    // paper grain: faint specks, the same ones on every render of this slide
    ctx.save(); ctx.fillStyle = look === "torn" || look === "strip" ? "rgba(90,70,40,.07)" : "rgba(60,50,30,.05)";
    for (let i = 0; i < 520; i++) { const x = rnd() * W, y = rnd() * H, r = (0.6 + rnd() * 1.6) * u; ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill(); }
    ctx.restore();
  }
  if (look === "block") {
    ctx.save();
    ctx.fillStyle = "#FFC93C"; ctx.beginPath(); ctx.arc(Math.round(26 * u), Math.round(30 * u), Math.round(118 * u), 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "#2F6FDE"; ctx.beginPath();
    ctx.moveTo(W, H - Math.round(120 * u)); ctx.lineTo(W, H); ctx.lineTo(W - Math.round(120 * u), H); ctx.closePath(); ctx.fill();
    ctx.restore();
  }
  if (look === "neon") {
    ctx.save();
    const g = ctx.createRadialGradient(W / 2, H * 0.42, 0, W / 2, H * 0.42, H * 0.75);
    g.addColorStop(0, "rgba(64,92,170,.28)"); g.addColorStop(1, "rgba(11,14,23,0)");
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
    ctx.strokeStyle = "rgba(120,150,220,.07)"; ctx.lineWidth = 1;
    const step = Math.round(54 * u);
    ctx.beginPath();
    for (let x = step; x < W; x += step) { ctx.moveTo(x, 0); ctx.lineTo(x, H); }
    for (let y = step; y < H; y += step) { ctx.moveTo(0, y); ctx.lineTo(W, y); }
    ctx.stroke(); ctx.restore();
  }
}
/* A strip of torn paper: straight sides, a ragged top and bottom. */
function skTorn(ctx, x, y, w, h, fill, u, rnd) {
  const step = Math.round(20 * u), amp = 5 * u;
  const top = [], bot = [];
  for (let px = 0; px <= w; px += step) { top.push([x + Math.min(px, w), y + (rnd() - 0.5) * 2 * amp]); bot.push([x + Math.min(px, w), y + h + (rnd() - 0.5) * 2 * amp]); }
  top.push([x + w, y + (rnd() - 0.5) * amp]); bot.push([x + w, y + h + (rnd() - 0.5) * amp]);
  ctx.save();
  ctx.shadowColor = "rgba(40,30,10,.20)"; ctx.shadowBlur = Math.round(10 * u); ctx.shadowOffsetY = Math.round(4 * u);
  ctx.fillStyle = fill; ctx.beginPath();
  top.forEach(([px, py], i) => (i ? ctx.lineTo(px, py) : ctx.moveTo(px, py)));
  for (let i = bot.length - 1; i >= 0; i--) ctx.lineTo(bot[i][0], bot[i][1]);
  ctx.closePath(); ctx.fill(); ctx.restore();
}
/* A marker stroke from one point to another: two passes a hair apart, round ends, so it reads as ink and not as a rule. */
function skStroke(ctx, x1, y1, x2, y2, colour, lw, rnd) {
  ctx.save(); ctx.strokeStyle = colour; ctx.lineCap = "round";
  for (let k = 0; k < 2; k++) {
    ctx.lineWidth = k ? Math.max(1, lw * 0.5) : lw; ctx.globalAlpha = k ? 0.55 : 1;
    const j = () => (rnd() - 0.5) * lw * 1.1;
    ctx.beginPath(); ctx.moveTo(x1 + j(), y1 + j());
    ctx.quadraticCurveTo((x1 + x2) / 2 + j(), (y1 + y2) / 2 + j() * 1.6, x2 + j(), y2 + j()); ctx.stroke();
  }
  ctx.restore();
}
/* An outline drawn by hand: a rounded box stroked twice, the second pass a hair off the first. */
function skOutline(ctx, x, y, w, h, r, colour, lw, rnd) {
  ctx.save(); ctx.strokeStyle = colour; ctx.lineJoin = "round"; ctx.lineCap = "round";
  for (let k = 0; k < 2; k++) {
    const j = () => (rnd() - 0.5) * lw * (k ? 1.4 : 0.5);
    ctx.lineWidth = k ? Math.max(1, lw * 0.5) : lw; ctx.globalAlpha = k ? 0.6 : 1;
    roundRect(ctx, x + j(), y + j(), w + j(), h + j(), r); ctx.stroke();
  }
  ctx.restore();
}
/* The container one point sits in. Returns the colour its words are drawn in. `i` picks the colour in the look's cycle. */
function skBox(ctx, S, look, x, y, w, h, i, u, rnd) {
  const c = S.fills ? S.fills[i % S.fills.length] : S.ink;
  if (look === "deck") {
    ctx.save(); ctx.fillStyle = "#FFFFFF"; roundRect(ctx, x, y, w, h, Math.round(14 * u)); ctx.fill(); ctx.restore();
    skOutline(ctx, x, y, w, h, Math.round(14 * u), c, Math.max(3, 4 * u), rnd);
    return S.ink;
  }
  if (look === "chalk") { skOutline(ctx, x, y, w, h, Math.round(12 * u), c, Math.max(3, 3.5 * u), rnd); return S.ink; }
  if (look === "strip") { skTorn(ctx, x, y, w, h, c, u, rnd); return S.onFill; }
  if (look === "metro") {
    ctx.save(); ctx.fillStyle = c; roundRect(ctx, x, y, w, h, Math.round(Math.min(24 * u, h / 2))); ctx.fill(); ctx.restore();
    return S.onFill;
  }
  if (look === "marker" || look === "kraft") {
    skStroke(ctx, x + 6 * u, y + h, x + w - 6 * u, y + h, "rgba(23,23,23,.55)", Math.max(2, 3 * u), rnd);
    return S.ink;
  }
  if (look === "torn") { skTorn(ctx, x, y, w, h, c, u, rnd); return S.onFill; }
  if (look === "block") {
    ctx.save(); ctx.fillStyle = c; roundRect(ctx, x, y, w, h, Math.round(Math.min(26 * u, h / 2))); ctx.fill(); ctx.restore();
    return S.onFill;
  }
  ctx.save();
  ctx.fillStyle = skHexA(c, 0.07); roundRect(ctx, x, y, w, h, Math.round(Math.min(22 * u, h / 2))); ctx.fill();
  ctx.strokeStyle = c; ctx.lineWidth = Math.max(2, Math.round(4 * u)); ctx.shadowColor = c; ctx.shadowBlur = Math.round(22 * u);
  roundRect(ctx, x, y, w, h, Math.round(Math.min(22 * u, h / 2))); ctx.stroke(); ctx.stroke();
  ctx.restore();
  return c;
}
/* The highlight block (the pick, or a slide's note). Returns the colour of its words. */
function skPickBox(ctx, S, look, x, y, w, h, u, rnd) {
  const P = S.pick;
  if (look === "torn" || look === "strip") { skTorn(ctx, x, y, w, h, P.fill, u, rnd); return P.ink; }
  if (look === "deck" || look === "chalk") {
    if (look === "deck") { ctx.save(); ctx.fillStyle = "#FFFFFF"; roundRect(ctx, x, y, w, h, Math.round(14 * u)); ctx.fill(); ctx.restore(); }
    skOutline(ctx, x, y, w, h, Math.round(14 * u), P.fill, Math.max(4, 5 * u), rnd);
    return P.ink;
  }
  if (look === "neon") {
    ctx.save();
    ctx.fillStyle = skHexA(P.fill, 0.12); roundRect(ctx, x, y, w, h, Math.round(24 * u)); ctx.fill();
    ctx.strokeStyle = P.fill; ctx.lineWidth = Math.max(3, Math.round(5 * u)); ctx.shadowColor = P.fill; ctx.shadowBlur = Math.round(30 * u);
    roundRect(ctx, x, y, w, h, Math.round(24 * u)); ctx.stroke(); ctx.stroke();
    ctx.restore(); return P.ink;
  }
  ctx.save(); ctx.fillStyle = P.fill;
  if (look === "marker") {
    // a block filled by hand: the corners are not quite square
    const j = () => (rnd() - 0.5) * 9 * u;
    ctx.beginPath(); ctx.moveTo(x + j(), y + j()); ctx.lineTo(x + w + j(), y + j()); ctx.lineTo(x + w + j(), y + h + j()); ctx.lineTo(x + j(), y + h + j()); ctx.closePath(); ctx.fill();
  } else { roundRect(ctx, x, y, w, h, Math.round((look === "kraft" ? 8 : 30) * u)); ctx.fill(); }
  ctx.restore(); return P.ink;
}
/* A tick or a cross, drawn, not typed: the handwriting faces have no ✓ or ✗, and a drawn mark takes the look's own colour. */
function skMark(ctx, S, look, kind, cx, cy, s, u, onPill) {
  const colour = kind === "yes" ? S.yes : S.no;
  ctx.save();
  if (S.pill && onPill) { ctx.fillStyle = S.pill; ctx.beginPath(); ctx.arc(cx, cy, s * 0.92, 0, Math.PI * 2); ctx.fill(); }
  ctx.strokeStyle = colour; ctx.lineWidth = Math.max(3, s * 0.24); ctx.lineCap = "round"; ctx.lineJoin = "round";
  if (S.glow) { ctx.shadowColor = colour; ctx.shadowBlur = Math.round(16 * u); }
  const k = S.pill && onPill ? 0.5 : 0.62;
  ctx.beginPath();
  if (kind === "yes") { ctx.moveTo(cx - s * k, cy + s * 0.04); ctx.lineTo(cx - s * k * 0.28, cy + s * k * 0.72); ctx.lineTo(cx + s * k, cy - s * k * 0.66); }
  else { ctx.moveTo(cx - s * k * 0.8, cy - s * k * 0.8); ctx.lineTo(cx + s * k * 0.8, cy + s * k * 0.8); ctx.moveTo(cx + s * k * 0.8, cy - s * k * 0.8); ctx.lineTo(cx - s * k * 0.8, cy + s * k * 0.8); }
  ctx.stroke(); ctx.restore();
}
/* The number in front of a point. */
function skNum(ctx, S, look, n, cx, cy, r, colour, u, rnd) {
  ctx.save(); ctx.textAlign = "center"; ctx.textBaseline = "middle";
  const label = String(n);
  if (look === "marker") {
    ctx.strokeStyle = S.accent; ctx.lineWidth = Math.max(3, 4.5 * u); ctx.lineCap = "round";
    for (let k = 0; k < 2; k++) { ctx.globalAlpha = k ? 0.6 : 1; ctx.beginPath(); ctx.ellipse(cx + (rnd() - 0.5) * 3 * u, cy + (rnd() - 0.5) * 3 * u, r * (1 + k * 0.05), r * (0.94 - k * 0.03), (rnd() - 0.5) * 0.5, 0.2, Math.PI * 2 + 0.6); ctx.stroke(); }
    ctx.globalAlpha = 1; ctx.fillStyle = S.accent; ctx.font = "400 " + Math.round(r * 1.15) + "px " + SK_MARK; ctx.fillText(label, cx, cy + r * 0.06);
  } else if (look === "deck") {
    ctx.fillStyle = colour; ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "#FFFFFF"; ctx.font = "800 " + Math.round(r * 1.05) + "px " + SK_SANS; ctx.fillText(label, cx, cy + r * 0.06);
  } else if (look === "chalk") {
    ctx.strokeStyle = colour; ctx.lineWidth = Math.max(2, 3 * u); ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.stroke();
    ctx.fillStyle = colour; ctx.font = "700 " + Math.round(r * 1.4) + "px " + SK_HAND; ctx.fillText(label, cx, cy + r * 0.04);
  } else if (look === "metro") {
    // a station: a white ring on the line, in the colour of its block
    ctx.fillStyle = "#FFFFFF"; ctx.strokeStyle = colour; ctx.lineWidth = Math.max(4, 7 * u);
    ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
    ctx.fillStyle = colour; ctx.font = "700 " + Math.round(r * 1.4) + "px " + SK_HAND; ctx.fillText(label, cx, cy + r * 0.04);
  } else if (look === "torn" || look === "strip") {
    ctx.fillStyle = S.ink; ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "#FFFFFF"; ctx.font = "700 " + Math.round(r * 1.35) + "px " + SK_HAND; ctx.fillText(label, cx, cy + r * 0.04);
  } else if (look === "block") {
    ctx.fillStyle = "#FFFFFF"; ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = S.ink; ctx.font = "800 " + Math.round(r * 1.05) + "px " + SK_SANS; ctx.fillText(label, cx, cy + r * 0.06);
  } else {
    ctx.strokeStyle = colour; ctx.lineWidth = Math.max(2, 3.5 * u); ctx.shadowColor = colour; ctx.shadowBlur = Math.round(14 * u);
    ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.stroke();
    ctx.fillStyle = colour; ctx.font = "700 " + Math.round(r * 1.05) + "px " + SK_SANS; ctx.fillText(label, cx, cy + r * 0.06);
  }
  ctx.restore();
}
/* Wrapped lines, drawn left or centred. Returns the y under the last line. */
function skLines(ctx, lines, x, y, w, lh, colour, centre, glow, u) {
  ctx.save(); ctx.fillStyle = colour; ctx.textBaseline = "top"; ctx.textAlign = centre ? "center" : "left";
  if (glow) { ctx.shadowColor = glow; ctx.shadowBlur = Math.round(14 * u); }
  for (const l of lines) { ctx.fillText(l, centre ? x + w / 2 : x, y); y += lh; }
  ctx.restore(); return y;
}
/* The headline, centred, the *marked* words in the accent. Words are measured one by one so a colour change never moves a break. */
function skTitle(ctx, S, look, text, x, y, w, px, u, ink, accent) {
  const raw = String(text || "").trim();
  if (!raw) return y;
  ctx.font = S.headW + " " + px + "px " + S.head; ctx.textBaseline = "top";
  const words = [];
  /* A word is what stands between two spaces, whatever its colours: in "*VISIA*?" the question mark belongs to VISIA. A piece
     that follows another with no space between them is glued to it (`glue`): no gap is drawn, and no line breaks there. */
  let spaced = true;
  for (const tok of gTokens(S.caps ? raw.toUpperCase() : raw, ink, accent)) {
    const lead = /^\s/.test(tok.t), trail = /\s$/.test(tok.t);
    tok.t.split(/\s+/).filter(Boolean).forEach((wd, k) => {
      hardSplit(ctx, wd, w).forEach((part, j) => words.push({ t: part, c: tok.c, glue: k === 0 && j === 0 && !lead && !spaced && words.length > 0 }));
    });
    spaced = trail || !tok.t.trim();
  }
  const sp = ctx.measureText(" ").width, lines = [];
  let line = [], lw = 0;
  for (let i = 0; i < words.length; i++) {
    // a word and the pieces glued to it are measured and placed as one
    let ww = ctx.measureText(words[i].t).width, j = i;
    while (j + 1 < words.length && words[j + 1].glue) { j += 1; ww += ctx.measureText(words[j].t).width; }
    const group = words.slice(i, j + 1);
    if (line.length && lw + sp + ww > w) { lines.push({ line, lw }); line = [...group]; lw = ww; } else { lw += (line.length ? sp : 0) + ww; line.push(...group); }
    i = j;
  }
  if (line.length) lines.push({ line, lw });
  const lh = Math.round(px * (S.head === SK_HAND ? 0.98 : 1.14));
  ctx.save(); ctx.textAlign = "left";
  for (const L of lines) {
    let cx = x + (w - L.lw) / 2;
    for (const wd of L.line) {
      if (wd.glue && wd !== L.line[0]) cx -= sp;
      const lit = !!S.hilite && wd.c === S.hilite;      // the marked words keep the ink and take a highlighter stroke behind them
      if (lit) { ctx.save(); ctx.fillStyle = S.hilite; ctx.fillRect(cx - px * 0.1, y + px * 0.04, ctx.measureText(wd.t).width + px * 0.2, px * 1.02); ctx.restore(); }
      ctx.fillStyle = lit ? ink : wd.c;
      if (S.glow) { ctx.shadowColor = wd.c; ctx.shadowBlur = Math.round(20 * u); }
      ctx.fillText(wd.t, cx, y);
      // Caveat has one weight and it is a light one at headline size: a stroke in the same colour gives it the weight of a brush
      if (S.head === SK_HAND) { ctx.strokeStyle = wd.c; ctx.lineWidth = Math.max(1, px * 0.022); ctx.lineJoin = "round"; ctx.strokeText(wd.t, cx, y); }
      cx += ctx.measureText(wd.t).width + sp;
    }
    y += lh;
  }
  ctx.restore();
  return y;
}
const skBodyFont = (S, px, bold) => (bold ? (S.boldW || (S.body === SK_SANS ? 800 : S.bodyW)) : S.bodyW) + " " + Math.round(px * S.bodyK) + "px " + S.body;
/* the heading of one point: a look may set it in its marker face (deck), else it is the body face in bold */
const skItemFont = (S, px) => (S.itemHead ? "400 " + Math.round(px * 1.02) + "px " + S.itemHead : skBodyFont(S, px, true));
const skItemHead = (S, t) => (S.itemHead ? String(t).toUpperCase() : t);
const skBodyLh = (S, px) => Math.round(px * S.bodyK * (S.body === SK_HAND ? 1.02 : 1.3));

/* The points as a column of containers. `numbered` puts the look's number in front. Every point is drawn, whole.
   Three looks lay the column out their own way: deck sets four or more points two to a row; metro puts the numbers on a line
   down the left, one station per point; strip sets a third cell at the right of the heading, as a price sits on a label. */
function skList(ctx, S, look, items, x, y, w, u, f, rnd, numbered) {
  const padX = Math.round(26 * u * f), padY = Math.round((look === "marker" ? 12 : 20) * u * f), gap = Math.round((look === "marker" ? 12 : 18) * u * f);
  const r = Math.round(27 * u * f), px = 33 * u * f, lh = skBodyLh(S, px);
  const rail = S.rail && numbered ? r * 2 + Math.round(26 * u * f) : 0;                 // metro: the line and its stations
  const cols = S.grid && items.length >= 4 ? 2 : 1, colGap = Math.round(18 * u * f);
  const bw = (w - rail - colGap * (cols - 1)) / cols;
  const inNum = numbered && !rail && look !== "strip";
  const numW = inNum ? r * 2 + Math.round(18 * u * f) : 0;
  const centred = !numbered && !S.inline && cols === 1;
  // measure every point first: a row of two is as tall as its taller card, and the line needs every station's place
  const cells = items.map((it, i) => {
    const c = gCells(it), head = c.length > 1 ? c[0] : "";
    const value = S.inline && c.length > 2 ? c[c.length - 1] : "";
    const detail = c.length > 1 ? c.slice(1, value ? -1 : undefined).filter(Boolean).join(" · ") : c[0];
    const tw = bw - padX * 2 - numW;
    ctx.font = skItemFont(S, px); const vw = value ? Math.min(tw * 0.5, ctx.measureText(value).width) : 0;
    const hl = head ? gWrap(ctx, skItemHead(S, head), tw - (vw ? vw + Math.round(20 * u * f) : 0)) : [];
    const vl = value ? gWrap(ctx, value, Math.max(vw, tw * 0.3)) : [];
    ctx.font = skBodyFont(S, px, false); const dl = detail ? gWrap(ctx, detail, tw) : [];
    const h = Math.max((Math.max(hl.length, vl.length) + dl.length) * lh, inNum ? r * 2 : 0, rail ? r * 2 : 0) + padY * 2;
    return { i, hl, vl, dl, h, tw };
  });
  const rows = [];
  for (let i = 0; i < cells.length; i += cols) rows.push(cells.slice(i, i + cols));
  const y0 = y, stations = [];
  for (const row of rows) {
    const h = Math.max(...row.map((c) => c.h));
    row.forEach((c, k) => {
      const bx = x + rail + k * (bw + colGap);
      const fill = S.fills ? S.fills[c.i % S.fills.length] : S.ink;
      const colour = skBox(ctx, S, look, bx, y, bw, h, c.i, u, rnd);
      if (inNum) skNum(ctx, S, look, c.i + 1, bx + padX + r, y + h / 2, r, look === "deck" || look === "chalk" ? fill : colour, u, rnd);
      if (rail) stations.push([x + r, y + h / 2, fill, c.i + 1]);
      const top = Math.max(c.hl.length, c.vl.length);
      let ty = y + Math.round((h - (top + c.dl.length) * lh) / 2);
      const tx = bx + padX + numW, glow = S.glow ? colour : "";
      const headC = S.headFromBox ? fill : (S.body === SK_HAND && !S.rail && !S.inline ? S.accent : colour);   // one-weight handwriting cannot go bold: the heading takes the accent
      if (c.hl.length) { ctx.font = skItemFont(S, px); skLines(ctx, c.hl, tx, ty, c.tw, lh, headC, centred, glow, u); }
      if (c.vl.length) {
        ctx.save(); ctx.font = skItemFont(S, px); ctx.fillStyle = colour; ctx.textAlign = "right"; ctx.textBaseline = "top";
        c.vl.forEach((l, n) => ctx.fillText(l, bx + bw - padX, ty + n * lh)); ctx.restore();
      }
      ty += top * lh;
      if (c.dl.length) { ctx.font = skBodyFont(S, px, false); skLines(ctx, c.dl, tx, ty, c.tw, lh, colour, centred, c.hl.length ? "" : glow, u); }
    });
    y += h + gap;
  }
  if (stations.length) {
    // the line: one stroke per stretch, in the colour of the station it runs into, then the stations on top of it
    ctx.save(); ctx.lineCap = "round"; ctx.lineWidth = Math.max(6, Math.round(12 * u * f));
    for (let i = 1; i < stations.length; i++) { ctx.strokeStyle = stations[i][2]; ctx.beginPath(); ctx.moveTo(stations[i - 1][0], stations[i - 1][1]); ctx.lineTo(stations[i][0], stations[i][1]); ctx.stroke(); }
    ctx.restore();
    for (const [cx, cy, c, n] of stations) skNum(ctx, S, look, n, cx, cy, r, c, u, rnd);
  }
  return Math.max(y0, y - (rows.length ? gap : 0));
}
/* The comparison. One row per point, cells split on "|". */
function skTable(ctx, S, look, items, x, y, w, u, f, rnd) {
  let rows = items.map((it) => gCells(it).slice(0, S.inline ? 9 : 5));          // a strip has no columns to run out of
  const cols = Math.max(...rows.map((r) => r.length));
  rows = rows.map((r) => [...r, ...Array(cols - r.length).fill("")]);
  const marked = (r) => r.slice(1).some((c) => skMarkOf(c));
  /* Column headings need three columns: in a two-column table the first row is a fact like any other ("Rinse-off | 3.0%" was
     drawn as a heading, small and in capitals, which hid a limit). With three or more, a first row with no tick or cross in it
     is the headings when at least half of the rows under it carry one. */
  const under = rows.slice(1);
  const header = cols >= 3 && under.length >= 2 && !marked(rows[0]) && under.filter(marked).length * 2 >= under.length ? rows.shift() : null;
  if (S.inline && header) return skStrips(ctx, S, look, header, rows, x, y, w, u, f, rnd);     // strip: one strip per row, the answers in a line
  if (S.rail) return skLineMap(ctx, S, look, header, rows, x, y, w, u, f, rnd);                   // metro: every row is a line
  const padX = Math.round(22 * u * f), padY = Math.round(16 * u * f), gap = Math.round((look === "marker" ? 6 : 14) * u * f);
  const firstW = Math.round(w * (cols === 2 ? 0.56 : cols === 3 ? 0.38 : cols === 4 ? 0.34 : 0.30)), restW = (w - firstW) / (cols - 1);
  const px = 30 * u * f, lh = skBodyLh(S, px);
  if (header) {
    // the headings come down in size until their longest word fits its column: a heading broken mid-word reads as a mistake
    const TH = S.tableHead || { face: SK_SANS, w: 700, k: 1 };
    const thFont = (hp) => TH.w + " " + Math.round(hp * TH.k) + "px " + TH.face;
    let hpx = 23 * u * f;
    const fitsCol = () => header.every((c, k) => String(c).toUpperCase().split(/\s+/).every((wd) => ctx.measureText(wd).width <= (k ? restW : firstW) - Math.round(10 * u)));
    for (; hpx > 13 * u; hpx -= 1) { ctx.font = thFont(hpx); if (fitsCol()) break; }
    ctx.font = thFont(hpx);
    const cellLines = header.map((c, k) => gWrap(ctx, String(c).toUpperCase(), (k ? restW : firstW) - Math.round(10 * u)));
    const hlh = Math.round(hpx * TH.k * 1.2), hh = Math.max(...cellLines.map((l) => l.length)) * hlh;
    cellLines.forEach((ls, k) => {
      const cx0 = k ? x + firstW + (k - 1) * restW : x + padX;
      const top = y + hh - ls.length * hlh;
      ctx.font = thFont(hpx);
      // deck and chalk give each column its own colour, the colour its card or box has above the table
      const hc = S.headFromBox && k ? S.fills[(k - 1) % S.fills.length] : look === "neon" ? S.muted : S.accent;
      skLines(ctx, ls, cx0, top, k ? restW : firstW - padX, hlh, hc, k > 0, "", u);
    });
    y += hh + Math.round(12 * u * f);
    if (look === "marker") skStroke(ctx, x, y - Math.round(4 * u * f), x + w, y - Math.round(4 * u * f), S.ink, Math.max(3, 4 * u), rnd);
    if (S.rowRule === "line") { ctx.save(); ctx.fillStyle = S.ink; ctx.fillRect(x, y - Math.round(6 * u * f), w, Math.max(2, Math.round(3 * u))); ctx.restore(); }
  }
  rows.forEach((r, i) => {
    ctx.font = skBodyFont(S, px, true); const ll = gWrap(ctx, r[0], firstW - padX - Math.round(8 * u));
    ctx.font = skBodyFont(S, px, false);
    const cl = r.slice(1).map((c) => (skMarkOf(c) ? null : gWrap(ctx, c, restW - Math.round(14 * u))));
    const tall = Math.max(ll.length, ...cl.map((l) => (l ? l.length : 1)));
    const h = tall * lh + padY * 2;
    let colour = S.ink;
    if (S.rowRule) {
      // deck and chalk rule the rows off instead of boxing them: a thin line, or a dashed one in chalk
      ctx.save(); ctx.strokeStyle = S.rowRule === "dash" ? skHexA(S.ink, 0.45) : "rgba(44,62,80,.18)"; ctx.lineWidth = Math.max(1, Math.round(2 * u));
      if (S.rowRule === "dash") ctx.setLineDash([Math.round(8 * u), Math.round(8 * u)]);
      ctx.beginPath(); ctx.moveTo(x, y + h + gap / 2); ctx.lineTo(x + w, y + h + gap / 2); ctx.stroke(); ctx.restore();
    } else colour = skBox(ctx, S, look, x, y, w, h, i, u, rnd);
    ctx.font = skBodyFont(S, px, true);
    skLines(ctx, ll, x + padX, y + Math.round((h - ll.length * lh) / 2), firstW - padX, lh, colour, false, S.glow ? colour : "", u);
    r.slice(1).forEach((c, k) => {
      const cx0 = x + firstW + k * restW, kind = skMarkOf(c);
      if (kind) skMark(ctx, S, look, kind, cx0 + restW / 2, y + h / 2, Math.min(lh * 0.62, restW * 0.24), u, true);
      else if (cl[k] && cl[k].length) { ctx.font = skBodyFont(S, px, false); skLines(ctx, cl[k], cx0, y + Math.round((h - cl[k].length * lh) / 2), restW, lh, colour, true, "", u); }
    });
    y += h + gap;
  });
  return y - (rows.length ? gap : 0);
}
/* strip: the comparison as ONE torn strip per row. The name, a value at the right (the last cell that is words, when there are
   two or more), the other words as a line under it, and every yes or no as "tick, column name" in a line that wraps. */
function skStrips(ctx, S, look, header, rows, x, y, w, u, f, rnd) {
  const padX = Math.round(28 * u * f), padY = Math.round(20 * u * f), gap = Math.round(18 * u * f);
  const px = 31 * u * f, lh = skBodyLh(S, px), npx = px * 1.3, nlh = skBodyLh(S, npx), tw = w - padX * 2;
  const ms = lh * 0.3, mGap = Math.round(10 * u * f), tGap = Math.round(26 * u * f);
  rows.forEach((r, i) => {
    const marks = [], texts = [];
    r.slice(1).forEach((c, k) => { const kind = skMarkOf(c); if (kind) marks.push([kind, String(header[k + 1] || "").trim()]); else if (String(c || "").trim()) texts.push(String(c).trim()); });
    const value = texts.length >= 2 ? texts.pop() : "";
    ctx.font = skBodyFont(S, npx, true);
    const vw = value ? Math.min(tw * 0.5, ctx.measureText(value).width) : 0;
    const nl = gWrap(ctx, r[0], tw - (vw ? vw + Math.round(24 * u * f) : 0)), vl = value ? gWrap(ctx, value, Math.max(vw, tw * 0.3)) : [];
    ctx.font = skBodyFont(S, px, false);
    const dl = texts.length ? gWrap(ctx, texts.join(" · "), tw) : [];
    // the answers, wrapped as whole "tick + name" pieces
    const lines = []; let line = [], lw = 0;
    for (const [kind, name] of marks) {
      const ww = ms * 2 + (name ? mGap + ctx.measureText(name).width : 0);
      if (line.length && lw + tGap + ww > tw) { lines.push(line); line = []; lw = 0; }
      line.push([kind, name, lw + (line.length ? tGap : 0)]); lw += (line.length > 1 ? tGap : 0) + ww;
    }
    if (line.length) lines.push(line);
    const top = Math.max(nl.length, vl.length);
    const h = top * nlh + dl.length * lh + lines.length * lh + (lines.length ? Math.round(6 * u * f) : 0) + padY * 2;
    const colour = skBox(ctx, S, look, x, y, w, h, i, u, rnd);
    let ty = y + padY;
    ctx.font = skBodyFont(S, npx, true); skLines(ctx, nl, x + padX, ty, tw, nlh, colour, false, "", u);
    if (vl.length) { ctx.save(); ctx.fillStyle = colour; ctx.textAlign = "right"; ctx.textBaseline = "top"; vl.forEach((l, n) => ctx.fillText(l, x + w - padX, ty + n * nlh + (nlh - lh) / 2)); ctx.restore(); }
    ty += top * nlh;
    if (dl.length) { ctx.font = skBodyFont(S, px, false); ty = skLines(ctx, dl, x + padX, ty, tw, lh, colour, false, "", u); }
    if (lines.length) ty += Math.round(6 * u * f);
    for (const ln of lines) {
      for (const [kind, name, off] of ln) {
        skMark(ctx, S, look, kind, x + padX + off + ms, ty + lh * 0.5, ms * 1.5, u, false);
        if (name) { ctx.save(); ctx.font = skBodyFont(S, px, false); ctx.fillStyle = colour; ctx.textBaseline = "top"; ctx.textAlign = "left"; ctx.fillText(name, x + padX + off + ms * 2 + mGap, ty); ctx.restore(); }
      }
      ty += lh;
    }
    y += h + gap;
  });
  return y - (rows.length ? gap : 0);
}
/* metro: the comparison as a line map. Every row is a line: its name in a coloured block at the left, the line running right
   through one station per column. Yes is a big white ring in the line's colour with a tick in it; no is a small grey stop with
   a red cross; words sit in a white plate on the line. The column names stand over dotted guides. */
function skLineMap(ctx, S, look, header, rows, x, y, w, u, f, rnd) {
  const cols = Math.max(...rows.map((r) => r.length));
  const firstW = Math.round(w * (cols <= 3 ? 0.42 : cols === 4 ? 0.36 : 0.32)), restW = (w - firstW) / Math.max(1, cols - 1);
  const padX = Math.round(22 * u * f), padY = Math.round(16 * u * f), gap = Math.round(22 * u * f);
  const px = 31 * u * f, lh = skBodyLh(S, px), spx = 24 * u * f, slh = skBodyLh(S, spx);
  const R = Math.min(restW * 0.3, Math.round(34 * u * f));
  const stationX = (k) => x + firstW + restW * (k + 0.5);
  let top = y;
  if (header) {
    let hpx = 27 * u * f;
    const fits = () => header.slice(1).every((c) => String(c).split(/\s+/).every((wd) => ctx.measureText(wd).width <= restW - Math.round(8 * u)));
    for (; hpx > 14 * u; hpx -= 1) { ctx.font = skBodyFont(S, hpx, true); if (fits()) break; }
    ctx.font = skBodyFont(S, hpx, true);
    const hl = header.slice(1).map((c) => gWrap(ctx, String(c), restW - Math.round(8 * u))), hlh = skBodyLh(S, hpx);
    const hh = Math.max(1, ...hl.map((l) => l.length)) * hlh;
    hl.forEach((ls, k) => { ctx.font = skBodyFont(S, hpx, true); skLines(ctx, ls, x + firstW + restW * k, y + hh - ls.length * hlh, restW, hlh, S.ink, true, "", u); });
    y += hh + Math.round(14 * u * f); top = y;
  }
  // every row measured first, so the guides can be drawn under the lines and the stations
  const laid = rows.map((r) => {
    ctx.font = skBodyFont(S, px, true); const nl = gWrap(ctx, r[0], firstW - padX * 2);
    ctx.font = skBodyFont(S, spx, false);
    const cl = r.slice(1).map((c) => (skMarkOf(c) || !String(c || "").trim() ? null : gWrap(ctx, c, restW - Math.round(26 * u * f))));
    const plate = Math.max(0, ...cl.map((l) => (l ? l.length * slh + Math.round(14 * u * f) : 0)));
    return { r, nl, cl, h: Math.max(nl.length * lh + padY * 2, R * 2 + Math.round(8 * u * f), plate) };
  });
  const total = laid.reduce((a, L) => a + L.h, 0) + gap * Math.max(0, laid.length - 1);
  ctx.save(); ctx.strokeStyle = "rgba(31,42,51,.22)"; ctx.lineWidth = Math.max(2, Math.round(3 * u)); ctx.setLineDash([Math.round(3 * u), Math.round(9 * u)]); ctx.lineCap = "round";
  for (let k = 0; k < cols - 1; k++) { ctx.beginPath(); ctx.moveTo(stationX(k), top); ctx.lineTo(stationX(k), top + total); ctx.stroke(); }
  ctx.restore();
  laid.forEach((L, i) => {
    const c = S.fills[i % S.fills.length], cy = y + L.h / 2;
    ctx.save(); ctx.strokeStyle = c; ctx.lineCap = "round"; ctx.lineWidth = Math.max(8, Math.round(15 * u * f));
    ctx.beginPath(); ctx.moveTo(x + firstW - Math.round(10 * u), cy); ctx.lineTo(x + w - Math.round(8 * u), cy); ctx.stroke(); ctx.restore();
    const colour = skBox(ctx, S, look, x, y, firstW, L.h, i, u, rnd);
    ctx.font = skBodyFont(S, px, true); skLines(ctx, L.nl, x + padX, y + Math.round((L.h - L.nl.length * lh) / 2), firstW - padX * 2, lh, colour, false, "", u);
    L.r.slice(1).forEach((cell, k) => {
      const cx = stationX(k), kind = skMarkOf(cell);
      ctx.save(); ctx.lineCap = "round"; ctx.lineJoin = "round";
      if (kind === "yes") {
        ctx.fillStyle = "#FFFFFF"; ctx.strokeStyle = c; ctx.lineWidth = Math.max(5, Math.round(9 * u * f));
        ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
        ctx.lineWidth = Math.max(4, R * 0.2); ctx.beginPath(); ctx.moveTo(cx - R * 0.46, cy + R * 0.04); ctx.lineTo(cx - R * 0.12, cy + R * 0.4); ctx.lineTo(cx + R * 0.5, cy - R * 0.36); ctx.stroke();
      } else if (kind === "no") {
        const q = R * 0.46;
        ctx.fillStyle = "#EEF0F2"; ctx.strokeStyle = "#9AA3AC"; ctx.lineWidth = Math.max(2, Math.round(4 * u * f));
        ctx.beginPath(); ctx.arc(cx, cy, q, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
        ctx.strokeStyle = S.no; ctx.lineWidth = Math.max(3, q * 0.3); ctx.beginPath();
        ctx.moveTo(cx - q * 0.45, cy - q * 0.45); ctx.lineTo(cx + q * 0.45, cy + q * 0.45); ctx.moveTo(cx + q * 0.45, cy - q * 0.45); ctx.lineTo(cx - q * 0.45, cy + q * 0.45); ctx.stroke();
      } else if (L.cl[k]) {
        const ph = L.cl[k].length * slh + Math.round(10 * u * f), pw = restW - Math.round(10 * u * f);
        ctx.fillStyle = "#FFFFFF"; ctx.strokeStyle = c; ctx.lineWidth = Math.max(2, Math.round(4 * u * f));
        roundRect(ctx, cx - pw / 2, cy - ph / 2, pw, ph, Math.round(12 * u * f)); ctx.fill(); ctx.stroke();
      }
      ctx.restore();
      if (!kind && L.cl[k]) { ctx.font = skBodyFont(S, spx, false); skLines(ctx, L.cl[k], cx - restW / 2, cy - (L.cl[k].length * slh) / 2, restW, slh, S.ink, true, "", u); }
    });
    y += L.h + gap;
  });
  return y - (laid.length ? gap : 0);
}
/* The highlight block with words in it: an optional headline and a body, both centred. */
function skPick(ctx, S, look, head, body, x, y, w, u, f, rnd, headPx) {
  const padX = Math.round(34 * u * f), padY = Math.round(26 * u * f), tw = w - padX * 2;
  const hpx = Math.round((headPx || 50) * u * f * S.headK), bpx = 33 * u * f, blh = skBodyLh(S, bpx);
  const hlh = Math.round(hpx * (S.head === SK_HAND ? 0.98 : 1.14));
  const headText = S.caps ? stripEmph(head).toUpperCase() : stripEmph(head);
  ctx.font = S.headW + " " + hpx + "px " + S.head; const hl = head ? gWrap(ctx, headText, tw) : [];
  ctx.font = skBodyFont(S, bpx, false); const bl = body ? gWrap(ctx, body, tw) : [];
  const mid = hl.length && bl.length ? Math.round(10 * u * f) : 0;
  const h = hl.length * hlh + mid + bl.length * blh + padY * 2;
  const colour = skPickBox(ctx, S, look, x, y, w, h, u, rnd);
  let ty = y + padY;
  if (hl.length) { ctx.font = S.headW + " " + hpx + "px " + S.head; ty = skLines(ctx, hl, x + padX, ty, tw, hlh, S.pick.head || colour, true, S.glow ? S.pick.fill : "", u) + mid; }
  if (bl.length) { ctx.font = skBodyFont(S, bpx, false); skLines(ctx, bl, x + padX, ty, tw, blh, colour, true, "", u); }
  return y + h;
}
/* The cover's picture, framed the way the look frames things. Drawn at a fixed height, so the hook's size never moves it. */
function skPicture(ctx, S, look, im, x, y, w, h, u, rnd) {
  if (look === "block" || look === "metro") { picInBox(ctx, im, x, y, w, h, Math.round(34 * u), 1, 0.5, 0.4); return; }
  if (look === "chalk") {
    picInBox(ctx, im, x, y, w, h, Math.round(14 * u), 1, 0.5, 0.4);
    skOutline(ctx, x, y, w, h, Math.round(14 * u), S.ink, Math.max(4, 5 * u), rnd); return;
  }
  if (look === "neon") {
    picInBox(ctx, im, x, y, w, h, Math.round(24 * u), 1, 0.5, 0.4);
    ctx.save(); ctx.strokeStyle = S.ink; ctx.lineWidth = Math.max(3, Math.round(5 * u)); ctx.shadowColor = "#4DB8FF"; ctx.shadowBlur = Math.round(28 * u);
    roundRect(ctx, x, y, w, h, Math.round(24 * u)); ctx.stroke(); ctx.stroke(); ctx.restore(); return;
  }
  // marker and torn: a print on the paper, white border, a soft shadow, held by two strips of tape
  const b = Math.round(14 * u);
  ctx.save(); ctx.shadowColor = "rgba(40,30,10,.28)"; ctx.shadowBlur = Math.round(18 * u); ctx.shadowOffsetY = Math.round(6 * u);
  ctx.fillStyle = "#FFFFFF"; ctx.fillRect(x, y, w, h); ctx.restore();
  picInBox(ctx, im, x + b, y + b, w - b * 2, h - b * 2, 0, 1, 0.5, 0.4);
  ctx.save(); ctx.fillStyle = look === "torn" || look === "strip" ? "rgba(246,227,161,.85)" : look === "deck" ? "rgba(244,208,63,.8)" : "rgba(215,38,61,.72)";
  for (const cx of [x + w * 0.2, x + w * 0.8]) {
    ctx.save(); ctx.translate(cx, y); ctx.rotate((rnd() - 0.5) * 0.24); ctx.fillRect(-Math.round(62 * u), -Math.round(16 * u), Math.round(124 * u), Math.round(32 * u)); ctx.restore();
  }
  ctx.restore();
}
const SKIN_PIC_H = 0.34;        // the cover picture's share of the card's height
/* Where the words may sit: under the mark and the eyebrow, above the source line (which is measured, because a long citation
   takes two lines and the block must stop above it). */
function skFoot(ctx, spec, W, H, u, M) {
  const footnote = String(spec.footnote || "").trim();
  if (!footnote) return { lines: [], lh: 0, y: H, bottom: H - Math.round(84 * u) };
  const px = Math.round(22 * u), lh = Math.round(30 * u);
  ctx.font = "400 " + px + "px " + SK_TEXT;
  const lines = gWrap(ctx, (spec.stream === "linkedin" ? "Source: " : "Sumber: ") + footnote, W - M * 2);
  const y = H - Math.round(50 * u) - lines.length * lh;
  return { lines, lh, y, px, bottom: y - Math.round(26 * u) };
}
const SKIN_TOP = 150;
const SKIN_TITLE_PX = { cover: 104, points: 66, table: 62, close: 82, pick: 62 };
/* How far the headline may grow before its longest word no longer fits the line. Past that the word would be cut in two
   ("NOTIFIKAS / I"), which reads as a mistake on the one line that has to land. */
function skWordCap(ctx, spec, W) {
  const look = skinOf(spec), S = SKINS[look], part = spec.template.slice(2);
  const u = W / 1080, w = W - Math.round(64 * u) * 2 - (part === "pick" ? Math.round(34 * u) * 2 : 0);
  const raw = stripEmph(spec.title || "").trim();
  if (!raw) return Infinity;
  ctx.font = S.headW + " " + Math.round((SKIN_TITLE_PX[part] || 66) * u * S.headK) + "px " + S.head;
  const widest = Math.max(...(S.caps ? raw.toUpperCase() : raw).split(/\s+/).map((x) => ctx.measureText(x).width));
  return widest > 0 ? (w / widest) * 0.97 : Infinity;
}
function skinPaint(ctx, spec, W, H, f, shift) {
  // ERA's dress takes ERA's red as it stands, so a saved design's own accent colour reaches a front page drawn in it
  const look = skinOf(spec), part = spec.template.slice(2);
  const S = look === "kraft" ? { ...SKINS.kraft, accent: ERA_PAL.red, no: ERA_PAL.red, pick: { fill: ERA_PAL.red, ink: "#FFFFFF" } } : SKINS[look];
  const u = W / 1080, M = Math.round(64 * u), w = W - M * 2;
  const rnd = picRng(skSeed(spec));                   // the same torn edges in the measuring pass and the painting pass
  const title = String(spec.title || "").trim(), lead = stripEmph(spec.lead || "").trim(), note = stripEmph(spec.note || "").trim();
  const items = (spec.items || []).map((x) => stripEmph(x).trim()).filter(Boolean);
  const warn = [];
  skGround(ctx, S, look, W, H, u, rnd);
  if (spec.eyebrow && S.badge) eraBadge(ctx, W, u, M, spec.eyebrow, spec);
  else if (spec.eyebrow) {
    ctx.save(); ctx.font = "700 " + Math.round(21 * u) + "px " + SK_SANS; ctx.fillStyle = S.muted; ctx.textBaseline = "top"; ctx.textAlign = "center";
    const eb = gWrap(ctx, String(spec.eyebrow).toUpperCase(), w)[0] || "";
    ctx.fillText(eb, W / 2, Math.round(98 * u)); ctx.restore();
  }
  const foot = skFoot(ctx, spec, W, H, u, M);
  if (foot.lines.length) { ctx.font = "400 " + foot.px + "px " + SK_TEXT; skLines(ctx, foot.lines, M, foot.y, w, foot.lh, S.muted, true, "", u); }
  // on the cover only the hook follows `f`; the supporting line, any points and the note keep to reading size
  const fr = part === "cover" ? Math.min(f, SKIN_COVER_REST) : f;
  const gapL = Math.round(30 * u * fr), gapS = Math.round(18 * u * fr);
  let y = Math.round(SKIN_TOP * u);
  if (part === "cover" && spec._im) {
    // the picture sits at the top and does not move; the hook is centred in what is left under it
    const ph = Math.round(H * SKIN_PIC_H);
    skPicture(ctx, S, look, spec._im, M, y, w, ph, u, rnd);
    y += ph + Math.round(40 * u);
  }
  y += shift;
  const leadLines = (px, colour) => {
    if (!lead) return;
    ctx.font = skBodyFont(S, px, false);
    y = skLines(ctx, gWrap(ctx, lead, w - Math.round(40 * u)), M + Math.round(20 * u), y, w - Math.round(40 * u), skBodyLh(S, px), colour, true, "", u);
  };
  if (part === "pick") {
    // the recommendation: the headline and its reason are the block
    y = skPick(ctx, S, look, title, lead, M, y, w, u, f, rnd, 62);
    if (items.length) { y += gapL; y = skList(ctx, S, look, items, M, y, w, u, f, rnd, true); }
    if (note) {
      y += gapL; ctx.font = skBodyFont(S, 34 * u * f, true);
      y = skLines(ctx, gWrap(ctx, note, w), M, y, w, skBodyLh(S, 34 * u * f), S.accent, true, S.glow ? S.accent : "", u);
    }
  } else {
    const tpx = SKIN_TITLE_PX[part] || 66;
    y = skTitle(ctx, S, look, title, M, y, w, Math.round(tpx * u * f * S.headK), u, S.ink, S.hilite || S.accent);
    if (look === "marker" && title) { y += Math.round(6 * u * f); skStroke(ctx, W / 2 - w * 0.2, y, W / 2 + w * 0.2, y + 2 * u, S.accent, Math.max(4, 6 * u * f), rnd); y += Math.round(6 * u * f); }
    if (lead && part === "cover" && S.leadBlock) { y += gapL; y = skPick(ctx, S, look, "", lead, M, y, w, u, fr, rnd); }
    else if (lead) { y += part === "cover" ? gapL : gapS; leadLines(34 * u * fr, part === "cover" ? S.muted : S.ink); }
    if (items.length) {
      y += gapL;
      y = part === "table" ? skTable(ctx, S, look, items, M, y, w, u, fr, rnd) : skList(ctx, S, look, items, M, y, w, u, fr, rnd, part === "points");
    }
    if (note) {
      // "Recommended: Meicet MD300. Closest to VISIA" → the words before the colon are the block's own headline
      const cut = /^([^:]{2,28}):\s+(\S[\s\S]*)$/.exec(note);
      y += gapL; y = skPick(ctx, S, look, cut ? cut[1] : "", cut ? cut[2] : note, M, y, w, u, fr, rnd, 44);
    }
  }
  if (y > foot.bottom + 2) warn.push("The slide is fuller than the card: shorten a line.");
  return { warn, y, bottom: foot.bottom };
}
async function renderSkinCard(spec) {
  const [W, H] = sizeOf(spec);
  const c = document.createElement("canvas"); c.width = W; c.height = H;
  const ctx = styleCtx(c.getContext("2d"), spec);
  try { await document.fonts.ready; } catch (e) { }
  const u = W / 1080, look = skinOf(spec);
  // only the cover takes a picture; a picture that will not load leaves a cover with no picture, never a broken card
  if (spec.template.slice(2) === "cover" && spec.bg) { const im = await loadImg(spec.bg); if (im) spec = { ...spec, _im: im }; }
  const top = Math.round(SKIN_TOP * u) + (spec._im ? Math.round(H * SKIN_PIC_H) + Math.round(40 * u) : 0);
  const probe = skinPaint(measureProxy(ctx), spec, W, H, 1, 0);
  const room = probe.bottom - top;
  const used = (f) => skinPaint(measureProxy(ctx), spec, W, H, f, 0).y - top;
  let fill = 1;
  const at1 = probe.y - top;
  if (at1 > room) {
    // fuller than the card: the type comes down until every word fits, and only a slide that does not fit at SKIN_MIN warns
    let lo = SKIN_MIN, hi = 1;
    if (used(lo) <= room) { for (let i = 0; i < 8; i++) { const mid = (lo + hi) / 2; if (used(mid) <= room) lo = mid; else hi = mid; } }
    fill = Math.floor(lo * 100) / 100;
  } else if (!spec.type_size && at1 < SKIN_FROM * room) {
    // room to spare: the type grows to fill it, by the search the hand-drawn cards use (on a cover, the hook alone and further)
    let lo = 1, hi = Math.max(1, Math.min(spec.template.slice(2) === "cover" ? SKIN_COVER_MAX : SKIN_MAX, skWordCap(ctx, spec, W)));
    for (let i = 0; i < 8; i++) { const mid = (lo + hi) / 2; if (used(mid) <= SKIN_TARGET * room) lo = mid; else hi = mid; }
    fill = lo > 1.03 ? Math.floor(lo * 100) / 100 : 1;
  }
  /* The height is not a smooth function of the size: one more pixel can push a word to the next line. So the size the search
     landed on is checked, and stepped down until the card really holds it. */
  for (let i = 0; i < 40 && fill > SKIN_MIN && used(fill) > room; i++) fill = Math.round((fill - 0.02) * 100) / 100;
  const slack = room - used(fill);
  const shift = slack > 0 ? Math.round(slack / 2) : 0;           // centred between the eyebrow and the source line
  const out = skinPaint(ctx, spec, W, H, fill, shift);
  if (spec.stream !== "linkedin") {
    await drawBrandMark(ctx, spec, W, u, Math.round(64 * u), { top: 40, h: 28, knockout: !!SKINS[look].dark, textFill: SKINS[look].dark ? "rgba(244,247,255,.6)" : "rgba(21,23,27,.5)" });
  }
  return { url: c.toDataURL("image/jpeg", 0.9), warn: out.warn, y: out.y, fill };
}

export const LOOKS = [
  { k: "classic", bm: "Semasa", en: "Semasa", hintBm: "Reka bentuk asal Semasa: kertas krim, tajuk serif, nombor slaid.",
    hintEn: "Semasa's own drawing: cream paper, serif headline, slide numbers." },
  { k: "hand", bm: "Lukisan tangan", en: "Hand-drawn", hintBm: "Papan kelabu-biru, kad putih sempadan bergetar, tajuk marker + highlighter kuning, jadual HEAD TO HEAD.",
    hintEn: "Grey-blue board, white card with wobbly borders, marker headline + yellow highlighter, HEAD TO HEAD table." },
  // the four poster looks (Wan, 16 Nov 2026): each is a cover, points, a tick-and-cross comparison, a recommendation and a closing slide
  { k: "marker", bm: "Poster marker", en: "Marker poster", hintBm: "Kertas krim, tajuk marker hitam, bulatan dan garis merah, blok merah untuk syor. Jadual ✓/✗.",
    hintEn: "Cream paper, black marker headline, red rings and rules, a red block for the pick. Tick and cross table." },
  { k: "torn", bm: "Kertas koyak", en: "Torn paper", hintBm: "Latar kuning air, setiap isi atas jalur kertas pastel yang dikoyak, jalur hijau tua untuk syor.",
    hintEn: "Beige ground, every point on its own torn strip of pastel paper, a dark green strip for the pick." },
  { k: "block", bm: "Blok warna", en: "Colour blocks", hintBm: "Blok warna pejal (biru tua, biru, hijau, oren) dengan tulisan putih, pil putih untuk ✓/✗, syor kuning.",
    hintEn: "Solid colour blocks (navy, blue, green, orange) with white type, white pills for the ticks, a yellow pick." },
  { k: "neon", bm: "Neon", en: "Neon", hintBm: "Latar gelap, kotak bergaris cahaya putih, biru, hijau dan oren, syor merah jambu.",
    hintEn: "A dark ground, glowing outlined boxes in white, blue, green and orange, a pink pick." },
  // four more poster looks (Wan, 16 Nov 2026, "add these poster design also"): the same five slides in four more dresses
  { k: "deck", bm: "Papan kad", en: "Card board", hintBm: "Kad putih atas papan kelabu-biru, setiap isi dalam kad bergaris warna, tajuk marker dengan highlighter kuning, syor berkotak hijau.",
    hintEn: "A white card on a grey-blue board, every point in its own outlined colour card, marker headline with a yellow highlighter, a green box for the pick." },
  { k: "chalk", bm: "Papan kapur", en: "Chalkboard", hintBm: "Papan hijau berbingkai kayu, tulisan kapur, kotak bergaris warna kapur, garis putus-putus, syor berkotak kuning.",
    hintEn: "A green board in a wooden frame, chalk handwriting, boxes outlined in chalk colours, dashed rules, a yellow box for the pick." },
  { k: "metro", bm: "Peta laluan", en: "Line map", hintBm: "Peta laluan: setiap isi satu stesen atas garisan, jadual jadi laluan berwarna dengan gelang ✓ besar dan ✗ kecil, syor blok hijau tua.",
    hintEn: "A line map: every point a station on the line, a comparison becomes coloured lines with big ringed ticks and small crosses, a dark green pick." },
  { k: "strip", bm: "Jalur koyak", en: "Torn strips", hintBm: "Jalur kertas koyak: dalam perbandingan setiap baris satu jalur dengan nama, nilai di kanan dan ✓/✗ sebaris.",
    hintEn: "Torn strips: in a comparison every row is one strip with its name, a value at the right and the ticks and crosses in a line." },
  { k: "grid", bm: "Grid", en: "Grid", hintBm: "Studio: kertas graf krim, tajuk tebal, satu perkataan oren.",
    hintEn: "Studio: cream graph paper, ultra-bold headline, one word in orange." },
  { k: "era", bm: "Info ERA", en: "Info ERA", hintBm: "Studio: kertas kraf, highlight marker, blok merah. Penerang yang lantang.",
    hintEn: "Studio: kraft paper, marker highlights, red blocks. A loud explainer." },
  { k: "photo", bm: "Foto", en: "Photo", hintBm: "Studio: gambar anda di belakang perkataan, pada setiap slaid. Perlu gambar latar.",
    hintEn: "Studio: your picture behind the words, on every slide. Needs a background picture." },
  { k: "image", bm: "Gambar", en: "Image", hintBm: "Gambar anda DI ATAS slaid: panel, cetakan bertampal, poster condong atau skrin telefon. Slaid tanpa gambar tetap lengkap.",
    hintEn: "Your picture ON the slide: a panel, a taped print, a tipped poster or a phone screen. A slide with no picture is still complete." },
];
/** A template key as a short readable name ("e_myth" → "ERA · Myth vs fact"), for hand-offs and logs. */
export const templateLabel = (k) => ({ g_title: "Grid · Title", g_stat: "Grid · Number", g_bars: "Grid · Bars", g_rows: "Grid · Numbered", g_table: "Grid · Table",
  g_check: "Grid · Checklist", g_myth: "Grid · Myth vs fact", g_steps: "Grid · Steps", e_hook: "ERA · Hook", e_explain: "ERA · Explainer", e_flow: "ERA · Flow",
  e_vs: "ERA · Versus", e_myth: "ERA · Myth vs fact", e_check: "ERA · Checklist", e_stat: "ERA · Figure", e_event: "ERA · Event poster", p_title: "Photo · Title", p_fact: "Photo · Fact",
  p_quote: "Photo · Quote", p_stat: "Photo · Figure", p_list: "Photo · List", p_split: "Photo · Split",
  h_poster: "Hand · Poster", h_hero: "Hand · Cover", h_note: "Hand · Note" }[k]
  || (SKIN_TPL[k] ? SKIN_NAMES[SKIN_OF[k[0]]] + " · " + SKIN_PART_NAMES[k.slice(2)] : String(k || "")));
export const STUDIO_LOOKS = ["grid", "era", "photo", "image", "hand", ...SKIN_LOOKS];
/** The family palettes, for the Canva hand-off brief: one copy of the hex codes, the ones the renderer draws with. */
export const PALETTES = { grid: GRID_PAL, era: ERA_PAL };
export const isStudioLook = (k) => STUDIO_LOOKS.includes(k);

/* The points of a slide as one paragraph block: one line each, marked when there is more than one. Studio's
   gWrap breaks on "\n", so every point starts on its own line and none is dropped. */
function asLines(points) {
  const p = (points || []).map((x) => String(x || "").trim()).filter(Boolean);
  return p.length > 1 ? p.map((x) => "• " + x).join("\n") : (p[0] || "");
}

/* A Semasa slide list as Studio card specs. EVERY WORD IS KEPT: Studio's templates slice their item lists
   (e_hook 3, e_explain 3, p_fact 4), so a slide with more points than its template shows is given the layout that
   draws them all as lines instead of a template that would silently drop the rest.
   A slide may carry its own design (Studio's per-slide editor, brought over 27 Sep 2026): `template` (any of the
   twenty-one, which then takes the points verbatim as its items, "Label | number" shapes and all), `lead`, `eyebrow`,
   `chip`, `note`, `footnote`, `scrim`, `mascot` ("none", a pose key, or unset = the pose the template hints at) and a
   background already resolved to a drawable address in `bg_url` (`bg: "none"` = no picture on this slide).
   Unset fields fall back to the look's own choices: cover, middle and closing slides take the templates Studio's
   groups name (CARD_GROUPS); the source line is drawn on the closing slide, Semasa's rule; the eyebrow on every
   slide, Studio's. o.mascots = [{k, url}] are the poses on offer (none offered = no mascot anywhere). */
export const TEMPLATE_KEYS = [...Object.keys(GRID_TPL), ...Object.keys(ERA_TPL), ...Object.keys(PHOTO_TPL), ...Object.keys(PIC_TPL), ...Object.keys(HAND_TPL), ...Object.keys(MORE_TPL), ...Object.keys(SKIN_TPL)];
export const takesMascot = (t) => MASCOTS_ON && !!MASCOT_TPL[t];
/** Which templates draw each pose by default: asked of pickMascotFor itself, the renderer's own rule, so the Design
    tab's library can never disagree with a render (Studio's mascotDutyMap). {poseKey: [template, ...]} */
export function mascotDuty(mascots) {
  const out = {};
  if (!MASCOTS_ON) return out;
  for (const tpl of Object.keys(MASCOT_TPL)) {
    const m = pickMascotFor(tpl, (mascots || []).map((x) => ({ name: x.k, k: x.k })));
    if (m) (out[m.k] ||= []).push(tpl);
  }
  return out;
}

function mascotUrl(s, template, mascots) {
  if (!MASCOTS_ON) return "";
  if (!mascots || !mascots.length || !MASCOT_TPL[template]) return "";
  if (s.mascot === "none") return "";
  if (s.mascot) return (mascots.find((m) => m.k === s.mascot) || {}).url || "";
  const m = pickMascotFor(template, mascots.map((x) => ({ name: x.k, url: x.url })));
  return m ? m.url : "";
}

/* "Fit the design to each slide" (Wan, 4 Oct 2026: "more design like ERA, grid, photo"). A look used to give every
   middle slide the same template, so a carousel read as one layout repeated. With `o.fit` a slide that has no template
   of its own gets the one in its family that suits its words: a figure → the figure card, "myth | fact" pairs → the
   myth card, a how-to → steps, a "before you ..." list → the checklist, "heading | detail" lines → the numbered panels.
   Only a template that draws EVERY point is ever chosen (the older ones slice their lists: rows 4, explain 3, flow 4,
   stat 2), and anything unrecognised returns "" so the look's own rule applies, unchanged. Pure: no canvas, no store. */
const RE_FIGURE = /^[~≈<>+\-]?\s*(RM\s?)?\d[\d.,]*\s*(%|x|×|k|m|hari|bulan|tahun|minggu|jam|days?|months?|years?|weeks?|hours?)?$/i;
const RE_MYTH = /mitos|myth|salah faham|misconception|fakta|\bfacts?\b/i;
const RE_STEPS = /langkah|\bsteps?\b|proses|process|cara |how to|aliran|\bflow\b|garis masa|timeline|urutan|selepas|after/i;
const RE_DATE = /\b\d{1,2}\s+[A-Za-zÀ-ÿ]{3,}\.?\s+\d{4}\b/;
const RE_CHECK = /senarai semak|checklist|\bsemak|\bcheck\b|sebelum|before|pastikan|ensure|wajib|\bmust\b|dokumen|documents/i;
/** An event slide: drawn as the event poster, or about to be by fit (a date in the note and people in the points). The editor shows
    the speaker photos for these. */
export const isEventSlide = (s) => (s.template ? s.template === "e_event"
  : RE_DATE.test(String(s.note || "")) && String(s.points || "").split("\n").some((l) => l.trim()));
export function fitTemplate(look, s, i, n, pts) {
  const title = String(s.title || "");
  const piped = pts.length > 0 && pts.every((x) => x.includes("|"));
  const figure = pts.length >= 1 && pts.length <= 2 && pts[0].length <= 12 && RE_FIGURE.test(pts[0]) && (!pts[1] || pts[1].length <= 28);
  const myth = piped && pts.length <= 3 && pts.every((x) => x.split("|").length === 2) && (RE_MYTH.test(title) || RE_MYTH.test(String(s.lead || "")));
  const steps = pts.length >= 2 && pts.length <= 5 && RE_STEPS.test(title);
  const check = pts.length >= 2 && pts.length <= 5 && RE_CHECK.test(title);
  const first = i === 0 && n > 1, last = i === n - 1 && n > 1;
  if (SKIN_LOOKS.includes(look)) return skinTemplate(look, s, i, n, pts);     // the poster looks dress every slide themselves
  if (!pts.length || first) return "";
  if (pts.length <= 6 && RE_DATE.test(String(s.note || ""))) return "e_event";     // a date in the note and people in the points: an event poster
  if (look === "grid") {
    if (figure) return "g_stat";
    if (myth) return "g_myth";
    if (steps) return "g_steps";
    if (check) return "g_check";
    if (piped && pts.length <= 4) return "g_rows";
    return "";
  }
  if (look === "era") {
    if (figure) return "e_stat";
    if (myth) return "e_myth";
    if (steps && piped && pts.length <= 4) return "e_flow";
    if (check || steps) return "e_check";
    if (piped && pts.length <= 3) return "e_explain";
    return "";
  }
  if (look === "image") {
    if (figure) return "i_hero";
    if (last) return "";
    // the step slide (a phone, a "before" print, "after") is for a how-to with a screenshot: it is chosen by hand, never by fit.
    // On an ordinary post its labels meant nothing and a third of the card stayed empty (16 Nov 2026)
    return "i_note";
  }
  if (look === "photo") {
    if (figure) return "p_stat";
    if (last) return "";
    if (piped || pts.length >= 3) return "p_list";
    return i % 2 ? "p_split" : "";
  }
  if (look === "hand") {
    // the poster is one card; a carousel cover is the hero, middle slides are notes. The table detects "Label | detail" pairs.
    if (n === 1) return "h_poster";
    if (piped && pts.length >= 2) return "h_poster";
    return first ? "h_hero" : "h_note";
  }
  return "";
}

/* ---- DESIGNS MADE FROM A REFERENCE (Wan, 4 Oct 2026: "how did you create ERA, Semasa, Grid before? all those are from a reference
   I gave from ws.regulab Studio, I want like that"). ERA, Grid and Photo were drawn by hand from his references. A design from a
   reference is the same idea made by the machine: the Design tab reads a reference picture once (the AI returns its LAYOUT: boxes,
   colours, fonts, which block is the headline, the points, the source, where the pictures and the logo are) and the layout is saved
   with NO words. When an idea becomes a draft, the new words are poured into that layout (lib/designCloneSeed.js layoutToSeed does
   the slot-filling and the fit) and this painter draws the result on the card. Pure canvas, no AI at draw time. */
const MAX_ELEMENTS = 60;
/** A layout as the painter will trust it: an object with at most MAX_ELEMENTS elements, and nothing else it does not know. */
export function normLayout(l) {
  if (!l || typeof l !== "object" || !Array.isArray(l.elements)) return null;
  const num = (v, d = 0) => (Number.isFinite(Number(v)) ? Number(v) : d);
  const els = l.elements.slice(0, MAX_ELEMENTS).filter((e) => e && ["text", "photo", "rect", "ellipse", "line"].includes(e.type)).map((e) => ({
    ...e, x: num(e.x), y: num(e.y), w: num(e.w), h: num(e.h), text: String(e.text || "").slice(0, 400),
  }));
  if (!els.length) return null;
  const covers = (Array.isArray(l.covers) ? l.covers : []).slice(0, 12).filter((c) => c && ["logo", "person"].includes(c.kind))
    .map((c) => ({ kind: c.kind, x: num(c.x), y: num(c.y), w: num(c.w), h: num(c.h) }));
  return { background: l.background && typeof l.background === "object" ? l.background : { color: "#ffffff", gradient: null }, elements: els, covers };
}
const wordsFromSpec = (spec) => ({
  eyebrow: String(spec.eyebrow || "").trim(),
  headline: stripEmph(spec.title || ""),
  points: [spec.lead, ...(spec.items || []), spec.note].map((x) => stripEmph(String(x || "").trim())).filter(Boolean),
  source: String(spec.footnote || "").trim(),
});
function seedGradient(ctx, g, x, y, w, h) {
  const c = gradientCoords(g.angle, w, h), gr = ctx.createLinearGradient(x + c.x1, y + c.y1, x + c.x2, y + c.y2);
  for (const st of g.stops || []) { try { gr.addColorStop(Math.max(0, Math.min(1, Number(st.at))), st.color); } catch (e) { } }
  return gr;
}
function seedPath(ctx, L) {
  ctx.beginPath();
  if (L.ellipse) { ctx.ellipse(L.x + L.w / 2, L.y + L.h / 2, L.w / 2, L.h / 2, 0, 0, Math.PI * 2); return; }
  const r = Math.min(Math.max(0, L.radius || 0), L.w / 2, L.h / 2);
  if (r > 0) gRound(ctx, L.x, L.y, L.w, L.h, r); else ctx.rect(L.x, L.y, L.w, L.h);
}
/* A text layer as the seed describes it: x is the CENTRE of the box and `top` its top edge. Lines are wrapped on spaces (a word
   wider than the box is split), the type shrinks by 6% a step until the widest word fits and, with `maxHeight`, until the block fits
   the box it had in the reference: the words are never cut. */
function seedText(ctx, L) {
  let size = L.size;
  const lh = L.lineHeight || 1.16, left = L.x - L.width / 2;
  const setFont = () => { ctx.font = `${L.italic ? "italic " : ""}${L.weight} ${size}px "${L.font}", ${L.font === "Playfair Display" ? "serif" : "sans-serif"}`; };
  let lines = [];
  const wrap = () => {
    setFont(); lines = [];
    for (const para of String(L.text).split("\n")) {
      let line = "";
      for (const w of para.split(/\s+/).filter(Boolean).flatMap((x) => hardSplit(ctx, x, L.width))) {
        const next = line ? line + " " + w : w;
        if (line && ctx.measureText(next).width > L.width) { lines.push(line); line = w; } else line = next;
      }
      lines.push(line);
    }
  };
  wrap();
  while ((L.maxHeight && lines.length * size * lh > L.maxHeight || lines.some((l) => ctx.measureText(l).width > L.width + 1)) && size > 12) { size = Math.max(12, size * 0.94); wrap(); }
  ctx.save();
  try { ctx.letterSpacing = ((L.spacing || 0) / 1000) * size + "px"; } catch (e) { }
  ctx.fillStyle = L.fill; ctx.textBaseline = "top"; ctx.textAlign = L.align === "center" ? "center" : L.align === "right" ? "right" : "left";
  if (L.shadow) { ctx.shadowColor = "rgba(0,0,0,.35)"; ctx.shadowBlur = Math.round(size * 0.25); ctx.shadowOffsetY = Math.round(size * 0.08); }
  const ax = L.align === "center" ? L.x : L.align === "right" ? left + L.width : left;
  lines.forEach((l, i) => ctx.fillText(l, ax, L.top + i * size * lh + (size * lh - size) / 2));
  ctx.restore();
  return L.top + lines.length * size * lh;
}
async function paintSeed(ctx, seed, o) {
  for (const L of seed.layers) {
    if (L.kind === "rect") {
      if (!L.fill && !L.gradient && !L.stroke) continue;
      ctx.save(); ctx.globalAlpha = L.opacity == null ? 1 : L.opacity; seedPath(ctx, L);
      if (L.gradient && (L.gradient.stops || []).length >= 2) ctx.fillStyle = seedGradient(ctx, L.gradient, L.x, L.y, L.w, L.h); else ctx.fillStyle = L.fill || "transparent";
      if (L.fill || L.gradient) ctx.fill();
      if (L.stroke && L.strokeW > 0) { ctx.strokeStyle = L.stroke; ctx.lineWidth = L.strokeW; ctx.stroke(); }
      ctx.restore();
    } else if (L.kind === "line") {
      ctx.save(); ctx.globalAlpha = L.opacity == null ? 1 : L.opacity; ctx.strokeStyle = L.stroke || "#000"; ctx.lineWidth = L.strokeW || 2; ctx.lineCap = "round";
      ctx.beginPath(); ctx.moveTo(L.x1, L.y1); ctx.lineTo(L.x2, L.y2); ctx.stroke(); ctx.restore();
    } else if (L.kind === "image") {
      const im = await loadImg(L.url);
      if (!im) continue;
      if (L.cover) coverDraw(ctx, im, seed.width, seed.height);
      else if (L.fitIn) {
        const k = Math.min(L.fitIn.w / im.width, L.fitIn.h / im.height);
        ctx.drawImage(im, L.fitIn.x + (L.fitIn.w - im.width * k) / 2, L.fitIn.y + (L.fitIn.h - im.height * k) / 2, im.width * k, im.height * k);
      }
    } else if (L.kind === "photo") {
      if (L.role === "person" && !L.url) continue;              // a face in the reference: nothing of ours stands in for it
      const im = L.url ? await loadImg(L.url) : null;
      if (!im) continue;                                       // no picture for this area: nothing is drawn (the background carries the look)
      ctx.save(); seedPath(ctx, { ...L, ellipse: L.shape === "ellipse", radius: L.shape === "rounded" ? Math.min(L.w, L.h) * 0.08 : 0 }); ctx.clip();
      ctx.translate(L.x, L.y); coverDraw(ctx, im, L.w, L.h);
      ctx.restore();
    } else if (L.kind === "text") seedText(ctx, L);
  }
}
/** A free place for our logo: the reference's own logo slot, else the first corner (top-left, top-right, bottom-right, bottom-left) no text touches. */
function logoSlot(layout) {
  const own = layout.covers.find((c) => c.kind === "logo");
  if (own) return own;
  const w = 0.26, h = 0.05, m = 0.045;
  const corners = [{ x: m, y: m }, { x: 1 - m - w, y: m }, { x: 1 - m - w, y: 1 - m - h }, { x: m, y: 1 - m - h }];
  const hit = (a, e) => a.x < e.x + e.w && a.x + w > e.x && a.y < e.y + e.h && a.y + h > e.y;
  const free = corners.find((c) => !layout.elements.some((e) => e.type === "text" && e.text !== undefined && hit(c, e)));
  return { kind: "logo", ...(free || corners[0]), w, h };
}
/** Our logo, trimmed to its mark and fitted in its slot; white when what is under it is dark. Drawn last, so nothing can hide it. */
async function paintLogo(ctx, box) {
  const ink = await logoInk();
  if (!ink || !ink.im) return;
  const k = Math.min(box.w / ink.sw, box.h / ink.sh), w = ink.sw * k, h = ink.sh * k, x = box.x + (box.w - w) / 2, y = box.y + (box.h - h) / 2;
  let dark = false;
  try {
    const d = ctx.getImageData(Math.max(0, Math.floor(x)), Math.max(0, Math.floor(y)), Math.max(1, Math.ceil(w)), Math.max(1, Math.ceil(h))).data;
    let sum = 0, n = 0;
    for (let i = 0; i < d.length; i += 16) { sum += 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2]; n++; }
    dark = n > 0 && sum / n < 120;
  } catch (e) { dark = false; }
  if (!dark) { ctx.drawImage(ink.im, ink.sx, ink.sy, ink.sw, ink.sh, x, y, w, h); return; }
  const oc = document.createElement("canvas");
  oc.width = Math.max(1, Math.round(w)); oc.height = Math.max(1, Math.round(h));
  const o = oc.getContext("2d");
  o.drawImage(ink.im, ink.sx, ink.sy, ink.sw, ink.sh, 0, 0, oc.width, oc.height);
  o.globalCompositeOperation = "source-in"; o.fillStyle = "#FFFFFF"; o.fillRect(0, 0, oc.width, oc.height);
  ctx.drawImage(oc, x, y, w, h);
}
async function renderRefCard(spec) {
  const [W, H] = sizeOf(spec);
  const c = document.createElement("canvas"); c.width = W; c.height = H;
  const ctx = styleCtx(c.getContext("2d"), spec);
  try { await document.fonts.ready; } catch (e) { }
  const layout = normLayout(spec.layout);
  if (!layout) return { warn: ["The saved design has no usable layout."], y: 0 };
  const showLogo = spec.stream !== "linkedin" && !!LOGO;         // our logo on every ws.regulab card, never hidden; LinkedIn carries none
  const slot = showLogo ? logoSlot(layout) : null;
  const hasPhoto = layout.elements.some((e) => e.type === "photo");
  const words = wordsFromSpec(spec);
  const seedOpts = { width: W, height: H, pictureUrl: hasPhoto ? spec.bg || "" : "", logoUrl: "" };
  const { seed } = layoutToSeed(layout, words, seedOpts);
  ctx.fillStyle = (layout.background && layout.background.color) || "#fff"; ctx.fillRect(0, 0, W, H);
  await paintSeed(ctx, seed);
  if (slot) await paintLogo(ctx, { x: slot.x * W, y: slot.y * H, w: slot.w * W, h: slot.h * H });
  const warn = [];
  if (!words.headline) warn.push("The design needs a headline.");
  return { url: c.toDataURL("image/jpeg", 0.9), warn, y: 0 };
}

/* ---- MY DESIGNS (Wan, 4 Oct 2026: "create a default design to use for carousel, poster and single card, like ERA, Photo, Grid
   and Semasa. I need not fill any text: the design has the layout, and the text fills it when the idea comes in from the draft.
   Don't make it complicated."). A design is the same machinery as a look, saved with a name and no words:
     look      grid | era | photo: the family whose drawing and palette it uses
     cover / middle / closing / single    the template for each place a slide can have in a set ("" = auto, as the look would choose);
               `single` is a poster or a one-card post
     accent, paper    two colours that replace the family's accent and its paper ("" = the family's own)
     bg, scrim, mascot, eyebrow    the background token, how much it is covered, the character, the small label (all optional)
   Pure and tolerant: anything it does not recognise is dropped, so a bad entry can never stop a card being drawn. */
const HEX6 = /^#[0-9a-f]{6}$/i;
const POSITIONS = ["cover", "middle", "closing", "single"];
export function normDesign(d) {
  if (!d || typeof d !== "object") return null;
  const look = STUDIO_LOOKS.includes(d.look) ? d.look : null;
  if (!look) return null;
  const out = { look };
  for (const p of POSITIONS) {
    const k = String(d[p] || "");
    if (TEMPLATE_KEYS.includes(k) && k[0] === lookLetter(look)) out[p] = k;       // a template of another family would not match the palette
  }
  if (HEX6.test(d.accent || "")) out.accent = d.accent.toLowerCase();
  if (HEX6.test(d.paper || "")) out.paper = d.paper.toLowerCase();
  const bg = String(d.bg || "");
  if (bg && bg !== "none") out.bg = bg;
  if (/^(none|light|medium|heavy)$/.test(d.scrim || "")) out.scrim = d.scrim;
  if (/^(none|[a-z]{2,20})$/.test(d.mascot || "")) out.mascot = d.mascot;
  const eb = String(d.eyebrow || "").trim().slice(0, 80);
  if (eb) out.eyebrow = eb;
  if (d.layouts && typeof d.layouts === "object") {                 // a design made from a reference: one layout per place, or "main" for all
    const ls = {};
    for (const k of [...POSITIONS, "main"]) { const nl = normLayout(d.layouts[k]); if (nl) ls[k] = nl; }
    if (Object.keys(ls).length) out.layouts = ls;
  }
  return out;
}
/** Where a slide sits in its set, for the design's per-place template. */
export const placeOf = (i, n) => (n <= 1 ? "single" : i === 0 ? "cover" : i === n - 1 ? "closing" : "middle");

export function specsFor(slides, o = {}) {
  const D = normDesign(o.design);
  const look = D ? D.look : (STUDIO_LOOKS.includes(o.look) ? o.look : "grid");
  const list = (slides || []).filter((s) => s && (String(s.title || "").trim() || (s.points || []).length
    || String(s.lead || "").trim() || String(s.note || "").trim() || String(s.ayat || "").trim()));
  const n = list.length;
  const linkedin = o.stream === "linkedin";
  return list.map((s, i) => {
    const pts = (s.points || []).map((x) => String(x || "").trim()).filter(Boolean);
    if (String(s.ayat || "").trim()) {
      // a slide that names an ayat is the verse card, whatever the look, the design or the template chosen on it
      return { stream: linkedin ? "linkedin" : "regulab", template: "q_ayat", size: o.size || undefined,
        title: String(s.title || "").trim(), lead: String(s.lead || "").trim(), items: pts,
        footnote: String(s.footnote || "").trim() || (i === n - 1 ? String(o.citation || "").trim() : ""),
        ayat: { ref: String(s.ayat).trim(), label: String(s.ayat_label || ""), ar: String(s.ayat_ar || ""), tr: String(s.ayat_tr || ""), ed: String(s.ayat_ed || "") } };
    }
    const last = i === n - 1;
    const lead0 = String(s.lead || "").trim();
    const withLead = (x) => [lead0, x].filter(Boolean).join("\n");
    const cite = String(o.citation || "").trim();
    const base = {
      stream: linkedin ? "linkedin" : "regulab",
      title: String(s.title || "").trim(),
      eyebrow: String(s.eyebrow || o.eyebrow || (D && D.eyebrow) || "").trim(),
      footnote: String(s.footnote || "").trim() || (last ? cite : ""),
      chip_label: String(s.chip || "").trim() || (last && cite ? (linkedin ? "Source" : "Sumber") : ""),
      note: String(s.note || "").trim(),
      bg: s.bg === "none" ? "" : (s.bg_url || o.bg || ""),
      scrim: s.scrim || (D && D.scrim) || (linkedin ? "heavy" : "medium"),
      auto_scrim: !s.scrim && !(D && D.scrim),
      palette: D && (D.accent || D.paper) ? { accent: D.accent, paper: D.paper } : undefined,
      // the event poster's speaker photos, one per point in order, already resolved to drawable addresses ("" = initials)
      avatars: Array.isArray(s.photo_urls) && s.photo_urls.some(Boolean) ? s.photo_urls : undefined,
      size: o.size || undefined,
      // SEMASA: the slide's own typography and character placement; absent = the template decides
      type_size: Number(s.type_size) || undefined,
      font: FONT_CHOICES.includes(s.font) ? s.font : undefined,
      mascot_pos: MASCOT_POS.includes(s.mascot_pos) ? s.mascot_pos : undefined,
      mascot_size: Number(s.mascot_size) || undefined,
    };
    let spec;
    // THE FRONT PAGE: a carousel in the Image, Info ERA or Hand-drawn look opens with a poster cover (see SKINS), unless the
    // slide chose its own template or a saved design names one. Info ERA's is in ERA's own dress (SKINS.kraft)
    const posterCover = i === 0 && n > 1 && !(s.template && TEMPLATE_KEYS.includes(s.template)) && !D ? POSTER_COVER[look] : "";
    const place = placeOf(i, n), refLayout = D && D.layouts && (D.layouts[place] || D.layouts.main || D.layouts.middle || D.layouts.cover || D.layouts.single);
    if (refLayout && !(s.template && TEMPLATE_KEYS.includes(s.template))) {
      // a design from a reference: every slide without a template of its own is drawn in that layout, the words poured in
      return { ...base, template: "c_ref", layout: refLayout, lead: lead0, items: pts, palette: undefined };
    }
    const chosen = s.template && TEMPLATE_KEYS.includes(s.template) ? s.template
      : (D && D[placeOf(i, n)]) || (o.fit ? fitTemplate(look, s, i, n, pts) : "");
    if (posterCover) {
      spec = { ...base, template: posterCover, lead: lead0, items: pts, ...(look === "era" ? { skin: "kraft" } : {}) };
    } else if (chosen) {
      spec = { ...base, template: chosen, lead: lead0, items: pts };
    } else if (look === "grid") {
      spec = { ...base, template: "g_title", lead: withLead(asLines(pts)) };
    } else if (look === "image") {
      // a cover with a picture is the poster; one without is the calm title. Middle slides are notes (words) or steps (a picture to show).
      // every point is kept: the painter turns a short figure into the stat pill and draws the rest as lines
      const tpl = (i === 0 || n === 1) ? (base.bg ? "i_hero" : "i_title") : last ? "i_title" : "i_note";
      spec = { ...base, template: tpl, lead: lead0, items: pts };
    } else if (look === "era") {
      if (i === 0 && n > 1 && pts.length <= 4) spec = { ...base, template: "e_hook", lead: lead0 || pts[0] || "", items: lead0 ? pts : pts.slice(1) };
      else if (pts.length && pts.length <= 3) spec = { ...base, template: "e_explain", lead: lead0, items: pts };
      else spec = { ...base, template: "e_explain", lead: withLead(asLines(pts)) };
    } else if (look === "hand") {
      // the hand-drawn family: a lone card is the poster; a carousel cover is the hero, middle slides are notes.
      const tpl = n === 1 ? "h_poster" : (i === 0 ? "h_hero" : "h_note");
      spec = { ...base, template: tpl, lead: lead0, items: pts };
    } else if (SKIN_LOOKS.includes(look)) {
      // the four poster looks: cover, points, comparison, recommendation or closing, by place and by what the points look like
      spec = { ...base, template: skinTemplate(look, s, i, n, pts), lead: lead0, items: pts };
    } else if (i === 0 || n === 1) spec = { ...base, template: "p_title", lead: withLead(asLines(pts)) };
    else if (last) spec = { ...base, template: "p_quote", lead: withLead(asLines(pts)) };
    else if (pts.length && pts.length <= 4) spec = { ...base, template: "p_fact", lead: lead0, items: pts };
    else spec = { ...base, template: "p_fact", lead: withLead(asLines(pts)) };
    const mascot = mascotUrl(D && D.mascot && !s.mascot ? { ...s, mascot: D.mascot } : s, spec.template, o.mascots);
    if (mascot) spec.mascot = mascot;
    /* The ERA hook slide was built round its character: the questions float between the headline and the figure. With no
       character (16 Nov 2026) that is a headline, two stickers and a bare card, so a hook slide chosen by hand or named by a
       saved design is drawn as the poster front page in ERA's dress, the same one an Info ERA carousel opens with. */
    if (spec.template === "e_hook" && !spec.mascot) { spec.template = "m_cover"; spec.skin = "kraft"; }
    return spec;
  });
}

/* ===================== AYAT AL-QURAN =====================================
   Wan, 16 Nov 2026: "make sure can write ayat al-Quran for reminder or under fatwa". A slide that names a verse (`ayat`,
   "2:168") is drawn as this card whatever the look of the set: the Arabic in a Quran face (Amiri Quran, the only Arabic face
   the cards carry), its translation, and the reference.
   THE WORDS ARE NEVER THIS FILE'S AND NEVER A WRITER'S: `ayat_ar` and `ayat_tr` are fetched from a published source
   (lib/quran.js on the page, backend/semasa/quran.py in the worker) and drawn exactly as fetched. So nothing here may alter
   them: no stripEmph, no capitals, no ellipsis, no slicing, and above all no hardSplit. An Arabic word is never cut (cutting
   one breaks the joins between its letters and can change what it reads as), and a pause mark never starts a line. A verse
   that does not fit at the smallest size is refused with the usual "fuller than the card" warning, never trimmed.
   Each ayat ends with its number in the end-of-ayat sign, as a mushaf prints it; the number comes from the reference.
   A slide whose verse has not been fetched draws the reference alone and warns, so the worker refuses it. */
const AYAT_FACE = '"Amiri Quran", "Scheherazade New", "Traditional Arabic", serif';
const AYAT_PAL = { paper: "#F7F2E6", ink: "#17251E", muted: "#5B645D", green: "#1F5C45", gold: "#B08A2E" };
/* the translation's credit, by edition: the same words as rules/compliance.json quran.editions (a test holds them equal) */
export const AYAT_CREDIT = { "ms.basmeih": "Terjemahan: Abdullah Basmeih, Tafsir Pimpinan Ar-Rahman", "en.sahih": "Translation: Saheeh International" };
export const AYAT_MIN = 0.65, AYAT_MAX = 1.5;
const AYAT_PAUSE = /^[ؕ-ؚۖ-ۭ]+$/;
const ayatDigits = (n) => String(n).replace(/\d/g, (d) => String.fromCharCode(0x0660 + Number(d)));
/** The ayat of a slide as the lines a mushaf would set: each one followed by its number in the end-of-ayat sign. */
function ayatArabic(ayat) {
  const m = /^(\d{1,3}):(\d{1,3})(?:-(\d{1,3}))?$/.exec(String(ayat.ref || ""));
  const first = m ? Number(m[2]) : 0;
  return String(ayat.ar || "").split("\n").map((x) => x.trim()).filter(Boolean)
    .map((x, i) => (first ? x + " ۝" + ayatDigits(first + i) : x)).join(" ");
}
/* Whole words only, right to left. A pause mark (a small letter above the line, written as a word of its own) stays with
   the word before it; a word wider than the column is left on a line by itself and the caller makes the type smaller. */
function ayatWrap(ctx, text, maxW) {
  const units = [];
  for (const t of String(text).split(/ +/).filter(Boolean)) {
    if (units.length && AYAT_PAUSE.test(t)) units[units.length - 1] += " " + t; else units.push(t);
  }
  const lines = []; let line = "", over = false;
  for (const w of units) {
    const next = line ? line + " " + w : w;
    if (line && ctx.measureText(next).width > maxW) { lines.push(line); line = w; } else line = next;
    if (ctx.measureText(w).width > maxW) over = true;
  }
  if (line) lines.push(line);
  return { lines, over };
}
function ayatStar(ctx, cx, cy, r, colour) {
  ctx.save(); ctx.translate(cx, cy); ctx.fillStyle = colour;
  for (let k = 0; k < 2; k++) { ctx.fillRect(-r * 0.72, -r * 0.72, r * 1.44, r * 1.44); ctx.rotate(Math.PI / 4); }
  ctx.fillStyle = AYAT_PAL.paper; ctx.beginPath(); ctx.arc(0, 0, r * 0.34, 0, Math.PI * 2); ctx.fill();
  ctx.restore();
}
async function renderAyatCard(spec) {
  const [W, H] = sizeOf(spec);
  const c = document.createElement("canvas"); c.width = W; c.height = H;
  const ctx = c.getContext("2d");                 // never styleCtx: a slide's own face must not replace the Quran face
  try { await document.fonts.ready; } catch (e) { }
  const warn = [], u = W / 1080, A = spec.ayat || {};
  const english = spec.stream === "linkedin";
  const frame = Math.round(40 * u), M = Math.round(96 * u), colW = W - M * 2;
  // the ground and its frame
  ctx.fillStyle = AYAT_PAL.paper; ctx.fillRect(0, 0, W, H);
  ctx.strokeStyle = AYAT_PAL.gold; ctx.lineWidth = Math.max(2, Math.round(3 * u));
  ctx.strokeRect(frame, frame, W - frame * 2, H - frame * 2);
  ctx.lineWidth = Math.max(1, Math.round(1 * u));
  ctx.strokeRect(frame + Math.round(12 * u), frame + Math.round(12 * u), W - (frame + Math.round(12 * u)) * 2, H - (frame + Math.round(12 * u)) * 2);
  for (const [x, y] of [[frame, frame], [W - frame, frame], [frame, H - frame], [W - frame, H - frame]]) ayatStar(ctx, x, y, Math.round(15 * u), AYAT_PAL.gold);
  await drawBrandMark(ctx, spec, W, u, M, { top: 82, h: 30, textFill: "rgba(23,37,30,.55)" });
  // the foot: whose translation it is, and the post's source when this is the slide that carries it
  const credit = AYAT_CREDIT[String(A.ed || "").split("@")[0]] || "";
  const source = stripEmph(spec.footnote || "").trim();
  const footLines = [];
  ctx.font = "500 " + Math.round(21 * u) + "px " + G_BODY;
  if (A.ar && A.tr && credit) footLines.push(...gWrap(ctx, credit, colW));
  if (source) footLines.push(...gWrap(ctx, (english ? "Source: " : "Sumber: ") + source, colW));
  const footLh = Math.round(30 * u), footTop = H - frame - Math.round(46 * u) - footLines.length * footLh;
  ctx.fillStyle = AYAT_PAL.muted; ctx.textAlign = "center"; ctx.textBaseline = "top";
  footLines.forEach((l, i) => ctx.fillText(l, W / 2, footTop + i * footLh));
  // the words, laid out at scale f: [draw(y) -> y]
  const top = Math.round(170 * u), bottom = footTop - Math.round(34 * u), room = bottom - top;
  const heading = stripEmph(spec.title || "").trim().toUpperCase();
  const ref = A.label ? "Surah " + A.label : String(A.ref || "");
  const notes = [spec.lead, ...(spec.items || [])].map((x) => stripEmph(x).trim()).filter(Boolean);
  const arabic = A.ar && A.tr ? ayatArabic(A) : "", translation = A.ar && A.tr ? String(A.tr).split("\n").map((x) => x.trim()).filter(Boolean).join(" ") : "";
  const layout = (f) => {
    const steps = []; let h = 0, fits = true;
    const add = (height, draw) => { steps.push([h, draw]); h += height; };
    const gap = (n) => { h += Math.round(n * u * f); };
    add(Math.round(40 * u), (y) => ayatStar(ctx, W / 2, y + Math.round(20 * u), Math.round(17 * u), AYAT_PAL.green));
    gap(18);
    if (heading) {
      const px = Math.round(27 * u * Math.min(f, 1.15)), lh = Math.round(px * 1.4);
      ctx.font = "700 " + px + "px " + G_HEAD; try { ctx.letterSpacing = Math.round(px * 0.16) + "px"; } catch (e) { }
      const lines = gWrap(ctx, heading, colW); try { ctx.letterSpacing = "0px"; } catch (e) { }
      add(lines.length * lh, (y) => {
        ctx.font = "700 " + px + "px " + G_HEAD; ctx.fillStyle = AYAT_PAL.green; ctx.textAlign = "center"; ctx.textBaseline = "top"; ctx.direction = "ltr";
        try { ctx.letterSpacing = Math.round(px * 0.16) + "px"; } catch (e) { }
        lines.forEach((l, i) => ctx.fillText(l, W / 2, y + i * lh));
        try { ctx.letterSpacing = "0px"; } catch (e) { }
      });
      gap(26);
    }
    if (arabic) {
      const px = Math.round(60 * u * f), lh = Math.round(px * 2.05);
      ctx.font = "400 " + px + "px " + AYAT_FACE; ctx.direction = "rtl";
      const w = ayatWrap(ctx, arabic, colW); ctx.direction = "ltr";
      if (w.over) fits = false;
      add(w.lines.length * lh, (y) => {
        ctx.font = "400 " + px + "px " + AYAT_FACE; ctx.fillStyle = AYAT_PAL.ink; ctx.direction = "rtl"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
        w.lines.forEach((l, i) => ctx.fillText(l, W / 2, y + i * lh + lh / 2));
        ctx.direction = "ltr";
      });
      gap(22);
      add(Math.round(14 * u), (y) => {
        ctx.strokeStyle = AYAT_PAL.gold; ctx.lineWidth = Math.max(1, Math.round(2 * u));
        const half = Math.round(110 * u), my = y + Math.round(7 * u);
        ctx.beginPath(); ctx.moveTo(W / 2 - half, my); ctx.lineTo(W / 2 - Math.round(16 * u), my); ctx.moveTo(W / 2 + Math.round(16 * u), my); ctx.lineTo(W / 2 + half, my); ctx.stroke();
        ctx.save(); ctx.translate(W / 2, my); ctx.rotate(Math.PI / 4); ctx.fillStyle = AYAT_PAL.gold; const d = Math.round(6 * u); ctx.fillRect(-d, -d, d * 2, d * 2); ctx.restore();
      });
      gap(26);
      const tpx = Math.round(33 * u * f), tlh = Math.round(tpx * 1.5);
      ctx.font = "500 " + tpx + "px " + G_BODY;
      const tl = gWrap(ctx, "“" + translation + "”", colW);
      add(tl.length * tlh, (y) => {
        ctx.font = "500 " + tpx + "px " + G_BODY; ctx.fillStyle = AYAT_PAL.ink; ctx.textAlign = "center"; ctx.textBaseline = "top";
        tl.forEach((l, i) => ctx.fillText(l, W / 2, y + i * tlh));
      });
      gap(24);
    }
    {
      const px = Math.round(30 * u * Math.min(f, 1.2)), lh = Math.round(px * 1.35);
      ctx.font = "700 " + px + "px " + G_HEAD;
      const lines = gWrap(ctx, ref, colW);
      add(lines.length * lh, (y) => {
        ctx.font = "700 " + px + "px " + G_HEAD; ctx.fillStyle = AYAT_PAL.green; ctx.textAlign = "center"; ctx.textBaseline = "top";
        lines.forEach((l, i) => ctx.fillText(l, W / 2, y + i * lh));
      });
    }
    if (!arabic) {
      gap(20);
      const px = Math.round(26 * u), lh = Math.round(px * 1.45);
      ctx.font = "500 " + px + "px " + G_BODY;
      const lines = gWrap(ctx, english ? "The verse has not been fetched yet." : "Teks ayat belum diambil.", colW);
      add(lines.length * lh, (y) => { ctx.font = "500 " + px + "px " + G_BODY; ctx.fillStyle = AYAT_PAL.muted; ctx.textAlign = "center"; ctx.textBaseline = "top"; lines.forEach((l, i) => ctx.fillText(l, W / 2, y + i * lh)); });
    }
    if (notes.length) {
      gap(26);
      const px = Math.round(27 * u * Math.min(f, 1.1)), lh = Math.round(px * 1.5);
      ctx.font = "500 " + px + "px " + G_BODY;
      const lines = notes.flatMap((nn) => gWrap(ctx, nn, colW));
      add(lines.length * lh, (y) => { ctx.font = "500 " + px + "px " + G_BODY; ctx.fillStyle = AYAT_PAL.muted; ctx.textAlign = "center"; ctx.textBaseline = "top"; lines.forEach((l, i) => ctx.fillText(l, W / 2, y + i * lh)); });
    }
    return { steps, h, fits };
  };
  // the largest size at which everything fits; a verse that does not fit at the smallest is refused, never trimmed
  let L = null;
  for (let f = AYAT_MAX; f >= AYAT_MIN - 1e-6; f -= 0.05) { L = layout(Math.round(f * 100) / 100); if (L.fits && L.h <= room) break; }
  if (!L.fits || L.h > room) warn.push(FULL + ": this verse is too long for one card. Use fewer ayat, or remove the lines under it.");
  if (!arabic) warn.push("The verse text has not been fetched: press Ambil ayat. A verse is never typed.");
  const y0 = top + Math.max(0, Math.round((room - L.h) / 2));
  for (const [dy, draw] of L.steps) draw(y0 + dy);
  ctx.direction = "ltr"; ctx.textAlign = "left"; ctx.textBaseline = "alphabetic";
  return { url: c.toDataURL("image/jpeg", 0.92), warn, y: y0 + L.h };
}

/* A design's two colours replace the family's accent and paper while ONE card is drawn. The palettes are shared constants, so every
   render waits its turn (the page previews several looks at once) and the originals are put back in a `finally`: a card in another
   look, or a failed one, can never inherit someone else's colours. */
let _renderTurn = Promise.resolve();
function renderSpec(spec) {
  const run = async () => {
    if (spec.template === "q_ayat") return renderAyatCard(spec);      // the verse card is the same in every look and design
    const p = spec.palette;
    if (!p) return renderSpecNow(spec);
    const keep = { go: GRID_PAL.orange, gc: GRID_PAL.cream, er: ERA_PAL.red, ep: ERA_PAL.paper };
    if (p.accent) { GRID_PAL.orange = p.accent; ERA_PAL.red = p.accent; }
    if (p.paper) { GRID_PAL.cream = p.paper; ERA_PAL.paper = p.paper; }
    try { return await renderSpecNow(spec); } finally { GRID_PAL.orange = keep.go; GRID_PAL.cream = keep.gc; ERA_PAL.red = keep.er; ERA_PAL.paper = keep.ep; }
  };
  const next = _renderTurn.then(run, run);
  _renderTurn = next.catch(() => null);
  return next;
}
async function renderSpecNow(spec) {
  if (spec.bg && spec.template[0] !== "p" && spec.template[0] !== "i" && spec.template[0] !== "h" && !SKIN_TPL[spec.template] && await groundIsLight(spec)) spec = { ...spec, scrim: "none", _light: true };
  if (spec.template === "c_ref") return renderRefCard(spec);
  if (MORE_TPL[spec.template]) return renderMoreCard(spec);
  if (GRID_TPL[spec.template]) return renderGridCard(spec);
  if (ERA_TPL[spec.template]) return renderEraCard(spec);
  if (PHOTO_TPL[spec.template]) return renderPhotoCard(spec);
  if (PIC_TPL[spec.template]) return renderPicCard(spec);
  if (HAND_TPL[spec.template]) return renderHandCard(spec);
  if (SKIN_TPL[spec.template]) return renderSkinCard(spec);
  throw new Error("unknown card template " + spec.template);
}

/* Draw every slide. Returns [{url (a JPEG data URL), warn[], template}], one per slide, in order. A warning is
   Studio's own "fuller than the card" or "no picture chosen": the page shows it, the worker refuses to ship it. */
export async function renderSlides(slides, o = {}) {
  const out = [];
  for (const spec of specsFor(slides, o)) {
    const r = await renderSpec(spec);
    out.push({ url: r.url, warn: fullWarnFixed(spec, r), template: spec.template });
  }
  return out;
}

/* Studio's "fuller than the card" test is one line for every template: the words end below H - 150u. Photo · Title
   puts its headline LOW on purpose (bottom-anchored over the photograph, drawn to end at H - M - reserve), so that
   test fires on every Photo · Title card, however short (Studio shows it and lets it through). Here a warning
   stops the render, so for that one template the real limit is used: the block overflows only when it runs past
   its own anchor, which happens when a long headline was pushed up against the top clamp. */
const FULL = "The slide is fuller than the card";
function fullWarnFixed(spec, r) {
  const warn = r.warn || [];
  if (spec.template !== "p_title" || typeof r.y !== "number") return warn;
  const [W, H] = sizeOf(spec), u = W / 1080, M = Math.round(74 * u);
  const reserve = Math.round((spec.footnote || spec.chip_label ? 96 : 46) * u);
  if (r.y <= H - M - reserve + 1) return warn.filter((w) => !String(w).startsWith(FULL));
  return warn;
}

/* The faces Studio's cards use. The canvas only draws with a face that is already LOADED, and nothing in the DOM
   uses these, so each is asked for by name; the sample text covers latin and latin-ext (ā, ş, ı ...). */
const FACES = ["600 20px Poppins", "700 20px Poppins", "800 20px Poppins", '400 20px Anton', '700 20px "Playfair Display"', '800 20px "Playfair Display"',
  '400 20px "Instrument Sans"', '500 20px "Instrument Sans"', '600 20px "Instrument Sans"',
  '400 20px "JetBrains Mono"', '500 20px "JetBrains Mono"', "700 20px Caveat",
  '400 20px "Permanent Marker"', '400 20px "Open Sans"', '700 20px "Open Sans"', '800 20px "Open Sans"'];
/* the Quran face is Arabic only, so it is asked for and checked with Arabic letters: "Aa" would never load its file */
const AYAT_FACES = ['400 20px "Amiri Quran"'], AYAT_SAMPLE = "\u0628\u0633\u0645 \u0627\u0644\u0644\u0647";
let _fonts = null;
export function ensureFonts(base = "") {
  if (_fonts) return _fonts;
  _fonts = (async () => {
    // fonts.css: the Studio faces; fragrance-fonts.css: Anton and Playfair, which a design made from a reference may ask for
    for (const css of ["fonts.css", "fragrance-fonts.css"]) {
      if (document.querySelector(`link[data-studio-cards="${css}"]`)) continue;
      const link = document.createElement("link");
      link.rel = "stylesheet"; link.href = base + css; link.dataset.studioCards = css;
      await new Promise((res) => { link.onload = res; link.onerror = res; document.head.appendChild(link); });
    }
    await Promise.all(FACES.map((f) => document.fonts.load(f, "Aa āşı 1–2").catch(() => null)));
    await Promise.all(AYAT_FACES.map((f) => document.fonts.load(f, AYAT_SAMPLE).catch(() => null)));
    const missing = FACES.filter((f) => !document.fonts.check(f, "Aa")).concat(AYAT_FACES.filter((f) => !document.fonts.check(f, AYAT_SAMPLE)));
    return { missing };
  })();
  return _fonts;
}

if (typeof window !== "undefined") window.SemasaCards = { LOOKS, specsFor, renderSlides, ensureFonts, setLogo };
