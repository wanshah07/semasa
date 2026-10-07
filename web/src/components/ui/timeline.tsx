"use client";

/* Timeline (pasted by Wan on 7 Oct 2026, 21st.dev "timeline"). In Semasa it draws a project's stages across (Bil →
   Projects: lead → quotation → invoice → paid) and a document's history down (Bil → viewer).
   Adapted from the paste in three ways, each because of what this repo is:
     - no @base-ui/react: its `useRender`/`mergeProps` only existed to let a caller swap the tag; a plain `render` prop
       (function of props) keeps that without a new dependency, and `mergeProps` here joins classNames and lets the
       caller's other props win;
     - Tailwind 3, not 4: `not-last:` became `[&:not(:last-child)]:`, oklch shadows became `shadow-xs`, and every
       colour is a token name from tailwind.config.js (primary = accent, border = line, muted-foreground = muted), so the
       component follows every Semasa theme with nothing in :root to add;
     - the item spacing is a prop (`gap`) because a history of twelve events cannot afford 4rem between each. */

import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const timelineVariants = cva("group/timeline flex", {
  variants: {
    orientation: {
      horizontal: "w-full flex-row",
      vertical: "flex-col",
    },
  },
  defaultVariants: { orientation: "vertical" },
});

const timelineIndicatorVariants = cva(
  "absolute flex size-6 items-center justify-center rounded-full border-2 shadow-xs transition-all duration-200",
  {
    variants: {
      state: {
        pending: "border-border bg-surface-2 text-muted",
        current: "border-primary bg-primary/10 text-primary outline outline-2 outline-offset-2 outline-primary/20",
        completed: "border-primary bg-primary text-primary-foreground",
      },
    },
    defaultVariants: { state: "pending" },
  },
);

const timelineSeparatorVariants = cva(
  "absolute transition-all duration-200 group-last/timeline-item:hidden",
  {
    variants: {
      orientation: {
        horizontal: "-top-6 left-7 h-0.5 w-[calc(100%-2rem)] -translate-y-1/2",
        vertical: "-left-6 top-7 h-[calc(100%-2rem)] w-0.5 -translate-x-1/2",
      },
      state: {
        pending: "bg-border",
        completed: "bg-primary/40",
      },
    },
    defaultVariants: { orientation: "vertical", state: "pending" },
  },
);

type Orientation = "horizontal" | "vertical";

type TimelineContextValue = {
  activeStep: number;
  setActiveStep: (step: number) => void;
  orientation: Orientation;
  gap: string;
};

const TimelineContext = React.createContext<TimelineContextValue | undefined>(undefined);
const TimelineItemContext = React.createContext<{ step: number } | undefined>(undefined);

const useTimeline = () => {
  const context = React.useContext(TimelineContext);
  if (!context) throw new Error("useTimeline must be used within a Timeline");
  return context;
};

type RenderFunction<T> = (props: T) => React.ReactElement | null;

/** The caller's props win; classNames are joined. */
function mergeProps<T extends { className?: string }>(own: T, theirs: Partial<T> & { className?: string }): T {
  return { ...own, ...theirs, className: cn(own.className, theirs.className) };
}

interface TimelineProps extends React.HTMLAttributes<HTMLDivElement>, VariantProps<typeof timelineVariants> {
  defaultValue?: number;
  value?: number;
  onValueChange?: (value: number) => void;
  /** Space between items, as a COMPLETE class (Tailwind only emits classes it can read whole in the source), e.g.
   *  `[&:not(:last-child)]:pb-6` down or `[&:not(:last-child)]:pe-4` across. Defaults: pb-16 down, pe-8 across. */
  gap?: string;
  render?: RenderFunction<React.HTMLAttributes<HTMLDivElement>>;
}

function Timeline({ defaultValue = 1, value, onValueChange, orientation = "vertical", gap, className, render, ...props }: TimelineProps) {
  const [activeStep, setInternalStep] = React.useState(defaultValue);
  const setActiveStep = React.useCallback(
    (step: number) => {
      if (value === undefined) setInternalStep(step);
      onValueChange?.(step);
    },
    [value, onValueChange],
  );
  const o: Orientation = orientation || "vertical";
  const rootProps = mergeProps(
    { className: timelineVariants({ orientation: o }), "data-orientation": o, "data-slot": "timeline" } as React.HTMLAttributes<HTMLDivElement>,
    { ...props, className },
  );
  return (
    <TimelineContext.Provider value={{ activeStep: value ?? activeStep, setActiveStep, orientation: o, gap: gap || (o === "horizontal" ? "[&:not(:last-child)]:pe-8" : "[&:not(:last-child)]:pb-16") }}>
      {render ? render(rootProps) : <div {...rootProps} />}
    </TimelineContext.Provider>
  );
}

