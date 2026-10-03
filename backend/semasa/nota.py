"""Nota regulatori: the landing page's list of what ws.regulab has posted, fed from Semasa (Wan, 3 Oct 2026: port what Studio did
that Semasa did not). Entry point: `python -m semasa.nota <out_dir>` (a step of publish.yml, after the publisher).

Studio's release Routine dumped its ws.regulab drafts to disk and ran `tools/notes_from_studio.py` in
`wanshah07/malaysian-regulatory-affairs`, which turned the posted ones into `site/src/data/notes.json`. The RULES for what may
appear (public link confirmed, a citation, no [SAHKAN], no competitor, dated today or earlier) live in that repo and stay
there. This module does only the first half: it writes Semasa's posted ws.regulab posts to disk in the SAME shape Studio's
drafts had, so `tools/notes_from_semasa.py` in that repo applies the same rules to them. Nothing here reads a caption: a note
is the post's hook, its citation and the public links, which are already public on the platforms.

A channel counts as sent only when Buffer says so (`published.<ch>.status == "sent"`) and gave a link; Semasa's own record keeps
the link under `url`, a post brought over from Studio keeps Buffer's `externalLink`: either is read.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from . import db
from .config import SupabaseSettings
from .log import get_logger

log = get_logger("semasa.nota")

LIVE = ("scheduled", "posted")          # a post can be sent on one channel and still waiting on another


def doc_of(post: dict[str, Any]) -> dict[str, Any]:
    """One post in the shape tools/notes_from_studio.py reads."""
    channels: dict[str, Any] = {}
    for ch, rec in (post.get("published") or {}).items():
        if not isinstance(rec, dict):
            continue
        link = rec.get("url") or rec.get("externalLink")
        if rec.get("status") == "sent" and link:
            channels[ch] = {"status": "sent", "externalLink": link}
    return {"stream": post.get("stream") or "regulab", "status": post.get("status"), "date": str(post.get("date") or "")[:10],
            "domain": post.get("domain") or "", "hook": post.get("hook") or "", "citation": post.get("citation") or "",
            "angle": "", "published": channels}


def dump(store: Any, out_dir: str | Path) -> dict[str, int]:
    """Write every ws.regulab post that is scheduled or posted, one JSON file each, into an EMPTY directory."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for stale in out.glob("*.json"):               # a leftover file would be read as a current post
        stale.unlink()
    rows = (store.table(db.POSTS).select("id,stream,status,date,domain,hook,citation,published")
            .eq("stream", "regulab").in_("status", list(LIVE)).execute().data or [])
    n = linked = 0
    for p in rows:
        d = doc_of(p)
        (out / f"{p['id']}.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        n += 1
        linked += bool(d["published"])
    return {"posts": n, "with_a_public_link": linked}


def main() -> int:
    if len(sys.argv) != 2:
        log.error("usage: python -m semasa.nota <out_dir>")
        return 2
    store = db.client(SupabaseSettings.load())
    counts = dump(store, sys.argv[1])
    log.info("nota: %s", counts)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(f"## Nota regulatori (dump)\n\n{counts['posts']} ws.regulab post(s), "
                     f"{counts['with_a_public_link']} with a public link\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
