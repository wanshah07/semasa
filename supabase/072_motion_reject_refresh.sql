-- 072 · Motion storyboard: reject and refresh (Wan, 11 Nov 2026: "tambah butang reject ... tambah juga butang refresh").
--
--   * The storyboard decision gains a third action, 'reject': the film is stopped at 'rejected' and never made.
--     The worker only claims 'pending', so a rejected film is never picked up again.
--   * The status set gains 'rejected' (kept by 049 on re-run).
-- Safe to re-run.

alter table public.semasa_motions drop constraint if exists semasa_motions_status_check;
alter table public.semasa_motions add constraint semasa_motions_status_check
  check (status in ('waiting', 'pending', 'working', 'review', 'done', 'rejected', 'error'));

-- the page's decision gains 'reject' (p_action): a rejected storyboard stops the film, nothing is drawn or rendered
drop function if exists public.semasa_motion_storyboard_decide(uuid, text, jsonb, bigint);
create or replace function public.semasa_motion_storyboard_decide(p_motion uuid, p_action text, p_storyboard jsonb default null,
                                                                  p_written bigint default null)
returns text
language plpgsql security definer set search_path = public as $$
declare
  m record;
begin
  if auth.uid() is null or not public.semasa_is_uploader() then
    raise exception 'semasa: sign in first';
  end if;
  select id, status, storyboard into m from public.semasa_motions where id = p_motion for update;
  if not found then
    return 'gone';
  end if;
  if m.status <> 'review' then
    return 'status:' || m.status;
  end if;
  if p_action = 'reject' then
    update public.semasa_motions
       set status = 'rejected', storyboard = m.storyboard, storyboard_approved_at = null,
           storyboard_approved_by = null, error = '', stage = ''
     where id = p_motion;
    return 'ok';
  end if;
  if p_written is null or m.storyboard is null or (m.storyboard ->> 'written_at') is null
     or floor(extract(epoch from (m.storyboard ->> 'written_at')::timestamptz))::bigint <> p_written then
    return 'changed';
  end if;
  if p_action = 'approve' then
    if coalesce(p_storyboard, m.storyboard) is null then
      return 'no_storyboard';
    end if;
    if p_storyboard is not null and jsonb_typeof(p_storyboard) <> 'object' then
      return 'bad_storyboard';
    end if;
    update public.semasa_motions
       set storyboard = coalesce(p_storyboard, m.storyboard), storyboard_approved_at = now(), storyboard_approved_by = auth.uid(),
           status = 'pending', attempts = 0, error = ''
     where id = p_motion;
    return 'ok';
  elsif p_action = 'rewrite' then
    update public.semasa_motions
       set storyboard = null, storyboard_approved_at = null, storyboard_approved_by = null, status = 'pending', attempts = 0,
           error = '', stage = ''
     where id = p_motion;
    return 'ok';
  end if;
  return 'bad_action';
end $$;
revoke execute on function public.semasa_motion_storyboard_decide(uuid, text, jsonb, bigint) from public, anon;
grant execute on function public.semasa_motion_storyboard_decide(uuid, text, jsonb, bigint) to authenticated;

-- Telegram: the same decision (service role only)
drop function if exists public.semasa_telegram_motion_decide(uuid, text, bigint, bigint);
create or replace function public.semasa_telegram_motion_decide(p_motion uuid, p_action text, p_telegram_user_id bigint,
                                                                p_written bigint)
returns text
language plpgsql security definer set search_path = public as $$
declare
  l public.semasa_telegram_link;
  v text;
begin
  select * into l from public.semasa_telegram_link where id = 1;
  if l.telegram_user_id is null or l.telegram_user_id <> p_telegram_user_id then
    return 'not_linked';
  end if;
  perform set_config('request.jwt.claims', jsonb_build_object('sub', l.user_id, 'role', 'authenticated')::text, true);
  v := public.semasa_motion_storyboard_decide(p_motion, p_action, null, p_written);
  perform set_config('request.jwt.claims', '', true);
  return v;
end $$;
revoke execute on function public.semasa_telegram_motion_decide(uuid, text, bigint, bigint) from public, anon, authenticated;

notify pgrst, 'reload schema';
