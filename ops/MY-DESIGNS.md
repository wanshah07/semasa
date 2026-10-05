# My designs

Wan, 4 Oct 2026: *"create a default design for carousel, poster and single card, like ERA, Photo, Grid and Semasa. I need not fill any
text: the design has the layout, and the text fills it when the idea comes in from the draft. Don't make it complicated."*

**Run `supabase/027_my_designs.sql` once** (two settings rows). Until then the Design tab says so and nothing else changes.

## Where you find it
* **Design tab → *My designs*** (open by default) → *New design from a reference picture*.
* **Design tab → Design reference box → *Save as my design*** (after you upload a reference there): reads the layout once, saves it, makes it
  the default for new drafts and selects it in *Slide design*. (The older *Rebuild / Inspired* buttons are unchanged: they make ONE picture and
  save nothing.)
* **Slide design** (in a post, in the Design tab and in the idea composer) shows your designs as tiles in the SAME row as Semasa, Grid, Info
  ERA and Photo, plus a dashed *My design from a reference picture* tile. The default design is pre-selected there.
* An idea that names a look (including Semasa's own) keeps it; only an idea that names none takes the default design.

## Make one FROM A REFERENCE PICTURE (the way ERA, Grid and Photo were made) — the main way
Wan, 4 Oct 2026: *"ERA, Grid and Photo came from references I gave from ws.regulab Studio. I want like that."*

Design tab → *My designs* → **New design from a reference picture**:
1. Choose a reference picture (a poster, a card, a slide you like). The AI reads its **layout** once (about half a minute): where the headline, the
   label, the supporting lines, the source, the pictures and the logo go; the shapes, fonts, sizes and alignment. The colours are then
   **measured from the picture's own pixels** (not guessed). Logos, brand names, faces and calls to action are never copied.
2. Optionally give a different reference for the cover, the middle slides, the closing slide or the single card / poster. The first one is used
   for every place that has none of its own.
3. The strip shows cover, middle, closing and single card on sample words. Name it, tick *Use for new drafts* if you want it as the default, Save.

When an idea becomes a draft, its words are poured into the saved layout (headline, label, points, source), the type shrinks to fit the boxes the
reference had (a word is never cut), the ws.regulab logo takes the place of the reference's logo (LinkedIn: none), and the post's background picture
fills the reference's picture area. Small decorative text in the reference (dates, page marks, side labels) is left out.
Best results come from a reference of the same shape as the cards (square for ws.regulab, 4:5 for LinkedIn).

## Drawn on the reference picture (5 Oct 2026)
A design from a reference now keeps the reference picture itself (`refart`: a file in the `semasa-reference` bucket, its size, and the
patches that cover its old words, logos and faces in the colour behind them). The card is drawn ON that picture, so the background is
the reference's own, and only the new words are drawn on top, where the layout puts them. A card of another shape (square or 4:5) sees
a cover-crop window of the picture, kept around the words (`cropWindow`); the layout is moved into the window (`remapLayout`).
* **Logo**: the ws.regulab logo is always drawn (LinkedIn carries none): in the reference's own logo slot if that slot is fully on the
  card, otherwise in the first corner no words touch. It is trimmed to its ink and goes white over a dark area. *Cause of the hidden
  logo*: the slot sat partly outside the cropped window, so the logo was drawn half off the card.
* **Matching**: after saving the design the page draws filler words of the reference's own length over it, scores it against the
  reference (`compareImages`), and asks the AI for up to 3 refine passes, keeping a pass only when the score rises.
* **Zoom**: every card preview (design strip, tiles, saved result) opens a full-size popup when clicked.
* **Saving**: each step (read, measure, draw, upload, save) shows its progress, and a failure stays on screen with the reason, in
  place of a toast that disappears. If saving still fails, copy that line.
* The worker reads the picture for each job (`media_generator.own_reference_art`); if it cannot, the design is drawn in layers as before.

## The simple way (family and colours)
Design tab → *My designs* → *Simple*, no words needed
1. **Start from** Grid, Info ERA or Photo (the drawing and palette it uses).
2. **Colours**: an accent and a paper colour, or Auto (the family's own).
3. **Background**: none, or one of your photographs; and how much the words cover it (Auto: a light picture gets none).
4. **Layout per place**: cover, middle slides, closing slide, single card / poster. Auto = the family chooses by the words.
5. Optional small label and mascot. The strip underneath shows cover, middle, closing and single card on sample words.
6. Tick **Use for new drafts** to make it the default.

## What happens with it
* Every draft written from an idea is drawn in the default design (carousel and poster), and the idea's words fill the layout.
  An idea that picked a look of its own (Grid, ERA, Photo, or another design) keeps that.
* In a post, the look picker shows **My designs** under the four looks; pick one and press *Generate slides*.
* The Design tab and the idea composer offer the same tiles. A template chosen on one slide always beats the design.
* A job carries the design as a snapshot (`meta.design_pack`): editing or deleting a design never changes a card already drawn,
  and a redraw gives the same card. A deleted design simply falls back to Semasa's own drawing.

## How it works (for the next person)
`web/src/lib/cards/studio.js` `normDesign` / `placeOf` / `specsFor` (the design decides the family, the template by place, the
palette, label, scrim and mascot); the two colours replace the family's accent and paper for one card at a time (`renderSpec`
serialises renders and restores the palette in a `finally`). `backend/semasa/my_designs.py` reads the settings and resolves a look
value (`grid`, `era`, `photo`, `classic`, `d:<id>`) when the idea becomes a draft (`ideas.slide_job` / `poster_job`).
A design from a reference carries `layouts` (`{place: layout}`); `studio.js` `normLayout` / `renderRefCard` / `paintSeed` pour the words
in through `designCloneSeed.js layoutToSeed` and paint the layers (the worker serves those two modules, `studio_cards.LIB_MODULES`).
`web/src/lib/designs.js` is the page's side (context, `resolveLook`). Tests: `designs.test.mjs`, `cards.test.mjs`,
`tests/test_my_designs.py`, `tests/test_studio_cards.py`, `design_fidelity.test.mjs`.
