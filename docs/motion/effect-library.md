# Effect library and asset preparation

The Motion form now keeps the approved design variant and complete attachment recipe separate from individual effects. Existing defaults (portrait, English, 30/60-second explainers, explicit 10-second teaser, existing voice/music/CTA rules) are preserved. The form previously omitted its selected `design` when submitting; this is now passed through too.

## Selection

- **Auto (recommended)** is the default for new form, idea and draft jobs. The worker chooses a small deterministic compatible recipe: a qualitative icon-flow illustration (`B04`), or calm abstract illustration (`B08`) for calm/abstract/ambient briefs; a supplied sourced screenshot takes priority (`P01`). Explainers add the conservative prepared-panel push (`M03`); teasers use only the visual. This supplements the existing complete Hook → Fact → Why → Solution recipe, not 99 simultaneous effects.
- **Manual** adds/removes cards and supports an empty selection. Editing any recommended card switches to Manual. The selected tray remains visible while filtering/searching. Save-defaults preserves selection policy and IDs, **not attachments from a previous job**.
- `effect_mode` controls selection. `asset_mode` remains separate (`auto`, `manual`, legacy `mixed`). New browser jobs specify both. Legacy queued jobs with no effects keep their original composition; legacy explicit IDs are respected.
- Original document sections, order and duplicates are recovered by `ops/import_effect_sections.py`, with a source DOCX hash in `rules/motion/effect-sections.json`: 99 unique IDs and 106 occurrences. The original repeated H06 is not silently renamed.
- Card thumbnails are self-authored **illustrations, not effect demonstrations**. Required assets and actual adaptation limitations are exposed on each card.

## Actual readiness, not prompt promises

`rules/motion/effect-adapters.json` is the worker's explicit capability registry:

| State | Count | Implemented behavior |
|---|---:|---|
| `ready` | 1 | M03 slow push on a prepared panel, not source-video camera editing |
| `autoasset` | 2 | B04/B08 original neutral vector with restrained movement, not transcript-aligned footage |
| `manualasset` | 2 | P01/B02 supplied sourced-screenshot panel adaptations; B02 is a single-card adaptation, not a full multi-card system |
| `fallback` | 94 | Explicit generic concept adaptation, **not the requested source-editing technique** |

A missing screenshot also becomes a declared fallback. The worker writes real local prepared files and `asset-plan.json`, injects a deterministic first-scene panel, adds animations to the registered timeline, and stores the plan in the job check report. The form's result card exposes those actual readiness reasons. Multiple manual effects share that one panel, not separate source-editing passes. No screenshot/chat, chart data, product, real footage, voice clone or evidence is fabricated. This is not a claim that all 99 original techniques have been implemented.

## Optional uploads

The UI uses the existing Supabase storage client, with a **new private bucket** rather than the existing public reference bucket. Apply `supabase/048_motion_assets.sql` separately to provision `semasa-motion-assets`; it was **not applied** by this change. Auto vector jobs do not need the bucket. Without it, manual upload reports the storage error and does not silently fall back to public uploads.

- At most eight files, each 1 byte–20 MB. Allowlisted MIME + extension + safe filename. PNG/JPEG/WebP images, MP4, MP3, WAV, PDF and UTF-8 plain text only.
- Explicit self-owned/licensed rights; screenshots require original-source metadata. No credential or public/signed URL is placed in job options.
- Browser storage policies use the existing uploader allowlist and creator UID folder. Worker independently validates owner/path, size, MIME/extension, rights and image bytes, then decodes/resizes/re-encodes images to safe local PNG files with a pixel limit and SHA-256 provenance.
- Video/audio/documents are validated and retained as reference files only. Their actual editing/extraction is **not supported**, and the plan says so. A document upload does not become invented evidence.
- Detach removes a reference from the current form, not a previously queued job's file. It does not delete shared uploaded files out from under an existing render. Storage retention cleanup remains a separate operational task.

## Verification boundaries

`npm test` includes selection/default/entrypoint tests and isolated storage-client tests. Backend tests prepare and decode real image files, reject invalid refs/MIME/ownership, regenerate section provenance and exercise `motion.process` through its existing renderer double. They do not claim a live Supabase upload, external writer response, VoiceStudio invocation or full HyperFrames MP4 acceptance run.

A local isolated browser harness rendered the actual component with 106 cards and the Auto tray. Screenshot capture subsequently timed out and the browser backend could not restart; no successful visual/mobile interaction audit is claimed. The harness is not included in the repository. The normal production Vite build succeeds. Repository-wide TypeScript checking reports existing errors in unchanged `ui/chart.tsx` and `ui/app-1.tsx`; CI currently gates web tests and build, not that typecheck.
