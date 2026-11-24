"""A comic as a Design job (Wan, 16 to 17 Nov 2026: "add comic as choice").

A comic is a `slides` job whose meta carries design "comic", like a poster or a card, so it is queued, listed, attached to a
post, judged and sent exactly as they are. What is its own sits in meta.comic:

  series, style        ids in the comic library (comic_library.py); a copy of each rides along in case one is deleted later
  script               {title, setting, panels} as Wan typed it, or as the writer wrote it from meta.brief (comic_writer.py)
  review               True: the written script waits for Wan before any picture is paid for (stage "script")
  words_mode           "auto" (the picture maker writes the words, Semasa checks them) or "art" (Semasa prints them)
  episode              this comic's number in its series: the series' count so far + 1, kept through a redraw
  words                how the words got there, for the page: {path, checked, exact, by, draws, why, tries, reader}
  stage                "script" (waiting for Wan) or "done"

THE WORDS (step 4 of the brief). The picture maker draws the whole comic, words included, because that is the look Wan
chose on 16 Nov. The picture is then read back by the picture reader Semasa already has (llm.describe_image: the reader
pinned on the API page first) and every bubble is compared with the script after case, spaces and the spacing around
punctuation are evened out. A difference means one more drawing. If that differs too, or nothing can read a picture, the
people are drawn with no words and Semasa prints the bubbles itself (comic.letter), which is exact by construction. Which of
the two happened, and whether the words were checked, is recorded and shown.

`make` is the whole of that and takes the picture maker and the reader as plain functions, so it runs in a test with no
network. `process` is the worker's job around it.
"""

from __future__ import annotations

import hashlib
import io
import re
import unicodedata
from datetime import UTC, datetime
from typing import Any

from PIL import Image

from . import comic, comic_library, comic_writer, db
from .log import get_logger

log = get_logger("semasa.comic_job")

# the makers the 16 Nov sample showed can spell a bubble come first; the rest still draw the people for the fallback
# Wan, 24 Nov 2026: "KioskAPI is the last choice to save credit": ChatGPT, the free and prepaid makers, KiosAPI ("openai") last
MAKERS = ("chatgpt", "cloudflare", "gemini", "replicate", "openai")
FULL_TRIES = 2                       # the comic with words is drawn at most twice before Semasa prints the words itself

READ_SYSTEM = "You copy the words printed in a comic exactly as they are drawn. Answer with one JSON object only."
READ_PROMPT = (
    "This picture is a comic page of four panels in a 2 by 2 grid. Copy the text of every speech bubble EXACTLY as it is "
    "drawn, letter for letter, including any spelling mistake, numbers, brackets and punctuation. Do not correct, translate, "
    "complete or tidy anything, and do not guess a word you cannot read: write what is there. JSON keys: "
    '"panels": [{"panel": 1, "bubbles": ["...", "..."]}, {"panel": 2, "bubbles": [...]}, {"panel": 3, "bubbles": [...]}, '
    '{"panel": 4, "bubbles": [...]}] where panel 1 is top left, 2 top right, 3 bottom left and 4 bottom right, and the '
    "bubbles of a panel are listed from left to right; "
    '"other_text": [any other words drawn in the picture that are not inside a speech bubble, or an empty list].')

_PUNCT_SPACE = re.compile(r"\s*([^\w\s])\s*")
_QUOTES = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u2013": "-", "\u2014": "-",
                         "\u2026": "...", "\u00a0": " "})


def norm(text: Any) -> str:
    """A bubble's words for comparing: one case, single spaces, and no space on either side of a punctuation mark, so
    "Klausa 40 (2) ." and "klausa 40(2)." are the same words while "Klausa 40(3)." is not."""
    s = unicodedata.normalize("NFKC", str(text or "")).translate(_QUOTES).casefold()
    return _PUNCT_SPACE.sub(r"\1", " ".join(s.split())).strip()


