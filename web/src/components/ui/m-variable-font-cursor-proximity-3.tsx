/* The nav example Wan pasted (11 Oct 2026), kept as the reference use of VariableFontCursorProximity. Two changes from the
   paste: it imports the piece from components/ui (the registry path it named does not exist here), and `min-h-50`, which
   Tailwind 3 does not have, is `min-h-[200px]`. The live use is the sidebar menu (components/ui/dashboard-sidebar.tsx). */
"use client";
import { useRef } from "react";
import { VariableFontCursorProximity } from "@/components/ui/variable-font-cursor-proximity";

const navItems = ["Home", "Work", "About", "Contact"];

export default function VariableFontCursorProximityNav() {
  const containerRef = useRef<HTMLDivElement>(null);

  return (
    <nav
      className="flex min-h-[200px] flex-wrap items-center justify-center gap-10 px-6"
      ref={containerRef}
    >
      {navItems.map((item) => (
        <VariableFontCursorProximity
          className="cursor-pointer text-muted-foreground text-xl"
          containerRef={containerRef}
          falloff="exponential"
          fromFontVariationSettings="'wght' 300"
          key={item}
          radius={60}
          toFontVariationSettings="'wght' 800"
        >
          {item}
        </VariableFontCursorProximity>
      ))}
    </nav>
  );
}
