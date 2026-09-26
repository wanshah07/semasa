/* One client for the whole page. The anon key is public by design; Row Level Security
   (supabase/002_rls.sql) is what protects the data, not secrecy of this key. */
import { createClient } from "@supabase/supabase-js";

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
  watch: "semasa_watch",
};
export const TABLES_UPLOADERS = "semasa_uploaders";
// Namespaced so Semasa can share a Supabase project with another app (supabase/003_storage.sql).
export const BUCKETS = { reference: "semasa-reference", generated: "semasa-generated" };

/** Surface a PostgREST/Storage error as one readable line. */
export function errText(error) {
  if (!error) return "";
  return [error.message, error.details, error.hint].filter(Boolean).join(" — ");
}
