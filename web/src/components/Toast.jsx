import { AnimatePresence, motion } from "framer-motion";
import { NoticeCard } from "@/components/ui/notifications-5";

/* Every toast in the app is one of the notification cards Wan pasted (ui/notifications-5.tsx): the theme's surface and ink
   with an icon in the tone's colour. The old toast was white text on a solid ok / warn / danger fill, which several themes
   could not keep readable. */
const VARIANT = { info: "info", ok: "success", warn: "warning", danger: "error", error: "error" };

export default function Toasts({ toasts }) {
  return (
    // top of the screen on a phone and bottom right from lg up: in the bottom centre a toast sat on the buttons just pressed
    // (two of them covered "Worth following" for five seconds, 15 Nov 2026)
    <div className="toast-stack pointer-events-none fixed left-1/2 z-50 flex w-full max-w-md -translate-x-1/2 flex-col items-center gap-2 px-4 lg:left-auto lg:right-4 lg:w-auto lg:translate-x-0 lg:items-end lg:px-0" role="status" aria-live="polite">
      <AnimatePresence>
        {toasts.map((t) => (
          <motion.div key={t.id} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 8 }} className="w-full max-w-sm">
            <NoticeCard notice={{ id: t.id, variant: VARIANT[t.tone] || "info", title: t.text }} />
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}
