import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { BUCKETS, TABLES, TABLES_UPLOADERS, errText, supabase } from "./SupabaseClient";
import { coalesce, liveName } from "./liveChannel";
import { dropRow, loadMedia, newMediaState, sortedRows } from "./mediaDelta";
import { dropRow as dropListRow, loadDelta, newDeltaState, sortedRows as sortedList } from "./tableDelta";
import { tr } from "./i18n";

/** Auth session, kept live. */
export function useSession() {
  const [session, setSession] = useState(null);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    if (!supabase) { setReady(true); return undefined; }
    supabase.auth.getSession().then(({ data }) => { setSession(data.session); setReady(true); });
    const { data: sub } = supabase.auth.onAuthStateChange((_e, s) => setSession(s));
    return () => sub.subscription.unsubscribe();
  }, []);
  return { session, user: session?.user ?? null, ready };
}

/** Is the signed-in user on public.semasa_uploaders? null while unknown. */
export function useCanUpload(user) {
  const [can, setCan] = useState(null);
  useEffect(() => {
    if (!supabase || !user) { setCan(null); return; }
    let live = true;
    supabase.from(TABLES_UPLOADERS).select("user_id").eq("user_id", user.id).maybeSingle()
      .then(({ data, error }) => { if (live) setCan(!error && Boolean(data)); });
    return () => { live = false; };
  }, [user]);
  return can;
}

/** A headline nobody turns into an idea leaves the page this many hours after it arrived, and the
    scraper deletes it once it can never come back (backend SCRAPE_PICK_HOURS; keep the two equal). */
export const PICK_HOURS = 48;

/** Latest headlines (the last PICK_HOURS only) plus the last scrape run, refreshed every `everyMs`. */
export function useTrends({ limit = 240, everyMs = 600_000 } = {}) {
  const [rows, setRows] = useState([]);
  const [lastRun, setLastRun] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    if (!supabase) { setLoading(false); return; }
    try {
      const [t, r] = await Promise.all([
        supabase.from(TABLES.trends).select("id,title,source,url,summary,category,lang,summary_source,published_at,created_at,tags")
          .gte("created_at", new Date(Date.now() - PICK_HOURS * 3600_000).toISOString())
          .order("created_at", { ascending: false }).limit(limit),
        // last FINISHED run: an in-progress run (or one that crashed before closing) has
        // seen/inserted 0 and would make the hero read "0 baharu" for minutes at a time
        supabase.from(TABLES.runs).select("started_at,finished_at,seen,inserted,llm_ok,llm_model,sources,note")
          .not("finished_at", "is", null)
          .order("started_at", { ascending: false }).limit(1),
      ]);
      if (t.error) setError(errText(t.error)); else { setRows(t.data ?? []); setError(""); }
      if (!r.error && r.data?.length) setLastRun(r.data[0]);
    } catch (e) {
      setError(e?.message || String(e));   // network down: say so, never a skeleton for ever
    } finally {
      setLoading(false);
    }
  }, [limit]);

  useEffect(() => {
    load();
    // Shared project: its free-plan egress is shared with the other app, so poll
    // only while the tab is visible, and catch up the moment it comes back.
    const tick = () => { if (!document.hidden) load(); };
    const id = setInterval(tick, everyMs);
    document.addEventListener("visibilitychange", tick);
    return () => { clearInterval(id); document.removeEventListener("visibilitychange", tick); };
  }, [load, everyMs]);

  return { rows, lastRun, error, loading, reload: load };
}

/** media_generations, live: realtime for status flips, a poll as the safety net. */
/* `need`: ids a post points at. The newest `limit` rows are loaded, and any needed row older than that is fetched by
   id, so an older post keeps its pictures (without it, once 300 newer jobs existed, an older post showed no picture,
   read "instagram needs an image" and could not be approved).
   One full read, then only the rows changed since (lib/mediaDelta.js): re-reading 300 rows every minute on every open
   device is what used up the project's egress (Wan, 16 Nov 2026). A full read again every 15 minutes, on `reload`, and
   whenever a delta read would be incomplete. */
