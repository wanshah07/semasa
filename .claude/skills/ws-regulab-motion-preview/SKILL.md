---
name: ws-regulab-motion-preview
description: "WS Regulab continuous-line preview video: one connected line world (540x960 reference, about 29 s)."
user-invocable: true
argument-hint: "[topic]"
---
# Preview (continuous line)

Reference: `reference/reference.mp4` (28.9 s, 540x960, 24 fps, voiced) and `reference/contact-sheet.jpg`. Match it.

## Format
- Design 2, ContinuousLine. Background `linear-gradient(150deg,#e4f4e8,#fcf9ed)`; thin green and warm-gold lines on it.
- ONE tall connected SVG world: a stroke grows down it with a small pen marker, and the camera tracks it calmly. Scenes are places on the
  line (a drop splitting into "water" and "skin", an open book with a citation, a bottle with branches "ingredient" and "context", a packaging
  outline with "directions" and "warnings"), never separate cards. Mask the stroke under label letters.
- Titles in a regular SERIF ("A role, explained.", "More than one role.", "Read the packaging."), small captions in sans beneath,
  every drawing marked as illustrative, not data.
- Narration as two-line transparent subtitles at the bottom. Slower pace than the other formats.
- Ends with a separate centred logo page and the exact CTA line (>= 3.3 s). No scene labels.

## Always (all four formats, 26 Oct 2026)
- Background: a soft diagonal gradient only (see the reference frames). NEVER circles, blobs, bokeh, dots or other decorative shapes.
- No mascot, no talking head, no scene labels such as HOOK / FAKTA on screen. Flow stays Hook, Fakta, Kenapa, Solusi.
- Photos are real stock (Unsplash, credited in the row), in their own frame, never behind text; illustration only, never proof.
- Text never overlaps: every block has its own region; the subtitle lane is separate from the content.
- At least 15 of the 99 styles apply to every film (the worker chooses them per scene for fit; `ws-regulab-motion` holds the catalogue).
- Silent films are slow (about 1.4 words a second); narrated films are brisk.
- The base skill `ws-regulab-motion` (contract, catalogues, templates) applies on top of this format spec.
