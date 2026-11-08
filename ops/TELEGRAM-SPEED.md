# Telegram response paths

Semasa owns `@SocialMediaWan_bot`. Hermes uses a different bot. This change does not alter transport ownership or approval rules.

## Fast, read-only commands

`supabase/functions/semasa-telegram/commands.js` serves exact, argument-free `/menu`, `/start`, `/help`, `/bantuan`, `/status`, `/jadual`, `/bil` and `/kesihatan` in the webhook response. Telegram executes the returned `sendMessage`; no bot token is needed in the function.

Only the linked private sender is eligible. A recent unfinished inbox item, pending topic, pending correction, unreadable state, malformed data or incomplete result returns control to the ordered worker. Successful fast commands are stored as `done`, not `new`, so they do not wake GitHub Actions. A duplicate command receipt does not return another message.

`/draf`, `/robot`, generation commands and every inline callback still use the worker. Draft previews must register the exact version and message before a later approval; publisher compliance, slot and duplicate guards remain unchanged. Motion still requires storyboard approval before rendering.

## Model answers

`fast.js` gives each attempted model at most seven seconds and shares a fifteen-second model budget, starting before team/context reads. The existing team picker and pin are preserved. A slow first gateway no longer consumes the full allowance intended for its backup. Content refusals do not route around to another gateway. Database calls, receipt persistence and turn logging are not a hard fifteen-second webhook SLA.

Fast receipts include `payload.semasa_timing` with the path and elapsed milliseconds; model receipts also include attempt count. Provider keys and request headers are not stored there.

## Deployment verification

After Deploy functions succeeds, manually run the Telegram workflow with `latency_probe=true`. It invokes `python -m semasa.telegram_latency_probe` using existing workflow credentials. The probe covers `/menu`, `/status`, `/jadual` and `/kesihatan`, prints HTTP elapsed time and reads back each exact generated update ID. Success requires the expected recipient, `sendMessage`, a `done` receipt and the matching command note.

The authenticated `X-Semasa-Probe: latency-v1` path cannot fall back to ordinary owner work: when a fast reply is unavailable it returns `probe=true, inline=false`, without queueing, linking accounts or clearing a pending topic. The probe does not execute the returned Telegram method or approve/publish anything. Run it only after the function version supporting probe mode is deployed.

Tests: `node web/telegramCommands.test.mjs`, `node web/telegramLatency.test.mjs`, `node web/telegramWebhook.test.mjs`, and `pytest tests/test_telegram_latency_probe.py` from backend. The webhook test transpiles the real entrypoint and substitutes only the database boundary. Full Node 20/Linux CI remains the release gate; Windows CRLF can affect unrelated source-text tests.
