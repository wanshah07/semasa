/* Wanshah, the 3D robot mascot (Wan, 20 Oct 2026). The card renderer already picks one of four poses by name; this file is the
   part that makes each pose a generated picture of the same robot, and turns the raw picture into a cut-out the cards can stand
   on a photograph. Pure functions only (no canvas, no network), so node tests cover them; the browser parts are in
   components/WanshahPanel.jsx. */

export const POSES = [
  { k: "wave", bm: "Melambai", en: "Waving", does: "waving one hand in greeting while holding a small clipboard in the other" },
  { k: "point", bm: "Menunjuk", en: "Pointing", does: "pointing with one hand at something just out of frame, looking helpful and sure" },
  { k: "confused", bm: "Keliru", en: "Confused", does: "shrugging both shoulders with palms up and a puzzled tilt of the head, one eyebrow raised" },
  { k: "shocked", bm: "Terkejut", en: "Shocked", does: "bracing in shock, both hands up near the face, eyes wide open" },
];

export const DEFAULT_LOOK = "a friendly 3D-rendered robot mascot named Wanshah: rounded white body with teal accents, big round glowing eyes, "
  + "a small antenna, glossy soft studio lighting, clean modern toy-like style";

/** One prompt per pose. The character half is the same words every time so the four come out as one robot; the picture is
    asked for on a flat white ground because that is what the cut-out removes. */
export function buildPrompt(pose, look) {
  const p = POSES.find((x) => x.k === pose);
  if (!p) throw new Error(`unknown pose ${pose}`);
  const who = String(look || "").trim() || DEFAULT_LOOK;
  return `${who}. Full body, centred, ${p.does}. Plain flat pure white background, no floor, no shadow on the ground, no text, no logo.`;
}

/** Make the background transparent: flood inward from every edge pixel that is near the corner colour, so white inside the robot
    (an eye, a glove) is kept and only the outside goes. `rgba` is a Uint8ClampedArray of w*h*4, changed in place.
    Returns how many pixels were cleared. A picture whose corners disagree has no flat ground and is left untouched (-1). */
export function floodTransparent(rgba, w, h, tol = 38) {
  const at = (x, y) => (y * w + x) * 4;
  const corners = [at(0, 0), at(w - 1, 0), at(0, h - 1), at(w - 1, h - 1)].map((i) => [rgba[i], rgba[i + 1], rgba[i + 2]]);
  const dist = (a, b) => Math.max(Math.abs(a[0] - b[0]), Math.abs(a[1] - b[1]), Math.abs(a[2] - b[2]));
  const bg = corners[0];
  if (corners.some((c) => dist(c, bg) > tol)) return -1;
  const seen = new Uint8Array(w * h);
  const stack = [];
  const push = (x, y) => {
    if (x < 0 || y < 0 || x >= w || y >= h) return;
    const k = y * w + x;
    if (seen[k]) return;
    const i = k * 4;
    if (dist([rgba[i], rgba[i + 1], rgba[i + 2]], bg) > tol) return;
    seen[k] = 1; stack.push(k);
  };
  for (let x = 0; x < w; x++) { push(x, 0); push(x, h - 1); }
  for (let y = 0; y < h; y++) { push(0, y); push(w - 1, y); }
  let n = 0;
  while (stack.length) {
    const k = stack.pop(), x = k % w, y = (k - x) / w;
    rgba[k * 4 + 3] = 0; n++;
    push(x + 1, y); push(x - 1, y); push(x, y + 1); push(x, y - 1);
  }
  // one soft pixel along the edge so the cut is not jagged
  for (let y = 1; y < h - 1; y++) for (let x = 1; x < w - 1; x++) {
    const k = y * w + x;
    if (seen[k]) continue;
    if (seen[k - 1] || seen[k + 1] || seen[k - w] || seen[k + w]) rgba[k * 4 + 3] = Math.min(rgba[k * 4 + 3], 190);
  }
  return n;
}

/** The box that holds everything still visible, so the pose is stored cropped (a robot in the middle of a white square would
    otherwise be drawn tiny). null when nothing is left. */
export function opaqueBox(rgba, w, h) {
  let x0 = w, y0 = h, x1 = -1, y1 = -1;
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    if (rgba[(y * w + x) * 4 + 3] > 16) { if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y; }
  }
  return x1 < 0 ? null : { x: x0, y: y0, w: x1 - x0 + 1, h: y1 - y0 + 1 };
}

/** Which approved pictures stand in for which poses, from the `wanshah` settings row. Anything not an https address is ignored. */
export function approvedPoses(row) {
  const out = {};
  const poses = row && typeof row === "object" && row.poses && typeof row.poses === "object" ? row.poses : {};
  for (const p of POSES) {
    const u = poses[p.k]?.url;
    if (typeof u === "string" && /^https:\/\//.test(u)) out[p.k] = u;
  }
  return out;
}
