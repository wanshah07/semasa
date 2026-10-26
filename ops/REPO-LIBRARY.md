# Pustaka repo: a library for every function

Wan, 23 Oct 2026: paste a GitHub link, Semasa reads the repo (never clones or runs it), checks it for safety, summarises it and files it.
Wan, 26 Oct 2026: *"the repo library only for style motion video, I want put all function repo"*.

## What it does

- The Repo tab takes any github.com link. The row lands as `pending`; the database wakes `repo-library.yml` (`repository_dispatch`
  `repo_pending`); `backend/semasa/repo_library.py` reads the repo through the GitHub API (metadata, README, root files, install
  manifests, workflow names) with a read-only token.
- **Safety** is two readings and the stricter stands: static rules (`SAFETY_RULES`: pipe to shell, `iex` download, base64 to shell,
  `eval` of fetched text, miners, wallet/seed asks, install hooks, no licence, archived, stale) and the AI's own. The AI can add concern,
  never remove a flag the rules found. "Safe" means nothing in what was read looks wrong: a reading, not an audit.
- **Function**: the AI writes `functions` (3 to 8 short lines of what the repo can DO, from the README), `summary_bm` / `summary_en`,
  `use_for`, `how_to_run`, tags and a category. The card shows them; Wan can re-file a repo (his category survives a re-read),
  re-check or remove it. Search and a safety filter sit above the list.

## Categories (26 Oct 2026: widened beyond video)

`motion, video, suara, muzik, imej, 3d, kemahiran-ai, agen-ai, mcp, scraper, pelayar, regulatori, dokumen, web, frontend, api, data,
analitik, automasi, pemasaran, keselamatan, devops, terjemahan, alatan, lain`. A repo is filed by what it DOES; `motion` is one of many.
The list lives in three places that must agree: `DEFAULT_CATEGORIES` (worker), `CATEGORIES` + `CATEGORY_WORDS` (page), and the stored
`settings.repo_library.categories` (**the stored list beats the code default**, so `supabase/055_repo_library_functions.sql` sets it).
Both tests fail if a category has no BM/EN word.

## Files

`supabase/055_repo_library_functions.sql` (the `functions` column, the stored list, re-read of the first three repos),
`backend/semasa/repo_library.py`, `web/src/components/RepoLibrary.jsx`, `web/src/lib/repoLibrary.js`, tests in
`backend/tests/test_repo_library.py` and `web/repoLibrary.test.mjs`.
