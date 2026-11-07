"use client";

/* AnimatedTabs (pasted by Wan, 7 Nov 2026: "Dalam 1 segment boleh create tab" — the tabs inside a segment, with the sliding
   pill). Kept as pasted, with what Semasa needs:
   - colours come from the theme (bg-surface-2 bar, bg-ink pill) instead of the fixed dark glass, so it reads in every theme;
   - it can be controlled (`value` + `onChange`), because a segment's tab is the page's address (#media, #media-lib…);
   - `hideContent` draws the bar alone (the page below is the content), and a label may carry an icon;
   - the pill's layoutId is unique per bar, so two bars on one page never fight over one animation;
   - the demo tabs carry no pictures (the pasted ones pointed at a third-party CDN). */
import React, { useId, useState } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

export interface Tab {
  id: string;
  label: React.ReactNode;
  content?: React.ReactNode;
}

interface AnimatedTabsProps {
  tabs?: Tab[];
  defaultTab?: string;
  className?: string;
  value?: string;
  onChange?: (id: string) => void;
  hideContent?: boolean;
  "aria-label"?: string;
}

const defaultTabs: Tab[] = [
  { id: "tab1", label: "Tab 1", content: <div className="flex flex-col gap-y-2"><h2 className="text-2xl font-bold">Tab 1</h2><p className="text-sm text-muted">The first tab.</p></div> },
  { id: "tab2", label: "Tab 2", content: <div className="flex flex-col gap-y-2"><h2 className="text-2xl font-bold">Tab 2</h2><p className="text-sm text-muted">The second tab.</p></div> },
  { id: "tab3", label: "Tab 3", content: <div className="flex flex-col gap-y-2"><h2 className="text-2xl font-bold">Tab 3</h2><p className="text-sm text-muted">The third tab.</p></div> },
];

const AnimatedTabs = ({ tabs = defaultTabs, defaultTab, className, value, onChange, hideContent = false, ...rest }: AnimatedTabsProps) => {
  const [own, setOwn] = useState<string>(defaultTab || tabs[0]?.id);
  const activeTab = value ?? own;
  const pill = `active-tab-${useId()}`;
  const choose = (id: string) => { if (value === undefined) setOwn(id); onChange?.(id); };

  if (!tabs?.length) return null;

  return (
    <div className={cn("flex w-full max-w-lg flex-col gap-y-1", className)}>
      <div role="tablist" aria-label={rest["aria-label"]} className="flex flex-nowrap gap-1 rounded-pill bg-surface-2 p-1 sm:flex-wrap">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={activeTab === tab.id}
            data-tab={tab.id}
            onClick={() => choose(tab.id)}
            className={cn(
              "relative flex items-center gap-1.5 whitespace-nowrap rounded-pill px-3.5 py-1.5 text-sm font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-accent",
              activeTab === tab.id ? "text-bg" : "text-muted hover:text-ink"
            )}
          >
            {activeTab === tab.id && (
              <motion.div
                layoutId={pill}
                className="absolute inset-0 rounded-pill bg-ink shadow-card"
                transition={{ type: "spring", duration: 0.6 }}
              />
            )}
            <span className="relative z-10 flex items-center gap-1.5">{tab.label}</span>
          </button>
        ))}
      </div>

      {!hideContent && (
        <div className="min-h-60 h-full rounded-card border border-line bg-surface p-4 shadow-card">
          {tabs.map(
            (tab) =>
              activeTab === tab.id && (
                <motion.div
                  key={tab.id}
                  initial={{ opacity: 0, scale: 0.95, x: -10, filter: "blur(10px)" }}
                  animate={{ opacity: 1, scale: 1, x: 0, filter: "blur(0px)" }}
                  exit={{ opacity: 0, scale: 0.95, x: -10, filter: "blur(10px)" }}
                  transition={{ duration: 0.5, ease: "circInOut", type: "spring" }}
                >
                  {tab.content}
                </motion.div>
              )
          )}
        </div>
      )}
    </div>
  );
};

export { AnimatedTabs };
