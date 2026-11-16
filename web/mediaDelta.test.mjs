// node mediaDelta.test.mjs: the media list is read in full once, then only what changed (lib/mediaDelta.js).
import assert from "node:assert/strict";
import { DELTA_CAP, FULL_EVERY_MS, OVERLAP_MS, cursorOf, dropRow, loadMedia, newMediaState, sinceOf, sortedRows, wantFull } from "./src/lib/mediaDelta.js";

let n = 0;
const ok = (name, fn) => Promise.resolve(fn()).then(() => { n += 1; }, (e) => { console.error(`FAIL ${name}\n`, e); process.exit(1); });

/* A fake Supabase client over an in-memory table. It counts the rows it hands back, which is what egress is made of. */
function fake(rows) {
  const db = { rows, sent: 0, calls: [], fail: false };
  db.client = {
    from() {
      const q = { sel: false, gte: null, inIds: null, ord: null, lim: Infinity };
      const b = {
        select() { q.sel = true; return b; },
        gte(col, v) { q.gte = [col, v]; return b; },
        in(col, ids) { q.inIds = ids; return b; },
        order(col, o) { q.ord = [col, o.ascending]; return b; },
        limit(k) { q.lim = k; return b; },
        then(res, rej) {
          if (db.fail) return Promise.resolve({ data: null, error: { message: "boom" } }).then(res, rej);
          let out = [...db.rows];
          if (q.gte) out = out.filter((r) => Date.parse(r[q.gte[0]]) >= Date.parse(q.gte[1]));
          if (q.inIds) out = out.filter((r) => q.inIds.includes(r.id));
          if (q.ord) out.sort((a, c) => (Date.parse(a[q.ord[0]]) - Date.parse(c[q.ord[0]])) * (q.ord[1] ? 1 : -1));
          out = out.slice(0, q.lim).map((r) => ({ ...r }));   // a real read returns fresh copies
          db.sent += out.length;
          db.calls.push({ gte: !!q.gte, inIds: !!q.inIds, n: out.length });
          return Promise.resolve({ data: out, error: null }).then(res, rej);
        },
      };
      return b;
    },
  };
  return db;
}

const T0 = Date.parse("2026-11-16T04:00:00.000Z");
const iso = (min) => new Date(T0 + min * 60_000).toISOString();
const row = (id, created, updated = created) => ({ id, created_at: iso(created), updated_at: iso(updated), status: "done" });
const many = (k) => Array.from({ length: k }, (_, i) => row(`r${i}`, i, i));   // r{k-1} is the newest

const run = (db, state, extra = {}) => loadMedia({ client: db.client, table: "media_generations", state, ...extra });

await ok("first read is full and newest first", async () => {
  const db = fake(many(10)); const st = newMediaState();
  const out = await run(db, st, { now: T0, limit: 4 });
  assert.equal(out.full, true);
  assert.deepEqual(out.rows.map((r) => r.id), ["r9", "r8", "r7", "r6"]);
  assert.equal(out.fetched, 4);
});

await ok("a second read with nothing new sends (almost) nothing and says rows unchanged", async () => {
  const db = fake(many(300)); const st = newMediaState();
  await run(db, st, { now: T0 });
  db.sent = 0;
  const out = await run(db, st, { now: T0 + 60_000 });
  assert.equal(out.full, false);
  assert.equal(out.rows, null, "no new list, so the page does not re-render");
  // only rows inside the 2-minute overlap come back again; the other ~295 stay home
  assert.ok(db.sent <= 5, `sent ${db.sent}`);
});

await ok("a changed row arrives and replaces its old copy", async () => {
  const db = fake(many(20)); const st = newMediaState();
  await run(db, st, { now: T0, limit: 20 });
  db.rows.find((r) => r.id === "r3").status = "error"; db.rows.find((r) => r.id === "r3").updated_at = iso(50);
  const out = await run(db, st, { now: T0 + 60_000, limit: 20 });
  assert.equal(out.full, false);
  assert.equal(out.rows.find((r) => r.id === "r3").status, "error");
  assert.equal(out.rows.length, 20);
});

await ok("a new row is added at the top", async () => {
  const db = fake(many(5)); const st = newMediaState();
  await run(db, st, { now: T0, limit: 5 });
  db.rows.push(row("fresh", 60));
  const out = await run(db, st, { now: T0 + 60_000, limit: 5 });
  assert.equal(out.rows[0].id, "fresh");
  assert.equal(out.rows.length, 6);
});

await ok("a row updated a moment BEFORE the cursor (late commit) is still seen: the overlap", async () => {
  const db = fake(many(5)); const st = newMediaState();
  await run(db, st, { now: T0, limit: 5 });          // cursor = r4's updated_at, minute 4
  db.rows.push({ id: "late", created_at: iso(3.5), updated_at: iso(3.5), status: "done" });   // older than the cursor
  const out = await run(db, st, { now: T0 + 60_000, limit: 5 });
  assert.ok(out.rows.some((r) => r.id === "late"), "found inside the overlap");
});

