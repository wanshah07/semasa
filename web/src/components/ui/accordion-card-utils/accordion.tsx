"use client"

/* shadcn's Accordion (Radix), with the `variant` prop accordion-card uses. The pasted file was the plain shadcn one,
   which has no `variant`: Radix would have handed it to the DOM as an unknown attribute and TypeScript refuses it.
   variant="default": rows divided by a line (shadcn's own look).
   variant="card": every item is its own rounded card with a gap between, the open one lifted.
   The accordion-down / accordion-up animations are in tailwind.config.js (Tailwind 3). Radix wraps each trigger in an
   h3, and Semasa gives every h3 its display serif (src/index.css): the header resets to the body face, so a trigger
   reads like the rest of the page and a caller picks the serif where it wants it. */
import * as React from "react"
import * as AccordionPrimitive from "@radix-ui/react-accordion"
import { ChevronDown } from "lucide-react"

import { cn } from "@/lib/utils"

type Variant = "default" | "card"
const VariantContext = React.createContext<Variant>("default")

type AccordionProps = React.ComponentPropsWithoutRef<typeof AccordionPrimitive.Root> & { variant?: Variant }

const Accordion = React.forwardRef<React.ElementRef<typeof AccordionPrimitive.Root>, AccordionProps>(
  ({ variant = "default", className, ...props }, ref) => (
    <VariantContext.Provider value={variant}>
      <AccordionPrimitive.Root
        ref={ref}
        data-variant={variant}
        className={cn(variant === "card" && "flex flex-col gap-2", className)}
        {...(props as React.ComponentPropsWithoutRef<typeof AccordionPrimitive.Root>)}
      />
    </VariantContext.Provider>
  ),
)
Accordion.displayName = "Accordion"

const AccordionItem = React.forwardRef<
  React.ElementRef<typeof AccordionPrimitive.Item>,
  React.ComponentPropsWithoutRef<typeof AccordionPrimitive.Item>
>(({ className, ...props }, ref) => {
  const variant = React.useContext(VariantContext)
  return (
    <AccordionPrimitive.Item
      ref={ref}
      className={cn(
        variant === "card"
          ? "rounded-card border border-border bg-card px-4 shadow-card transition-shadow data-[state=open]:shadow-lift"
          : "border-b border-border",
        className,
      )}
      {...props}
    />
  )
})
AccordionItem.displayName = "AccordionItem"

const AccordionTrigger = React.forwardRef<
  React.ElementRef<typeof AccordionPrimitive.Trigger>,
  React.ComponentPropsWithoutRef<typeof AccordionPrimitive.Trigger>
>(({ className, children, ...props }, ref) => {
  const variant = React.useContext(VariantContext)
  return (
    <AccordionPrimitive.Header className="flex font-sans tracking-normal">
      <AccordionPrimitive.Trigger
        ref={ref}
        className={cn(
          "flex flex-1 items-center justify-between gap-3 py-4 text-left font-medium transition-all [&[data-state=open]>svg]:rotate-180",
          variant === "card" ? "hover:text-primary" : "hover:underline",
          className,
        )}
        {...props}
      >
        {children}
        <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-200" />
      </AccordionPrimitive.Trigger>
    </AccordionPrimitive.Header>
  )
})
AccordionTrigger.displayName = AccordionPrimitive.Trigger.displayName

const AccordionContent = React.forwardRef<
  React.ElementRef<typeof AccordionPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof AccordionPrimitive.Content>
>(({ className, children, ...props }, ref) => (
  <AccordionPrimitive.Content
    ref={ref}
    className="overflow-hidden text-sm transition-all data-[state=closed]:animate-accordion-up data-[state=open]:animate-accordion-down"
    {...props}
  >
    <div className={cn("pb-4 pt-0", className)}>{children}</div>
  </AccordionPrimitive.Content>
))

AccordionContent.displayName = AccordionPrimitive.Content.displayName

export { Accordion, AccordionItem, AccordionTrigger, AccordionContent }
