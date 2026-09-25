-- Semasa · the log · run ONCE in the SQL editor after 001–007. Idempotent: safe to run again.
--
-- SAFE IN A SHARED PROJECT (KPI): it creates semasa_log, one semasa_log_* function per table it
-- watches and one AFTER trigger on each Semasa table. No other app's table, policy or function is
-- read or changed.
--
-- Why it is built this way (Wan, 25 Sep 2026: "proper and organize, bukan macam ws regulab studio").
-- Studio's log was free text written by hand by three Routines: two timestamp shapes, fields nested one
-- level down so the page showed them blank, and events that nobody remembered to write were simply
-- missing. Here every row has the same shape, and the DATABASE writes it: a trigger on each table
-- records what changed at the moment it changes, whoever changed it (the page, the worker or the
-- SQL editor). An event cannot be forgotten by the code, and it cannot be written in a different
-- shape. A logging failure never blocks the change it describes: every trigger swallows its own error.
--
--   at        timestamptz, always (the page shows it in Malaysia time)
--   level     info | warn | error
--   area      scrape | idea | post | media | faq | publish | settings | system
--   event     a fixed code, e.g. post.approved, media.error, scrape.finished
--   title     one Malay line a person reads
--   ref_*     the row it is about, so the page can open it
--   actor     who did it (auth user id); null = the worker or the SQL editor
--   detail    the numbers and names behind the title

create table if not exists public.semasa_log (
  id        bigint generated always as identity primary key,
  at        timestamptz not null default now(),
  level     text        not null default 'info',
  area      text        not null,
  event     text        not null,
  title     text        not null,
  ref_table text,
  ref_id    text,
  actor     uuid        references auth.users (id) on delete set null,
  detail    jsonb       not null default '{}'::jsonb,
  constraint semasa_log_level_check check (level in ('info', 'warn', 'error')),
  constraint semasa_log_area_check  check (area in ('scrape', 'idea', 'post', 'media', 'faq', 'publish', 'settings', 'system'))
);
create index if not exists semasa_log_at_idx   on public.semasa_log (at desc);
create index if not exists semasa_log_area_idx on public.semasa_log (area, at desc);

alter table public.semasa_log enable row level security;
drop policy if exists "semasa log: uploaders read" on public.semasa_log;
create policy "semasa log: uploaders read" on public.semasa_log
  for select to authenticated using (public.semasa_is_uploader());
-- no insert/update/delete policy: only the triggers below (security definer) and the worker (service role) write

-- one writer for every trigger; it never raises
create or replace function public.semasa_log_write(p_level text, p_area text, p_event text, p_title text,
  p_ref_table text, p_ref_id text, p_detail jsonb) returns void
language plpgsql security definer set search_path = public as $$
begin
  insert into public.semasa_log (level, area, event, title, ref_table, ref_id, actor, detail)
  values (p_level, p_area, p_event, left(coalesce(p_title, p_event), 300), p_ref_table, p_ref_id, auth.uid(),
          coalesce(p_detail, '{}'::jsonb));
exception when others then
  raise warning 'semasa_log_write: % (%)', sqlerrm, p_event;
end $$;
-- Only the triggers (which run as the definer) may write the log. Supabase lets anon and authenticated call any
-- public function through PostgREST (/rest/v1/rpc/...), and the anon key is published in the site, so without
-- this a stranger could write "Dihantar ke instagram" rows, or fill the shared database with them.
revoke execute on function public.semasa_log_write(text, text, text, text, text, text, jsonb) from public, anon, authenticated;

-- helpers
create or replace function public.semasa_log_clip(t text, n int default 90) returns text
language sql immutable as $$
  select case when t is null or btrim(t) = '' then '(tanpa tajuk)'
              when length(btrim(t)) > n then left(btrim(t), n - 1) || '…' else btrim(t) end
$$;

