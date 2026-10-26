-- 054 · Motion → the post queue can take a booked slot (Wan, 26 Oct 2026: "dari video motion pun boleh select slot atau override
-- slot book"). semasa_queue_motion gains p_override: the draft or approved posts of the film's stream that hold the chosen date and slot
-- are released from it, in the same transaction that queues the film. A scheduled or sent post is never released (the slot guard refuses).
-- The function changes signature (one more argument with a default), so the 051 one is dropped first: two overloads that both match a
-- call would be ambiguous. Safe to re-run.

drop function if exists public.semasa_queue_motion(uuid, text[], text, text, jsonb, text, date, text, jsonb, int, boolean);

create or replace function public.semasa_queue_motion(
  p_motion   uuid,
  p_channels text[],
  p_lang     text,
  p_hook     text,
  p_text     jsonb,
  p_citation text,
  p_date     date,
  p_slot     text,
  p_flags    jsonb,
  p_hard     int,
  p_approve  boolean default false,
  p_override boolean default false
) returns uuid
language plpgsql security definer set search_path = public as $$
declare
  m       public.semasa_motions%rowtype;
  v_media uuid;
  v_post  uuid;
  v_url   text;
  v_ok    boolean := coalesce(p_approve, false) and coalesce(p_hard, 0) = 0;
  v_when  text := to_char(now(), 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"');
begin
  if not public.semasa_is_uploader() then
    raise exception 'not allowed';
  end if;
  select * into m from public.semasa_motions where id = p_motion for update;
  if not found then
    raise exception 'the film does not exist';
  end if;
  if m.status <> 'done' or coalesce(m.video_url, '') = '' then
    raise exception 'the film is not finished';
  end if;
  if m.queued_post_id is not null then
    raise exception 'the film is already in the post queue';
  end if;
  if coalesce(array_length(p_channels, 1), 0) = 0 then
    raise exception 'choose at least one platform';
  end if;
  v_url := coalesce(nullif(m.social_url, ''), m.video_url);

  -- Wan, 26 Oct 2026: "dari video motion pun boleh select slot atau override slot book". With p_override the draft or approved
  -- posts of this stream that hold p_date + p_slot are let go of it first (an approved one goes back to draft: semasa_posts_gate does
  -- that itself when its slot changes). A post the publisher has scheduled or sent is not touched, so the slot guard
  -- (semasa_posts_gate_v3) still refuses the new post when one of those holds the slot.
  if coalesce(p_override, false) and p_date is not null and p_slot is not null then
    update public.semasa_posts
       set date = null, slot = null,
           decisions = decisions || jsonb_build_array(jsonb_build_object('at', v_when, 'by', 'page', 'action', 'moved',
                         'note', 'slot ' || p_date::text || ' ' || p_slot || ' released for a film queued from Motion'))
     where stream = m.stream and date = p_date and slot = p_slot and status in ('draft', 'approved');
  end if;

  insert into public.media_generations (reference_url, generated_media_url, type, status, mode, prompt, provider, model, idea_id,
                                        meta, created_by)
  values (m.video_url, v_url, 'video', 'done', 'clip', coalesce(m.title, ''), 'semasa', 'motion', m.idea_id,
          jsonb_build_object('flow', 'motion', 'motion_id', m.id, 'poster_url', m.poster_url, 'width', m.width,
                             'height', m.height, 'seconds', m.duration_s,
                             'bytes', case when coalesce(m.social_url, '') <> '' then m.social_bytes else m.bytes end,
                             'compressed', coalesce(m.social_url, '') <> '', 'alt', coalesce(m.title, '')),
          auth.uid())
  returning id into v_media;

  -- a new post starts as draft (semasa_posts_gate); Wan's Approve click is then an update, which the same gate stamps
  insert into public.semasa_posts (idea_id, stream, lang, hook, text, citation, media_ids, date, slot, status, flags, hard_flags,
                                   channels, created_by, decisions)
  values (m.idea_id, m.stream, p_lang, left(coalesce(p_hook, ''), 300), coalesce(p_text, '{}'::jsonb), coalesce(p_citation, ''),
          array[v_media], p_date, p_slot, 'draft', coalesce(p_flags, '[]'::jsonb), coalesce(p_hard, 0), p_channels, auth.uid(),
          jsonb_build_array(jsonb_build_object('at', to_char(now(), 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'), 'by', 'page',
                                               'action', 'queued from Motion')))
  returning id into v_post;
  if v_ok then
    update public.semasa_posts
       set status = 'approved',
           decisions = decisions || jsonb_build_array(jsonb_build_object(
             'at', to_char(now(), 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'), 'by', 'page', 'action', 'approved'))
     where id = v_post;
  end if;

  update public.media_generations set post_id = v_post where id = v_media;
  update public.semasa_motions set queued_post_id = v_post, queued_at = now() where id = m.id;
  return v_post;
end;
$$;

revoke all on function public.semasa_queue_motion(uuid, text[], text, text, jsonb, text, date, text, jsonb, int, boolean, boolean) from public, anon;
grant execute on function public.semasa_queue_motion(uuid, text[], text, text, jsonb, text, date, text, jsonb, int, boolean, boolean) to authenticated;
notify pgrst, 'reload schema';
