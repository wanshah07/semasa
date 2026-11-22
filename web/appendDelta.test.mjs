// node appendDelta.test.mjs: an append-only list (semasa_log, semasa_api_usage) is read in full once, then only what is new
// (lib/appendDelta.js).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { DELTA_CAP, FULL_EVERY_MS, OVERLAP_MS, dropRow, loadAppend, mergeRows, newAppendState, sortedRows } from "./src/lib/appendDelta.js";

let n = 0;
const ok = (name, fn) => Promise.resolve(fn()).then(() => { n += 1; }, (e) => { console.error(`FAIL ${name}\n`, e); process.exit(1); });

/* A fake Supabase client over an in-memory table that counts what it sends and honours the column list. */
function fake(rows) {
  const db = { rows, sent: 0, bytes: 0, calls: [], fail: false };
  db.client = {
    from() {
      const q = { cols: "*", gte: null, eq: null, neq: null, ord: null, lim: Infinity };
      const b = {
        select(c = "*") { q.cols = c; return b; },
        gte(col, v) { q.gte = [col, v]; return b; },
        eq(col, v) { q.eq = [col, v]; return b; },
        neq(col, v) { q.neq = [col, v]; return b; },
        order(col, o) { q.ord = [col, o.ascending]; return b; },
        limit(k) { q.lim = k; return b; },
        then(res, rej) {
          if (db.fail) return Promise.resolve({ data: null, error: { message: "boom" } }).then(res, rej);
          let out = [...db.rows];
          if (q.eq) out = out.filter((r) => r[q.eq[0]] === q.eq[1]);
          if (q.neq) out = out.filter((r) => r[q.neq[0]] !== q.neq[1]);
          if (q.gte) out = out.filter((r) => Date.parse(r[q.gte[0]]) >= Date.parse(q.gte[1]));
          if (q.ord) out.sort((a, c) => (Date.parse(a[q.ord[0]]) - Date.parse(c[q.ord[0]])) * (q.ord[1] ? 1 : -1));
          out = out.slice(0, q.lim).map((r) => (q.cols === "*" ? { ...r } : Object.fromEntries(q.cols.split(",").map((c) => [c, r[c]]))));
          db.sent += out.length; db.bytes += JSON.stringify(out).length;
          db.calls.push({ cols: q.cols, gte: !!q.gte, neq: q.neq, n: out.length });
          return Promise.resolve({ data: out, error: null }).then(res, rej);
        },
      };
      return b;
    },
  };
  return db;
}

const T0 = Date.parse("2026-11-22T04:00:00.000Z");
const MIN = 60_000;
const iso = (min) => new Date(T0 + min * MIN).toISOString();
const DETAIL = { note: "x".repeat(300) };
let seq = 0;
const line = (min, extra = {}) => ({ id: ++seq, at: iso(min), level: "info", area: "post", event: "e", title: "t", detail: DETAIL, ...extra });
const many = (k) => Array.from({ length: k }, (_, i) => line(i - k));          // one a minute, the newest a minute ago
const LOG = { table: "semasa_log", at: "at", limit: 3000 };
const run = (db, st, extra = {}) => loadAppend({ client: db.client, state: st, ...LOG, ...extra });
const ids = (rows) => rows.map((r) => r.id);

await ok("the first read is the whole list, newest first, cut at the limit", async () => {
  seq = 0; const db = fake(many(10)); const st = newAppendState();
  const out = await run(db, st, { now: T0, limit: 4 });
  assert.equal(out.kind, "full");
  assert.deepEqual(ids(out.rows), [10, 9, 8, 7]);
  assert.equal(out.fetched, 4);
});

await ok("a poll on a quiet list asks only for the overlap and re-renders nothing", async () => {
  seq = 0; const db = fake(many(3000)); const st = newAppendState();
  await run(db, st, { now: T0 });
  const full = db.bytes; db.sent = 0; db.bytes = 0;
  const out = await run(db, st, { now: T0 + 90_000 });
  assert.equal(out.kind, "delta");
  assert.equal(out.rows, null);
  assert.ok(db.sent <= OVERLAP_MS / MIN + 1, `sent ${db.sent}`);
  assert.ok(db.bytes * 100 < full, `a quiet poll cost ${db.bytes} bytes against ${full} for the full read`);
});

await ok("new lines are merged in at the top and the list stays at its limit", async () => {
  seq = 0; const db = fake(many(50)); const st = newAppendState();
  await run(db, st, { now: T0, limit: 50 });
  db.rows.push(line(2), line(3));
  const out = await run(db, st, { now: T0 + 4 * MIN, limit: 50 });
  assert.equal(out.kind, "delta");
  assert.deepEqual(ids(out.rows).slice(0, 3), [52, 51, 50]);
  assert.equal(out.rows.length, 50);
  assert.ok(!out.rows.some((r) => r.id === 1), "the oldest went to make room, as a full read would have it");
});

