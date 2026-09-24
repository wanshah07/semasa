/* Motion presets. Components import these rather than inventing durations, so the
   whole app moves with one hand. Respects prefers-reduced-motion via `useReducedMotion`. */
export const EASE = [0.22, 1, 0.36, 1];

export const fadeUp = {
  hidden: { opacity: 0, y: 14 },
  show: { opacity: 1, y: 0, transition: { duration: 0.45, ease: EASE } },
};

export const stagger = (delay = 0.04) => ({
  hidden: {},
  show: { transition: { staggerChildren: delay } },
});

export const pop = {
  hidden: { opacity: 0, scale: 0.96 },
  show: { opacity: 1, scale: 1, transition: { duration: 0.35, ease: EASE } },
  exit: { opacity: 0, scale: 0.98, transition: { duration: 0.2 } },
};
