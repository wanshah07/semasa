# Backlog for Fable (Wan, 15 Nov 2026: "check deeply any bug or UI/UX problem but only list for fable do later on once weekly usage limit restart")

Nothing below has been changed. Each line says how sure it is: **verified** (seen in the live data, a screenshot or a run) or
**suspected** (read in the code, not reproduced). Fix in this order unless Wan says otherwise.

## Bugs

1. **Two devices editing Expert content overwrite each other** (suspected). The page saves the whole `settings.experts` row from
   what it holds. A phone and a desktop open at once, each adding a handle, leave only the later save. Fix: re-read the row just
   before saving and merge by category id and handle, or save only the changed category.
2. **A sweep with many Instagram handles may not finish** (suspected). `MAX_READS = 20` counts profile pages, but an Instagram
   profile is up to seven page loads (`PER_ACCOUNT_IG = 6` posts, each opened), and a Threads chain adds one more page. Twenty
   Instagram handles is about 140 loads, on top of the community and MYRA parts, inside the Sources workflow's 30-minute limit.
   Fix: count loads rather than profiles, and stop the experts part cleanly at a time budget, carrying the rest to the next sweep
   (the rotation is already there).
3. **A chain that grows after it was read is not updated** (verified by design). The feed row is keyed by the first part's address
   and a known address is skipped, so a part 3 added a day later never reaches the row. Fix: for a chain read in the last 3 days,
   compare `chain_urls` and re-analyse when it is longer.
4. **A Facebook or Instagram post's own `Translate` / "See more" text is not cleaned** (suspected). Only the Threads reader strips
   page labels. Check `social_web.py` output for "See more", "…" and "Translate" on real posts.
5. **`@quantum_thought_bot (Threads)` reads 0 posts with no error** (verified in the 14 Nov report). The page says nothing, the chip
   is orange. Either the account has nothing in 14 days or the name is wrong; the chip should say which (the profile page shows a
   "no threads yet" text when empty, and a not-found page otherwise).
6. **Source-lights stay green on "live: 0 read"** (verified: Reddit, Facebook and Instagram on 14 Nov, 12:25 UTC) because old rows are
   still inside the window. Correct by design, but it hides a source that has gone quiet for days. Consider orange after three
   sweeps with nothing new even when old rows are still shown.
7. **The AI brain keeps the old fragments of a healed chain** (known cost of this PR's heal). The brain gets the whole chain as a new
   reference, and the old part-by-part references already filed stay in Otak AI until Wan deletes them there.
8. **The unread `health_state` of 14 Nov 07:38 still listed the Facebook / Instagram / YouTube lines at 21:00** (verified): the watchdog
   refreshes every six hours, so a fixed problem can show for up to six hours. Fine, but worth saying on the card ("last checked").

## UI / UX

1. **Expert content on a phone: the first post starts 2,193 px down** (verified, 390 px wide). The three left cards (handles,
   suggestions, settings) come before the posts. Fix: posts first on a phone, the three cards behind a "Manage accounts" button
   or a bottom sheet; keep the two-column layout from `lg` up.
2. **Isu semasa's tab row is ten pills tall on a phone** (verified in a screenshot: five wrapped rows before any content). Make it one
   horizontal scrolling row, with the open tab scrolled into view, and keep the status line under it.
3. **No way to see a handle's own posts** (suggested). A handle row could open the feed filtered to that owner (the filter exists,
   `who`); today it is a dropdown that only appears with more than one account.
4. **No count of what was hidden as off the niche per handle** (suggested). Wan sees `0 posts` and cannot tell "nothing posted" from
   "everything judged off the niche" (hamiddi_ and m0d0 each have several hidden markers). Show "5 read, 3 shown, 2 hidden".
5. **"Worth following" has no way to ask again today** (verified: AI list empty since the daily search ran at 12:14 UTC and found only
   accounts already followed). A "search again" button, rate-limited, would answer "why is it empty".
6. **Brain switch changes are silent about the past**: turning it on files only new posts. Say so, and offer "send the last 14 days".
7. **Original post card cuts at five lines on a phone** with "Show all"; for a chain of four parts that is the first paragraph only.
   Show part by part, collapsed, with the part number.
8. **The two toasts stack over the Worth-following card** (verified in the screenshot) and hide the buttons for five seconds. Put toasts
   at the top on a phone, or shorten the time for a plain "saved".
9. **Category settings is closed by default and carries no hint that the brain switch lives inside** except a small "AI brain on" label.
   Move the switch to the category tab row as a toggle.
10. **Dashboard status card has ten tiles at five columns**: two even rows on a wide screen, but 5 rows of 2 on a phone. A compact one-line
    version (dots only, details on press) would leave room on Papan.

## Done in this change (not backlog)

- Threads chains are read as one post (verified live against a real profile: 2- and 4-part chains joined, paragraphs and links kept).
- Chains already stored part by part are replaced once, automatically.
- One owner can have a different username on each platform.
