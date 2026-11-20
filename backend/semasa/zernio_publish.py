"""Zernio publish — the publish-only half, for Hermes to trigger.

Publishes a FINISHED film to the social platforms through Zernio, using the account ids
already configured in `semasa_settings.channels.zernio` and the API keys held in the repo's
secrets (ZERNIO_API_KEY_1/2/3). This does NOT render, import, draft or approve anything: it
only hands the film + captions to Zernio's queue (or publishes now when no `--scheduled-for`
is given). Wan's go-ahead is the trigger; nothing here overrides his approval.

The film must already be at a public https URL. Channels are a subset of the platforms Zernio
holds (settings.channels.zernio.accounts); TikTok takes a video only, which is what this sends.

Usage (run by hand, or via .github/workflows/zernio-publish.yml):
  python -m semasa.zernio_publish \
    --video-url https://.../film.mp4 \
    --channels facebook,instagram,threads,tiktok \
    --captions-json '{"facebook":"...","instagram":"...","threads":"...","tiktok":"..."}' \
    [--scheduled-for 2026-11-21T08:00:00+08:00]
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from . import db, tiktok_ratio
from .config import SupabaseSettings
from .log import get_logger
from .publisher import ZERNIO_FORMATS, load_settings, zernio_accounts, zernio_hub

log = get_logger("semasa.zernio_publish")

VIDEO_PLATFORMS = ("instagram", "facebook", "threads", "tiktok")


def _captions(raw: str, channels: list[str]) -> dict[str, str]:
    """{channel: caption} from the JSON object given on the command line. `channels` is the list to send to."""
    if not raw:
        return {}
    obj = json.loads(raw)
    if not isinstance(obj, dict):
        raise SystemExit("--captions-json must be a JSON object of {channel: caption}")
    return {c: str(obj[c]).strip() for c in channels if str(obj.get(c) or "").strip()}


def _channels(raw: str) -> list[str]:
    out = [c.strip() for c in (raw or "").split(",") if c.strip()]
    bad = [c for c in out if c not in VIDEO_PLATFORMS]
    if bad:
        raise SystemExit(f"unknown channel(s): {', '.join(bad)} (allowed: {', '.join(VIDEO_PLATFORMS)})")
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
    if not accounts:
        raise SystemExit("Zernio is not enabled (settings.channels.zernio.enabled is not true)")
    hub = zernio_hub(zcfg)
    if hub is None:
        raise SystemExit("no Zernio sender: the ZERNIO_API_KEY_* secrets are not set for the configured accounts")
    formats = {**ZERNIO_FORMATS,
               **{k: tuple(v) for k, v in (zcfg.get("formats") or {}).items() if isinstance(v, list)}}
    due_at = (scheduled_for or "").strip() or None
    out: dict[str, Any] = {}
    for channel in channels:
        acc = accounts.get(channel)
        if acc is None:
            out[channel] = {"error": f"no Zernio account id for {channel} in settings.channels.zernio.accounts"}
            continue
        if "video" not in formats.get(channel, ()):
            out[channel] = {"error": f"{channel} is not configured to take a video (formats: {formats.get(channel)})"}
            continue
        caption = captions.get(channel) or ""
        video = {"url": video_url, "vertical": True}
        if channel == "tiktok":
            # TikTok takes upright 9:16 only: a landscape film from Hermes gets an upright copy first (tiktok_ratio)
            try:
                video = tiktok_ratio.for_tiktok(store, video)
            except Exception as exc:  # noqa: BLE001 - this channel fails; the others still go
                out[channel] = {"error": getattr(exc, "message", str(exc))}
                continue
        rec = hub.create_video(acc["id"], channel, caption, video, due_at)
        out[channel] = {"id": rec.get("id"), "status": rec.get("status"), "due_at": rec.get("dueAt") or "now"}
        log.info("zernio publish %s: %s", channel, out[channel])
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Publish a finished film to social platforms via Zernio.")
    ap.add_argument("--video-url", required=True)
    ap.add_argument("--channels", default="facebook,instagram,threads,tiktok")
    ap.add_argument("--captions-json", default="{}")
    ap.add_argument("--scheduled-for", default="")
    args = ap.parse_args()

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
