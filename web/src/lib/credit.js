/* API credit as the page sees it (pages/CreditTab.jsx): the reading semasa_api_status.balance.credit that
   backend/semasa/api_credit.py writes every 15 minutes for Mireld, rootsys and KiosAPI, and the figure Wan may type from a
   gateway's own dashboard (settings.api_credit_manual). Pure functions, tested in credit.test.mjs; no i18n or Supabase import, so
   node can test them (text goes through the `t` the component hands in). The status rules here are the same as
   api_credit.status_of: change one, change both. */

export const CARDS = [
  { slug: "mireld", name: "Mireld", host: "api.mireld.my", unit: "credits" },
  { slug: "rootsys", name: "rootsys (Afiq)", host: "rootsys.cloud", unit: "credits" },
  { slug: "kiosapi", name: "KiosAPI", host: "kiosapi.com", unit: "Rp" },
];
// the gateways whose balance sits on the ACCOUNT and needs the panel's access token + user id (supabase/096): KiosAPI's New-API panel
export const ACCOUNT_KEY_SLUGS = ["kiosapi"];

/** Why the typed account key cannot be saved, as [BM, EN], or null when it can. The database checks the same things. */
export function accountKeyProblem(token, userId) {
  const tk = String(token || "").trim(), id = String(userId || "").trim();
  if (!tk || !id) return ["Isi kedua-dua token akses dan ID pengguna.", "Fill in both the access token and the user ID."];
  if (/\s/.test(tk) || tk.length < 16 || tk.length > 400) return ["Itu tidak kelihatan seperti token akses (satu rentetan panjang, tiada ruang).", "That does not look like an access token (one long string, no spaces)."];
  if (!/^[0-9]{1,12}$/.test(id)) return ["ID pengguna ialah NOMBOR yang ditunjukkan panel untuk akaun anda.", "The user ID is the NUMBER the panel shows for your account."];
  return null;
}

export const LOW_PERCENT = 15;          // under this much left is "low" ...
export const LOW_DAYS = 7;              // ... and so is under this long to run
export const LATE_MS = 45 * 60_000;     // a reading older than this means the 15-minute run has missed its turns
const MYT_MS = 8 * 3600_000;

export const numOf = (v) => (v === null || v === undefined || v === "" || typeof v === "boolean" ? null : Number.isFinite(Number(v)) ? Number(v) : null);
const when = (iso) => { const t = Date.parse(iso || ""); return Number.isFinite(t) ? t : null; };

/** ok | low | expired | unknown, from the stored figures and the clock (a reading ages into `expired` by itself). */
export function statusOf(c, now = Date.now()) {
  if (!c) return "unknown";
  const exp = when(c.expires_at);
  if (exp !== null && exp <= now) return "expired";
  const rem = numOf(c.remaining), pct = numOf(c.percent_left);
  if (rem === null && exp === null && !c.unlimited) return "unknown";
  if (rem !== null && (rem <= 0 || (pct !== null && pct < LOW_PERCENT))) return "low";
  if (exp !== null && exp - now < LOW_DAYS * 86400_000) return "low";
  return "ok";
}

/** Time to a date: { past, days, hours, minutes } counted from `now` (past: how long ago). null when there is no date. */
export function countdownOf(iso, now = Date.now()) {
  const t = when(iso);
  if (t === null) return null;
  const ms = Math.abs(t - now);
  const mins = Math.floor(ms / 60_000);
  return { past: t <= now, days: Math.floor(mins / 1440), hours: Math.floor((mins % 1440) / 60), minutes: mins % 60 };
}

/** "16d 0h remaining" · "5h 12m remaining" · "expired 2d 3h ago" (BM: "16 hari 0 jam lagi"), through `t`. */
export function countdownText(cd, t) {
  if (!cd) return "";
  const { days: d, hours: h, minutes: m } = cd;
  const span = d > 0 ? t(`${d} hari ${h} jam`, `${d}d ${h}h`) : h > 0 ? t(`${h} jam ${m} min`, `${h}h ${m}m`) : t(`${m} min`, `${m}m`);
  return cd.past ? t(`tamat ${span} lalu`, `expired ${span} ago`) : t(`${span} lagi`, `${span} remaining`);
}

/** An instant in Malaysia time, "09 Dec 2026, 23:31 MYT" (the form Wan's dashboards use), never the viewer's own zone. */
export function mytText(iso, lang = "en") {
  const t = when(iso);
  if (t === null) return "";
  const d = new Date(t + MYT_MS), pad = (n) => String(n).padStart(2, "0");
  const mon = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const monBm = ["Jan", "Feb", "Mac", "Apr", "Mei", "Jun", "Jul", "Ogo", "Sep", "Okt", "Nov", "Dis"];
  return `${pad(d.getUTCDate())} ${(lang === "en" ? mon : monBm)[d.getUTCMonth()]} ${d.getUTCFullYear()}, ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())} MYT`;
}

/** A figure in a short form: 89,113,109 → "89.11M", 1,275,000,000 → "1.28B", 8817 → "8,817", 12.5 → "12.5". */
export function compact(n) {
  const v = numOf(n);
  if (v === null) return "";
  const a = Math.abs(v);
  if (a >= 1e9) return `${(v / 1e9).toFixed(2).replace(/\.?0+$/, "")}B`;
  if (a >= 1e6) return `${(v / 1e6).toFixed(2).replace(/\.?0+$/, "")}M`;
  if (a >= 1e4) return Math.round(v).toLocaleString("en-US");
  return String(Math.round(v * 1000) / 1000);
}

