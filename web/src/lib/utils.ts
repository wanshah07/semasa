import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/** shadcn's `cn`: join class names (strings, arrays, `{ "class": condition }` objects), and when two Tailwind classes
 *  fight over the same property the later one wins (`cn("object-cover", "object-contain")` → `object-contain`).
 *  tailwind-merge 2.x is the line that understands Tailwind 3, which Semasa uses. */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
