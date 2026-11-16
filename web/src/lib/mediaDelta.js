/* Reading media_generations without re-downloading the whole list every minute (Wan, 16 Nov 2026: Supabase restricted the
   project for exceed_egress_quota; the page was re-reading the newest 300 rows, about 518 KB, every 60 s on every open device).

   A full read happens once, and again every FULL_EVERY_MS. Between full reads the page asks only for rows whose updated_at is
   newer than the last one it saw (the column and its trigger exist since 001, no SQL). A delta read:
     - goes back OVERLAP_MS before the cursor, because a row can commit after a later one (a long transaction, a clock that is
       a little behind): the rows it fetches twice are few, the row it would otherwise miss is not seen until the next full read;
     - ignores an old row that a full read would not have listed (older than the oldest row on show, not wanted by a post), so
       a list does not grow rows that vanish again at the next full read;
     - falls back to a full read when it hits DELTA_CAP, because then the picture of "what changed" is not complete;
     - cannot see a DELETE: the page drops the row it deleted itself (dropRow), a realtime DELETE event drops the others, and
       the next full read settles anything else.
   No React and no Supabase import, so web/mediaDelta.test.mjs runs this under Node with a fake client. */

export const FULL_EVERY_MS = 15 * 60_000;
export const OVERLAP_MS = 2 * 60_000;
export const DELTA_CAP = 500;

export const newMediaState = () => ({ map: new Map(), cursor: null, fullAt: 0 });

const ms = (iso) => { const t = Date.parse(iso); return Number.isFinite(t) ? t : 0; };

/** Newest first, the order a full read returns. */
export const sortedRows = (state) =>
  [...state.map.values()].sort((a, b) => ms(b.created_at) - ms(a.created_at));

/** The largest updated_at seen, as the string the server sent (full precision), starting from `prev`. */
export function cursorOf(rows, prev = null) {
  let best = prev;
  for (const r of rows || []) {
    if (r?.updated_at && (best === null || ms(r.updated_at) > ms(best))) best = r.updated_at;
  }
  return best;
}

/** Where a delta read starts: the cursor, minus the overlap. */
export const sinceOf = (cursor, overlapMs = OVERLAP_MS) => new Date(ms(cursor) - overlapMs).toISOString();

export const wantFull = (state, now) => !state.cursor || now - state.fullAt >= FULL_EVERY_MS;

/** Forget a row the page just deleted, or a realtime DELETE named. True when it was on show. */
export const dropRow = (state, id) => state.map.delete(id);

const idsOf = (need) => (need ? need.split(",").filter(Boolean) : []);

/* Rows a post points at that are not loaded yet, fetched by id in groups of 100. A failed group ends the loop: what loaded
   still shows, and the next read tries again. */
async function fetchMissing(client, table, state, need) {
  const missing = idsOf(need).filter((id) => !state.map.has(id));
  let added = 0;
  for (let i = 0; i < missing.length; i += 100) {
    const { data, error } = await client.from(table).select("*").in("id", missing.slice(i, i + 100));
    if (error) break;
    for (const r of data ?? []) { state.map.set(r.id, r); added += 1; }
    state.cursor = cursorOf(data, state.cursor);
  }
  return added;
}

/**
 * One read. Returns { rows, full, fetched } where rows is the whole list to show, or null when nothing changed (the page
 * keeps what it has and does not re-render), or { error } when the read failed.
 * `fetched` counts rows that came over the wire, which is what costs egress.
 */
export async function loadMedia({ client, table, state, now = Date.now(), limit = 300, need = "", force = false }) {
  if (force || wantFull(state, now)) {
    const { data, error } = await client.from(table).select("*").order("created_at", { ascending: false }).limit(limit);
    if (error) return { error };
    const next = { map: new Map((data ?? []).map((r) => [r.id, r])), cursor: cursorOf(data), fullAt: now };
    const extra = await fetchMissing(client, table, next, need);
    state.map = next.map; state.cursor = next.cursor; state.fullAt = next.fullAt;
    return { rows: sortedRows(state), full: true, fetched: (data?.length ?? 0) + extra };
  }

  const { data, error } = await client.from(table).select("*")
    .gte("updated_at", sinceOf(state.cursor)).order("updated_at", { ascending: true }).limit(DELTA_CAP);
  if (error) return { error };
  if ((data?.length ?? 0) >= DELTA_CAP) return loadMedia({ client, table, state, now, limit, need, force: true });

  const wanted = new Set(idsOf(need));
  let oldest = Infinity;
  for (const r of state.map.values()) oldest = Math.min(oldest, ms(r.created_at));
  let changed = 0;
  for (const r of data ?? []) {
    const had = state.map.get(r.id);
    if (!had && !wanted.has(r.id) && ms(r.created_at) < oldest) continue;   // a full read would not list it
    if (!had || had.updated_at !== r.updated_at) { state.map.set(r.id, r); changed += 1; }
  }
  state.cursor = cursorOf(data, state.cursor);
  const extra = await fetchMissing(client, table, state, need);
  changed += extra;
  return { rows: changed ? sortedRows(state) : null, full: false, fetched: (data?.length ?? 0) + extra };
}
