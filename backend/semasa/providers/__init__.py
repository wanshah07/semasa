"""Generation providers: generate(kind, reference_url, prompt, options) and generate_from_text(prompt, options)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class Generated:
    data: bytes
    content_type: str
    model: str
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def extension(self) -> str:
        return {
            "image/png": "png", "image/jpeg": "jpg", "image/webp": "webp",
            "video/mp4": "mp4", "video/webm": "webm",
        }.get(self.content_type, "bin")


class Provider(Protocol):
    name: str

    def generate(self, kind: str, reference_url: str, prompt: str, options: dict[str, Any]) -> Generated:
        """From a picture (image edit / image-to-video)."""
        ...

    def generate_from_text(self, prompt: str, options: dict[str, Any]) -> Generated:
        """An image from words alone. Video from words is a still from this, then generate()."""
        ...


class ProviderError(RuntimeError):
    """A refusal or failure that a retry with the same inputs will not change."""


class OutOfTime(TimeoutError):
    """The RUN ran out of time while the provider was still working (not the provider being slow): the job goes back
    to the queue with no attempt spent, and the paid job at the provider has been cancelled where it can be."""


def wait_limit(max_wait: int, deadline: float | None) -> tuple[float, bool]:
    """How long a poll may wait: the provider's own limit, or less when the run must stop first (True)."""
    import time
    if deadline is None:
        return float(max_wait), False
    left = max(0.0, deadline - time.time())
    return (left, True) if left < max_wait else (float(max_wait), False)