-- --- scrape runs: one row when a run closes --------------------------------------------------
create or replace function public.semasa_log_scrape() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  v_failed jsonb;
  v_nfail  int;
  v_level  text := 'info';
  v_title  text;
begin
  if not (old.finished_at is null and new.finished_at is not null) then
    return new;
  end if;
  select coalesce(jsonb_agg(s->>'name'), '[]'::jsonb), count(*) into v_failed, v_nfail
    from jsonb_array_elements(coalesce(new.sources, '[]'::jsonb)) s where coalesce((s->>'ok')::boolean, true) = false;
  if coalesce(new.note, '') like 'crashed%' or coalesce(new.note, '') = 'every source failed' then
    v_level := 'error';
    v_title := 'Scrape gagal: ' || coalesce(new.note, '');
  else
    if v_nfail > 0 or (new.llm_model is not null and new.llm_ok is false) then v_level := 'warn'; end if;
    v_title := format('Scrape selesai: %s baharu daripada %s dibaca', new.inserted, new.seen)
      || case when v_nfail > 0 then format(' · %s sumber gagal', v_nfail) else '' end
      || case when new.llm_model is not null and new.llm_ok is false then ' · AI tidak digunakan' else '' end;
  end if;
  perform public.semasa_log_write(v_level, 'scrape', 'scrape.finished', v_title, 'scrape_runs', new.id::text,
    jsonb_build_object('seen', new.seen, 'inserted', new.inserted, 'llm_ok', new.llm_ok, 'llm_model', new.llm_model,
                       'failed_sources', v_failed, 'note', new.note,
                       'seconds', round(extract(epoch from new.finished_at - new.started_at))));
  return new;
exception when others then
  raise warning 'semasa_log_scrape: %', sqlerrm;
  return new;
end $$;
drop trigger if exists semasa_log_scrape on public.scrape_runs;
create trigger semasa_log_scrape after update on public.scrape_runs
  for each row execute function public.semasa_log_scrape();

-- --- ideas ------------------------------------------------------------------------------------
create or replace function public.semasa_log_idea() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  v_name text;
begin
  if tg_op = 'DELETE' then
    perform public.semasa_log_write('info', 'idea', 'idea.deleted', 'Idea dipadam: ' || public.semasa_log_clip(old.source_title),
      'semasa_ideas', old.id::text, '{}'::jsonb);
    return old;
  end if;
  v_name := public.semasa_log_clip(new.source_title);
  if tg_op = 'INSERT' then
    perform public.semasa_log_write('info', 'idea', 'idea.new', 'Idea baharu: ' || v_name, 'semasa_ideas', new.id::text,
      jsonb_build_object('stream', new.stream, 'domain', new.domain, 'media', new.make_media));
  elsif new.status is distinct from old.status then
    if new.status = 'drafted' then
      perform public.semasa_log_write('info', 'idea', 'idea.drafted', 'Draf ditulis: ' || v_name, 'semasa_ideas', new.id::text,
        jsonb_build_object('post_id', new.brief->>'post_id', 'read_article', new.brief->'source'->'ok', 'model', new.brief->>'model'));
    elsif new.status = 'error' then
      perform public.semasa_log_write('error', 'idea', 'idea.error', 'Idea gagal: ' || v_name, 'semasa_ideas', new.id::text,
        jsonb_build_object('error', new.error, 'attempts', new.attempts));
    elsif new.status = 'rejected' then
      perform public.semasa_log_write('info', 'idea', 'idea.rejected', 'Idea ditolak: ' || v_name, 'semasa_ideas', new.id::text, '{}'::jsonb);
    elsif new.status = 'new' and old.status in ('error', 'rejected') then
      perform public.semasa_log_write('info', 'idea', 'idea.requeued', 'Idea dihantar semula: ' || v_name, 'semasa_ideas', new.id::text, '{}'::jsonb);
    end if;
  end if;
  return new;
exception when others then
  raise warning 'semasa_log_idea: %', sqlerrm;
  return coalesce(new, old);
