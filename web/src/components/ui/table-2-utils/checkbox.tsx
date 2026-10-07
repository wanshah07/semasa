"use client";
/* shadcn's Checkbox (Radix), pasted with components/ui/table-2.tsx (Bil). `indeterminate` draws the half state Radix
   spells as checked="indeterminate" (the pasted table passed it as a prop of its own). */
import * as React from "react";
import * as CheckboxPrimitive from "@radix-ui/react-checkbox";
import { Check, Minus } from "lucide-react";

import { cn } from "@/lib/utils";

type Props = React.ComponentPropsWithoutRef<typeof CheckboxPrimitive.Root> & { indeterminate?: boolean };

const Checkbox = React.forwardRef<React.ElementRef<typeof CheckboxPrimitive.Root>, Props>(
  ({ className, indeterminate, checked, ...props }, ref) => (
    <CheckboxPrimitive.Root
      ref={ref}
      checked={indeterminate ? "indeterminate" : checked}
      className={cn(
        "peer h-4 w-4 shrink-0 rounded-sm border border-primary ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 data-[state=checked]:bg-primary data-[state=checked]:text-primary-foreground data-[state=indeterminate]:bg-primary data-[state=indeterminate]:text-primary-foreground",
        className,
      )}
      {...props}
    >
      <CheckboxPrimitive.Indicator className={cn("flex items-center justify-center text-current")}>
        {indeterminate ? <Minus className="h-3 w-3" /> : <Check className="h-3.5 w-3.5" />}
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  ),
);
Checkbox.displayName = CheckboxPrimitive.Root.displayName;

export { Checkbox };