/** What a reading shows for one amount: the dashboard's own form when the gateway's factor is known (Mireld: 89.11 → "89.11M"),
    else the raw figure. `raw` is always the API's number, so the two can be told apart. */
export function amountOf(value, credit) {
  const v = numOf(value);
  if (v === null) return { text: "", raw: "" };
  const scale = numOf(credit?.display_scale);
  const unit = credit?.unit && credit.unit !== "credit" ? credit.unit : "";
  const text = scale && scale > 0 ? compact(v * scale) : compact(v);
  return { text: unit ? `${text} ${unit}` : text, raw: String(Math.round(v * 1e6) / 1e6), scaled: !!(scale && scale > 0) };
}

/** Wan's typed amount → a number. `unit` "Rp"/"IDR" reads a dot as a thousands mark ("Rp 8.817" is 8,817) and a comma as the
    decimal point; every other unit reads a comma as thousands. K, M and B suffixes: "545.1M" → 545,100,000. null when it is not a number. */
export function parseAmount(text, unit = "") {
  let s = String(text ?? "").trim().replace(/\s+/g, "").replace(/^(?:rp|idr|usd|us\$|\$|rm|myr)/i, "");
  const m = /([kmb])$/i.exec(s);
  const mult = m ? { k: 1e3, m: 1e6, b: 1e9 }[m[1].toLowerCase()] : 1;
  if (m) s = s.slice(0, -1);
  if (!s || /[^0-9.,\-]/.test(s)) return null;
  const idr = /^(rp|idr)$/i.test(String(unit).trim());
  s = idr ? s.replace(/\./g, "").replace(",", ".") : s.replace(/,/g, "");
  const n = Number(s);
  return Number.isFinite(n) ? n * mult : null;
}

/** A date and time typed as Malaysia time ("2026-12-09T23:31") → ISO UTC; "" or garbage → null. */
export function mytInputToIso(text) {
  const m = /^(\d{4})-(\d\d)-(\d\d)(?:[T ](\d\d):(\d\d))?$/.exec(String(text || "").trim());
  if (!m) return null;
  const ms = Date.UTC(+m[1], +m[2] - 1, +m[3], +(m[4] || 0), +(m[5] || 0)) - MYT_MS;
  return Number.isFinite(ms) ? new Date(ms).toISOString().replace(/\.\d+Z$/, "Z") : null;
}
/** The reverse, for the form: ISO UTC → "2026-12-09T23:31" in Malaysia time. */
export const isoToMytInput = (iso) => { const t = when(iso); return t === null ? "" : new Date(t + MYT_MS).toISOString().slice(0, 16); };

/** The manual entry that goes into settings.api_credit_manual[slug]; null when nothing usable was typed. */
export function manualEntry({ remaining, total, unit, expires, note }, now = Date.now()) {
  const rem = parseAmount(remaining, unit), tot = parseAmount(total, unit), exp = mytInputToIso(expires);
  if (rem === null && exp === null) return null;
  return { remaining: rem, total: tot, unit: String(unit || "").trim().slice(0, 12), expires_at: exp,
    note: String(note || "").trim().slice(0, 160), entered_at: new Date(now).toISOString().replace(/\.\d+Z$/, "Z") };
}

/** One card's picture of a gateway: the live reading, else Wan's typed figure (labelled manual), the status, the freshness.
    row = a semasa_api_status row, manual = settings.api_credit_manual[slug]. A typed figure is never mixed into a live one. */
export function viewOf(row, manual, now = Date.now()) {
  const bal = row?.balance && typeof row.balance === "object" ? row.balance : {};
  const live = bal.credit && typeof bal.credit === "object" ? bal.credit : null;
  const hasLive = !!live && (numOf(live.remaining) !== null);
  const man = manual && typeof manual === "object" ? manual : null;
  const useManual = !hasLive && !!man && numOf(man.remaining) !== null;
  const fig = hasLive ? live : useManual ? { ...man, percent_left: pct(man.remaining, man.total) } : null;
  // a date: the live one, else the typed one (labelled), never both
  const expLive = live?.expires_at || null;
  const expManual = !expLive && man?.expires_at ? man.expires_at : null;
  const merged = { remaining: fig?.remaining ?? null, percent_left: fig?.percent_left ?? null, unlimited: !!live?.unlimited,
    expires_at: expLive || expManual };
  const readAt = live?.checked_at || bal.checked_at || null;
  // the latest ATTEMPT, which moves even when the gateway was unreachable and the last good figure was kept: a Refresh is
  // finished when this moves (Codex review of #332), while the freshness of the figure itself is `readAt`
  const attemptAt = [bal.checked_at, live?.checked_at].filter((x) => when(x) !== null).sort((a, b) => when(b) - when(a))[0] || null;
  const age = when(readAt) === null ? null : now - when(readAt);
  return {
    slug: row?.slug || "", hasRow: !!row, keySet: row ? row.key_set !== false : true,
    source: hasLive ? "live" : useManual ? "manual" : "none",
    figure: fig, expiresAt: merged.expires_at, expiryManual: !!expManual,
    status: statusOf(merged, now),
    readAt, attemptAt, ageMs: age, late: age !== null && age > LATE_MS, stale: !!live?.stale,
    endpoint: live?.source || null, tried: Array.isArray(bal.tried) ? bal.tried : [],
    manual: man, manualAt: man?.entered_at || null,
    raw: hasLive ? live : null,
  };
}

export function pct(remaining, total) {
  const r = numOf(remaining), t = numOf(total);
  return r === null || t === null || t <= 0 ? null : Math.round(Math.max(0, Math.min(100, (100 * r) / t)) * 10) / 10;
}
