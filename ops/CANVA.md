# Canva: the bot builds a carousel and sends it back to Semasa

Wan, 4 Oct 2026: *"Rebuild the next carousel post in Canva. Create new project > Carousel Studio > Create Design > send to
semasa. This also applies to an uploaded reference design. The bot designs, not me."*

Canva is driven from a Claude session that has the Canva connector. Semasa cannot call Canva; its half is
`backend/semasa/canva_bridge.py`, run by `.github/workflows/canva-bridge.yml`.

## The run (what a session does when asked "rebuild the next carousel post in Canva")

1. **Queue.** Dispatch `canva-bridge.yml` with `action: queue`. The step summary prints the next carousel post (draft or approved,
   two or more slides; scheduled and posted are never offered) in full, and the newest uploaded reference design with no Canva
   rebuild yet. A post that already has a Canva set is not offered again.
2. **Folder.** Canva folder **Carousel Studio** (`FAHXCB-FJiQ`, created 4 Oct 2026). Every design goes in it (`move-item-to-folder`).
3. **Logo.** The real logo, never a text mark: upload `web/public/cards/logo-ink.png` (the logo trimmed to its visible mark,
   230×35) with `upload-asset-from-url` from its `raw.githubusercontent.com` address, and place it top-left on every page
   (left 72, top 56, 224×34 px: the same place and size Semasa's own cards draw it). ws.regulab only; a LinkedIn carousel
   carries no ws.regulab identity at all (rules/compliance.json, Studio rule 7).
4. **Brand kit.** Wan, 4 Oct 2026: apply the brand kit on the next one. Canva's plain `create-design` cannot apply a kit; the
   on-brand route is `generate-design` with `brand_kit_id` (`list-brand-kits`: today one kit, `kAGD2twp8yg`), then
   `create-design-from-candidate`. A second kit (say one for the LinkedIn byline) is made in Canva by Wan; the bot picks per
   stream. `generate-design` makes an `instagram_post` at 1080×1350, so a ws.regulab (1080×1080) post is resized with
   `resize-design` afterwards; LinkedIn's 1080×1350 needs no resize.
5. **Words.** Exactly the post's words: nothing added, dropped or reworded. Check them with `read-design` afterwards; the
   generator can split a headline across two boxes (fine) or put the closing page second (not fine: reorder it).
6. **Look at every page.** `read-design` thumbnails are often blank for a new design; an `edit-design` call with a no-change
   `update_title` returns the page picture, then `finalize: cancel`.
7. **Export** PNG at the card's size (`export-design`): 1080×1080 for ws.regulab, 1080×1350 for LinkedIn.
8. **Send.** Dispatch `canva-bridge.yml` with `action: import`, `post_id`, `urls` (the export addresses, in page order, a JSON list)
   and `design_url`. For a reference design use `job_id` instead of `post_id`. The addresses must be https on canva.com; a page of
   the wrong shape is refused by name; a 2× export is brought to size.

## What the import does, and does not

* A **draft** takes the pages at once as its slide set, replacing the earlier set (the earlier media row is kept; "Use this set"
  brings it back). Press **Generate slides** to go back to Semasa's own drawing.
* An **approved** post is not changed behind Wan's back: the pages are stored and the report says to move it back to draft.
* A **reference design** comes in beside the Semasa drawing as a new Design result and waits for Wan's Save.
* Nothing is approved, scheduled or sent by this path.

## Two things to know

* The repo is public, so the queue's step summary (the first post's words) and the import's inputs (Canva export addresses,
  which expire within the hour) are readable in the workflow run while it exists.
* Canva's API cannot set a font family on text, so a font the generator picked cannot be changed from a session; the brand kit is
  what pulls the fonts toward the house look.
