# Cutover: ws.regulab Studio → Semasa (Friday 2 Oct 2026)

Wan, 29 Sep 2026: *"we will start using semasa this friday and will delete ws.regulab studio permanently … all post from
friday night move to semasa … 100% functioning without wait my approval on friday night"*.

"Without my approval" means the **cutover** runs with nobody at a keyboard. The **per-post Approve gate stays**: a post
Wan approved in Studio arrives in Semasa already approved; a post he had not approved arrives as a draft and waits.

## Before Friday (Wan)

| # | What | Where |
|---|------|-------|
| 1 | `BUFFER_API_KEY` secret | publish.buffer.com/settings/api → GitHub → semasa → Settings → Secrets → Actions |
| 2 | `COMPOSIO_CONSUMER_KEY` secret (the **For You** key, `ck_…`: the workspace that holds the LinkedIn connection) | Composio → Switch → For You → Connect my agent → MCP URL → Your API Key → **Copy** (never Regenerate: that cuts off Claude too) → same place. The old `COMPOSIO_API_KEY` (Platform) is ignored while this one is set |
| 3 | Run `supabase/023_go_live.sql` once | Supabase (KPI project) → SQL editor. The last select must return one row |
| 4 | Run **Senders probe** once | GitHub → Actions → Senders probe → Run workflow. Green = both roads open, nothing posted |

Keys never go in a chat, a file or a commit.

## Friday night (MYT) — no one needs to be awake

| Time | What | Who |
|------|------|-----|
| 19:20 | Studio's last release run (hosts + schedules the 21:00 post, sends LinkedIn 19:00) | Studio Routine |
| 19:45 | Disable Studio's 4 Routines; final read of Studio's store; host any new card in `argus-cards`; md5-prove every card; `studio-import.yml` with `dry=false` | cutover session (`send_later`) |
| 20:00 | Publishing switch opens by itself (`enabled_from 2026-10-02T12:00:00Z`) | database |
| 20:05 | One `publish.yml` run by hand (workflow_dispatch): the clock's next run is Sat 06:20, too late for a Friday 21:00 post Studio's 19:20 run did not place. Buffer gets the Friday 21:00 and the coming days' approved posts, each at its own slot; one already in Buffer is adopted, not doubled | cutover session (`send_later`) |
| Sat 06:20 | First clock run; first LinkedIn slot (06:00) through Composio | publish.yml (06:20 · 11:20 · 19:20 MYT) |
| Sat 06:40 | Session checks the first runs and the publish log | cutover session |

The session commands, in order:

```
python ops/studio_cutover.py host  --dump DIR --cards /home/user/argus-cards --since 2026-09-27T00:00+08:00
git -C /home/user/argus-cards push
python ops/studio_cutover.py build --dump DIR --cards /home/user/argus-cards --since 2026-09-27T00:00+08:00 --out OUT
# then one studio-import.yml dispatch per OUT/import-NN.json, dry=true first, then dry=false
```

Rehearsed 29 Sep: the four approved ws.regulab posts from Fri 21:00 to Sat 21:00 had their cards hosted in
`argus-cards` (`673b228`), all four md5-proven, one message of 20.5k characters.

`DIR` is an **empty** folder the Studio `drafts` (date ≥ 27 Sep) and their cards were read into with `out_dir`.

**Why from 27 Sep and not only Friday night.** The 27 Sep import brought Studio's queue over as drafts, and Studio kept
moving posts after that. The 29 Sep rehearsal found one: Semasa's copy of `k1pju7557n` still sat on Fri 2 Oct 21:00,
while Studio had moved it to Thu 1 Oct 21:00 and put it in Buffer. Re-importing everything since 27 Sep brings every
copy up to date on the same ids: what Studio already put in Buffer arrives `scheduled` and is never sent again (the
tally marks it posted); an approved post whose slot has passed is overdue and waits for Wan, never fired late. Only
a post from Friday 21:00 on is actually sent by Semasa.

## Why nothing is sent twice

- **Buffer**: before creating, the publisher looks for a post on that channel with the same first 100 letters within
  ±36 hours and **adopts** it instead. A post Studio already put in Buffer comes over as `scheduled` with its Buffer ids
  and is never sent again.
- **LinkedIn**: the publisher writes a `sending` line before it calls Composio. A `sending` with no `sent` after it is
  marked *unconfirmed* and **never resent** blindly; Wan checks the profile.
- **The import** keys every post on the same id the 27 Sep import used, so running it twice changes nothing, and it
  never overwrites a post Semasa has already scheduled or sent.

## If something goes wrong

1. Semasa → Settings → Publishing → **Pause** (`publishing.paused = true`). This beats `enabled_from`.
2. Re-enable Studio's release Routine (`trig_01SemfrrqFRXZ2Jf4LVXuPJe`) only after pausing, never while Semasa publishes:
   one publisher per Buffer account and LinkedIn profile.

## What replaces Studio's three source-reading duties (added 30 Sep 2026)

Wan: *"port all three before Friday"*. They run from `sources.yml` (05:10 and 17:10 MYT, also woken by the database) through
the Composio For You key, and they only ever write FEED ROWS in `semasa_watch` (`backend/semasa/intake.py`). Nothing drafts,
approves or posts; a click on "Jadikan idea", or autofill from Fri 20:00, still ends in a draft that waits for Wan.

