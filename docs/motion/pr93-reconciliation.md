# PR93 reconciliation with merged PR94

## Outcome

Merged current `origin/main` **c4547b72153f3a88a5dd1220b8147b50a4ab2db8** (PR94) into PR93's branch, starting from **5c4cb069e74df6c52455b76f96a89e572e188aa2**. The initially clean worktree was protected with local backup branch `backup/pr93-pre-pr94-5c4cb06`. This is a branch reconciliation, **not a GitHub PR merge or deployment**. No other PR is in scope.

Both actual conflicts were resolved by combining the contracts, not taking either file wholesale:

| Conflict | Combined implementation |
| --- | --- |
| `backend/semasa/motion_layout.py` compose signature | Accept both PR94 `design` and PR93 `worker_captions`; retain design normalization and PR94 gradients. |
| `backend/semasa/motion.py` fallback call | Pass both the selected design and `worker_captions=True`; preserve PR93's Continuous Line fail-closed guard before fallback. |

PR94's four format skills/reference films, minimum 15 selected styles, plain-HTML writer/legacy JSON compatibility and retained native headings remain. PR93's transparent worker-owned captions, actual-word versus estimated-phrase provenance, Wayne EN/Osman BM defaults, normal rate/pitch, explicit voice overrides, personal identity, preview/provenance and source-audio safety remain. The 15-style selection floor is not proof of 15 visually realized effects in a generated film.

## Merge remains held: two distinct gates

1. **Actual generated voiced acceptance in both approved designs remains unverified.** Earlier real Wayne/Osman samples, authored silent/gimmick render fixtures and isolated worker/LLM tests are not generated voiced end-to-end films. No paid writer call or live database write was used to manufacture acceptance evidence.
2. **Gimmick CTA source conflict needs confirmation.** The earlier reconciliation incorrectly characterized `Stay tuned` only as an established latest explicit user rule. Available PR94 source, `.claude/skills/ws-regulab-motion-gimmick/SKILL.md`, explicitly specifies **`Stay tuned. Follow us for more.`** inside the persistent scene, while existing PR93 policy/backend/tests specify **`Stay tuned`** only. PR94's body describes four new reference films but does not establish a later user instruction removing Follow. The original user context also included Stay tuned plus follow. This conflict is therefore unresolved, not a verified latest-wins rule. This reconciliation leaves both source versions intact and does not silently overwrite Claude's format skill or invent a new restriction. Confirm the exact wording, then synchronize policy, worker, tests and skill before merging.

The earlier PR comments and prior version of this document describe historical snapshots; they must not be read as proof that the CTA was confirmed or that integration was tested before this reconciliation.

## Verification on the combined working tree

- Added `backend/tests/test_pr93_pr94_integration.py`: both layout arguments work together for each design, actual-word chunk endpoints are retained, safe layout does not duplicate worker subtitles, and the worker's voiced fallback passes both arguments and saves the gradient composition. These are explicitly fixtures, not generated-film acceptance.
- Focused integration/voice/video/auto suites passed (one unavailable-Chrome skip).
- Full backend: **911 passed, 19 skipped in 77.80s**. Log: `/opt/data/cache/scratch/pr93-pr94-backend.log`. Skips cover unconfigured Chrome routes and missing optional openpyxl.
- Ruff backend passed. Full web `npm test` and production build passed; existing fflate/chunk-size warnings remain.
- No source change to PR94 `motion_auto.py`, `native_text.py`, or `llm.py` was needed beyond importing main unchanged.
- Exact pushed-head CI and fresh remote head/base/mergeability are recorded in the reconciliation PR comment, not inferred from historical runs.

No production database write, migration, private upload, paid provider request, Claude CLI/model call, avatar job, deployment or GitHub merge was performed. PR95 and other branches remain untouched.