export function useGenerations({ limit = 300, enabled = true, need = "" } = {}) {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");
  const loadRef = useRef(null);
  const stateRef = useRef(newMediaState());

  // a different limit, or signing out and in, starts from a full read
  useEffect(() => { stateRef.current = newMediaState(); }, [limit, enabled]);

  const load = useCallback(async (force = false) => {
    if (!supabase || !enabled) return;
    const out = await loadMedia({ client: supabase, table: TABLES.media, state: stateRef.current, limit, need, force: force === true });
    if (out.error) { setError(errText(out.error)); return; }
    if (out.rows) setRows(out.rows);
    setError("");
  }, [limit, enabled, need]);
  loadRef.current = load;

  useEffect(() => {
    if (!supabase || !enabled) return undefined;
    // one read for a burst of row changes, and never two in flight (see coalesce)
    const kick = coalesce(() => loadRef.current?.());
    kick.now();
    const channel = supabase.channel(liveName("media_generations_live"))
      .on("postgres_changes", { event: "*", schema: "public", table: TABLES.media }, (payload) => {
        // a delta read cannot see a deleted row, so the event that names it removes it at once
        if (payload?.eventType === "DELETE" && payload.old?.id && dropRow(stateRef.current, payload.old.id)) {
          setRows(sortedRows(stateRef.current));
        }
        kick();
      })
      .subscribe();
    const id = setInterval(() => { if (!document.hidden) kick.now(); }, 60_000);
    const onShow = () => { if (!document.hidden) kick.now(); };
    document.addEventListener("visibilitychange", onShow);
    return () => { kick.cancel(); supabase.removeChannel(channel); clearInterval(id); document.removeEventListener("visibilitychange", onShow); };
  }, [load, enabled]);

  // A Retry is a fresh start: the attempt count restarts and the provider is the one picked on the card ("" = the
  // runner's default). RLS lets only the job's owner do it, and a refused update returns no row rather than an error.
  const requeue = useCallback(async (id, provider) => {
    const patch = { status: "pending", error: null, attempts: 0 };
    if (provider !== undefined) patch.provider = provider || null;
    const { data, error: e } = await supabase.from(TABLES.media).update(patch).eq("id", id).select("id");
    if (e) throw new Error(errText(e));
    if (!data?.length) throw new Error(tr("Kerja ini tidak dapat dimasukkan semula: hanya orang yang memulakannya boleh cuba semula.",
      "This job could not be put back in the queue: only the person who started it can retry it."));
  }, []);

  const remove = useCallback(async (row) => {
    const { error: e } = await supabase.from(TABLES.media).delete().eq("id", row.id);
    if (e) throw new Error(errText(e));
    if (dropRow(stateRef.current, row.id)) setRows(sortedRows(stateRef.current));
    if (row.reference_path) await supabase.storage.from(BUCKETS.reference).remove([row.reference_path]);
  }, []);

  return { rows, error, reload: () => load(true), requeue, remove };
}

export const TOAST_MS = { ok: 2600, info: 3500, warn: 6000, danger: 7000, error: 7000 };

/** Tiny toast queue. */
export function useToasts() {
  const [toasts, setToasts] = useState([]);
  const push = useCallback((text, tone = "info") => {
    const id = Math.random().toString(36).slice(2);
    setToasts((t) => [...t, { id, text, tone }]);
    // a plain "saved" does not need five seconds over the page; a failure is read, so it stays longer
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), TOAST_MS[tone] || TOAST_MS.info);
  }, []);
  return { toasts, push };
}

/** A private table, kept live for a listed uploader: realtime where the table is in the
 *  publication, a poll as the net (only while the tab is visible). `enabled` false = no reads.
 *  `delta`: for a wide list on a table with `updated_at` (posts, ideas, FAQ, motions). The list is read in full once; after
 *  that a poll or a realtime event reads only the rows that changed, and `reload` (and every five minutes) checks the list
 *  of ids so a deleted row leaves (lib/tableDelta.js). Without it every poll downloads the whole list again. */
