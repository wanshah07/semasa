/* The seven 2D styles (Wan, 11 Nov 2026: "reset motion format ... apply motion skill below randomly", "I don't want that layout
   code, you have freedom"). A film whose props carry `skin` is drawn here and nowhere else: none of this mirrors motion_layout.py.
   Each style is its own world (ground, type, way of arriving), drawn only with SVG and React and timed from useCurrentFrame, so
   a frame is the same every time it is rendered. What every style shares is only what keeps a film readable: one safe box, type
   sized until it fits, and the subtitle lane. The colours are each style's own, never the brand palette: the brand is the cover
   in front and the logo card at the end. */
import React from "react";
import { AbsoluteFill, Easing, Img, interpolate, random, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" };
/* one letter for every style (Wan, 11 Nov 2026: Plus Jakarta Sans for all formats): a style is told apart by its ground, its
   colours, its shapes and how it moves, and by the weight and case of the same typeface */
const SANS = '"Plus Jakarta Sans", system-ui, sans-serif';
const INTER = SANS, BANGERS = SANS, PIXEL = SANS, CHALK = SANS;

/* how wide an average glyph is, as a share of the font size: measured high on purpose, so an estimate never under-counts lines */
const wrapLines = (text, px, width, factor) => {
  let n = 1, cur = 0;
  const space = px * factor * 0.5;
  for (const word of String(text || " ").split(/\s+/).filter(Boolean)) {
    const wd = word.length * px * factor;
    if (cur && cur + space + wd > width) { n += 1; cur = wd; } else cur += (cur ? space : 0) + wd;
    if (wd > width) { n += Math.floor(wd / width); cur = wd % width; }
  }
  return n;
};
/* the largest size at which every text in `texts` (each in its own block, `extra` px of padding and gap per block) fits `height` */
const fit = (texts, max, min, width, height, factor, lh, extra = 0) => {
  for (let px = max; px > min; px -= 2) {
    const total = texts.reduce((sum, t) => sum + wrapLines(t, px, width, factor) * px * lh + extra, 0);
    if (total <= height) return px;
  }
  return min;
};

export const SKINS = {
  comic: { head: BANGERS, hf: 0.68, hlh: 1.08, hw: 800, headMax: 96, body: INTER, bf: 0.6, bw: 800, lineMax: 54, pic: true,
           cap: { color: "#111111", fontFamily: INTER, fontWeight: 800 } },
  pixel: { head: PIXEL, hf: 0.64, hlh: 1.16, hw: 800, headMax: 92, body: PIXEL, bf: 0.58, bw: 500, lineMax: 50, pic: true,
           cap: { color: "#F4F4F4", fontFamily: PIXEL, fontWeight: 500 } },
  chalk: { head: CHALK, hf: 0.6, hlh: 1.12, hw: 500, headMax: 100, body: CHALK, bf: 0.56, bw: 400, lineMax: 52, pic: false,
           cap: { color: "#F2F2EA", fontFamily: CHALK, fontWeight: 500 } },
  glow: { head: INTER, hf: 0.6, hlh: 1.12, hw: 300, headMax: 104, body: INTER, bf: 0.56, bw: 300, lineMax: 54, pic: false,
          cap: { color: "#FFE7C2", fontFamily: INTER, fontWeight: 400 } },
  flat: { head: INTER, hf: 0.63, hlh: 1.08, hw: 800, headMax: 104, body: INTER, bf: 0.58, bw: 600, lineMax: 52, pic: true,
          cap: { color: "#F2EEE8", fontFamily: INTER, fontWeight: 600 } },
  papercut: { head: INTER, hf: 0.63, hlh: 1.1, hw: 800, headMax: 96, body: INTER, bf: 0.58, bw: 600, lineMax: 52, pic: true,
              cap: { color: "#4A2A16", fontFamily: INTER, fontWeight: 700 } },
  dankoe: { head: INTER, hf: 0.58, hlh: 1.14, hw: 300, headMax: 96, body: INTER, bf: 0.55, bw: 300, lineMax: 54, pic: false,
            cap: { color: "#FFFFFF", fontFamily: INTER, fontWeight: 300 } },
};
export const isSkin = (id) => Object.prototype.hasOwnProperty.call(SKINS, id);

/* ---------------------------------------------------------------- grounds: one per film, so the world carries across scenes */

const ComicGround = () => {
  const f = useCurrentFrame();
  const { width: W, height: H, fps } = useVideoConfig();
  const u = W / 1080;
  const drift = ((f % fps) / fps) * 44 * u;                       // one dot pitch a second: a seamless loop
  const rays = Array.from({ length: 18 }, (_, i) => i * 20 + (f / fps) * 6);
  return (
    <AbsoluteFill style={{ background: "#FFF4D6" }}>
      <svg width={W} height={H} style={{ position: "absolute" }}>
        <defs>
          <pattern id="halftone" width={44 * u} height={44 * u} patternUnits="userSpaceOnUse" patternTransform={`translate(${drift} ${drift}) rotate(20)`}>
            <circle cx={22 * u} cy={22 * u} r={8 * u} fill="#FFD23F" />
          </pattern>
          <radialGradient id="halfmask" cx="50%" cy="38%" r="75%">
            <stop offset="35%" stopColor="#fff" stopOpacity="0" /><stop offset="100%" stopColor="#fff" stopOpacity="1" />
          </radialGradient>
          <mask id="halfm"><rect width={W} height={H} fill="url(#halfmask)" /></mask>
        </defs>
        <g transform={`translate(${W / 2} ${H * 0.4})`} opacity="0.07">
          {rays.map((a, i) => <path key={i} d={`M0 0 L${H * 1.2} ${-H * 0.045} L${H * 1.2} ${H * 0.045} Z`} fill="#111" transform={`rotate(${a})`} />)}
        </g>
        <rect width={W} height={H} fill="url(#halftone)" mask="url(#halfm)" />
        <path d={`M0 ${H} L0 ${H * 0.93} L${W} ${H * 0.9} L${W} ${H} Z`} fill="#1D4ED8" stroke="#111" strokeWidth={6 * u} />
        <path d={`M0 0 L${W * 0.3} 0 L0 ${H * 0.06} Z`} fill="#E63946" stroke="#111" strokeWidth={6 * u} />
      </svg>
    </AbsoluteFill>
  );
};

const PixelGround = () => {
  const f = useCurrentFrame();
  const { width: W, height: H } = useVideoConfig();
  const px = W / 144;                                            // the 144-wide canvas, upscaled: everything lands on this grid
  const rows = Math.round(H / px);
  const stars = Array.from({ length: 64 }, (_, i) => ({
    x: Math.floor(random(`px${i}`) * 142), y: Math.floor(random(`py${i}`) * rows * 0.72), t: Math.floor(random(`pt${i}`) * 30),
    c: random(`pc${i}`) > 0.8 ? "#FFCD75" : random(`pc${i}`) > 0.5 ? "#94B0C2" : "#F4F4F4" }));
  const hills = Array.from({ length: 36 }, (_, i) => 6 + Math.floor(random(`ph${i}`) * 9) + (i % 5 === 0 ? 4 : 0));
  return (
    <AbsoluteFill style={{ background: "#1A1C2C" }}>
      <svg width={W} height={H} shapeRendering="crispEdges" style={{ position: "absolute" }}>
        {stars.map((s, i) => ((Math.floor(f / 6) + s.t) % 5 === 0 ? null
          : <rect key={i} x={s.x * px} y={s.y * px} width={2 * px} height={2 * px} fill={s.c} opacity={(Math.floor(f / 6) + s.t) % 5 === 1 ? 0.45 : 1} />))}
        <rect x={112 * px} y={14 * px} width={14 * px} height={14 * px} fill="#FFCD75" />
        <rect x={110 * px} y={16 * px} width={18 * px} height={10 * px} fill="#FFCD75" />
        <rect x={118 * px} y={18 * px} width={4 * px} height={4 * px} fill="#EF7D57" />
        {hills.map((h, i) => <rect key={i} x={i * 4 * px} y={(rows - h - 8) * px} width={4 * px} height={(h + 8) * px} fill="#29366F" />)}
        {hills.map((h, i) => <rect key={`b${i}`} x={i * 4 * px} y={(rows - Math.floor(h / 2) - 5) * px} width={4 * px} height={(h + 5) * px} fill="#333C57" />)}
        {hills.map((h, i) => (h % 3 === 0 ? <rect key={`w${i}`} x={(i * 4 + 1) * px} y={(rows - h - 5) * px} width={px} height={px}
          fill={(Math.floor(f / 15) + i) % 4 ? "#FFCD75" : "#41A6F6"} /> : null))}
      </svg>
    </AbsoluteFill>
  );
};

const ChalkDefs = ({ u }) => (
  <svg width="0" height="0" style={{ position: "absolute" }}>
    <defs>
      <filter id="chalk" x="-5%" y="-5%" width="110%" height="110%">
        <feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="2" seed="7" result="n" />
        <feDisplacementMap in="SourceGraphic" in2="n" scale={3.2 * u} xChannelSelector="R" yChannelSelector="G" result="d" />
        <feTurbulence type="fractalNoise" baseFrequency="1.6" numOctaves="1" seed="3" result="g" />
        <feColorMatrix in="g" type="matrix" values="0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 -1.6 1.55" result="grain" />
        <feComposite in="d" in2="grain" operator="in" />
      </filter>
    </defs>
  </svg>
);

const ChalkGround = () => {
  const { width: W, height: H } = useVideoConfig();
  const u = W / 1080;
  const fr = 30 * u;
  const smudges = Array.from({ length: 7 }, (_, i) => ({ x: random(`sx${i}`) * W, y: random(`sy${i}`) * H, rx: (140 + random(`sr${i}`) * 260) * u,
    ry: (40 + random(`sq${i}`) * 70) * u, a: -25 + random(`sa${i}`) * 50 }));
  return (
    <AbsoluteFill style={{ background: "#8B5A2B" }}>
      <div style={{ position: "absolute", inset: fr, background: "#2F4F3A", boxShadow: `inset 0 0 ${90 * u}px rgba(0,0,0,.45), 0 0 0 ${4 * u}px #6E4520`, overflow: "hidden" }}>
        <svg width={W} height={H} style={{ position: "absolute", left: -fr, top: -fr, filter: `blur(${22 * u}px)` }}>
          {smudges.map((s, i) => <ellipse key={i} cx={s.x} cy={s.y} rx={s.rx} ry={s.ry} fill="#F2F2EA" opacity="0.08" transform={`rotate(${s.a} ${s.x} ${s.y})`} />)}
        </svg>
      </div>
      <ChalkDefs u={u} />
    </AbsoluteFill>
  );
};

const GlowGround = () => {
  const f = useCurrentFrame();
  const { width: W, height: H, fps } = useVideoConfig();
  const u = W / 1080;
  const draw = interpolate(f, [0, fps * 1.6], [1, 0], { ...clamp, easing: Easing.inOut(Easing.cubic) });
  const sparks = Array.from({ length: 14 }, (_, i) => ({ x: random(`gx${i}`) * W, y: random(`gy${i}`) * H * 0.95, s: (10 + random(`gs${i}`) * 16) * u, t: random(`gt${i}`) * fps * 2 }));
  return (
    <AbsoluteFill style={{ background: "#000000" }}>
      <svg width={W} height={H} style={{ position: "absolute", filter: `drop-shadow(0 0 ${5 * u}px #FFE7C2) drop-shadow(0 0 ${16 * u}px rgba(255,231,194,.55))` }}
           fill="none" stroke="#FFE7C2" strokeWidth={2.5 * u} strokeLinecap="round">
        <rect x={W * 0.045} y={H * 0.075} width={W * 0.91} height={H * 0.85} rx={46 * u} pathLength="1" strokeDasharray="1" strokeDashoffset={draw} opacity="0.55" />
        {sparks.map((s, i) => {
          const o = 0.25 + 0.6 * Math.abs(Math.sin(((f + s.t) / fps) * Math.PI));
          return <path key={i} d={`M${s.x - s.s} ${s.y} H${s.x + s.s} M${s.x} ${s.y - s.s} V${s.y + s.s}`} opacity={o} strokeWidth={1.6 * u} />;
        })}
      </svg>
    </AbsoluteFill>
  );
};

const FlatGround = () => {
  const f = useCurrentFrame();
  const { width: W, height: H, fps } = useVideoConfig();
  const u = W / 1080;
  const layer = (seed, n, base, tall, colour, speed) => {
    const bw = (W * 1.4) / n;
    const shift = -((f / fps) * speed * u) % bw;
    return Array.from({ length: n + 2 }, (_, i) => {
      const h = (base + random(`${seed}${i % n}`) * tall) * u;
      return <rect key={seed + i} x={i * bw + shift - bw} y={H - h} width={bw + 1} height={h} fill={colour} />;
    });
  };
  return (
    <AbsoluteFill style={{ background: "#1B2A4A" }}>
      <svg width={W} height={H} style={{ position: "absolute" }}>
        <circle cx={W * 0.82} cy={H * 0.07} r={54 * u} fill="#F2EEE8" />
        <circle cx={W * 0.82 + 20 * u} cy={H * 0.07 - 13 * u} r={46 * u} fill="#1B2A4A" />
        {layer("a", 9, 250, 190, "#24365E", 8)}
        {layer("b", 12, 150, 150, "#2E4372", 16)}
        {layer("c", 15, 70, 90, "#3A5286", 30)}
        <rect x="0" y={H * 0.063} width={W * 0.16} height={10 * u} fill="#F28C38" />
      </svg>
    </AbsoluteFill>
  );
};

/* a torn edge: a wobbling line from left to right at height y, closed down to the bottom of the frame */
const torn = (W, H, y, amp, seed, steps = 28) => {
  let d = `M0 ${H} L0 ${y}`;
  for (let i = 1; i <= steps; i++) d += ` L${(W * i) / steps} ${y + (random(`${seed}${i}`) - 0.5) * amp + Math.sin(i / 3 + seed.length) * amp}`;
  return d + ` L${W} ${H} Z`;
};

const PaperDefs = () => (
  <svg width="0" height="0" style={{ position: "absolute" }}>
    <defs>
      <filter id="kraft" x="0" y="0" width="100%" height="100%">
        <feTurbulence type="fractalNoise" baseFrequency="0.7" numOctaves="3" seed="11" />
        <feColorMatrix type="matrix" values="0 0 0 0 0.48  0 0 0 0 0.29  0 0 0 0 0.16  0 0 0 0.22 0" />
      </filter>
    </defs>
  </svg>
);

const PaperGround = () => {
  const f = useCurrentFrame();
  const { width: W, height: H, fps } = useVideoConfig();
  const u = W / 1080;
  const sway = Math.sin((f / fps) * 0.8) * 6 * u;
  const shadow = (n) => `drop-shadow(0 ${-n * u}px ${n * 1.6 * u}px rgba(74,42,22,.28))`;
  return (
    <AbsoluteFill style={{ background: "#F6E7CB" }}>
      <PaperDefs />
      <svg width={W} height={H} style={{ position: "absolute" }}>
        <circle cx={W * 0.84} cy={H * 0.068} r={62 * u} fill="#E9B872" style={{ filter: `drop-shadow(${6 * u}px ${8 * u}px ${8 * u}px rgba(74,42,22,.3))` }} />
        <path d={torn(W, H, H * 0.905, 16 * u, "h1")} fill="#E9B872" style={{ filter: shadow(5) }} transform={`translate(${sway} 0)`} />
        <path d={torn(W, H, H * 0.935, 14 * u, "h2")} fill="#C9773C" style={{ filter: shadow(6) }} transform={`translate(${-sway * 1.4} 0)`} />
        <path d={torn(W, H, H * 0.962, 12 * u, "h3")} fill="#7A4A2A" style={{ filter: shadow(7) }} transform={`translate(${sway * 2} 0)`} />
        <rect width={W} height={H} filter="url(#kraft)" opacity="0.5" />
      </svg>
    </AbsoluteFill>
  );
};

const DotGround = () => {
  const f = useCurrentFrame();
  const { width: W, height: H, fps } = useVideoConfig();
  const u = W / 1080;
  const t = f / fps;
  const dots = Array.from({ length: 140 }, (_, i) => {
    const x0 = random(`dx${i}`) * W, y0 = random(`dy${i}`) * H, sp = 6 + random(`ds${i}`) * 18, ph = random(`dp${i}`) * 6.28;
    return { x: x0 + Math.sin(t * 0.4 + ph) * 14 * u, y: (((y0 - t * sp * u) % H) + H) % H, r: (0.8 + random(`dr${i}`) * 1.6) * u, o: 0.25 + random(`do${i}`) * 0.55 };
  });
  return (
    <AbsoluteFill style={{ background: "#000000" }}>
      <svg width={W} height={H} style={{ position: "absolute" }}>
        {dots.map((d, i) => <circle key={i} cx={d.x} cy={d.y} r={d.r} fill="#fff" opacity={d.o} />)}
        <circle cx={W * 0.5} cy={H * 0.96} r={W * 0.62} fill="none" stroke="#fff" strokeWidth={1.25 * u} opacity="0.35"
                strokeDasharray={`${3 * u} ${11 * u}`} transform={`rotate(${t * 2} ${W * 0.5} ${H * 0.96})`} />
      </svg>
    </AbsoluteFill>
  );
};

const GROUNDS = { comic: ComicGround, pixel: PixelGround, chalk: ChalkGround, glow: GlowGround, flat: FlatGround, papercut: PaperGround, dankoe: DotGround };
export const SkinGround = ({ skin }) => { const G = GROUNDS[skin]; return G ? <G /> : null; };

/* ---------------------------------------------------------------- how a block arrives, per style */

const useArrive = (skin, at) => {
  const f = useCurrentFrame();
  const { fps, width: W } = useVideoConfig();
  const u = W / 1080;
  const t = f - at;
  if (skin === "comic") {
    const s = spring({ frame: t, fps, config: { damping: 9, mass: 0.6, stiffness: 160 } });
    return { opacity: t < 0 ? 0 : 1, transform: `scale(${0.3 + 0.7 * s})` };
  }
  if (skin === "pixel") {                                         // no easing: it steps in on the pixel grid
    const step = Math.max(0, Math.min(4, Math.floor(t / 2)));
    return { opacity: t < 0 ? 0 : 1, transform: `translateY(${(4 - step) * (W / 144) * 2}px)` };
  }
  if (skin === "chalk") {                                         // written on from the left
    const p = interpolate(t, [0, fps * 0.7], [100, 0], { ...clamp, easing: Easing.out(Easing.quad) });
    return { clipPath: `inset(-10% ${p}% -10% -5%)` };
  }
  if (skin === "glow") {
    const p = interpolate(t, [0, fps * 0.8], [0, 1], clamp);
    return { opacity: p, filter: `blur(${(1 - p) * 10 * u}px)` };
  }
  if (skin === "flat") {
    const p = interpolate(t, [0, fps * 0.5], [0, 1], { ...clamp, easing: Easing.out(Easing.cubic) });
    return { opacity: p, transform: `translateX(${(1 - p) * -70 * u}px)` };
  }
  if (skin === "papercut") {                                      // dropped on the table: falls, lands, settles
    const s = spring({ frame: t, fps, config: { damping: 13, mass: 0.7 } });
    return { opacity: t < 0 ? 0 : Math.min(1, s * 3), transform: `translateY(${(1 - s) * -90 * u}px) rotate(${(1 - s) * -5}deg)` };
  }
  const p = interpolate(t, [0, fps * 1.1], [0, 1], { ...clamp, easing: Easing.out(Easing.cubic) });
  return { opacity: p, transform: `translateY(${(1 - p) * 14 * u}px)` };
};

const Arrive = ({ skin, at, style, children }) => {
  const a = useArrive(skin, at);
  return <div style={{ ...style, ...a, transform: [style?.transform, a.transform].filter(Boolean).join(" ") || undefined }}>{children}</div>;
};

/* a stroke that draws itself */
const Stroke = ({ d, at, len = 0.6, width, colour, style, box }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const off = interpolate(f - at, [0, fps * len], [1, 0], { ...clamp, easing: Easing.inOut(Easing.cubic) });
  return (
    <svg viewBox={box} preserveAspectRatio="none" style={{ display: "block", overflow: "visible", ...style }}>
      <path d={d} fill="none" stroke={colour} strokeWidth={width} strokeLinecap="round" strokeLinejoin="round"
            strokeDasharray="6000" strokeDashoffset={off * 6000} vectorEffect="non-scaling-stroke" />
    </svg>
  );
};

/* ---------------------------------------------------------------- one scene */

const COMIC_TILT = [-1.6, 1.2, -0.8];
const PAPER_TILT = [-1.4, 1.1, -0.6];
const COMIC_FILL = ["#E63946", "#1D4ED8", "#111111"];

export const SkinScene = ({ scene, skin }) => {
  const f = useCurrentFrame();
  const { fps, width: W, height: H, durationInFrames: D } = useVideoConfig();
  const S = SKINS[skin];
  const u = W / 1080;
  const px = W / 144;
  const tall = H > W;
  const out = interpolate(f, [D - 7, D], [1, 0], clamp);
  const boxL = W * 0.08, boxW = W * 0.78, boxTop = H * (tall ? 0.13 : 0.1), boxH = H * 0.75 - boxTop;
  const lines = (scene.lines || []).slice(0, 3).map(String).filter((x) => x.trim());
  const pic = S.pic && scene.photo ? scene.photo : "";

  /* padding each style puts round its heading and its lines, taken off the width and height the type is sized for */
  const padH = { comic: 34, pixel: 0, chalk: 0, glow: 0, flat: 0, papercut: 36, dankoe: 0 }[skin] * u;
  const padL = { comic: 22, pixel: 0, chalk: 0, glow: 0, flat: 24, papercut: 22, dankoe: 0 }[skin] * u;
  const mark = { comic: 84, pixel: 44, chalk: 74, glow: 76, flat: 84, papercut: 70, dankoe: 76 }[skin] * u;
  const gap = { comic: 22, pixel: 22, chalk: 14, glow: 26, flat: 16, papercut: 20, dankoe: 30 }[skin] * u;
  const words = String(scene.heading || "").split(/\s+/).filter(Boolean).length;
  const headMax = S.headMax * u * (words <= 4 ? 1 : words <= 8 ? 0.86 : 0.72) * (pic ? 0.82 : 1);
  const head = fit([scene.heading], headMax, 42 * u, boxW - 2 * padH - 8 * u, boxH * (pic ? 0.24 : 0.34) - 2 * padH, S.hf, S.hlh);
  const lineW = boxW - mark - 2 * padL - 10 * u;
  const lineSize = lines.length ? fit(lines, S.lineMax * u * (pic ? 0.9 : 1), 32 * u, lineW, boxH * (pic ? 0.3 : 0.44), S.bf, 1.24, 2 * padL + gap) : 0;
  const first = Math.round(fps * 0.75);
  const step = Math.max(8, Math.floor(Math.min(fps * 1.1, (D - fps * 1.2) / Math.max(lines.length, 1))));

  const headStyle = { fontFamily: S.head, fontWeight: S.hw, fontSize: head, lineHeight: S.hlh, overflowWrap: "anywhere" };
  let heading;
  if (skin === "comic") {
    heading = (
      <Arrive skin={skin} at={2} style={{ transform: "rotate(-2deg)", transformOrigin: "30% 60%" }}>
        <div style={{ ...headStyle, background: "#FFD23F", color: "#111", border: `${6 * u}px solid #111`, padding: `${padH * 0.55}px ${padH}px`,
                      boxShadow: `${12 * u}px ${12 * u}px 0 #111`, letterSpacing: "0.02em", textTransform: "uppercase" }}>{scene.heading}</div>
      </Arrive>
    );
  } else if (skin === "pixel") {
    const shown = Math.floor(Math.max(0, f - 2) * 1.4);          // typed on, a character or so a frame
    const text = String(scene.heading || "");
    heading = (
      <div style={{ ...headStyle, color: "#FFCD75", textShadow: `${px}px ${px}px 0 #EF7D57` }}>
        <span>{text.slice(0, shown)}</span><span style={{ opacity: 0 }}>{text.slice(shown)}</span>
        {shown < text.length || Math.floor(f / 8) % 2 === 0 ? null : <span style={{ color: "#41A6F6" }}>_</span>}
      </div>
    );
  } else if (skin === "chalk") {
    heading = (
      <div style={{ filter: "url(#chalk)" }}>
        <Arrive skin={skin} at={2} style={{ ...headStyle, color: "#F2F2EA" }}>{scene.heading}</Arrive>
        <Stroke at={Math.round(fps * 0.6)} len={0.5} width={5 * u} colour="#F2F2EA" box="0 0 100 10" d="M1 6 C 20 2, 38 9, 58 4 S 88 7, 99 3"
                style={{ width: "72%", height: 18 * u, marginTop: 4 * u }} />
      </div>
    );
  } else if (skin === "glow") {
    heading = (
      <div style={{ filter: `drop-shadow(0 0 ${6 * u}px rgba(255,231,194,.9)) drop-shadow(0 0 ${22 * u}px rgba(255,231,194,.45))` }}>
        <Arrive skin={skin} at={2} style={{ ...headStyle, color: "#FFE7C2", letterSpacing: "-0.01em" }}>{scene.heading}</Arrive>
        <Stroke at={Math.round(fps * 0.4)} len={0.9} width={2.5 * u} colour="#FFE7C2" box="0 0 100 4" d="M0 2 H100" style={{ width: "100%", height: 6 * u, marginTop: 26 * u }} />
      </div>
    );
  } else if (skin === "flat") {
    heading = <Arrive skin={skin} at={2} style={{ ...headStyle, color: "#F2EEE8", letterSpacing: "-0.02em" }}>{scene.heading}</Arrive>;
  } else if (skin === "papercut") {
    heading = (
      <Arrive skin={skin} at={2} style={{ transform: "rotate(-1.5deg)" }}>
        <div style={{ ...headStyle, color: "#4A2A16", background: "#FFF8EA", padding: `${padH * 0.7}px ${padH}px`, letterSpacing: "-0.02em",
                      clipPath: "polygon(0 3%, 6% 0, 19% 2.5%, 34% 0.5%, 52% 3%, 71% 0, 88% 2.5%, 100% 1%, 99% 97%, 90% 100%, 72% 97.5%, 55% 100%, 37% 97%, 20% 99.5%, 7% 97%, 0.8% 100%)" }}>
          {scene.heading}</div>
      </Arrive>
    );
  } else {
    heading = (
      <div>
        <Stroke at={0} len={1.2} width={1.25 * u} colour="#fff" box="0 0 100 2" d="M0 1 H100" style={{ width: "100%", height: 3 * u, marginBottom: 44 * u }} />
        <Arrive skin={skin} at={6} style={{ ...headStyle, color: "#fff", letterSpacing: "-0.015em" }}>{scene.heading}</Arrive>
      </div>
    );
  }

  const lineText = { fontFamily: S.body, fontWeight: S.bw, fontSize: lineSize, lineHeight: 1.24, overflowWrap: "anywhere", flex: "1 1 0", minWidth: 0 };
  const row = { display: "flex", alignItems: "center", gap: 10 * u, width: "100%" };
  const renderLine = (line, i) => {
    const at = first + i * step;
    const n = i + 1;
    if (skin === "comic") {
      return (
        <Arrive key={i} skin={skin} at={at} style={{ transform: `rotate(${COMIC_TILT[i % 3]}deg)` }}>
          <div style={{ ...row, background: "#fff", border: `${6 * u}px solid #111`, padding: padL, boxShadow: `${8 * u}px ${8 * u}px 0 #111` }}>
            <svg viewBox="-50 -50 100 100" style={{ width: mark - 10 * u, height: mark - 10 * u, flex: "none", overflow: "visible" }}>
              <polygon points={Array.from({ length: 20 }, (_, k) => { const r = k % 2 ? 34 : 50, a = (k / 20) * Math.PI * 2; return `${Math.cos(a) * r},${Math.sin(a) * r}`; }).join(" ")}
                       fill={COMIC_FILL[i % 3]} stroke="#111" strokeWidth="5" strokeLinejoin="round" />
              <text x="0" y="14" textAnchor="middle" fontFamily={BANGERS} fontWeight="800" fontSize="40" fill="#fff">{n}</text>
            </svg>
            <span style={{ ...lineText, color: "#111" }}>{line}</span>
          </div>
        </Arrive>
      );
    }
    if (skin === "pixel") {
      return (
        <Arrive key={i} skin={skin} at={at} style={row}>
          <span style={{ width: mark - 10 * u, flex: "none", fontFamily: PIXEL, fontWeight: 700, fontSize: lineSize, color: "#41A6F6" }}>{">"}</span>
          <span style={{ ...lineText, color: "#F4F4F4" }}>{line}</span>
        </Arrive>
      );
    }
    if (skin === "chalk") {
      return (
        <div key={i} style={{ ...row, filter: "url(#chalk)" }}>
          <Stroke at={at} len={0.35} width={4.5 * u} colour="#F2F2EA" box="0 0 60 30" d="M3 16 C 16 13, 30 17, 50 15 M38 5 L52 15 L39 26"
                  style={{ width: mark - 14 * u, height: lineSize * 0.62, flex: "none", marginRight: 4 * u }} />
          <Arrive skin={skin} at={at + 6} style={{ ...lineText, color: "#F2F2EA" }}>{line}</Arrive>
        </div>
      );
    }
    if (skin === "glow") {
      return (
        <div key={i} style={{ ...row, filter: `drop-shadow(0 0 ${5 * u}px rgba(255,231,194,.8)) drop-shadow(0 0 ${16 * u}px rgba(255,231,194,.35))` }}>
          <div style={{ position: "relative", width: mark - 14 * u, height: mark - 14 * u, flex: "none", marginRight: 4 * u }}>
            <Stroke at={at} len={0.6} width={2.5 * u} colour="#FFE7C2" box="0 0 100 100" d="M50 4 A46 46 0 1 1 49.9 4"
                    style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }} />
            <Arrive skin={skin} at={at + 6} style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center",
                                                    fontFamily: INTER, fontWeight: 300, fontSize: (mark - 14 * u) * 0.46, color: "#FFE7C2" }}>{n}</Arrive>
          </div>
          <Arrive skin={skin} at={at + 4} style={{ ...lineText, color: "#FFE7C2" }}>{line}</Arrive>
        </div>
      );
    }
    if (skin === "flat") {
      return (
        <Arrive key={i} skin={skin} at={at} style={{ ...row, background: "#24365E", padding: padL }}>
          <span style={{ width: mark - 24 * u, height: mark - 24 * u, flex: "none", marginRight: 14 * u, background: "#F28C38", color: "#1B2A4A", display: "flex",
                         alignItems: "center", justifyContent: "center", fontFamily: INTER, fontWeight: 800, fontSize: (mark - 24 * u) * 0.56 }}>{n}</span>
          <span style={{ ...lineText, color: "#F2EEE8" }}>{line}</span>
        </Arrive>
      );
    }
    if (skin === "papercut") {
      const tag = ["#FFF8EA", "#F2D6A2", "#FFF8EA"][i % 3];
      return (
        <Arrive key={i} skin={skin} at={at} style={{ transform: `rotate(${PAPER_TILT[i % 3]}deg)`, filter: `drop-shadow(${4 * u}px ${7 * u}px ${7 * u}px rgba(74,42,22,.3))` }}>
          <div style={{ ...row, background: tag, padding: padL, borderRadius: 6 * u }}>
            <span style={{ width: mark - 20 * u, height: mark - 20 * u, flex: "none", marginRight: 10 * u, borderRadius: "50%", background: "#C9773C", color: "#FFF8EA",
                           display: "flex", alignItems: "center", justifyContent: "center", fontFamily: INTER, fontWeight: 800, fontSize: (mark - 20 * u) * 0.54 }}>{n}</span>
            <span style={{ ...lineText, color: "#4A2A16" }}>{line}</span>
          </div>
        </Arrive>
      );
    }
    return (
      <Arrive key={i} skin={skin} at={at} style={{ ...row, alignItems: "baseline", borderTop: `${1.25 * u}px solid rgba(255,255,255,.45)`, paddingTop: gap * 0.8 }}>
        <span style={{ width: mark - 10 * u, flex: "none", fontFamily: INTER, fontWeight: 300, fontSize: lineSize * 0.62, color: "rgba(255,255,255,.6)",
                       letterSpacing: "0.08em" }}>{String(n).padStart(2, "0")}</span>
        <span style={{ ...lineText, color: "#fff" }}>{line}</span>
      </Arrive>
    );
  };

  let picture = null;
  if (pic) {
    const zoom = interpolate(f, [0, D], [1.02, 1.1], clamp);
    const img = { position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover", transform: `scale(${zoom})` };
    const slot = { flex: "1 1 0", minHeight: 0, width: "100%" };
    if (skin === "comic") {
      picture = (
        <Arrive skin={skin} at={8} style={{ ...slot, transform: "rotate(1.2deg)" }}>
          <div style={{ position: "relative", width: "100%", height: "100%", overflow: "hidden", border: `${6 * u}px solid #111`, boxShadow: `${12 * u}px ${12 * u}px 0 #111`, background: "#fff" }}>
            <Img src={staticFile(pic)} style={{ ...img, filter: "contrast(1.35) saturate(1.5)" }} />
            <div style={{ position: "absolute", inset: 0, mixBlendMode: "multiply", opacity: 0.35,
                          backgroundImage: `radial-gradient(#111 ${2.2 * u}px, transparent ${2.6 * u}px)`, backgroundSize: `${9 * u}px ${9 * u}px` }} />
          </div>
        </Arrive>
      );
    } else if (skin === "pixel") {                                // the picture itself on the coarse grid: drawn small, shown big
      const k = 6;
      picture = (
        <Arrive skin={skin} at={8} style={slot}>
          <div style={{ position: "relative", width: "100%", height: "100%", overflow: "hidden", border: `${px}px solid #F4F4F4`, boxSizing: "border-box" }}>
            <div style={{ position: "absolute", left: 0, top: 0, width: `${100 / k}%`, height: `${100 / k}%`, transform: `scale(${k})`, transformOrigin: "0 0", imageRendering: "pixelated" }}>
              <Img src={staticFile(pic)} style={{ width: "100%", height: "100%", objectFit: "cover", imageRendering: "pixelated", filter: "contrast(1.15) saturate(1.2)" }} />
            </div>
          </div>
        </Arrive>
      );
    } else if (skin === "flat") {
      picture = (
        <Arrive skin={skin} at={8} style={slot}>
          <div style={{ position: "relative", width: "100%", height: "100%", overflow: "hidden", background: "#24365E" }}>
            <Img src={staticFile(pic)} style={img} />
            <div style={{ position: "absolute", left: 0, bottom: 0, width: "34%", height: 12 * u, background: "#F28C38" }} />
          </div>
        </Arrive>
      );
    } else {
      picture = (
        <Arrive skin={skin} at={8} style={{ ...slot, transform: "rotate(1.3deg)", filter: `drop-shadow(${6 * u}px ${10 * u}px ${10 * u}px rgba(74,42,22,.35))` }}>
          <div style={{ position: "relative", width: "100%", height: "100%", background: "#FFF8EA", padding: 16 * u, boxSizing: "border-box" }}>
            <div style={{ position: "relative", width: "100%", height: "100%", overflow: "hidden" }}><Img src={staticFile(pic)} style={{ ...img, filter: "sepia(.18) saturate(1.05)" }} /></div>
            <div style={{ position: "absolute", left: "50%", top: -16 * u, width: 150 * u, height: 40 * u, marginLeft: -75 * u, background: "rgba(233,184,114,.85)", transform: "rotate(-3deg)" }} />
          </div>
        </Arrive>
      );
    }
  }

  return (
    <AbsoluteFill style={{ opacity: out }}>
      <div style={{ position: "absolute", left: boxL, top: boxTop, width: boxW, height: boxH, display: "flex", flexDirection: "column",
                    justifyContent: pic ? "space-between" : "center", gap: pic ? 34 * u : (skin === "dankoe" ? 70 : 54) * u }}>
        <div style={{ flex: "none" }}>{heading}</div>
        {picture}
        {lines.length ? <div style={{ display: "flex", flexDirection: "column", gap, flex: "none", width: "100%" }}>{lines.map(renderLine)}</div> : null}
      </div>
    </AbsoluteFill>
  );
};

