# Following an uploaded reference design

Design tab → upload a reference → **Rebuild** (layers) or **On the reference picture**. What keeps the rebuild faithful:

1. **Layout** – the AI reads boxes, roles, fonts and sizes once (`supabase/functions/semasa-chat/design.js`).
2. **Colours are measured, not guessed** – `lib/designFidelity.js snapLayout` replaces the AI's colours with the colours in the
   reference's own pixels: the background (flat, or a gradient along its own angle), every shape fill, every text block's ink.
   A block on a photograph keeps the AI's colour and is listed in the review ("on a photograph").
3. **Every rebuild is scored** – `compareImages` gives a 0–100 match (colour in Lab + edge structure on a 24×24 grid) and names the
   furthest cells. Shown in the review as "Match to the reference".
4. **A worse refine is thrown away** – up to 3 automatic AI refine passes; each result is drawn and scored, kept only if it is closer
   (`judgePass`), loop stops at 90% or when a pass no longer helps.
5. **Editable / replaceable** – text is real Kanvas text layers with the new words (font, size, colour editable); shapes are layers;
   the reference's picture areas and faces become dashed **Gambar (ganti)** boxes to drop a picture into; the reference's logo is never
   copied – ws.regulab's own logo is placed in its slot (LinkedIn gets none, rule 7).
6. **Canva** – the same reference can be rebuilt by the Canva bridge (`ops/CANVA.md`, job → import) when Kanvas is not enough.

Not committed: third-party reference posters. Tests draw their own pictures (`web/design_fidelity.test.mjs`).