await ok("an old row that a full read would not list is ignored unless a post wants it", async () => {
  const db = fake(many(30)); const st = newMediaState();
  await run(db, st, { now: T0, limit: 10 });          // shows r29..r20
  db.rows.find((r) => r.id === "r1").updated_at = iso(99);
  let out = await run(db, st, { now: T0 + 60_000, limit: 10 });
  assert.equal(out.rows, null, "r1 is old news: not added, no re-render");
  assert.ok(!sortedRows(st).some((r) => r.id === "r1"));
  out = await run(db, st, { now: T0 + 120_000, limit: 10, need: "r1" });
  assert.ok(out.rows.some((r) => r.id === "r1"), "but a post that points at it gets it");
});

await ok("a needed old row is fetched by id once, not on every read", async () => {
  const db = fake(many(30)); const st = newMediaState();
  let out = await run(db, st, { now: T0, limit: 10, need: "r2,r3" });
  assert.deepEqual(out.rows.slice(-2).map((r) => r.id).sort(), ["r2", "r3"]);
  db.calls.length = 0;
  out = await run(db, st, { now: T0 + 60_000, limit: 10, need: "r2,r3" });
  assert.ok(!db.calls.some((c) => c.inIds), "already loaded: no by-id read");
});

await ok("a need that appears later is fetched by id on the next delta read", async () => {
  const db = fake(many(30)); const st = newMediaState();
  await run(db, st, { now: T0, limit: 10 });
  const out = await run(db, st, { now: T0 + 60_000, limit: 10, need: "r5" });
  assert.equal(out.full, false);
  assert.ok(out.rows.some((r) => r.id === "r5"));
});

await ok("a delta that hits the cap is incomplete, so it falls back to a full read", async () => {
  const db = fake(many(DELTA_CAP + 50)); const st = newMediaState();
  await run(db, st, { now: T0, limit: 20 });
  db.rows.forEach((r) => { r.updated_at = iso(2000); });                  // everything changed at once
  const out = await run(db, st, { now: T0 + 60_000, limit: 20 });
  assert.equal(out.full, true);
  assert.equal(out.rows.length, 20);
});

await ok("a full read again after FULL_EVERY_MS settles deletes made elsewhere", async () => {
  const db = fake(many(6)); const st = newMediaState();
  await run(db, st, { now: T0, limit: 6 });
  db.rows = db.rows.filter((r) => r.id !== "r2");                         // deleted on another device
  let out = await run(db, st, { now: T0 + 60_000, limit: 6 });
  assert.equal(out.rows, null, "a delta read cannot see a delete");
  assert.equal(wantFull(st, T0 + FULL_EVERY_MS + 1), true);
  out = await run(db, st, { now: T0 + FULL_EVERY_MS + 1, limit: 6 });
  assert.equal(out.full, true);
  assert.ok(!out.rows.some((r) => r.id === "r2"));
});

await ok("dropRow removes a deleted row at once", async () => {
  const db = fake(many(4)); const st = newMediaState();
  await run(db, st, { now: T0, limit: 4 });
  assert.equal(dropRow(st, "r1"), true);
  assert.equal(dropRow(st, "r1"), false);
  assert.ok(!sortedRows(st).some((r) => r.id === "r1"));
});

await ok("a failed read reports the error and leaves what is on show alone", async () => {
  const db = fake(many(4)); const st = newMediaState();
  await run(db, st, { now: T0, limit: 4 });
  db.fail = true;
  const out = await run(db, st, { now: T0 + 60_000, limit: 4 });
  assert.ok(out.error);
  assert.equal(sortedRows(st).length, 4);
});

await ok("force asks for a full read", async () => {
  const db = fake(many(4)); const st = newMediaState();
  await run(db, st, { now: T0, limit: 4 });
  const out = await run(db, st, { now: T0 + 1000, limit: 4, force: true });
  assert.equal(out.full, true);
});

await ok("helpers: cursor is the newest updated_at, since() goes back by the overlap", () => {
  assert.equal(cursorOf([{ updated_at: iso(1) }, { updated_at: iso(9) }, { updated_at: iso(4) }]), iso(9));
  assert.equal(cursorOf([], iso(2)), iso(2));
  assert.equal(sinceOf(iso(10)), new Date(Date.parse(iso(10)) - OVERLAP_MS).toISOString());
});

// the point of it all: an hour of polling on one open device, 300 rows on the table, one row changing now and then
await ok("an hour of polls moves a small fraction of the rows the old way did", async () => {
  const db = fake(many(300)); const st = newMediaState();
  await run(db, st, { now: T0 });
  let delta = db.sent;
  for (let i = 1; i <= 60; i += 1) {
    if (i % 10 === 0) { const r = db.rows[i]; r.updated_at = iso(300 + i); }       // six changes in the hour
    await run(db, st, { now: T0 + i * 60_000 });
  }
  delta = db.sent;
  const old = 61 * 300;                                                            // the old loop: 300 rows, 61 times
  console.log(`  rows over the wire in an hour: ${delta} (old way ${old}), ${(100 - (delta / old) * 100).toFixed(1)}% fewer`);
  assert.ok(delta < old * 0.1, `${delta} vs ${old}`);
});

console.log(`mediaDelta: ${n} groups pass`);
