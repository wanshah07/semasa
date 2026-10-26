---
name: ws-regulab-motion
description: "Create WS Regulab videos using approved motion templates."
user-invocable: true
argument-hint: "[topic] [design] [en|ms-MY] [voice|silent|gimmick]"
---
# Approved WS Regulab motion

Use for video creation, motion explainers, short reels, bilingual/silent variants, and footage editing in the previously aligned WS style. This is a Claude Code skill, not a claim of Claude.ai account synchronization. Read `references/contract.md` and `references/sources.md` before authoring. The current request's explicit overrides win; do not overwrite either approved design.

## Prerequisites
Use existing FFmpeg/FFprobe and a Python interpreter that actually imports Pillow. On this server `/usr/local/bin/python3` works; `python` does not. For full browser compositions use the existing pinned HyperFrames 0.8.188 described in `references/sources.md`; do not install a replacement. No paid APIs, ElevenLabs, model CLI calls, account uploads, repo integration or voice cloning without separate authorization. Keep secrets, models, personal footage and unlicensed reel audio out of portable packages.

## Resolve before drawing
1. Read actual approved reference frames/projects, not only the rejected seven-frame storyboard. Design 1 is **BrightPhotoDiagramEditorial**: licensed real photographs, editorial hierarchy, original explanatory diagrams, semantic motion. Design 2 is **ContinuousLine**: one tall connected SVG world, a growing path and camera tracking. Same colors alone are not design equivalence.
2. Resolve independent axes: design, complete-video recipe, individual effects, language, channel/brand, narration, duration, voice gender/provider and audio rights. Defaults: Design 1, 30 seconds, English, WS, optional voice (confirm on/off if unspecified), no mascot. Sixty seconds optional; ten seconds ONLY explicit gimmick. Never silently select a voice when its gender is requested differently.
3. Preserve the complete source catalogs in `references/Styles.txt` and `references/complete-motion.txt`, including original headings and occurrence order. Use `references/catalog.json`, not an invented taxonomy. Complete recipes and 99 distinct effect IDs are separate axes from the two approved designs. Original duplicate/missing IDs remain warnings, not repaired content. A catalog entry is NOT a tested renderer capability.
4. For generated explainers write Hook → Fact → Why → Solution, first the complete conversational script and retrieved evidence, then actual supported-language narration when enabled, then synchronize the beat sheet. Silent-first has its own complete connected story at roughly ≤2 visible words/sec, counting all labels/citations. It is not a spoken transcript with audio muted.
5. For uploaded footage preserve its original voice and meaning; obtain actual source-hash-matched ASR word boundaries using an existing authorized non-ElevenLabs backend before editing. Do not replace the speaker with TTS or fake timestamp highlighting. Keep source footage visible behind overlays and the face clear; torso overlap is allowed. Strategy changes to the user's cut require approval.

## Build, not just prompt
Resolve and validate settings using `scripts/resolve.py`; save the resolved manifest with the project. This resolver does not synthesize a finished science explainer: author the complete evidence-grounded scenes using the reference project and approved primitives. The included deterministic templates exercise the visual contract with an **8-second visual-only smoke**, not a shortened final explainer:

```sh
/usr/local/bin/python3 SKILL_DIR/scripts/resolve.py --design BrightPhotoDiagramEditorial --language en --mode silent --output /path/to/new-project.json
/usr/local/bin/python3 SKILL_DIR/scripts/smoke.py --design BrightPhotoDiagramEditorial --out /path/to/new-smoke
/usr/local/bin/python3 SKILL_DIR/scripts/smoke.py --design ContinuousLine --out /path/to/line-smoke
# Resolve.py validates configs; smoke.py builds HTML, runs pinned HyperFrames,
# ffprobes, fully decodes, and extracts contact frames. Inspect those PNGs.
```
Replace `SKILL_DIR` with the directory containing this SKILL.md. `smoke.py` defaults to the existing server renderer; laptop users supply `--hyperframes /path/to/already-installed/bin/hyperframes.mjs` and must provision its browser dependencies. Never rerun old full build scripts in protected approved output folders: copy/adapt into a fresh output directory first.

## Reject before presenting
- REJECT repeated generic bottle arches, empty decorative circles standing in for products, repeated headlines across all frames, tiny bottom captions, slide-only drafts, and a tiny final “Follow” logo. Never call these approved-template output.
- REJECT invented charts/results/quotes/testimonials/chat/screenshots; use retrieved evidence and authentic assets. Meaningful conceptual diagrams are allowed, clearly not quantitative data. A source citation is not proof of a product claim.
- REJECT unreadable typography or headline/photo collisions. Preview 540×960, final 1080×1920, 9:16. Center text or use one deliberate grid; reserve platform UI margins. Captions stay transparent, stable, 2–4 words when supported by actual ASR, no capsule boxes. A generated full-sentence reading layer is not ASR karaoke.
- REJECT recurring WS/Label Literacy headers and page numbers on teaching scenes. Long WS videos end with a separate centered official alpha-logo page held ≥3.3s. EN exact CTA: “Follow us for more”; BM: “Jangan lupa follow kami untuk tips seterusnya.” Personal LinkedIn uses avatar + exact “Ts. ChM. Muhammad” + “Follow me for more”, NO WS logo. Gimmick: ONE persistent composition, curious truthful question/partial reveal, “Stay tuned. Follow us for more” inside it; no explanation pages or separate long outro.
- REJECT publishing unverified reel audio in the portable pack/public final. Use cleared approved piano, subtle fades and ducking, no droning noise. Voice is optional. State actual engine/preset/rate and any approximate caption timing, never imply cloning or listening verification.

## Verify and deliver
Run the local negative/positive tests in `scripts/test_contract.py`. Before rendering record hashes of approved MP4s; after rendering confirm unchanged. Save source, settings, provenance, licenses and QA with the new MP4. FFprobe dimensions/fps/frame count/duration, full-decode every output, inspect encoded first/middle/last and transition/caption frames at phone size, and inspect the actual logo alpha. If voiced, check synchronization, pronunciation (requires listening), clipping, LUFS and true peak. Correct failures and rerender. Never equate lint, storyboard PNGs, file existence, or a successful CLI exit with complete visual approval.

Report exactly which design and adaptations were rendered, what was measured versus visually reviewed, and what remains untested. The included short smoke proves fresh composition/encoding only; it does not prove full bilingual narration, all catalog effects, application deployment, automatic Claude invocation, or pixel-identical future LLM output.
