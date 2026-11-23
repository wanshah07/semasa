/* "Too full for this design" and its Fix button (Wan, 23 Nov 2026: "if got blocker, put the fix button so your worker can fix the
   blocker"). A slide the chosen design cannot hold is drawn as two: the points are shared between the halves, or a single long
   point is broken at a sentence or a comma near its middle. Every word is kept (the same rule as the worker's
   carousel.split_full), the design keys travel with both halves, and nothing is invented. Pure functions on the editor's rows
   ({title, points: "one per line", ...design keys}), so the preview simply re-measures the result. */

const MARK = /\s*\((\d+)\/(\d+)\)\s*$/;
const stripMark = (title) => String(title || "").replace(MARK, "").trim();
const lines = (points) => String(points || "").split("\n").map((p) => p.trim()).filter(Boolean);

/** Break one long text near its middle, preferring a sentence end, then ; or , then a space. null when it is too short to split. */
export function breakText(text, min = 24) {
  const s = String(text || "").trim();
  if (s.length < min * 2) return null;
  const mid = s.length / 2;
  for (const re of [/[.!?](?=\s)/g, /[;:](?=\s)/g, /,(?=\s)/g, /\s/g]) {
    let best = -1;
    for (const m of s.matchAll(re)) {
      const at = m.index + (re.source.startsWith("\\s") ? 0 : 1);
      if (at >= min && s.length - at >= min && (best < 0 || Math.abs(at - mid) < Math.abs(best - mid))) best = at;
    }
    if (best >= 0) return [s.slice(0, best).trim(), s.slice(best).trim()];
  }
  return null;
}

/** One row as two rows, or null when there is nothing left to split. */
export function splitRow(row) {
  const pts = lines(row.points);
  let a; let b;
  if (pts.length >= 2) {
    const half = Math.ceil(pts.length / 2);
    a = pts.slice(0, half); b = pts.slice(half);
  } else {
    const cut = breakText(pts[0] || "");
    if (!cut) return null;
    [a, b] = [[cut[0]], [cut[1]]];
  }
  const title = stripMark(row.title);
  return [{ ...row, title, points: a.join("\n") }, { ...row, title, points: b.join("\n") }];
}

/** Number the pieces of a split slide "(1/2)", "(2/2)": consecutive rows with the same title, so a second split renumbers. */
export function renumber(rows) {
  const out = rows.map((r) => ({ ...r }));
  let i = 0;
  while (i < out.length) {
    const base = stripMark(out[i].title);
    let j = i + 1;
    while (j < out.length && base && stripMark(out[j].title) === base && (MARK.test(out[j].title) || MARK.test(out[i].title) || j === i + 1)) j += 1;
    const n = j - i;
    if (n > 1 && base) for (let k = i; k < j; k += 1) out[k].title = `${base} (${k - i + 1}/${n})`;
    i = j;
  }
  return out;
}

/** The fix: split every row in `idx` (0-based indexes into `rows`). {rows, split, stuck}: how many were split and which could not be. */
export function fixFullRows(rows, idx) {
  const want = new Set(idx);
  const out = []; let split = 0; const stuck = [];
  rows.forEach((r, i) => {
    if (!want.has(i)) return out.push(r);
    const two = splitRow(r);
    if (!two) { stuck.push(i); return out.push(r); }
    split += 1;
    out.push(...two);
  });
  return { rows: split ? renumber(out) : out, split, stuck };
}

/** The note that asks the worker to rewrite a post so its blockers go (the existing revise job: the caption and hook, never the facts). */
export function fixNote(flags) {
  const items = flags.filter((f) => f.hard).map((f) => `${f.where}: ${f.msg}`);
  const head = "Clear every approval blocker below and change nothing else. Where a blocker marks a fact the source does not give, leave that fact out; never guess one. ";
  return (head + items.map((x, i) => `${i + 1}) ${x}`).join(" ")).slice(0, 800);
}
