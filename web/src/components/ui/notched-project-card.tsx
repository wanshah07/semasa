"use client";

/* Pasted from 21st.dev (Wan, 29 Sep 2026: "add this for card"), with four changes for Semasa, each marked below:
   1. `surface` defaults to Semasa's page colour, rgb(var(--c-bg)). The original read Tailwind 4's --color-background,
      which does not exist under Tailwind 3, so the notch would have been painted transparent and shown.
   2. Tailwind 3 scales through `transform`, not the separate `scale` property Tailwind 4 uses, so the transitions name
      `transform`; with `scale` the hover grew in one jump instead of easing.
   3. Any other <a> attribute (target, rel, download, aria-label) passes through, so a card can open a new tab.
   4. `imgLoading` lets a long grid load its covers lazily. */

import * as React from "react";
import { ArrowUpRight } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * NotchedProjectCard
 *
 * A project card whose cover has a rounded notch bitten out of its
 * bottom-right corner, with the "open" arrow nested inside it. The cut is
 * concentric with the arrow disc, and filleted where it meets the cover's
 * edges, so the cover curves into it instead of ending on a point.
 *
 * The notch is drawn by three layers painted in the colour of the surface
 * BEHIND the card (`surface`, the page background by default). Put the card
 * on a different background and pass that colour, or the notch shows.
 *
 * Optional extras:
 * - `screen`: a product screen layered over the cover photo. The photo holds
 *   still and the screen grows on hover, so the card gains depth instead of
 *   just zooming.
 * - `monochrome`: the cover sits in black and white and takes its colours
 *   back on hover or keyboard focus.
 */

export interface NotchedProjectCardProps
  extends Omit<React.AnchorHTMLAttributes<HTMLAnchorElement>, "title"> {
  href: string;
  title: string;
  description?: string;
  /** cover photograph */
  image: string;
  imageAlt?: string;
  /** a pill at the top of the cover, e.g. the year */
  badge?: string;
  tags?: string[];
  /** a product screen over the photo (transparent PNG/WebP works best) */
  screen?: { src: string; alt: string; className?: string };
  /** a dark wash between the photo and the screen, 0 to 1 */
  dim?: number;
  monochrome?: boolean;
  /** the colour behind the card; the notch is painted in it */
  surface?: string;
  /** the arrow disc's fill on hover (any CSS colour); defaults to the theme's primary */
  accent?: string;
  /** the arrow's colour on that fill; pick one that contrasts with `accent` */
  accentForeground?: string;
  /** "lazy" for a long grid */
  imgLoading?: "eager" | "lazy";
  className?: string;
}

const DISC = 64; // the arrow disc, px
const BLOCK = 80; // the notch block, px (radius = BLOCK - DISC / 2)
const FILLET = 28; // the curve where the cut meets the cover's edges, px

export function NotchedProjectCard({
  href,
  title,
  description,
  image,
  imageAlt = "",
  badge,
  tags = [],
  screen,
  dim = screen ? 0.45 : 0,
  monochrome = false,
  surface = "rgb(var(--c-bg))", // (1)
  accent,
  accentForeground = "#0a0a0a",
  imgLoading = "eager",
  className,
  ...rest // (3)
}: NotchedProjectCardProps) {
  const tone = monochrome
    ? "grayscale transition-[filter,transform] duration-500 group-hover:grayscale-0 group-focus-visible:grayscale-0" // (2)
    : "transition-transform duration-500";

  return (
    <a
      {...rest}
      href={href}
      className={cn(
        "group flex flex-col rounded-[28px] outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-4 focus-visible:ring-offset-background",
        className,
      )}
    >
      <div className="relative">
        {/* the cover */}
        <div className="relative aspect-[4/3] overflow-hidden rounded-[28px] bg-muted">
          <img
            src={image}
            alt={screen ? "" : imageAlt}
            loading={imgLoading}
            className={cn(
              "absolute inset-0 h-full w-full object-cover",
              tone,
              !screen && "group-hover:scale-[1.04]",
            )}
          />
          {dim > 0 && (
            <div aria-hidden className="absolute inset-0" style={{ backgroundColor: `rgb(0 0 0 / ${dim})` }} />
          )}
          {screen && (
            <img
              src={screen.src}
              alt={screen.alt}
              loading={imgLoading}
              className={cn(
                "absolute bottom-0 right-0 w-[82%] origin-bottom-right drop-shadow-[0_18px_40px_rgba(0,0,0,0.5)] group-hover:scale-[1.07]",
                tone,
                screen.className,
              )}
            />
          )}
          {badge && (
            <div className="pointer-events-none absolute inset-x-0 top-0 flex justify-center pt-4">
              <span className="rounded-full border border-white/40 bg-black/30 px-2.5 py-1 text-[11px] font-medium text-white backdrop-blur-md">
                {badge}
              </span>
            </div>
          )}
        </div>

        {/* the notch: a block with a concave corner, and a fillet at each
            end where the cut meets the cover's right and bottom edges */}
        <div
          aria-hidden
          className="absolute bottom-0 right-0"
          style={{ width: BLOCK, height: BLOCK, borderTopLeftRadius: BLOCK - DISC / 2, background: surface }}
        />
        {[
          { bottom: BLOCK, right: 0 },
          { bottom: 0, right: BLOCK },
        ].map((pos, i) => (
          <div
            key={i}
            aria-hidden
            className="absolute"
            style={{
              ...pos,
              width: FILLET,
              height: FILLET,
              background: `radial-gradient(circle at top left, transparent ${FILLET - 0.5}px, ${surface} ${FILLET}px)`,
            }}
          />
        ))}

        {/* the arrow, nested in the notch */}
        <span
          aria-hidden
          className={cn(
            "absolute bottom-0 right-0 flex items-center justify-center rounded-full bg-secondary text-secondary-foreground transition-[background-color,color,transform] duration-300 group-hover:scale-105", // (2)
            accent
              ? "group-hover:bg-[var(--card-accent)] group-hover:text-[var(--card-accent-fg)]"
              : "group-hover:bg-primary group-hover:text-primary-foreground",
          )}
          style={
            {
              width: DISC,
              height: DISC,
              "--card-accent": accent,
              "--card-accent-fg": accentForeground,
            } as React.CSSProperties
          }
        >
          <ArrowUpRight className="size-5 transition-transform duration-300 group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />
        </span>
      </div>

      <h3 className="mt-5 text-2xl font-medium tracking-tight text-foreground">{title}</h3>
      {description && <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{description}</p>}
      {tags.length > 0 && (
        <ul className="mt-4 flex flex-wrap gap-2">
          {tags.map((t, i) => (
            <li
              key={`${t}-${i}`}
              className="rounded-md bg-secondary px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-secondary-foreground"
            >
              {t}
            </li>
          ))}
        </ul>
      )}
    </a>
  );
}

export default NotchedProjectCard;
