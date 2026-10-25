# motion-v16 — continuous-line / supplied-reel-audio approval preview

Deliverable: `english-continuous-line-reel.mp4` — 26.041667 seconds, native 540×960, 24 fps / 625 frames, H.264 + AAC 48 kHz. Actual HyperFrames 0.8.188 render, not a static mockup or upscale.

## Different visual style

One tall illustrated SVG world, one growing green story-thread and warm-gold pen marker, with calm vertical camera tracking through conceptual branches. Thin botanical/editorial lines, regular-weight serif annotations and bright mint/cream replace the previous bold headline/photo/card treatment. This adapts the supplied reel's continuous-line storytelling idea, not its exact family artwork, frames or dark palette.

The connected path travels from ingredient-name question → glycerin/water/skin → dermatology review → formulation context → package directions/warnings. Drawings are conceptual illustrations, not chemical bonds, formula composition percentages or fabricated product results. The review node is explicitly not a product test. No people, page numbers, recurring brand headers, fake evidence screenshots or invented data.

The final 3.313 seconds are a standalone, centered official transparent-alpha brand logo with **Follow us for more** visible and spoken. Sentence/clause captions are centered on transparent backgrounds. Caption boundaries reuse the approved approximate phrase timing; no claim of forced word alignment. Source HTML and build scripts are included under `continuous-line/` and this directory.

## Real approved voice + requested reel audio

Narration is a byte-identical copy of the approved v15 English narration WAV (actual VoiceStudio Kitten expr-voice-2-f, original native speed 1.50 and disclosed pitch-preserving atempo 1.04, measured active speech approximately 171.69 wpm). No new synthetic substitute, ElevenLabs, paid service or voice clone. Exact text and provider metadata: `ENGLISH-SCRIPT.md`, `english-voice-provider.json`.

The audio under it is the actual first 26.041667 seconds of the user's supplied Instagram reel, not the old piano. It is leveled, ducked under narration and faded at the boundaries with original pitch/tempo. Offline ASR/VAD found no speech in this used excerpt. This is not human listening or source separation, and not a guarantee that the original audio contains no vocals. **License unknown; private reference/approval only, not cleared for commercial publishing.** See `AUDIO-LICENSE.md` and `reel-audio-inspection.json`.

## Verification

`verification.json` records a full successful FFmpeg decode, ffprobe native dimensions/fps/frame count/runtime, decoded sample peak, encoded integrated loudness and true peak, narration hash equality, prior-output hash checks, and near-perfect residual correlation verifying the actual reel-derived bed remains in the premaster mix. `review/contact-sheet.jpg` includes all caption midpoints and the final logo frame. The first inspection found connector lines crossing title lettering; the final render uses glyph halos to keep those labels readable. No inspected caption overflow or logo collision. Tiny mechanism/provenance notes are secondary, with the core message in larger captions and narration.

HyperFrames lint: zero errors; one intentional `audio_file_without_element` warning. This pipeline renders graphics first and explicitly muxes/master-checks the real audio afterward; the final deliverable is NOT silent. Do not distribute the intermediate visual-only MP4 as the final.

All protected earlier videos, including approved silent/gimmick/BM outputs, are unchanged. No prior output files, repository source, installs, models, auth or upload assets were altered. Nothing was published or deployed. Asset folders are read-only-style symlinks to existing approved assets in motion-v15; retain earlier folders alongside this source project.

## Reproduce

```sh
OPENBLAS_NUM_THREADS=1 /usr/local/bin/python3 /opt/data/outputs/motion-v16/build.py
OPENBLAS_NUM_THREADS=1 /usr/local/bin/python3 /opt/data/outputs/motion-v16/render.py
OPENBLAS_NUM_THREADS=1 /usr/local/bin/python3 /opt/data/outputs/motion-v16/verify.py
# Optional original-excerpt speech screening, with existing local model only:
OPENBLAS_NUM_THREADS=1 /usr/local/bin/python3 /opt/data/outputs/motion-v16/check-reel-audio.py
```

`verify.py` does the final two-pass loudness master and mux; rerunning only `render.py` does not regenerate the named mastered deliverable. Original supplied reel must remain available at the provenance path for rebuilding the audio bed. The temporary unducked excerpt is removed; only short derived preview mixes/bed remain.

Issue resolved: installed faster-whisper/PyAV API mismatch (`metadata_errors`) was bypassed by FFmpeg WAV decoding and direct NumPy waveform input; no package changes. Disk stayed above the renderer threshold, with no unrelated cleanup required. User listening approval and publication rights clearance remain outside the technical verification.
