"use client";

/* Progress family (pasted by Wan on 27 Sep 2026). In Semasa, ShimmerProgress shows a job the worker is still on and
   SegmentedProgress how far a Wangian design has come (pages/FragranceTab.jsx, components/GenerationGallery.jsx).
   Unchanged from the paste except this note: its colours come from --primary-foreground, --info, --brand and
   --success, which src/index.css defines for every Semasa theme, and bg-info from tailwind.config.js. */

import type * as React from "react";
import { motion, useReducedMotion } from "motion/react";

import { cn } from "@/lib/utils";

/* Progress family: 5 decorative progress bars. Colour comes ONLY from tokens (alpha via color-mix). Size = the track height. value is 0-100 (Shimmer is indeterminate and takes no value). framer-motion drives the fill width and the sweeps; under reduced-motion the fill snaps into place and the sweeps stop. */

export type StyledSize = "sm" | "md" | "lg" | "xl";

const track: Record<StyledSize, string> = {
  sm: "h-1",
  md: "h-1.5",
  lg: "h-2.5",
  xl: "h-3.5",
};

const trackBase =
  "relative w-56 max-w-full overflow-hidden rounded-full bg-secondary";

type Props = React.ComponentProps<"div"> & {
  size?: StyledSize;
  value?: number;
  label?: string;
};

function clamp(v: number) {
  return Math.max(0, Math.min(100, v));
}

/* Striped: token cizgili dolgu, cizgiler surekli kayar. */
export function StripedProgress({
  className,
  size = "md",
  value = 60,
  label = "Progress",
  ...props
}: Props) {
  const reduce = useReducedMotion();
  const v = clamp(value);
  return (
    <div
      data-slot="styled-progress"
      role="progressbar"
      aria-valuenow={v}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label}
      className={cn(trackBase, track[size], className)}
      {...props}
    >
      <motion.span
        className="absolute inset-y-0 left-0 bg-primary [background-image:repeating-linear-gradient(45deg,color-mix(in_oklab,var(--primary-foreground)_25%,transparent)_0,color-mix(in_oklab,var(--primary-foreground)_25%,transparent)_6px,transparent_6px,transparent_12px)] [background-size:17px_100%]"
        initial={reduce ? false : { width: 0 }}
        animate={
          reduce
            ? { width: `${v}%` }
            : { width: `${v}%`, backgroundPositionX: ["0px", "17px"] }
        }
        transition={
          reduce
            ? undefined
            : {
                width: { duration: 0.8, ease: "easeOut" },
                backgroundPositionX: {
                  duration: 0.6,
                  ease: "linear",
                  repeat: Infinity,
                },
              }
        }
      />
    </div>
  );
}

/* Gradient: cok tonlu token gradyan dolgu. */
export function GradientProgress({
  className,
  size = "md",
  value = 60,
  label = "Progress",
  ...props
}: Props) {
  const reduce = useReducedMotion();
  const v = clamp(value);
  return (
    <div
      data-slot="styled-progress"
      role="progressbar"
      aria-valuenow={v}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label}
      className={cn(trackBase, track[size], className)}
      {...props}
    >
      <motion.span
        className="absolute inset-y-0 left-0 rounded-full [background-image:linear-gradient(90deg,var(--info),var(--brand),var(--success))]"
        initial={reduce ? false : { width: 0 }}
        animate={{ width: `${v}%` }}
        transition={reduce ? undefined : { duration: 0.8, ease: "easeOut" }}
      />
    </div>
  );
}

/* Glow: token dolgu, ilerledikce isir (box-shadow). */
export function GlowProgress({
  className,
  size = "md",
  value = 60,
  label = "Progress",
  ...props
}: Props) {
  const reduce = useReducedMotion();
  const v = clamp(value);
  return (
    <div
      data-slot="styled-progress"
      role="progressbar"
      aria-valuenow={v}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label}
      className={cn(trackBase, track[size], className)}
      {...props}
    >
      <motion.span
        className="absolute inset-y-0 left-0 rounded-full bg-info shadow-[0_0_10px_0_var(--info)]"
        initial={reduce ? false : { width: 0 }}
        animate={{ width: `${v}%` }}
        transition={reduce ? undefined : { duration: 0.8, ease: "easeOut" }}
      />
    </div>
  );
}

/* Segmented: ayrik token bloklar; dolu olanlar value orant. */
export function SegmentedProgress({
  className,
  size = "md",
  value = 60,
  label = "Progress",
  ...props
}: Props) {
  const v = clamp(value);
  const total = 10;
  const filled = Math.round((v / 100) * total);
  return (
    <div
      data-slot="styled-progress"
      role="progressbar"
      aria-valuenow={v}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label}
      className={cn("flex w-56 max-w-full gap-1", track[size], className)}
      {...props}
    >
      {Array.from({ length: total }).map((_, i) => (
        <span
          key={i}
          className={cn(
            "h-full flex-1 rounded-full",
            i < filled ? "bg-primary" : "bg-secondary",
          )}
        />
      ))}
    </div>
  );
}

/* Shimmer: belirsiz durum - token parlama iz boyunca surekli supurur. */
export function ShimmerProgress({
  className,
  size = "md",
  label = "Loading",
  ...props
}: Omit<Props, "value">) {
  const reduce = useReducedMotion();
  return (
    <div
      data-slot="styled-progress"
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      className={cn(trackBase, track[size], className)}
      {...props}
    >
      {reduce ? (
        <span className="absolute inset-y-0 left-0 w-2/5 rounded-full bg-primary" />
      ) : (
        <motion.span
          className="absolute inset-y-0 w-2/5 rounded-full bg-primary"
          animate={{ left: ["-40%", "100%"] }}
          transition={{ duration: 1.3, ease: "easeInOut", repeat: Infinity }}
        />
      )}
    </div>
  );
}

export default StripedProgress;
