"""Postiz public API adapter (verified against Postiz public.integrations.controller).

Postiz has no idempotency header on POST /public/v1/posts. Semasa therefore uses
Postiz's ``group`` field as its stable key, searches the scheduled date window
before any retry, and treats transport/5xx outcomes as unknown until readback.
"""

from __future__ import annotations

import mimetypes
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import requests

from . import publishing


class PostizError(Exception):
    pass


class UnknownOutcome(PostizError):
    pass


class MediaValidationError(PostizError):
    pass


@dataclass(frozen=True)
class Result:
    post_id: str
    status: str
    due_at: str
    url: str | None = None
    raw: dict[str, Any] | None = None


class Postiz:
    name = "postiz"

    def __init__(self, api_key: str, url: str, session: Any = None):
        self.url = url.rstrip("/")
        self.http = session or requests.Session()
        self.http.headers.update({"Authorization": api_key})

    def _request(self, method: str, path: str, **kwargs) -> Any:
        try:
            response = self.http.request(method, self.url + path, timeout=60, **kwargs)
        except requests.RequestException as exc:
            raise UnknownOutcome(f"Postiz outcome unknown: {exc}") from exc
        if response.status_code >= 500 or response.status_code == 429:
            raise UnknownOutcome(f"Postiz outcome unknown: HTTP {response.status_code}")
        try:
            body = response.json()
        except ValueError as exc:
            raise PostizError(f"Postiz returned no JSON (HTTP {response.status_code})") from exc
        if response.status_code >= 400:
            message = body.get("msg") or body.get("message") or str(body)
            raise PostizError(f"Postiz refused: {message}")
        return body

    def integrations(self) -> list[dict[str, Any]]:
        return self._request("GET", "/public/v1/integrations")

    def upload(self, asset: publishing.MediaAsset) -> dict[str, str]:
        actual = __import__("hashlib").sha256(asset.data).hexdigest()
        if actual != asset.sha256:
            raise MediaValidationError("media bytes changed after approval")
        if asset.size and asset.size != len(asset.data):
            raise MediaValidationError("media size changed after approval")
        if not publishing.supports("linkedin" if asset.mime == "video/mp4" else "generic", [asset.mime]):
            raise MediaValidationError(f"unsupported media type: {asset.mime}")
        name = f"{asset.asset_id}{mimetypes.guess_extension(asset.mime) or '.bin'}"
        boundary = uuid.uuid4().hex
        prefix = (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\n'
            f"Content-Type: {asset.mime}\r\n\r\n"
        ).encode()
        body = prefix + asset.data + f"\r\n--{boundary}--\r\n".encode()
        got = self._request(
            "POST", "/public/v1/upload", data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
        )
        if not got.get("id") or not got.get("path"):
            raise MediaValidationError("Postiz upload returned no durable asset id/path")
        return {"id": str(got["id"]), "path": str(got["path"])}

    def publish(self, package: publishing.ContentPackage) -> Result:
        actual_media = tuple(a.asset_id for a in package.assets)
        if package.expected_media and actual_media != package.expected_media:
            raise MediaValidationError("approved media package is incomplete; video/media was not dropped")
        if not publishing.supports(package.channel, [a.mime for a in package.assets]):
            raise MediaValidationError(f"{package.channel} cannot accept this media package")
        uploaded = [self.upload(asset) for asset in package.assets]
        if any(a.mime == "video/mp4" for a in package.assets) and len(uploaded) != 1:
            raise MediaValidationError("a video post must contain exactly one uploaded video")
        payload = {
            "type": "schedule",
            "shortLink": False,
            "date": package.scheduled_at,
            "tags": [],
            "posts": [
                {
                    "integration": {"id": package.integration_id},
                    "group": package.idempotency_key,
                    "value": [{"content": package.caption, "image": uploaded}],
                    "settings": {"__type": package.channel},
                }
            ],
        }
        created = self._request("POST", "/public/v1/posts", json=payload)
        if not created or not created[0].get("postId"):
            raise PostizError("Postiz returned no post id")
        result = Result(str(created[0]["postId"]), "scheduled", package.scheduled_at)
        return self.readback(result, package.scheduled_at)

    def readback(self, result: Result, scheduled_at: str) -> Result:
        at = datetime.fromisoformat(scheduled_at.replace("Z", "+00:00"))
        query = urlencode({"startDate": (at - timedelta(days=1)).isoformat(), "endDate": (at + timedelta(days=1)).isoformat()})
        posts = self._request("GET", "/public/v1/posts?" + query).get("posts") or []
        found = next((p for p in posts if p.get("id") == result.post_id), None)
        if not found:
            raise PostizError("Postiz post id was not returned by readback")
        states = {"PUBLISHED": "sent", "ERROR": "error"}
        return Result(
            str(found["id"]),
            states.get(found.get("state"), "scheduled"),
            str(found.get("publishDate") or scheduled_at),
            found.get("releaseURL") or None,
            found,
        )

    def find_by_key(self, key: str, scheduled_at: str) -> Result | None:
        at = datetime.fromisoformat(scheduled_at.replace("Z", "+00:00"))
        query = urlencode({"startDate": (at - timedelta(days=1)).isoformat(), "endDate": (at + timedelta(days=1)).isoformat()})
        posts = self._request("GET", "/public/v1/posts?" + query).get("posts") or []
        found = next((p for p in posts if p.get("group") == key), None)
        return self.readback(Result(str(found["id"]), "scheduled", scheduled_at), scheduled_at) if found else None