| Studio Routine duty | Semasa | Tab (Isu semasa row) |
|---|---|---|
| Ideas sweep, Reddit pass (`REDDIT_SEARCH_ACROSS_SUBREDDITS`, r/malaysia, ranked by comments) | `community.py` | Reddit |
| Ideas sweep, YouTube pass (`YOUTUBE_SEARCH_YOU_TUBE`, real view counts) | `community.py` | YouTube |
| Nightly drafter §2, OneDrive `/40. HERMES` folders (+ `urgent post/DDMMYY`, + LabMuffin "Post Matrix") | `folders.py` + `autofill.py` | OneDrive |
| "Cosmetic Reg Daily Sweep" reader (MYRA's sheet, read only) | `myra.py` | MYRA |

Needs `supabase/024_sources.sql` once (four new sections, the twice-a-day clock, the "Sweep now" trigger). Until it is run,
`SOURCES_DRY=1` reads and judges everything and stores nothing, and a real run stops with "024 has not been run".

Known limits, so they are not discovered on the night: YouTube search runs on Composio's SHARED Google project, whose daily
search quota was already used up on 30 Sep (the sweep reports it and Reddit carries on); `sains_kosmetik` has no folder (as
in Studio) and is fed by the Latest publications tab; what the writer is sent from a OneDrive file is at most 12,000
characters with e-mail addresses, phone numbers and company names masked, and `sources.folders.use_writer: false` stops it.

## Routines after cutover (8 → 2)

| Routine | Fate |
|---------|------|
| Studio release + ideas sweep `trig_01SemfrrqFRXZ2Jf4LVXuPJe` | disabled Fri 19:45, deleted with Studio |
| Studio sweep reader `trig_01RbfY71f5Dbux1UehkLiwQs` | same |
| Studio nightly drafter `trig_016adwzHAbVCnzW3RGeiawsU` | same (Semasa's autofill takes over, same `enabled_from`) |
| Studio link `trig_01Nu26P8gBCt23h7B6KbvfYy` | same; `STUDIO-LINK-ROUTINE.md` marked RETIRED |
| Semasa bug scan | deleted after a clean weekend |
| MYRA check-in (one-shot) | ends by itself |
| MYRA daily log, KKM Targets | kept |

Semasa's own schedule lives in GitHub Actions (`publish.yml`, the sweeps, autofill), not in Routines.

## Saturday

Backup zip of Studio's whole store goes to Wan first. Studio's artifact is deleted **only** on Wan's confirmation.

## What the 2 Oct run taught (added the same night)

- **Delivery of the import.** `studio-import.yml` takes the posts as one pasted input of up to 65,535 characters, and four
  messages were ~190 KB. Retyping that through a chat cannot be proved byte for byte, so the session committed the four
  files to a throwaway branch (`cutover/studio-import-1002`, never merged: it holds caption text) and dispatched the
  workflow from that branch with `posts` set to the file name. A branch run uses that branch's `studio_import.py`, which
  reads `ops/import/<name>` when the input is a `.json` file name. Dry first, then real, one dispatch at a time: the
  `studio-import` concurrency group keeps one pending run and cancels any extra.
- **The importer wrote the picture before the post.** `media_generations.post_id` has a foreign key to the post, so the
  first post the 27 Sep import never created failed the whole run (nothing written). Post first, then the picture, and a
  test pins the order.
- **`host` now also covers `posted` drafts, and `build` tolerates a posted picture with no bytes** (an Unsplash pick):
  the first is public already, the second is history and has nothing to prove against.
- **A "clash" in the dry run can be a post in another message.** The check looks at every Semasa post on those dates that
  is not in THIS message, so a Studio post that moves date in message 3 (k1pju7557n) shows as a clash in message 4.
  A clash with a post whose id is not a Studio id is the real one.

## One post to a slot, the same words never twice (added 3 Oct 2026)

Wan: *"allow us to drag and drop the post to dedicated time … make blocker to avoid duplicate post to be posted, and more
than 1 post in 1 slot"*. Three layers, one rule, so a gap in one is not a gap in the post:

- **Page** (`web/src/lib/slots.js` `moveCheck`, `duplicatesOf`): the schedule map moves a draft or approved post by drag or by
  grip-then-click; a held, past, off-day or foreign slot is refused with the reason, and the slot is re-read from the database
  first. The editor will not approve onto a held slot or with words another approved, scheduled or posted post already carries.
- **Database** (`supabase/026_slot_and_duplicate_guard.sql`, run once in the KPI project's SQL editor): the same two refusals
  for a signed-in browser. A clash that already exists is not touched (editing its words still works; approving it does not).
  The importer, the worker and the publisher write with the service key and are never stopped here on purpose.
- **Publisher** (`backend/semasa/guard.py`, no SQL needed): of two approved posts on one slot, or carrying the same opening
  words within 90 days, only the one that outranks the other is sent (already scheduled or posted, then half-sent, then
  approved first). The other is logged `blocked`, shown on its card, and goes when the other is moved or rejected.

The caption key (first 120 letters and digits, case and punctuation ignored, in the language sent) is the same in all three;
`rules/caption_keys.json` is run by both test suites.
