# Motion: approved designs, attachment recipes, and rollout

## Two designs, not a replacement

`options.design` is independent of `options.style` (the editing recipe):

1. **Design 1 — Original Bright Photo / Diagram / Editorial** (`bright-editorial`, default). Preserve the approved v9–v15 English, silent, BM and single-scene gimmick family. Bright mint/cream, editorial hierarchy, real licensed photos when provided, qualitative diagrams, transparent centered/grid captions.
2. **Design 2 — Continuous Line** (`continuous-line`). Approved v17, derived from v16: one tall SVG world, a growing green thread and warm-gold pen marker, calm camera tracking, thin botanical/editorial lines and regular serif labels. Mask connectors beneath glyphs. Not disconnected cards. Design 1 remains available.

The form selector, saved defaults, direct idea composer, idea rows/bulk and post shortcuts save the design; both script and HTML worker prompts consume it. Visual reference HTML is kept in `rules/motion/designs/`. These are inert authoring references, **not a deterministic template renderer or proof that new model-authored output matches approved previews**. Worker tests exercise both design prompts/project writes with model/CLI/TTS boundaries stubbed. Real generated output still needs visual and listening review.

## Full attachment catalog

`rules/motion/attachment-reference.txt` preserves the entire source extraction. `recipes.json` retains source timings, primary/overlay/audio/global layers, order, requirements and provenance. Eight named sections represent seven distinct recipe bodies:

| Source section | Native availability / asset requirement |
| --- | --- |
| Viral Talking Head | Listed, disabled: original footage, authentic screenshots, licensed SFX/music; preserve original voice. |
| SaaS Product Demo | Listed, disabled: real website/UI captures and product photo; no invented interface. |
| Cinematic Brand Film | Listed, disabled: source footage/B-roll and licensed sound. |
| Financial Education Reel | Available educational adaptation: omit charts/counters without verified data, use qualitative diagrams. |
| E-Book Launch Trailer | Listed, disabled: actual PDF/document, product image, footage. |
| Tutorial / Screen Recording | Listed, disabled: actual recording/captures and speaker footage. |
| Client Testimonial | **Source duplicates Tutorial / Screen Recording. No distinct testimonial recipe supplied; never invent one.** |
| High Energy Promo | Listed, disabled: real footage/photos and licensed beat/SFX assets. |

Auto and Bright education are additional supported adaptations, not extra attachment sections. Rebuild metadata with `python ops/import_motion_recipes.py /path/to/attachment-text.txt` (original DOCX alongside). Attachment references never authorize executing Claude CLI/model calls or installing tools.

## Latest Wan requirements

