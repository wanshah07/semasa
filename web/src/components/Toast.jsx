import { AnimatePresence, motion } from "framer-motion";

export default function Toasts({ toasts }) {
  const tone = { info: "bg-ink text-bg", ok: "bg-ok text-white", warn: "bg-warn text-white", danger: "bg-danger text-white" };
  return (
    <div className="pointer-events-none fixed bottom-5 left-1/2 z-50 flex w-full max-w-md -translate-x-1/2 flex-col items-center gap-2 px-4" role="status" aria-live="polite">
      <AnimatePresence>
        {toasts.map((t) => (
          <motion.div key={t.id} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 8 }}
            className={`max-w-full rounded-tile px-4 py-2 text-center text-sm shadow-lift ${tone[t.tone] || tone.info}`}>
            {t.text}
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}
