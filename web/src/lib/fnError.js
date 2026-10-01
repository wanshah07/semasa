/** The answer a failed Edge Function call carries: our functions always answer {error}; a missing function is a plain 404.
    On its own so lib/chat.js, lib/faqAi.js and lib/designClone.js can all read it without importing one another in a circle. */
export async function explain(error) {
  const res = error?.context;
  if (res && typeof res.status === "number") {
    if (res.status === 404) return { missing: true };
    try { const j = await res.clone().json(); if (j?.error) return { message: String(j.error) }; } catch { /* not JSON */ }
    return { message: `HTTP ${res.status}` };
  }
  return { message: String(error?.message || error) };
}
