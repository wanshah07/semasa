/* CRM (supabase/031_crm.sql): the page's arithmetic. Plain functions with no imports so web/crm.test.mjs runs them under
   Node. The database's semasa_crm_queue is the authority on WHO gets a campaign; `audienceOf` here is the same rule, so the
   composer can say "goes to 23 of 31" before the click and the two never disagree on the count. */

export const STAGES = ["lead", "prospect", "client", "dormant", "lost"];
export const STAGE_WORDS = {
  lead: ["Prospek baharu", "Lead"], prospect: ["Dalam perbincangan", "Prospect"], client: ["Pelanggan", "Client"],
  dormant: ["Senyap", "Dormant"], lost: ["Hilang", "Lost"],
};
export const ACTIVITY_KINDS = ["note", "call", "meeting", "email", "whatsapp"];
export const CAMPAIGN_STATUS = ["draft", "scheduled", "sending", "sent", "paused"];

/** Can this contact receive marketing e-mail at all: an address, consent, not unsubscribed. */
export function mailable(k) {
  return Boolean(k?.email && k.email.includes("@") && k.consent && !k.unsubscribed_at);
}

/** The contacts a campaign's audience names (stages / tags / lang; empty = everyone), split into those who get the mail
    and those skipped, with the reason. Mirrors semasa_crm_queue. */
export function audienceOf(campaign, contacts) {
  const a = campaign?.audience || {};
  const stages = Array.isArray(a.stages) ? a.stages : [];
  const tags = Array.isArray(a.tags) ? a.tags : [];
  const lang = a.lang || "";
  const named = (contacts || []).filter((k) =>
    (!stages.length || stages.includes(k.stage))
    && (!tags.length || tags.some((t) => (k.tags || []).includes(t)))
    && (!lang || k.lang === lang));
  const send = named.filter(mailable);
  const skipped = named.filter((k) => !mailable(k)).map((k) => ({ ...k, why: !k.email ? "no_email" : k.unsubscribed_at ? "unsubscribed" : "no_consent" }));
  return { named, send, skipped };
}

/** {{name}} and {{company}} filled for one contact (the same two fields the database fills). */
export function merge(text, k) {
  return String(text || "").replaceAll("{{name}}", k?.name || "").replaceAll("{{company}}", k?.company || "");
}

/** What stops a campaign being sent, as field names; empty means it can go. */
export function validateCampaign(c) {
  const bad = [];
  if (!String(c.name || "").trim()) bad.push("name");
  if (!String(c.subject || "").trim()) bad.push("subject");
  if (!String(c.body || "").trim()) bad.push("body");
  if (c.kind === "broadcast" && c.send_at && Number.isNaN(Date.parse(c.send_at))) bad.push("send_at");
  return bad;
}

/** What stops a contact being saved. */
export function validateContact(k) {
  const bad = [];
  if (!String(k.name || "").trim()) bad.push("name");
  if (k.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(k.email)) bad.push("email");
  if (!STAGES.includes(k.stage)) bad.push("stage");
  if (k.consent && !String(k.consent_source || "").trim()) bad.push("consent_source");   // PDPA: a consent without a source is a guess
  return bad;
}

/** Tags typed as "a, b; c" → ["a","b","c"], lower-cased, unique. */
export function parseTags(text) {
  return [...new Set(String(text || "").split(/[,;\n]/).map((s) => s.trim().toLowerCase()).filter(Boolean))];
}

/** The pipeline counts and the consent picture for the tiles. */
export function crmSummary(contacts, outbox, today) {
  const by = Object.fromEntries(STAGES.map((s) => [s, 0]));
  let consenting = 0, unsub = 0;
  for (const k of contacts || []) {
    by[k.stage] = (by[k.stage] || 0) + 1;
    if (mailable(k)) consenting++;
    if (k.unsubscribed_at) unsub++;
  }
  const due = (contacts || []).filter((k) => k.next_action_at && k.next_action_at <= today && !["client", "lost"].includes(k.stage) ? true : k.next_action_at && k.next_action_at <= today).length;
  const sent30 = (outbox || []).filter((o) => o.status === "sent" && !o.is_test && o.sent_at && o.sent_at.slice(0, 10) >= addDays(today, -30)).length;
  const failed = (outbox || []).filter((o) => o.status === "error").length;
  return { total: (contacts || []).length, byStage: by, consenting, unsubscribed: unsub, actionsDue: due, sent30, failed };
}

export function addDays(iso, n) {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

/** A blank contact / campaign for the forms. */
export const blankContact = () => ({ name: "", company: "", email: "", phone: "", stage: "lead", source: "", tags: [], lang: "bm", consent: false,
  consent_source: "", notes: "", next_action: "", next_action_at: "" });
export const blankCampaign = () => ({ name: "", kind: "broadcast", subject: "", body: "", lang: "bm", audience: { stages: [], tags: [], lang: "" }, send_at: "" });

/** The picker's "YYYY-MM-DDTHH:MM" is Malaysia time whatever the browser's zone; a value carrying its own zone is kept. */
export function sendAtIso(v) {
  if (!v) return null;
  const s = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(v) ? `${v}:00+08:00` : v;
  const ms = Date.parse(s);
  return Number.isNaN(ms) ? null : new Date(ms).toISOString();
}

/** The row as the database takes it. */
export function contactRow(k) {
  return {
    name: String(k.name || "").trim(), company: String(k.company || "").trim(), email: String(k.email || "").trim().toLowerCase(),
    phone: String(k.phone || "").trim(), stage: STAGES.includes(k.stage) ? k.stage : "lead", source: String(k.source || "").trim(),
    tags: Array.isArray(k.tags) ? k.tags : parseTags(k.tags), lang: k.lang === "en" ? "en" : "bm", consent: Boolean(k.consent),
    consent_source: String(k.consent_source || "").trim(), notes: String(k.notes || "").trim(),
    next_action: String(k.next_action || "").trim(), next_action_at: k.next_action_at || null,
  };
}
export function campaignRow(c) {
  return {
    name: String(c.name || "").trim(), kind: c.kind === "welcome" ? "welcome" : "broadcast", subject: String(c.subject || "").trim(),
    body: String(c.body || ""), lang: c.lang === "en" ? "en" : "bm",
    audience: { stages: (c.audience?.stages || []).filter((s) => STAGES.includes(s)), tags: c.audience?.tags || [], lang: c.audience?.lang || "" },
    send_at: c.kind === "welcome" ? null : sendAtIso(c.send_at),
  };
}
