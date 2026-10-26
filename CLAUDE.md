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
