"""Prove both roads out BEFORE the night they are needed, sending nothing (senders-probe.yml, run by hand).

  Buffer   — the key opens the account; the organization and the three ws.regulab channel ids in settings exist there;
             the plan's scheduled-post cap, and how many posts each channel holds now.
  Composio — the key opens the project; exactly one ACTIVE LinkedIn connection is visible to it; and a picture can be
             put through the presigned upload that a card post uses (a 1-pixel JPEG: uploaded, never posted).

Nothing here creates, edits or deletes a post anywhere. It prints what it found and exits 1 if either road is shut.
"""

from __future__ import annotations

import io
import os
import sys
from datetime import UTC, datetime, timedelta

from PIL import Image

from . import db, publisher, senders
from .config import SupabaseSettings


def check_buffer(settings: dict) -> list[str]:
    key = os.environ.get("BUFFER_API_KEY")
    cfg = (settings.get("channels") or {}).get("buffer") or {}
    if not key:
        return ["Buffer: BUFFER_API_KEY secret is not set"]
    if not cfg.get("organizationId"):
        return ["Buffer: settings 'channels' has no buffer.organizationId (run supabase/023_go_live.sql)"]
    b = senders.Buffer(key, cfg["organizationId"])
    try:
        acct = b._gql("query { account { organizations { id name limits { scheduledPosts } } } }")
        orgs = {o["id"]: o for o in (acct.get("account") or {}).get("organizations") or []}
        if cfg["organizationId"] not in orgs:
            return [f"Buffer: the key opens {len(orgs)} organization(s) but not {cfg['organizationId']}"]
        org = orgs[cfg["organizationId"]]
        print(f"Buffer: organization '{org['name']}', {org['limits']['scheduledPosts']} scheduled posts per channel")
        chans = b._gql("query($input: ChannelsInput!) { channels(input: $input) { id service name isDisconnected } }",
                       {"input": {"organizationId": cfg["organizationId"]}}).get("channels") or []
        by_id = {c["id"]: c for c in chans}
        now = datetime.now(UTC)
        problems = []
        for svc in ("facebook", "instagram", "threads"):
            c = by_id.get(cfg.get(svc) or "")
            if not c:
                problems.append(f"Buffer: no channel {cfg.get(svc)} for {svc}")
                continue
            held = b.posts([c["id"]], now.isoformat(), (now + timedelta(days=30)).isoformat())
            waiting = sum(1 for p in held if p.get("status") == "scheduled")
            print(f"Buffer: {svc} = '{c['name']}' ({c['service']}){' DISCONNECTED' if c['isDisconnected'] else ''}, "
                  f"{waiting} post(s) scheduled")
            if c["isDisconnected"] or c["service"] != svc:
                problems.append(f"Buffer: {svc} channel is disconnected or is not {svc}")
        return problems
    except senders.SendError as exc:
        return [f"Buffer: {exc.message}"]


def check_composio(settings: dict) -> list[str]:
    key = os.environ.get("COMPOSIO_API_KEY")
    cfg = (settings.get("channels") or {}).get("linkedin") or {}
    if not key:
        return ["Composio: COMPOSIO_API_KEY secret is not set"]
    if not cfg.get("author"):
        return ["Composio: settings 'channels' has no linkedin.author (run supabase/023_go_live.sql)"]
    li = senders.LinkedIn(key, cfg["author"], account_id=cfg.get("account_id") or None)
    try:
        acct = li.account()
        print(f"Composio: LinkedIn connection {acct} is active")
        buf = io.BytesIO()
        Image.new("RGB", (1, 1), (255, 255, 255)).save(buf, "JPEG")
        up = li.upload(buf.getvalue(), "probe.jpg", "image/jpeg")
        print(f"Composio: a picture uploads (key {up['s3key'][:12]}…); nothing was posted")
        return []
    except senders.SendError as exc:
        return [f"Composio: {exc.message}"]


def main() -> int:
    store = db.client(SupabaseSettings.load())
    settings = publisher.load_settings(store)
    print(f"Publishing switch: {'ON' if publisher.publishing_on(settings, datetime.now(UTC)) else 'off'} "
          f"({settings.get('publishing')})")
    problems = check_buffer(settings) + check_composio(settings)
    for p in problems:
        print("PROBLEM:", p)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write("## Senders probe\n\n" + ("\n".join(f"- {p}" for p in problems) or "Both roads open.") + "\n")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
