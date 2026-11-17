-- 084 · A half-sent post can be moved to a new slot, to send its failed channels again (Wan, 16 Nov 2026: "move to new slot").
-- Run ONCE in the SQL editor, after 072. Idempotent: safe to run again.
--
-- SAFE IN A SHARED PROJECT (KPI): replaces two functions, public.semasa_posts_gate and public.semasa_posts_gate_v3 (the triggers
-- that call them are not touched), and the WITH CHECK of one policy on semasa_posts. NOT applied by anything: run it in the
-- SQL editor.
--
-- Why. On 16 Nov two ws.regulab films lost channels when their slot came (one went to Instagram only; TikTok and Threads
-- failed). Their `published` then held a `sent` record and `error` records, all for the old slot. Two things stopped the page
-- moving such a post: 072 locks the date and slot of any post with a channel in `published`, and the update policy (005)
-- refuses every write from a browser that leaves a post `scheduled`. And the publisher never sent a failed channel again.
-- The publisher now does, but only for a post a PERSON has moved (backend/semasa/publisher.py stale_failures): this file is
-- what lets the page make that move.
--
-- The rule added, for a signed-in browser only (auth.uid() not null; the publisher and the SQL editor are service_role):
--   The date and slot of a post already handed over may change when EVERY record in `published` is settled (status `sent` or
--   `error`: the scheduler holds nothing more for it) and AT LEAST ONE is `error`. While any record is still pending
--   (scheduled, sending, unconfirmed) the move is refused exactly as before: the scheduler still holds that slot.
--   * an APPROVED post that moves goes back to draft and is approved again, as any approved post does (and that draft may
--     move again);
--   * a SCHEDULED post stays scheduled and keeps who approved it and when. That move is the ONE write a browser may make to a
--     scheduled post: its date and slot (and the decision note the page adds), nothing else. Its words, source, slides and
--     pictures are what was approved and what is already out on the channels that went. The new slot must be in the future,
--     and it must be free: semasa_posts_gate_v3 now checks the slot for a scheduled post that moves, with the same lock and
--     the same refusal as for a draft. The policy's WITH CHECK takes `scheduled` for that one write; `posted` stays out, and
--     no browser can SET scheduled (the gate: "only the publisher sets").
--   Pictures, language, stream and the captions of the channels in `published` stay locked, as in 072.
--   The publisher then sends ONLY the channels whose record is `error`; a `sent` channel is never sent twice.
-- One more line: the gate no longer erases approved_by / approved_at on a scheduled or posted post (its last branch cleared
-- them for any status but approved). The publisher's guard ranks posts by approved_at.
--
-- Everything else is the two functions as 072_posts_published_lock.sql and 026_slot_and_duplicate_guard.sql define them, and
-- as they run in the project today (read back 16 Nov 2026), copied exactly.

create or replace function public.semasa_posts_gate() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  sent_lang text;
  held      text;
  moved     boolean := false;
  resend    boolean := false;
