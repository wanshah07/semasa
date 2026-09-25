"""Media generator. Entry point: `python -m semasa.media_generator` (see .github/workflows/media.yml).

A run first hands any `new` ideas to the idea writer (semasa.ideas: Flow A), then takes
`pending` rows from media_generations, oldest first. Two modes:

  prompt    words only. An image comes straight from the words; a video is a still made
            from the words first, then animated from that still.
  recreate  a reference picture. The bot READS it first (VISION_MODEL describes it, and the
            description is stored in `reference_read`), then makes a new one:
              * Flow B, Wan's own reference: the picture itself goes to the image-edit /
                image-to-video model together with the words and the read;
              * Flow A, a picture found on a news page (meta.flow = "A"): only the READ goes
                forward and the picture is made from words. A publisher's photograph is
                somebody else's work — describing it and drawing afresh is a new picture;
                feeding the pixels to an edit model is a copy of theirs.

The result goes to bucket `semasa-generated`; the public address is written back. A failure
is stored ON THE ROW, and the row goes back to `pending` until `attempts` reaches
MEDIA_MAX_ATTEMPTS. A row left `processing` by a runner that died is put back to `pending`
after MEDIA_STALE_MINUTES. Nothing here deletes a row or a file.

MEDIA_ONLY_ID (from a repository_dispatch payload) narrows the media step to one row.
"""

from __future__ import annotations

import hashlib
import io
import os
import sys
from datetime import UTC, datetime
from typing import Any

from . import db
from .config import LLMSettings, MediaSettings, SupabaseSettings
from .llm import LLM
from .log import get_logger
from .providers import Generated, Provider, ProviderError
from .providers.common import fetch_reference

log = get_logger("semasa.media")

READ_MAX_BYTES = 600_000   # the picture travels base64 inside one request; gateways cap bodies near 1 MiB

READ_SYSTEM = (
    "You describe a reference picture so that an image model can make a NEW picture from your words. "
    "Answer with one JSON object only."
)
READ_PROMPT = (
    "Describe this picture for re-creation. JSON keys: "
    '"description" (4 to 7 sentences: subject, setting, composition and camera angle, lighting, colour palette, style, mood), '
    '"subject" (a few words), "style" (a few words), '
    '"text_in_image" (any words printed in the picture, verbatim, or ""), '
    '"people" (true if a recognisable real person is shown), "brands" (logos or brand names visible, or []).'
)
FLOW_A_GUARD = (
    "Make a new, original picture. Do not copy any photograph. No logos, no watermarks, no brand names, "
    "no printed text, and no recognisable real person."
)


def make_provider(name: str, s: MediaSettings) -> Provider:
    if name == "replicate":
        from .providers.replicate import ReplicateProvider
        return ReplicateProvider(s)
    if name == "openai":
        from .providers.openai_images import OpenAIProvider
        return OpenAIProvider(s)
    raise ProviderError(f"unknown provider {name!r}")


IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".gif")


def reference_is_image(row: dict[str, Any]) -> bool:
    """Both providers generate FROM a picture. A PDF or text reference used to reach
    the provider and fail there (after the job was claimed, sometimes after credits
    were spent), so it is refused here with a message the page can show."""
    mime = str(((row.get("meta") or {}).get("mime")) or "").lower()
    if mime:
        return mime.startswith("image/")
    path = str(row.get("reference_url") or "").split("?")[0].lower()
    return path.endswith(IMAGE_EXTENSIONS)


def shrink_for_read(data: bytes, mime: str, budget: int = READ_MAX_BYTES) -> tuple[bytes, str]:
    """A picture small enough to send inline. Longest side 1024, JPEG, quality stepped down
    until it fits. Returns the input untouched when it already fits and is not a GIF."""
    if len(data) <= budget and mime in ("image/jpeg", "image/png", "image/webp"):
        return data, mime
    from PIL import Image

    img = Image.open(io.BytesIO(data))
    img.seek(0)
    img = img.convert("RGB")
    img.thumbnail((1024, 1024))
    for quality in (85, 75, 65, 50, 40):
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=quality)
        if buf.tell() <= budget:
            return buf.getvalue(), "image/jpeg"
    img.thumbnail((640, 640))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=60)
    return buf.getvalue(), "image/jpeg"


def read_reference(llm: LLM | None, url: str) -> dict[str, Any] | None:
    """The READ step. None when there is no model that can see, or it would not answer:
    the row then says "not read", never an invented description."""
    if llm is None or not llm.configured:
        return None
    try:
        data, ct, _ = fetch_reference(url)
        small, small_ct = shrink_for_read(data, ct)
    except Exception as exc:  # noqa: BLE001 - a read that fails must not fail the job
        log.warning("could not load the reference for reading: %s", exc)
        return None
    out = llm.describe_image(READ_SYSTEM, READ_PROMPT, small, small_ct)
    if not out or not str(out.get("description") or "").strip():
        return None
    return out


