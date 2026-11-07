/* Which hook shapes earn views and interaction (Wan, 7 Nov 2026). The worker (backend/semasa/hook_learning.py, daily) writes the
   ranking to settings.hook_learning; the page only reads it and keeps one switch, settings.hook_learning_on. Pure helpers, tested
   in hookLearning.test.mjs. */

export const SWITCH_KEY = "hook_learning_on";

/** settings.hook_learning as the card shows it. Empty before the first run. */
export function learningOf(raw) {
  const v = raw && typeof raw === "object" ? raw : {};
  const num = (x, d = 0) => (Number.isFinite(Number(x)) ? Number(x) : d);
  const ranking = (Array.isArray(v.ranking) ? v.ranking : []).filter((r) => r && Number.isFinite(Number(r.shape)))
    .map((r) => ({ shape: Number(r.shape), style: String(r.style || ""), n: num(r.n), views: num(r.views), rate: num(r.rate), score: num(r.score), films: num(r.films) }));
  return { at: v.at || null, windowDays: num(v.window_days, 60), minPosts: num(v.min_posts, 3), measured: num(v.measured), ranking };
}

/** On unless Wan switched it off (the worker reads the same rule). */
export const learningOn = (raw) => !(raw && typeof raw === "object" && raw.enabled === false);

/** The interaction rate as a percentage text, one decimal. */
export const ratePct = (rate) => `${(Math.round(Number(rate || 0) * 1000) / 10).toFixed(1)}%`;

/** The rows to draw: the best first, with the first three marked as the ones the writers are pointed at. */
export const learningRows = (ranking, top = 3) => (ranking || []).map((r, i) => ({ ...r, top: i < top }));
