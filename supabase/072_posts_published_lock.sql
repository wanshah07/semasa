-- 072 · A post already handed to Buffer or LinkedIn stays where Buffer holds it (review of the publisher, 7 Nov 2026).
--
-- SAFE IN A SHARED PROJECT (KPI): replaces one function, public.semasa_posts_gate (the trigger that calls it is not touched).
-- Re-runnable. NOT applied by anything: run it in the SQL editor.
--
-- The bug. An APPROVED post can be half sent: Facebook is in Buffer for its slot while Instagram and Threads waited (Buffer's
-- plan cap) or failed. `published` then holds Facebook's record. The page could still move it, change its pictures, its
-- language or the caption Facebook carries, send it back to draft, reject it, or release its slot (Clear booked slots, a film
-- queued from Motion with p_override, supabase/054). The gate below sent an edited post back to draft and KEPT `published`;
-- Buffer kept the old slot and the old words. On re-approval the publisher sent the remaining channels at the NEW slot, the
-- post was split over two slots, and the old slot read as free to the page while Buffer still fired a post on it.
--
-- The rule added, for a signed-in browser only (auth.uid() not null; the publisher and the SQL editor are service_role):
-- once `published` has any channel in it, the post's date, slot, pictures (media_ids), language, stream and the caption of
-- every channel already handed over are locked, an approved post cannot be sent back to draft, and no such post can be
-- rejected (Buffer would still send what it holds while the page reads "rejected"). The captions
-- of channels NOT handed over yet may still change (a refused Instagram caption can be fixed); the gate then sends the post
-- back to draft as before, and approving it again sends only those channels. The page says the same (web/src/lib/slots.js
-- handedOver, PostEditor, releaseSlots); this is the layer that cannot be bypassed from a browser.
--
-- The way out when such a post really must move: delete its posts in Buffer (or on LinkedIn) first, then clear the records
-- in the SQL editor: update public.semasa_posts set published = '{}'::jsonb where id = '<post id>';
--
-- Everything else is the function as 006_slides.sql last defined it (identical to 005), copied exactly.

create or replace function public.semasa_posts_gate() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  sent_lang text;
  held      text;
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

  -- 072 · already handed to Buffer or LinkedIn: what Buffer holds cannot be changed from the page
  if jsonb_typeof(old.published) = 'object' and old.published <> '{}'::jsonb then
    select string_agg(k, ', ' order by k) into held from jsonb_object_keys(old.published) k;
    sent_lang := coalesce(old.lang, case when old.stream = 'linkedin' then 'en' else 'bm' end);
    if new.date is distinct from old.date or new.slot is distinct from old.slot
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

  new.published := old.published;
  new.errors := old.errors;
  if new.status = 'approved' and old.status is distinct from 'approved' then
    new.approved_by := auth.uid(); new.approved_at := now();
  elsif new.status = 'approved' and (new.text is distinct from old.text or new.citation is distinct from old.citation
        or new.media_ids is distinct from old.media_ids or new.date is distinct from old.date
        or new.slot is distinct from old.slot or new.lang is distinct from old.lang
        or new.stream is distinct from old.stream or new.slides is distinct from old.slides) then
    new.status := 'draft'; new.approved_by := null; new.approved_at := null;
  elsif new.status <> 'approved' then
    new.approved_by := null; new.approved_at := null;
  else
    new.approved_by := old.approved_by; new.approved_at := old.approved_at;
  end if;
  return new;
end $$;

-- Check (should print: 1): the gate carries the new refusal
--   select count(*) from pg_proc where proname = 'semasa_posts_gate' and prosrc like '%already handed to Buffer%';
-- From a signed-in page, moving a half-sent post now answers "semasa: post ini sudah diserahkan kepada Buffer/LinkedIn ...".
-- semasa_queue_motion (054) with p_override over such a post now fails with the same message instead of releasing it.
