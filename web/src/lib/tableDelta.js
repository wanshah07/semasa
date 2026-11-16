/* Reading a wide list without downloading all of it on every poll (Wan, 16 Nov 2026: "compactkan atau improve supaya supabase
   egress database not too much"). Measured that day, one open tab: semasa_faqs 2.3 MB, semasa_posts 1.0 MB and semasa_ideas
   0.7 MB, each re-read in full every 90 seconds and on every realtime event, about 160 MB an hour for three lists that change
   a few times a day. lib/mediaDelta.js did this for media_generations; this is the same idea for any table that has an
   `updated_at` column kept by the semasa_set_updated_at trigger (posts, ideas, FAQ, motions and most others).

   Three kinds of read:
     full    the whole list, once (and again only when a cheaper read cannot be trusted);
     delta   rows whose updated_at is newer than the last one seen. For OVERLAP_MS after the newest row arrived the read goes
             back OVERLAP_MS before it, because a row can commit after a later one; once that time has passed with nothing
             new, the list is "calm" and a poll asks only for rows strictly newer, which on a quiet list is no rows at all;
     settle  `id, updated_at` for the whole list (about 80 bytes a row instead of kilobytes): rows that are gone are dropped,
             rows that are new or changed are fetched by id. This is what sees a DELETE, a row that left the filter, and
             anything a delta missed. It runs every SETTLE_EVERY_MS and whenever the page asks to reload after its own write.
   Every read returns { rows, kind, fetched }: rows is the whole list in order, or null when nothing changed (the page keeps
   the array it has, so an open form is not reset); fetched counts rows that crossed the wire. A failed read returns { error }
   and leaves what is on show alone.
   No React and no Supabase import, so web/tableDelta.test.mjs runs this under Node with a fake client. */

export const SETTLE_EVERY_MS = 5 * 60_000;
export const OVERLAP_MS = 2 * 60_000;
export const DELTA_CAP = 300;       // a delta this large is not a delta: read in full
export const SETTLE_FETCH_CAP = 200; // so is a settle that would fetch this many rows by id

export const newDeltaState = () => ({ map: new Map(), cursor: null, cursorAt: 0, calm: false, settledAt: 0 });

const ms = (iso) => { const t = Date.parse(iso); return Number.isFinite(t) ? t : 0; };

/* One order for every kind of read, so a list never reshuffles between a full read and a delta: the order column (dates as
   dates, numbers as numbers, the rest as text), then id, because rows written in one statement share a created_at. */
function comparer(order, ascending) {
  const dir = ascending ? 1 : -1;
  const isDate = /(_at|^at|_date)$/.test(order);
  return (a, b) => {
    const x = a?.[order]; const y = b?.[order];
    let c = 0;
    if (x == null && y != null) c = 1;            // nulls last, as Postgres does for ascending; kept last either way
    else if (x != null && y == null) c = -1;
    else if (x != null && y != null) {
      if (isDate) c = (ms(x) - ms(y)) * dir;
      else if (typeof x === "number" && typeof y === "number") c = (x - y) * dir;
      else c = String(x).localeCompare(String(y)) * dir;
    }
    return c || String(a?.id).localeCompare(String(b?.id));
  };
}

export const sortedRows = (state, order = "created_at", ascending = false) => [...state.map.values()].sort(comparer(order, ascending));

/** The largest updated_at seen, as the string the server sent. */
export function cursorOf(rows, prev = null) {
  let best = prev;
  for (const r of rows || []) {
    if (r?.updated_at && (best === null || ms(r.updated_at) > ms(best))) best = r.updated_at;
  }
  return best;
}

export const sinceOf = (cursor, overlapMs = OVERLAP_MS) => new Date(ms(cursor) - overlapMs).toISOString();

/* Move the cursor to the newest updated_at in `rows`. A cursor that moved starts the overlap again; one that has stood still
   for OVERLAP_MS, through a read that looked back over the overlap, makes the list calm. */
function advance(state, rows, now, lookedBack = false) {
  const next = cursorOf(rows, state.cursor);
  if (next !== state.cursor) { state.cursor = next; state.cursorAt = now; state.calm = false; }
  else if (lookedBack && now - state.cursorAt >= OVERLAP_MS) state.calm = true;
}

/** Forget a row the page just deleted, or a realtime DELETE named. True when it was on show. */
export const dropRow = (state, id) => state.map.delete(id);

