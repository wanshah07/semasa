import { useMemo } from "react";

/* A lightweight preview of the Threads-style design (backend/semasa/threads_slides.py). It follows the worker's plan: the page
   number in a solid box at the top right, the words, the picture under them (beside them on a wide page), and a row of connected
   dots at the foot with this page's dot filled. It is drawn with CSS in this browser, from an original abstract picture: the
   worker draws the real pages (and puts your own picture there when there is one), so this is a guide to the layout, not a proof
   that the words fit; the rules in lib/threadsSlides.js say that. Sizes are in container units, so the proportions hold at any width. */

const PAPER = "#FAF7F2", INK = "#1C1917", MUTED = "#6E6762", ACCENT = "#B0792A", ACCENT_TEXT = "#855612", PANEL = "#EEE5D6", EDGE = "#C4B8A6";

/* The words, with one *marked* word in the accent colour, as the worker draws them. */
function Words({ text }) {
  const parts = useMemo(() => String(text || "").split(/(\*[^*\n]+\*)/g).filter(Boolean), [text]);
  return parts.map((p, i) => (/^\*[^*\n]+\*$/.test(p)
    ? <span key={i} style={{ color: ACCENT_TEXT }}>{p.slice(1, -1)}</span> : <span key={i}>{p}</span>));
}

/* The original drawing for a page with no picture: shapes in the page's own colours, placed by the page's number. */
function Art({ index, total }) {
  const x = total > 1 ? 28 + 44 * (index / (total - 1)) : 50;
  return (
    <svg viewBox="0 0 100 60" preserveAspectRatio="xMidYMid slice" className="h-full w-full" aria-hidden="true">
      <rect width="100" height="60" fill={PANEL} />
      <circle cx={x} cy="26" r="21" fill={INK} />
      <circle cx={x} cy="26" r="13" fill={ACCENT} />
      <rect x="8" y="46" width="34" height="2.4" fill={INK} />
      <rect x="14" y="52" width="26" height="2.4" fill={PAPER} />
    </svg>
  );
}

/** One page. `ratio` is "W / H" (the page's own shape); `cover` pages use the larger headline. */
export function ThreadsPage({ page, index = 0, total = 1, ratio = "1080 / 1350", photo = "", label = "" }) {
  const [W, H] = String(ratio).split("/").map((x) => Number(x) || 1);
  const wide = W > H * 1.15;
  const cover = index === 0;
  const points = (page?.points || []).filter(Boolean);
  const dot = (on) => ({ width: "1.9cqw", height: "1.9cqw", borderRadius: "50%", background: on ? INK : PAPER, border: `0.28cqw solid ${on ? INK : MUTED}` });
  return (
    <div style={{ aspectRatio: ratio, containerType: "inline-size", background: PAPER, color: INK }} className="relative w-full overflow-hidden">
      <div style={{ position: "absolute", inset: "6.7cqw", display: "flex", flexDirection: "column", gap: "3cqw" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: "2.2cqw", fontWeight: 600, minHeight: "4.8cqw" }}>
          <span style={{ color: ACCENT_TEXT, overflow: "hidden", whiteSpace: "nowrap", textOverflow: "ellipsis", maxWidth: "70%" }}>{label}</span>
          <span style={{ background: INK, color: PAPER, borderRadius: "1cqw", padding: "0.9cqw 1.8cqw" }}>{index + 1}/{total}</span>
        </div>
        <div style={{ display: "flex", flex: 1, minHeight: 0, flexDirection: wide ? "row" : "column", gap: "3cqw" }}>
          <div style={{ flex: "1 1 56%", minWidth: 0, minHeight: 0, overflow: "hidden" }}>
            <p style={{ fontFamily: "Georgia, serif", fontWeight: 700, lineHeight: 1.14, fontSize: cover ? "8.1cqw" : "5.7cqw", margin: 0, overflowWrap: "anywhere" }}>
              <Words text={page?.title} /></p>
            {points.map((p, i) => (
              <p key={i} style={{ fontSize: "3.7cqw", lineHeight: 1.4, margin: i ? "1.5cqw 0 0" : "2.6cqw 0 0", color: index ? INK : MUTED, overflowWrap: "anywhere" }}>
                <Words text={p} /></p>
            ))}
          </div>
          <div style={{ flex: wide ? "0 0 44%" : "0 0 40%", minWidth: 0, minHeight: 0, borderRadius: "2.6cqw", overflow: "hidden", border: `0.2cqw solid ${EDGE}` }}>
            {photo ? <img src={photo} alt="" style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }} /> : <Art index={index} total={total} />}
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "3.2cqw", minHeight: "4cqw" }} aria-hidden="true">
          {Array.from({ length: total }, (_, i) => <span key={i} style={dot(i === index)} />)}
        </div>
      </div>
    </div>
  );
}

/** The set, as a row of pages like the other designs' strip. */
export default function ThreadsStrip({ slides, ratio, label = "" }) {
  return (
    <div className="mt-1.5 flex gap-2 overflow-x-auto pb-1" style={{ scrollSnapType: "x mandatory" }}>
      {slides.map((s, i) => (
        <div key={i} className="w-44 shrink-0 overflow-hidden rounded-tile border border-line sm:w-48 lg:w-40" style={{ scrollSnapAlign: "start" }}>
          <ThreadsPage page={s} index={i} total={slides.length} ratio={ratio} label={label} />
        </div>
      ))}
    </div>
  );
}
