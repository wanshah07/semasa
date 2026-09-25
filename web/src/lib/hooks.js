import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { BUCKETS, TABLES, TABLES_UPLOADERS, errText, supabase } from "./SupabaseClient";
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
export function useGenerations({ limit = 300, enabled = true } = {}) {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");
  const loadRef = useRef(null);

  const load = useCallback(async () => {
    if (!supabase || !enabled) return;
    const { data, error: e } = await supabase.from(TABLES.media).select("*")
      .order("created_at", { ascending: false }).limit(limit);
    if (e) setError(errText(e)); else { setRows(data ?? []); setError(""); }
  }, [limit, enabled]);
  loadRef.current = load;

  useEffect(() => {
    if (!supabase || !enabled) return undefined;
    load();
    const channel = supabase.channel("media_generations_live")
      .on("postgres_changes", { event: "*", schema: "public", table: TABLES.media }, () => loadRef.current?.())
      .subscribe();
    const id = setInterval(() => loadRef.current?.(), 60_000);
    return () => { supabase.removeChannel(channel); clearInterval(id); };
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
    if (row.reference_path) await supabase.storage.from(BUCKETS.reference).remove([row.reference_path]);
  }, []);

  return { rows, error, reload: load, requeue, remove };
}

/** Tiny toast queue. */
export function useToasts() {
  const [toasts, setToasts] = useState([]);
  const push = useCallback((text, tone = "info") => {
    const id = Math.random().toString(36).slice(2);
    setToasts((t) => [...t, { id, text, tone }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 5000);
  }, []);
  return { toasts, push };
}

/** A private table, kept live for a listed uploader: realtime where the table is in the
 *  publication, a poll as the net (only while the tab is visible). `enabled` false = no reads. */
export function useTable(table, { enabled = true, select = "*", order = "created_at", ascending = false, limit = 200,
  realtime = true, everyMs = 90_000 } = {}) {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const loadRef = useRef(null);
  const sigRef = useRef("");

  const load = useCallback(async () => {
    if (!supabase || !enabled) { setLoading(false); return; }
    const { data, error: e } = await supabase.from(table).select(select).order(order, { ascending }).limit(limit);
    if (e) setError(errText(e));
    else {
      // an unchanged answer keeps the same array, so a poll does not re-render (and reset) every open form
      const sig = JSON.stringify(data ?? []);
      if (sig !== sigRef.current) { sigRef.current = sig; setRows(data ?? []); }
      setError("");
    }
    setLoading(false);
  }, [table, enabled, select, order, ascending, limit]);
  loadRef.current = load;

  useEffect(() => {
    if (!supabase || !enabled) return undefined;
    load();
    let channel = null;
    if (realtime) {
      channel = supabase.channel(`${table}_live`)
        .on("postgres_changes", { event: "*", schema: "public", table }, () => loadRef.current?.())
        .subscribe();
    }
    const tick = () => { if (!document.hidden) loadRef.current?.(); };
    const id = setInterval(tick, everyMs);
    document.addEventListener("visibilitychange", tick);
    return () => {
      if (channel) supabase.removeChannel(channel);
      clearInterval(id); document.removeEventListener("visibilitychange", tick);
    };
  }, [load, enabled, realtime, table, everyMs]);

  return { rows, error, loading, reload: load };
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