end $$;
drop trigger if exists semasa_log_idea on public.semasa_ideas;
create trigger semasa_log_idea after insert or update or delete on public.semasa_ideas
  for each row execute function public.semasa_log_idea();

-- --- posts ------------------------------------------------------------------------------------
create or replace function public.semasa_log_post() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  v_name  text;
  v_where jsonb;
begin
  if tg_op = 'DELETE' then
    perform public.semasa_log_write('info', 'post', 'post.deleted', 'Post dipadam: ' || public.semasa_log_clip(old.hook),
      'semasa_posts', old.id::text, jsonb_build_object('status', old.status));
    return old;
  end if;
  v_name := public.semasa_log_clip(nullif(new.hook, ''));
  v_where := jsonb_build_object('stream', new.stream, 'date', new.date, 'slot', new.slot);
  if tg_op = 'INSERT' then
    perform public.semasa_log_write('info', 'post', 'post.created', 'Draf baharu: ' || v_name, 'semasa_posts', new.id::text,
      v_where || jsonb_build_object('hard_flags', new.hard_flags));
  elsif new.status is distinct from old.status then
    if new.status = 'approved' then
      perform public.semasa_log_write('info', 'post', 'post.approved', 'Post diluluskan: ' || v_name, 'semasa_posts', new.id::text, v_where);
    elsif new.status = 'rejected' then
      perform public.semasa_log_write('info', 'post', 'post.rejected', 'Post ditolak: ' || v_name, 'semasa_posts', new.id::text, v_where);
    elsif new.status = 'draft' and old.status = 'approved'
          and (new.text, new.citation, new.media_ids, new.date, new.slot, new.lang, new.stream, new.slides)
              is distinct from (old.text, old.citation, old.media_ids, old.date, old.slot, old.lang, old.stream, old.slides) then
      -- the gate sent it back because it was changed after approval (the same fields the gate watches)
      perform public.semasa_log_write('warn', 'post', 'post.unapproved', 'Kembali ke draf (diubah selepas diluluskan): ' || v_name,
        'semasa_posts', new.id::text, v_where);
    elsif new.status = 'draft' and old.status = 'approved' then
      -- Wan pressed "Kembali ke draf" himself: nothing changed, nothing to warn about
      perform public.semasa_log_write('info', 'post', 'post.returned', 'Dikembalikan ke draf: ' || v_name,
        'semasa_posts', new.id::text, v_where);
    elsif new.status = 'draft' and old.status = 'rejected' then
      perform public.semasa_log_write('info', 'post', 'post.restored', 'Post dipulihkan ke draf: ' || v_name, 'semasa_posts', new.id::text, v_where);
    elsif new.status in ('scheduled', 'posted') then
      perform public.semasa_log_write('info', 'post', 'post.' || new.status,
        case new.status when 'scheduled' then 'Post dijadualkan: ' else 'Post diterbitkan: ' end || v_name,
        'semasa_posts', new.id::text, v_where || jsonb_build_object('published', new.published));
    end if;
  elsif new.status = 'approved' and (new.date is distinct from old.date or new.slot is distinct from old.slot) then
    perform public.semasa_log_write('info', 'post', 'post.moved', 'Post dialih: ' || v_name, 'semasa_posts', new.id::text,
      v_where || jsonb_build_object('from_date', old.date, 'from_slot', old.slot));
  end if;
  return new;
exception when others then
  raise warning 'semasa_log_post: %', sqlerrm;
  return coalesce(new, old);
end $$;
drop trigger if exists semasa_log_post on public.semasa_posts;
create trigger semasa_log_post after insert or update or delete on public.semasa_posts
  for each row execute function public.semasa_log_post();