- Default 30-second portrait explainer; optional 60 seconds. Final 1080×1920, 30 fps; approved reference previews 540×960 (manual v16/v17 references are 24 fps). Never silently upscale a reference preview and call it a native full-resolution final.
- Explain with **Hook → Fact → Why → Solution**: strong curiosity hook and connected complete casual sentences, not isolated headings. English or Malaysian Malay, never Indonesian.
- **10 seconds ONLY an explicit gimmick/teaser**, one persistent composition and curiosity hook. No compressed paper explanation, multi-page slideshow, or standalone logo/CTA page. “Stay tuned. Follow us for more” stays in that same scene. Legacy 10s defaults without teaser become 30s.
- Voice optional on/off, English/BM/both. One frontend resolver is used by direct/defaults/idea/post/bulk entry points: incompatible BM/both + Kitten becomes native Edge female. Backend protects legacy incompatible rows too; explicit `off` remains silent.
- English: actual configured VoiceStudio Kitten adapter, expr-voice-2-f, native speed 1.50 then pitch-preserving `atempo=0.936` (v16's 1.04 × approved 0.90), not the rushed v16 setting. Target approval approximately 154 active-speech wpm, not a guarantee for every generated phrase. BM/both: native ms-MY Edge +15%; never label it VoiceStudio. Say `pembungkusan` instead of the problematic spoken `label`. No ElevenLabs, cloning, Claude CLI or Claude model calls.
- Silent mode is **separately written reading-paced narrative**, not a muted transcript: complete sentences, roughly ≤2 visible words/sec including both languages. Worker clears teaching narration and enforces visible-copy minimum dwell; overfull jobs fail with duration/topic advice instead of accelerating speech. Keep captions transparent, no boxes/pills/scrims, consistent center/grid alignment, safe zones and 4.5:1 contrast.
- More than two citation authors: FirstAuthor et al. (year). Explain briefly what the publication studied/reviewed and why it supports the point. Use accessible evidence, never invented findings, quantities, screenshots, testimonials, product UI or efficacy. Ingredient role ≠ finished-product proof.
- Preserve source URL, reference URLs, source name, angle/domain, structured citations and origin IDs in `options.evidence`, separately from the truncated creative brief. Worker hydrates saved idea evidence before source reading. Reference URLs/metadata are not proof of their contents or an uploaded-media implementation.
- Real images require license/provenance; do not fabricate photos or evidence. Native upload/editing support is not added here; asset-dependent recipes remain disabled. No mascot by default; approved designs contain no mascot.
- Branding only on a separate final long-video page, supplied official alpha PNG centered, full tagline intact. English visible/spoken CTA: **Follow us for more**. BM/both: **Jangan lupa follow kami untuk tips seterusnya**. Worker reserves at least three seconds and extends when measured CTA/read time requires it, within selected total. Gimmick is the exception above.
- Music fades subtly and ducks under voice. Preserve approved v17 relative tuning: bed ×0.45 versus v16 (about 7dB lower), voice gain ×0.9, English pace ×0.9. These relative mix settings do not imply identical perceived loudness for unrelated tracks.

## Preferred preview soundtrack versus cleared export

Wan prefers the supplied reel as the **default/preferred private-preview soundtrack**. Defaults and rows retain `preferred_preview_music: {source: 'user-reel', rights_status: 'unverified', preview_only: true}`. This records his preference, **not a verified free/commercial license**. The UI distinguishes this from public export. Do not commit the extracted track, auto-download it on every job, or relabel it cleared.

The native worker currently uploads generated artifacts to public storage, so it uses the existing approved self-owned piano (`music-v8.mp3`) for exports, never silently swaps in reel audio. Unknown-rights custom export audio fails closed before model/storage calls. If the optional local reel source is absent, the cleared export remains available. To publish the preferred track, provide actual license evidence or use the user's explicitly chosen platform-licensed audio workflow after exporting. There is no native private-preview audio render route in this PR; the approved v17 private preview remains the reference artifact. Do not claim a production reel preview mix has been generated merely because the preference is saved.

## Entry-point behavior

- IdeaComposer “Motion only” queues directly into motions; no unnecessary post/image draft or AI image spend. URL-only motion ideas are allowed.
- Idea bulk action explicitly covers **filtered loaded ideas**, not every saved idea. It honors each row's language, retries failed variants, and does not treat a different language/design as already completed. Load more/filter as needed; no hidden promise of server-wide pagination.
- Post shortcut requires saving dirty/unsaved drafts; missing `post.lang` falls back to available EN/BM text. Motion generation does not edit the post.

## Runtime prerequisites / rollout

No merge, deploy, live database writes, model downloads or service installation are authorized by this PR update.

1. Apply existing `supabase/047_motion_styles.sql` **separately after 046**, with explicit rollout authorization, before the new UI. JSON options cover design/evidence/preview preferences; no extra migration needed. Merge ≠ apply.
2. Configure an already-installed VoiceStudio checkout exposing `services.tts_backend.KittenTTSBackend`, cached Kitten model, torch and soundfile. Set `VOICESTUDIO_PYTHON` and `VOICESTUDIO_ROOT` on the actual worker. Missing configuration fails explicitly; hosted Actions runners are not automatically configured.
3. Keep the current pinned HyperFrames CLI/browser/FFmpeg/ffprobe, LLM access and Supabase storage credentials. Remotion is optional. No installation occurs here.
4. Review real generated outputs for both designs, EN/BM/both/silent, 30/60s and 10s gimmicks before production acceptance. Verify decoding, final dimensions/fps/runtime, caption dwell/safe zones, evidence, correct logo/CTA and actual listening/master loudness. Tests alone are not this visual acceptance.

## Checks

```sh
cd web && npm test && npm run build
cd ../backend && pytest -q
ruff check backend
```

Regression suites include `motionRequirements.test.mjs`, `motionEntrypoints.test.mjs` and `backend/tests/test_motion_requirements.py`. The latter inspects actual prompt/build paths and worker project output with external boundaries stubbed, not synthetic claims of live renders.
