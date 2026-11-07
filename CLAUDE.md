# Standing rules for Semasa

## Anti slop
`antislop active: during (project instruction, Wan, 26 Oct 2026)`. The skills are in `.claude/skills/antislop*` (github.com/miqdadbadjuber/anti-slop
v3.2.23, MIT). Before UI, copy or comment work, load the core `antislop` skill and the one that matches the work: `antislop-ui`,
`antislop-layoutmobile`, `antislop-copywriting`, `antislop-code` (comments), `antislop-human`. The skill's mode question is already answered:
do not ask it again here.

- Text this system writes for the public goes through `backend/semasa/antislop.py` (`PROMPT` for the writer, `clean()` on what comes back).
  A new writer of public text gets both. `ops/ANTISLOP.md` says what is applied and lists the open findings.
- Wan's own voice outranks the filter (R-37): the film hooks, the connecting sentences between scenes and the closing line stay.
- Malaysian Malay only, never Indonesian (`motion.malaysian`, `compliance.json` `indo`).
- No em dash in anything a person reads. No fabricated number, name, quote or claim.

## Hooks and captions

`.claude/skills/hook-bank/SKILL.md` holds 25 fill-in-the-blank hook shapes in five groups
(CURIOSITY, TRANSFORM, VULNERABLE, BOLD, RELATABLE). `backend/semasa/hook_bank.py` carries the
same 25 (re-exported by `ideas.py` as `HOOK_FAMILIES`) and **every post's first line must be built
on one of them** (Wan, 6 Nov 2026: "25 hook tu wajib dalam ayat"). The writer is always given the
shapes its stream may use, numbered 1 to 25 in series order, and must say which in `"hook_shape"`.
An answer without a usable number (or with blanks left in the hook) is asked for once more; a second
miss fails the idea with a reason, so no post leaves without a shape. The same holds for "revise
with a note". The number and whether the caption opens with the hook are kept on the idea's `brief`
(`hook_shape`, `hook_in_caption`). If the bank changes, both copies change: the markdown is the
reference, the constant is what the writer actually sees.

The shapes are Malaysian Malay. A Malay post uses a shape as written; an English post (LinkedIn)
translates it faithfully. The rules above still outrank the shapes, and when no shape can be filled
without inventing a fact the writer takes a RELATABLE or CURIOSITY shape, which assert nothing.
VULNERABLE is withheld on the company stream by `OFF_BRAND`: first-person confession belongs to
Wan, never to ws.regulab. `hook_family` on an idea narrows the shapes to one family; it no longer
decides whether a shape is used.

A **hook style** made from screenshots (`ops/HOOK-STYLES.md`, `hook_styles.py`, `semasa_hook_styles`) replaces the built-in 25 and
their default guidance while it is selected (the default in `settings.hook_style`, or `brief.hook_style` on one idea): the same
requirement applies to ITS numbered shapes, and its instruction can never lift a rule (`hook_styles.LIFT` drops the sentences that try).

Pick the group by how much the post asserts: CURIOSITY and RELATABLE assert nothing,
BOLD asserts an opinion, TRANSFORM asserts a result, VULNERABLE asserts something about the
author. The higher the assertion, the higher the evidence bar, and rule 4 above already
forbids any invented fact.

Two hard limits that come from this repo's own rules, not from the format:

- A hook may not promise a figure, a duration, an approval or a cure. Blanks stay abstract
  until the source in `rules/` supports a specific.
- A VULNERABLE hook is first person about a named human. Never render one under a company
  identity; Semasa's public voice is the company.

