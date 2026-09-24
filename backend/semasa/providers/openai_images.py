"""OpenAI: image edits (gpt-image-1) and video (sora-2) — also any OpenAI-compatible
base URL that implements the same routes.

image → POST {base}/images/edits   multipart: model, prompt, size, image=<reference>
video → POST {base}/videos         multipart: model, prompt, seconds, size, input_reference=<reference>
        GET  {base}/videos/{id}    until status completed | failed
        GET  {base}/videos/{id}/content  → mp4 bytes
"""

from __future__ import annotations

import base64
import time
from typing import Any

import requests

from ..config import MediaSettings
from ..log import get_logger
from . import Generated, ProviderError
from .common import download, fetch_reference

log = get_logger("semasa.openai")


class OpenAIProvider:
    name = "openai"

    def __init__(self, s: MediaSettings):
        if not s.openai_key:
            raise ProviderError("OPENAI_API_KEY is not set")
        self.s = s
        self.base = s.openai_base_url
        self.auth = {"Authorization": f"Bearer {s.openai_key}"}

    def generate(self, kind: str, reference_url: str, prompt: str, options: dict[str, Any]) -> Generated:
        ref_bytes, ref_ct, ref_name = fetch_reference(reference_url)
        if not ref_ct.startswith("image/"):
            raise ProviderError(f"OpenAI routes need an image reference, got {ref_ct}")
        return self._video(ref_bytes, ref_ct, ref_name, prompt, options) if kind == "video" \
            else self._image(ref_bytes, ref_ct, ref_name, prompt, options)

    def _image(self, data: bytes, ct: str, name: str, prompt: str, options: dict[str, Any]) -> Generated:
        model = options.get("model") or self.s.openai_image_model
        r = requests.post(
            f"{self.base}/images/edits",
            headers=self.auth,
            files={"image": (name, data, ct)},
            data={"model": model, "prompt": prompt, "size": options.get("size") or self.s.openai_image_size,
                  "n": 1},
            timeout=self.s.max_wait_image,
        )
        if r.status_code in (400, 422):
            raise ProviderError(f"OpenAI rejected the request: {r.text[:300]}")
        r.raise_for_status()
        item = (r.json().get("data") or [{}])[0]
        if item.get("b64_json"):
            out = base64.b64decode(item["b64_json"])
            fmt = (options.get("output_format") or "png").lower()
            ct = f"image/{'jpeg' if fmt == 'jpg' else fmt}"
            return Generated(out, ct, model, {"revised_prompt": item.get("revised_prompt")})
        if item.get("url"):
            out, out_ct = download(item["url"])
            return Generated(out, out_ct, model, {"output_url": item["url"]})
        raise ProviderError("OpenAI answered without image data")

    def _video(self, data: bytes, ct: str, name: str, prompt: str, options: dict[str, Any]) -> Generated:
        model = options.get("model") or self.s.openai_video_model
        r = requests.post(
            f"{self.base}/videos",
            headers=self.auth,
            files={"input_reference": (name, data, ct)},
            data={"model": model, "prompt": prompt,
                  "seconds": str(options.get("seconds") or self.s.openai_video_seconds),
                  "size": options.get("size") or self.s.openai_video_size},
            timeout=120,
        )
        if r.status_code in (400, 422):
            raise ProviderError(f"OpenAI rejected the video request: {r.text[:300]}")
        r.raise_for_status()
        job = r.json()
        started = time.time()
        while job.get("status") not in ("completed", "failed", "cancelled", "canceled"):
            if time.time() - started > self.s.max_wait_video:
                raise TimeoutError(f"OpenAI video {job.get('id')} still {job.get('status')} after {self.s.max_wait_video}s")
            time.sleep(self.s.poll_seconds)
            rr = requests.get(f"{self.base}/videos/{job['id']}", headers=self.auth, timeout=60)
            rr.raise_for_status()
            job = rr.json()
        if job.get("status") != "completed":
            raise ProviderError(f"OpenAI video {job.get('status')}: {str(job.get('error'))[:300]}")
        content = requests.get(f"{self.base}/videos/{job['id']}/content", headers=self.auth, timeout=600)
        content.raise_for_status()
        return Generated(content.content, "video/mp4", model, {"video_id": job.get("id"), "seconds": job.get("seconds")})
