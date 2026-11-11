-- 077 · Prestasi reads Zernio too (Wan, 11 Nov 2026: "linkedn no analysis, add for tiktok").
--
-- Zernio is the publisher since 10 Nov 2026, so the posts it sends are not in Buffer and had no figures. The worker
-- (backend/semasa/metrics.py) now also reads Zernio's analytics for Facebook, Instagram, Threads, TikTok and LinkedIn and
-- writes them with source 'zernio'. This file only lets the table accept that value. Nothing else changes.
--
-- SAFE IN A SHARED PROJECT (KPI): one check constraint on one semasa_ table. Run once; re-running changes nothing.

alter table public.semasa_post_metrics drop constraint if exists semasa_post_metrics_source_check;
alter table public.semasa_post_metrics add constraint semasa_post_metrics_source_check
  check (source in ('buffer', 'instagram', 'manual', 'zernio'));