await ok("a delta that comes back full is not trusted: the list is read in full", async () => {
  seq = 0; const db = fake(many(5)); const st = newAppendState();
  await run(db, st, { now: T0 });
  for (let i = 0; i < DELTA_CAP + 5; i++) db.rows.push(line(1 + i / 1000));
  const out = await run(db, st, { now: T0 + 2 * MIN });
  assert.equal(out.kind, "full");
});

await ok("a full read again every FULL_EVERY_MS settles what a delta cannot see (a line housekeeping deleted)", async () => {
  seq = 0; const db = fake(many(20)); const st = newAppendState();
  await run(db, st, { now: T0 });
  db.rows = db.rows.filter((r) => r.id !== 5);
  assert.equal((await run(db, st, { now: T0 + 10 * MIN })).rows, null);
  const out = await run(db, st, { now: T0 + FULL_EVERY_MS });
  assert.equal(out.kind, "full");
  assert.ok(!ids(out.rows).includes(5));
});

await ok("a window keeps only recent rows, and rows age out of it between full reads", async () => {
  seq = 0; const db = fake([line(-400), line(-200), line(-10)]); const st = newAppendState();
  const W = 5 * 60 * MIN;
  const out = await run(db, st, { now: T0, windowMs: W, table: "semasa_api_usage" });
  assert.deepEqual(ids(out.rows), [3, 2]);
  assert.ok(db.calls[0].gte, "the window is asked of the server, not filtered after the download");
  const later = await run(db, st, { now: T0 + 150 * MIN, windowMs: W });
  assert.deepEqual(ids(later.rows), [3], "the 200-minute-old row is now past the window");
});

await ok("a filter goes to the server on every read (the API pulse's rows never cross the wire)", async () => {
  seq = 0;
  const rows = [line(-3, { area: "pulse" }), line(-2, { area: "media" }), line(-1, { area: "pulse" })];
  const db = fake(rows); const st = newAppendState();
  const out = await run(db, st, { now: T0, neq: ["area", "pulse"] });
  assert.deepEqual(ids(out.rows), [2]);
  db.rows.push(line(1, { area: "pulse" }), line(1.5, { area: "chat" }));
  const d = await run(db, st, { now: T0 + 2 * MIN, neq: ["area", "pulse"] });
  assert.deepEqual(ids(d.rows), [5, 2]);
  assert.ok(db.calls.every((c) => c.neq?.[1] === "pulse"));
});

await ok("a realtime INSERT is merged with no read; a row already held changes nothing", () => {
  seq = 0; const st = newAppendState();
  st.cursor = iso(0);
  assert.equal(mergeRows(st, [line(1)], { at: "at", limit: 3 }), true);
  assert.equal(mergeRows(st, [{ ...st.map.get(1) }], { at: "at", limit: 3 }), false);
  mergeRows(st, [line(2), line(3), line(4)], { at: "at", limit: 3 });
  assert.deepEqual(ids(sortedRows(st, "at")), [4, 3, 2]);
  assert.equal(st.cursor, iso(4));
  assert.equal(mergeRows(st, [line(-50)], { at: "at", limit: 3 }), false, "an old row past the limit is cut straight off again");
});

await ok("a DELETE event drops the row; a failed read keeps the list and says so", async () => {
  seq = 0; const db = fake(many(5)); const st = newAppendState();
  await run(db, st, { now: T0 });
  assert.equal(dropRow(st, 3), true);
  assert.equal(dropRow(st, 3), false);
  db.fail = true;
  const out = await run(db, st, { now: T0 + MIN });
  assert.ok(out.error);
  assert.equal(st.map.size, 4);
});

await ok("rows of one moment keep one order (by id), so a list never reshuffles between reads", () => {
  const st = newAppendState();
  const at = iso(0);
  mergeRows(st, [{ id: 2, at }, { id: 10, at }, { id: 7, at }], { at: "at" });
  assert.deepEqual(ids(sortedRows(st, "at")), [10, 7, 2]);
});

// the wiring: the Log tab reads named columns as an append list, and the two usage pages no longer read thousands of raw rows
await ok("the log and AI usage are read through the append reader, the usage charts through the daily totals", () => {
  const app = readFileSync(new URL("./src/App.jsx", import.meta.url), "utf8");
  assert.match(app, /useTable\(TABLES\.log, \{[^}]*select: LOG_COLUMNS, append: \{ windowMs: 0 \}, liveWaitMs: 5000/);
  assert.doesNotMatch(/const LOG_COLUMNS = "([^"]+)"/.exec(app)[1], /\*/);
  for (const page of ["HomeTab", "ApiTab"]) {
    const src = readFileSync(new URL(`./src/pages/${page}.jsx`, import.meta.url), "utf8");
    assert.match(src, /useApiUsage\(\{ days: (14|90)/, page);
    assert.doesNotMatch(src, /useTable\(TABLES\.apiUsage/, `${page} reads usage only through useApiUsage`);
  }
  const hooks = readFileSync(new URL("./src/lib/hooks.js", import.meta.url), "utf8");
  assert.match(hooks, /neq: rawPulse \? null : \["area", "pulse"\]/, "Papan's raw fallback leaves the pulse out on the server");
});

console.log(`appendDelta: ${n} cases ok`);
