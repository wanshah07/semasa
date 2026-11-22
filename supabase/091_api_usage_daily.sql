-- Semasa · AI usage as daily totals for the page (Wan, 22 Nov 2026: "Fix what you recommend", after an egress audit). Run ONCE in
-- the SQL editor, after 090. Idempotent: safe to run again. Until it is run the page reads raw rows as before (web/src/lib/
-- usageDaily.js answers "missing" and hooks.useApiUsage falls back), so running it late breaks nothing.
--
-- Papan's tokens chart re-read 2,000 semasa_api_usage rows every 5 minutes and the API page 5,000; the API pulse alone writes
-- ~800 rows a day (area 'pulse', 0 tokens), so the "14-day" chart covered about two days and the "90-day" view about four.
-- This returns one row per Malaysian day, gateway, area, model and ok, with the calls and the sums: 90 days were 545 rows
-- (57 KB) on 22 Nov 2026, against 21,000 raw rows (5 MB). The page asks for the whole window once and then only the last two
-- days, so a 5-minute refresh is a few dozen rows.
--
-- SAFE IN A SHARED PROJECT (KPI): it creates one function, semasa_api_usage_daily, and touches nothing else. SECURITY INVOKER:
-- it reads semasa_api_usage as the caller, so the table's own policy ("uploaders read", supabase/035) decides who sees what,
-- exactly as a direct read does. anon cannot call it.
create or replace function public.semasa_api_usage_daily(p_days integer default 30)
returns table (day date, gateway text, area text, model text, ok boolean, calls bigint, total_tokens bigint, prompt_tokens bigint,
               completion_tokens bigint, ms bigint)
language sql stable security invoker set search_path = public as $$
  select (u.created_at at time zone 'Asia/Kuala_Lumpur')::date as day, u.gateway, u.area, u.model, u.ok,
         count(*)::bigint, sum(u.total_tokens)::bigint, sum(u.prompt_tokens)::bigint, sum(u.completion_tokens)::bigint,
         sum(u.ms)::bigint
    from public.semasa_api_usage u
   where u.created_at >= (((now() at time zone 'Asia/Kuala_Lumpur')::date - (greatest(1, least(coalesce(p_days, 30), 120)) - 1))::timestamp
                          at time zone 'Asia/Kuala_Lumpur')
   group by 1, 2, 3, 4, 5
   order by 1 desc, 2, 3, 4, 5
$$;

revoke execute on function public.semasa_api_usage_daily(integer) from public, anon;
grant execute on function public.semasa_api_usage_daily(integer) to authenticated, service_role;

notify pgrst, 'reload schema';

-- Check (as the SQL editor, which bypasses RLS: the totals of the last 14 days, the pulse apart):
select day, sum(calls) filter (where area <> 'pulse') as calls, sum(calls) filter (where area = 'pulse') as pulse_calls,
       sum(total_tokens) as tokens
  from public.semasa_api_usage_daily(14) group by day order by day desc;
-- To undo:
--   drop function if exists public.semasa_api_usage_daily(integer);
