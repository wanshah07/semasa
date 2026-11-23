/* A carousel is under 10 pictures (Wan, 23 Nov 2026: "limitkan slide less 10"). ws.regulab gets the brand cover in front and the
   logo card at the end, so 7 written slides; LinkedIn has neither, so 9. The browser twin of carousel.compact / join /
   fit_points: neighbouring slides with the fewest words are joined (never the first, never the last), every word is kept, and a
   join that would be too dense to read is not made. Slides here are {title, lead?, points: [], note?, foot?, ...design keys}. */

export const MAX_PICTURES = 9;
export const writtenCap = (stream) => MAX_PICTURES - (stream === "linkedin" ? 0 : 2);
export const MAX_POINTS = 5;                 // compliance.MAX_POINTS: points on one slide
export const DENSE = 420;                    // a joined slide holds at most this many characters, or it stays two (still readable)

const clean = (x) => String(x ?? "").replace(/\s+/g, " ").trim();
const sentence = (title, lead) => { const t = clean(title), l = clean(lead); return !l ? t : !t ? l : `${t}${/[.!?:;]$/.test(t) ? " " : ". "}${l}`; };
const chars = (s) => clean(s.title).length + clean(s.lead).length + clean(s.note).length + (s.points || []).reduce((n, p) => n + clean(p).length, 0);

/** At most `most` points, no word lost: the two neighbours with the fewest letters become one ("first; second"). */
export function fitPoints(points, most = MAX_POINTS) {
  const pts = points.slice();
  while (pts.length > most && most >= 1) {
    let at = 0, best = Infinity;
    for (let k = 0; k < pts.length - 1; k += 1) { const w = pts[k].length + pts[k + 1].length; if (w < best) { best = w; at = k; } }
    const b = pts[at + 1];
    pts.splice(at, 2, `${pts[at].replace(/[.;:\s]+$/, "")}; ${b.charAt(0).toLowerCase()}${b.slice(1)}`);
  }
  return pts;
}

/** Two neighbouring slides as one, or null: a verse is never folded into another slide, and a join too dense to read is refused. */
export function joinSlides(a, b) {
  if (a.ayat || b.ayat) return null;
  const pts = fitPoints([clean(a.lead), ...(a.points || []), sentence(b.title, b.lead), ...(b.points || []), clean(b.note)]
    .map(clean).filter(Boolean));
  const { title, lead, points, note, foot, ...keep } = a; // eslint-disable-line no-unused-vars
  const feet = [a.foot, b.foot].map(clean).filter(Boolean);
  const joined = { ...keep, title: a.title, points: pts, ...(feet.length ? { foot: feet[0] } : {}) };
  return chars(joined) > DENSE ? null : joined;
}

/** The set joined down to `target` slides. {slides, joined}: stops early when no further join is readable. */
export function limitSlides(slides, target) {
  const out = slides.map((s) => ({ ...s }));
  let joined = 0;
  while (out.length > target && out.length >= 4) {
    let best = null;
    for (let i = 1; i < out.length - 2; i += 1) {
      const m = joinSlides(out[i], out[i + 1]);
      if (!m) continue;
      const w = chars(out[i]) + chars(out[i + 1]);
      if (!best || w < best.w) best = { w, i, m };
    }
    if (!best) break;
    out.splice(best.i, 2, best.m);
    joined += 1;
  }
  return { slides: out, joined };
}
