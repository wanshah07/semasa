/* The Whiteboard style, drawn by hand (Wan, 11 Nov 2026: the lemo-opuscar pilot is "better and more aesthetic, if can apply for
   option 1 that is great"). The film's own scenes are written stroke by stroke on one long board by floating markers, with
   lemo-opuscar's whiteboard engine (vendor/opuscar, MIT): real marker ink, a glossy board, a camera that travels down the board
   from scene to scene and pulls back at the end to show the whole lesson. Nothing here is written by an AI at render time: the
   worker's scenes (heading, lines, picture, times) are laid out by the fixed rules below, so every film fits.
   Navy is for headings, teal for the points, red for the one mark that matters in each scene. */
import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { continueRender, delayRender, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import * as WB from "./vendor/opuscar/wb.js";
import font from "./vendor/opuscar/EMSTech.json";

const NAVY = "#1f2a44", TEAL = "#1f8a8a", RED = "#c8363a", GREEN = "#2e8b57";
const CX = 1500, COL = 900;                         // the column every scene is written in, in board units (1 = 1px at 1080 wide)

/* the lettering has Latin letters, digits and common signs: anything else is brought to its nearest plain form */
const plain = (s) => String(s || "").normalize("NFKD").replace(/[̀-ͯ]/g, "").replace(/[‘’]/g, "'").replace(/[“”]/g, '"')
  .replace(/[–—]/g, "-").replace(/…/g, "...").replace(/\*/g, "").replace(/\s+/g, " ").trim();
const widthOf = (str, h) => { let w = 0; for (const ch of str) w += (font.glyphs[ch] || font.glyphs["?"]).w * (h / 677); return w; };
const wrap = (str, h, maxW) => {
  const out = []; let cur = "";
  for (const word of plain(str).split(" ").filter(Boolean)) {
    const next = cur ? cur + " " + word : word;
    if (cur && widthOf(next, h) > maxW) { out.push(cur); cur = word; } else cur = next;
  }
  if (cur) out.push(cur);
  return out;
};

/* one scene's block: sizes come down together until it fits the room between the top margin and the subtitle lane */
function measure(scene, room, hasPic) {
  for (const k of [1, 0.92, 0.84, 0.76, 0.68, 0.6, 0.52]) {
    const hH = 86 * k, lH = 50 * k, picH = hasPic ? Math.min(460, room * 0.34) * (k < 0.7 ? 0.8 : 1) : 0;
    let head = wrap(scene.heading, hH, COL);
    const lines = (scene.lines || []).slice(0, 3).map((x) => wrap(x, lH, COL - 96 * k)).filter((x) => x.length);
    const headH = head.length * hH * 1.42 + 34 * k;
    const linesH = lines.reduce((n, l) => n + l.length * lH * 1.5 + 30 * k, 0);
    const total = headH + (picH ? picH + 56 * k : 0) + linesH;
    if (total <= room || k === 0.52) return { k, hH, lH, picH, head, lines, total };
  }
  return null;
}

export function buildBoard(scenes, W, H, images) {
  WB.setScreen(W, H); WB.resetSeed(); WB.setFont("tech", font.glyphs);
  const z = W / 1080, visH = H / z, top = visH * 0.13, room = visH * 0.76 - top - 40;
  const tl = new WB.Timeline();
  const N = new WB.Pen("navy", NAVY, { park: [W + 190, H * 0.74] });
  const T = new WB.Pen("teal", TEAL, { park: [-190, H * 0.68] });
  const R = new WB.Pen("red", RED, { park: [W + 190, H * 0.3] });
  const G = new WB.Pen("green", GREEN, { park: [-190, H * 0.4] });
  const X0 = CX - COL / 2;
  const pics = [], cams = [];
  const pull = scenes.length > 1 && scenes[scenes.length - 1].duration > 5.5;     // the last scene ends on a pull-back: its writing is done before that
  let y = 400;
  scenes.forEach((sc, i) => {
    const img = sc.photo ? images[sc.photo] : null;
    const m = measure(sc, room, !!img);
    const t0 = sc.start, D = Math.max(2, sc.duration);
    cams.push({ t: t0, y: y - top + visH / 2, y0: y, total: m.total });
    let cy = y;
    // heading: written while the narrator starts, done within the first quarter of the scene
    const headEnd = t0 + Math.min(2.2, D * 0.28);
    const hs = m.head.map((row, r) => WB.text(row, X0, cy + (r + 1) * m.hH * 1.42 - m.hH * 0.3, { h: m.hH, color: NAVY }));
    tl.draw(N, hs, t0 + 0.2, { by: headEnd });
    cy += m.head.length * m.hH * 1.42;
    const lastW = Math.min(COL, widthOf(m.head[m.head.length - 1] || "", m.hH));
    tl.draw(R, WB.curve([[X0 - 6, cy + 6], [X0 + lastW * 0.35, cy - 2], [X0 + lastW * 0.7, cy + 9], [X0 + lastW + 10, cy + 2]], { w: 11 * m.k + 2 }), headEnd + 0.15, { by: headEnd + 0.55 });
    cy += 34 * m.k;
    if (img) {
      const ar = img.naturalWidth / Math.max(1, img.naturalHeight), ph = m.picH, pw = Math.min(COL * 0.86, ph * Math.max(0.8, Math.min(1.6, ar)));
      pics.push({ img, x: CX - pw / 2, y: cy + 14 * m.k, w: pw, h: ph, t: headEnd + 0.5, tilt: (i % 2 ? 1 : -1) * 0.018 });
      tl.cue(headEnd + 0.5, "magnet");
      cy += ph + 56 * m.k;
    }
    // the points: each gets its share of what is left of the scene, a green tick first, then the words in teal
    const from = (img ? headEnd + 1.1 : headEnd + 0.7), left = Math.max(1.2, t0 + D - (pull && i === scenes.length - 1 ? 2.2 : 0.5) - from), per = left / Math.max(1, m.lines.length);
    m.lines.forEach((rows, li) => {
      const a = from + li * per, b = a + Math.min(per * 0.82, 0.5 + rows.join(" ").length * 0.045);
      const ty = cy + m.lH * 1.05;
      tl.draw(G, WB.poly([[X0 + 4, ty - m.lH * 0.42], [X0 + 26 * m.k, ty - m.lH * 0.05], [X0 + 66 * m.k, ty - m.lH * 0.95]], { w: 9 * m.k + 2 }), a, { by: a + 0.22 });
      tl.draw(T, rows.map((row, r) => WB.text(row, X0 + 96 * m.k, ty + r * m.lH * 1.5, { h: m.lH, color: TEAL })), a + 0.25, { by: b });
      cy += rows.length * m.lH * 1.5 + 30 * m.k;
    });
    y += Math.max(m.total + 300, visH * 0.5);
  });
  tl.end();
  // the camera holds on a scene, travels to the next as it starts, and pulls back over the last moments to show the whole board
  const keys = [[0, CX, cams[0].y, z]];
  cams.forEach((c, i) => { if (i) keys.push([c.t - 0.45, CX, cams[i - 1].y, z], [c.t + 0.45, CX, c.y, z]); });
  const last = scenes[scenes.length - 1], end = last.start + last.duration, spanTop = cams[0].y0 - 160, spanBot = cams[cams.length - 1].y0 + cams[cams.length - 1].total + 160;
  if (pull) {
    const zAll = Math.max(0.5 * z, Math.min(z, H / (spanBot - spanTop)));
    keys.push([end - 1.9, CX, cams[cams.length - 1].y, z], [end - 0.6, CX, (spanTop + spanBot) / 2, zAll], [end + 1, CX, (spanTop + spanBot) / 2, zAll]);
  }
  const cam = new WB.Camera(keys);
  const board = new WB.Board(tl, { W: 3000, H: y + 3200, y0: -1400 });
  // the scene's picture, held on the board by two magnets: it drops on, a little tilted
  board.objs.push({ draw: (ctx, t, c) => {
    for (const p of pics) {
      if (t < p.t) continue;
      const u = Math.min(1, (t - p.t) / 0.35), e = 1 - (1 - u) ** 3;
      WB.applyCam(ctx, c);
      ctx.save(); ctx.translate(p.x + p.w / 2, p.y + p.h / 2 - (1 - e) * 40); ctx.rotate(p.tilt * (2 - e)); ctx.globalAlpha = e;
      ctx.shadowColor = "rgba(30,30,45,.28)"; ctx.shadowBlur = 26 + (1 - e) * 30; ctx.shadowOffsetY = 10 + (1 - e) * 24;
      ctx.fillStyle = "#ffffff"; ctx.fillRect(-p.w / 2 - 14, -p.h / 2 - 14, p.w + 28, p.h + 28);
      ctx.shadowColor = "transparent";
      const ar = p.img.naturalWidth / p.img.naturalHeight, br = p.w / p.h;
      let sw = p.img.naturalWidth, sh = p.img.naturalHeight, sx = 0, sy = 0;
      if (ar > br) { sw = sh * br; sx = (p.img.naturalWidth - sw) / 2; } else { sh = sw / br; sy = (p.img.naturalHeight - sh) / 2; }
      ctx.drawImage(p.img, sx, sy, sw, sh, -p.w / 2, -p.h / 2, p.w, p.h);
      for (const mx of [-p.w * 0.36, p.w * 0.36]) {
        ctx.fillStyle = RED; ctx.beginPath(); ctx.arc(mx, -p.h / 2 - 2, 17, 0, Math.PI * 2); ctx.fill();
        ctx.fillStyle = "rgba(255,255,255,.55)"; ctx.beginPath(); ctx.arc(mx - 5, -p.h / 2 - 8, 5, 0, Math.PI * 2); ctx.fill();
      }
      ctx.restore();
    }
  } });
  for (const p of [N, T, R, G]) board.objs.push({ draw: (ctx, t, c) => { const pose = WB.penPose(p, t, cam); if (pose) WB.drawMarker(ctx, p, pose, c, t); } });
  return { render: (ctx, t) => board.render(ctx, t, cam), strokes: tl.strokes.length };
}

export const Handboard = ({ scenes }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const ref = useRef(null);
  const [images, setImages] = useState(null);
  const [handle] = useState(() => delayRender("whiteboard pictures"));
  useEffect(() => {
    const names = [...new Set(scenes.map((s) => s.photo).filter(Boolean))];
    Promise.all(names.map((name) => new Promise((done) => {
      const img = new Image();
      img.onload = () => done([name, img]); img.onerror = () => done([name, null]);     // a picture that will not load is left out
      img.src = staticFile(name);
    }))).then((got) => { setImages(Object.fromEntries(got.filter(([, img]) => img))); continueRender(handle); });
  }, [scenes, handle]);
  const film = useMemo(() => (images ? buildBoard(scenes, width, height, images) : null), [images, scenes, width, height]);
  useLayoutEffect(() => {
    if (!film || !ref.current) return;
    const ctx = ref.current.getContext("2d");
    ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = 1;
    film.render(ctx, frame / fps);
  }, [film, frame, fps]);
  return <canvas ref={ref} width={width} height={height} style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }} />;
};
