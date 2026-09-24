import { useCallback, useEffect, useRef, useState } from "react";
import { BUCKETS, TABLES, TABLES_UPLOADERS, errText, supabase } from "./SupabaseClient";

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

/** Latest headlines plus the last scrape run, refreshed every `everyMs`. */
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
export function useGenerations({ limit = 60 } = {}) {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");
  const loadRef = useRef(null);

  const load = useCallback(async () => {
    if (!supabase) return;
    const { data, error: e } = await supabase.from(TABLES.media).select("*")
      .order("created_at", { ascending: false }).limit(limit);
    if (e) setError(errText(e)); else { setRows(data ?? []); setError(""); }
  }, [limit]);
  loadRef.current = load;

  useEffect(() => {
    if (!supabase) return undefined;
    load();
    const channel = supabase.channel("media_generations_live")
      .on("postgres_changes", { event: "*", schema: "public", table: TABLES.media }, () => loadRef.current?.())
      .subscribe();
    const id = setInterval(() => loadRef.current?.(), 60_000);
    return () => { supabase.removeChannel(channel); clearInterval(id); };
  }, [load]);

  const requeue = useCallback(async (id) => {
    const { error: e } = await supabase.from(TABLES.media).update({ status: "pending", error: null }).eq("id", id);
    if (e) throw new Error(errText(e));
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
