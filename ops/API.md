# API: the AI gateways, their keys, their models and the tokens we spend

Wan, 9 Oct 2026: *"add feature that I can track status of token from mireld and afiq API including their models"*.

## What it is
One tab (**API**, under Reference), one card per gateway the workers are configured with: **rootsys (Afiq)** as the primary
writer (`LLM_BASE_URL`), **Mireld** as the backup (`LLM_FALLBACK_BASE_URL`), and the page's own reader slot when it points
at a third host. Each card:

- **verdict**: Up (a five-token question answered) · Model did not answer · Key refused (401/403) · Unreachable · No key ·
  Not checked in 13 h;
- **key**: set or not, its last four characters (a key never reaches the page: the probe writes the last four, nothing else);
- **model**: the configured model and whether it is in the gateway's own `/models` list — the "spelt differently" trap the
  chat function's README records (`claude-sonnet-5.5` vs `claude-sonnet-5-5`);
- **latency** and the HTTP status of the models call;
- **models listed**: every id the gateway returns, the configured one first, models we have spent tokens on tinted green;
- **balance**, when the gateway exposes one (`/dashboard/billing/credit_grants`, `/credits`, `/balance`, `/user/balance`,
  `/usage`, `/key` are tried; whichever answers JSON with a number is shown with its path). Neither gateway is assumed to.
- **tokens** in the chosen window (7 / 30 / 90 days), calls and failures.

Under the cards: tokens a day, stacked by gateway, and who spends them (scrape, media, idea, receipt, probe).

## Two writers, two sources of truth
1. **The probe** — `backend/semasa/api_status.py`, `.github/workflows/api.yml` every 6 hours (`40 */6 * * *` UTC) and on
   demand — writes `semasa_api_status`. It uses the same secrets and variables as the scrape, so it probes exactly the
   configuration the workers run with, after the page's AI settings (016) are laid over GitHub's.
2. **The usage sink** — every runner that builds an `LLM` calls `api_status.attach(store, area)` first (scrape, media,
   idea, receipt). From then on `llm.py` records one `semasa_api_usage` row per call: gateway (by host), model, the
   `usage` the gateway reported (`prompt_tokens`/`completion_tokens`, or Anthropic's `input_tokens`/`output_tokens`),
   milliseconds, ok or the error. A gateway that reports no usage still counts as a call with 0 tokens. The sink never
   raises and never slows a call that failed. Rows older than `settings.api_probe.keep_days` (90) are pruned by the probe.

The AI **chat** (`supabase/functions/semasa-chat`) holds its own Mireld key in the function's secrets and is not on this
page: its calls go browser → function → Mireld and never through the workers. Adding it means the function inserting
its own usage rows with the service role, which it does not hold today.

## Deploy
1. Run `supabase/035_repos_api.sql` once (shared with the Repo tab).
2. Actions → **API status** → Run workflow. Usage rows appear from the next scrape / media / idea / receipt run.

## The router asks live (31 Oct 2026)

Wan: *"why I cannot change the model, make sure for auto model search is live"*. Two faults, one cause.

- **A pin to another model of a gateway was thrown away unasked.** The 6-hourly probe asks each gateway ONE model. rootsys's probe
  model (kimi-k3.1-pro) answered 502, so the router wrote the whole gateway off as down, and a pin to glm-5.3 on it was "switched away
  from" without glm-5.3 ever being tried: the text writer stayed on Mireld's kimi-k3 and the tab showed no change.
- **Auto never looked further than the configured model.** A gateway whose one model was down stayed down however many of its
  other models were working.

`ai_team.route(..., live=ai_team.LIVE)` now asks at decision time (a five-token question, 12 s, up to 3 tries a gateway, answers kept
10 minutes in `ai_team_state.live`): a **pinned model** is asked itself and its answer outranks the probe of another model; in **Auto**
a gateway whose configured model is not known to work is **searched**: the configured model, then the models that answered its real
calls (fastest first), then its live `/models` list minus pictures and embeddings. The first that answers is used and the decision
says so ("glm-5.3 found by a live search"). A pin whose model does not answer is still switched away from, now with the reason.
`AI_TEAM_LIVE=0` turns the questions off (tests do).

**Decided at once.** Saving `settings.ai_team` (a pin, or "Test live") wakes `api.yml` through `supabase/057` (repository_dispatch
`ai_team_changed`, the Vault token 042 uses), which probes and decides again in about a minute; the tab shows "testing your choice
live" until a decision newer than the change arrives, then the live answers under the job. Without the Vault token the pin takes
effect at the next run, as before.
