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

/* SEMASA: set by setLogo(); Studio pasted its logo in here at build time. */
let LOGO = "";
export function setLogo(src) { LOGO = src || ""; _logoInk = null; }
/* SEMASA: Studio sized every card by stream; the Design tab also draws a 4:5 poster and a 9:16 story. */
function sizeOf(spec) {
  if (Array.isArray(spec.size) && spec.size.length === 2) return [spec.size[0], spec.size[1]];
  return CARD_SIZES[spec.stream === "linkedin" ? "linkedin" : "regulab"];
}

/* ======================= COPIED FROM STUDIO (begin) ======================= */
/* ---------- card templates: rendered in-page to a real PNG ---------- */
const CARD_SIZES = { regulab: [1080, 1080], linkedin: [1080, 1350] };

const GRID_TPL = { g_title: 1, g_stat: 1, g_bars: 1, g_rows: 1, g_table: 1 };
const GRID_DARK = { g_stat: 1, g_table: 1 };
const ERA_TPL = { e_hook: 1, e_explain: 1, e_flow: 1, e_vs: 1 };
const PHOTO_TPL = { p_title: 1, p_fact: 1, p_quote: 1 };
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
];
function groupOf(tpl) { return ERA_TPL[tpl] ? "era" : PHOTO_TPL[tpl] ? "photo" : "grid"; }
function groupDef(k) { return CARD_GROUPS.find(g => g.k === k) || CARD_GROUPS[0]; }

/* Which templates can carry the character. g_table stays "no character" -- it is the dark
   structured data table the reference prompt itself never puts one on. g_stat joined the
   rest on 19 Sep 2026 (Wan: "for dark slide adapt the mascot") for its advice/hint branch
   only (no figure given -- see the giant-number branch in renderGridCard, which still gets
   no character, since a mascot has nothing to point at there). */
const MASCOT_TPL = { g_title: 1, g_bars: 1, g_rows: 1, g_stat: 1, e_hook: 1, e_explain: 1, e_vs: 1 };
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
  const h = Math.round((o.h || 34) * u), w = Math.round(h * (ink.sw / ink.sh));
  if (o.knockout) {
    const oc = document.createElement("canvas");
    oc.width = Math.max(1, w); oc.height = Math.max(1, h);
    const octx = oc.getContext("2d");
    octx.drawImage(ink.im, ink.sx, ink.sy, ink.sw, ink.sh, 0, 0, w, h);
    octx.globalCompositeOperation = "source-in";
    octx.fillStyle = "#FFFFFF"; octx.fillRect(0, 0, w, h);
    ctx.save();
    ctx.shadowColor = "rgba(0,0,0,.45)"; ctx.shadowBlur = Math.round(10 * u);
    ctx.drawImage(oc, M, top, w, h);
    ctx.restore();
  } else {
    ctx.drawImage(ink.im, ink.sx, ink.sy, ink.sw, ink.sh, M, top, w, h);
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
async function drawGround(ctx, spec, W, H) {
  if (!spec || !spec.bg) return false;
  let img = null;
  try { img = await loadImg(spec.bg); } catch (e) { return false; }
  if (!img) return false;
  coverDraw(ctx, img, W, H);
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
function gEyebrow(ctx, text, x, y, colour, px) {
  if (!text) return y;
  ctx.save(); ctx.font = "700 " + px + "px " + G_HEAD;
  try { ctx.letterSpacing = Math.round(px * 0.17) + "px"; } catch (e) { }
  ctx.fillStyle = colour; ctx.textBaseline = "top";
  ctx.fillText(stripEmph(text).toUpperCase(), x, y); ctx.restore();
  return y + Math.round(px * 2.2);
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
    set(t, k, v) { try { t[k] = v; } catch (e) { } return true; },
  });
}
/* Where the words sit between the handle at the top and the source line pinned to the
   bottom margin. Both are drawn outside the content block and must not be centred into. */
