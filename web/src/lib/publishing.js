/* The publishing switch, read exactly as the publisher reads it (backend/semasa/publisher.py publishing_on):
   on when `enabled` is true, or once `enabled_from` (an ISO moment with its zone) has passed; `paused` wins. */
export function publishingOn(pub = {}, now = Date.now()) {
  if (!pub || pub.paused === true) return false;
  if (pub.enabled === true) return true;
  const from = opensAt(pub);
  return from !== null && now >= from;
}

/* The moment the switch opens by itself, in ms, or null when there is none (or it carries no zone, which never opens). */
export function opensAt(pub = {}) {
  const s = pub && pub.enabled_from;
  if (!s || !/(Z|[+-]\d\d:?\d\d)$/.test(String(s))) return null;
  const ms = Date.parse(s);
  return Number.isNaN(ms) ? null : ms;
}
