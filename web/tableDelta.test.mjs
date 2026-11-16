// node tableDelta.test.mjs: a wide list is read in full once, then only what changed (lib/tableDelta.js).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { DELTA_CAP, OVERLAP_MS, SETTLE_EVERY_MS, SETTLE_FETCH_CAP, cursorOf, dropRow, loadDelta, newDeltaState, nextKind, sinceOf,
  sortedRows } from "./src/lib/tableDelta.js";

let n = 0;
const ok = (name, fn) => Promise.resolve(fn()).then(() => { n += 1; }, (e) => { console.error(`FAIL ${name}\n`, e); process.exit(1); });

/* A fake Supabase client over an in-memory table. It counts the BYTES it hands back, which is what egress is made of, and
   honours the column list, so an `id,updated_at` read is as small here as it is on the wire. */
function fake(rows) {
  const db = { rows, bytes: 0, sent: 0, calls: [], fail: false };
  db.client = {
    from() {
      const q = { cols: "*", gte: null, gt: null, inIds: null, eq: null, neq: null, ord: null, lim: Infinity };
      const b = {
        select(c = "*") { q.cols = c; return b; },
        gte(col, v) { q.gte = [col, v]; return b; },
        gt(col, v) { q.gt = [col, v]; return b; },
        eq(col, v) { q.eq = [col, v]; return b; },
        neq(col, v) { q.neq = [col, v]; return b; },
        in(col, ids) { q.inIds = ids; return b; },
        order(col, o) { q.ord = [col, o.ascending]; return b; },
        limit(k) { q.lim = k; return b; },
        then(res, rej) {
          if (db.fail) return Promise.resolve({ data: null, error: { message: "boom" } }).then(res, rej);
          let out = [...db.rows];
          if (q.eq) out = out.filter((r) => r[q.eq[0]] === q.eq[1]);
          if (q.neq) out = out.filter((r) => r[q.neq[0]] !== q.neq[1]);
          if (q.gte) out = out.filter((r) => Date.parse(r[q.gte[0]]) >= Date.parse(q.gte[1]));
          if (q.gt) out = out.filter((r) => Date.parse(r[q.gt[0]]) > Date.parse(q.gt[1]));
          if (q.inIds) out = out.filter((r) => q.inIds.includes(r.id));
          if (q.ord) out.sort((a, c) => (Date.parse(a[q.ord[0]]) - Date.parse(c[q.ord[0]])) * (q.ord[1] ? 1 : -1));
          out = out.slice(0, q.lim).map((r) => (q.cols === "*" ? { ...r } : Object.fromEntries(q.cols.split(",").map((c) => [c, r[c]]))));
          db.sent += out.length;
          db.bytes += JSON.stringify(out).length;
          db.calls.push({ cols: q.cols, gte: !!q.gte, gt: !!q.gt, inIds: !!q.inIds, n: out.length });
          return Promise.resolve({ data: out, error: null }).then(res, rej);
        },
      };
      return b;
    },
  };
  return db;
}

const T0 = Date.parse("2026-11-16T04:00:00.000Z");
const MIN = 60_000;
const iso = (min) => new Date(T0 + min * MIN).toISOString();
const BODY = "x".repeat(4000);                                             // a post is about 4.5 KB
const row = (id, created, updated = created, extra = {}) => ({ id, created_at: iso(created), updated_at: iso(updated), status: "draft", body: BODY, ...extra });
const many = (k) => Array.from({ length: k }, (_, i) => row(`r${String(i).padStart(4, "0")}`, i - k, i - k));   // all in the past, last is newest
const run = (db, state, extra = {}) => loadDelta({ client: db.client, table: "semasa_posts", state, limit: 1000, ...extra });
const ids = (rows) => rows.map((r) => r.id);

await ok("the first read is the whole list, newest first", async () => {
  const db = fake(many(10)); const st = newDeltaState();
  const out = await run(db, st, { now: T0, limit: 4 });
  assert.equal(out.kind, "full");
  assert.deepEqual(ids(out.rows), ["r0009", "r0008", "r0007", "r0006"]);
  assert.equal(out.fetched, 4);
});