begin
  if auth.uid() is null then
    return new;                       -- service_role / SQL editor: the publisher itself
  end if;
  if tg_op = 'INSERT' then
    if new.status not in ('draft', 'rejected') then
      raise exception 'semasa: a new post starts as draft';
    end if;
    new.approved_by := null; new.approved_at := null;
    new.published := '{}'::jsonb; new.errors := '{}'::jsonb;
    return new;
  end if;
  if new.status in ('scheduled', 'posted') and new.status is distinct from old.status then
    raise exception 'semasa: only the publisher sets %', new.status;
  end if;
  if old.status in ('scheduled', 'posted') and new.status is distinct from old.status then
    raise exception 'semasa: a % post cannot be moved back from the page', old.status;
  end if;

  moved := new.date is distinct from old.date or new.slot is distinct from old.slot;
  -- 084 · a scheduled post takes one change from the page: its date and slot (with the page's decision note)
  if old.status = 'scheduled'
     and (to_jsonb(new) - array['date', 'slot', 'decisions', 'updated_at'])
         is distinct from (to_jsonb(old) - array['date', 'slot', 'decisions', 'updated_at']) then
    raise exception 'semasa: post yang sudah dijadualkan hanya boleh ditukar tarikh dan slotnya, untuk menghantar semula saluran yang gagal. / Only the date and slot of a scheduled post may change, to send its failed channels again.'
      using errcode = 'P0001';
  end if;

  -- 072 · already handed to Buffer or LinkedIn: what Buffer holds cannot be changed from the page
  if jsonb_typeof(old.published) = 'object' and old.published <> '{}'::jsonb then
    select string_agg(k, ', ' order by k) into held from jsonb_object_keys(old.published) k;
    sent_lang := coalesce(old.lang, case when old.stream = 'linkedin' then 'en' else 'bm' end);
    -- 084 · every hand-over is settled and at least one failed: the scheduler holds nothing, so the post may move
    resend := old.status in ('draft', 'approved', 'scheduled')
              and not exists (select 1 from jsonb_each(old.published) r
                               where jsonb_typeof(r.value) <> 'object'
                                  or coalesce(r.value ->> 'status', '') not in ('sent', 'error'))
              and exists (select 1 from jsonb_each(old.published) r where r.value ->> 'status' = 'error');
    if (moved and not resend)
       or new.media_ids is distinct from old.media_ids or new.lang is distinct from old.lang
       or new.stream is distinct from old.stream
       or exists (select 1 from jsonb_object_keys(old.published) k
                   where (new.text -> sent_lang ->> k) is distinct from (old.text -> sent_lang ->> k)) then
      raise exception 'semasa: post ini sudah diserahkan kepada Buffer/LinkedIn (%): tarikh, slot, gambar, bahasa dan kapsyen saluran itu dikunci. Padam dahulu di Buffer, kemudian kosongkan rekodnya. / This post is already handed to Buffer/LinkedIn (%): its date, slot, pictures, language and those channels'' captions are locked. Delete it in Buffer first, then clear its records.',
        held, held using errcode = 'P0001';
    end if;
    if (old.status = 'approved' and new.status = 'draft')
       or (new.status = 'rejected' and old.status is distinct from 'rejected') then
      raise exception 'semasa: post ini sudah diserahkan kepada Buffer/LinkedIn (%): ia tidak boleh dikembalikan ke draf atau ditolak kerana Buffer tetap menghantarnya. Padam dahulu di Buffer, kemudian kosongkan rekodnya. / This post is already handed to Buffer/LinkedIn (%): it cannot go back to draft or be rejected, because Buffer still sends it. Delete it in Buffer first, then clear its records.',
        held, held using errcode = 'P0001';
    end if;
  end if;

  -- 084 · a scheduled post moves only to send failed channels again, and only to a slot still ahead: nothing approves it
  -- again after the move, so nothing later would catch a slot already gone
  if moved and old.status = 'scheduled' then
    if not resend then
      raise exception 'semasa: post yang sudah dijadualkan hanya boleh dipindah apabila ada salurannya yang gagal. / A scheduled post moves only when one of its channels failed.'
        using errcode = 'P0001';
    end if;
    if new.date is null or new.slot is null or new.slot !~ '^([01][0-9]|2[0-3]):[0-5][0-9]$'
       or (new.date::text || ' ' || new.slot || ':00+08')::timestamptz <= now() then
      raise exception 'semasa: slot baharu mesti tarikh dan masa yang belum tiba. / The new slot must be a date and time still ahead.'
        using errcode = 'P0001';
    end if;
  end if;

  new.published := old.published;
  new.errors := old.errors;
  if new.status = 'approved' and old.status is distinct from 'approved' then
    new.approved_by := auth.uid(); new.approved_at := now();
  elsif new.status = 'approved' and (new.text is distinct from old.text or new.citation is distinct from old.citation
        or new.media_ids is distinct from old.media_ids or new.date is distinct from old.date
        or new.slot is distinct from old.slot or new.lang is distinct from old.lang
        or new.stream is distinct from old.stream or new.slides is distinct from old.slides) then
    new.status := 'draft'; new.approved_by := null; new.approved_at := null;
  elsif old.status in ('scheduled', 'posted') then
    new.approved_by := old.approved_by; new.approved_at := old.approved_at;     -- 084 · the approval it went out on is kept
  elsif new.status <> 'approved' then
    new.approved_by := null; new.approved_at := null;
  else
    new.approved_by := old.approved_by; new.approved_at := old.approved_at;
  end if;
  return new;
end $$;

-- semasa_posts_gate_v3 as 026 defines it, with one change: a SCHEDULED post that moves is checked for a free slot too
-- (before 084 no scheduled post could move from a browser, so 026 had no reason to look).
create or replace function public.semasa_posts_gate_v3() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  other record;
  moved boolean;
  mine  text[];
  lang  text;
begin
  if auth.uid() is null then
    return new;                          -- the publisher, the worker, the importer, the SQL editor
  end if;

  moved := tg_op = 'INSERT' or new.date is distinct from old.date or new.slot is distinct from old.slot
           or new.stream is distinct from old.stream;

  -- 1 · a position holds one post
  if new.date is not null and new.slot is not null
     and ((new.status = 'approved' and (tg_op = 'INSERT' or old.status is distinct from 'approved' or moved))
          or (new.status in ('draft', 'scheduled') and moved)) then
    perform pg_advisory_xact_lock(hashtext('semasa_slot ' || new.stream || ' ' || new.date::text || ' ' || new.slot));
    select p.id, p.hook, p.status into other from public.semasa_posts p
      where p.id <> new.id and p.stream = new.stream and p.date = new.date and p.slot = new.slot and p.status <> 'rejected'
      order by p.created_at limit 1;
    if found then
      raise exception 'semasa: slot taken: % % is already held by "%" (%). Move one of the two posts first.',
        new.date, new.slot, left(coalesce(nullif(other.hook, ''), other.id::text), 60), other.status
        using errcode = 'P0001';
    end if;
  end if;

  -- 2 · the same words are not approved twice
  if new.status = 'approved' and (tg_op = 'INSERT' or old.status is distinct from 'approved') then
    lang := coalesce(new.lang, case when new.stream = 'linkedin' then 'en' else 'bm' end);
    mine := public.semasa_caption_keys(new.text, lang);
    if array_length(mine, 1) is not null then
      select p.id, p.hook, p.status, p.date into other from public.semasa_posts p
        where p.id <> new.id and p.stream = new.stream and p.status in ('approved', 'scheduled', 'posted')
          and (p.date is null or new.date is null or abs(p.date - new.date) <= 90)
          and public.semasa_caption_keys(p.text, coalesce(p.lang, case when p.stream = 'linkedin' then 'en' else 'bm' end)) && mine
        order by p.created_at limit 1;
      if found then
        raise exception 'semasa: duplicate post: "%" (%, %) already carries these words. Change the wording or reject one of them.',
          left(coalesce(nullif(other.hook, ''), other.id::text), 60), other.status, coalesce(other.date::text, 'no date')
          using errcode = 'P0001';
      end if;
    end if;
  end if;
  return new;
end $$;
revoke execute on function public.semasa_posts_gate_v3() from public, anon, authenticated;

-- The update policy as 005_studio.sql defines it, with `scheduled` added to what the written row may be. Before this, every
-- browser write that left a post scheduled was refused here, whatever it changed. The gate above is what keeps that true for
-- everything but the move: it runs first, and refuses any other change to a scheduled post.
alter policy "semasa posts: uploaders update" on public.semasa_posts
  using (public.semasa_is_uploader())
  with check (public.semasa_is_uploader() and status in ('draft', 'approved', 'rejected', 'scheduled'));

-- Check (should print 1 | 1 | 1): both gates and the policy carry the new rule
select (select count(*) from pg_proc where proname = 'semasa_posts_gate' and prosrc like '%to send its failed channels again%') as gate,
       (select count(*) from pg_proc where proname = 'semasa_posts_gate_v3' and prosrc like '%(''draft'', ''scheduled'')%') as slot_check,
       (select count(*) from pg_policies where tablename = 'semasa_posts' and policyname = 'semasa posts: uploaders update'
          and with_check like '%scheduled%') as policy;
-- From a signed-in page, moving a post whose every channel record is sent or failed (at least one failed) is now accepted;
-- while a channel is still queued it answers "semasa: post ini sudah diserahkan kepada Buffer/LinkedIn ..." as before.
