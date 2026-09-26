"""Media generator. Entry point: `python -m semasa.media_generator` (see .github/workflows/media.yml).

A run first hands any `new` ideas to the idea writer (semasa.ideas: Flow A), then takes
`pending` rows from media_generations, oldest first. Three modes:

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
  slides    carousel slides drawn here from words (semasa.slides): no provider, no key, no
            cost. meta.slides is the snapshot of the words; the pictures are meta.slide_urls.

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
from datetime import UTC, datetime, timedelta
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
    if name == "cloudflare":
        from .providers.cloudflare import CloudflareProvider
        return CloudflareProvider(s)
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


def slide_ground(store: Any, row: dict[str, Any]) -> tuple[bytes | None, str | None]:
    """The background picture a slide job asked for: (bytes, the media id used) or (None, None).
    meta.bg is "none", "post_image" (the post's first finished picture), "reference" (the job's own uploaded
    picture) or a media id (a picture made for it, such as the Design tab's AI background)."""
    meta = row.get("meta") or {}
    bg = str(meta.get("bg") or "none")
    if bg == "none":
        return None, None
    if bg == "reference":
        # the Design tab: a picture Wan uploaded for this artwork, stored as the job's reference
        if not row.get("reference_url"):
            return None, None
        data, _, _ = fetch_reference(row["reference_url"])
        return data, "reference"
    q = store.table(db.MEDIA).select("id,status,type,mode,generated_media_url,created_at")
    if bg == "post_image":
        if not row.get("post_id"):
            return None, None
        rows = q.eq("post_id", row["post_id"]).eq("status", "done").order("created_at").execute().data or []
    else:
        rows = q.eq("id", bg).execute().data or []
    pick = next((r for r in rows if r.get("type") == "image" and r.get("mode") != "slides"
                 and r.get("status") == "done" and r.get("generated_media_url")), None)
    if not pick:
        return None, None
    data, _, _ = fetch_reference(pick["generated_media_url"])
    return data, pick["id"]


SLIDES_WAIT = timedelta(hours=2)


def picture_pending(store: Any, row: dict[str, Any]) -> bool:
    """True while slides meant to sit on a picture would be drawn before that picture exists: a picture job for the
    same post (bg "post_image"), or the picture made for this artwork (bg = its media id), is still pending or
    running. The picture and the slide job are queued together, so their order is otherwise undefined. After
    SLIDES_WAIT the slides are drawn anyway (on paper, and bg_missing says so) rather than wait for ever."""
    meta = row.get("meta") or {}
    bg = str(meta.get("bg") or "none")
    if bg in ("none", "reference") or (bg == "post_image" and not row.get("post_id")):
        return False
    try:
        made = datetime.fromisoformat(str(row.get("created_at")).replace("Z", "+00:00"))
        if datetime.now(UTC) - made > SLIDES_WAIT:
            return False
    except (TypeError, ValueError):
        return False
    try:
        q = store.table(db.MEDIA).select("id,mode,status").in_("status", ["pending", "processing"])
        # the post's picture, or the one picture made for this artwork (a media id)
        q = q.eq("post_id", row["post_id"]) if bg == "post_image" else q.eq("id", bg)
        rows = q.execute().data or []
    except Exception as exc:  # noqa: BLE001 - never block the slides on a failed look-up
        log.info("could not check the post's picture (%s)", str(exc)[:80])
        return False
    return any(r.get("mode") != "slides" and r.get("id") != row["id"] for r in rows)


def process_slides(store: Any, row: dict[str, Any], s: MediaSettings, llm: LLM | None = None) -> bool:
    """Mode `slides`: draw the snapshot of words in meta.slides with semasa.slides. No provider,
    no key, no cost. Too long to fit is a final error that names the slide, never a cut.
    A Design-tab job (meta.design) may bring only an idea (meta.brief): the writer turns it into words first, and
    those words are saved on the job before drawing, so a retry draws them again instead of writing new ones."""
    from . import compliance, design, ideas, slides, studio_cards

    row_id = row["id"]
    meta = dict(row.get("meta") or {})
    if picture_pending(store, row):
        # drawn on the post's picture, which is still being made: wait for it rather than draw on paper
        store.table(db.MEDIA).update({"status": "pending", "attempts": max(0, int(row.get("attempts") or 1) - 1),
                                      "error": None}).eq("id", row_id).eq("status", "processing").execute()
        log.info("%s: waiting for the post's picture before drawing the slides", row_id)
        return True
    try:
        items = slides.normalise(meta.get("slides"))
        stream = meta.get("stream") or "regulab"
        kind = str(meta.get("design") or "")
        if kind and not items and str(meta.get("brief") or "").strip():
            items, cit = design.write(llm, str(meta["brief"]), kind, stream)
            meta.update(slides=items, written_by=getattr(llm, "last_model", "") or None)
            if not str(meta.get("citation") or "").strip():
                meta["citation"] = cit
            store.table(db.MEDIA).update({"meta": meta}).eq("id", row_id).execute()
        if not items:
            raise slides.SlideError("no slides to draw: write at least one slide" + ("" if kind else " in the post"))
        if kind:
            design.check(items, kind)
            # the words are judged by the rules a post is judged by; a hard flag is shown on the artwork and blocks
            # the post it is attached to, and the drawing still goes ahead so Wan can see what he is fixing
            meta["flags"] = [f for f in compliance.scan({"stream": stream, "citation": meta.get("citation") or "",
                                                         "media": [{"artwork": items}]})
                             if f["where"].startswith(("Design", "Source"))]
        brand = (ideas.load_settings(store).get("brand") or {})
        reg, li = brand.get("regulab") or {}, brand.get("linkedin") or {}
        eyebrow = str(meta.get("eyebrow") or "").strip()
        if not eyebrow:
            if stream == "linkedin":
                eyebrow = str((li.get("angles") or {}).get(meta.get("angle") or "", "") or "")
            else:
                eyebrow = str((reg.get("domains") or {}).get(meta.get("domain") or "", "") or "")
        website = str(reg.get("website") or "www.kkmhalalconsultant.com")
        ground, ground_id = slide_ground(store, row)
        if meta.get("bg") not in (None, "none") and ground is None:
            meta["bg_missing"] = "the background picture was not ready, so the slides were drawn on paper"
        size = design.size_of(meta, stream) if kind else None
        look = str(meta.get("look") or "classic")
        if studio_cards.is_studio_look(look):
            # ws.regulab Studio's own designs, drawn by Studio's own code in headless Chrome
            from .providers.cloudflare import content_type_of
            pics = studio_cards.render(items, look=look, stream=stream, eyebrow=eyebrow,
                                       source=str(meta.get("citation") or ""), ground=ground,
                                       ground_mime=content_type_of(ground) if ground else "image/jpeg", size=size)
        else:
            look = "classic"
            pics = slides.render(items, stream=stream, eyebrow=eyebrow, source=str(meta.get("citation") or ""),
                                 website=website, ground=ground, size=size)
        day = datetime.now(UTC).strftime("%Y/%m")
        urls, paths, sums = [], [], []
        for i, data in enumerate(pics, 1):
            path = f"{day}/{row_id}-slide{i:02d}.jpg"
            urls.append(db.upload_generated(store, path, data, "image/jpeg"))
            paths.append(path)
            sums.append(hashlib.sha256(data).hexdigest())
        meta.update(slides=items, slide_urls=urls, slide_paths=paths, sha256=sums, count=len(urls), look=look,
                    bg_used=ground_id, content_type="image/jpeg", bytes=sum(len(p) for p in pics),
                    finished_at=datetime.now(UTC).isoformat())
        db.finish_media(store, row_id, status="done", generated_media_url=urls[0], provider="semasa",
                        model="slides-v1" if look == "classic" else f"studio-{look}", error=None, meta=meta)
        if row.get("post_id"):
            # a Design artwork is added to the post's pictures; a post's own carousel replaces its earlier one
            (db.attach_media_to_draft if kind else db.attach_slides_to_draft)(store, row["post_id"], row_id)
        log.info("%s: %d slides drawn (%s)", row_id, len(urls), look)
        return True
    except Exception as exc:  # noqa: BLE001 - the row records it; the run continues
        from .slides import SlideError
        attempts = int(row.get("attempts") or 0)
        final = isinstance(exc, SlideError) or attempts >= s.max_attempts
        msg = f"{type(exc).__name__}: {str(exc)[:600]}"
        log.error("%s: %s (attempt %d)", row_id, msg, attempts)
        db.finish_media(store, row_id, status="error" if final else "pending", error=msg, provider="semasa")
        return False


def process_row(store: Any, row: dict[str, Any], s: MediaSettings, providers: dict[str, Provider],
                llm: LLM | None = None) -> bool:
    if row.get("mode") == "slides":
        return process_slides(store, row, s, llm)
    if row.get("mode") == "clip":
        # a short cut from a long video (semasa.video)
        from . import video
        return video.process_clip(store, row, s.max_attempts)
    if (row.get("provider") or "").lower() == "unsplash":
        # a search, then a pick: not a generation (semasa.unsplash)
        from . import unsplash
        return unsplash.process(store, row, s.max_attempts)
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
        if kind == "video" and not getattr(provider, "video", True):
            # stopped before the still is drawn: a picture made for a video nobody can make is spent for nothing
            raise ProviderError(f"{name} makes pictures only: choose Replicate or OpenAI for a video")

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
        # The row keeps the provider it was GIVEN: writing the runner's default here pinned every later Retry to it,
        # so three jobs kept asking Replicate for a key it never had after Cloudflare became the default (25 Sep 2026)
        db.finish_media(store, row_id, status=status, error=msg, provider=row.get("provider"),
                        reference_read=_read_text(read))
        return False


def main() -> int:
    s = MediaSettings.load()
    store = db.client(SupabaseSettings.load())
    llm = LLM(LLMSettings.load())
    from . import faq, ideas, trial
    trial_on = trial.start(store, llm, "media")         # the page's "Try Mireld for one run": Mireld is asked first

    # Flow A first, so the pictures an idea asks for are made in this same run.
    idea_note = ideas.run(store, llm)
    faq_note = faq.run(store, llm)
    from . import video
    video_note = video.run(store, llm)                 # long videos waiting to be read (supabase/011_video.sql)
    from . import watch
    watch_note = watch.run_if_due(store, llm, only_forced=True)   # the page's "sweep now" (the scrape keeps the daily clock)
    paste_note = watch.process_pasted(store, llm)       # links pasted in Regulatory / Latest publication (013)
    watch_note = "\n\n".join(x for x in (watch_note, paste_note) if x)

    recovered = db.recover_stale_media(store, s.stale_minutes)
    only_id = (os.environ.get("MEDIA_ONLY_ID") or "").strip() or None
    rows = db.claim_pending(store, s.batch, only_id)
    done = 0
    if rows:
        providers: dict[str, Provider] = {}
        # pictures first (slides may be drawn on them), the long clips last
        rows.sort(key=lambda r: {"slides": 1, "clip": 2}.get(r.get("mode"), 0))
        done = sum(process_row(store, r, s, providers, llm) for r in rows)
        log.info("%d/%d generated", done, len(rows))
    else:
        log.info("nothing pending")
    trial_note = trial.finish(store, llm, "media") if trial_on else ""
    from . import sheet
    sheet_note = sheet.sync_log(store)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write(f"## Semasa worker\n\n{idea_note}\n\n{faq_note}\n\n{video_note}\n\n{watch_note}\n\n"
                     f"{done}/{len(rows)} media jobs generated "
                     f"(default provider {s.provider}); {recovered} stuck job(s) put back in the queue\n\n{sheet_note}\n"
                     + (f"\n{trial_note}\n" if trial_note else ""))
    return 0 if done == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
