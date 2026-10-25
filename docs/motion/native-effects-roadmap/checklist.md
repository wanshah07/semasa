# Native effects roadmap — PR79 baseline

Frozen baseline: `f5e6fb4e23ae17ec1a6cba3f8d8bc97108718931` (PR79, not modified).

99 unique IDs / 106 source occurrences; 7 exact duplicates retained as provenance, H07 absent (not invented), no imported conflicting codes.
94 unique concept fallbacks enumerated below. Group headings preserve all 11 exact source section titles. Each checklist row occurs once under its first source section; JSON also retains all section memberships and original asset/fallback requirements.

## Scope and counts

Status counts: `{'not_implemented': 90, 'render_tested_heading_adaptation': 4}`.
Implementation tracks: `{'needs_assets_and_core_renderer': 88, 'core_renderer': 6}`.
Four render-tested **heading-only** native adaptations are not full source-video equivalents. Existing five prepared-panel/vector/screenshot adaptations are unchanged. The other 90 baseline fallbacks remain unimplemented. V10 is deferred: its source says both 3s overall and ≥3.3s hold after the last chunk; this timing conflict is not silently resolved.
Core-renderer track can use existing authored headings, or has no required assets in the original source (V08). Needs-assets-and-core-renderer requires both authentic original inputs AND native implementation; source video, word timing, masks, data, audio and rights are not created by this batch. Captions are not fake word-aligned. No source-footage processing is claimed.

## Featured Effects

- [ ] **X01 — Orbit Cards** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video, Screenshots. Sections: Featured Effects / Signature Effects.
- [ ] **X02 — Infinite Content Wall** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video, Screenshots. Sections: Featured Effects / Signature Effects.
- [ ] **X03 — Frame Break** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video. Sections: Featured Effects / Signature Effects.
- [x] **H01 — Headline Slam** · `core_renderer` · render_tested_heading_adaptation. Original required assets: Source video. Sections: Featured Effects / Hooks.
- [ ] **C01 — Karaoke Follow** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video. Sections: Featured Effects / Captions.

## Hooks

- [ ] **H02 — Pattern Interrupt** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video. Sections: Hooks.
- [x] **H03 — Question First** · `core_renderer` · render_tested_heading_adaptation. Original required assets: Source video. Sections: Hooks.
- [ ] **H04 — Result Before Process** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video. Sections: Hooks.
- [ ] **H05 — Countdown Hook** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video. Sections: Hooks.
- [ ] **H06 — Split Reveal** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video. Sections: Hooks.
- [ ] **H08 — Scroll Stop Flash** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video. Sections: Hooks.
- [ ] **H09 — Contrarian Hook** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video. Sections: Hooks.
- [ ] **H10 — Cinematic Cold Open** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video. Sections: Hooks.

## Captions

- [ ] **C02 — Pop Word Captions** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video. Sections: Captions.
- [ ] **C03 — Typewriter Subtitles** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video. Sections: Captions.
- [ ] **C04 — Highlight Sweep** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video. Sections: Captions.
- [ ] **C05 — Stacked Captions** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video. Sections: Captions.
- [ ] **C06 — Editorial Lower Thirds** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video. Sections: Captions.
- [ ] **C07 — Explosive Keywords** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video. Sections: Captions.
- [ ] **C08 — Subtitle Capsules** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video. Sections: Captions.
- [ ] **C09 — Monospace Terminal Captions** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video. Sections: Captions.
- [ ] **C10 — Bilingual Caption Flow** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video, Transcript with timing. Sections: Captions.

## Layouts

- [ ] **L01 — Vertical Split Screen** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video. Sections: Layouts.
- [ ] **L02 — Picture-in-Picture Focus** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video. Sections: Layouts.
- [ ] **L03 — Triple Stack** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video. Sections: Layouts.
- [ ] **L04 — Floating Device Frame** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Screen recording. Sections: Layouts.
- [ ] **L05 — Editorial Sidebar** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video. Sections: Layouts.
- [ ] **L06 — Center Spotlight** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video. Sections: Layouts.
- [ ] **L07 — Grid Conversation** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video, Second shot. Sections: Layouts.
- [ ] **L08 — Cinematic Letterbox** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video. Sections: Layouts.
- [ ] **L09 — Collage Canvas** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Photos. Sections: Layouts.
- [ ] **L10 — Adaptive Proof Panel** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video, Screenshots. Sections: Layouts.

## Proof

- [ ] **P02 — Comment Spotlight** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video, Social comment. Sections: Proof.
- [ ] **P03 — Metrics Count-Up** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video, Verified data. Sections: Proof.
- [ ] **P04 — Before and After Wipe** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Before & after pair. Sections: Proof.
- [ ] **P05 — Search-to-Result** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Screenshots. Sections: Proof.
- [ ] **P06 — Receipt Stack** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Screenshots. Sections: Proof.
- [ ] **P07 — Annotation Marker** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Screenshots. Sections: Proof.
- [ ] **P08 — Timeline Evidence** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Verified data. Sections: Proof.
- [ ] **P09 — Quote Card Reveal** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Quotation text. Sections: Proof.
- [ ] **P10 — App UI Breakdown** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Screenshots. Sections: Proof.

## Visual Beats

