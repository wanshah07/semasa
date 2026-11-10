/* Semasa's film drawn by Remotion. Everything on screen comes from the props the worker writes (motion_remotion.py): the same
   scenes, times, words, pictures and palette the HyperFrames renderer gets. The LAYOUT mirrors motion_layout.py so a film
   drawn half by each engine does not show where they meet (Wan, 10 Nov 2026): the same safe box, the same mint-to-cream
   gradient with its line grid, a feathered picture, numbered points, and subtitles in the same lane. No sound here: the
   worker mixes the recorded voice and the music afterwards, exactly as it does for HyperFrames. */
import React, { useState } from "react";
import { AbsoluteFill, Easing, Img, Sequence, continueRender, delayRender, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import interLatin from "@fontsource-variable/inter/files/inter-latin-wght-normal.woff2";
import interExt from "@fontsource-variable/inter/files/inter-latin-ext-wght-normal.woff2";

const FONT = '"Inter", system-ui, -apple-system, "Segoe UI", sans-serif';
const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" };

/* Inter is bundled (the worker's browser has none): one variable file per script range, loaded before the first frame */
let fontsStarted = false;
const useFonts = () => {
  const [handle] = useState(() => (fontsStarted ? null : delayRender("Inter")));
  if (!fontsStarted) {
    fontsStarted = true;
    Promise.all([[interLatin, "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD"],
      [interExt, "U+0100-02BA,U+02BD-02C5,U+02C7-02CC,U+02CE-02D7,U+02DD-02FF,U+0304,U+0308,U+0329,U+1D00-1DBF,U+1E00-1E9F,U+1EF2-1EFF,U+2020,U+20A0-20AB,U+20AD-20C0,U+2113,U+2C60-2C7F,U+A720-A7FF"]]
      .map(([url, range]) => new FontFace("Inter", `url(${url})`, { weight: "100 900", unicodeRange: range }).load().then((f) => document.fonts.add(f))))
      .catch(() => {}).finally(() => continueRender(handle));
  }
};

/* the same estimates motion_layout.py uses: a greedy word wrap with an average glyph width */
const WIDE = 0.62, BODY = 0.56;
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
/* the largest size from max down to min at which the text fits the box height */
const sizeFor = (text, max, min, width, height, factor, lh) => {
  for (let px = max; px > min; px -= 2) if (wrapLines(text, px, width, factor) * px * lh <= height) return px;
  return min;
};

const Rise = ({ at = 0, children, style }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame: frame - at, fps, config: { damping: 200 } });
  return <div style={{ opacity: s, transform: `translateY(${(1 - s) * 36}px)`, ...style }}>{children}</div>;
};

const Backdrop = ({ bg }) => {
  const { width: W } = useVideoConfig();
  const u = W / 1080;
  const step = (bg.step || 72) * u;
  return (
    <AbsoluteFill style={{ background: `${bg.to} linear-gradient(${bg.angle}deg, ${bg.from}, ${bg.to} ${bg.stop}%)` }}>
      <AbsoluteFill style={{ backgroundImage: `repeating-linear-gradient(0deg, ${bg.grid} 0 2px, transparent 2px ${step}px), repeating-linear-gradient(90deg, ${bg.grid} 0 2px, transparent 2px ${step}px)` }} />
    </AbsoluteFill>
  );
};

/* Designs 3 and 4, the blurred photo (mirrors blur_layer / blur_tweens in motion_layout.py): the scene's own picture, blurred and pushed
   in, under a pale veil so the dark words stay readable on any picture. It arrives zooming out of a heavy blur, drifts, then
   rushes forward into blur as the scene ends (a zoom-through into the next one), and a soft accent band sweeps across at the cut. */
