/* Aurora background (pasted by Wan on 11 Oct 2026, an Aceternity snippet). In Semasa it replaces the radial gradient behind the
   home dashboard's hero band (pages/HomeTab.jsx). What changed from the paste, and why:
     - no <main> wrapper: every Semasa page is already a <main>, and a page may have only one;
     - `transition-bg` (a utility the original project defined) is `transition-colors`, which Tailwind 3 has;
     - motion-reduce stops the drift for anyone who asked their system for less motion;
     - the colour variables it reads (--white, --black, --transparent, --blue-500 …) come from the plugin in
       tailwind.config.js, which publishes ONLY Tailwind's own palette, never Semasa's token colours (those already have
       variables of their own, and two of them, --brand and --info, would have been overwritten).
   The defaults are the original full-screen look; a caller narrows it with className (tailwind-merge lets the later class
   win), as HomeTab does for the band. */
"use client";
import { cn } from "@/lib/utils";
import React, { ReactNode } from "react";

interface AuroraBackgroundProps extends React.HTMLProps<HTMLDivElement> {
  children: ReactNode;
  showRadialGradient?: boolean;
}

export const AuroraBackground = ({
  className,
  children,
  showRadialGradient = true,
  ...props
}: AuroraBackgroundProps) => {
  return (
    <div
      className={cn(
        "relative flex flex-col h-[100vh] items-center justify-center bg-zinc-50 dark:bg-zinc-900 text-slate-950 transition-colors",
        className
      )}
      {...props}
    >
      <div className="absolute inset-0 overflow-hidden" aria-hidden>
        <div
          className={cn(
            `
          [--white-gradient:repeating-linear-gradient(100deg,var(--white)_0%,var(--white)_7%,var(--transparent)_10%,var(--transparent)_12%,var(--white)_16%)]
          [--dark-gradient:repeating-linear-gradient(100deg,var(--black)_0%,var(--black)_7%,var(--transparent)_10%,var(--transparent)_12%,var(--black)_16%)]
          [--aurora:repeating-linear-gradient(100deg,var(--blue-500)_10%,var(--indigo-300)_15%,var(--blue-300)_20%,var(--violet-200)_25%,var(--blue-400)_30%)]
          [background-image:var(--white-gradient),var(--aurora)]
          dark:[background-image:var(--dark-gradient),var(--aurora)]
          [background-size:300%,_200%]
          [background-position:50%_50%,50%_50%]
          filter blur-[10px] invert dark:invert-0
          after:content-[""] after:absolute after:inset-0 after:[background-image:var(--white-gradient),var(--aurora)]
          after:dark:[background-image:var(--dark-gradient),var(--aurora)]
          after:[background-size:200%,_100%]
          after:animate-aurora after:[background-attachment:fixed] after:mix-blend-difference
          motion-reduce:after:animate-none
          pointer-events-none
          absolute -inset-[10px] opacity-50 will-change-transform`,

            showRadialGradient &&
              `[mask-image:radial-gradient(ellipse_at_100%_0%,black_10%,var(--transparent)_70%)]`
          )}
        ></div>
      </div>
      {children}
    </div>
  );
};

export default AuroraBackground;
