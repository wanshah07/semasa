"""Zernio publish — the publish-only half, for Hermes to trigger.

Publishes a FINISHED film to the social platforms through Zernio, using the account ids
already configured in `semasa_settings.channels.zernio` and the API keys held in the repo's
secrets (ZERNIO_API_KEY_1/2/3). This does NOT render, import, draft or approve anything: it
only hands the film + captions to Zernio's queue (or publishes now when no `--scheduled-for`
is given). Wan's go-ahead is the trigger; nothing here overrides his approval.

The film must already be at a public https URL. Channels are a subset of the platforms Zernio
holds (settings.channels.zernio.accounts); TikTok takes a video only, which is what this sends. The film is sent in
the shape the platforms take (upright 9:16, film_ratio): a 16:9 film from Hermes gets a fitted copy first.

Usage (run by hand, or via .github/workflows/zernio-publish.yml):
  python -m semasa.zernio_publish \
    --video-url https://.../film.mp4 \
    --channels facebook,instagram,tiktok \
    --captions-json '{"facebook":"...","instagram":"...","tiktok":"..."}' \
    [--scheduled-for 2026-11-21T08:00:00+08:00]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any

from . import db, film_ratio
from .config import SupabaseSettings
from .log import get_logger
from .publisher import ZERNIO_FORMATS, load_settings, zernio_accounts, zernio_extra_accounts, zernio_hub

log = get_logger("semasa.zernio_publish")

VIDEO_PLATFORMS = ("instagram", "facebook", "tiktok")   # a film never goes to Threads (Wan, 22 Nov 2026)


def _captions(raw: str, channels: list[str]) -> dict[str, str]:
    """{channel: caption} from the JSON object given on the command line. `channels` is the list to send to."""
    if not raw:
        return {}
    obj = json.loads(raw)
    if not isinstance(obj, dict):
        raise SystemExit("--captions-json must be a JSON object of {channel: caption}")
    return {c: str(obj[c]).strip() for c in channels if str(obj.get(c) or "").strip()}


EXTRA_NAME = re.compile(r"^[a-z][a-z0-9_]{2,30}$")


def _channels(raw: str) -> list[str]:
    """The channels asked for: a film platform, or the name of an extra account in settings (the cat series' own TikTok is
    `tiktok_cats`); `run` refuses a name settings does not hold."""
    out = [c.strip() for c in (raw or "").split(",") if c.strip()]
    bad = [c for c in out if c not in VIDEO_PLATFORMS and not (EXTRA_NAME.match(c) and "_" in c)]
    if bad:
        raise SystemExit(f"unknown channel(s): {', '.join(bad)} "
                         f"(allowed: {', '.join(VIDEO_PLATFORMS)}, or an extra account name)")
    return out


def run(
    store: Any,
    video_url: str,
    channels: list[str],
    captions: dict[str, str],
    scheduled_for: str | None = None,
) -> dict[str, Any]:
    settings = load_settings(store)
    zcfg = (settings.get("channels") or {}).get("zernio") or {}
    accounts = zernio_accounts(zcfg)
    extra = zernio_extra_accounts(zcfg)
    if not accounts:
        raise SystemExit("Zernio is not enabled (settings.channels.zernio.enabled is not true)")
    hub = zernio_hub(zcfg)
    if hub is None:
        raise SystemExit("no Zernio sender: the ZERNIO_API_KEY_* secrets are not set for the configured accounts")
    formats = {**ZERNIO_FORMATS,
               **{k: tuple(v) for k, v in (zcfg.get("formats") or {}).items() if isinstance(v, list)}}
    due_at = (scheduled_for or "").strip() or None
    out: dict[str, Any] = {}
    fitted: list[dict[str, Any]] = []
    for channel in channels:
        acc = accounts.get(channel) if channel in VIDEO_PLATFORMS else extra.get(channel)
        if acc is None:
            out[channel] = {"error": f"no Zernio account id for {channel} in settings.channels.zernio.accounts or .extra"}
            continue
        service = acc.get("platform") or channel                 # an extra account names the platform it lives on
        if "video" not in formats.get(service, ()):
            out[channel] = {"error": f"{channel} is not configured to take a video (formats: {formats.get(service)})"}
            continue
        # an extra TikTok carries its own caption, else the main TikTok's, else the Instagram one (TikTok reads that)
        caption = captions.get(channel) or ""
        if not caption and channel != service:
            caption = captions.get(service) or captions.get("instagram") or ""
        # Every channel here is a ws.regulab one, which takes the stream's shape (upright 9:16): a film of another shape (Hermes /
        # Nous, usually 16:9) goes as a fitted copy, made once for all of them (film_ratio). When the copy cannot be made no
        # channel gets the film in the wrong shape.
        if not fitted:
            try:
                fitted.append(film_ratio.for_stream(store, {"url": video_url}, "regulab"))
            except Exception as exc:  # noqa: BLE001 - nothing wrong-shaped goes to a platform
                fitted.append({"error": getattr(exc, "message", str(exc))})
        video = fitted[0]
        if video.get("error"):
            out[channel] = {"error": video["error"]}
            continue
        rec = hub.create_video(acc["id"], service, caption, video, due_at)
        out[channel] = {"id": rec.get("id"), "status": rec.get("status"), "due_at": rec.get("dueAt") or "now"}
        log.info("zernio publish %s: %s", channel, out[channel])
    return out


def list_accounts() -> int:
    """Which Zernio login holds which social account (ids, platforms and names only, never a key): to find the `key` an account
    belongs to before it is added to settings.channels.zernio. One line per account, for each ZERNIO_API_KEY_<n> that is set."""
    from . import senders
    found = 0
    for n in ("1", "2", "3", "4", "5"):
        secret = os.environ.get(f"ZERNIO_API_KEY_{n}")
        if not secret:
            continue
        try:
            accounts = senders.Zernio(secret).accounts()
        except Exception as exc:  # noqa: BLE001 - one login failing must not hide the others
            print(f"key {n}: could not list accounts ({str(exc)[:120]})")
            continue
        for a in accounts:
            found += 1
            print(f"key {n}: {a.get('_id') or a.get('id')}  {a.get('platform')}  "
                  f"{a.get('username') or a.get('displayName') or a.get('name') or ''}  "
                  f"{'ACTIVE' if a.get('isActive', True) else 'inactive'}")
    print(f"{found} account(s) in total")
    return 0 if found else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Publish a finished film to social platforms via Zernio.")
    ap.add_argument("--list-accounts", action="store_true", help="print which login holds which account, and stop")
    ap.add_argument("--video-url", default="")
    ap.add_argument("--channels", default="facebook,instagram,tiktok")
    ap.add_argument("--captions-json", default="{}")
    ap.add_argument("--scheduled-for", default="")
    args = ap.parse_args()

    if args.list_accounts:
        return list_accounts()
    if not args.video_url:
        raise SystemExit("--video-url is required")
    channels = _channels(args.channels)
    captions = _captions(args.captions_json, channels)
    store = db.client(SupabaseSettings.load())
    try:
        result = run(store, args.video_url, channels, captions, args.scheduled_for)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - the summary below still prints the reason
        log.exception("zernio publish failed")
        print(f"error: {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    failed = [c for c, r in result.items() if r.get("error")]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