def read_panels(answer: Any) -> list[list[str]] | None:
    """The reader's answer as four lists of bubble texts, or None when it is not a reading of four panels."""
    panels = answer.get("panels") if isinstance(answer, dict) else None
    if not isinstance(panels, list) or len(panels) != comic.PANELS:
        return None
    out: list[list[str]] = [[] for _ in range(comic.PANELS)]
    for i, p in enumerate(panels):
        if not isinstance(p, dict):
            return None
        try:
            n = int(p.get("panel") or i + 1)
        except (TypeError, ValueError):
            n = i + 1
        if not 1 <= n <= comic.PANELS or out[n - 1]:
            n = i + 1
        bubbles = p.get("bubbles")
        if isinstance(bubbles, str):
            bubbles = [bubbles]
        out[n - 1] = [str(b) for b in (bubbles if isinstance(bubbles, list) else []) if str(b or "").strip()]
    return out


def compare(script: dict[str, Any], answer: Any) -> list[dict[str, Any]]:
    """[] when every bubble the reader saw is the script's bubble, panel by panel (the order inside a panel is free); else
    [{panel, want: [...], got: [...]}] for each panel that differs. An answer that is not a reading of four panels differs
    everywhere: an unreadable check is never a pass."""
    got = read_panels(answer)
    out = []
    for n, panel in enumerate(script["panels"], 1):
        want = [line["text"] for line in panel["lines"]]
        seen = got[n - 1] if got else []
        if sorted(norm(w) for w in want) != sorted(norm(g) for g in seen):
            out.append({"panel": n, "want": want, "got": seen[:4]})
    return out


def _jpeg(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=90)
    return buf.getvalue()


def _say(diff: dict[str, Any]) -> str:
    got = " | ".join(diff["got"]) or "nothing readable"
    return f'panel {diff["panel"]}: wanted "{" | ".join(diff["want"])}", drawn "{got}"'[:300]


def _full(script: dict[str, Any], style: dict[str, Any] | None, draw: Any, read: Any, words: dict[str, Any],
          keep: dict[str, Any] | None) -> tuple[Image.Image, dict[str, Any]] | None:
    """The picture maker draws the words too and the picture is read back (FULL_TRIES at most); None when nothing matched or the
    reader gave nothing (`words` then says why). The picture is shown whole: nothing of the maker's is ever cropped."""
    for _ in range(FULL_TRIES):
        picture = comic.trim(draw(comic.prompt_full(script, style)))
        words["draws"] += 1
        answer = read(_jpeg(picture))
        if answer is None:
            words["why"] = "the picture reader gave no answer, so the picture maker's words could not be checked"
            return None
        diff = compare(script, answer)
        if not diff:
            if keep is not None:
                keep.update(art=picture, wordless=False)
            other = answer.get("other_text") if isinstance(answer, dict) else None
            extra = [str(x)[:80] for x in (other if isinstance(other, list) else []) if str(x or "").strip()][:6]
            return picture, {**words, "path": "full", "checked": True, "exact": True, "by": "maker", "why": "",
                             **({"other_text": extra} if extra else {})}
        words["tries"].append([_say(d) for d in diff[:4]])
        words["why"] = f"the picture maker's words differed from the script twice ({_say(diff[0])})"
    return None