const BlurBackdrop = ({ photo, accent, veil = 0.66, blurPx = 30 }) => {
  const frame = useCurrentFrame();
  const { fps, width: W, durationInFrames: D } = useVideoConfig();
  const u = W / 1080;
  const inEnd = Math.round(fps * 0.9), outLen = Math.round(fps * 0.4);
  const expo = Easing.out(Easing.exp);
  let scale, blur;
  if (frame < inEnd) {
    const t = interpolate(frame, [0, inEnd], [0, 1], { ...clamp, easing: expo });
    scale = 1.35 + (1.12 - 1.35) * t;
    blur = blurPx * 2 + (blurPx - blurPx * 2) * t;
  } else {
    scale = interpolate(frame, [inEnd, Math.max(inEnd + 1, D - outLen)], [1.12, 1.22], clamp);
    blur = blurPx;
  }
  const rush = interpolate(frame, [D - outLen, D], [0, 1], { ...clamp, easing: Easing.in(Easing.quad) });
  scale += (1.55 - scale) * rush;
  blur += (blurPx * 2 + 10 - blur) * rush;
  const sweep = interpolate(frame, [0, Math.round(fps * 0.65)], [0, 1], { ...clamp, easing: Easing.in(Easing.cubic) });
  const drift = interpolate(frame, [inEnd, D], [0, -3], clamp);
  return (
    <AbsoluteFill style={{ overflow: "hidden" }}>
      <Img src={staticFile(photo)} style={{ position: "absolute", left: "-8%", top: "-8%", width: "116%", height: "116%", objectFit: "cover",
        transform: `translateX(${drift}%) scale(${scale})`, filter: `blur(${blur * u}px) saturate(1.2)` }} />
      <AbsoluteFill style={{ background: `rgba(255,255,255,${veil})` }} />
      <div style={{ position: "absolute", left: 0, top: 0, width: "16%", height: "100%", opacity: 1 - sweep,
        transform: `translateX(${-130 + (640 + 130) * sweep}%)`, background: `linear-gradient(90deg, transparent, ${accent}8c, transparent)` }} />
    </AbsoluteFill>
  );
};

const Scene = ({ scene, palette, design, backdrop }) => {
  const frame = useCurrentFrame();
  const { fps, width: W, height: H, durationInFrames: D } = useVideoConfig();
  const u = W / 1080;
  const tall = H > W;
  const out = interpolate(frame, [D - 8, D], [1, 0], clamp);
  const zoom = interpolate(frame, [0, D], [1.03, 1.1], clamp);
  /* the safe box of motion_layout.py: 8% in from the left, 14% from the right, 13% from the top, down to the subtitle lane */
  const boxW = W * 0.78, boxTop = H * (tall ? 0.13 : 0.11), boxH = H * 0.76 - boxTop - H * 0.02;
  const lines = (scene.lines || []).slice(0, 4);
  const bd = 84 * u;
  /* a scene with no sharp picture (every Design 4 scene) is set as large as motion_layout.py sets it: the type starts big by the
     heading's length, a sparse scene a little bigger still, and is brought down until the column holds it */
  const noPic = !scene.photo || design === "blur-full";
  const nWords = String(scene.heading || "").split(/\s+/).filter(Boolean).length;
  const sparse = noPic && nWords + lines.join(" ").split(/\s+/).filter(Boolean).length <= 14;
  const headMax = noPic ? (nWords <= 4 ? 128 : nWords <= 7 ? 108 : nWords <= 11 ? 88 : 66) * u * (sparse ? 1.25 : 1) : 64 * u;
  const lineMax = noPic ? 62 * u * (sparse ? 1.2 : 1) : 46 * u;
  const head = sizeFor(scene.heading, headMax, 46 * u, boxW, boxH * (noPic ? 0.4 : 0.3), WIDE, 1.12);
  const lineW = boxW - bd - 22 * u;
  const lineSize = sizeFor(lines.join(" "), lineMax, 38 * u, lineW, boxH * (noPic ? 0.42 : 0.3), BODY, 1.2);
  const step = Math.max(8, Math.floor(Math.min(fps * 1.1, (D - fps) / Math.max(lines.length, 1))));
  const photo = scene.photo && design !== "blur-full" ? (
    <Rise at={8} style={{ flex: "1 1 0", minHeight: 0, width: "100%", position: "relative", overflow: "hidden",
        WebkitMaskImage: "linear-gradient(to right, transparent, #000 14%, #000 86%, transparent), linear-gradient(to bottom, transparent, #000 16%, #000 84%, transparent)",
        WebkitMaskComposite: "source-in", maskComposite: "intersect",
        maskImage: "linear-gradient(to right, transparent, #000 14%, #000 86%, transparent), linear-gradient(to bottom, transparent, #000 16%, #000 84%, transparent)" }}>
      <Img src={staticFile(scene.photo)} style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover", transform: `scale(${zoom})` }} />
    </Rise>
  ) : null;
  const blurred = (design === "blur-photo" || design === "blur-full") && !!scene.photo;
  const punch = blurred ? interpolate(frame, [0, Math.round(fps * 0.8)], [0.965, 1], { ...clamp, easing: Easing.out(Easing.exp) }) : 1;
  return (
    <>
    {blurred ? <BlurBackdrop photo={scene.photo} accent={palette.accent} veil={backdrop?.veil} blurPx={backdrop?.blur} /> : null}
    <AbsoluteFill style={{ color: palette.ink, fontFamily: FONT, opacity: out, transform: punch === 1 ? undefined : `scale(${punch})` }}>
      <div style={{ position: "absolute", left: W * 0.08, top: boxTop, width: boxW, height: boxH, display: "flex",
                    flexDirection: "column", justifyContent: "space-evenly", alignItems: "flex-start", gap: W * 0.028, overflow: "hidden" }}>
        <Rise at={2} style={{ fontSize: head, fontWeight: 800, lineHeight: 1.12, overflowWrap: "anywhere", maxWidth: "100%", flex: "none" }}>{scene.heading}</Rise>
        {photo}
        {lines.length ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 18 * u, flex: "none", width: "100%" }}>
            {lines.map((line, i) => (
              <Rise key={i} at={Math.round(fps * 0.6) + i * step} style={{ position: "relative", paddingLeft: bd + 22 * u, minHeight: bd, display: "flex", alignItems: "center" }}>
                <span style={{ position: "absolute", left: 0, top: "50%", transform: "translateY(-50%)", width: bd, height: bd, borderRadius: "50%", background: palette.accent,
                               color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 800, fontSize: 46 * u }}>{i + 1}</span>
                <span style={{ fontSize: lineSize, lineHeight: 1.2, fontWeight: 600, overflowWrap: "anywhere" }}>{line}</span>
              </Rise>
            ))}
          </div>
        ) : null}
      </div>
    </AbsoluteFill>
    </>
  );
};

