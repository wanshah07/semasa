/* Semasa's film drawn by Remotion. Everything on screen comes from the props the worker writes (motion_remotion.py):
   the same scenes, times, words, pictures and palette the HyperFrames renderer gets. No sound here: the worker mixes the
   recorded voice and the music onto the rendered video afterwards, exactly as it does for HyperFrames. */
import React from "react";
import { AbsoluteFill, Img, Sequence, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";

const FONT = '"Inter", system-ui, -apple-system, "Segoe UI", sans-serif';
const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" };

/* one size for a block of text that must fit a box: shorter text is larger, long text steps down, never below `min` */
const fit = (text, max, min, perLine, lines) => {
  const need = Math.ceil(String(text || "").length / perLine);
  return Math.max(min, Math.min(max, max * Math.sqrt(lines / Math.max(need, 1))));
};

const Rise = ({ at = 0, children, style }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame: frame - at, fps, config: { damping: 200 } });
  return <div style={{ opacity: s, transform: `translateY(${(1 - s) * 40}px)`, ...style }}>{children}</div>;
};

const Scene = ({ scene, palette, index, count }) => {
  const frame = useCurrentFrame();
  const { fps, width: W, height: H, durationInFrames: D } = useVideoConfig();
  const u = W / 1080;
  const tall = H > W;
  const out = interpolate(frame, [D - 8, D], [1, 0], clamp);
  const zoom = interpolate(frame, [0, D], [1.04, 1.12], clamp);
  const head = fit(scene.heading, (tall ? 76 : 56) * u, (tall ? 46 : 38) * u, tall ? 20 : 18, 4);
  const lines = (scene.lines || []).slice(0, 3);
  const lineSize = fit(lines.join(" "), (tall ? 44 : 34) * u, (tall ? 30 : 26) * u, tall ? 30 : 28, tall ? 6 : 5);
  const step = Math.max(8, Math.floor(Math.min(fps * 1.2, (D - fps) / Math.max(lines.length, 1))));
  const photo = scene.photo ? (
    <Rise at={10} style={{ alignSelf: "center", width: tall ? "62%" : "100%", flex: tall ? "1 1 0" : "none",
                           height: tall ? undefined : "92%", minHeight: 0, overflow: "hidden",
                           borderRadius: `${999 * u}px ${999 * u}px ${28 * u}px ${28 * u}px`,
                           boxShadow: `0 ${18 * u}px ${50 * u}px rgba(0,0,0,.18)` }}>
      <Img src={staticFile(scene.photo)} style={{ width: "100%", height: "100%", objectFit: "cover",
                                                   transform: `scale(${zoom})` }} />
    </Rise>
  ) : null;
  const heading = <Rise at={4} style={{ fontSize: head, fontWeight: 800, lineHeight: 1.12 }}>{scene.heading}</Rise>;
  const points = (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 * u }}>
      {lines.map((line, i) => (
        <Rise key={i} at={fps * 0.6 + i * step}
              style={{ fontSize: lineSize, lineHeight: 1.25, fontWeight: 600, paddingLeft: 22 * u,
                       borderLeft: `${6 * u}px solid ${palette.accent}` }}>
          {line}
        </Rise>
      ))}
    </div>
  );
  /* the content stops at 76% of the height: the subtitle lane below it is never met. Upright: one column with the picture
     between the heading and the points. Square or wide: the words on the left, the picture on the right. */
  const box = { position: "absolute", left: 72 * u, right: 72 * u, top: H * 0.07, height: H * 0.69 };
  return (
    <AbsoluteFill style={{ background: palette.ground, color: palette.ink, fontFamily: FONT, opacity: out }}>
      {tall ? (
        <div style={{ ...box, display: "flex", flexDirection: "column", gap: 28 * u }}>
          {heading}{photo || <div style={{ flex: "1 1 0" }} />}{points}
        </div>
      ) : (
        <div style={{ ...box, display: "flex", gap: 40 * u, alignItems: "center" }}>
          <div style={{ flex: photo ? "0 0 60%" : "1 1 0", display: "flex", flexDirection: "column", gap: 22 * u }}>
            {heading}{points}
          </div>
          {photo ? <div style={{ flex: "1 1 0", height: "100%", display: "flex", alignItems: "center" }}>{photo}</div> : null}
        </div>
      )}
      <div style={{ position: "absolute", left: 72 * u, right: 72 * u, top: H * 0.035, display: "flex", gap: 8 * u }}>
        {Array.from({ length: count }).map((_, i) => (
          <div key={i} style={{ flex: 1, height: 6 * u, borderRadius: 6, background: palette.accent,
                                opacity: i < index ? 0.9 : i > index ? 0.22 : 1, overflow: "hidden" }}>
            {i === index ? <div style={{ width: `${(frame / D) * 100}%`, height: "100%", background: palette.ink }} /> : null}
          </div>
        ))}
      </div>
    </AbsoluteFill>
  );
};

const Caption = ({ text }) => {
  const { width: W, height: H } = useVideoConfig();
  const u = W / 1080;
  const size = fit(text, 52 * u, 34 * u, H > W ? 34 : 44, 2);
  return (
    <div style={{ position: "absolute", left: 72 * u, right: 72 * u, top: H * 0.78, height: H * 0.115, display: "flex",
                  alignItems: "center", justifyContent: "center", textAlign: "center", fontFamily: FONT, fontWeight: 700,
                  fontSize: size, lineHeight: 1.3 }}>
      {text}
    </div>
  );
};

/* the closing card: the ws.regulab logo itself (never the name typed out) and the follow line; on LinkedIn Wan's own icon,
   his name and the follow line, with no brand at all */
const Outro = ({ outro }) => {
  const { width: W } = useVideoConfig();
  const u = W / 1080;
  const brand = !!outro.brand;
  return (
    <AbsoluteFill style={{ background: brand ? "#e5f6ed" : "#f5f7fb", color: brand ? "#143e35" : "#111827", fontFamily: FONT,
                           alignItems: "center", justifyContent: "center", textAlign: "center", padding: 90 * u, gap: 36 * u }}>
      {outro.logo ? (
        <Rise style={{ width: brand ? "64%" : "50%" }}>
          <Img src={staticFile(outro.logo)} style={{ width: "100%", height: "auto", objectFit: "contain" }} />
        </Rise>
      ) : null}
      {outro.name && (!brand || !outro.logo) ? <Rise at={4} style={{ fontSize: 54 * u, fontWeight: 700 }}>{outro.name}</Rise> : null}
      {outro.line ? <Rise at={8} style={{ fontSize: 50 * u, color: brand ? "#143e35" : "#0f5d4a" }}>{outro.line}</Rise> : null}
    </AbsoluteFill>
  );
};

export const Film = ({ scenes, palette, outro, fps }) => {
  const f = (s) => Math.round(s * fps);
  const shown = scenes.filter((s) => s.id !== "brand-outro");
  return (
    <AbsoluteFill style={{ background: palette.ground, color: palette.ink }}>
      {scenes.map((s) => (
        <Sequence key={s.id} from={f(s.start)} durationInFrames={Math.max(1, f(s.duration))}>
          {s.id === "brand-outro" && outro
            ? <Outro outro={outro} />
            : <Scene scene={s} palette={palette} index={shown.indexOf(s)} count={shown.length} />}
        </Sequence>
      ))}
      {scenes.flatMap((s) => (s.captions || []).map(([text, a, b], i) => (
        <Sequence key={`${s.id}-c${i}`} from={f(a)} durationInFrames={Math.max(1, f(b) - f(a))}>
          <Caption text={text} />
        </Sequence>
      )))}
    </AbsoluteFill>
  );
};