def _art(script: dict[str, Any], style: dict[str, Any] | None, draw: Any, read: Any, words: dict[str, Any],
         keep: dict[str, Any] | None) -> tuple[Image.Image, dict[str, Any]]:
    """The people are drawn with no words and Semasa prints the bubbles where the picture is EMPTY (comic.measure_heads reads the
    people's position off the picture; a bubble never covers a head). When the first drawing leaves no room for the words at the
    smallest readable size, or has a head against the panel's top edge, it is drawn ONCE more with a stronger framing instruction.
    Still no room: the picture maker's own words path when a reader exists (the panels are shown whole), else the comic is refused
    with the reason (comic.NoRoom). A head against the top edge that remains is recorded (`words.framing`), not refused."""
    reason = ""
    for attempt in range(2):
        art = comic.trim(draw(comic.prompt_art(script, style, strong=attempt > 0)))
        words["draws"] += 1
        heads = comic.measure_heads(art)
        touching = [i + 1 for i, e in enumerate(heads.edges) if e["top"]]
        try:
            lettered = comic.letter(art, script, heads=heads)
        except comic.NoRoom as exc:
            also = f"; a head also touches the top edge of panel {', '.join(map(str, touching))}" if touching else ""
            reason = str(exc) + also
            words.setdefault("framing", []).append(f"drawing {attempt + 1}: {reason}")
            continue
        if touching and attempt == 0:
            where = ", ".join(map(str, touching))
            words.setdefault("framing", []).append(f"drawing 1: a head touches the top edge of panel {where}")
            continue
        if touching:
            words.setdefault("framing", []).append(
                f"drawing 2: a head still touches the top edge of panel {', '.join(map(str, touching))}")
        if keep is not None:
            keep.update(art=art, wordless=True)
        return lettered, {**words, "path": "art", "exact": True, "by": "semasa", "retried": attempt > 0}
    words["why"] = f"{reason} (drawn twice)"
    if read is not None:
        got = _full(script, style, draw, read, words, keep)
        if got:
            return got[0], {**got[1], "why": f"{words['why']}: the picture maker's own words are used instead"}
    raise comic.NoRoom(f"{words['why']}. Shorten the longest bubble or ask for fewer words, then draw again")


def make(script: dict[str, Any], style: dict[str, Any] | None, draw: Any, read: Any = None, *,
         mode: str = "auto", keep: dict[str, Any] | None = None) -> tuple[Image.Image, dict[str, Any]]:
    """(the square comic, how its words got there). `draw(prompt) -> picture bytes`; `read(jpeg bytes) -> the reader's JSON
    answer, or None when it gave nothing`; `read` itself None means there is no reader. Every picture is trimmed of the
    picture maker's stray border first. See the module note for the steps.

    `keep`, when given, receives what a film made from this comic needs (the daily series, comic_film.py): `keep["art"]` is
    the square picture BEFORE any words are on it (only when Semasa printed the words, so the picture is wordless) and
    `keep["wordless"]` says which it is. Without wordless art the film shows the drawn picture as it is."""
    words: dict[str, Any] = {"path": "", "checked": False, "exact": False, "by": "", "draws": 0, "why": "", "tries": []}
    if mode != "art":
        if read is None:
            words["why"] = "no picture reader is available, so the picture maker's words could not be checked"
        else:
            got = _full(script, style, draw, read, words, keep)
            if got:
                return got
    else:
        words["why"] = "Semasa was asked to print the words itself"
    # in "auto" the picture maker's own words were already tried above, so a failure here is final; in "art" they are the way out
    return _art(script, style, draw, read if mode == "art" else None, words, keep)


# ------------------------------------------------------------------------------------------------------------ the worker

def episodes_so_far(store: Any, series_id: str, row_id: str) -> int:
    """How many episodes the series has: its finished comics other than this one, and never less than the highest number
    one of them carries (a deleted episode's number is not handed out again while a later one exists)."""
    try:
        rows = (store.table(db.MEDIA).select("id,status,meta").eq("mode", "slides").eq("meta->>design", "comic")
                .eq("status", "done").limit(2000).execute().data or [])
    except Exception as exc:  # noqa: BLE001 - a count that cannot be read numbers this episode 1 rather than failing it
        log.info("could not count the episodes of %s: %s", series_id, str(exc)[:120])
        return 0
    count, highest = 0, 0
    for r in rows:
        c = ((r.get("meta") or {}).get("comic") or {}) if isinstance(r.get("meta"), dict) else {}
        if r.get("id") == row_id or c.get("series") != series_id or not c.get("episode"):
            continue
        count += 1
        highest = max(highest, _number(c["episode"]))
    return max(count, highest)


