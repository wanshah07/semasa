# My designs

Wan, 4 Oct 2026: *"create a default design for carousel, poster and single card, like ERA, Photo, Grid and Semasa. I need not fill any
text: the design has the layout, and the text fills it when the idea comes in from the draft. Don't make it complicated."*

**Run `supabase/027_my_designs.sql` once** (two settings rows). Until then the Design tab says so and nothing else changes.

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
`tests/test_my_designs.py`, `tests/test_studio_cards.py`.
