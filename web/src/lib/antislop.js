/* Anti slop in levels (supabase/052, backend/semasa/antislop.py): the worker keeps one row per post or film it writes, with the level
   in force and the slop found before and after its own edits. These helpers put the rows side by side per level. */

export const LEVELS = ["off", "clean", "full"];
export const ENOUGH = 10;                       // outputs per level before a difference is worth reading

export function levelOf(setting) {
  const v = setting && typeof setting === "object" ? setting.level : setting;
  return LEVELS.includes(v) ? v : "full";
}

/** One row per level: outputs, characters and slop per 1,000 characters, as written (raw) and after the edits (final). */
export function summarise(rows) {
  const out = LEVELS.map((level) => ({ level, outputs: 0, chars: 0, raw: 0, final: 0 }));
  for (const r of rows || []) {
    const s = out.find((x) => x.level === r.level);
    if (!s) continue;
    s.outputs += 1; s.chars += Number(r.chars) || 0; s.raw += Number(r.raw_hits) || 0; s.final += Number(r.final_hits) || 0;
  }
  return out.map((s) => ({
    ...s, rawPer1k: s.chars ? (s.raw * 1000) / s.chars : null, finalPer1k: s.chars ? (s.final * 1000) / s.chars : null,
    enough: s.outputs >= ENOUGH,
  }));
}

/** The plain reading of a summary: which level leaves the least slop, or why it is too early to say. */
export function verdict(summary) {
  const ready = summary.filter((s) => s.enough);
  if (ready.length < 2) return { ready: false, best: null };
  const best = [...ready].sort((a, b) => a.finalPer1k - b.finalPer1k)[0];
  return { ready: true, best: best.level };
}
