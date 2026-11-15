# Backlog of 15 Nov 2026: what was done with it

Wan, 15 Nov 2026: "check deeply any bug or UI/UX problem but only list for fable do later", then "use md.file to fix". Every
item of the list is below with what was done. **Proven** means driven in a browser or run against the real platform;
**tested** means covered by the repo's tests only; **not proven** says what is still unverified.

## Bugs

1. **Two devices editing Expert content overwrote each other.** Fixed. A save now reads the setting as it is stored at that
   moment, applies the one change to it, and saves that. Proven in a browser: a handle added "on the phone" after the desktop
   page loaded survived the desktop's next save.
2. **A sweep with many Instagram handles might not finish.** Fixed. The budget is counted in page loads (Threads 1, Facebook 1,
   Instagram 7; 60 a sweep) and the part stops cleanly after 12 minutes. Accounts not reached go first next sweep, and the page
   says the sweep stopped and how many were left. Tested.
3. **A chain that grows after it was read was not updated.** Fixed. A chain now longer than the stored one (or a single post
   that has since been carried on) is read again whole; a post Wan had hidden stays hidden. Tested.
4. **Facebook and Instagram expert posts were cut at 500 characters, Facebook at "See more".** Fixed for both caps (now 4,000).
   Facebook: every "See more" is opened before reading and paragraphs are kept (tested against a page built for the test).
   **Not proven:** on real Facebook with the saved login, and whether Instagram's own page description carries a whole long
   caption (that is Instagram's text, read as given).
5. **`@quantum_thought_bot` read 0 posts with no reason.** Fixed, and a worse bug found beside it. Checked live: that account's
   newest post is from November 2024, so the chip now says "newest post is N days old, outside the 14-day window". The worse
   bug: Threads sends a visitor to its login page for a username that does not exist, the sweep read that as "Threads asked
   for a login" and **stopped every other Threads read of that sweep**. A missing account is now reported as "account not found
   or private" for that handle only. Proven live for both cases; tested.
6. **Lights stayed green on "0 read" because of old rows.** Fixed. Green for a quiet sweep or two; after three sweeps in a row
   with nothing read the light turns orange and reaches the watchdog, even when older rows are still on show. Tested.
7. **The AI brain kept the old pieces of a healed chain.** Fixed. When a chain replaces its pieces, the sweep's own old
   references to those pieces are removed from the brain, with the entries read from them. An entry Wan edited or pinned
   stays, and so does anything he dropped in himself. Tested.
8. **A fixed problem could still show for up to six hours.** No change needed: nothing in the page shows that list (it is the
   watchdog e-mail's own state), and the Papan status card already says when the watchdog last updated.

## UI / UX

1. **Posts first on a phone.** Done. The three account cards open from "Manage accounts"; the first post moved from 2,193 px
   down to 649. Proven at 390 px wide.
2. **Isu semasa's tab row.** Done. One scrolling row on a phone (44 px tall instead of five wrapped rows), the open tab scrolled
   into view. Proven.
3. **See one account's posts.** Done. Pressing an account's name filters the feed to that owner; a chip clears it. Proven.
4. **Counts per account.** Done. Each account shows "N shown · N off the field · N hidden by you". Proven.
5. **Search again for accounts worth following.** Done, at most once an hour. An empty list now says why (for example "found 6
   authors, 2 already followed; the bot judged 4 and none showed enough depth"). Proven in the page; the search itself tested.
6. **Brain switch and the past.** Done. Turning it on says it files new posts only, and "Send the N posts already here" sends
   the rest. Proven in a browser.
7. **Chains in a card.** Done. Shown part by part, numbered; closed, the first part with "Show all N parts". Proven.
8. **Toasts covering buttons.** Done. Top of the screen on a phone, bottom right on a wide screen, and a plain "saved" stays
   2.6 seconds instead of 5 (a failure stays 7). Applies to the whole app.
9. **Brain switch visibility.** Done. It is a switch in the open category's bar, not inside the closed settings card.
10. **Dashboard status card on a phone.** Done. A chip a source, then only the sources that need a look with their reasons.
    Proven.

## Still open

- Facebook "See more" and long Instagram captions need one real sweep with a Facebook or Instagram expert account to be proven.
- The Expert page's blurb is hidden on a phone to bring the posts up; say if it should stay.
