# Hook styles from screenshots (Wan, 6 Nov 2026)

The 25 built-in hook shapes are required in every post (`backend/semasa/hook_bank.py`). A **hook style** replaces them: Wan adds
screenshots of hooks he likes, the bot writes an instruction and its own fill-in-the-blank shapes, and while the style is selected
the writer must build every post's first line on one of ITS shapes, with ITS instruction in place of the default guidance.

## Add a style (Tetapan tab, Hook styles from screenshots)
1. Optional name, then up to 8 screenshots (PNG, JPG, WEBP) of the hook line: a post, a reel caption, a carousel cover.
2. **Analyse and make the style.** The files go to `semasa-reference/<your uid>/`; the database wakes the **Hook styles** workflow.
3. About a minute or two later the style says *Ready* with its shapes. **Edit** shows the instruction and the shapes: change them,
   one shape a line, `___` for every specific (`bold | Stop buat ___ kalau kau nak ___` sets the family). Fewer than 3 shapes is refused.
4. **Use as default** makes it the style of every new post. Pick it on one idea instead from the idea form (**Hook style**); a pick on
   the idea beats the default, and **The built-in 25** brings the original bank back for that idea.
5. **Delete** (two clicks) removes the style and its screenshots, and clears the default if it pointed at it.

## What the bot does (`backend/semasa/hook_styles.py`)
* Reads each screenshot with the picture reader (`describe_image`): the hook lines, language, format, voice, devices.
* Asks the writer for `{name, summary, instruction, shapes}`. A shape is a PATTERN: every name, brand, number, product, place and
  result becomes `___`; an example sentence is never copied.
* Cleans what came back: blanks written any way become `___`; a shape needs 1 to 5 blanks, 12 to 160 characters and some fixed
  wording, with no link, handle, hashtag or em dash; duplicates go; at least 3 must survive (one retry, then it fails with advice).
* Drops any instruction sentence that tries to lift a rule ("ignore the rules above", "make up a statistic", "you are now ...").
* Reads only screenshots that sit in the style creator's own folder.

## How the writer uses it (`hook_bank.py`)
The required-hook block is the same for the built-in 25 and for a style: numbered shapes, `"hook_shape"` in the answer, one retry,
then the idea fails with a reason. The style's instruction replaces the default guidance only; the requirement and the guardrails
(no invented figure, duration, approval or cure; the rules above outrank it; no underscores left) stay. A style whose family is
`vulnerable` is withheld on ws.regulab like the built-in confessions. A style that is deleted, not ready or unreadable falls back to
the built-in 25: a post is still written. The idea's `brief` records `hook_shape` and `hook_style`.

## Needs
`supabase/060_hook_styles.sql` (table, policies, the wake-up trigger, the `hook_style` setting row), a picture-reading model (the
AI tab's picture reader or `VISION_MODEL`), and the same Vault dispatch token as the other wake-ups.
