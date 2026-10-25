# Native text batch 1 — implementation and local evidence

## Delivered scope

Dependent on PR79 at `f5e6fb4e23ae17ec1a6cba3f8d8bc97108718931`; new branch, no changes pushed to PR79. No merge, deployment, migration, production queue/storage write, paid voice API or new heavy installation.

The frozen inventory contains **94 unique baseline concept fallbacks**, across all **11 exact source section titles**, retaining all memberships/occurrences, original requirements/fallback text, duplicates and missing H07. Classification: **6 core-renderer candidates** (four delivered limited text adapters, V10 deferred, V08 has no original required assets) and **88 needing assets plus native core work**. These tracks are not claims of full source-technique readiness.

Four deterministic **authored-heading-only adaptations** were implemented and actually rendered:

| ID | Native operation | Eligibility / boundaries |
|---|---|---|
| H01 Headline Slam | Scale 2.2 → 1 with back-out and fade exit | Existing first-scene heading, at most five words; no invented headline, footage shake or motion blur |
| H03 Question First | Existing words rise/fade in a bounded visual stagger | Existing first-scene question ending `?`, at most twelve words; no fabricated question, dimmed footage, wipe or speech-alignment claim |
| V01 Kinetic Section Title | Existing heading rises through a local overflow mask | At most four words; no invented chapter number, additional heading, full-frame scrim or source edit |
| V03 Keyword Spotlight | Existing short heading scales into an outlined frame | At most three words; no arbitrary transcript keyword extraction, background blur/dim or claimed word sync |

These are native deterministic **text animations**, not equivalent to all steps of the original footage techniques. The five existing prepared-panel/vector/screenshot adaptations remain unchanged; **90 baseline concept fallbacks remain unimplemented**. V10 is deliberately deferred: its source describes 3 seconds overall but also ≥3.3 seconds of hold after the last phrase. Original source text and this conflict are preserved rather than silently repaired.

## Runtime path and safeguards

Actual gallery card choice → React state → existing `motionRow` manual payload → real backend `motion_assets.prepare` → `motion_assets.inject` → `native_text.inject` → effect-specific registered GSAP timeline → actual HyperFrames MP4 encode.

The native layer transforms an **existing matching semantic h1/h2/h3** rather than adding text. Scene-ID scoping is preferred; ambiguous/missing/ineligible headings are skipped with an explicit per-job fallback reason. Conflicting opening effects do not stack; later visual effects use non-overlapping scene windows. No brand-outro transformation. The worker persists the resolved cue/readiness in `asset-plan.json` after composition, including repair attempts.

The adapters preserve heading copy/language, existing position/base design and inline emphasis. They do not move captions or add background panels. H03's stagger is purely visual, not karaoke or fabricated speech timing. Supporting captions, design selections, style recipes, language/CTA logic, logo alpha asset and soundtrack preferences are unchanged. Auto recommendations remain the existing conservative recipe; selecting these four is Manual. The generic source-editing fallbacks are unchanged.

## Executed local verification

- Test-first failures observed for missing H01 renderer; missing H03/V01/V03 renderers; worker persistence of resolved cues; preservation of H03 inline emphasis; ambiguous heading handling. Each subsequently passed.
- **71 targeted backend tests passed**, including motion worker, asset safety, source sections, recipes/design/language constraints, roadmap and native tests. `ruff check .` passed for the backend. Full local backend suite is not claimed; full-suite verification is delegated to the PR's CI checks.
- Full `npm test` passed with the new four-ID manual queue/policy assertions. `npm run build` passed; existing fflate import/chunk-size warnings remain. A 90-second build attempt timed out; retry with a sufficient budget completed in 3m31s.
- Real React gallery in a local Chromium harness: **8 selection-to-payload flows** (four IDs on desktop 1440×1000 and mobile 390×844); zero page errors, no document horizontal overflow. These are local component checks, not authenticated live-app acceptance. The selected rows were saved and consumed by the real backend render smoke.
- Real cached **HyperFrames 0.8.188** rendered **four 2.000-second** videos using `--strict --no-best-effort --workers 1 --low-memory-mode`. FFprobe verified each at **1080×1920, 12fps, 24 frames**. Full FFmpeg decode passed for every file. Software screenshot capture was used (WebGL unavailable); no renderer double substitutes for this evidence.
- Inspected final encoded contact sheet at 0.12/0.6/1.4 seconds for all four IDs: no visible text clipping or caption overlap in these fixtures. H03 shows staggered words; V03 has an outlined box/fade; H01 and V01 show bounded transform entry. This does not certify arbitrary future writer layouts or source footage.

## Evidence and reproduction

Local evidence root: `/opt/data/outputs/native-effects-roadmap/`.

- `inventory.json`, `checklist.md`: the full baseline cohort, mirrored in this repository directory.
- `qa/render-results.json`, `{H01,H03,V01,V03}.mp4`, `qa/contact-sheet.jpg`, per-ID frames/logs/projects/asset plans.
- `qa/browser-results.json`, `qa/selected-rows.json`, `qa/harness.jsx`, `qa/browser-qa.mjs`, eight selection screenshots.
- `qa/backend-tests.log`, `qa/web-tests.log`, `qa/web-build.log`.

```sh
python3 ops/native_effects_roadmap.py --output docs/motion/native-effects-roadmap
python3 ops/smoke_native_text.py \
  --cli /path/to/existing/hyperframes/dist/cli.js \
  --gsap /path/to/existing/gsap.min.js \
  --rows /path/to/selected-rows.json \
  --output /path/to/local/qa
```

The render script requires an existing HyperFrames installation and local GSAP, not an install/download. `--rows` is optional; supplied browser rows retain their original video defaults while the representative test composition is explicitly two seconds. No personal selfie/source media is committed. No LLM/TTS, live private uploads, full narrated films, source footage editing, masks, screenshot authenticity or commercial soundtrack licensing is proven by these local tests.
