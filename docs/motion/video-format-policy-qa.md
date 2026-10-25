# Video-format policy QA and integration boundary

## Verified on this follow-up branch

- Local focused backend suite: **135 passed**, including real JS form/idea/draft payloads through worker orchestration (24 configurations), policy, captions, source ownership, existing asset/style/native roadmap and voice tests. Writer/TTS/renderer/storage in these worker tests are explicit doubles.
- Backend Ruff and `git diff --check` passed. Added-line static scan found no quoted credentials, shell=True, eval/exec or pickle deserialization. The new personal still path reuses creator-owned private asset validation, rights and exact size validation, then verifies an actual decodable image. No independent reviewer was run; PR review remains necessary.
- Full local npm test and production Vite build passed. Existing fflate static/dynamic import and large-chunk warnings remain.
- Full remote CI at code head `29ea5fb0ee7a77c0f8815b062eba03497eac574a`: **879 passed,18 skipped**, Ruff passed, web tests/build passed. Runs `40216940667` and `40216944158`. Later security-only validation tests require a fresh final-head CI check; the PR body records that result.
- An earlier full local backend run finished with **828 passed,18 skipped,1 failure**: an old exact gimmick CTA assertion omitted the newly required final period. It was fixed and the focused suite and full CI subsequently passed. Do not describe that earlier local run as green.
- Two actual offline authored fixtures rendered with cached HyperFrames0.8.188: silent-first **30s** and single-composition gimmick **10s**, each **1080×1920**. Real approved soundtrack mix and half-size **540×960** preview encode passed; all four files fully decoded. No writer/TTS/stock/personal-media calls in this smoke. Command: `python ops/smoke_video_formats.py --cli <existing cached cli.js> --gsap <existing gsap.min.js> --output <qa directory>`.
- Local evidence: `/opt/data/outputs/video-format-policy/qa/results.json`, fixture `input-row.json`, HTML and render logs, masters/previews, extracted frames and `contact-sheet.jpg`. Visual inspection of the sheet confirmed readable unclipped text, stable gimmick composition at0.5/5/9.5s, and the silent standalone official alpha logo/CTA page. These are authored renderer fixtures, not an all-format end-to-end generated-video claim.
- Registry-derived snapshot, not a promoted readiness claim:99 IDs,90 `fallback`,5 `ready`,2 `manualasset`,2 `autoasset`. Imported titles/occurrences/source files were not rewritten.

## Concurrent upstream integration is still required

This task started from PR80 `acaf09d` above PR79 and merged then-current main `4b38bc2` locally to preserve its voice fixes. During execution, **other workstreams merged PR79/80 and PR84/85/87/88/89**. Freshly fetched main is now `a822929`. The follow-up must therefore be based on **main**, not the now-merged dependency branch.

**Do not merge this draft as if it were integrated with those newer changes.** Current main changes the worker's signatures/orchestration, caption ownership/layout, automatic photos/effects, fitting behaviour, and provider/tempo rules. Those are meaningful policy changes, not a mechanical base rename. They were not overwritten or reset by this workstream. A subsequent integration must reconcile them with the [requirements matrix](video-format-policy.md) and obtain the actual latest user direction where requirements conflict.

In particular:

- PR84 sentence-span word spreading is explicitly **mouth timing only**. It must not feed this branch's `actual-word` caption path. Carry an explicit timing provenance flag or retain phrase captions whenever word alignment is estimated.
- Current-main voice code now describes brisk English×1.15/BM×1.25, Kitten atempo1.0 and a disclosed Google fallback, whereas the task handoff specified approved English~154wpm and BM+15%. Do not silently decide which newer user instruction wins solely from a code comment.
- Current-main PR85 adds automatic Unsplash sourcing; this branch's matrix describes the capability state of its own tested base. Preserve real license/provenance sidecars and do not replace the new source integration with the older unconfigured status when integrating.
- Current-main safe-layout/pacing and writer corrections must coexist with silent reading budgets, exact brand/personal endings, no duplicate subtitles and the two preserved designs. PR90 is a further open overlap/reference-layout workstream and was not modified here.

No PR was merged, no deployment/migration was applied, no paid calls were made, and no other worktree or SadTalker/model installation was touched. Real English/BM narration, actual personal still approval, licensed-stock generation, talking-avatar, clone and Drive archive are not claimed verified by this branch's offline smoke.
