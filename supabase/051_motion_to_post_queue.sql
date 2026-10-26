-- 051 · Motion → the post queue (Wan, 26 Oct 2026: "allow me to choose which platform to post, so from the video can directly post
-- or queue to post to platform, once post automatically the video compress and into post queue and remove from motion list").
--
-- A finished film is queued from the Motion tab to the platforms Wan picks. `semasa_queue_motion` writes, in one transaction, the
-- film as a video in media_generations (the compressed copy when the worker made one) and a DRAFT post that points at it, on the
-- chosen platforms and the chosen date and slot, then marks the film `queued_post_id` so the Motion list stops showing it. The
-- post is a draft: the single gate is still Wan's Approve click in the Posts tab, and the publisher scans it again before sending.
--   · semasa_motions.social_url / social_bytes   the worker's platform-friendly copy (H.264 High, yuv420p, AAC, capped bitrate)
--   · semasa_motions.queued_post_id / queued_at  set when the film is queued; null again if that draft is deleted
--   · semasa_posts.channels                      the platforms this post goes to; null means every channel of its stream
-- Safe to re-run. Run it BEFORE the worker that writes social_url and the publisher that reads channels are deployed.

alter table public.semasa_motions add column if not exists social_url text not null default '';
alter table public.semasa_motions add column if not exists social_bytes int not null default 0;
alter table public.semasa_motions add column if not exists queued_post_id uuid references public.semasa_posts (id) on delete set null;
alter table public.semasa_motions add column if not exists queued_at timestamptz;
create index if not exists semasa_motions_queued_idx on public.semasa_motions (queued_post_id);

alter table public.semasa_posts add column if not exists channels text[];
alter table public.semasa_posts drop constraint if exists semasa_posts_channels_check;
alter table public.semasa_posts add constraint semasa_posts_channels_check
  check (channels is null or channels <@ array['facebook', 'instagram', 'threads', 'linkedin']::text[]);

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
  p_hard     int
) returns uuid
language plpgsql security definer set search_path = public as $$
declare
  m       public.semasa_motions%rowtype;
  v_media uuid;
  v_post  uuid;
  v_url   text;
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

  insert into public.media_generations (reference_url, generated_media_url, type, status, mode, prompt, provider, model, idea_id,
                                        meta, created_by)
  values (m.video_url, v_url, 'video', 'done', 'clip', coalesce(m.title, ''), 'semasa', 'motion', m.idea_id,
          jsonb_build_object('flow', 'motion', 'motion_id', m.id, 'poster_url', m.poster_url, 'width', m.width,
                             'height', m.height, 'seconds', m.duration_s,
                             'bytes', case when coalesce(m.social_url, '') <> '' then m.social_bytes else m.bytes end,
                             'compressed', coalesce(m.social_url, '') <> '', 'alt', coalesce(m.title, '')),
          auth.uid())
  returning id into v_media;

  insert into public.semasa_posts (idea_id, stream, lang, hook, text, citation, media_ids, date, slot, status, flags, hard_flags,
                                   channels, created_by)
  values (m.idea_id, m.stream, p_lang, left(coalesce(p_hook, ''), 300), coalesce(p_text, '{}'::jsonb), coalesce(p_citation, ''),
          array[v_media], p_date, p_slot, 'draft', coalesce(p_flags, '[]'::jsonb), coalesce(p_hard, 0), p_channels, auth.uid())
  returning id into v_post;

  update public.media_generations set post_id = v_post where id = v_media;
  update public.semasa_motions set queued_post_id = v_post, queued_at = now() where id = m.id;
  return v_post;
end;
$$;

revoke all on function public.semasa_queue_motion(uuid, text[], text, text, jsonb, text, date, text, jsonb, int) from public, anon;
grant execute on function public.semasa_queue_motion(uuid, text[], text, text, jsonb, text, date, text, jsonb, int) to authenticated;
notify pgrst, 'reload schema';