await ok("a poll on a quiet list soon after: only the rows inside the overlap come again, and nothing re-renders", async () => {
  const db = fake(many(200)); const st = newDeltaState();
  await run(db, st, { now: T0 });
  db.sent = 0;
  const out = await run(db, st, { now: T0 + 90_000 });
  assert.equal(out.kind, "delta");
  assert.equal(out.rows, null);
  assert.ok(db.sent <= 3, `sent ${db.sent}`);
});

await ok("once the newest row is OVERLAP_MS old the list is calm: a poll asks for strictly newer rows and gets none", async () => {
  const db = fake(many(200)); const st = newDeltaState();
  await run(db, st, { now: T0 });
  await run(db, st, { now: T0 + 90_000 });
  assert.equal(st.calm, false, "not yet: the overlap has not passed");
  await run(db, st, { now: T0 + OVERLAP_MS + 1000 });                      // this read still looks back, then the list is calm
  assert.equal(st.calm, true);
  db.sent = 0; db.calls.length = 0;
  const out = await run(db, st, { now: T0 + OVERLAP_MS + 90_000 });
  assert.equal(db.sent, 0, "zero rows over the wire");
  assert.ok(db.calls[0].gt && !db.calls[0].gte);
  assert.equal(out.rows, null);
});

await ok("a calm list wakes up: a changed row arrives, replaces its old copy, and the overlap starts again", async () => {
  const db = fake(many(20)); const st = newDeltaState();
  await run(db, st, { now: T0 });
  await run(db, st, { now: T0 + OVERLAP_MS + 1 });
  assert.equal(st.calm, true);
  Object.assign(db.rows.find((r) => r.id === "r0003"), { status: "approved", updated_at: iso(3) });
  const out = await run(db, st, { now: T0 + 4 * MIN });                    // before a settle is due
  assert.equal(out.kind, "delta");
  assert.equal(out.rows.find((r) => r.id === "r0003").status, "approved");
  assert.equal(out.rows.length, 20);
  assert.equal(st.calm, false);
  assert.equal(st.cursor, iso(3));
});

await ok("a new row goes to the top", async () => {
  const db = fake(many(5)); const st = newDeltaState();
  await run(db, st, { now: T0 });
  db.rows.push(row("fresh", 1));
  const out = await run(db, st, { now: T0 + 90_000 });
  assert.equal(out.rows[0].id, "fresh");
  assert.equal(out.rows.length, 6);
});

await ok("a row that commits late, with an updated_at just before the cursor, is still seen inside the overlap", async () => {
  const db = fake(many(5)); const st = newDeltaState();
  await run(db, st, { now: T0 });                                          // cursor = minute -1
  db.rows.push(row("late", -1.5));                                         // older than the cursor, arrived after the read
  const out = await run(db, st, { now: T0 + 60_000 });
  assert.ok(ids(out.rows).includes("late"));
});

await ok("the list never grows past its limit: a new row pushes the oldest one off", async () => {
  const db = fake(many(30)); const st = newDeltaState();
  await run(db, st, { now: T0, limit: 10 });
  db.rows.push(row("fresh", 1));
  const out = await run(db, st, { now: T0 + 60_000, limit: 10 });
  assert.equal(out.rows.length, 10);
  assert.equal(out.rows[0].id, "fresh");
  assert.ok(!ids(out.rows).includes("r0020"), "the row that was tenth is gone");
});

await ok("an old row past the limit that changes is not added, and nothing re-renders", async () => {
  const db = fake(many(30)); const st = newDeltaState();
  await run(db, st, { now: T0, limit: 10 });
  db.rows.find((r) => r.id === "r0001").updated_at = iso(1);
  const out = await run(db, st, { now: T0 + 60_000, limit: 10 });
  assert.equal(out.rows, null);
  assert.equal(st.map.size, 10);
});

await ok("a delta read cannot see a delete; the settle does, for the price of ids", async () => {
  const db = fake(many(100)); const st = newDeltaState();
  await run(db, st, { now: T0 });
  db.rows = db.rows.filter((r) => r.id !== "r0042");                       // deleted on another device
  let out = await run(db, st, { now: T0 + 60_000 });
  assert.equal(out.rows, null);
  assert.equal(nextKind(st, T0 + SETTLE_EVERY_MS), "settle");
  db.bytes = 0; db.calls.length = 0;
  out = await run(db, st, { now: T0 + SETTLE_EVERY_MS });
  assert.equal(out.kind, "settle");
  assert.ok(!ids(out.rows).includes("r0042"));
  assert.equal(out.rows.length, 99);
  assert.equal(db.calls[0].cols, "id,updated_at");
  assert.ok(db.bytes < 100 * 120, `a settle of 100 rows cost ${db.bytes} bytes, not ${100 * 4100}`);
});

