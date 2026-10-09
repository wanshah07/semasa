# Repo: the office repositories in six dimensions

Wan, 9 Oct 2026: *"add all repo office environment in 6D in the system so i can track the repos progress and status"*.

## What it is
One tab (**Repo**, under Reference) with one card per repository and six tiles on each card:

| Dimension | What the tile says | Where it comes from |
|---|---|---|
| Code | commits in 7 / 30 days, the last commit, a 14-day sparkline | `GET /repos/{r}/commits?since=` |
| Pull requests | open PRs with the CI verdict on each head, merged in 30 days | `/pulls`, `/commits/{sha}/check-runs` |
| CI | green when every workflow's latest run passed, red when any failed | `/actions/workflows`, each `/runs?per_page=1` |
| Issues | open issues (GitHub's count includes PRs; they are subtracted) | `/issues` |
| Schedules | workflows with a `cron:`, read from the workflow file itself | `/contents/.github/workflows/*.yml` |
| Deploy | GitHub Pages address and the latest build | `/pages`, `/pages/builds/latest` |

Two rings: **health** (100 minus penalties: red CI −30, no push for 30 days −20 / 14 days −10, more than 3 open PRs −10,
a PR with red CI −10, more than 5 issues −10, a failing cron −10) and **progress** (merged ÷ (merged + open) over 30 days).
Cards are sorted worst first. A table under the cards lists every cron in the office with its last verdict, so a
schedule that quietly stopped is visible in one place.

## The six repositories
`settings.repos.list`, seeded by `supabase/035_repos_api.sql`: `wanshah07/semasa`, `argus`, `argus-cards`, `kkm-complaints`,
`kpi-system`, `malaysian-regulatory-affairs`. **Repo list** in the tab edits it (one `owner/name` a line; a GitHub URL is
accepted). The next run reads the new list; a repo removed keeps its last row until the next run drops nothing — rows are
upserted by `full_name`, never deleted, so remove a stale card by deleting its row if it bothers you.

## The worker
`backend/semasa/repos.py`, run by `.github/workflows/repos.yml` every 6 hours (`25 */6 * * *` UTC) and on demand. About
10–30 GitHub calls a repository. Token, in order: **`REPOS_TOKEN`** (make a fine-grained PAT: Repository access → the
six repositories; Permissions → Contents, Actions, Issues, Pull requests, Metadata, all *Read-only*), else
`LANDING_REPO_TOKEN`, else the job's own `GITHUB_TOKEN` (which reads only `semasa` itself: the private repositories then
show *404* on their card, which is the token saying it cannot see them, not an outage).

## Deploy
1. Run `supabase/035_repos_api.sql` once in the KPI project (proof row `3 | 3 | 2`).
2. GitHub → Settings → Secrets → Actions → `REPOS_TOKEN` (the PAT above).
3. Actions → **Repos** → Run workflow. The tab fills on its next refresh.