interface SlotProps<E> extends React.HTMLAttributes<E> {
  render?: RenderFunction<React.HTMLAttributes<E>>;
}

function TimelineContent({ className, render, ...props }: SlotProps<HTMLDivElement>) {
  const p = mergeProps({ className: "text-sm leading-relaxed text-muted", "data-slot": "timeline-content" } as React.HTMLAttributes<HTMLDivElement>, { ...props, className });
  return render ? render(p) : <div {...p} />;
}

function TimelineDate({ className, render, ...props }: SlotProps<HTMLTimeElement>) {
  const p = mergeProps({ className: "mb-1 block text-xs font-medium tabular-nums text-muted", "data-slot": "timeline-date" } as React.HTMLAttributes<HTMLTimeElement>, { ...props, className });
  return render ? render(p) : <time {...p} />;
}

function TimelineHeader({ className, render, ...props }: SlotProps<HTMLDivElement>) {
  const p = mergeProps({ className: "", "data-slot": "timeline-header" } as React.HTMLAttributes<HTMLDivElement>, { ...props, className });
  return render ? render(p) : <div {...p} />;
}

function TimelineIndicator({ className, children, render, ...props }: SlotProps<HTMLDivElement>) {
  const { orientation, activeStep } = useTimeline();
  const item = React.useContext(TimelineItemContext);
  const state = item ? (item.step < activeStep ? "completed" : item.step === activeStep ? "current" : "pending") : "pending";
  const p = mergeProps(
    {
      className: cn(timelineIndicatorVariants({ state }), orientation === "horizontal" ? "-top-6 left-0 -translate-y-1/2" : "-left-6 top-0 -translate-x-1/2"),
      "aria-hidden": "true",
      "data-slot": "timeline-indicator",
      "data-state": state,
    } as React.HTMLAttributes<HTMLDivElement>,
    { ...props, className },
  );
  return render ? render(p) : <div {...p}>{children}</div>;
}

interface TimelineItemProps extends SlotProps<HTMLDivElement> {
  step: number;
}

function TimelineItem({ step, className, render, ...props }: TimelineItemProps) {
  const { activeStep, orientation, gap } = useTimeline();
  const isCompleted = step <= activeStep;
  const isCurrent = step === activeStep;
  const p = mergeProps(
    {
      className: cn(
        "group/timeline-item relative flex flex-1 flex-col gap-2",
        orientation === "horizontal" ? "mt-8" : "ms-8",
        gap,
      ),
      "data-completed": isCompleted || undefined,
      "data-current": isCurrent || undefined,
      "data-slot": "timeline-item",
    } as React.HTMLAttributes<HTMLDivElement>,
    { ...props, className },
  );
  return <TimelineItemContext.Provider value={{ step }}>{render ? render(p) : <div {...p} />}</TimelineItemContext.Provider>;
}

function TimelineSeparator({ className, render, ...props }: SlotProps<HTMLDivElement>) {
  const { orientation, activeStep } = useTimeline();
  const item = React.useContext(TimelineItemContext);
  const state = item && item.step < activeStep ? "completed" : "pending";
  const p = mergeProps(
    { className: timelineSeparatorVariants({ orientation, state }), "aria-hidden": "true", "data-slot": "timeline-separator", "data-state": state } as React.HTMLAttributes<HTMLDivElement>,
    { ...props, className },
  );
  return render ? render(p) : <div {...p} />;
}

function TimelineTitle({ className, render, ...props }: SlotProps<HTMLHeadingElement>) {
  const p = mergeProps({ className: "text-sm font-semibold leading-none", "data-slot": "timeline-title" } as React.HTMLAttributes<HTMLHeadingElement>, { ...props, className });
  return render ? render(p) : <h3 {...p} />;
}

export { Timeline, TimelineContent, TimelineDate, TimelineHeader, TimelineIndicator, TimelineItem, TimelineSeparator, TimelineTitle };
export default Timeline;
