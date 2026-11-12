/* A realtime channel name that is never shared. supabase-js hands back the EXISTING channel when a name is reused, and calling
   .on("postgres_changes") on a channel that is already subscribed throws. Two components reading the same table (the API page
   loads the AI providers in ApiTab AND in AiProviders) both asked for "<table>_live", the second one threw during render, and
   with no error boundary the whole page went blank, on every segment after it and on every reopen of an app that remembers its
   last tab (Wan, 8 Nov 2026: "cannot open API segment ... any segment cannot open", phone app blank). One name per subscription,
   so a table may be watched by as many components as need it. No imports, so web/liveChannel.test.mjs runs this under Node. */
let seq = 0;
export const liveName = (base) => `${base}_${++seq}`;

/* A burst of realtime events, or a poll landing on top of one, must be ONE read of the table, not one read each (Wan, 12 Nov
   2026: "canceling statement due to statement timeout" at 17:33 UTC: a media run changes many rows in a few seconds, and every
   change reloaded up to 300 wide rows at once on a small database whose CPU was already throttled).
   kick()      trailing debounce: the read happens `wait` ms after the LAST event;
   kick.now()  run now (first load, a poll), but never while a read is already in flight: that asks for one more read after it;
   kick.cancel() drops a read not yet started (unmount). At most one read is in flight, and at most one is waiting behind it. */
export function coalesce(fn, wait = 1500) {
  let timer = null;
  let running = false;
  let dirty = false;
  const run = async () => {
    clearTimeout(timer);
    timer = null;
    if (running) { dirty = true; return; }
    running = true;
    try { await fn(); } catch { /* the loader reports its own errors */ } finally {
      running = false;
      if (dirty) { dirty = false; timer = setTimeout(run, wait); }
    }
  };
  const kick = () => { clearTimeout(timer); timer = setTimeout(run, wait); };
  kick.now = run;
  kick.cancel = () => { clearTimeout(timer); timer = null; dirty = false; };
  return kick;
}
