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
(CURIOSITY, TRANSFORM, VULNERABLE, BOLD, RELATABLE). `backend/semasa/ideas.py` carries the
same 25 in `HOOK_FAMILIES` and hands the family set to the writer through `hook_block()`
when an idea names `hook_family`. If the bank changes, both copies change: the markdown is the
reference, the constant is what the writer actually sees.

The writer is told the shapes are optional and the rules above outrank them, and it is told to
drop the underscores. VULNERABLE is withheld on the company stream by
`HOOK_FAMILY_OFF_BRAND`: first-person confession belongs to Wan, never to ws.regulab.

Pick the group by how much the post asserts: CURIOSITY and RELATABLE assert nothing,
BOLD asserts an opinion, TRANSFORM asserts a result, VULNERABLE asserts something about the
author. The higher the assertion, the higher the evidence bar, and rule 4 above already
forbids any invented fact.

Two hard limits that come from this repo's own rules, not from the format:

- A hook may not promise a figure, a duration, an approval or a cure. Blanks stay abstract
  until the source in `rules/` supports a specific.
- A VULNERABLE hook is first person about a named human. Never render one under a company
  identity; Semasa's public voice is the company.