/** Which read the next poll should be. */
export const nextKind = (state, now) => (!state.cursor ? "full" : now - state.settledAt >= SETTLE_EVERY_MS ? "settle" : "delta");

function base(client, table, columns, { eq, neq }) {
  let q = client.from(table).select(columns);
  if (eq?.[0]) q = q.eq(eq[0], eq[1]);
  if (neq?.[0]) q = q.neq(neq[0], neq[1]);
  return q;
}

/* Keep the list no longer than a full read would return it: the rows past `limit` in order are dropped. */
function trim(state, order, ascending, limit) {
  if (state.map.size <= limit) return;
  const keep = sortedRows(state, order, ascending).slice(0, limit);
  state.map = new Map(keep.map((r) => [r.id, r]));
}

async function readFull(o) {
  const { client, table, state, now, select, order, ascending, limit } = o;
  const { data, error } = await base(client, table, select, o).order(order, { ascending }).limit(limit);
  if (error) return { error };
  state.map = new Map((data ?? []).map((r) => [r.id, r]));
  state.cursor = cursorOf(data) || new Date(now).toISOString();   // an empty list still has a place to read on from
  state.cursorAt = now; state.calm = false;
  state.settledAt = now;
  return { rows: sortedRows(state, order, ascending), kind: "full", fetched: data?.length ?? 0 };
}

async function readDelta(o) {
  const { client, table, state, now, select, order, ascending, limit } = o;
  const calm = state.calm;
  const q = base(client, table, select, o);
  const { data, error } = await (calm ? q.gt("updated_at", state.cursor) : q.gte("updated_at", sinceOf(state.cursor)))
    .order("updated_at", { ascending: true }).limit(DELTA_CAP);
  if (error) return { error };
  if ((data?.length ?? 0) >= DELTA_CAP) return readFull(o);
  const fresh = [];
  for (const r of data ?? []) {
    const had = state.map.get(r.id);
    if (!had || had.updated_at !== r.updated_at) { state.map.set(r.id, r); fresh.push(r); }
  }
  advance(state, data, now, !calm);
  if (fresh.length) trim(state, order, ascending, limit);
  // an old row that landed past the limit was cut straight off again: nothing on show changed
  const changed = fresh.some((r) => state.map.get(r.id) === r);
  return { rows: changed ? sortedRows(state, order, ascending) : null, kind: "delta", fetched: data?.length ?? 0 };
}

async function readSettle(o) {
  const { client, table, state, now, select, order, ascending, limit } = o;
  const { data, error } = await base(client, table, "id,updated_at", o).order(order, { ascending }).limit(limit);
  if (error) return { error };
  const listed = new Map((data ?? []).map((r) => [r.id, r.updated_at]));
  const want = [];
  for (const [id, at] of listed) {
    const had = state.map.get(id);
    if (!had || had.updated_at !== at) want.push(id);
  }
  if (want.length >= SETTLE_FETCH_CAP) return readFull(o);
  const got = [];
  for (let i = 0; i < want.length; i += 100) {
    const part = await client.from(table).select(select).in("id", want.slice(i, i + 100));
    if (part.error) return { error: part.error };
    got.push(...(part.data ?? []));
  }
  let changed = 0;
  for (const id of [...state.map.keys()]) {
    if (!listed.has(id)) { state.map.delete(id); changed += 1; }
  }
  for (const r of got) { state.map.set(r.id, r); changed += 1; }
  advance(state, [...(data ?? []), ...got], now);
  state.settledAt = now;
  return { rows: changed ? sortedRows(state, order, ascending) : null, kind: "settle", fetched: (data?.length ?? 0) + got.length };
}

/**
 * One read of `table`. `kind`: "auto" (full the first time, a settle when one is due, else a delta), or "full" / "settle" /
 * "delta" to ask for one. `select` must include id and updated_at ("*" does).
 */
export async function loadDelta({ client, table, state, now = Date.now(), select = "*", order = "created_at", ascending = false,
  limit = 200, eq = null, neq = null, kind = "auto" }) {
  const o = { client, table, state, now, select, order, ascending, limit, eq, neq };
  const k = !state.cursor ? "full" : kind === "auto" ? nextKind(state, now) : kind;
  if (k === "full") return readFull(o);
  if (k === "settle") return readSettle(o);
  return readDelta(o);
}
