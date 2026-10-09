/* Gradient background (pasted by Wan on 9 Oct 2026, a 21st.dev snippet: one radial gradient behind a page). In Semasa it is
   the hero band at the top of the home dashboard (pages/HomeTab.jsx). Three things changed from the paste:
     - the colours are the theme's tokens, not #fff and #6366f1: the surface fades into the accent, so under noir the band
       is dark-into-blue and under the light theme white-into-sky, and a brand theme (regulab, facerinna) recolours it for free;
     - it is a BAND with children, not a min-h-screen page: a dashboard's hero is one strip, and the cards sit under it;
     - the unused counter state is gone. */
import * as React from "react";
import { cn } from "@/lib/utils";

type Props = React.HTMLAttributes<HTMLDivElement> & {
  /** Where the glow sits: the top edge (default) or the bottom. */
  glow?: "top" | "bottom";
  /** Token name of the glow colour: accent (default), gold or warm. */
  tone?: "accent" | "gold" | "warm";
  children?: React.ReactNode;
};

export function GradientBackground({ glow = "top", tone = "accent", className, children, ...rest }: Props) {
  const y = glow === "top" ? "10%" : "90%";
  return (
    <div className={cn("relative w-full overflow-hidden rounded-card border border-line/80", className)} {...rest}>
      <div aria-hidden className="absolute inset-0 z-0"
        style={{
          backgroundImage: `radial-gradient(125% 125% at 50% ${y}, rgb(var(--c-surface)) 40%, rgb(var(--c-${tone}) / 0.85) 100%)`,
          backgroundSize: "100% 100%",
        }} />
      <div className="relative z-10">{children}</div>
    </div>
  );
}

export default GradientBackground;
