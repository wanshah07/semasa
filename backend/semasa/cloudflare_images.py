"""Motion's scene pictures from Cloudflare Workers AI (Wan, 7 Nov 2026: "for motion, make sure image can come from chatgpt,
cloudflare, gemini").

The third picture maker after ChatGPT (his login) and Gemini (his keys). It reuses the provider the post images already use
(providers/cloudflare.py, FLUX on Workers AI, the free 10,000 neurons a day) and the same credentials, which are the GitHub
secrets CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN (or the page's image slot, ai_config.media_for): nothing new to set up.
It answers a square picture; a scene shows it cropped to the frame like any photograph.

Used by motion_gpt_images.py. Every failure is a CloudflareError the caller turns into a note, and `limit` says the day's
allowance is used up or the token is refused, so the rest of that film stops asking.
"""

from __future__ import annotations

from typing import Any

from .log import get_logger

log = get_logger("semasa.motion.cloudflare")

LIMIT_WORDS = ("used up", "neurons", "refused the token", "needs the cloudflare workers paid plan")


class CloudflareError(RuntimeError):
    """A picture Cloudflare did not give. `limit`: the allowance is used up or the token refused (stop asking for this film)."""

    def __init__(self, message: str, *, limit: bool = False):
        super().__init__(message)
        self.limit = limit


class Drawer:
    """Draws pictures with Cloudflare Workers AI. `provider` is a stand-in in tests; otherwise it is built from the page's image
    slot over GitHub's settings the first time it is needed."""

    def __init__(self, store: Any = None, provider: Any = None):
        self.store = store
        self._provider = provider
        self._tried = provider is not None
        self.why = ""

    def _get(self) -> Any:
        if not self._tried:
            self._tried = True
            try:
                from . import ai_config
                from .config import MediaSettings
                from .media_generator import make_provider
                s = ai_config.media_for(self.store, MediaSettings.load())
                if s.cloudflare_account_id and s.cloudflare_token:
                    self._provider = make_provider("cloudflare", s)
                else:
                    self.why = "CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN are not set"
            except Exception as exc:  # noqa: BLE001 - not set up is not an error for a film
                self.why = str(exc)[:120]
                log.info("cloudflare pictures off: %s", self.why)
        return self._provider

    def ready(self) -> bool:
        return self._get() is not None

    def draw(self, prompt: str, *, resolution: str = "portrait") -> bytes:  # noqa: ARG002 - square: a scene crops it
        provider = self._get()
        if provider is None:
            raise CloudflareError(f"Cloudflare is not set up ({self.why or 'no credentials'})", limit=True)
        try:
            gen = provider.generate_from_text(prompt, {})
        except Exception as exc:  # noqa: BLE001 - ProviderError, a network error, a bad answer: all a note
            text = " ".join(str(exc).split())[:240]
            raise CloudflareError(text, limit=any(w in text.lower() for w in LIMIT_WORDS)) from exc
        if not getattr(gen, "data", b""):
            raise CloudflareError("Cloudflare answered without a picture")
        return gen.data
