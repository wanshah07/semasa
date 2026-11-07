/* Businesses (lib/businesses.js, supabase/066). `npm test`. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { DEFAULT_BUSINESS, PERSONAL, billingOf, businessList, logoFor, newBusinessBilling, ofBusiness, prefixClashes, slugOf } from "./src/lib/businesses.js";

let n = 0;
const t = (name, fn) => { try { fn(); n++; } catch (e) { console.error("FAIL:", name); throw e; } };
const ws = { id: "wsregulab", name: "WS REGULAB", sort: 1, billing: { company: { name: "WS Regulab Solutions" }, prefix: { quotation: "QT", invoice: "INV", receipt: "RPT" } } };
const val = { id: "valorith", name: "VALORITH", sort: 2, billing: { company: { name: "Valorith" }, prefix: { quotation: "VAL-QT", invoice: "VAL-INV", receipt: "VAL-RPT" } } };

t("the list is the active businesses in order, and WS REGULAB alone before the table exists", () => {
  assert.deepEqual(businessList([val, ws, { id: "old", name: "Old", sort: 0, active: false }]).map((b) => b.id), ["wsregulab", "valorith"]);
  assert.deepEqual(businessList([]).map((b) => b.id), [DEFAULT_BUSINESS]);
});
t("a business's billing settings are its own; only WS REGULAB falls back to the old shared settings", () => {
  assert.equal(billingOf(val, { company: { name: "shared" } }).company.name, "Valorith");
  assert.equal(billingOf({ id: "wsregulab", billing: {} }, { company: { name: "shared" } }).company.name, "shared");
  assert.deepEqual(billingOf({ id: "new", billing: {} }, { company: { name: "shared" } }), {}, "a new business never borrows WS REGULAB's letterhead");
});
t("a new business gets a free id, its own name, its own prefixes and no bank", () => {
  assert.equal(slugOf("Valorith Fragrance Sdn. Bhd.", ["wsregulab"]), "valorith-fragrance-sdn-bhd");
  assert.equal(slugOf("Valorith", ["valorith"]), "valorith-2");
  assert.equal(slugOf("!!!", []), "syarikat");
  const b = newBusinessBilling("Hermes Lab", "hermes-lab", { terms: { invoice: "Pay in 30 days." }, email: { auto_send: true } });
  assert.equal(b.company.name, "Hermes Lab");
  assert.deepEqual(b.prefix, { quotation: "HER-QT", invoice: "HER-INV", receipt: "HER-RPT" });
  assert.equal(b.bank.account_no, "");
  assert.equal(b.terms.invoice, "Pay in 30 days.");
  assert.equal(b.email.auto_send, false, "nothing is e-mailed by itself until Wan has checked the new letterhead");
});
t("a prefix another business uses is named before it can be saved", () => {
  assert.deepEqual(prefixClashes([ws, val], "valorith", { quotation: "VAL-QT", invoice: "inv", receipt: "VAL-RPT" }), [{ prefix: "INV", business: "WS REGULAB" }]);
  assert.deepEqual(prefixClashes([ws, val], "valorith", val.billing.prefix), []);
});
t("only WS REGULAB's papers carry the ws.regulab logo", () => {
  assert.equal(logoFor("wsregulab", ws.billing, "WS.png"), "WS.png");
  assert.equal(logoFor(undefined, {}, "WS.png"), "WS.png");
  assert.equal(logoFor("valorith", val.billing, "WS.png"), "");
  assert.equal(logoFor("valorith", { company: { logo_url: "https://x/v.png" } }, "WS.png"), "https://x/v.png");
});
t("rows by business: all, one, or personal (no business)", () => {
  const rows = [{ id: 1, business_id: "wsregulab" }, { id: 2, business_id: "valorith" }, { id: 3 }, { id: 4, business_id: null }];
  assert.deepEqual(ofBusiness(rows, "all").map((r) => r.id), [1, 2, 3, 4]);
  assert.deepEqual(ofBusiness(rows, "valorith").map((r) => r.id), [2]);
  assert.deepEqual(ofBusiness(rows, "wsregulab").map((r) => r.id), [1, 3, 4], "a row from before 066 is WS REGULAB's, as the column default says");
  assert.deepEqual(ofBusiness(rows, PERSONAL).map((r) => r.id), [3, 4]);
});
t("the migration seeds WS REGULAB from the old settings and keeps its counters going", () => {
  const sql = readFileSync(new URL("../supabase/066_businesses.sql", import.meta.url), "utf8");
  assert.match(sql, /'wsregulab', 'WS REGULAB', coalesce\(\(select value from public\.semasa_settings where key = 'billing'\)/);
  assert.match(sql, /primary key \(business_id, prefix, year\)/);
  assert.match(sql, /business_id text not null default 'wsregulab'/);
  assert.match(sql, /semasa_receipts\s+add column if not exists business_id text references/, "receipts may belong to no business");
});

t("073: billing settings (bank details) are read by a Semasa uploader only, and the public link and issue still work", () => {
  const sql = readFileSync(new URL("../supabase/073_billing_settings_guard.sql", import.meta.url), "utf8");
  const fn = sql.slice(sql.indexOf("create or replace function public.semasa_billing_settings_for"));
  assert.match(fn, /semasa_billing_settings_for\(p_business text\) returns jsonb/, "the same signature as 066");
  assert.match(fn, /security invoker/, "inside a definer caller (semasa_billing_public for anon, semasa_billing_issue) current_user is its owner");
  assert.match(fn, /if current_user in \('anon', 'authenticated'\)/);
  assert.match(fn, /not coalesce\(public\.semasa_is_uploader\(\), false\)/);
  assert.match(fn, /raise exception 'semasa: sign in first'/);
  assert.match(fn, /coalesce\(auth\.role\(\), ''\) <> 'service_role'/, "the service role (no auth.uid()) is never refused");
  // the same answer as 066: the business's own billing, else the old shared settings, else {}
  const body = (s) => s.slice(s.indexOf("coalesce(\n"), s.indexOf("'{}'::jsonb);") + 13).replace(/\s+/g, " ");
  const old = readFileSync(new URL("../supabase/066_businesses.sql", import.meta.url), "utf8");
  assert.equal(body(fn), body(old.slice(old.indexOf("create or replace function public.semasa_billing_settings_for"))));
  assert.match(fn, /revoke all on function public\.semasa_billing_settings_for\(text\) from public, anon;/);
  assert.ok(!/\bdrop\b|\bdelete from\b|\btruncate\b|\balter table\b/i.test(sql.replace(/^--.*$/gm, "")), "it changes this one function only");
});

console.log(`businesses: ${n} checks passed`);