-- --- media jobs: queued, done, failed (not every processing flip) ---------------------------------
create or replace function public.semasa_log_media() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  v_what text;
begin
  v_what := case new.mode when 'slides' then 'slaid' when 'recreate' then 'cipta semula' else 'prompt' end
            || ' · ' || new.type;
  if tg_op = 'INSERT' then
    perform public.semasa_log_write('info', 'media', 'media.queued', 'Kerja media dibaris (' || v_what || '): '
      || public.semasa_log_clip(nullif(new.prompt, ''), 70), 'media_generations', new.id::text,
      jsonb_build_object('mode', new.mode, 'type', new.type, 'post_id', new.post_id, 'idea_id', new.idea_id));
  elsif new.status is distinct from old.status and new.status = 'done' then
    perform public.semasa_log_write('info', 'media', 'media.done', 'Media siap (' || v_what || ')', 'media_generations', new.id::text,
      jsonb_build_object('provider', new.provider, 'model', new.model, 'attempts', new.attempts,
                         'slides', new.meta->'count', 'post_id', new.post_id));
  elsif new.status is distinct from old.status and new.status = 'error' then
    perform public.semasa_log_write('error', 'media', 'media.error', 'Media gagal (' || v_what || ')', 'media_generations', new.id::text,
      jsonb_build_object('error', new.error, 'provider', new.provider, 'attempts', new.attempts));
  end if;
  return new;
exception when others then
  raise warning 'semasa_log_media: %', sqlerrm;
  return new;
end $$;
drop trigger if exists semasa_log_media on public.media_generations;
create trigger semasa_log_media after insert or update of status on public.media_generations
  for each row execute function public.semasa_log_media();

-- --- FAQ: one row per real step; candidates are summarised by the scraper instead --------------------
create or replace function public.semasa_log_faq() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  v_name text;
begin
  if tg_op = 'DELETE' then
    perform public.semasa_log_write('info', 'faq', 'faq.deleted', 'FAQ dipadam: '
      || public.semasa_log_clip(coalesce(nullif(old.question_bm, ''), old.raw_question)), 'semasa_faqs', old.id::text, '{}'::jsonb);
    return old;
  end if;
  v_name := public.semasa_log_clip(coalesce(nullif(new.question_bm, ''), new.raw_question));
  if tg_op = 'INSERT' then
    if new.status = 'new' then
      perform public.semasa_log_write('info', 'faq', 'faq.new',
        case new.source_kind when 'headline' then 'FAQ daripada isu: ' else 'FAQ ditampal: ' end || v_name,
        'semasa_faqs', new.id::text, jsonb_build_object('source', new.source_kind));
    end if;
  elsif new.status is distinct from old.status then
    if new.status = 'new' and old.status = 'candidate' then
      perform public.semasa_log_write('info', 'faq', 'faq.accepted', 'Calon FAQ diterima: ' || v_name, 'semasa_faqs', new.id::text,
        jsonb_build_object('source', new.source_name));
    elsif new.status = 'new' then
      perform public.semasa_log_write('info', 'faq', 'faq.requeued', 'FAQ dihantar semula ke AI: ' || v_name, 'semasa_faqs', new.id::text, '{}'::jsonb);
    elsif new.status = 'dismissed' then
      perform public.semasa_log_write('info', 'faq', 'faq.dismissed', 'Calon FAQ diabaikan: ' || v_name, 'semasa_faqs', new.id::text,
        jsonb_build_object('source', new.source_name));
    elsif new.status = 'ready' and old.status = 'working' then
      perform public.semasa_log_write(case when new.needs_check then 'warn' else 'info' end, 'faq', 'faq.ready',
        'FAQ siap: ' || v_name || case when new.needs_check then ' (perlu semakan)' else '' end, 'semasa_faqs', new.id::text,
        jsonb_build_object('category', new.category, 'subcategory', new.subcategory, 'answer_source', new.answer_source,
                           'check_note', nullif(new.check_note, '')));
    elsif new.status = 'error' then
      perform public.semasa_log_write('error', 'faq', 'faq.error', 'FAQ gagal: ' || v_name, 'semasa_faqs', new.id::text,
        jsonb_build_object('error', new.error));
    end if;
  elsif new.status = 'ready' and auth.uid() is not null and (new.question_bm, new.answer_bm, new.question_en, new.answer_en, new.category)
        is distinct from (old.question_bm, old.answer_bm, old.question_en, old.answer_en, old.category) then
    perform public.semasa_log_write('info', 'faq', 'faq.edited', 'FAQ disunting: ' || v_name, 'semasa_faqs', new.id::text,
      jsonb_build_object('category', new.category));
  end if;
  return new;