export function useTable(table, { enabled = true, select = "*", order = "created_at", ascending = false, limit = 200,
  realtime = true, everyMs = 90_000, eq = null, neq = null, delta = false } = {}) {
  // eq / neq: one [column, value] pair each, so two pages can share a table without reading each other's rows
  const [eqCol, eqVal] = eq || [];
  const [neqCol, neqVal] = neq || [];
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const loadRef = useRef(null);
  const sigRef = useRef("");
  const stateRef = useRef(newDeltaState());
  const listRef = useRef("");

  const load = useCallback(async (kind) => {
    if (!supabase || !enabled) { setLoading(false); return; }
    if (delta) {
      // a different list (another filter, order or limit) starts from a full read
      const list = [table, select, order, ascending, limit, eqCol, eqVal, neqCol, neqVal].join("|");
      if (listRef.current !== list) { listRef.current = list; stateRef.current = newDeltaState(); }
      const out = await loadDelta({ client: supabase, table, state: stateRef.current, select, order, ascending, limit,
        eq: eqCol ? [eqCol, eqVal] : null, neq: neqCol ? [neqCol, neqVal] : null, kind: typeof kind === "string" ? kind : "auto" });
      if (out.error) setError(errText(out.error));
      else { if (out.rows) setRows(out.rows); setError(""); }   // rows is null when nothing changed: no re-render
      setLoading(false);
      return;
    }
    let q = supabase.from(table).select(select);
    if (eqCol) q = q.eq(eqCol, eqVal);
    if (neqCol) q = q.neq(neqCol, neqVal);
    const { data, error: e } = await q.order(order, { ascending }).limit(limit);
    if (e) setError(errText(e));
    else {
      // an unchanged answer keeps the same array, so a poll does not re-render (and reset) every open form
      const sig = JSON.stringify(data ?? []);
      if (sig !== sigRef.current) { sigRef.current = sig; setRows(data ?? []); }
      setError("");
    }
    setLoading(false);
  }, [table, enabled, select, order, ascending, limit, eqCol, eqVal, neqCol, neqVal, delta]);
  loadRef.current = load;

  useEffect(() => {
    if (!supabase || !enabled) return undefined;
    if (delta) {
      if (stateRef.current.cursor) stateRef.current.settledAt = 0;   // back on show after a pause: check the ids first
      else setLoading(true);                                          // first time on show: say so, not "nothing here"
    }
    const kick = coalesce(() => loadRef.current?.());       // one read for a burst of changes, never two in flight
    kick.now();
    let channel = null;
    if (realtime) {
      channel = supabase.channel(liveName(`${table}_live`))
        .on("postgres_changes", { event: "*", schema: "public", table }, (payload) => {
          // a delta read cannot see a deleted row, so the event that names it removes it at once
          if (delta && payload?.eventType === "DELETE" && payload.old?.id && dropListRow(stateRef.current, payload.old.id)) {
            setRows(sortedList(stateRef.current, order, ascending));
          }
          kick();
        })
        .subscribe();
    }
    const tick = () => { if (!document.hidden) kick.now(); };
    const id = setInterval(tick, everyMs);
    document.addEventListener("visibilitychange", tick);
    return () => {
      kick.cancel();
      if (channel) supabase.removeChannel(channel);
      clearInterval(id); document.removeEventListener("visibilitychange", tick);
    };
  }, [load, enabled, realtime, table, everyMs, delta, order, ascending]);

  // after the page's own write: the changed rows, and the rows it deleted
  const reload = useCallback(() => load(delta ? "settle" : undefined), [load, delta]);

  return { rows, error, loading, reload };
}

/** semasa_settings as { key: value }. */
export function useSettings(enabled) {
  const t = useTable(TABLES.settings, { enabled, select: "key,value,updated_at", order: "key", ascending: true, realtime: false });
  const map = useMemo(() => Object.fromEntries(t.rows.map((r) => [r.key, r.value])), [t.rows]);
  const save = useCallback(async (key, value) => {
    const { data, error: e } = await supabase.from(TABLES.settings).update({ value }).eq("key", key).select("key");
    if (e) throw new Error(errText(e));
    // an update that matched nothing is not a save: the row is missing (its SQL file has not run)
    if (!data?.length) throw new Error(`setting "${key}" not found (0 rows): run its supabase/*.sql file`);
    await t.reload();
  }, [t]);
  return { settings: map, loading: t.loading, error: t.error, save, reload: t.reload };
}
