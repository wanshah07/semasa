/* Businesses (supabase/066 semasa_businesses; Wan, 11 Oct 2026: "business separate to WS REGULAB and VALORITH, I able to add
   the business"). Pure, so web/businesses.test.mjs runs it under Node. A business is {id, name, billing, sort, active};
   `billing` has the shape settings.billing has always had, and the page reads it through billingSettings(). */
import { DEFAULT_BILLING } from "./billing.js";

export const DEFAULT_BUSINESS = "wsregulab";
/** Personal: the receipts and subscriptions that belong to no business (business_id null). */
export const PERSONAL = "personal";

/** Active businesses in their order; WS REGULAB first when the table is not there yet (before 066), so nothing breaks. */
export function businessList(rows) {
  const list = (rows || []).filter((b) => b && b.id && b.active !== false)
    .sort((a, b) => (a.sort ?? 0) - (b.sort ?? 0) || String(a.name).localeCompare(String(b.name)));
  return list.length ? list : [{ id: DEFAULT_BUSINESS, name: "WS REGULAB", billing: {}, sort: 1, active: true }];
}

/** A business's billing settings, else (for WS REGULAB before 066 is applied) the shared settings.billing. */
export function billingOf(business, fallback) {
  const own = business?.billing && typeof business.billing === "object" && Object.keys(business.billing).length ? business.billing : null;
  return own || (business?.id === DEFAULT_BUSINESS || !business ? fallback : null) || {};
}

/** A new business's id from its name: lower case, letters, digits and dashes, 2 to 31 long, not already taken. */
export function slugOf(name, taken = []) {
  const base = String(name || "").normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase()
    .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 28) || "syarikat";
  const ids = new Set(taken);
  let id = base.length < 2 ? `${base}-1` : base, n = 2;
  while (ids.has(id)) id = `${base}-${n++}`;
  return id;
}

/** The billing settings a new business starts with: its own name, no bank, prefixes made from its id, the terms and e-mail
    rules of `template` (WS REGULAB's) to edit, and auto-send off until Wan checks the letterhead. */
export function newBusinessBilling(name, id, template = {}) {
  const tag = String(id || "").replace(/[^a-z0-9]/g, "").slice(0, 3).toUpperCase() || "BIZ";
  return {
    company: { ...DEFAULT_BILLING.company, name: String(name || "").trim(), reg_no: "", tagline: "", footer: "", website: "", email: "", phone: "",
      address: "", sst_no: "", tin: "", signatory: "", logo_url: "" },
    bank: { name: "", account_name: "", account_no: "" },
    prefix: { quotation: `${tag}-QT`, invoice: `${tag}-INV`, receipt: `${tag}-RPT` },
    days: { ...DEFAULT_BILLING.days, ...(template.days || {}) },
    tax_rate: 0,
    terms: { ...DEFAULT_BILLING.terms, ...(template.terms || {}) },
    email: { ...DEFAULT_BILLING.email, ...(template.email || {}), auto_send: false },
  };
}

/** The prefixes of `prefix` that another business already uses: a number must belong to one business only. */
export function prefixClashes(businesses, id, prefix) {
  const mine = Object.values(prefix || {}).map((p) => String(p || "").trim().toUpperCase()).filter(Boolean);
  const others = new Map();
  for (const b of businesses || []) {
    if (b.id === id) continue;
    for (const p of Object.values(b.billing?.prefix || {})) if (p) others.set(String(p).trim().toUpperCase(), b.name);
  }
  return mine.filter((p) => others.has(p)).map((p) => ({ prefix: p, business: others.get(p) }));
}

/** The paper's top mark: the business's own logo_url, WS REGULAB's logo only on WS REGULAB's papers, else none (the name). */
export function logoFor(businessId, cfg, wsLogo) {
  const own = String(cfg?.company?.logo_url || "").trim();
  if (/^https:\/\//.test(own)) return own;
  return (businessId || DEFAULT_BUSINESS) === DEFAULT_BUSINESS ? wsLogo : "";
}

/** Rows that belong to `id`; "all" keeps every row; PERSONAL keeps the rows with no business. */
export function ofBusiness(rows, id) {
  if (!id || id === "all") return rows || [];
  if (id === PERSONAL) return (rows || []).filter((r) => !r.business_id);
  return (rows || []).filter((r) => (r.business_id || DEFAULT_BUSINESS) === id);
}
