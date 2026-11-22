/* Reading an append-only list without downloading all of it on every poll (Wan, 22 Nov 2026: "Fix what you recommend", after an
   egress audit). semasa_log and semasa_api_usage only ever get new rows (the worker inserts; nothing updates them, and the only
   deletes are housekeeping's of rows weeks old), and they have no updated_at, so lib/tableDelta.js cannot read them. Measured on
   22 Nov 2026: the Log tab re-read 3,000 log rows (~1.4 MB) on every 90-second poll and every realtime event; Papan 2,000 usage
   rows (~0.5 MB) and the API page 5,000 (~1.2 MB) every 5 minutes.

   Two kinds of read:
     full    the list as before (newest `limit` rows, and only inside `windowMs` when one is given): the first time, again every
             FULL_EVERY_MS (which settles anything a delta cannot see, such as a row housekeeping deleted), and when a delta
             comes back full;
     delta   rows whose time column is at or after the newest seen, less OVERLAP_MS (a row can commit after a later one), merged
             in by id. On a quiet list that is a handful of rows, most of them already held.
   After a merge the list is trimmed back to what a full read would return: nothing older than the window, at most `limit` rows.
   A realtime INSERT carries its whole row, so `mergeRows` adds it with no read at all.
   Every read returns { rows, kind, fetched }: rows is the whole list newest first, or null when nothing changed (the page keeps
   the array it has); fetched counts rows that crossed the wire. A failed read returns { error } and leaves the list alone.
   No React and no Supabase import, so web/appendDelta.test.mjs runs this under Node with a fake client. */

export const FULL_EVERY_MS = 6 * 3600_000;   // nothing edits these rows; deletes are housekeeping's, of rows weeks old
export const OVERLAP_MS = 2 * 60_000;
export const DELTA_CAP = 500;

export const newAppendState = () => ({ map: new Map(), cursor: null, fullAt: 0 });

const ms = (iso) => { const t = Date.parse(iso); return Number.isFinite(t) ? t : 0; };

/* Newest first by the time column, then by id (a log id is a number, a usage id a uuid), so rows written in one statement
   keep one order between a full read and a delta. */
function byNewest(at) {
  return (a, b) => {
    const c = ms(b?.[at]) - ms(a?.[at]);
    if (c) return c;
    const x = a?.id; const y = b?.id;
    return typeof x === "number" && typeof y === "number" ? y - x : String(y).localeCompare(String(x));
  };
}

export const sortedRows = (state, at = "created_at") => [...state.map.values()].sort(byNewest(at));

/** The newest time seen, as the string the server sent, starting from `prev`. */
export function cursorOf(rows, at = "created_at", prev = null) {
  let best = prev;
  for (const r of rows || []) {
    if (r?.[at] && (best === null || ms(r[at]) > ms(best))) best = r[at];
  }
  return best;
}

export const sinceOf = (cursor, overlapMs = OVERLAP_MS) => new Date(ms(cursor) - overlapMs).toISOString();

export const wantFull = (state, now) => !state.cursor || now - state.fullAt >= FULL_EVERY_MS;

/** Forget a row a realtime DELETE named. True when it was on show. */
export const dropRow = (state, id) => state.map.delete(id);

/* Drop what a full read would not list: rows older than the window, then everything past the newest `limit`. Returns the ids
   that went. */
function trim(state, { at, limit, windowMs, now }) {
  const gone = [];
  if (windowMs) {
    const from = now - windowMs;
    for (const [id, r] of state.map) if (ms(r[at]) < from) { state.map.delete(id); gone.push(id); }
  }
  if (state.map.size > limit) {
    const keep = sortedRows(state, at).slice(0, limit);
    const kept = new Set(keep.map((r) => r.id));
    for (const id of state.map.keys()) if (!kept.has(id)) gone.push(id);
    state.map = new Map(keep.map((r) => [r.id, r]));
  }
  return gone;
}

/**
 * Merge rows that arrived (a delta read, a realtime INSERT) into the list, then trim it. Returns true when what is on show
 * changed: a new row that survived the trim, or a row the window aged out.
 */
export function mergeRows(state, rows, { at = "created_at", limit = 1000, windowMs = 0, now = Date.now() } = {}) {
  const fresh = [];
  for (const r of rows || []) {
    if (r?.id == null) continue;
    if (!state.map.has(r.id)) { state.map.set(r.id, r); fresh.push(r); }   // append-only: a row once held never changes
  }
  state.cursor = cursorOf(rows, at, state.cursor);
  const added = new Set(fresh.map((r) => r.id));
  const gone = trim(state, { at, limit, windowMs, now });
  // a row that was on show went (aged out, or pushed past the limit), or a new one stayed; a new row cut straight off is neither
  return gone.some((id) => !added.has(id)) || fresh.some((r) => state.map.get(r.id) === r);
}

function base(client, table, select, { eq, neq }) {
  let q = client.from(table).select(select);
  if (eq?.[0]) q = q.eq(eq[0], eq[1]);
  if (neq?.[0]) q = q.neq(neq[0], neq[1]);
  return q;
}

async function readFull(o) {
  const { client, table, state, now, select, at, limit, windowMs } = o;
  let q = base(client, table, select, o);
  if (windowMs) q = q.gte(at, new Date(now - windowMs).toISOString());
  const { data, error } = await q.order(at, { ascending: false }).limit(limit);
  if (error) return { error };
  state.map = new Map((data ?? []).map((r) => [r.id, r]));
  state.cursor = cursorOf(data, at) || new Date(now).toISOString();   // an empty list still has a place to read on from
  state.fullAt = now;
  return { rows: sortedRows(state, at), kind: "full", fetched: data?.length ?? 0 };
}

async function readDelta(o) {
  const { client, table, state, now, select, at, limit, windowMs } = o;
  const { data, error } = await base(client, table, select, o).gte(at, sinceOf(state.cursor))
    .order(at, { ascending: true }).limit(DELTA_CAP);
  if (error) return { error };
  if ((data?.length ?? 0) >= DELTA_CAP) return readFull(o);          // not a delta any more: the picture may have a hole
  const changed = mergeRows(state, data, { at, limit, windowMs, now });
  return { rows: changed ? sortedRows(state, at) : null, kind: "delta", fetched: data?.length ?? 0 };
}

/**
 * One read of an append-only `table`. `at`: its time column ("created_at", "at"). `windowMs`: only rows this recent (0 = no
 * window). `kind`: "auto" (full when one is due, else a delta), "full" or "delta". `select` must include id and `at`.
 */
export async function loadAppend({ client, table, state, now = Date.now(), select = "*", at = "created_at", limit = 1000,
  windowMs = 0, eq = null, neq = null, kind = "auto" }) {
  const o = { client, table, state, now, select, at, limit, windowMs, eq, neq };
  const k = kind === "auto" ? (wantFull(state, now) ? "full" : "delta") : !state.cursor ? "full" : kind;
  return k === "full" ? readFull(o) : readDelta(o);
}
