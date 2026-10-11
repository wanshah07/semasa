/* Variable font, cursor proximity (Wan, 11 Oct 2026, pasted with a nav example that imported it from a registry this project
   does not have, "@/registry/default/motion/variable-font-cursor-proximity"; this is that piece, written here). Each letter's
   font-variation-settings move from `from…` to `to…` as the cursor comes within `radius` px of it, so the word thickens where
   the pointer is. In Semasa: the sidebar menu labels (components/ui/dashboard-sidebar.tsx).

   How it stays cheap: one pointermove listener per instance writes the pointer into a ref, and one animation frame per
   instance writes each letter's style directly. Nothing goes through React state, so 20 menu labels never re-render on a
   mouse move. When the pointer is outside the container, or the system asks for reduced motion, the letters rest at `from`.
   Screen readers get the word whole (sr-only); the letter spans are aria-hidden. */
"use client";
import * as React from "react";
import { cn } from "@/lib/utils";

type Falloff = "linear" | "exponential" | "gaussian";

type Props = Omit<React.HTMLAttributes<HTMLSpanElement>, "children"> & {
  children: string;
  fromFontVariationSettings: string;
  toFontVariationSettings: string;
  containerRef: React.RefObject<HTMLElement | null>;
  radius?: number;
  falloff?: Falloff;
};

/** "'wght' 300, 'slnt' 0" → Map { wght → 300, slnt → 0 } */
export function parseSettings(s: string): Map<string, number> {
  const out = new Map<string, number>();
  for (const m of String(s || "").matchAll(/['"]([A-Za-z]{4})['"]\s+(-?\d+(?:\.\d+)?)/g)) out.set(m[1], Number(m[2]));
  return out;
}

/** 1 at the letter, 0 at `radius` and beyond. */
export function strength(distance: number, radius: number, falloff: Falloff): number {
  const t = Math.max(0, 1 - distance / Math.max(1, radius));
  if (falloff === "exponential") return t * t;
  if (falloff === "gaussian") return Math.exp(-((distance / Math.max(1, radius)) ** 2) * 4) * (distance <= radius ? 1 : 0);
  return t;
}

export function mixSettings(from: Map<string, number>, to: Map<string, number>, k: number): string {
  const axes = new Set([...from.keys(), ...to.keys()]);
  return [...axes].map((a) => {
    const f = from.get(a) ?? to.get(a) ?? 0;
    const t = to.get(a) ?? f;
    return `'${a}' ${Math.round((f + (t - f) * k) * 10) / 10}`;
  }).join(", ");
}

export function VariableFontCursorProximity({
  children, fromFontVariationSettings, toFontVariationSettings, containerRef, radius = 50, falloff = "linear",
  className, style, ...rest
}: Props) {
  const letters = React.useRef<(HTMLSpanElement | null)[]>([]);
  const pointer = React.useRef<{ x: number; y: number } | null>(null);
  const from = React.useMemo(() => parseSettings(fromFontVariationSettings), [fromFontVariationSettings]);
  const to = React.useMemo(() => parseSettings(toFontVariationSettings), [toFontVariationSettings]);
  const rest0 = React.useMemo(() => mixSettings(from, to, 0), [from, to]);

  React.useEffect(() => {
    const box = containerRef.current;
    const reduce = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (!box || reduce) return undefined;
    let raf = 0;
    let last = "";
    // the loop runs only while the pointer moves over the container, and stops once it is still or gone
    const tick = () => {
      const p = pointer.current;
      const els = letters.current.filter(Boolean) as HTMLSpanElement[];
      if (!p) {
        for (const el of els) el.style.fontVariationSettings = rest0;
        raf = 0;
        return;
      }
      // every position is read before any style is written, so one frame costs one layout, not one per letter
      const centres = els.map((el) => { const r = el.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; });
      els.forEach((el, i) => {
        const d = Math.hypot(p.x - centres[i][0], p.y - centres[i][1]);
        el.style.fontVariationSettings = mixSettings(from, to, strength(d, radius, falloff));
      });
      const here = `${p.x},${p.y}`;
      raf = here === last ? 0 : requestAnimationFrame(tick);     // a still pointer: one settling frame, then stop
      last = here;
    };
    const start = () => { if (!raf) raf = requestAnimationFrame(tick); };
    const move = (e: PointerEvent) => { pointer.current = { x: e.clientX, y: e.clientY }; start(); };
    const leave = () => { pointer.current = null; start(); };
    box.addEventListener("pointermove", move);
    box.addEventListener("pointerleave", leave);
    return () => { cancelAnimationFrame(raf); box.removeEventListener("pointermove", move); box.removeEventListener("pointerleave", leave); };
  }, [containerRef, from, to, rest0, radius, falloff]);

  const chars = Array.from(children);
  letters.current.length = chars.length;            // a shorter label (the language switched) leaves no stale letters
  return (
    <span className={cn("inline", className)} style={style} {...rest}>
      <span className="sr-only">{children}</span>
      <span aria-hidden>
        {chars.map((ch, i) => (
          <span key={i} ref={(el) => { letters.current[i] = el; }} className="inline-block whitespace-pre"
            style={{ fontVariationSettings: rest0 }}>{ch}</span>
        ))}
      </span>
    </span>
  );
}

export default VariableFontCursorProximity;
