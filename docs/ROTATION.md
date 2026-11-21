# Hooks and poster looks take their turn (Wan, 20 Nov 2026)

> "make sure hook sentiasa berubah, tak berulang dan ikut turutan" · "follow turn not repeat"

**What was wrong.** The writer was told to pick the hook shape that fitted the story best, so it picked the same one: shape 16
("Semua orang cakap ___, tapi realitinya ___") opened nearly every recent post, and every poster was drawn in the one default look
(`hand` for LinkedIn, `image` for the rest).

**What happens now** (`backend/semasa/rotation.py`, used by `ideas.process_idea`):

- **Hooks.** The shapes come round in a fixed turn that moves through the families, so two posts in a row never share a shape or
  a family: 1, 6, 16, 21, 2, 7, 17, 22, ... (ws.regulab has no first-person family, LinkedIn has all five). Each stream keeps its
  own place, read from the last ideas it wrote (`brief.hook_shape`). The writer is told THIS post's shape, two fall-backs for when
  it cannot be filled without inventing a fact, and the last eight hooks so it does not echo their opening words. A shape that is
  not its turn is asked for once more; after that what the writer gave stands, so a post is never lost to the rotation.
- **Looks (ws.regulab).** A carousel or a poster whose idea names no look takes the next Semasa poster look: hand-drawn, marker poster, torn
  paper, colour blocks, neon, cardboard, chalkboard, line map, torn strips, grid, Semasa's own. Looks Wan hid in the picker
  (`default_design.hidden`) are skipped, and one is not used again until four others have been. The look is stored on the idea
  (`brief.look`), which is how the next post knows where the turn is. `photo`, `image` and `threads` need a picture and stay a hand
  choice.
- **Every post that is not a film is a poster look.** Auto-fill makes a slot set to `single` (or to nothing) a Semasa poster, one
  4:5 artwork, for both streams, so ws.regulab and LinkedIn are drawn in the same looks. Carousels keep their slides and take the
  turn's look too.
- **Wan's own choice wins.** In the New idea composer, a look he picks is sent and kept. With nothing picked the composer says the
  turn will be used and sends no look.

**LinkedIn writing.** The LinkedIn writer now gives 5 to 8 NUMBERED facts (250 to 380 words), each with its exact figure, entry,
clause or date from the source, and ends with no invitation: no "follow me", no "as a formulator" or any "as a ..." about the
author, no reader addressed by job title.

**Blocker removed.** `orang dalam` is no longer a blocking phrase (`rules/compliance.json`).

Posts already written are not changed: their hooks and looks stay as they are.

## LinkedIn and the news (Wan, 20 Nov 2026)

> "for linkedn, no need include idea from recent issue unless berkaitan regulatory, circular from authority etc"

Auto-fill already never takes a newspaper story for a LinkedIn slot. The ideas that still reached LinkedIn on 19 and 20 Nov (an organ
donor, a wasp-sting rescue, a wrongly removed ovary, an awards list) came from a headline turned into an idea by hand, usually for
both streams at once. The worker now judges them (`ideas.linkedin_news_gate`): an idea whose source is a headline from the issue
feed (`trend_id`) is written for LinkedIn only when it names an act of an authority (a circular, guideline, regulation or law,
recall, ban, seizure, licence, registration, approval, enforcement, standard, fatwa, or a named product regulator). Otherwise it
stops with a plain sentence, before any writer is paid, and the writer is also told to decline such a story. A note Wan writes on the
idea overrides the gate (his own words are his decision). Regulator rows, papers, the websites he lists and the folder bank are
never judged.

## LinkedIn keeps one look (Wan, 21 Nov 2026)

> "I want like this for linkedn" (the clean Image slide: cream paper, a serif title, sans text, the source at the foot)

LinkedIn does not take turns. Its carousels and posters are the **Image look on plain cream paper**, with no blurred photo behind
the words (`rotation.STREAM_LOOK`, `ideas.slide_ground`). A look Wan picks on the idea still wins. ws.regulab keeps its turn.
Posts already written keep the look they were drawn in.
