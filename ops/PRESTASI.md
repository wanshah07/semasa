# Prestasi · post analytics (9 Oct 2026)

Wan: *"add feature that can track post same as attached"* — two screenshots of Threads' own analytics: account reach, average
views, engagement, replies, the peak post, *Best publishing window Fri 12-15*, a *Posting performance by time* heatmap (day ×
3-hour window, post counts) and a *Window inspector*.

## What it is
- **`semasa_post_metrics`** (`supabase/034_post_metrics.sql`): one row per channel-post. Buffer's post id, the channel, the Semasa
  post it came from (`post_id`, joined through `semasa_posts.published.<channel>.id`), when the network sent it, and the figures
  normalised into columns (views, reach, impressions, reactions, comments, shares, saves, reposts, quotes, clicks, follows,
  engagement %) plus the raw list.
- **Worker** `backend/semasa/metrics.py`, `.github/workflows/metrics.yml`, once a day at 13:10 MYT (after Buffer refreshes its
  figures, which it does between about 01:30 and 04:00 UTC). It reads every SENT post on the three ws.regulab channels for the
  last `settings.metrics.days_back` days (120) with `senders.Buffer.sent_with_metrics` and upserts. Two Buffer calls a run.
  Run it by hand: GitHub → Actions → Metrics → Run workflow.
- **Prestasi tab** (`web/src/pages/PrestasiTab.jsx`, arithmetic in `web/src/lib/analytics.js`, tests in `web/analytics.test.mjs`):
  channel and period filters (all / Threads / Instagram / Facebook; 7 / 30 / 90 days); tiles for account views (reach on
  Instagram), average views a post, engagement, replies; views a day; the peak post; the 7 × 8 heatmap in Malaysia time with
  the best window ringed; the window inspector (average views, total views, replies, engagement, the posts in it); a per-channel
  split; and the ranked table. Everything is computed in the browser from the rows; the page writes nothing.

## What each network gives through Buffer (measured 9 Oct 2026)
| channel | figures |
|---|---|
| Threads | views, reactions, comments, quotes, reposts, engagement rate |
| Instagram | views, reach, reactions, comments, shares, saves, follows, engagement rate |
| Facebook | impressions (used as "views"), reactions, comments, shares, clicks, engagement rate |
| LinkedIn | **nothing**: the Composio connection holds `w_member_social` only (it can post, not read). The page says so. |

"Engagement" on the tiles is interactions ÷ views (interactions = reactions + comments + shares + saves + reposts + quotes), computed
across the posts in the filter; the table shows each network's own engagement rate as Buffer reports it. "Best publishing window" is
the day × window cell with the highest average views among cells carrying at least one post; with few posts it moves as posts land.

## Not done, said plainly
- The figures are a daily snapshot, not a time series: a post's row is overwritten with Buffer's latest numbers.
- Threads' *account* reach (780,522 in the screenshot) is a profile-level figure Buffer does not expose; the tile sums post views.
- Instagram's own insights through Composio (`INSTAGRAM_GET_IG_MEDIA_INSIGHTS`, measured 21 Sep 2026) would add saves/profile
  activity per post; the worker has a `source` column for it but does not read it yet.