/* the subtitle lane of motion_layout.py: 78% down, 11.5% tall, centred, medium weight, shrunk until it fits */
const Caption = ({ text, ink }) => {
  const { width: W, height: H } = useVideoConfig();
  const u = W / 1080;
  const boxW = W * 0.78, laneH = H * 0.115;
  const size = sizeFor(text, 52 * u, 44 * u, boxW, laneH, BODY, 1.3);
  return (
    <div style={{ position: "absolute", left: W * 0.08, top: H * 0.78, width: boxW, height: laneH, display: "flex", alignItems: "center",
                  justifyContent: "center", textAlign: "center", fontFamily: FONT, fontWeight: 500, fontSize: size, lineHeight: 1.3, color: ink, overflowWrap: "anywhere" }}>
      <span style={{ display: "block", maxWidth: "100%" }}>{text}</span>
    </div>
  );
};

/* the closing card: the ws.regulab logo file itself and the follow line; on LinkedIn Wan's own icon, his name and the line */
const Outro = ({ outro }) => {
  const { width: W } = useVideoConfig();
  const u = W / 1080;
  const brand = !!outro.brand;
  return (
    <AbsoluteFill style={{ background: brand ? "#e5f6ed" : "#f5f7fb", color: brand ? "#143e35" : "#111827", fontFamily: FONT, alignItems: "center",
                           justifyContent: "center", textAlign: "center", padding: 90 * u, gap: 40 * u }}>
      {outro.logo ? (
        <Rise style={{ width: brand ? "64%" : "50%" }}>
          <Img src={staticFile(outro.logo)} style={{ width: "100%", height: "auto", objectFit: "contain" }} />
        </Rise>
      ) : null}
      {outro.name && (!brand || !outro.logo) ? <Rise at={4} style={{ fontSize: 54 * u, fontWeight: 700 }}>{outro.name}</Rise> : null}
      {outro.line ? <Rise at={8} style={{ fontSize: 54 * u, color: brand ? "#143e35" : "#0f5d4a" }}>{outro.line}</Rise> : null}
    </AbsoluteFill>
  );
};

export const Film = ({ scenes, palette, outro, fps, bg, design, backdrop }) => {
  useFonts();
  const f = (s) => Math.round(s * fps);
  return (
    <AbsoluteFill style={{ background: palette.ground, color: palette.ink }}>
      {bg ? <Backdrop bg={bg} /> : null}
      {scenes.map((s) => (
        <Sequence key={s.id} from={f(s.start)} durationInFrames={Math.max(1, f(s.duration))}>
          {s.id === "brand-outro" && outro ? <Outro outro={outro} /> : <Scene scene={s} palette={palette} design={design} backdrop={backdrop} />}
        </Sequence>
      ))}
      {scenes.flatMap((s) => (s.captions || []).map(([text, a, b], i) => (
        <Sequence key={`${s.id}-c${i}`} from={f(a)} durationInFrames={Math.max(1, f(b) - f(a))}>
          <Caption text={text} ink={palette.ink} />
        </Sequence>
      )))}
    </AbsoluteFill>
  );
};
