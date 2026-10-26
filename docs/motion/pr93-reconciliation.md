# PR93 reconciliation with merged PR94 and PR95

## Outcome

PR93 starts this reconciliation at `f451ddb015cbe68383992678e3e6424df3135c5c`, which already integrates PR94/main `c4547b72153f3a88a5dd1220b8147b50a4ab2db8`. The clean starting worktree was protected by local backup `backup/pr93-pre-pr95-f451ddb`. Merged main snapshot `c4a52e9081b6c3b9fa921225ef831ead97e71527` incorporates independently merged PR95. This is a branch reconciliation, **not a GitHub PR merge or deployment**.

All three PR95 conflicts are combined deliberately, not resolved by replacing files wholesale:

| File | Combined contract |
| --- | --- |
| `web/src/lib/motion.js` | Idea/post rows remain `waiting`; direct form remains `pending`. Waiting-row deduplication retains PR95's one queued row per idea, while started variants retain format/mute/avatar checks. Queue hydration/start preserve policy, Wayne/Osman defaults, explicit overrides, evidence, personal identity, design, mute and avatar. Mode/language edits normalize at start. |
| `web/src/components/MotionLab.jsx` | Retains queue-first controls, start/start-all/remove, lazy effect library and actual applied-style report, alongside PR93 actual voice/timing and provenance report. |
| `web/motion.test.mjs` | Expected rows combine `waiting` with normalized PR93 policy fields; new PR95 queue assertions use approved male defaults/Osman fallback rather than stale Kitten/female defaults. |

Queue adds the same format selector as the direct form, including an explicit way to re-enable narration after silent-first. PR95's SQL migration is imported unchanged; this task does not apply or independently verify the live migration. Existing worker `pending`-only claiming remains tested.

PR94 gradients/no circles, four format skills, minimum 15 selected styles, plain-HTML writer, persistent native headings and both `design`/`worker_captions` arguments remain. PR93 transparent worker-owned actual-word versus estimated-phrase captions, Continuous Line fail-closed behavior, source-footage rejection, reading-paced silent narration, normal-rate Wayne/Osman and explicit voice overrides remain. Selected-style counts are not proof of 15 visually realized effects.

## CTA correction

The user confirmed the previously approved full gimmick phrase: **`Stay tuned. Follow us for more.`**. Prior claims that “Stay tuned only” was latest authoritative intent were incorrect. Policy JSON, backend CTA/prompt, general motion skill/resolver/contract, tests and authored smoke runner now use the full phrase, matching PR94's unchanged gimmick skill. The CTA remains inside the same persistent composition, never a separate outro. Long EN/BM and personal LinkedIn CTAs are unchanged.

Observed regressions fail before implementation for backend CTA, skill resolver CTA, and queue hydration losing format/mute/avatar. New `web/motionQueuePolicy.test.mjs` exercises both idea/post → waiting → form → start for silent, gimmick and bilingual formats, plus personal English/portrait identity, evidence, design, explicit female choice and variant matching; it is part of `npm test`.

## Verification on the combined tree

- Full backend: **912 passed, 19 skipped in 81.32s**. `/opt/data/cache/scratch/pr93-pr95-backend.log` and `pr93-pr95-tests.xml`. Unavailable configured Chrome and optional openpyxl paths remain skipped.
- Focused voice/alignment/PR94 integration/queue-worker/style suites passed, with one unavailable-Chrome skip.
- General motion skill contract: **8 passed**.
- Ruff backend + smoke script and `git diff --check` passed.
- Full web `npm test` including new queue-policy coverage and production build passed. Existing fflate/chunk-size warnings remain.
- No change relative to main in PR94 `motion_auto.py`, `native_text.py` or `llm.py`.
- Exact pushed-head CI, latest main and mergeability are read afresh and recorded in the PR comment; historical green checks are not integration evidence for a moving base.

## Merge held: generated-media acceptance remains unresolved

**Actual LLM-generated voiced films in both approved designs have not been produced/accepted on this combined tree.** Prior real Wayne/Osman MP3 samples, authored silent/gimmick strict-render fixtures and isolated worker tests are separate evidence, not generated voiced end-to-end acceptance. The existing smoke runner explicitly authors silent/gimmick HTML and cannot establish that gate; changing its fixture text is not a new render. No writer/provider call is made here to manufacture evidence. A verified permitted writer/runtime path plus representative films, full decode/probe, frame review and EN/BM listening/editorial checks are still needed before the conditional merge can proceed.

Scientific accuracy, pronunciation, actual personal still approval and real stock/source rights remain runtime/editorial boundaries described in the matrix; optional avatar/clone/private music/Drive routes remain unconfigured or pending. No production DB write, migration execution, private upload, paid generation, Claude CLI/model call, HeyGen job, deployment, auto-merge or GitHub merge was performed.
