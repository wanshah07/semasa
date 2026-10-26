# PR93 reconciliation against current Claude Code work

## Scope and decision

Rechecked live `main` at `f48093bb46afff4e4f6449da15e9c14b6d7769b9` and PR93 at `684f0805227db2165ac2e16474e6a2ea9d785205` before this incremental correction. Main has not advanced since PR92. No existing local changes were present. No merged Claude work was reverted. Only PR93 is authorized for conditional merge; no other PR is merged by this audit.

**Hold merge:** generated voiced acceptance in both approved designs remains unverified. Existing real Wayne/Osman synthesis samples and authored silent/gimmick renderer fixtures are different evidence, not generated voiced end-to-end films. Do not replace that gate with unit-test doubles or a green CI claim.

## Latest parallel Claude work

Open PR94 (`fix/motion-native-heading-stays`) advanced during this audit from `9f3fd02e44eba746bf8351efe261f19214e5e32b` to **`d2acc3ce1c4fdb05e3dce6c50126b6ab1ce30980`**, while main stayed unchanged. It introduces plain-HTML writer responses with JSON compatibility and retained native headings. The new commit also implements gradient/no decorative circles, four format-specific skills/reference films, and a minimum of 15 selected styles per film. Its body reports run-40 JSON writer failures in both films. The Idea → queue → choose styles → render flow remains deferred there and would need a database `waiting` status; no migration is applied here.

The initial non-mutating merge-tree against `9f3fd02` was textually clean. **The refreshed merge-tree against `d2acc3c` has content conflicts in `backend/semasa/motion.py` and `backend/semasa/motion_layout.py`.** These are real parallel-contract overlaps (layout `design` versus `worker_captions`, plus worker fallback composition), not something to resolve by choosing one side wholesale. PR94's commits remain untouched on their own branch; they are not silently copied into PR93 or claimed merged. Per conditional authorization, hold rather than merge through uncertain alignment or discard newer Claude changes. PR93's Continuous Line fail-closed guard must remain; successful real writer output is an important integration gate. Recheck latest main and PR94 status before a future merge.

## Correction made here

Latest explicit gimmick CTA is **`Stay tuned` only**, in the same persistent composition. The prior PR93 suffix `Follow us for more` contradicted that rule. A regression test was observed failing before the correction. Backend CTA/prompt, shared policy, skill resolver/contract, tests and fixture runner now agree. Approved historical reference HTML/media are preserved, not rewritten to masquerade as new evidence. Existing rendered fixtures still contain the superseded CTA and are not new-head visual proof.

English Wayne `en-SG-WayneNeural`, Malay Osman `ms-MY-OsmanNeural`, normal tempo/pitch, explicit female/English Kitten overrides, silent-first versus mute-all, true-word caption provenance, personal LinkedIn identity, entrypoint policy, and existing photo/layout/re-record features are retained.

## Verification and earlier failure investigation

- Earlier `backend-full.log` exit 1 was real: four assertions in `test_style_bundles.py` expected old CTA punctuation. The subsequent committed assertions match approved BM punctuation, and current focused/full runs pass. This was not ignored on the strength of CI.
- New regression: failed as expected on `Stay tuned. Follow us for more.` versus `Stay tuned`; corrected focused suite: 23 passed.
- Full current working-tree backend: **862 passed, 19 skipped**, 77.70s. Skips: unconfigured Chrome routes and missing optional openpyxl. Log: `/opt/data/outputs/semasa-voice-alignment/reconcile-backend.log`.
- Skill contract: **8 passed** after installing PyYAML in the existing scratch virtualenv. Initial attempt could not import yaml; no repository dependency was silently changed.
- Full `npm test` and production build passed after `npm ci` restored missing local dependencies. Initial test attempt failed because local `fflate` was absent. Existing fflate chunk and bundle-size warnings remain.
- npm audit reports 7 dependency vulnerabilities (4 moderate, 3 high); dependency declarations and lockfile are unchanged from main (PR93 only extends the package test script). No unrelated dependency upgrade was forced. Audit: `/opt/data/outputs/semasa-voice-alignment/reconcile-npm-audit.json`.
- Ruff backend/smoke and `git diff --check` pass. Exact pushed-head CI must be read separately after this commit; earlier CI for `684f080` does not verify this correction.

No production database write, migration, private upload, paid provider request, Claude CLI/model call, clone, avatar resource job, deployment or merge was performed. Optional deployment configuration gates remain distinct from the generated-film acceptance gate above.
