# Telegram response paths

Semasa owns `@SocialMediaWan_bot`. Hermes uses a different bot. This change does not alter transport ownership or approval rules.

## Fast, read-only commands

`supabase/functions/semasa-telegram/commands.js` serves exact, argument-free `/menu`, `/start`, `/help`, `/bantuan`, `/status`, `/jadual`, `/bil` and `/kesihatan` in the webhook response. Telegram executes the returned `sendMessage`; no bot token is needed in the function.

Only the linked private sender is eligible. A recent unfinished inbox item, pending topic, unreadable state, malformed data or incomplete result returns control to the ordered worker. A 👎 correction that is still awaited no longer does (16 Nov 2026): the worker never takes a command as the correction, and one 👎 left unanswered had been sending every `/menu` to the worker. Successful fast commands are stored as `done`, not `new`, so they do not wake GitHub Actions. A duplicate command receipt does not return another message.

## Menu taps (16 Nov 2026)

`/menu` and `/start` open the button menu of every Semasa segment and page. It is one catalogue, `rules/telegram_menu.json`, drawn by `menu.js` here and by `backend/semasa/telegram_menu.py` in the worker (`menu_data.js` is the generated copy the function reads; `python ops/telegram_menu_copy.py` rewrites it and `rules/telegram_menu_cases.json`, and both test suites fail while either is behind).

A tap that only opens another menu (`m:home`, `m:s:<segment>`, `m:p:<tab>`) is answered in the webhook response with `editMessageText`: the same message is redrawn, no worker starts, and the receipt is stored as `done` with `semasa_timing.path = "menu"`. The way back under an answer is `n:<node>`: the same menu, sent as a new message (`sendMessage`), so the answer he just read stays in the chat. The reads `a:status`, `a:jadual`, `a:kesihatan`, `a:bil` and `a:help` are answered here too, with the slash command's own text. The rules are the fast commands' own: only the linked account in its private chat, nothing of his unfinished in the inbox, and no pending question (a menu button drops a pending question, and only the worker writes that row). A pending 👎 correction does not hold a tap back: it waits for his next message, not for a button.

Everything a button does (drafts and their approval, a new idea, a poster, the language switch) still goes to the worker, which also draws any menu the webhook left to it.

One thing was not measured on a live Telegram app: the webhook answers a menu tap with the menu itself and so never calls `answerCallbackQuery` for it (a webhook response carries one method). After a redraw the pressed button is gone with the old keyboard; after an `n:` tap the pressed button stays, and its progress mark can show until Telegram gives up waiting for an answer. Nothing is lost either way. If that reads badly on Wan's phone, set `menu_inline` to `false` in the `telegram_chat` settings row: every tap then goes to the worker, which answers the tap first ("Sedang diproses…") and draws the menu after.

`/draf`, `/robot`, generation commands and every other inline callback still use the worker. Draft previews must register the exact version and message before a later approval; publisher compliance, slot and duplicate guards remain unchanged. Motion still requires storyboard approval before rendering.

## Model answers

`fast.js` gives each attempted model at most seven seconds and shares a fifteen-second model budget, starting before team/context reads. The existing team picker and pin are preserved. A slow first gateway no longer consumes the full allowance intended for its backup. Content refusals do not route around to another gateway. Database calls, receipt persistence and turn logging are not a hard fifteen-second webhook SLA.

Fast receipts include `payload.semasa_timing` with the path and elapsed milliseconds; model receipts also include attempt count. Provider keys and request headers are not stored there.

## Deployment verification

After Deploy functions succeeds, manually run the Telegram workflow with `latency_probe=true`. It invokes `python -m semasa.telegram_latency_probe` using existing workflow credentials. The probe covers `/menu`, `/status`, `/jadual` and `/kesihatan`, prints HTTP elapsed time and reads back each exact generated update ID. Success requires the expected recipient, `sendMessage`, a `done` receipt and the matching command note.

The authenticated `X-Semasa-Probe: latency-v1` path cannot fall back to ordinary owner work: when a fast reply is unavailable it returns `probe=true, inline=false`, without queueing, linking accounts or clearing a pending topic. The probe does not execute the returned Telegram method or approve/publish anything. Run it only after the function version supporting probe mode is deployed.

Tests: `node web/telegramCommands.test.mjs`, `node web/telegramMenu.test.mjs`, `node web/telegramLatency.test.mjs`, `node web/telegramWebhook.test.mjs`, and `pytest tests/test_telegram_latency_probe.py` from backend. The webhook test transpiles the real entrypoint and substitutes only the database boundary. Full Node 20/Linux CI remains the release gate; Windows CRLF can affect unrelated source-text tests.
