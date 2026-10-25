# Approved design references — preserved independently

These HTML files are **inert visual authoring references**, read into model prompts, not runnable standalone production projects. They intentionally retain original asset paths and old durations/wording as provenance. External assets, narration, image licenses and GSAP are not bundled here. Current worker policy overrides old sample captions/timing/audio. Never reuse the sample paper/ingredient claims as evidence for an unrelated brief.

| Repository reference | Approved local source | SHA-256 |
| --- | --- | --- |
| bright-editorial-reference.html | motion-v15/english-new-style/index.html | d7d33f1841d621629ce5ddf7e5ab0a89a13cf5bd2d8727a81017e43384aa4f4a |
| bright-bm-reference.html | motion-v15/malay-voiced/index.html | 8c297133b5a663109fa128318ed58005ec3a7618289adede5433f2429e871289 |
| bright-silent-reference.html | motion-v13/silent-first-30s/index.html | 064da0e0fb2abc51d82db45d0094e5aaa012a01f24d0603fd9f014418582ca9d |
| bright-gimmick-reference.html | motion-v13/gimmick-single-scene-10s/index.html | e018efe3a6de55559db433090292b60b3fd6bb2f7b3317d6bdcb287816a213f3 |
| continuous-line-reference.html | motion-v16/continuous-line/index.html | 15f660f60da5d147c71e317911f85a3acd51569acfecdca4ba92d95ef2edc121 |

The first four preserve Design 1, not superseded by the fifth (Design 2). No approved original output was changed. Local sources resolve beneath `/opt/data/outputs/` on the approval host, not a portable project path. Long-video brand logo is the original transparent-alpha PNG in the parent directory; it was byte-compared to `/opt/data/outputs/motion-v6/brand-assets/official-logo-transparent.png`.

## v17 approval and reproduction settings

Approved artifact: `/opt/data/outputs/motion-v17/preview.mp4`.
SHA-256: `8745e9f1e641d82b73fcd1c618f2efc9f6d276cdac2cc79cd90db91a6fe5c453`.
Verified with ffprobe: native 540×960, 24 fps, 694 frames, 28.916667 seconds. This is a preview, not the requested native 1080×1920 production final.

v17 reuses Design 2's v16 encoded picture and separate narration/music stems. Approved changes: picture time and narration slowed to 90% of v16, music bed gain ×0.45 (roughly −7dB relative), voice gain ×0.9. English active-speech target about 154 rather than 171 wpm. Preserve pitch using FFmpeg `atempo`, never waveform sample-rate reinterpretation. Do not restore v16's faster pace or louder bed.

A reconstruction from the retained original stems uses the following filter relationships (not a byte-identical archival rebuild command):

- picture `setpts=PTS/0.9`, at the original 24 fps;
- narration `atempo=0.9,volume=0.9`;
- music `atempo=0.9,volume=0.45`, retaining existing speech duck/fades;
- `amix=inputs=2:normalize=0`, then inspect/master loudness and true peak before encoding AAC/H.264;
- verify full duration and final official-logo page before applying any `-shortest` option.

For a source-picture regeneration on the original host, retain `/opt/data/outputs/motion-v15` and `/opt/data/outputs/motion-v16` asset links and use v16's `build.py`, `render.py`, then `verify.py`; the last step performs mastering. **That regenerates v16, not v17; apply the approved v17 time/mix relationships afterward.** The copied `v16-README.md`, provider JSON and script text document those prerequisites. They are historical references, not a claim that their absolute paths exist on a production worker.

For newly generated native English jobs, VoiceStudio adapter uses native 1.50 and pitch-preserving 0.936 (= v16's 1.04 × 0.90). Measured phrase duration drives timing; never guarantee identical words-per-minute for different text.

## Audio rights and distribution

Wan's preferred preview soundtrack is the supplied reel (`v16-AUDIO-LICENSE.md` records provenance). `rights_status=unverified`, `preview_only=true` until actual license evidence. User preference is not overridden, but no raw/derived Instagram audio is committed here, auto-downloaded or marked commercially cleared. Only private approval uses the retained local reel excerpt. Public export stays on approved self-owned piano unless the user supplies license evidence or chooses the platform-licensed-audio route. Absence of the local reel source must not break cleared exports.

The native worker remains model-authored HyperFrames + GSAP, not a template clone of these approved manual previews. Both prompts consume the selected design/reference; model output still requires visual/listening review.
