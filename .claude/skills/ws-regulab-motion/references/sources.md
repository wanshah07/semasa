# Source map and scope

Approved references on this server (read-only; never rerun their builders in-place):
- `/opt/data/outputs/motion-v13/silent-first-30s.mp4`: silent-first photo/editorial.
- `/opt/data/outputs/motion-v13/gimmick-single-scene-10s.mp4`: one-composition gimmick.
- `/opt/data/outputs/motion-v15/english-new-style.mp4`, `malay-voiced.mp4`; README, build-en.py, build-ms.py, voice-en.py, prepare-ms.py, master-en.py, verify.py, HTML in `english-new-style/` and `malay-voiced/`.
- `/opt/data/outputs/motion-v17/preview.mp4`: approved slower continuous-line reference. `/opt/data/outputs/motion-v16/continuous-line/` holds its underlying connected SVG composition; v16 README documents the faster voice and unverified reel rights, not the final v17 pace.
- `/opt/data/outputs/motion-v6/brand-assets/official-logo-transparent.png`: actual RGBA logo.
- `/opt/data/outputs/styles-new/Styles.txt`: untouched individual-effect catalog, copied here as Styles.txt.
- `/opt/data/outputs/motion-styles/attachment-text.txt`: untouched complete recipes, copied here as complete-motion.txt.
- `/opt/data/outputs/motion-v15/LICENSES.md`, JOURNAL-PROVENANCE.md and citations/: inherited stock/evidence sources. Local `LICENSES.md` preserves inherited license prose with its historical scope. The bundled bottle is illustrative stock, not a tested formula.

Existing HyperFrames executable (0.8.188):
`/opt/data/.npm/_npx/28cdaee379cf4d67/node_modules/hyperframes/bin/hyperframes.mjs`
Use `node PATH render PROJECT -o OUTPUT --workers 1 --low-memory-mode --no-browser-gpu --fps 24 --quality draft --frames-cache-dir off`.
Use `node PATH lint PROJECT` and `node PATH validate PROJECT` where applicable. Real encode, FFprobe/full decode and frame inspection are still required. No renderer download/install is needed on this server. Do not clear cached executable/browser while cleaning scratch.

## Bundled assets
`assets/bottle.jpg`: Alesia Kozik, Pexels photo 7796984, https://www.pexels.com/photo/brown-glass-dropper-bottle-on-brown-surface-7796984/ ; download https://images.pexels.com/photos/7796984/pexels-photo-7796984.jpeg?auto=compress&w=1100 ; Pexels License https://www.pexels.com/license/ . License metadata is inherited from prior verified project, not freshly re-retrieved. Bundled only as this project's composition dependency.
`assets/official-logo-transparent.png`: user-supplied official artwork; authorized WS compositions, not a public trademark asset license.
`assets/gsap.min.js`: preserved animation runtime; see bundled original license banner. `assets/asset-provenance.json` contains original absolute source paths and SHA-256 hashes.

The two template HTML files are fresh short visual regression compositions built from the approved design language. They are not old MP4 copies, exact full-project migrations, or new science claims. No soundtrack or TTS is present in their visual-only smoke output. Neither 8-second smoke is a 10-second gimmick or a complete explainer.

Official skill-location/invocation reference: https://code.claude.com/docs/en/skills . Personal skills use `~/.claude/skills/NAME/SKILL.md`, can be relevant to natural-language requests and can be invoked explicitly `/NAME`. This proves file placement only; no model call was made to verify automatic invocation.
