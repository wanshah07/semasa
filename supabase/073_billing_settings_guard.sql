-- 073 · Billing settings: only a Semasa uploader may read them (7 Nov 2026 review).
--
-- semasa_billing_settings_for (066) was SECURITY DEFINER and granted to every `authenticated` user with no check of its own,
-- and Semasa shares the KPI Supabase project (mwaocnbgvbkhovktgods) with other apps. So any signed-in user of ANY app on that
-- project could call it over the REST API and read every business's billing settings: bank name, account name and number,
-- company details, prefixes and terms.
--
-- The same signature and the same answer, with one difference: called straight from the API by a user who is not a Semasa
-- uploader, it raises 'semasa: sign in first'.
--
-- Why the check reads current_user and not auth.uid(), and why the function is now SECURITY INVOKER:
--   * semasa_billing_public (066) calls this function for a CLIENT opening a "view online" link: that caller is `anon`, with no
--     auth.uid(). A check on auth.uid() or auth.role() would refuse that client and break every public quotation, invoice and
--     receipt link. semasa_billing_issue (066) calls it too.
--   * Both callers are SECURITY DEFINER, so inside them current_user is their owner (postgres), never anon or authenticated.
--     As SECURITY INVOKER this function sees that owner as its current_user, so a definer caller passes the check and reads
--     both tables as the owner, exactly as before. A direct API call sees current_user = 'authenticated' (or 'anon', which
--     has no EXECUTE anyway) and must be an uploader.
--   * The service role (backend/semasa, GitHub workflows) has current_user = 'service_role', no auth.uid(), and bypasses RLS:
--     it passes, as before. auth.role() = 'service_role' is accepted too, for a caller that carries the claim in its JWT.
--   * Read directly by an uploader, both tables answer through their own RLS policies ("semasa businesses: uploaders read",
--     "semasa settings: uploaders read"), which let an uploader read every row this reads: the same answer as before.
-- Nothing else changes: no table, policy or other function. Safe to run again.

create or replace function public.semasa_billing_settings_for(p_business text) returns jsonb
language plpgsql stable security invoker set search_path = public as $$
begin
  if current_user in ('anon', 'authenticated')
     and coalesce(auth.role(), '') <> 'service_role'
     and not coalesce(public.semasa_is_uploader(), false) then
    raise exception 'semasa: sign in first';
  end if;
  return coalesce(
    (select nullif(billing, '{}'::jsonb) from public.semasa_businesses where id = coalesce(p_business, 'wsregulab')),
    (select value from public.semasa_settings where key = 'billing'),
    '{}'::jsonb);
end $$;
revoke all on function public.semasa_billing_settings_for(text) from public, anon;
grant execute on function public.semasa_billing_settings_for(text) to authenticated, service_role;
