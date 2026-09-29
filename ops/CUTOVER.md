# Cutover: ws.regulab Studio → Semasa (Friday 2 Oct 2026)

Wan, 29 Sep 2026: *"we will start using semasa this friday and will delete ws.regulab studio permanently … all post from
friday night move to semasa … 100% functioning without wait my approval on friday night"*.

"Without my approval" means the **cutover** runs with nobody at a keyboard. The **per-post Approve gate stays**: a post
Wan approved in Studio arrives in Semasa already approved; a post he had not approved arrives as a draft and waits.

## Before Friday (Wan)

| # | What | Where |
|---|------|-------|
| 1 | `BUFFER_API_KEY` secret | publish.buffer.com/settings/api → GitHub → semasa → Settings → Secrets → Actions |
| 2 | `COMPOSIO_API_KEY` secret | Composio dashboard → Settings → API Keys → same place |
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
