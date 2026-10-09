/* One client for the whole page. The anon key is public by design; Row Level Security
   (supabase/002_rls.sql) is what protects the data, not secrecy of this key. */
import { createClient } from "@supabase/supabase-js";
import { tr } from "./i18n";
import { isOutage } from "./upstream";

const url = import.meta.env.VITE_SUPABASE_URL;
const anon = import.meta.env.VITE_SUPABASE_ANON_KEY;

export const configured = Boolean(url && anon);

export const supabase = configured
  ? createClient(url, anon, {
      auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
      realtime: { params: { eventsPerSecond: 5 } },
    })
  : null;

export const TABLES = {
  trends: "isu_semasa_trends", media: "media_generations", runs: "scrape_runs",
  ideas: "semasa_ideas", posts: "semasa_posts", prompts: "semasa_prompts",
  settings: "semasa_settings", publishLog: "semasa_publish_log", faqs: "semasa_faqs", log: "semasa_log",
  watch: "semasa_watch", fragrances: "semasa_fragrances", canvas: "semasa_canvas", aiConfig: "semasa_ai_config",
  // Bil (supabase/028_billing.sql)
  clients: "semasa_clients", projects: "semasa_projects", billingDocs: "semasa_billing_docs", billingEvents: "semasa_billing_events",
  billingOutbox: "semasa_billing_outbox", billingCounters: "semasa_billing_counters",
  subscriptions: "semasa_subscriptions",                      // Langganan (supabase/030_subscriptions.sql)
  receipts: "semasa_receipts",                                // Resit (supabase/033_receipts.sql)
  // CRM (supabase/031_crm.sql)
  crmContacts: "semasa_crm_contacts", crmCampaigns: "semasa_crm_campaigns", crmOutbox: "semasa_crm_outbox", crmActivities: "semasa_crm_activities",
};
export const TABLES_UPLOADERS = "semasa_uploaders";
// Namespaced so Semasa can share a Supabase project with another app (supabase/003_storage.sql).
export const BUCKETS = { reference: "semasa-reference", generated: "semasa-generated" };

/** Surface a PostgREST/Storage error as one readable line. */
export function errText(error) {
  if (!error) return "";
  const text = [error.message, error.details, error.hint].filter(Boolean).join(" — ");
  // an upstream outage (Cloudflare/Supabase 5xx) comes back as a whole HTML error page: say it in one line, never print the page
  if (isOutage(error)) {
    return tr("Pelayan Supabase tidak menjawab seketika (ralat 5xx). Cuba lagi sebentar; fail anda tidak hilang.",
      "Supabase did not answer for a moment (a 5xx error). Try again shortly; your file is not lost.");
  }
  // the database's own refusals (supabase/017_review_fixes.sql) are written in English: say them in the page's language
  if (/belongs to an approved post/.test(text)) {
    return tr("Gambar ini milik post yang sudah diluluskan: kembalikan post itu ke draf dahulu, kemudian ubah atau padam gambar.",
      "This picture belongs to an approved post: put that post back to draft first, then change or delete the picture.");
  }
  // supabase/026: a browser write that would put two posts on one slot, or approve the same words twice
  const taken = /semasa: slot taken: (\S+) (\d\d:\d\d) is already held by "([^"]*)"/.exec(text);
  if (taken) {
    return tr(`Slot ${taken[1]} ${taken[2]} sudah dipegang oleh "${taken[3]}". Pindahkan salah satu post dahulu.`,
      `The slot ${taken[1]} ${taken[2]} is already held by "${taken[3]}". Move one of the two posts first.`);
  }
  const dup = /semasa: duplicate post: "([^"]*)" \(([^)]*)\) already carries these words/.exec(text);
  if (dup) {
    return tr(`Perkataan yang sama sudah ada pada "${dup[1]}" (${dup[2]}). Ubah ayatnya atau tolak salah satu post.`,
      `"${dup[1]}" (${dup[2]}) already carries these words. Change the wording or reject one of the two posts.`);
  }
  return text;
}