def _number(value: Any) -> int:
    """An episode number Wan typed or an earlier drawing kept: a whole number from 1 to 9999, else 0 (count it instead)."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 0
    return n if 1 <= n <= 9999 else 0


def maker_chain(s: Any, store: Any, want: str = "") -> list[str]:
    """The picture makers a comic tries, in order: the one Wan picked for this comic first, then MAKERS, each only when it
    has credentials here."""
    from . import media_generator as mg
    out = [want] if want in mg.PROVIDER_CAPS else []
    out += [n for n in MAKERS if n not in out and mg.has_credentials(n, s, store)]
    return out or [s.provider]


def _reader(llm: Any) -> Any:
    """`read(jpeg) -> answer | None` on the picture reader Semasa already has, or None when nothing here can see."""
    if llm is None or not getattr(llm, "can_see", getattr(llm, "configured", False)):
        return None

    def read(data: bytes) -> Any:
        from .media_generator import shrink_for_read
        small, ct = shrink_for_read(data, "image/jpeg")
        return llm.describe_image(READ_SYSTEM, READ_PROMPT, small, ct, max_tokens=900)
    return read


def process(store: Any, row: dict[str, Any], s: Any, llm: Any = None, *, providers: dict[str, Any] | None = None,
            deadline: float | None = None, draw: Any = None, read: Any = "auto") -> bool:
    """One comic job. `draw` and `read` are for tests; the worker passes neither."""
    from . import ideas
    from . import media_generator as mg
    from .providers import OutOfTime, ProviderError

    row_id = row["id"]
    meta = dict(row.get("meta") or {})
    c = dict(meta.get("comic") or {})
    stream = str(meta.get("stream") or "regulab")
    try:
        settings = ideas.load_settings(store)
        lib = comic_library.library(settings.get("comic"))
        # a job that names none (an idea that asked for a comic without picking) takes the library's defaults
        series = comic_library.series_of(lib, c.get("series") or lib["default_series"], c.get("series_copy"))
        style = comic_library.style_of(lib, c.get("style") or lib["default_style"], c.get("style_copy"))
        if not series or not style:
            raise comic.ComicError("the comic's series or style is not in the library any more: pick one and send it again")
        c.update(series=series["id"], style=style["id"])
        reg = ((settings.get("brand") or {}).get("regulab") or {})
        source = str(meta.get("citation") or "")
        note = str((c.get("revise") or {}).get("note") or "") if isinstance(c.get("revise"), dict) else ""
        if (not c.get("script") or note) and str(meta.get("brief") or "").strip():
            written = comic_writer.write(llm, str(meta["brief"]), stream, series, source=source, note=note, brand=reg)
            cit = written.pop("citation", "")
            c.update(script=written, written_by=getattr(llm, "last_model", "") or None)
            c.pop("revise", None)
            if not source.strip():
                meta["citation"] = source = cit
            if c.get("review"):
                # the script waits for Wan before any picture is paid for: he reads it, edits it, then presses Draw
                c["stage"] = "script"
                script = comic_writer.assemble(written, series, stream, source)
                meta.update(comic=c, slides=comic_writer.artwork(script), flags=comic_writer.flags(script, stream, reg))
                db.finish_media(store, row_id, status="done", error=None, provider="semasa", meta=meta)
                log.info("%s: comic script written, waiting for Wan", row_id)
                return True
            meta["comic"] = c
            store.table(db.MEDIA).update({"meta": meta}).eq("id", row_id).execute()      # a retry draws these words again
        script = comic_writer.assemble(c.get("script"), series, stream, source)
        found = comic_writer.flags(script, stream, reg)
        meta["flags"] = found
        why = comic_writer.refusal(found)
        if why:
            raise comic.ComicError(f"the script breaks a post rule, so nothing was drawn: {why}")

        used: dict[str, Any] = {}
        if draw is None:
            names = maker_chain(s, store, str(c.get("maker") or ""))
            provs = providers if providers is not None else {}

            def draw(prompt: str) -> bytes:
                def one(p: Any) -> Any:
                    opts = {"resolution": "square", **({"size": "1024x1024"} if getattr(p, "name", "") == "openai" else {})}
                    return p.generate_from_text(prompt, opts)
                gen, name, tried = mg.generate_with_failover(provs, names, s, store, one, deadline=deadline, row_id=row_id)
                if not gen.data:
                    raise ProviderError("the picture maker returned no picture")
                used.update(maker=name, model=gen.model, **({"failover": tried} if tried else {}))
                return gen.data
        kept: dict[str, Any] | None = {} if c.get("film") else None       # a film is made from this comic (comic_film.py)
        picture, words = make(script, style, draw, _reader(llm) if read == "auto" else read,
                              mode=str(c.get("words_mode") or "auto"), keep=kept)
        if words.get("checked"):
            words["reader"] = getattr(llm, "last_model", "") or None
        episode = _number(c.get("episode")) or episodes_so_far(store, series["id"], row_id) + 1
        website = str(reg.get("website") or "www.kkmhalalconsultant.com")
        line = comic_library.episode_line(series["name"], episode, script["lang"])
        poster = comic.frame(picture, script, episode=line, stream=stream, website=website)

        day, stamp = datetime.now(UTC).strftime("%Y/%m"), datetime.now(UTC).strftime("%d%H%M%S")
        before = [x for x in (meta.get("slide_paths") or []) if x]
        old_art = ((meta.get("comic") or {}).get("art") or {}).get("path") if isinstance(meta.get("comic"), dict) else None
        path = f"{day}/{row_id}-{stamp}-comic.jpg"                 # a redraw is a new file, never an hour-old cached one
        url = db.upload_generated(store, path, poster, "image/jpeg")
        if kept and kept.get("art") is not None:
            # the square picture the film is cut into panels from, stored once so a failed film never draws the comic again
            art_path = f"{day}/{row_id}-{stamp}-comic-art.jpg"
            c["art"] = {"path": art_path, "url": db.upload_generated(store, art_path, _jpeg(kept["art"]), "image/jpeg"),
                        "wordless": bool(kept.get("wordless")), "size": list(kept["art"].size)}
        c.update(episode=episode, episode_line=line, words=words, stage="done", series_name=series["name"],
                 style_name=style["name"], **used)
        c.pop("revise", None)
        meta.update(comic=c, slides=comic_writer.artwork(script), slide_urls=[url], slide_paths=[path],
                    sha256=[hashlib.sha256(poster).hexdigest()], count=1, look="comic", format="portrait",
                    content_type="image/jpeg", bytes=len(poster), finished_at=datetime.now(UTC).isoformat())
        db.finish_media(store, row_id, status="done", generated_media_url=url, provider=used.get("maker") or "semasa",
                        model=used.get("model") or "comic-v1", error=None, meta=meta)
        new_art = (c.get("art") or {}).get("path")
        mg._drop_files(store, row_id, [x for x in before if x != path] + ([old_art] if old_art and old_art != new_art else []))
        if row.get("post_id"):
            db.attach_media_to_draft(store, row["post_id"], row_id)
        log.info("%s: comic drawn (%s episode %s, words %s, %d drawing(s))", row_id, series["id"], episode,
                 words["path"], words["draws"])
        return True
    except OutOfTime as exc:
        log.warning("%s: %s; handed back to the next run", row_id, exc)
        db.release_media(store, row)
        return False
    except Exception as exc:  # noqa: BLE001 - the row records it; the run continues
        attempts = int(row.get("attempts") or 0)
        final = isinstance(exc, (comic.ComicError, ProviderError)) or attempts >= s.max_attempts
        msg = f"{type(exc).__name__}: {str(exc)[:600]}"
        also = getattr(exc, "also_failed", None)
        if also:
            msg += " | also failed: " + "; ".join(f"{t['provider']}: {t['why'][:120]}" for t in also)[:600]
        log.error("%s: %s (attempt %d)", row_id, msg, attempts)
        db.finish_media(store, row_id, status="error" if final else "pending", error=msg, provider=row.get("provider"))
        return False
