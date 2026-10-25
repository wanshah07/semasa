# Attachment-derived motion recipes

## Scope and current policy

The Motion form saves `options.style` and `options.mode` on `semasa_motions`; idea/post shortcuts and saved defaults carry both. The worker injects the chosen supported recipe into both script and composition prompts. This is not just a visual dropdown.

- Default: 30-second English explainer, portrait 9:16, VoiceStudio KittenTTS, no mascot. Optional 60 seconds. Explain with **Hook → Fact → Why → Solution**.
- **10 seconds is ONLY an explicitly selected gimmick/teaser mode**, never an explainer. A legacy 10-second saved setting without teaser mode becomes 30 seconds. Durations include the separate three-second brand outro. Never accelerate or truncate narration to fit.
- Bright mint/cream, deep teal type; transparent captions without boxes/pills/scrims, centered or grid-aligned and inside mobile safe zones. The official transparent logo appears only on the final page, full tagline intact. Visible CTA: “Follow for more tips!”; spoken: “Follow us for more.”
- Citation shorthand: FirstAuthor et al. (year) for more than two authors; explain briefly what the journal publication studied/reviewed and how it supports the claim. Do not invent findings or data.
- Approved supplied original synthesized melody v8 is mixed softly, ducked under narration, with fade-in/out. No downloaded commercial music.

## Catalog and provenance

`rules/motion/attachment-reference.txt` preserves the full supplied extraction. `recipes.json` has all eight source sections, representing seven distinct recipe bodies. Client Testimonial repeats Tutorial / Screen Recording in the source: explicitly flagged, never invented as a testimonial specification. Source timings, instruction order and primary/overlay/audio/global treatment metadata remain in the catalog; teaching-window timings are adapted in the worker prompt, not sorted into a flattened timeline.

Available now: Auto, Bright education adaptation, Financial Education Reel. Other recipes remain visible but disabled because this form has no uploaded footage, captures, document/product cutouts or photo assets. Unknown/unavailable recipes fall back to bright education. Charts and counters require verified data, otherwise the prompt omits them in favor of qualitative diagrams. Recipe adherence beyond the injected policy is model-authored and still needs visual review; this is not a deterministic implementation of every attachment effect.

Original talking-head speech must be preserved when a future upload/editing path is implemented. This branch does not add that path and does not claim to edit or re-voice source footage.

To rebuild catalog/provenance from the original supplied extraction (requires the original DOCX alongside it):

```sh
python ops/import_motion_recipes.py /path/to/attachment-text.txt
```

## Runtime prerequisites — adapter, not a live VoiceStudio service

This PR does not install or launch VoiceStudio, download model weights, deploy a worker, or apply SQL. The English adapter requires:

- An already installed compatible VoiceStudio checkout exposing `services.tts_backend.KittenTTSBackend` and its cached KittenTTS model; `soundfile`, `torch` and model dependencies in that environment.
- `VOICESTUDIO_PYTHON` set to that environment's Python executable and `VOICESTUDIO_ROOT` to the checkout. The worker must be able to access both locally. Existing hosted Actions runners are not automatically configured for it.
- FFmpeg/ffprobe, pinned HyperFrames CLI and browser dependencies already used by the motion worker, LLM access, and Supabase storage credentials.

KittenTTS is English-only, uses a preset at normal speed, never cloning, Claude Max or ElevenLabs. Missing Kitten configuration fails explicitly rather than silently falling back. No fabricated word alignment: the adapter returns no word timestamps. Edge male/female remain optional for BM/bilingual jobs. Existing legacy rows retain explicit language/voice choices.

Apply `supabase/047_motion_styles.sql` manually **after 046** and before deploying the new UI. It adds JSON options, changes new-row duration/mascot defaults and permits `kitten`; it does not modify existing rows. Do not apply it as part of code review.

## Focused checks

```sh
cd web
node motion.test.mjs && node motionStyles.test.mjs
npm run build
cd ../backend
pytest tests/test_motion.py tests/test_motion_styles.py -q
```

Worker tests stub LLM, CLI, speech and storage boundaries. Passing them is not evidence of a live VoiceStudio installation, a real generated explainer, production migration or deployment.