await ok("a settle fetches by id exactly the rows that are new or changed, and says nothing when all is the same", async () => {
  const db = fake(many(50)); const st = newDeltaState();
  await run(db, st, { now: T0 });
  let out = await run(db, st, { now: T0 + 1000, kind: "settle" });
  assert.equal(out.rows, null, "nothing changed: no re-render");
  Object.assign(db.rows.find((r) => r.id === "r0007"), { status: "posted", updated_at: iso(2) });
  db.rows.push(row("fresh", 3));
  db.calls.length = 0;
  out = await run(db, st, { now: T0 + 2000, kind: "settle" });
  const byId = db.calls.find((c) => c.inIds);
  assert.equal(byId.n, 2);
  assert.equal(out.rows.find((r) => r.id === "r0007").status, "posted");
  assert.equal(out.rows[0].id, "fresh");
  assert.equal(st.cursor, iso(3));
});

await ok("a settle that would fetch too many rows by id reads in full instead", async () => {
  const db = fake(many(SETTLE_FETCH_CAP + 20)); const st = newDeltaState();
  await run(db, st, { now: T0 });
  db.rows.forEach((r) => { r.updated_at = iso(5); });
  const out = await run(db, st, { now: T0 + 1000, kind: "settle" });
  assert.equal(out.kind, "full");
});

await ok("a delta that hits the cap is not a delta: it reads in full", async () => {
  const db = fake(many(DELTA_CAP + 50)); const st = newDeltaState();
  await run(db, st, { now: T0 });
  db.rows.forEach((r) => { r.updated_at = iso(5); });
  const out = await run(db, st, { now: T0 + 60_000 });
  assert.equal(out.kind, "full");
  assert.equal(out.rows.length, DELTA_CAP + 50);
});

await ok("a filter is carried by every kind of read, and a row that leaves the filter leaves the list at the settle", async () => {
  const rows = [...many(6).map((r, i) => ({ ...r, section: i % 2 ? "expert" : "regulatory" }))];
  const db = fake(rows); const st = newDeltaState();
  const opts = { neq: ["section", "expert"] };
  let out = await run(db, st, { now: T0, ...opts });
  assert.deepEqual(ids(out.rows), ["r0004", "r0002", "r0000"]);
  db.rows.push({ ...row("e1", 1), section: "expert" }, { ...row("g1", 1), section: "regulatory" });
  out = await run(db, st, { now: T0 + 60_000, ...opts });
  assert.deepEqual(ids(out.rows).slice(0, 1), ["g1"]);
  assert.ok(!ids(out.rows).includes("e1"));
  Object.assign(db.rows.find((r) => r.id === "r0002"), { section: "expert", updated_at: iso(2) });
  out = await run(db, st, { now: T0 + 120_000, ...opts, kind: "settle" });
  assert.ok(!ids(out.rows).includes("r0002"));
});

await ok("rows written in one statement share a created_at: their order is the same after every kind of read", async () => {
  const same = ["c", "a", "b"].map((id) => row(id, -5));
  const db = fake([...same, row("z", -9)]); const st = newDeltaState();
  const full = await run(db, st, { now: T0 });
  db.rows.find((r) => r.id === "a").updated_at = iso(1);
  const delta = await run(db, st, { now: T0 + 60_000 });
  assert.deepEqual(ids(full.rows), ["a", "b", "c", "z"]);
  assert.deepEqual(ids(delta.rows), ["a", "b", "c", "z"]);
});

await ok("ascending order and a non-date order column sort the way the query does", async () => {
  const st = newDeltaState();
  st.map = new Map([["1", { id: "1", name: "beta" }], ["2", { id: "2", name: "Alpha" }], ["3", { id: "3", name: null }]]);
  assert.deepEqual(ids(sortedRows(st, "name", true)), ["2", "1", "3"]);
});