def compose_prompt(row: dict[str, Any], read: dict[str, Any] | None) -> str:
    """The words the generator gets. Wan's own words first: they are the instruction."""
    words = (row.get("prompt") or "").strip()
    flow_a = (row.get("meta") or {}).get("flow") == "A"
    parts: list[str] = []
    if row.get("mode") == "recreate":
        if flow_a:
            parts.append("Draw a new picture of this scene." if read else "")
        else:
            parts.append("Recreate the reference picture." + (f" Changes wanted: {words}" if words else ""))
    if words and not (row.get("mode") == "recreate" and not flow_a):
        parts.append(words)
    if read:
        parts.append(f"What the reference shows: {read['description'].strip()}")
    if flow_a:
        parts.append(FLOW_A_GUARD)
    return "\n\n".join(p for p in parts if p).strip()


def _read_text(read: dict[str, Any] | None) -> str | None:
    return (str(read.get("description") or "").strip() or None) if read else None


def _store(store: Any, row_id: str, gen: Generated, suffix: str = "") -> tuple[str, str]:
    day = datetime.now(UTC).strftime("%Y/%m")
    path = f"{day}/{row_id}{suffix}.{gen.extension}"
    return db.upload_generated(store, path, gen.data, gen.content_type), path


def process_row(store: Any, row: dict[str, Any], s: MediaSettings, providers: dict[str, Provider],
                llm: LLM | None = None) -> bool:
    row_id = row["id"]
    kind = row.get("type") or "image"
    mode = row.get("mode") or "recreate"
    name = (row.get("provider") or s.provider).lower()
    options = dict((row.get("meta") or {}).get("options") or {})
    flow_a = (row.get("meta") or {}).get("flow") == "A"
    extra: dict[str, Any] = {}
    read: dict[str, Any] | None = None
    try:
        if mode == "recreate":
            if not row.get("reference_url"):
                raise ProviderError("recreate needs a reference picture")
            if not reference_is_image(row):
                raise ProviderError("reference must be an image (PNG, JPG, WEBP or GIF); put text in the prompt instead")
        elif not (row.get("prompt") or "").strip():
            raise ProviderError("a words-only job needs a prompt")
        if name not in providers:
            providers[name] = make_provider(name, s)
        provider = providers[name]

        read = read_reference(llm, row["reference_url"]) if mode == "recreate" else None
        if mode == "recreate":
            extra["read"] = read or None
            extra["read_model"] = (llm.s.vision_model or llm.s.model) if (read and llm) else None
            if flow_a and not read and not (row.get("prompt") or "").strip():
                raise ProviderError("the news picture could not be read and there are no words to draw from; "
                                    "set VISION_MODEL to a model that sees pictures, or add a prompt")
        prompt = compose_prompt(row, read)
        log.info("%s: %s/%s via %s — %s", row_id, mode, kind, name, prompt[:80])

        if mode == "recreate" and not flow_a:
            gen = provider.generate(kind, row["reference_url"], prompt, options)
        else:
            still = provider.generate_from_text(prompt, options)
            if kind == "video":
                still_url, still_path = _store(store, row_id, still, "-still")
                extra.update(still_url=still_url, still_path=still_path)
                gen = provider.generate("video", still_url, (row.get("prompt") or prompt), options)
            else:
                gen = still
        if not gen.data:
            raise ProviderError("provider returned no bytes")
        url, path = _store(store, row_id, gen)
        meta = {**(row.get("meta") or {}), **gen.meta, **extra, "bytes": len(gen.data),
                "sha256": hashlib.sha256(gen.data).hexdigest(), "content_type": gen.content_type,
                "generated_path": path, "final_prompt": prompt, "finished_at": datetime.now(UTC).isoformat()}
        db.finish_media(store, row_id, status="done", generated_media_url=url, provider=name, model=gen.model,
                        error=None, meta=meta, reference_read=_read_text(read))
        if row.get("post_id"):
            db.attach_media_to_draft(store, row["post_id"], row_id)
        log.info("%s: done → %s (%d bytes)", row_id, url, len(gen.data))
        return True
    except Exception as exc:  # noqa: BLE001 - the row records it; the run continues
        attempts = int(row.get("attempts") or 0)
        final = isinstance(exc, ProviderError) or attempts >= s.max_attempts
        status = "error" if final else "pending"
        msg = f"{type(exc).__name__}: {str(exc)[:600]}"
        log.error("%s: %s (attempt %d, → %s)", row_id, msg, attempts, status)
        db.finish_media(store, row_id, status=status, error=msg, provider=name, reference_read=_read_text(read))
        return False


def main() -> int:
    s = MediaSettings.load()
    store = db.client(SupabaseSettings.load())
    llm = LLM(LLMSettings.load())

    # Flow A first, so the pictures an idea asks for are made in this same run.
    from . import ideas
    idea_note = ideas.run(store, llm)

    recovered = db.recover_stale_media(store, s.stale_minutes)
    only_id = (os.environ.get("MEDIA_ONLY_ID") or "").strip() or None
    rows = db.claim_pending(store, s.batch, only_id)
    done = 0
    if rows:
        providers: dict[str, Provider] = {}
        done = sum(process_row(store, r, s, providers, llm) for r in rows)
        log.info("%d/%d generated", done, len(rows))
    else:
        log.info("nothing pending")
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write(f"## Semasa worker\n\n{idea_note}\n\n{done}/{len(rows)} media jobs generated "
                     f"(default provider {s.provider}); {recovered} stuck job(s) put back in the queue\n")
    return 0 if done == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
