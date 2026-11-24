/* More than one ChatGPT account for pictures (Wan, 24 Nov 2026: "add chatgpt segment that I can add multiple accounts to support
   image gen using chatgpt"). supabase/095 keeps the extra accounts; the worker asks the main login first and then each of these,
   and an account that says its allowance is used up rests for three hours while the next one draws. This file turns what
   semasa_chatgpt_accounts_status() returns into what the card shows. Pure helpers, tested in chatgptAccounts.test.mjs. */

export const MAX_ACCOUNTS = 8;

/** One account's state: off | resting | error | ok | ready | idle.
    off: switched off. resting: it said its allowance is used up and is not asked again before `limit_until`.
    error: its last error is newer than its last picture. ok: it has drawn a picture. ready: its login was accepted (a refresh
    worked) and it has not been needed yet. idle: saved, not yet checked. */
export function accountState(row, now = Date.now()) {
  const r = row || {};
  if (r.enabled === false) return "off";
  const until = Date.parse(r.limit_until || "");
  if (Number.isFinite(until) && until > now) return "resting";
  const ok = Date.parse(r.last_ok_at || "") || 0;
  const bad = Date.parse(r.last_error_at || "") || 0;
  // the error that started a rest is "limit reached": once the rest is over it is history, not a fault to show
  const wasLimit = Number.isFinite(until) && bad > 0 && bad <= until;
  if (bad > ok && bad > (Date.parse(r.checked_at || "") || 0) && !wasLimit) return "error";
  if (ok) return "ok";
  return r.checked_at ? "ready" : "idle";
}

export const ACCOUNT_WORDS = {
  off: ["Dimatikan", "Switched off"],
  resting: ["Berehat (had dicapai)", "Resting (limit reached)"],
  error: ["Ralat", "Error"],
  ok: ["Melukis", "Drawing"],
  ready: ["Sedia", "Ready"],
  idle: ["Belum disemak", "Not checked yet"],
};

export const ACCOUNT_CLS = {
  off: "bg-surface-2 text-muted",
  resting: "bg-warn/15 text-warn",
  error: "bg-danger/15 text-danger",
  ok: "bg-ok/15 text-ok",
  ready: "bg-ok/15 text-ok",
  idle: "bg-surface-2 text-muted",
};

/** Minutes until a resting account is asked again, rounded up; 0 when it is not resting. */
export function restMinutes(row, now = Date.now()) {
  const until = Date.parse((row || {}).limit_until || "");
  return Number.isFinite(until) && until > now ? Math.ceil((until - now) / 60000) : 0;
}

/** "2j 5m" / "2h 5m" for a number of minutes. */
export function restText(minutes, en) {
  const m = Math.max(0, Math.floor(minutes || 0));
  const h = Math.floor(m / 60);
  const hour = en ? "h" : "j";
  return h ? `${h}${hour} ${m % 60}m` : `${m}m`;
}

/** The accounts in the order the worker asks them (by number: acc1, acc2, ... acc10), whatever order the rows arrive in. */
export function ordered(rows) {
  const n = (r) => Number(String((r || {}).id || "").replace(/^acc/, "")) || 0;
  return (Array.isArray(rows) ? rows : []).filter((r) => r && r.id).slice().sort((a, b) => n(a) - n(b));
}

/** How many of the accounts could draw right now (on, and not resting). */
export const usable = (rows, now = Date.now()) => ordered(rows).filter((r) => !["off", "resting"].includes(accountState(r, now))).length;

/** Whether one more may be added. */
export const canAdd = (rows) => ordered(rows).length < MAX_ACCOUNTS;