await ok("dropRow removes a deleted row at once", async () => {
  const db = fake(many(4)); const st = newDeltaState();
  await run(db, st, { now: T0 });
  assert.equal(dropRow(st, "r0001"), true);
  assert.equal(dropRow(st, "r0001"), false);
  assert.equal(sortedRows(st).length, 3);
});

await ok("a failed read of any kind reports the error and leaves what is on show alone", async () => {
  const db = fake(many(4)); const st = newDeltaState();
  await run(db, st, { now: T0 });
  db.fail = true;
  for (const kind of ["delta", "settle", "full"]) {
    const out = await run(db, st, { now: T0 + 60_000, kind });
    assert.ok(out.error, kind);
    assert.equal(sortedRows(st).length, 4, kind);
  }
});

await ok("an empty list still reads on: the first row to arrive is seen by a delta", async () => {
  const db = fake([]); const st = newDeltaState();
  let out = await run(db, st, { now: T0 });
  assert.deepEqual(out.rows, []);
  db.rows.push(row("first", 1));
  out = await run(db, st, { now: T0 + 90_000 });
  assert.equal(out.kind, "delta");
  assert.deepEqual(ids(out.rows), ["first"]);
});

await ok("helpers", () => {
  assert.equal(cursorOf([{ updated_at: iso(1) }, { updated_at: iso(9) }, { updated_at: iso(4) }]), iso(9));
  assert.equal(cursorOf([], iso(2)), iso(2));
  assert.equal(sinceOf(iso(10)), new Date(Date.parse(iso(10)) - OVERLAP_MS).toISOString());
  assert.equal(nextKind(newDeltaState(), T0), "full");
});

// the point of it all: an hour on one open device with the three lists as they were on 16 Nov 2026 (rows and bytes measured
// in the database that day), a poll every 90 s, a handful of changes
await ok("an hour of polls moves a small fraction of the bytes the old way did", async () => {
  const lists = [["posts", 223, 4500], ["ideas", 487, 1430], ["faqs", 888, 2615]];
  let oldBytes = 0; let newBytes = 0;
  for (const [name, count, size] of lists) {
    const rows = Array.from({ length: count }, (_, i) => ({ id: `${name}${i}`, created_at: iso(i - count), updated_at: iso(i - count), body: "x".repeat(size - 110) }));
    const db = fake(rows); const st = newDeltaState();
    const one = JSON.stringify(rows).length;
    await loadDelta({ client: db.client, table: name, state: st, now: T0, limit: 3000 });
    for (let i = 1; i <= 40; i += 1) {
      if (i % 8 === 0) Object.assign(db.rows[i], { updated_at: new Date(T0 + i * 90_000 - 5000).toISOString() });   // five changes in the hour
      await loadDelta({ client: db.client, table: name, state: st, now: T0 + i * 90_000, limit: 3000 });
    }
    oldBytes += one * 41; newBytes += db.bytes;
  }
  const mb = (b) => (b / 1e6).toFixed(1);
  console.log(`  bytes over the wire in an hour, three lists: ${mb(newBytes)} MB (old way ${mb(oldBytes)} MB), ${(100 - (newBytes / oldBytes) * 100).toFixed(1)}% fewer`);
  assert.ok(newBytes < oldBytes * 0.06, `${newBytes} vs ${oldBytes}`);
});

// the wiring: these lists use the loader, and the widest one is read only where it is shown
await ok("posts, ideas, FAQ and films are read as deltas; FAQ only while its tab is open", () => {
  const app = readFileSync(new URL("./src/App.jsx", import.meta.url), "utf8");
  assert.match(app, /useTable\(TABLES\.posts, \{[^}]*delta: true/);
  assert.match(app, /useTable\(TABLES\.ideas, \{[^}]*delta: true/);
  assert.match(app, /useTable\(TABLES\.faqs, \{ enabled: allowed && tab === "faq",[^}]*delta: true/);
  assert.match(readFileSync(new URL("./src/components/MotionLab.jsx", import.meta.url), "utf8"), /useTable\(TABLES\.motions, \{[^}]*delta: true/);
  const hooks = readFileSync(new URL("./src/lib/hooks.js", import.meta.url), "utf8");
  assert.match(hooks, /load\(delta \? "settle" : undefined\)/, "reload after the page's own write checks the ids, so a deleted row leaves");
});

console.log(`tableDelta: ${n} groups pass`);