/* the subtitle lane: the same place in every style (78% down, 11.5% tall), in that style's own letter and ink */
export const SkinCaption = ({ text, skin }) => {
  const { width: W, height: H } = useVideoConfig();
  const S = SKINS[skin];
  const u = W / 1080;
  const boxW = W * 0.78, laneH = H * 0.115;
  const k = S.cap.scale || 1;
  const size = fit([text], 50 * u * k, 38 * u * k, boxW, laneH, S.bf, 1.28);
  return (
    <div style={{ position: "absolute", left: W * 0.08, top: H * 0.78, width: boxW, height: laneH, display: "flex", alignItems: "center", justifyContent: "center",
                  textAlign: "center", fontSize: size, lineHeight: 1.28, overflowWrap: "anywhere", color: S.cap.color, fontFamily: S.cap.fontFamily,
                  fontWeight: S.cap.fontWeight, filter: skin === "chalk" ? "url(#chalk)" : undefined,
                  textShadow: skin === "comic" ? "0 0 6px #FFF4D6, 0 0 6px #FFF4D6, 0 0 12px #FFF4D6" : skin === "papercut" ? "0 0 8px #F6E7CB, 0 0 8px #F6E7CB" : undefined }}>
      <span style={{ display: "block", maxWidth: "100%" }}>{text}</span>
    </div>
  );
};
