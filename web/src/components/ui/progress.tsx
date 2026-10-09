"use client";
/* shadcn's Progress (Radix), pasted with components/ui/app-1.tsx (Bil overview: how much of a project's invoicing is paid). */
import * as React from "react";
import * as ProgressPrimitive from "@radix-ui/react-progress";

import { cn } from "@/lib/utils";

const Progress = React.forwardRef<
  React.ElementRef<typeof ProgressPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof ProgressPrimitive.Root>
>(({ className, value, ...props }, ref) => (
  <ProgressPrimitive.Root ref={ref} className={cn("relative h-2 w-full overflow-hidden rounded-pill bg-surface-2", className)} {...props}>
    <ProgressPrimitive.Indicator
      className="h-full w-full flex-1 rounded-pill bg-accent transition-all"
      style={{ transform: `translateX(-${100 - Math.max(0, Math.min(100, value || 0))}%)` }}
    />
  </ProgressPrimitive.Root>
));
Progress.displayName = ProgressPrimitive.Root.displayName;

export { Progress };
