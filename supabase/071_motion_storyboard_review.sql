-- 071 · Every Motion storyboard is shown and approved before a picture is drawn or a frame rendered (Wan, 7 Nov 2026: "make
-- sure all storyboard appear and approve before proceed for motion creation").
--
-- How it works:
--   * The worker writes the storyboard (the script and each scene's shot; for a template film, the whole storyboard object),
--     saves it in `storyboard` and sets the film to 'review'. It stops there: nothing is drawn, rendered or spent.
--   * The Motion tab and Telegram show it. Wan approves it as it is, approves it with his edits, or asks for a new one.
--     Approving stamps storyboard_approved_at/_by and sets the film 'pending', which wakes the worker (043's trigger fires on
--     status = 'pending'); the worker then makes the film from EXACTLY the saved storyboard, never a new one.
--   * The database holds the line, not only the worker: a film cannot become 'done' unless its storyboard was approved.
--     Films finished before this migration are left as they are (the guard only checks a change INTO 'done').
--   * An automatic retry after a failure keeps the approved storyboard. "Make again" in the page asks for a new storyboard,
--     and so a new approval.
--
-- Safe to re-run. Keeps every earlier status (043 + 049's 'waiting') and adds 'review'.

alter table public.semasa_motions drop constraint if exists semasa_motions_status_check;
alter table public.semasa_motions add constraint semasa_motions_status_check
  check (status in ('waiting', 'pending', 'working', 'review', 'done', 'error'));

alter table public.semasa_motions add column if not exists storyboard jsonb;
alter table public.semasa_motions add column if not exists storyboard_approved_at timestamptz;
alter table public.semasa_motions add column if not exists storyboard_approved_by uuid references auth.users (id) on delete set null;

-- 1 · the guard: no film is finished on a storyboard nobody approved ------------------------------------------------------
create or replace function public.semasa_motions_storyboard_guard() returns trigger
language plpgsql set search_path = public as $$
begin
  if new.status = 'done' and old.status is distinct from 'done' and new.storyboard_approved_at is null then
    raise exception 'semasa: this film''s storyboard has not been approved (Motion → Storyboard)';
  end if;
  -- the approval belongs to the storyboard it was given for: a new storyboard (or none) clears it
  if new.storyboard is distinct from old.storyboard and new.storyboard_approved_at is not distinct from old.storyboard_approved_at
     and old.storyboard_approved_at is not null then
    new.storyboard_approved_at := null;
    new.storyboard_approved_by := null;
  end if;
  return new;
end $$;
revoke execute on function public.semasa_motions_storyboard_guard() from public, anon, authenticated;

drop trigger if exists semasa_motions_storyboard_guard on public.semasa_motions;
create trigger semasa_motions_storyboard_guard before update on public.semasa_motions
  for each row execute function public.semasa_motions_storyboard_guard();

-- 2 · the page: approve (optionally with edits) or ask for a new storyboard -------------------------------------------------
-- p_action: 'approve' | 'rewrite'. p_storyboard: the edited storyboard, or null to approve the saved one unchanged. The worker
-- checks an edited storyboard again before it uses it (counts, word limits, banned words), so an edit cannot slip a rule.
create or replace function public.semasa_motion_storyboard_decide(p_motion uuid, p_action text, p_storyboard jsonb default null)
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
revoke execute on function public.semasa_motion_storyboard_decide(uuid, text, jsonb) from public, anon;
grant execute on function public.semasa_motion_storyboard_decide(uuid, text, jsonb) to authenticated;

-- 3 · Telegram: the same decision, for the one linked Telegram account only (service role only) -----------------------------
create or replace function public.semasa_telegram_motion_decide(p_motion uuid, p_action text, p_telegram_user_id bigint)
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
  -- act as Wan's own login for this transaction only, so the approval is stamped with his account exactly as a page click is
  perform set_config('request.jwt.claims', jsonb_build_object('sub', l.user_id, 'role', 'authenticated')::text, true);
  v := public.semasa_motion_storyboard_decide(p_motion, p_action, null);
  perform set_config('request.jwt.claims', '', true);
  return v;
end $$;
revoke execute on function public.semasa_telegram_motion_decide(uuid, text, bigint) from public, anon, authenticated;

notify pgrst, 'reload schema';
