-- Semasa · PRE-CHECK · READ-ONLY. Run in the target project's SQL editor BEFORE 001–005.
-- It changes nothing. It answers: does anything named like Semasa's objects already exist here,
-- and how much of the shared free plan is already used?

select 'table' as kind, table_name as name
  from information_schema.tables
 where table_schema = 'public'
   and (table_name in ('isu_semasa_trends', 'media_generations', 'scrape_runs') or table_name like 'semasa%')
union all
select 'function', routine_name
  from information_schema.routines
 where routine_schema = 'public' and routine_name like 'semasa%'
union all
select 'bucket', id from storage.buckets where id like 'semasa%'
union all
select 'policy', tablename || ': ' || policyname
  from pg_policies where policyname ilike '%semasa%'
union all
select 'size: database', pg_size_pretty(pg_database_size(current_database()))
union all
select 'size: storage ' || bucket_id, pg_size_pretty(sum(coalesce((metadata->>'size')::bigint, 0)))
  from storage.objects group by bucket_id
order by 1, 2;
-- Expected on a project that has never had Semasa: only the "size:" rows.
