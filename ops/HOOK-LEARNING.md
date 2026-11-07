# Hooks that learn from results (Wan, 7 Nov 2026)

*"make sure all apply the 25 Hooks, and will update the instructions automatically based on top viewers and interaction post"*

## Where the 25 hooks apply now
| Output | Hook |
|---|---|
| Post caption (ws.regulab, LinkedIn) | first line built on a shape, declared in `hook_shape` (#131) |
| Carousel cover and poster headline | the cover's / poster's title **is the hook** (`hook_bank.cover`): kept when the writer already did it, set to the hook when not (up to 12 words), left alone when the hook is too long for a headline. `brief.hook_on_cover` says which |
| Motion film | scene 1's heading is the hook, shape declared and kept on the film (#134); the 3 stages and the shots are in `ops/MOTION-PIPELINE.md` |
| A hook style made from screenshots | replaces the built-in 25 in all of the above while selected |

## The learning
`.github/workflows/hook-learning.yml` runs daily at 05:40 UTC (13:40 MYT), after `metrics.yml` has refreshed `semasa_post_metrics`.
`backend/semasa/hook_learning.py`:
1. takes every post with figures in the last **60 days** (views, or reach / impressions when there are no views; interactions =
   reactions + comments + shares + saves + reposts + quotes + clicks), summing a post's channels;
2. joins each to the shape it was written on: the idea's `brief.hook_shape`, or for a film's post the film's `check_report.hook.shape`
   (post, then its media job, then the film), and to the hook style it came from;
3. ranks each (style, shape) with **3 or more results** on the mean of its average views and its average interaction rate, each as a
   share of the best shape's (so one viral outlier or a tiny fan audience cannot decide alone);
4. writes `settings.hook_learning` (the ranking), shown on the card **Hook yang berjaya / Hooks that work** in Tetapan.

The writers (post, revise, film script) get one sentence appended to the required-hook block, after every rule: *the top three shapes
earned the most views and interaction; prefer one when it fits the story; use another when none fits, and now and then one with fewer
than 3 results; never reuse an earlier hook's words.* Nothing is said until two shapes are ranked.

## Why it cannot lock itself in or break a rule
* A hint, never a rule: all 25 shapes (or the style's own) stay allowed, every standing rule outranks it, and no hook text is quoted.
* Unranked shapes keep getting tried (the sentence says so), so they can earn a place.
* The numbers are on the card; **Learn from results** (`settings.hook_learning_on`) turns it off for every writer.
* It writes only `settings.hook_learning`: no post, idea or setting of yours.

## Limits to know
* LinkedIn gives no figures (the connection reads none), so its posts add nothing. Only Facebook, Instagram and Threads (Buffer) count.
* Figures are a daily snapshot per channel post. Films are counted only through the post they were queued as.
* Early on there is little to rank: with a few posts a week it takes weeks before a shape reaches 3 results.
