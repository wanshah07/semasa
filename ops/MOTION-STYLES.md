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

## NEW Styles.docx: separate effect library and complete recipes

The new document is archived independently at `docs/motion/Styles.docx`, with a full
paragraph extraction in `Styles.txt`. `rules/motion/style-effects.json` preserves
**106 occurrences, 99 unique instruction bodies and seven exact duplicates**.
There are no conflicting same-code bodies in this source; **H07 was not supplied**.
The importer preserves conflicting bodies under distinct digest-qualified IDs rather
than overwriting them. Source and extraction SHA-256 hashes, counts and categories
are in `style-effects-provenance.json`. Rebuild using
`python ops/import_style_effects.py /path/to/Styles.docx`; no source instructions execute.

The 99 entries are a reference effect library, **not 99 finished-video recipes**.
`style-bundles.json` defines three selectable complete native adaptations:
Editorial explainer, Kinetic explainer and Blueprint / process explainer. Each
combines eight tracks (hook, captions, layout, proof, illustration, motion, audio,
look) with Hook → Fact → Why → Solution and the official final outro. Both writers
receive the entire adapted recipe; the worker saves `recipe-plan.json` with actual
scene times and retains roles in the stored script and plan in the lint report.
An isolated opening overlay does not satisfy the four-scene explainer contract.
Explicit 10s teasers remain one persistent scene with the in-scene CTA.

Both approved design selectors, the old eight-section attachment, saved defaults
and all motion entry points remain independent and supported. These new recipes
adapt named techniques to the approved design and latest requirements; they do
not execute the raw attachment or promise deterministic recreation of every effect.
Creator / proof footage editing stays listed but disabled; the backend rejects it
even if a caller supplies a fake asset path. No footage upload/alignment/matte
pipeline or selfie media has been added. Real footage, verified screenshots,
word timestamps, licensed audio and consent for any voice cloning are not inferred.
Real runtime/visual/listening acceptance remains required as described below.

## Latest Wan requirements

- Default 30-second portrait explainer; optional 60 seconds. Final 1080×1920, 30 fps; approved reference previews 540×960 (manual v16/v17 references are 24 fps). Never silently upscale a reference preview and call it a native full-resolution final.
- Explain with **Hook → Fact → Why → Solution**: strong curiosity hook and connected complete casual sentences, not isolated headings. English or Malaysian Malay, never Indonesian.
- **10 seconds ONLY an explicit gimmick/teaser**, one persistent composition and curiosity hook. No compressed paper explanation, multi-page slideshow, or standalone logo/CTA page. “Stay tuned. Follow us for more” stays in that same scene. Legacy 10s defaults without teaser become 30s.
- Voice optional on/off, English/BM/both. One frontend resolver is used by direct/defaults/idea/post/bulk entry points: incompatible BM/both + Kitten becomes native Edge female. Backend protects legacy incompatible rows too; explicit `off` remains silent.
- English: actual configured VoiceStudio Kitten adapter, expr-voice-2-f, native speed 1.50 then pitch-preserving `atempo=0.936` (v16's 1.04 × approved 0.90), not the rushed v16 setting. Target approval approximately 154 active-speech wpm, not a guarantee for every generated phrase. BM/both: native ms-MY Edge; never label it VoiceStudio. **Pace, 25 Oct 2026 (Wan): a narrated film is brisk (Edge English x1.15, Malay x1.25 by ffmpeg tempo after recording, 0.2 s between scenes); a silent film is slow, about 1.4 words a second, so it can be read. Every explainer is Hook, Fakta, Kenapa, Solusi, has Unsplash photos, no mascot, and styles chosen per scene by `motion_auto.py`; the layout that cannot overlap is `motion_layout.py`.** Say `pembungkusan` instead of the problematic spoken `label`. No ElevenLabs, cloning, Claude CLI or Claude model calls.
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


## Wan's skill `ws-regulab-motion` (25 Oct 2026)
Installed twice, one source of truth: `.claude/skills/ws-regulab-motion/` is a Claude Code **project skill** (open this repo in Claude Code and run `/ws-regulab-motion ...`; on a laptop, copy the folder to `~/.claude/skills/`), and the motion worker (`motion.skill_context`) hands its `references/contract.md` and the template of the chosen design to the writer on every film, below the fixed scenes and the current policy, which win where they differ. The skill's own scripts (`resolve.py`, `smoke.py`, `test_contract.py`) are unchanged and need Pillow, PyYAML and a local HyperFrames; their defaults point at the server they were built on.

## The worker composes the film, with as many of the 99 styles as fit (26 Oct 2026)
Both test films (26 Oct) had the AI writer's own layout refused by HyperFrames' `content_overlap` on all three tries: it places text by coordinates and draws circles. So the worker composes every film itself (`backend/semasa/motion_layout.py`); `MOTION_WRITER=1` brings the writer back. Wan: "push to use as many styles from 99 styles as you can, include the diagram, flow, charts and publication study if any".
- **Per scene, not per film:** each scene has its own caption style (C02 C03 C04 C05 C06 C07 C09 C10), its own finish when it has a photo (F02 F03 F05 F06 F07 F10) and the hand-over that leaves it (M02 M08 M09). The chooser then adds every other eligible style to the scene it suits, up to 8 a scene (`motion_auto.choose`, `PER_SCENE`): about 17 to 26 styles in a four-scene film, 37 different styles across 40 random test films.
- **Built from the words and nothing else:** P03 counts a printed whole number up to itself; V09 draws a bar for each percentage in the lines, as long as the figure says; P08 draws a timeline from two or more years in the lines; B04 is a numbered step rail, or a flow diagram of boxes joined by arrows in the Solusi scene; V05 two option cards; V06 a progress track; L05 a side panel beside the photo; P09 a card for the quoted words.
- **The publication study (P09):** when the idea is a paper, a card shows the journal, the paper's title and the PMID or DOI, taken from `options.evidence` (`source_name`, `source_title`, `source_url`) and from nothing else. A news item is never drawn as a study.
- Also built: H02 H05 H06 H08 H10, L06, V02 V04 V08 V10, B05 B08, X06 X10, M03 M04 M07; natively H01 H03 V01 V03. Not built, with the reason on the row: styles that need footage, a screen capture, a sound file or a layer that could hide text.
- `check_report.layout.built` lists what was really drawn (not only what was chosen) and `not_built` what was chosen but could not be drawn for that film's words.
