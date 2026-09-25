"""Replicate: image-to-image and image-to-video through the HTTP API, no SDK.

POST /v1/models/{owner}/{name}/predictions   (official model, latest version)
POST /v1/predictions  with {"version": …}     (a pinned version hash, "owner/name:hash")
then GET urls.get until status is succeeded | failed | canceled.

The reference picture goes in as its public Supabase URL — Replicate fetches it —
so the bytes never pass through the runner for the image half of this route.
"""

from __future__ import annotations

import time
from typing import Any

import requests

from ..config import MediaSettings
from ..log import get_logger
from . import Generated, ProviderError
from .common import download

log = get_logger("semasa.replicate")
API = "https://api.replicate.com/v1"


class ReplicateProvider:
    name = "replicate"

    def __init__(self, s: MediaSettings):
        if not s.replicate_token:
            raise ProviderError("REPLICATE_API_TOKEN is not set")
        self.s = s
        self.headers = {"Authorization": f"Bearer {s.replicate_token}", "Content-Type": "application/json",
                        "Prefer": "wait=60"}

    def generate(self, kind: str, reference_url: str, prompt: str, options: dict[str, Any]) -> Generated:
        if kind == "video":
            model = options.get("model") or self.s.replicate_video_model
            key = options.get("input_key") or self.s.replicate_video_input_key
            max_wait = self.s.max_wait_video
        else:
            model = options.get("model") or self.s.replicate_image_model
            key = options.get("input_key") or self.s.replicate_image_input_key
            max_wait = self.s.max_wait_image
        payload_input: dict[str, Any] = {"prompt": prompt, key: reference_url}
        payload_input.update(options.get("input") or {})
        return self._run(model, payload_input, max_wait)

    def generate_from_text(self, prompt: str, options: dict[str, Any]) -> Generated:
        model = options.get("t2i_model") or self.s.replicate_t2i_model
        payload_input: dict[str, Any] = {"prompt": prompt, "aspect_ratio": options.get("aspect_ratio") or "1:1"}
        payload_input.update(options.get("t2i_input") or {})
        return self._run(model, payload_input, self.s.max_wait_image)

    def _run(self, model: str, payload_input: dict[str, Any], max_wait: int) -> Generated:
        if ":" in model:
            slug, version = model.split(":", 1)
            r = requests.post(f"{API}/predictions", headers=self.headers,
                              json={"version": version, "input": payload_input}, timeout=90)
        else:
            r = requests.post(f"{API}/models/{model}/predictions", headers=self.headers,
                              json={"input": payload_input}, timeout=90)
        if r.status_code == 422:
            raise ProviderError(f"Replicate rejected the input for {model}: {r.text[:300]}")
        r.raise_for_status()
        pred = r.json()
        pred = self._wait(pred, max_wait)
        output = pred.get("output")
        url = output[0] if isinstance(output, list) and output else output
        if not isinstance(url, str) or not url.startswith("http"):
            raise ProviderError(f"Replicate finished without a file URL: {str(output)[:200]}")
        data, ct = download(url)
        return Generated(data=data, content_type=ct, model=model,
                         meta={"prediction_id": pred.get("id"), "metrics": pred.get("metrics"), "output_url": url})

    def _wait(self, pred: dict[str, Any], max_wait: int) -> dict[str, Any]:
        started = time.time()
        while pred.get("status") not in ("succeeded", "failed", "canceled"):
            if time.time() - started > max_wait:
                raise TimeoutError(f"Replicate prediction {pred.get('id')} still {pred.get('status')} after {max_wait}s")
            time.sleep(self.s.poll_seconds)
            r = requests.get(pred["urls"]["get"], headers=self.headers, timeout=60)
            r.raise_for_status()
            pred = r.json()
        if pred["status"] != "succeeded":
            raise ProviderError(f"Replicate {pred['status']}: {str(pred.get('error'))[:300]}")
        return pred
