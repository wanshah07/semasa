"""Cloudflare Workers AI: pictures only, inside the free 10,000 neurons a day (Wan, 25 Sep 2026: "check if got any
free generated image API" → "go").

text → POST {api}/accounts/{account}/ai/run/{model}
        FLUX.1 [schnell] takes JSON {prompt, steps}; the FLUX.2 models take multipart form data even for a prompt
        alone. Both answer {"success": true, "result": {"image": "<base64>"}}.
image → the same multipart call to FLUX.2 [klein] with the reference as `input_image_0`. Cloudflare requires every
        input picture to be smaller than 512x512, so the reference is shrunk here first.

Free plan: the neurons reset at 00:00 UTC (08:00 MYT). Past them Cloudflare refuses the call and never bills: the job
records why and waits for Wan's Retry. Video is not offered: Cloudflare's video models are third-party ones paid
from prepaid credits, not from the free neurons, so a video job on this provider stops before anything is spent.
"""

from __future__ import annotations

import base64
import io
from typing import Any

import requests

from ..config import MediaSettings
from ..log import get_logger
from . import Generated, ProviderError
from .common import fetch_reference

log = get_logger("semasa.cloudflare")
API = "https://api.cloudflare.com/client/v4"
REF_MAX = 511          # "All input images must be smaller than 512x512"
MAGIC = ((b"\x89PNG", "image/png"), (b"\xff\xd8", "image/jpeg"), (b"RIFF", "image/webp"))
USED_UP = 3036        # HTTP 429 "You have used up your daily free allocation of 10,000 neurons" (Workers AI errors)
PAID_ONLY = 5035      # HTTP 403: this model needs the Workers Paid plan


def content_type_of(data: bytes) -> str:
    for head, ct in MAGIC:
        if data.startswith(head):
            return ct
    return "image/jpeg"


def is_multipart(model: str) -> bool:
    """FLUX.2 on Workers AI reads multipart form data only; FLUX.1 [schnell] reads JSON."""
    return "flux-2" in model


def shrink(data: bytes, limit: int = REF_MAX) -> tuple[bytes, str]:
    """The reference as a JPEG no larger than limit x limit, keeping its shape."""
    from PIL import Image
    with Image.open(io.BytesIO(data)) as im:
        im = im.convert("RGB")
        im.thumbnail((limit, limit))
        out = io.BytesIO()
        im.save(out, format="JPEG", quality=90)
    return out.getvalue(), "image/jpeg"


class CloudflareProvider:
    name = "cloudflare"
    video = False          # media_generator stops a video job before anything is spent

    def __init__(self, s: MediaSettings):
        if not s.cloudflare_account_id or not s.cloudflare_token:
            raise ProviderError("CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN must both be set")
        self.s = s
        self.base = f"{API}/accounts/{s.cloudflare_account_id}/ai/run"
        self.auth = {"Authorization": f"Bearer {s.cloudflare_token}"}

    def generate(self, kind: str, reference_url: str, prompt: str, options: dict[str, Any]) -> Generated:
        if kind == "video":
            raise ProviderError("Cloudflare makes pictures only here: choose Replicate or OpenAI for a video")
        ref, ref_ct, _ = fetch_reference(reference_url)
        if not ref_ct.startswith("image/"):
            raise ProviderError(f"Cloudflare needs an image reference, got {ref_ct}")
        small, small_ct = shrink(ref)
        model = options.get("model") or self.s.cloudflare_edit_model
        if not is_multipart(model):
            raise ProviderError(f"{model} cannot take a reference picture; use a FLUX.2 model")
        return self._run(model, prompt, options, files={"input_image_0": ("reference.jpg", small, small_ct)})

    def generate_from_text(self, prompt: str, options: dict[str, Any]) -> Generated:
        return self._run(options.get("model") or self.s.cloudflare_t2i_model, prompt, options)

    def _run(self, model: str, prompt: str, options: dict[str, Any],
             files: dict[str, tuple[str, bytes, str]] | None = None) -> Generated:
        url = f"{self.base}/{model}"
        size = str(options.get("size") or self.s.cloudflare_size)
        if is_multipart(model):
            fields = {"prompt": (None, prompt), "width": (None, size), "height": (None, size)}
            r = requests.post(url, headers=self.auth, files={**fields, **(files or {})},
                              timeout=self.s.max_wait_image)
        else:
            body: dict[str, Any] = {"prompt": prompt[:2048], "steps": int(options.get("steps") or 4)}
            r = requests.post(url, headers={**self.auth, "Content-Type": "application/json"}, json=body,
                              timeout=self.s.max_wait_image)
        return self._answer(r, model)

    def _answer(self, r: requests.Response, model: str) -> Generated:
        try:
            body = r.json()
        except ValueError:
            body = {}
        errs = body.get("errors") or []
        codes = {e.get("code") for e in errs if isinstance(e, dict)}
        errors = "; ".join(f"{e.get('code')}: {e.get('message')}" for e in errs if isinstance(e, dict))[:300]
        if USED_UP in codes or "daily free allocation" in errors.lower():
            raise ProviderError("the free 10,000 neurons for today are used up; they come back at 08:00 MYT. "
                                f"Press Retry after that. ({errors})")
        if PAID_ONLY in codes:
            raise ProviderError(f"{model} needs the Cloudflare Workers Paid plan; choose a model the free plan "
                                f"runs (CLOUDFLARE_T2I_MODEL / CLOUDFLARE_EDIT_MODEL). ({errors})")
        if r.status_code in (401, 403):
            raise ProviderError(f"Cloudflare refused the token (HTTP {r.status_code}): check CLOUDFLARE_API_TOKEN "
                                f"has Workers AI access and CLOUDFLARE_ACCOUNT_ID is right. {errors}".strip())
        if r.status_code in (400, 422):
            raise ProviderError(f"Cloudflare rejected the request: {errors or r.text[:300]}")
        r.raise_for_status()      # 3040 out of capacity (429) and 5xx: the runner tries again (MEDIA_MAX_ATTEMPTS)
        image = ((body.get("result") or {}) if isinstance(body.get("result"), dict) else {}).get("image")
        if not body.get("success", True) or not image:
            raise ProviderError(f"Cloudflare answered without a picture: {errors or str(body)[:300]}")
        data = base64.b64decode(image)
        return Generated(data, content_type_of(data), model, {"cloudflare_model": model})