- [x] **V01 — Kinetic Section Title** · `core_renderer` · render_tested_heading_adaptation. Original required assets: Source video. Sections: Visual Beats.
- [ ] **V02 — Number Burst** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video. Sections: Visual Beats.
- [x] **V03 — Keyword Spotlight** · `core_renderer` · render_tested_heading_adaptation. Original required assets: Source video, Transcript with timing. Sections: Visual Beats.
- [ ] **V04 — List Cascade** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video. Sections: Visual Beats.
- [ ] **V05 — Comparison Collision** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video. Sections: Visual Beats.
- [ ] **V06 — Progress Journey** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video. Sections: Visual Beats.
- [ ] **V07 — Callout Bubble** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video. Sections: Visual Beats.
- [ ] **V08 — Shape Morph** · `core_renderer` · not_implemented. Original required assets: None specified. Sections: Visual Beats.
- [ ] **V09 — Data Visualization Beat** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Verified data. Sections: Visual Beats.
- [ ] **V10 — Statement Reveal** · `core_renderer` · not_implemented. Original required assets: Source video. Sections: Visual Beats.

## Animated B-Roll

- [ ] **B01 — Browser Flythrough** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Screenshots. Sections: Animated B-Roll.
- [ ] **B03 — Device Showcase** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Screen recording. Sections: Animated B-Roll.
- [ ] **B05 — Parallax Photo Depth** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Photos. Sections: Animated B-Roll.
- [ ] **B06 — Product Cutout Reveal** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Product image. Sections: Animated B-Roll.
- [ ] **B07 — Animated Map Journey** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Map locations. Sections: Animated B-Roll.
- [ ] **B09 — Document Flyover** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Document / PDF. Sections: Animated B-Roll.
- [ ] **B10 — Interface Component Breakdown** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Screenshots. Sections: Animated B-Roll.

## Signature Effects

- [ ] **X04 — UI World** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video, Screenshots. Sections: Signature Effects.
- [ ] **X05 — Infinite Zoom Tunnel** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Photos. Sections: Signature Effects.
- [ ] **X06 — Magnetic Mosaic** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Photos. Sections: Signature Effects.
- [ ] **X07 — Reality Portal** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video, Second shot. Sections: Signature Effects.
- [ ] **X08 — Clone Echo** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video. Sections: Signature Effects.
- [ ] **X09 — Cinematic Carousel** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Screenshots. Sections: Signature Effects.
- [ ] **X10 — Blueprint Universe** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Transcript with timing. Sections: Signature Effects.

## Motion Pace

- [ ] **M01 — Snap Zoom** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video. Sections: Motion Pace.
- [ ] **M02 — Whip Transition** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video. Sections: Motion Pace.
- [ ] **M04 — Freeze Beat** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video. Sections: Motion Pace.
- [ ] **M05 — Rhythm Cuts** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video. Sections: Motion Pace.
- [ ] **M06 — Speed Ramp** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video. Sections: Motion Pace.
- [ ] **M07 — Subtle Camera Shake** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video. Sections: Motion Pace.
- [ ] **M08 — Seamless Match Cut** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video, Second shot. Sections: Motion Pace.
- [ ] **M09 — Mask Swipe** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video. Sections: Motion Pace.
- [ ] **M10 — Stutter Motion** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video. Sections: Motion Pace.

## Sound

- [ ] **S01 — Impact Hit** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video, Sound effects. Sections: Sound.
- [ ] **S02 — Cinematic Whoosh** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video, Sound effects. Sections: Sound.
- [ ] **S03 — Tension Riser** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video, Sound effects. Sections: Sound.
- [ ] **S04 — Keyboard Ticks** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video, Sound effects. Sections: Sound.
- [ ] **S05 — Silence Drop** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video. Sections: Sound.
- [ ] **S06 — Beat Synchronization** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video, Music track. Sections: Sound.
- [ ] **S07 — Subtle Foley Accents** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video, Sound effects. Sections: Sound.
- [ ] **S08 — Dynamic Voice Ducking** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video, Music track. Sections: Sound.
- [ ] **S09 — Transition Bass Pulse** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video. Sections: Sound.
- [ ] **S10 — Outro Audio Resolve** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video, Music track. Sections: Sound.

## Colour & Finish

- [ ] **F01 — Clean Creator Grade** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video. Sections: Colour & Finish.
- [ ] **F02 — Warm Editorial** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video. Sections: Colour & Finish.
- [ ] **F03 — Cool Technology** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video. Sections: Colour & Finish.
- [ ] **F04 — Cinematic Teal Shadows** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video. Sections: Colour & Finish.
- [ ] **F05 — Modern Monochrome** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video. Sections: Colour & Finish.
- [ ] **F06 — Bold Pop Colour** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video. Sections: Colour & Finish.
- [ ] **F07 — Soft Pastel Film** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video. Sections: Colour & Finish.
- [ ] **F08 — Film Grain & Bloom** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video. Sections: Colour & Finish.
- [ ] **F09 — Analog Tape Texture** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video. Sections: Colour & Finish.
- [ ] **F10 — Premium Commercial Finish** · `needs_assets_and_core_renderer` · not_implemented. Original required assets: Source video. Sections: Colour & Finish.

## Acceptance / evidence

See `native-text-batch1-qa.md` for executed tests, real 2-second HyperFrames renders and limitations. `ops/smoke_native_text.py` reproduces the local render proof without LLM, TTS, live storage or new installs. No migrations, deployment or merge.
