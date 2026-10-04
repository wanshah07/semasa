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

## Event posters and "the same background" (4 Oct 2026)

Wan's example: a symposium poster (small label, boxed topic, two-weight headline, speakers with round pictures, big date, a pink glass
sphere behind it). Semasa now draws that kind of poster, and can make that kind of background:

* **ERA · Event poster** (`e_event`). Slide fields: `eyebrow` (SCIENTIFIC SYMPOSIUM), `lead` (the boxed topic; line 1 bold), `title`
  (`*bold phrase* light words *bold phrase*`), points (`Name | Country`, a round picture slot each), `note`
  (`Wednesday 30 Sep 2026 | 16:15 – 17:00 | Room: Hub 2`), `chip` (organiser). With **fit** on, any slide whose note holds a date and
  that has speaker points gets this design under every Studio look. A note that is not a date is drawn as plain bold lines.
* **Light backgrounds** keep dark ink and no scrim, automatically (`groundIsLight`), unless a scrim was chosen on purpose. Scrim
  **None** forces it. Photo-family designs stay dark.
* **Background from a reference.** The reader now describes the background the way an image generator wants it (subject, where it sits,
  hex palette, light, which part stays empty). Design → Background → *AI picture* has style starters (pink glass sphere, gel droplets,
  soft studio gradient, bright lab, leaves and dew) and *Like the reference* uses the reader's description. Cloudflare makes it free.
* **Canva**: the same poster was rebuilt in Canva (folder Carousel Studio) with the brand kit's colours, the real logo, the glass picture
  made by Canva, round picture slots, and live text.
