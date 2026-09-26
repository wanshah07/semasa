/* The divider blogs-3 imports but the paste did not include. A 1px rule in the theme's line colour. `contained`: it
   stays inside its container. Otherwise it runs the full width of the page, clipped so it can never make the page
   scroll sideways. */
import { cn } from "@/lib/utils";

export function FullWidthDivider({ contained = false, className }: { contained?: boolean; className?: string }) {
  if (contained) {
    return <div role="separator" aria-hidden="true" className={cn("h-px w-full bg-border", className)} />;
  }
  return (
    <div aria-hidden="true" className={cn("relative h-px w-full overflow-x-clip", className)}>
      <div role="separator" className="absolute left-1/2 top-0 h-px w-[100vw] max-w-[100vw] -translate-x-1/2 bg-border" />
    </div>
  );
}
