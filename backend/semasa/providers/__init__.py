"""Generation providers. Each exposes generate(kind, reference_url, prompt, options) -> Generated."""

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

    def generate(self, kind: str, reference_url: str, prompt: str, options: dict[str, Any]) -> Generated: ...


class ProviderError(RuntimeError):
    """A refusal or failure that a retry with the same inputs will not change."""
