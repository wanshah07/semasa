-- 026 · One post to a slot, and the same words never twice (Wan, 3 Oct 2026: "make blocker to avoid duplicate post to be
-- posted, and more than 1 post in 1 slot").
--
-- SAFE IN A SHARED PROJECT (KPI): adds two functions and one trigger on semasa_posts, nothing else. Re-runnable.
--
-- What it refuses, and only for a signed-in browser (auth.uid() not null). The publisher, the worker, the importer and the
-- SQL editor are service_role, where auth.uid() is null: they are never stopped here, because the publisher has its own
-- guard (backend/semasa/guard.py) and an importer must be able to bring a clash over so a person can see and fix it.
--   1. SLOT.      A draft or approved post cannot be put on a position (stream + date + slot) that another post that is
--                 not rejected already holds. Checked when the post is created, when its date, slot or stream changes, and
--                 when it is approved. A clash that already exists is NOT touched: editing the words of one of the two is
--                 still allowed, approving it is not until one of them moves.
--   2. DUPLICATE. A post cannot be APPROVED while another approved, scheduled or posted post of the same stream, within 90
--                 days, carries the same opening words (its first 120 letters and digits, case and punctuation ignored,
--                 in the language it is sent in). Same key as web/src/lib/slots.js captionKey and guard.caption_key.
-- Two tabs claiming one free slot at the same moment are serialised with an advisory lock on the position.
--
-- Runs after semasa_posts_gate and semasa_posts_gate_v2 (triggers of one kind fire in name order), so a post that gate 1
-- has already put back to draft (its words changed after approval) is checked as the draft it now is.

create or replace function public.semasa_caption_keys(t jsonb, lang text) returns text[]
language sql immutable set search_path = public as $$
  select coalesce(array_agg(distinct k), '{}'::text[]) from (
    select left(regexp_replace(lower(v.value), '[^[:alnum:]]+', '', 'g'), 120) as k
    from jsonb_each_text(case when jsonb_typeof(t -> lang) = 'object' then t -> lang else '{}'::jsonb end) v
  ) x where length(k) >= 20
$$;

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
          or (new.status = 'draft' and moved)) then
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

drop trigger if exists semasa_posts_gate_v3 on public.semasa_posts;
create trigger semasa_posts_gate_v3 before insert or update on public.semasa_posts
  for each row execute function public.semasa_posts_gate_v3();
revoke execute on function public.semasa_posts_gate_v3() from public, anon, authenticated;

-- Check (should print: 1 | 1):
--   select (select count(*) from pg_trigger where tgname = 'semasa_posts_gate_v3' and not tgisinternal) as trigger_present,
--          (select count(*) from pg_proc where proname = 'semasa_caption_keys') as keys_function;
-- A browser write that clashes now answers "semasa: slot taken: ..." or "semasa: duplicate post: ...".
