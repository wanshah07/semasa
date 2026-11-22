"""`python -m semasa.draft_announce`: tell Wan on Telegram about every new draft, of both streams, with its pictures and its
Approve / Reject buttons (Wan, 22 Nov 2026: "hantar ke telegram setiap kali siap post draft untuk both ws dan linkedin untuk
dapatkan approval").

The last step of every workflow whose worker writes drafts (media.yml: ideas → drafts → pictures; motion.yml: the daily comic and
imported videos), so a draft is announced in the same run its picture is drawn, not at the Telegram worker's next scheduled run
(GitHub skips those often: none ran overnight on 21-22 Nov, and three drafts written then were never sent). The Telegram worker
announces too, as the net. Each draft once (telegram_bot.push_new_drafts). Quietly nothing without TELEGRAM_BOT_TOKEN or a linked
account. Never fails the job.
"""

from __future__ import annotations

import sys

from . import db, telegram_bot
from .log import get_logger

log = get_logger("semasa.draft_announce")


def main() -> int:
    try:
        out = telegram_bot.announce(db.client())
    except Exception as exc:  # noqa: BLE001 - an announcement must never turn a worker's run red
        log.warning("drafts not announced: %s", telegram_bot.scrub(exc)[:300])
        return 0
    print(f"Draft announcements: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
