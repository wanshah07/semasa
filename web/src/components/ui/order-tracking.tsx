"use client"

/* OrderTracking (pasted by Wan, 7 Nov 2026: "add this untuk status proses macam (idea>storyboard>motion)"). Kept as pasted,
   with two optional fields a process needs that an order does not: `isActive` (the step running now, drawn with a spinning
   ring) and `isFailed` (the step a run stopped at). Steps without them draw exactly as the original. Used by the Motion
   film card (components/MotionLab.jsx) through lib/motion.js motionTrack(). */
import * as React from "react"
import { AlertCircle, CheckCircle2, Circle, Loader2 } from "lucide-react"
import { cn } from "@/lib/utils"

export interface OrderTrackingProps
  extends React.HTMLAttributes<HTMLDivElement> {
  steps: {
    name: string
    timestamp: string
    isCompleted: boolean
    isActive?: boolean
    isFailed?: boolean
  }[]
}

const OrderTracking = React.forwardRef<HTMLDivElement, OrderTrackingProps>(
  ({ steps = [], className, ...props }, ref) => {
    return (
      <div ref={ref} className={cn("w-full max-w-md", className)} {...props}>
        {steps.length > 0 ? (
          <div>
            {steps.map((step, index) => (
              <div key={index} className="flex" data-step-state={step.isFailed ? "failed" : step.isCompleted ? "done" : step.isActive ? "active" : "todo"}>
                <div className="flex flex-col items-center">
                  {step.isFailed ? (
                    <AlertCircle className="h-6 w-6 shrink-0 text-danger" />
                  ) : step.isCompleted ? (
                    <CheckCircle2 className="h-6 w-6 shrink-0 text-primary/70" />
                  ) : step.isActive ? (
                    <Loader2 className="h-6 w-6 shrink-0 animate-spin text-primary" />
                  ) : (
                    <Circle className="h-6 w-6 shrink-0 text-muted-foreground" />
                  )}
                  {index < steps.length - 1 && (
                    <div
                      className={cn("w-[1.5px] grow", {
                        "bg-primary/70": steps[index + 1].isCompleted || steps[index + 1].isActive,
                        "bg-muted-foreground": !steps[index + 1].isCompleted && !steps[index + 1].isActive,
                      })}
                    />
                  )}
                </div>
                <div className="ml-3 pb-6">
                  <p className={cn("text-sm font-medium", step.isFailed && "text-danger")}>{step.name}</p>
                  <p className="text-sm text-muted-foreground">
                    {step.timestamp}
                  </p>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-foreground/80">
            This order has no tracking information.
          </p>
        )}
      </div>
    )
  }
)
OrderTracking.displayName = "OrderTracking"

export { OrderTracking }
