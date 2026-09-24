"""Environment reading. Every setting is read once, here, and a missing REQUIRED
one fails loudly at import of the script that needs it — never halfway through a run.

Secrets (GitHub → Settings → Secrets and variables → Actions → Secrets):
  SUPABASE_URL                 https://<ref>.supabase.co
  SUPABASE_SERVICE_ROLE_KEY    service_role key (bypasses RLS; runner only, never the browser)
  LLM_API_KEY                  bearer for the summariser (OpenAI, Anthropic, Mireld, any OpenAI-compatible)
  REPLICATE_API_TOKEN          if MEDIA_PROVIDER=replicate
  OPENAI_API_KEY               if MEDIA_PROVIDER=openai (may equal LLM_API_KEY)

Variables (same page → Variables; not secret):
  LLM_PROVIDER      openai | anthropic            default openai   (openai = any OpenAI-compatible endpoint)
  LLM_BASE_URL      API root for LLM_PROVIDER=openai  default https://api.openai.com/v1
  LLM_MODEL         default gpt-4o-mini (openai) / claude-haiku-4-5-20251001 (anthropic)
  MEDIA_PROVIDER    replicate | openai            default replicate
  ... the rest are documented beside their default below.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


class ConfigError(RuntimeError):
    pass


def env(name: str, default: str | None = None, *, required: bool = False) -> str | None:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        if required:
            raise ConfigError(f"{name} is not set — add it under Settings → Secrets and variables → Actions")
        return default
    return value.strip()


def env_int(name: str, default: int) -> int:
    raw = env(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc


@dataclass(frozen=True)
class SupabaseSettings:
    url: str
    service_role_key: str

    @classmethod
    def load(cls) -> SupabaseSettings:
        return cls(
            url=env("SUPABASE_URL", required=True),
            service_role_key=env("SUPABASE_SERVICE_ROLE_KEY", required=True),
        )


@dataclass(frozen=True)
class LLMSettings:
    provider: str          # openai | anthropic
    api_key: str | None
    base_url: str
    model: str
    timeout: int

    @classmethod
    def load(cls) -> LLMSettings:
        provider = (env("LLM_PROVIDER", "openai") or "openai").lower()
        if provider not in ("openai", "anthropic"):
            raise ConfigError(f"LLM_PROVIDER must be openai or anthropic, got {provider!r}")
        default_model = "gpt-4o-mini" if provider == "openai" else "claude-haiku-4-5-20251001"
        default_base = "https://api.openai.com/v1" if provider == "openai" else "https://api.anthropic.com"
        return cls(
            provider=provider,
            api_key=env("LLM_API_KEY") or env("OPENAI_API_KEY") or env("ANTHROPIC_API_KEY"),
            base_url=(env("LLM_BASE_URL", default_base) or default_base).rstrip("/"),
            model=env("LLM_MODEL", default_model) or default_model,
            timeout=env_int("LLM_TIMEOUT", 60),
        )


@dataclass(frozen=True)
class ScraperSettings:
    max_per_source: int
    max_age_hours: int
    llm_batch: int
    use_playwright: bool
    request_timeout: int
    keep_days: int          # headlines and run rows older than this are deleted (0 = keep for ever)

    @classmethod
    def load(cls) -> ScraperSettings:
        return cls(
            max_per_source=env_int("SCRAPE_MAX_PER_SOURCE", 40),
            max_age_hours=env_int("SCRAPE_MAX_AGE_HOURS", 48),
            llm_batch=env_int("SCRAPE_LLM_BATCH", 12),
            use_playwright=(env("SCRAPE_USE_PLAYWRIGHT", "1") or "1") not in ("0", "false", "no"),
            request_timeout=env_int("SCRAPE_REQUEST_TIMEOUT", 25),
            # 30 days holds roughly 60 MB. The Supabase project may be shared with
            # another app, and the free plan's 500 MB database is shared with it.
            keep_days=env_int("SCRAPE_KEEP_DAYS", 30),
        )


@dataclass(frozen=True)
class MediaSettings:
    provider: str                      # replicate | openai
    batch: int
    max_attempts: int
    poll_seconds: int
    max_wait_image: int
    max_wait_video: int
    replicate_token: str | None
    replicate_image_model: str
    replicate_video_model: str
    replicate_image_input_key: str
    replicate_video_input_key: str
    openai_key: str | None
    openai_base_url: str
    openai_image_model: str
    openai_video_model: str
    openai_image_size: str
    openai_video_seconds: str
    openai_video_size: str

    @classmethod
    def load(cls) -> MediaSettings:
        provider = (env("MEDIA_PROVIDER", "replicate") or "replicate").lower()
        if provider not in ("replicate", "openai"):
            raise ConfigError(f"MEDIA_PROVIDER must be replicate or openai, got {provider!r}")
        return cls(
            provider=provider,
            batch=env_int("MEDIA_BATCH", 5),
            max_attempts=env_int("MEDIA_MAX_ATTEMPTS", 3),
            poll_seconds=env_int("MEDIA_POLL_SECONDS", 8),
            max_wait_image=env_int("MEDIA_MAX_WAIT_IMAGE", 300),
            max_wait_video=env_int("MEDIA_MAX_WAIT_VIDEO", 1500),
            replicate_token=env("REPLICATE_API_TOKEN"),
            # Official-model slugs. Both take a picture + a prompt.
            replicate_image_model=env("REPLICATE_IMAGE_MODEL", "black-forest-labs/flux-kontext-pro"),
            replicate_video_model=env("REPLICATE_VIDEO_MODEL", "kwaivgi/kling-v2.1"),
            # The input field that carries the reference picture differs per model.
            replicate_image_input_key=env("REPLICATE_IMAGE_INPUT_KEY", "input_image"),
            replicate_video_input_key=env("REPLICATE_VIDEO_INPUT_KEY", "start_image"),
            openai_key=env("OPENAI_API_KEY") or env("LLM_API_KEY"),
            openai_base_url=(env("OPENAI_BASE_URL", "https://api.openai.com/v1") or "").rstrip("/"),
            openai_image_model=env("OPENAI_IMAGE_MODEL", "gpt-image-1"),
            openai_video_model=env("OPENAI_VIDEO_MODEL", "sora-2"),
            openai_image_size=env("OPENAI_IMAGE_SIZE", "1024x1024"),
            openai_video_seconds=env("OPENAI_VIDEO_SECONDS", "8"),
            openai_video_size=env("OPENAI_VIDEO_SIZE", "1280x720"),
        )
