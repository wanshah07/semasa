/* A realtime channel name that is never shared. supabase-js hands back the EXISTING channel when a name is reused, and calling
   .on("postgres_changes") on a channel that is already subscribed throws. Two components reading the same table (the API page
   loads the AI providers in ApiTab AND in AiProviders) both asked for "<table>_live", the second one threw during render, and
   with no error boundary the whole page went blank, on every segment after it and on every reopen of an app that remembers its
   last tab (Wan, 8 Nov 2026: "cannot open API segment ... any segment cannot open", phone app blank). One name per subscription,
   so a table may be watched by as many components as need it. No imports, so web/liveChannel.test.mjs runs this under Node. */
let seq = 0;
export const liveName = (base) => `${base}_${++seq}`;
