# Asset licenses — motion-v10

Asset provenance below is preserved from motion-v8/v9. No fresh license retrieval, stock download or voice generation is claimed for v10. All used source images, official logo, narration recordings and approved music are byte-preserved; v10 re-edits them. The edited teaser bed is `teaser-10s/music-bed.wav` (the inherited `micro-10s` references below describe v9).

Stock-source verification, original downloads and scientific evidence were preserved from motion-v7; no fresh full-paper inspection or new stock-license retrieval is claimed. These photographs remain illustrative: the bottle was not tested, the cream is not pure glycerin, and the sample ingredient list is not the bottle’s formulation. These disclosures are kept here/README rather than overlaid on the teaching scenes.

## Real stock photographs (Pexels Free, not Unsplash+)

1. **Alesia Kozik — Brown Glass Dropper Bottle on Brown Surface**
   - Photo page: https://www.pexels.com/photo/brown-glass-dropper-bottle-on-brown-surface-7796984/
   - Photographer: https://www.pexels.com/@alesiakozik/
   - Downloaded image: https://images.pexels.com/photos/7796984/pexels-photo-7796984.jpeg?auto=compress&w=1100
   - Local file: `assets/bottle.jpg`.
   - Photo page was retrieved and explicitly offers Free download / License Free. Visually inspected: amber bottle with blank black label, cork platform and dried flowers; no identifiable model or visible brand/logo. Used only as illustrative stock, not a product endorsement or evidence of its contents.
2. **Jana Kukebal — A White Cream on White Surface**
   - Photo page: https://www.pexels.com/photo/a-white-cream-on-white-surface-6689397/
   - Photographer: https://www.pexels.com/@janakukebal/
   - Downloaded image: https://images.pexels.com/photos/6689397/pexels-photo-6689397.jpeg?auto=compress&w=1100
   - Local file: `assets/cream-texture.jpg`.
   - Photo page was retrieved and explicitly offers Free download / License Free. Visually inspected: smooth white cosmetic texture, no identifiable people, branding or logo. Illustrative cream texture, NOT pure glycerin or a tested formulation.

Both: **Pexels License**, https://www.pexels.com/license/ (retrieved for this task). License text states all photos/videos on Pexels can be downloaded and used for free, attribution is not required, and modification is allowed. Restrictions include no implied endorsement, no unaltered resale, no redistribution to other stock/wallpaper platforms, no trademark use, and no offensive treatment of identifiable people. These files are project dependencies for this specific composed video, not a stock library for redistribution. Photographers are credited here voluntarily.

Treatment: framed photographs with crop and gentle scale/pan. No false alpha cutout, fabricated bottle backside or claim of full 3D rotation. Original JPEGs retained.

## Other assets

- `brand-assets/official-logo-transparent.png` and `official-original.png`: user-supplied official artwork, preserved from v6; use limited to the requested WS Regulab video. No license to others is asserted.
- `assets/approved-v8-melody.wav`: byte-preserved approved original synthesized warm additive electric-piano cue from motion-v8, with changing chord voicings, bass and melody. `approved-v8-music-score.json` preserves its original note events. This version edits only its opening/ending with a 0.5-second crossfade, lowers/ducks it and adds soft fades; no new pad, noise or downloaded track. `music-bed.wav` and `micro-10s/music-bed.wav` are the edited beds. Original composition lived in motion-v8/build.py, not this version's build.py. Not premium stock, MusicGen or a purchased library recording.
- `assets/long-voice-*.wav` and `assets/micro-voice-*.wav`: newly generated via actual installed debpalash/VoiceStudio `KittenTTSBackend` using existing `KittenML/kitten-tts-mini-0.8`, English preset `expr-voice-2-f`. Native speed 1.36, no atempo stretching. No cloning or third-party voice API. VoiceStudio repository AGPL-3.0; engine/model family documented Apache-2.0 in existing toolchain README. No model redistribution here.
- `assets/gsap.min.js`, `assets/background.png`: preserved from approved motion-v6 toolchain/design. GSAP is the existing project animation runtime; no package downloaded or license status changed.
- Journal card: original typographic bibliographic card, not a publisher screenshot. Process chart is our original conceptual layout, based on cited prose; no copyrighted paper figure was copied, traced or embedded.

Full scientific provenance and limitations: `citations/EVIDENCE.md`.
