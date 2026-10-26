# Anti slop in Semasa

Wan, 26 Oct 2026: "apply github miqdadbadjuber/anti-slop untuk buang AI slop dalam sistem". The rules are github.com/miqdadbadjuber/anti-slop
(v3.2.23, commit 5ca57fe, MIT). It is a filter, not a style guide: it prescribes no colours, fonts or layouts, and Wan's direction stays his.

## What is applied

**1. The agent rules.** The six skills are vendored in `.claude/skills/antislop*` (core, copywriting, code comments, UI, mobile layout, people)
with the MIT licence beside the core. `CLAUDE.md` loads them for any session in this repo, in the skill's "during" mode.

**2. Text the system writes.** `backend/semasa/antislop.py`:
- `PROMPT` is handed to every writer whose words reach the public: the post writers in `ideas.py` (new draft and rewrite), the clip captions in
  `video.py`, the card words in `design.py`, the ad copy in `fragrance.py`, and the film script in `motion.py` (`PROMPT_FILM`, which keeps Wan's own hooks).
- `clean()` makes the machine-safe edits on what comes back: the em dash and the double hyphen, a decorative emoji that opens a line, a chatbot
  closer, "let's dive in", filler such as "in order to" and "dalam usaha untuk". It adds no word and touches no number, name or reference.
  It runs in `ideas.normalise_text` (every AI caption) and on every heading, line and narration of a film.
- The tells that need a person are `soft` rules with `"tell": true` in `rules/compliance.json`, so the page's scan and the publisher's scan
  name the same ones (empty vocabulary, significance inflation, fake-candid openers, "not just X, it's Y" and "bukan sekadar X, malah Y",
  unnamed authority, a generic upbeat ending, a clause in ALL CAPS). They are warnings in the post editor and never a block.
  `rules/cases.json` has three cases for them, run by pytest and `npm test`.

**3. The page's own words.** The em dashes in text a person reads (the card warnings, two Billing selects, the Fragrance description, the
error line) are plain punctuation now.

## Levels, to see whether it is better (Wan, 26 Oct 2026: "can buat berperingkat so we know if anti slop better or not")

`settings.antislop.level` is set in Tetapan (card "Anti slop berperingkat") and read by the worker before every post and film:
- `off`: the writers are not told the rules and nothing is edited. This is the control.
- `clean`: the machine edits only (`clean()`), the writers are not told the rules.
- `full`: the rules in every writer's prompt and the machine edits. The default, and what ran from 26 Oct.

Every post and film is scored by `antislop.hits()` (each edit `clean()` would make plus each tell that needs a person), once as the writer
wrote it and once after the edits, and one row goes to `semasa_antislop_log` (`supabase/052`) with the level in force. The card shows, per
level, outputs and slop per 1,000 characters written and left. Read it only once two levels have at least 10 outputs each: the three
levels run one after another on different ideas, so a small count is noise. The numbers count patterns, not quality; read a few of the
actual captions beside them before deciding.

## Where Wan's own voice outranks the filter

The skill says so itself (R-37: the owner's voice sample wins, and the conflict is named, not settled silently). These stay:
- the film hooks: Tahukah anda, Amaran, Berita terkini; Did you know, Warning, Breaking news (`motion_auto.hook_of`);
- the short connecting sentences between scenes ("Jadi kenapa ni penting?");
- the closing line of a film (`motion_styles.cta`), even though "follow kami" is a call to action elsewhere. Rule 7 of the post rules still
  bans a call to action in a caption.

## Findings (the skill's "after" mode). 1, 2 and 5 fixed on 26 Oct 2026 (Wan: "fix 1, 2 and 5, create in english version")

Priority follows the skill: Hard Gate is HIGH, Purpose-Gate MEDIUM, Quality Locks LOW.

1. FIXED, HIGH, R-02: the em dash that stood in for an empty value in tables, selects and printed documents is now "Tiada" / "None" (a
   bilingual pair in the page, `W.none` in the printed billing documents). Two pure helpers return an empty string and the caller says
   "Tiada / None" (`fmtMs`, `sizeLabel`); receipts with no date group under "Tiada tarikh / No date". Em dashes inside code comments and the
   `[,;:–—]` character class in `fromCaption.js` (a real splitter, not text) stay.
2. FIXED, MEDIUM, R-04: the Sparkles icon on "generate" buttons and tab icons is replaced by an icon that names what the button makes:
   ImagePlus (Jana gambar, Jana Wanshah, the Media lab tab and its log icon), Plus (More poses), Clapperboard (Buat video motion), Eye
   (Needs a look), FolderPlus (category made by Semasa), FileQuestion (the FAQ AI bar).
3. OPEN, MEDIUM, R-04: 56 files import the same thin-stroke Lucide set. It is the default icon-set look. Changing it is a design decision, not a clean-up.
4. OPEN, MEDIUM, R-06: 60 uppercase labels carry wide tracking. Check each against the brand's own type direction.
5. FIXED, LOW, R-16: the generic "Bot" label (140 lines of page text, Malay and English) now names the system, "Semasa" ("Semasa tulis ...",
   "Semasa writes ..."), and three buttons say what happens instead ("Hantar untuk ditulis / Send to be written"). Stored values named `bot`
   (`category_by`, the Log actor filter) and the worker's Malay log titles ("Bot menambah ...", matched by `LogTab`) are data and did not change.

Reply with the numbers to fix.
