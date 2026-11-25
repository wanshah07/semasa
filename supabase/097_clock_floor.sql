-- Semasa · the clock also wakes the worker when fewer than `min_drafts` posts wait for Wan · run ONCE. Idempotent.
--
-- Wan, 25 Nov 2026: "make sure every hours ada at least 2 draft post ... do it now since I do[n't] receive any in telegram".
-- The worker's autofill keeps `settings.autofill.min_drafts` (default 2) drafts waiting (backend/semasa/autofill.py), and each
-- media run announces new drafts on Telegram. But semasa_clock_worker woke the worker ONLY when a job, idea, FAQ, video or
-- watch link was waiting ("an idle day costs no Actions minutes"), and GitHub's own 15-minute schedule is best effort: on 25 Nov
-- it did not start the media workflow once between 05:21 and 11:51 UTC. With every draft approved nothing was waiting, so
-- nothing woke the worker, no draft was written and Telegram stayed silent.
--
-- Now an empty queue counts as work: when autofill is on and fewer than min_drafts drafts (dated today or later) plus open ideas
-- are waiting, the clock wakes the worker, at most once every 30 minutes (so a feed with nothing fitting costs a run every half
-- hour, not every 10 minutes). The rest of the body is unchanged from 009, 011, 013 and 017.

create or replace function public.semasa_clock_floor() returns boolean
language plpgsql security definer set search_path = public as $$
declare
  s        jsonb;
  v_on     boolean;
  v_min    int;
  v_streams text[];
  v_today  date := (now() at time zone 'Asia/Kuala_Lumpur')::date;
  v_have   int;
begin
  select value into s from public.semasa_settings where key = 'autofill';
  if s is null or jsonb_typeof(s) <> 'object' then return false; end if;
  v_on := coalesce((s->>'enabled') = 'true', false);
  if not v_on and s->>'enabled_from' is not null then
    begin
      v_on := now() >= (s->>'enabled_from')::timestamptz;
    exception when others then v_on := false;
    end;
  end if;
  if not v_on then return false; end if;
  begin
    v_min := case when s ? 'min_drafts' then (s->>'min_drafts')::int else 2 end;
  exception when others then v_min := 2;
  end;
  v_min := least(greatest(v_min, 0), 10);
  if v_min = 0 then return false; end if;
  v_streams := coalesce(
    (select array_agg(x) from jsonb_array_elements_text(case when jsonb_typeof(s->'streams') = 'array' then s->'streams'
                                                           else '[]'::jsonb end) x
      where x in ('regulab', 'linkedin')),
    array['regulab', 'linkedin']);
  if array_length(v_streams, 1) is null then v_streams := array['regulab', 'linkedin']; end if;
  v_have := (select count(*) from public.semasa_posts where status = 'draft' and date >= v_today and stream = any(v_streams))
          + (select count(*) from public.semasa_ideas where status in ('new', 'working') and stream = any(v_streams));
  if v_have >= v_min then return false; end if;
  if exists (select 1 from public.semasa_log where event = 'clock.floor' and at > now() - interval '30 minutes') then
    return false;
  end if;
  perform public.semasa_log_write('info', 'system', 'clock.floor',
    'Jam Supabase: kurang daripada ' || v_min || ' draf menunggu (' || v_have || '), pekerja dikejutkan untuk menulis lagi',
    null, null, jsonb_build_object('waiting', v_have, 'min_drafts', v_min));
  return true;
end $$;

create or replace function public.semasa_clock_worker() returns text
language plpgsql security definer set search_path = public as $$
-- ONE body in every file that defines this function (009, 011, 013, 017, 097): re-running an older file must never drop what
-- a later one added. A table or column a later file creates is counted only once it exists.
declare
  v_waiting int := 0;
begin
  select count(*) into v_waiting from public.media_generations
   where status = 'pending' or (status = 'processing' and updated_at < now() - interval '60 minutes');
  v_waiting := v_waiting + (select count(*) from public.semasa_ideas
   where status = 'new' or (status = 'working' and updated_at < now() - interval '30 minutes'));
  begin
    v_waiting := v_waiting + (select count(*) from public.semasa_faqs
     where status = 'new' or (status = 'working' and updated_at < now() - interval '30 minutes'));
  exception when undefined_table then null;            -- 007 not run yet
  end;
  begin
    v_waiting := v_waiting + (select count(*) from public.semasa_videos
     where status = 'new' or (status = 'working' and updated_at < now() - interval '30 minutes'));
  exception when undefined_table then null;            -- 011 not run yet
  end;
  begin
    -- a stuck link is counted whatever its attempts: the worker ends it in error rather than leave it spinning
    v_waiting := v_waiting + (select count(*) from public.semasa_watch
     where status = 'pending' or (status = 'working' and claimed_at < now() - interval '30 minutes'));
  exception when undefined_table or undefined_column then null;   -- 012 / 013 not run yet
  end;
  if v_waiting = 0 and public.semasa_clock_floor() then
    v_waiting := 1;                                     -- too few drafts waiting: the worker writes more (autofill's floor)
  end if;
  if v_waiting = 0 then
    return 'nothing waiting';
  end if;
  return public.semasa_clock_dispatch('media_pending');
end $$;
