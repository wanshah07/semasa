// The webhook has one total model budget; a slow gateway must leave time for its backup.
export const FAST_TOTAL_MS = 15000;
export const FAST_ATTEMPT_MS = 7000;

export async function tryFastGates(tries, { deadline, now = Date.now, fetchImpl = fetch,
  messagesFor, requestFor, answerText, errorText, switchable }) {
  let attempts = 0;
  for (const t of tries) {
    const left = deadline - now();
    if (left < 1000) return null;
    const rq = requestFor(t, messagesFor(t));
    attempts++;
    try {
      const response = await fetchImpl(rq.url, { method: 'POST', headers: rq.headers, body: rq.body,
        signal: AbortSignal.timeout(Math.floor(Math.min(FAST_ATTEMPT_MS, left))) });
      const json = await response.json().catch(() => null);
      if (now() >= deadline) return null;
      if (!response.ok) {
        if (switchable(response.status, errorText(json))) continue;
        return null;
      }
      const answer = String(answerText(t.gate, json) || '').trim();
      if (answer) return { answer, who: `${t.name} · ${json?.model || t.model}`, attempts };
    } catch {
      continue;
    }
  }
  return null;
}
