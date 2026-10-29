"""Revision-bound approvals and provider-independent publishing contracts.

A content package is atomic: caption, account, scheduled moment and immutable media
identities travel together. Provider routing is explicit; no provider failure may
silently select another provider.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class MediaAsset:
    asset_id: str
    url: str
    mime: str
    data: bytes = field(repr=False)
    sha256: str
    size: int = 0
    duration: float | None = None


@dataclass(frozen=True)
class ContentPackage:
    post_id: str
    caption: str
    channel: str
    integration_id: str
    scheduled_at: str
    timezone: str
    idempotency_key: str
    assets: tuple[MediaAsset, ...]
    expected_media: tuple[str, ...] = ()


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def media_identity(row: dict[str, Any]) -> dict[str, Any]:
    meta = row.get("meta") or {}
    return {
        "id": row.get("id"),
        "url": row.get("generated_media_url"),
        "type": row.get("type"),
        "mime": meta.get("mime") or ("video/mp4" if row.get("type") == "video" else "image/jpeg"),
        "sha256": meta.get("sha256"),
        "bytes": meta.get("bytes"),
        "seconds": meta.get("seconds"),
        "slide_urls": meta.get("slide_urls") or [],
    }


def approval_token(post: dict[str, Any], media: list[dict[str, Any]], accounts: dict[str, str]) -> str:
    """The approval token is a hash, not authority to publish; the existing user gate is the authority."""
    channels = post.get("channels") or ([post.get("stream")] if post.get("stream") == "linkedin" else [])
    scheduled_at = f"{post.get('date')}T{post.get('slot')}:00+08:00" if post.get("date") and post.get("slot") else None
    material = {
        "post_id": post.get("id"),
        "provider": post.get("provider"),
        "stream": post.get("stream"),
        "content_sha256": _sha({"text": post.get("text"), "lang": post.get("lang"), "citation": post.get("citation")}),
        "media_sha256": _sha([media_identity(m) for m in media]),
        "channels": channels,
        "scheduled_at": scheduled_at,
        "timezone": "Asia/Kuala_Lumpur",
        "account_ids": {c: accounts.get(c) for c in channels},
    }
    return _sha(material)


def approval_valid(post: dict[str, Any], media: list[dict[str, Any]], accounts: dict[str, str]) -> bool:
    return bool(post.get("approval_token")) and post["approval_token"] == approval_token(post, media, accounts)


def provider_for(post: dict[str, Any], settings: dict[str, Any]) -> str:
    explicit = post.get("provider")
    if explicit in ("postiz", "buffer", "composio"):
        return explicit
    publishing = settings.get("publishing") or {}
    configured = (settings.get("channels") or {}).get("postiz") or {}
    if publishing.get("default_provider") == "postiz" and configured.get("enabled") is True:
        return "postiz"
    return "composio" if post.get("stream") == "linkedin" else "buffer"


def fallback_allowed(record: dict[str, Any]) -> bool:
    """Only a definitive pre-acceptance refusal permits an operator to choose a backup."""
    return record.get("outcome") == "refused" and record.get("remote_accepted") is False


def supports(channel: str, mimes: list[str]) -> bool:
    if channel == "instagram" and not mimes:
        return False
    if "video/mp4" in mimes and len(mimes) != 1:
        return False  # native video is a standalone package, never dropped for images
    return all(m in ("video/mp4", "image/jpeg", "image/png", "image/webp", "image/gif") for m in mimes)


def media_bytes(row: dict[str, Any], data: bytes) -> tuple[str, int]:
    expected = (row.get("meta") or {}).get("sha256")
    actual = hashlib.sha256(data).hexdigest()
    if not expected or expected != actual:
        raise ValueError("media SHA-256 is missing or does not match the approved bytes")
    return actual, len(data)
