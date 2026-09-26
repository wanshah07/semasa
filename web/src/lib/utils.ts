/** shadcn's `cn`: join class names, dropping the empty ones. Semasa does not carry clsx or tailwind-merge, so a later
 *  class does not override an earlier conflicting one here: write the class you want once. */
export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}