exception when others then
  raise warning 'semasa_log_faq: %', sqlerrm;
  return coalesce(new, old);
end $$;
drop trigger if exists semasa_log_faq on public.semasa_faqs;
create trigger semasa_log_faq after insert or update or delete on public.semasa_faqs
  for each row execute function public.semasa_log_faq();

-- --- the publisher (dry run today) ---------------------------------------------------------------------
create or replace function public.semasa_log_publish() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  v_hook text;
begin
  select public.semasa_log_clip(nullif(hook, ''), 60) into v_hook from public.semasa_posts where id = new.post_id;
  perform public.semasa_log_write(
    case new.action when 'error' then 'error' when 'blocked' then 'warn' else 'info' end, 'publish', 'publish.' || new.action,
    case new.action
      when 'dry_run' then 'Cubaan kering: ' || new.channel || ' akan menghantar ' || coalesce(v_hook, 'post')
      when 'sent'    then 'Dihantar ke ' || new.channel || ': ' || coalesce(v_hook, 'post')
      when 'blocked' then 'Disekat (' || new.channel || '): ' || coalesce(v_hook, 'post')
      else 'Ralat penerbit (' || new.channel || '): ' || coalesce(v_hook, 'post') end,
    'semasa_posts', new.post_id::text,
    jsonb_build_object('channel', new.channel, 'why', new.detail->'why', 'due_at', new.detail->'would_send'->>'due_at'));
  return new;
exception when others then
  raise warning 'semasa_log_publish: %', sqlerrm;
  return new;
end $$;
drop trigger if exists semasa_log_publish on public.semasa_publish_log;
create trigger semasa_log_publish after insert on public.semasa_publish_log
  for each row execute function public.semasa_log_publish();

-- --- settings (not the worker's own bookkeeping rows: a log_sheet row logged would be sent to the sheet,
-- which moves log_sheet again, which is logged again — one row per run for ever) --------------------------
create or replace function public.semasa_log_settings() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if new.key in ('faq_sheet', 'log_sheet', 'telegram') or new.value is not distinct from old.value then
    return new;
  end if;
  perform public.semasa_log_write('info', 'settings', 'settings.changed',
    'Tetapan diubah: ' || case new.key when 'brand' then 'slot dan giliran' when 'faq' then 'kategori FAQ'
                                        when 'bahasa' then 'tabung perkataan Indonesia'
                                        when 'publishing' then 'suis penerbitan' else new.key end,
    'semasa_settings', new.key, jsonb_build_object('key', new.key));
  return new;
exception when others then
  raise warning 'semasa_log_settings: %', sqlerrm;
  return new;
end $$;
drop trigger if exists semasa_log_settings on public.semasa_settings;
create trigger semasa_log_settings after update on public.semasa_settings
  for each row execute function public.semasa_log_settings();

do $$
begin
  if not exists (select 1 from pg_publication_tables where pubname = 'supabase_realtime' and tablename = 'semasa_log') then
    alter publication supabase_realtime add table public.semasa_log;
  end if;
end $$;

-- Check (should print 1 | 7): the table, and its seven triggers
--   select (select count(*) from information_schema.tables where table_name = 'semasa_log'),
--          (select count(*) from pg_trigger where tgname like 'semasa_log_%' and not tgisinternal);