function cardZone(H, u, topU) {
  return { top: Math.round((topU || 150) * u), bottom: H - Math.round(150 * u) };
}
function centreShift(H, u, contentEndY, topU) {
  const z = cardZone(H, u, topU);
  const slack = (z.bottom - z.top) - Math.max(0, contentEndY - z.top);
  /* Never pull content upward past its own start, and never centre a block that already
     fills the card -- a negative shift would push the last line under the source line. */
  return slack > 0 ? Math.round(slack / 2) : 0;
}
async function renderGridCard(spec) {
  const [W, H] = sizeOf(spec);
  const c = document.createElement("canvas"); c.width = W; c.height = H;
  const ctx = c.getContext("2d");
  try { await document.fonts.ready; } catch (e) { }
  const u = W / 1080;
  /* Wan, 19 Sep 2026: "make sure the design and render ensure the text is middle of card".
     The type scale is fixed on purpose (a short lead must not grow the headline), so a
     slide with little text used to sit high with a dead band beneath it. Measuring first
     and shifting the whole block keeps every size exactly as it is and moves the words. */
  const probe = await gridCardPaint(measureProxy(ctx), spec, W, H, 0);
  return gridCardPaint(ctx, spec, W, H, centreShift(H, u, probe.y), c);
}
async function gridCardPaint(ctx, spec, W, H, yShift, canvasOut) {
  const warn = [];
  const t = spec.template;
  const dark = !!GRID_DARK[t] || !!(spec && spec.bg);   // a photograph is always a dark card
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
     grows the headline to fill it. g_stat's giant figure and its own subhead stay a
     deliberately separate, smaller tier: they are numerals, not the slide's headline. */
  const HEAD_PX = Math.round(80 * u), HEAD_LH = Math.round(90 * u);
  const LEAD_PX = Math.round(34 * u), LEAD_LH = Math.round(48 * u);
  const ITEM_HEAD_PX = Math.round(36 * u), ITEM_BODY_PX = Math.round(30 * u), ITEM_BODY_LH = Math.round(40 * u);

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
  const mascotMh = mascot ? Math.round(H * 0.30) : 0;
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
    if (spec.note) y = Math.max(y, gBubble(ctx, bubbleX, afterY + Math.round(24 * u), Math.round(470 * u), spec.note, Math.round(30 * u)));
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
      if (spec.note) y = Math.max(y, gBubble(ctx, bubbleX, statAfterY + Math.round(24 * u), Math.round(470 * u), spec.note, Math.round(30 * u)));
    } else {
      const figure = items[0] || spec.title || "";
      const unit = items[1] || "";
      ctx.font = "800 " + Math.round(300 * u) + "px " + G_HEAD; ctx.textBaseline = "top";
      ctx.fillStyle = ink; ctx.fillText(figure, M, y);
      const fw = ctx.measureText(figure).width;
      if (unit) {
        ctx.font = "700 " + Math.round(54 * u) + "px " + G_HEAD; ctx.fillStyle = accent;
        ctx.fillText(unit, M + fw + Math.round(28 * u), y + Math.round(150 * u));
      }
      y += Math.round(330 * u);
      /* This subhead sits under a giant numeral -- a deliberately smaller tier than the
         carousel's main headline, the same way it was before standardisation; only the
         body text below it joins the shared LEAD size. */
      if (spec.title) y = gHeadline(ctx, spec.title, M, y, maxW, Math.round(58 * u), Math.round(70 * u), ink, accent);
      y += Math.round(34 * u);
      if (spec.lead) y = gPara(ctx, spec.lead, M, y, Math.round(maxW * 0.95), LEAD_PX, LEAD_LH, muted);
      gSparks(ctx, W - Math.round(84 * u), Math.round(220 * u), 3, accent, Math.round(22 * u), Math.round(26 * u));
    }
  } else if (t === "g_bars") {
    y = gHeadline(ctx, spec.title || "", M, y, headW, HEAD_PX, HEAD_LH, ink, accent);
    y += Math.round(18 * u);
    if (spec.lead) { ctx.font = "700 " + Math.round(40 * u) + "px " + G_MARK; ctx.fillStyle = muted; ctx.textBaseline = "top"; ctx.fillText(spec.lead, M, y); y += Math.round(60 * u); }
    /* A mascot plus a speech bubble both eat vertical room a bar chart doesn't have to
       spare -- fewer rows, not smaller type (Wan's rule: no font-size change to make
       things fit). A note on top of both is one row too many. */
    const rows = items.slice(0, 5).map(l => { const c2 = gCells(l); return { label: c2[0] || "", v: parseFloat(c2[1]) || 0, show: c2[2] || c2[1] || "" }; });
    const max = Math.max(1e-9, ...rows.map(r => r.v));
    const rowH = Math.round(104 * u), padY = Math.round(50 * u);
    const barsW = maxW;
    gPanel(ctx, M, y, barsW, rows.length * rowH + padY);
    let by = y + Math.round(38 * u);
    const trackX = M + Math.round(38 * u), trackW = Math.round(barsW * 0.72);
    rows.forEach((r, i) => {
      ctx.font = "600 " + ITEM_BODY_PX + "px " + G_BODY; ctx.fillStyle = GRID_PAL.ink; ctx.textBaseline = "top";
      ctx.fillText(r.label, trackX, by);
      const bh = Math.round(26 * u);
      ctx.fillStyle = "#EDE6D6"; gRound(ctx, trackX, by + Math.round(44 * u), trackW, bh, bh / 2); ctx.fill();
      ctx.fillStyle = i === 0 ? accent : "#2A2E34";
      gRound(ctx, trackX, by + Math.round(44 * u), Math.max(bh, (r.v / max) * trackW), bh, bh / 2); ctx.fill();
      ctx.font = "700 " + ITEM_BODY_PX + "px " + G_HEAD; ctx.fillStyle = GRID_PAL.ink;
      ctx.textAlign = "right"; ctx.fillText(r.show, M + barsW - Math.round(38 * u), by + Math.round(40 * u)); ctx.textAlign = "left";
      by += rowH;
    });
    y += rows.length * rowH + padY + Math.round(32 * u);
    const barsAfterY = y;
    drawMascot(barsAfterY);
    if (spec.note) y = Math.max(y, gBubble(ctx, bubbleX, barsAfterY + Math.round(24 * u), Math.round(470 * u), spec.note, Math.round(30 * u)));
  } else if (t === "g_rows") {
    y = gHeadline(ctx, spec.title || "", M, y, headW, HEAD_PX, HEAD_LH, ink, accent);
    y += Math.round(30 * u);
    /* Same reasoning as g_bars above -- a mascot plus a speech bubble need the room a
       fourth panel would take, so the row count gives way, not the type size. */
    const rows = items.slice(0, 4).map(gCells);
    const rowH = Math.round(168 * u), gap = Math.round(28 * u);
    const rowsW = maxW;
    rows.forEach((r, i) => {
      gPanel(ctx, M, y, rowsW, rowH);
      ctx.font = "800 " + Math.round(44 * u) + "px " + G_HEAD; ctx.fillStyle = accent; ctx.textBaseline = "top";
      ctx.fillText(String(i + 1), M + Math.round(38 * u), y + Math.round(54 * u));
      ctx.font = "700 " + ITEM_HEAD_PX + "px " + G_HEAD; ctx.fillStyle = GRID_PAL.ink;
      ctx.fillText(r[0] || "", M + Math.round(110 * u), y + Math.round(38 * u));
      if (r[1]) gPara(ctx, r[1], M + Math.round(110 * u), y + Math.round(90 * u), rowsW - Math.round(160 * u), ITEM_BODY_PX, ITEM_BODY_LH, GRID_PAL.muted);
      y += rowH + gap;
    });
    const rowsAfterY = y;
    drawMascot(rowsAfterY);
    /* The footer row is clamped inside the card. A sticky note is taller than a chip and
       the square ws.regulab card is 270px shorter than the LinkedIn one, so on three rows
       it ran off the bottom edge before this. A mascot takes the sticky note's usual
       corner, so with one placed the note becomes a speech bubble at the mascot's side
       instead (Wan's reference prompt: "pointing with bubble speech"). */
    const fy = Math.min(y + Math.round(6 * u), H - M - Math.round(150 * u));
    if (spec.note && mascot) y = Math.max(y, gBubble(ctx, bubbleX, rowsAfterY + Math.round(6 * u), Math.round(470 * u), spec.note, Math.round(30 * u)));
    else if (spec.note) gSticky(ctx, W - M - Math.round(410 * u), fy, Math.round(410 * u), spec.note, GRID_PAL.yellow, 0.03, Math.round(46 * u));
  } else if (t === "g_table") {
    y = gHeadline(ctx, spec.title || "", M, y, maxW, HEAD_PX, HEAD_LH, ink, accent);
    y += Math.round(40 * u);
    const rows = items.slice(0, 5).map(gCells);
    const rowH = Math.round(128 * u);
    gPanel(ctx, M, y, maxW, rows.length * rowH + Math.round(40 * u), { fill: "rgba(255,255,255,.055)", shadow: false, stroke: "rgba(255,255,255,.12)" });
    let ry = y + Math.round(34 * u);
    rows.forEach((r, i) => {
      ctx.textBaseline = "top";
      ctx.font = "500 " + Math.round(28 * u) + "px " + G_MONO; ctx.fillStyle = accent;
      ctx.fillText(r[0] || "", M + Math.round(42 * u), ry + Math.round(6 * u));
      ctx.font = "700 " + Math.round(34 * u) + "px " + G_HEAD; ctx.fillStyle = "#fff";
      ctx.fillText(r[1] || "", M + Math.round(126 * u), ry);
      if (r[2]) gPara(ctx, r[2], M + Math.round(126 * u), ry + Math.round(48 * u), maxW - Math.round(180 * u), Math.round(27 * u), Math.round(36 * u), "rgba(255,255,255,.6)");
      if (i < rows.length - 1) {
        ctx.save(); ctx.strokeStyle = "rgba(255,255,255,.12)"; ctx.lineWidth = 2; ctx.setLineDash([8, 8]);
        ctx.beginPath(); ctx.moveTo(M + Math.round(42 * u), ry + Math.round(108 * u)); ctx.lineTo(W - M - Math.round(42 * u), ry + Math.round(108 * u)); ctx.stroke(); ctx.restore();
      }
      ry += rowH;
    });
    y += rows.length * rowH + Math.round(80 * u);
    const fyT = Math.min(y, H - M - Math.round(150 * u));
    if (spec.note) gSticky(ctx, W - M - Math.round(410 * u), fyT, Math.round(410 * u), spec.note, GRID_PAL.purple, 0.028, Math.round(46 * u));
  }

  /* One source line, pinned to the card's own bottom margin, drawn last so nothing else
     overlaps it -- see gSourceLine. */
  gSourceLine(ctx, W, H, M, u, spec.chip_label || (spec.footnote ? "Sumber" : ""), spec.footnote || "", dark);

  /* Reserve room for the source line drawn just below this check -- it is pinned to the
     card's own bottom margin regardless of how far the content above it flowed, so a
     bubble or panel that merely cleared the canvas could still run into it unseen. */
  if (y > H - Math.round(150 * u)) warn.push("The slide is fuller than the card — shorten a line.");
  /* The measuring pass wants the layout, not a picture: it is handed no canvas and returns
     only where the content ended, which is what centreShift needs. */
  return canvasOut ? { url: canvasOut.toDataURL("image/jpeg", 0.88), warn, y } : { warn, y };
}
const SCRIM = { light: [0.28, 0.38, 0.56], medium: [0.46, 0.54, 0.72], heavy: [0.62, 0.70, 0.86] };

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
function eraBadge(ctx, W, u, M, text) {
  if (!text) return;
  const px = Math.round(23 * u);
  ctx.save();
  ctx.font = "700 " + px + "px " + G_HEAD; ctx.textBaseline = "top"; ctx.textAlign = "left";
  const label = stripEmph(text).toUpperCase();
  const padX = Math.round(px * 0.8), h = Math.round(px * 2);
  const w = Math.min(ctx.measureText(label).width + padX * 2, Math.round(W * 0.56));
  const x = W - M - w, y = Math.round(50 * u);
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
  const ctx = c.getContext("2d");
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
  return eraCardPaint(ctx, spec, W, H, 0, c);
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
  const onGround = !!(spec && spec.bg);
  const ink = onGround ? "#FFFFFF" : ERA_PAL.ink,
        muted = onGround ? "rgba(255,255,255,.72)" : ERA_PAL.muted,
        red = ERA_PAL.red;
  const items = (spec.items || []).filter(x => String(x || "").trim());
  /* One fixed type scale for the whole family, for the same reason the grid family has one
     (Wan, 19 Sep 2026: "no font size change if we delete the text"). */
  const HEAD_PX = Math.round(76 * u), HEAD_LH = Math.round(90 * u);
  const LEAD_PX = Math.round(33 * u), LEAD_LH = Math.round(46 * u);
  const ITEM_HEAD_PX = Math.round(40 * u), ITEM_BODY_PX = Math.round(29 * u), ITEM_BODY_LH = Math.round(39 * u);

  if (!await drawGround(ctx, spec, W, H)) eraPaper(ctx, W, H);
  /* Rule 7 again: the mark is the consultancy's and LinkedIn carries none of it. */
  await drawBrandMark(ctx, spec, W, u, M, { top: 54, h: 34, textFill: "rgba(21,21,21,.6)" });
  eraBadge(ctx, W, u, M, spec.eyebrow);

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
  sizeMascot(H * (hero ? 0.36 : 0.27));
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
    sizeMascot(Math.min(H * 0.44, Math.max(H * 0.26, mascotFloor - y - Math.round(215 * u))));
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
    const blocks = items.slice(0, 3).map(gCells);
    /* With blocks under it the title is a section heading and takes the red stamp; with
       nothing under it the slide IS the title, so it takes the marker instead. A three-line
       red block is a wall, and a wall is exactly what an auto-built carousel slide -- which
       has a headline and no items at all -- would have produced every single time. */
    if (blocks.length) { y = eraBand(ctx, M, y, maxW, spec.title || "", Math.round(44 * u)); y += Math.round(32 * u); }
    else { y = eraMark(ctx, spec.title || "", M, y, maxW, Math.round(62 * u), Math.round(76 * u), ink, red); y += Math.round(26 * u); }
    if (blocks.length) {
      for (const cells of blocks) {
        y = eraMark(ctx, cells[0] || "", M, y, Math.round(maxW * 0.9), ITEM_HEAD_PX, Math.round(ITEM_HEAD_PX * 1.26), ink, red);
        y += Math.round(14 * u);
        if (cells[1]) y = gPara(ctx, cells[1], M, y, Math.round(maxW * (mascot ? 0.78 : 0.9)), ITEM_BODY_PX, ITEM_BODY_LH, muted);
        y += Math.round(30 * u);
      }
    } else if (spec.lead) {
      y = gPara(ctx, spec.lead, M, y, Math.round(maxW * 0.9), LEAD_PX, LEAD_LH, muted);
    }
    const afterY = y;
    drawMascot(afterY);
    if (spec.note) y = Math.max(y, gBubble(ctx, bubbleX, afterY + Math.round(20 * u), Math.round(470 * u), spec.note, Math.round(30 * u)));
  } else if (t === "e_flow") {
    y = eraBand(ctx, M, y, maxW, spec.title || "", Math.round(44 * u));
    y += Math.round(34 * u);
    const steps = items.slice(0, 4).map(gCells);
    steps.forEach((s, i) => {
      const inset = Math.round(150 * u);
      ctx.font = "800 " + ITEM_HEAD_PX + "px " + G_HEAD;
      const headLines = gWrap(ctx, s[0] || "", maxW - inset);
      ctx.font = "500 " + ITEM_BODY_PX + "px " + G_BODY;
      const bodyLines = s[1] ? gWrap(ctx, s[1], maxW - inset) : [];
      const h = Math.round(30 * u) + headLines.length * Math.round(ITEM_HEAD_PX * 1.2)
        + bodyLines.length * ITEM_BODY_LH + Math.round(22 * u);
      eraCard(ctx, M, y, maxW, h, i % 2 ? 0.006 : -0.006, (k, cw) => {
        const r = Math.round(30 * u);
        k.fillStyle = ERA_PAL.red;
        k.beginPath(); k.arc(Math.round(50 * u) + r, Math.round(32 * u) + r, r, 0, Math.PI * 2); k.fill();
        k.fillStyle = "#FFFFFF"; k.font = "800 " + Math.round(32 * u) + "px " + G_HEAD;
        k.textAlign = "center"; k.textBaseline = "middle";
        k.fillText(String(i + 1), Math.round(50 * u) + r, Math.round(32 * u) + r + Math.round(2 * u));
        k.textAlign = "left"; k.textBaseline = "top";
        let ty = Math.round(32 * u);
        k.font = "800 " + ITEM_HEAD_PX + "px " + G_HEAD; k.fillStyle = ERA_PAL.ink;
        for (const l of headLines) { k.fillText(l, Math.round(128 * u), ty); ty += Math.round(ITEM_HEAD_PX * 1.2); }
        if (bodyLines.length) {
          k.font = "500 " + ITEM_BODY_PX + "px " + G_BODY; k.fillStyle = ERA_PAL.muted;
          for (const l of bodyLines) { k.fillText(l, Math.round(128 * u), ty); ty += ITEM_BODY_LH; }
        }
      });
      y += h;
      if (i < steps.length - 1) {
        /* The arrow needs a shaft long enough to read as one. At a 32px drop the head alone
           filled it and the result was a wedge, not an arrow. */
        const ax = M + Math.round(maxW * 0.5);
        eraArrow(ctx, ax, y + Math.round(10 * u), ax, y + Math.round(54 * u), Math.round(12 * u), red, Math.max(3, Math.round(6 * u)));
        y += Math.round(66 * u);
      }
    });
    y += Math.round(20 * u);
    if (spec.note) y = eraBand(ctx, M, y, maxW, spec.note, Math.round(32 * u));
  } else if (t === "e_vs") {
    y = eraMark(ctx, spec.title || "", M, y, maxW, Math.round(56 * u), Math.round(70 * u), ink, red);
    y += Math.round(58 * u);
    const gap = Math.round(30 * u), colW = Math.round((maxW - gap) / 2);
    const pairs = [items[0] || "", items[1] || ""].map(gCells);
    /* Both notes take the height the taller one needs. A fixed height left whichever side had
       the shorter label as a mostly-empty white box, which reads as a mistake rather than as
       a design. */
    const colHof = (p, i) => {
      ctx.font = "600 " + Math.round(25 * u) + "px " + G_BODY;
      const lab = gWrap(ctx, p[0] || "", colW - Math.round(44 * u)).length * Math.round(32 * u);
      const fpx = Math.round((i ? 60 : 50) * u);
      ctx.font = "800 " + fpx + "px " + G_HEAD;
      const fig = gWrap(ctx, p[1] || "", colW - Math.round(36 * u)).length * Math.round(fpx * 1.14);
      return Math.round(26 * u) + lab + Math.round(14 * u) + fig + Math.round(26 * u);
    };
    const colH = Math.max(colHof(pairs[0], 0), colHof(pairs[1], 1), Math.round(150 * u));
    pairs.forEach((p, i) => {
      const x = M + i * (colW + gap);
      /* The arrow lands in the gap the headline leaves above each note, so it never has to
         know how many lines the headline ran to. */
      eraArrow(ctx, x + colW * (i ? 0.84 : 0.16), y - Math.round(46 * u),
        x + colW * (i ? 0.64 : 0.36), y - Math.round(8 * u),
        i ? -Math.round(14 * u) : Math.round(14 * u), red, Math.max(3, Math.round(6 * u)));
      eraCard(ctx, x, y, colW, colH, i ? 0.012 : -0.012, (k, cw) => {
        k.textBaseline = "top"; k.textAlign = "left";
        k.font = "600 " + Math.round(25 * u) + "px " + G_BODY; k.fillStyle = ERA_PAL.muted;
        let ty = Math.round(26 * u);
        for (const l of gWrap(k, p[0] || "", cw - Math.round(44 * u))) { k.fillText(l, Math.round(24 * u), ty); ty += Math.round(32 * u); }
        ty += Math.round(14 * u);
        const fpx = Math.round((i ? 60 : 50) * u);
        k.font = "800 " + fpx + "px " + G_HEAD; k.fillStyle = i ? ERA_PAL.red : ERA_PAL.ink;
        for (const l of gWrap(k, p[1] || "", cw - Math.round(36 * u))) { k.fillText(l, Math.round(24 * u), ty); ty += Math.round(fpx * 1.14); }
      });
    });
    y += colH + Math.round(34 * u);
    if (spec.note) { y = eraBand(ctx, M, y, maxW, spec.note, Math.round(34 * u)); y += Math.round(22 * u); }
    for (const b of items.slice(2, 5)) {
      y = eraBullet(ctx, b, M, y, Math.round(maxW * (mascot ? 0.68 : 0.92)), Math.round(27 * u), Math.round(36 * u));
      y += Math.round(16 * u);
    }
    drawMascot(Math.round(H * 0.6));
  }

  gSourceLine(ctx, W, H, M, u, spec.chip_label || (spec.footnote ? "Sumber" : ""), spec.footnote || "", false);
  if (y > H - Math.round(150 * u)) warn.push("The slide is fuller than the card — shorten a line.");
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
  const ctx = c.getContext("2d");
  try { await document.fonts.ready; } catch (e) { }
  if (spec.template === "p_fact") {
    const probe = await photoCardPaint(measureProxy(ctx), spec, W, H, 0);
    const u = W / 1080, panelTop = Math.round(H * 0.46) + Math.round(58 * u);
    const slack = (H - Math.round(150 * u)) - Math.max(panelTop, probe.y);
    return photoCardPaint(ctx, spec, W, H, slack > 0 ? Math.round(slack / 2) : 0, c);
  }
  return photoCardPaint(ctx, spec, W, H, 0, c);
}
async function photoCardPaint(ctx, spec, W, H, yShift, canvasOut) {
  const warn = [];
  const t = spec.template, u = W / 1080, M = Math.round(74 * u), maxW = W - M * 2;
  const items = (spec.items || []).filter(x => String(x || "").trim());
  const bg = spec.bg ? await loadImg(spec.bg) : null;
  if (!bg) warn.push("This design is built on a picture and none is chosen — pick one under Background.");
  const HEAD_PX = Math.round(72 * u), HEAD_LH = Math.round(84 * u);
  const LEAD_PX = Math.round(32 * u), LEAD_LH = Math.round(45 * u);
  const paintBg = (x, y, w, h) => {
    ctx.save(); ctx.beginPath(); ctx.rect(x, y, w, h); ctx.clip(); ctx.translate(x, y);
    if (bg) coverDraw(ctx, bg, w, h);
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
  let y = 0;
  const quote = t === "p_quote";
  if (t === "p_fact") {
    const photoH = Math.round(H * 0.46);
    paintBg(0, 0, W, photoH);
    scrim(0, 0, W, photoH, "light");
    ctx.fillStyle = GRID_PAL.cream; ctx.fillRect(0, photoH, W, H - photoH);
    y = photoH + Math.round(58 * u) + (yShift || 0);
    if (spec.eyebrow) y = gEyebrow(ctx, spec.eyebrow, M, y, GRID_PAL.orange, Math.round(23 * u));
    y = gHeadline(ctx, spec.title || "", M, y, maxW, Math.round(56 * u), Math.round(68 * u), GRID_PAL.ink, GRID_PAL.orange);
    y += Math.round(18 * u);
    if (spec.lead) y = gPara(ctx, spec.lead, M, y, Math.round(maxW * 0.92), LEAD_PX, LEAD_LH, GRID_PAL.muted);
    if (items.length) {
      y += Math.round(16 * u);
      for (const it of items.slice(0, 4)) {
        ctx.fillStyle = GRID_PAL.orange;
        ctx.beginPath(); ctx.arc(M + Math.round(9 * u), y + Math.round(15 * u), Math.round(8 * u), 0, Math.PI * 2); ctx.fill();
        y = gPara(ctx, it, M + Math.round(34 * u), y, maxW - Math.round(34 * u), Math.round(28 * u), Math.round(38 * u), GRID_PAL.ink, 600);
        y += Math.round(10 * u);
      }
    }
  } else {
    paintBg(0, 0, W, H);
    scrim(0, 0, W, H, spec.scrim || (spec.stream === "linkedin" ? "heavy" : "medium"));
    const hp = quote ? Math.round(62 * u) : HEAD_PX, hl = quote ? Math.round(78 * u) : HEAD_LH;
    const headText = quote ? "“" + String(spec.title || "") + "”" : String(spec.title || "");
    ctx.font = "800 " + hp + "px " + G_HEAD;
    const hLines = gWrap(ctx, headText, maxW);
    ctx.font = "500 " + LEAD_PX + "px " + G_BODY;
    const lLines = spec.lead ? gWrap(ctx, spec.lead, Math.round(maxW * 0.86)) : [];
    const blockH = hLines.length * hl + (lLines.length ? Math.round(22 * u) + lLines.length * LEAD_LH : 0);
    /* Room for the source line, which is pinned to the bottom margin and drawn last. */
    const reserve = Math.round((spec.footnote || spec.chip_label ? 96 : 46) * u);
    y = Math.max(Math.round(190 * u), quote ? Math.round((H - blockH) / 2) : H - M - reserve - blockH);
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
  if (y > H - Math.round(150 * u)) warn.push("The slide is fuller than the card — shorten a line.");
  return canvasOut ? { url: canvasOut.toDataURL("image/jpeg", 0.9), warn, y } : { warn, y };
}
/* ======================= COPIED FROM STUDIO (end) ========================= */

/* ======================= SEMASA: slides -> Studio cards ===================== */

/* The looks Wan chooses from. "classic" is Semasa's own Pillow drawing (backend/semasa/slides.py); the other three
   are Studio's groups above, in Studio's own order: Grid first, as the house look. */
export const LOOKS = [
  { k: "classic", bm: "Semasa", en: "Semasa", hintBm: "Reka bentuk asal Semasa: kertas krim, tajuk serif, nombor slaid.",
    hintEn: "Semasa's own drawing: cream paper, serif headline, slide numbers." },
  { k: "grid", bm: "Grid", en: "Grid", hintBm: "Studio: kertas graf krim, tajuk tebal, satu perkataan oren.",
    hintEn: "Studio: cream graph paper, ultra-bold headline, one word in orange." },
  { k: "era", bm: "Info ERA", en: "Info ERA", hintBm: "Studio: kertas kraf, highlight marker, blok merah. Penerang yang lantang.",
    hintEn: "Studio: kraft paper, marker highlights, red blocks. A loud explainer." },
  { k: "photo", bm: "Foto", en: "Photo", hintBm: "Studio: gambar anda di belakang perkataan, pada setiap slaid. Perlu gambar latar.",
    hintEn: "Studio: your picture behind the words, on every slide. Needs a background picture." },
];
export const STUDIO_LOOKS = ["grid", "era", "photo"];
export const isStudioLook = (k) => STUDIO_LOOKS.includes(k);

/* The points of a slide as one paragraph block: one line each, marked when there is more than one. Studio's
   gWrap breaks on "\n", so every point starts on its own line and none is dropped. */
function asLines(points) {
  const p = (points || []).map((x) => String(x || "").trim()).filter(Boolean);
  return p.length > 1 ? p.map((x) => "• " + x).join("\n") : (p[0] || "");
}

/* A Semasa slide list ({title, points}[]) as Studio card specs. EVERY WORD IS KEPT: Studio's templates slice their
   item lists (e_hook 3, e_explain 3, p_fact 4), so a slide with more points than its template shows is given the
   layout that draws them all as lines instead of a template that would silently drop the rest.
   Cover, middle and closing slides take the templates Studio's own groups name (CARD_GROUPS). The source line is
   drawn on the closing slide only, Semasa's rule; the eyebrow on every slide, Studio's. */
export function specsFor(slides, o = {}) {
  const look = STUDIO_LOOKS.includes(o.look) ? o.look : "grid";
  const list = (slides || []).filter((s) => s && (String(s.title || "").trim() || (s.points || []).length));
  const n = list.length;
  const linkedin = o.stream === "linkedin";
  return list.map((s, i) => {
    const pts = (s.points || []).map((x) => String(x || "").trim()).filter(Boolean);
    const last = i === n - 1;
    const base = {
      stream: linkedin ? "linkedin" : "regulab",
      title: String(s.title || "").trim(),
      eyebrow: String(o.eyebrow || "").trim(),
      footnote: last ? String(o.citation || "").trim() : "",
      chip_label: last && String(o.citation || "").trim() ? (linkedin ? "Source" : "Sumber") : "",
      bg: o.bg || "",
      scrim: linkedin ? "heavy" : "medium",
      size: o.size || undefined,
    };
    if (look === "grid") return { ...base, template: "g_title", lead: asLines(pts) };
    if (look === "era") {
      if (i === 0 && n > 1 && pts.length <= 4) return { ...base, template: "e_hook", lead: pts[0] || "", items: pts.slice(1) };
      if (pts.length && pts.length <= 3) return { ...base, template: "e_explain", items: pts };
      return { ...base, template: "e_explain", lead: asLines(pts) };
    }
    // photo
    if (i === 0 || n === 1) return { ...base, template: "p_title", lead: asLines(pts) };
    if (last) return { ...base, template: "p_quote", lead: asLines(pts) };
    if (pts.length && pts.length <= 4) return { ...base, template: "p_fact", items: pts };
    return { ...base, template: "p_fact", lead: asLines(pts) };
  });
}

function renderSpec(spec) {
  if (GRID_TPL[spec.template]) return renderGridCard(spec);
  if (ERA_TPL[spec.template]) return renderEraCard(spec);
  if (PHOTO_TPL[spec.template]) return renderPhotoCard(spec);
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
const FACES = ["600 20px Poppins", "700 20px Poppins", "800 20px Poppins",
  '400 20px "Instrument Sans"', '500 20px "Instrument Sans"', '600 20px "Instrument Sans"',
  '400 20px "JetBrains Mono"', '500 20px "JetBrains Mono"', "700 20px Caveat"];
let _fonts = null;
export function ensureFonts(base = "") {
  if (_fonts) return _fonts;
  _fonts = (async () => {
    const href = base + "fonts.css";
    if (!document.querySelector(`link[data-studio-cards]`)) {
      const link = document.createElement("link");
      link.rel = "stylesheet"; link.href = href; link.dataset.studioCards = "1";
      await new Promise((res) => { link.onload = res; link.onerror = res; document.head.appendChild(link); });
    }
    await Promise.all(FACES.map((f) => document.fonts.load(f, "Aa āşı 1–2").catch(() => null)));
    const missing = FACES.filter((f) => !document.fonts.check(f, "Aa"));
    return { missing };
  })();
  return _fonts;
}

if (typeof window !== "undefined") window.SemasaCards = { LOOKS, specsFor, renderSlides, ensureFonts, setLogo };
