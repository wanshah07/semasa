"""Writing styles (Wan, 11 Oct 2026, Phase 4: "writing style bank, asing dan boleh pilih; aku upload link post viral, AI analyse
dan terjemah jadi gaya penulisan"). `python -m semasa.writing_styles`, woken by the database when a style is added (supabase/067,
repository_dispatch 'writing_style') with a daily net.

A hook style (hook_styles.py) decides a post's FIRST LINE. A writing style decides how the rest of the caption reads: the voice,
the rhythm, the length of a sentence and a paragraph, how it is structured, how it moves from the hook to the substance, the
language mix, how it ends. Wan adds viral posts as links, pasted text and/or screenshots; this worker reads them and asks the
writer for

  * `instruction`  at most MAX_INSTRUCTION characters, imperative, to a writer: how a caption in this style is written;
  * `traits`       up to MAX_TRAITS short lines naming what marks the style, shown on the card.

What it never keeps: anything a source post said word for word (a sentence of the instruction that repeats SAME_RUN words in a
row from a source is dropped, as is any trait that does), a name, a brand, a handle or a link. A sentence that tries to lift a
rule is dropped (hook_styles.LIFT). The style goes into the caption writer's prompt AFTER every rule and the house style, and is
told it changes the voice only: never a fact, the citation, the stream's language, the hook requirement or any rule.

Links: a site that answers a plain fetch (a blog, a news page, most Facebook and Threads posts' preview) gives its text; LinkedIn,
Instagram and TikTok often give only a preview or nothing, which the card says, and pasted text or a screenshot fills the gap.
"""

from __future__ import annotations

import re
import sys
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from . import ai_config, api_status, db, hook_styles
from .llm import LLM
from .log import get_logger

log = get_logger("semasa.writing_styles")

TABLE = "semasa_writing_styles"
BUCKET = "semasa-reference"
MAX_LINKS = 8
MAX_IMAGES = 8
MAX_SAMPLE = 12000
MAX_ATTEMPTS = 3
PER_RUN = 3
MAX_INSTRUCTION = 1500
MAX_TRAITS = 8
SAME_RUN = 8                 # words in a row shared with a source = copied
PER_SOURCE = 3000            # characters of one source the writer is shown
MIN_WORDS = 40               # what the sources must give together before a style can be made of them

READ_SYSTEM = ("You read ONE screenshot of a social-media post and copy out its caption text exactly as printed "
               "(not the comments, not the buttons). Answer with one JSON object and nothing else.")
READ_PROMPT = ('JSON keys: "text" (the caption as printed, up to 2500 characters), "language" (ms, en or mixed), "format" (post, '
               'carousel, reel caption, thread or other). If there is no caption, return {"text": ""}.')
SYNTH_SYSTEM = ("You study several social-media posts that did well and describe their WRITING STYLE so another writer can "
                "write new posts the same way, on different subjects. Answer with ONE JSON object and nothing else.")
SYNTH_PROMPT = """The posts:
{posts}

Describe the style they share:
{{"name": "a short name for the style, at most 40 characters",
 "summary": "one sentence on what this style is",
 "instruction": "at most {limit} characters, imperative, to a writer: the voice and who is speaking, the register and the
  language mix, sentence and paragraph length and rhythm, how the post is structured from the first line to the end, how
  it moves from the opening to the substance, the devices it uses (questions, lists, line breaks, contrast, numbers as
  structure), how it ends, and what it avoids",
 "traits": ["at most {traits} short lines, each one thing that marks the style"]}}

Rules:
- Describe HOW the posts are written, never WHAT they say. Do not repeat any of their sentences, names, brands, products,
  places, figures, handles, hashtags or links.
- The instruction must not tell the writer to ignore, override or relax any rule, to invent a figure, an approval, a quote or
  a cure, to add a call to action, a link or a hashtag, or to use a name or a brand.
- No em dash."""

LINKISH = re.compile(r"https?://\S+|www\.\S+|@\w{2,}|#\w{2,}")
WORD = re.compile(r"[\w']+", re.UNICODE)
HARD_HOSTS = ("instagram.com", "linkedin.com", "tiktok.com", "x.com", "twitter.com")


# ---- what the writer made, cleaned ----------------------------------------------------------------------------------------

def _runs(text: str, n: int = SAME_RUN) -> set[tuple[str, ...]]:
    w = [x.lower() for x in WORD.findall(text or "")]
    return {tuple(w[i:i + n]) for i in range(max(0, len(w) - n + 1))}


def copied(line: str, sources: list[str], n: int = SAME_RUN) -> bool:
    """Whether `line` repeats `n` or more words in a row from any source."""
    mine = _runs(line, n)
    return bool(mine) and any(mine & _runs(s, n) for s in sources)


def clean_instruction(raw: Any, sources: list[str]) -> str:
    """The instruction, minus a sentence that lifts a rule, carries a link or a handle, or repeats a source; at most
    MAX_INSTRUCTION characters."""
    sentences = re.split(r"(?<=[.!?])\s+", " ".join(str(raw or "").replace("—", ", ").replace("–", " - ").split()))
    kept = [s for s in sentences if s and not hook_styles.LIFT.search(s) and not LINKISH.search(s) and not copied(s, sources)]
    text = " ".join(kept)
    return text[:MAX_INSTRUCTION].rsplit(" ", 1)[0] if len(text) > MAX_INSTRUCTION else text


def clean_traits(raw: Any, sources: list[str]) -> list[str]:
    out, seen = [], set()
    for item in raw if isinstance(raw, list) else []:
        t = " ".join(str(item or "").replace("—", ", ").split()).strip(" -•*")[:140]
        key = re.sub(r"\W+", "", t.lower())
        if len(t) < 4 or key in seen or LINKISH.search(t) or hook_styles.LIFT.search(t) or copied(t, sources):
            continue
        seen.add(key)
        out.append(t)
        if len(out) >= MAX_TRAITS:
            break
    return out


# ---- reading what Wan gave ------------------------------------------------------------------------------------------------

def good_links(row: dict[str, Any]) -> list[str]:
    out = []
    for u in row.get("links") or []:
        u = str(u or "").strip()
        p = urlparse(u)
        if p.scheme in ("http", "https") and p.netloc and u not in out:
            out.append(u)
    return out[:MAX_LINKS]


def read_links(links: list[str], reader: Any = None) -> tuple[list[str], list[str]]:
    """([the text each link gave], [a note for each link that gave nothing])."""
    if reader is None:
        from .ideas import read_source  # imported here: ideas imports this module for the writer's block
        reader = read_source
    texts, notes = [], []
    for i, url in enumerate(links, 1):
        try:
            got = reader(url) or {}
        except Exception as exc:  # noqa: BLE001 - one dead link does not stop the others
            got = {"ok": False, "why": f"{type(exc).__name__}"}
        body = " ".join(" ".join([str(got.get("description") or ""), str(got.get("text") or "")]).split())
        if len(WORD.findall(body)) >= 15:
            texts.append(body[:PER_SOURCE])
            continue
        host = urlparse(url).netloc.lower()
        hard = any(host == h or host.endswith("." + h) for h in HARD_HOSTS)
        why = (f" ({host} hides posts from a plain fetch: paste the text or add a screenshot)" if hard
               else f" ({got.get('why') or 'nothing readable'})")
        notes.append(f"link {i} gave no post text{why}")
    return texts, notes


def read_screens(llm: Any, images: list[bytes]) -> tuple[list[str], list[str]]:
    texts, notes = [], []
    for i, data in enumerate(images, 1):
        try:
            small, ct = hook_styles.shrink(data)
        except Exception as exc:  # noqa: BLE001
            notes.append(f"screenshot {i} is not a readable picture ({type(exc).__name__})")
            continue
        got = llm.describe_image(READ_SYSTEM, READ_PROMPT, small, ct, max_tokens=1500)
        text = " ".join(str((got or {}).get("text") or "").split()) if isinstance(got, dict) else ""
        if len(WORD.findall(text)) >= 15:
            texts.append(text[:PER_SOURCE])
        else:
            notes.append(f"screenshot {i} showed no caption")
    return texts, notes


def own_paths(row: dict[str, Any]) -> list[str]:
    owner = str(row.get("created_by") or "")
    paths = [str(p) for p in (row.get("images") or [])]
    return [p for p in paths if owner and p.startswith(f"{owner}/") and ".." not in p][:MAX_IMAGES]


def synthesise(llm: Any, sources: list[str]) -> dict[str, Any]:
    """{name, summary, instruction, traits}; raises ValueError with a reason when it cannot."""
    posts = "\n\n".join(f"POST {i}:\n{s}" for i, s in enumerate(sources, 1))
    user = SYNTH_PROMPT.format(posts=posts, limit=MAX_INSTRUCTION, traits=MAX_TRAITS)
    out = None
    for _ in range(2):
        out = llm.chat_json(SYNTH_SYSTEM, user, max_tokens=2500)
        if isinstance(out, dict) and len(clean_instruction(out.get("instruction"), sources)) >= 80:
            break
        user += ("\n\nYOUR LAST ANSWER HAD NO USABLE INSTRUCTION. Describe HOW the posts are written in your own words, "
                 "without repeating their sentences, and answer again.")
    instruction = clean_instruction((out or {}).get("instruction") if isinstance(out, dict) else "", sources)
    if len(instruction) < 80:
        raise ValueError("the posts did not give a usable writing style: add more of them, or longer ones")
    return {"name": " ".join(str(out.get("name") or "").split())[:40],
            "summary": " ".join(str(out.get("summary") or "").split())[:300],
            "instruction": instruction, "traits": clean_traits(out.get("traits"), sources)}


# ---- the worker -----------------------------------------------------------------------------------------------------------

def claim(store: Any, limit: int = PER_RUN) -> list[dict[str, Any]]:
    rows = store.table(TABLE).select("*").eq("status", "new").order("created_at").limit(limit).execute().data or []
    got = []
    for r in rows:
        if r.get("source") == "manual":
            continue
        if int(r.get("attempts") or 0) >= MAX_ATTEMPTS:
            store.table(TABLE).update({"status": "error", "error": "gave up after 3 tries: add the posts again"}) \
                .eq("id", r["id"]).execute()
            continue
        hit = store.table(TABLE).update({"status": "working", "attempts": int(r.get("attempts") or 0) + 1, "error": None}) \
            .eq("id", r["id"]).eq("status", "new").execute().data
        if hit:
            got.append(hit[0])
    return got


def process(store: Any, llm: Any, row: dict[str, Any], *, download: Any = None, reader: Any = None) -> str:
    """Reads one style's posts and saves the style. Returns "ready" or "error"; never raises."""
    download = download or (lambda path: store.storage.from_(BUCKET).download(path))
    patch: dict[str, Any]
    try:
        if llm is None or not getattr(llm, "configured", False):
            raise ValueError("no AI writer is set: add one in the AI tab, then press Try again")
        sources, notes = read_links(good_links(row), reader)
        sample = str(row.get("sample") or "").strip()[:MAX_SAMPLE]
        if sample:
            # pasted text may hold several posts: blank lines between them keep them apart
            parts = [" ".join(p.split()) for p in re.split(r"\n\s*\n", sample) if p.strip()]
            sources += [p[:PER_SOURCE] for p in parts if len(WORD.findall(p)) >= 8] or [" ".join(sample.split())[:PER_SOURCE]]
        paths = own_paths(row)
        if paths:
            if not getattr(llm, "can_see", False):
                notes.append("the screenshots were skipped: no picture reader is set in the AI tab")
            else:
                images = []
                for p in paths:
                    try:
                        images.append(download(p))
                    except Exception as exc:  # noqa: BLE001
                        log.info("writing style %s: %s not downloaded (%s)", row.get("id"), p, str(exc)[:100])
                got, more = read_screens(llm, images)
                sources += got
                notes += more
        if sum(len(WORD.findall(s)) for s in sources) < MIN_WORDS:
            raise ValueError("nothing readable came from the posts" + (f" ({'; '.join(notes[:3])})" if notes else "")
                             + ": paste the post text or add screenshots")
        made = synthesise(llm, sources)
        patch = {"status": "ready", "error": None, "summary": made["summary"], "instruction": made["instruction"],
                 "traits": made["traits"], "name": (row.get("name") or "").strip() or made["name"] or "My writing style"}
        if notes:
            patch["error"] = "Some posts were skipped: " + "; ".join(notes[:4])
    except Exception as exc:  # noqa: BLE001 - the reason goes on the style, the page shows it
        log.warning("writing style %s failed: %s", row.get("id"), str(exc)[:200])
        patch = {"status": "error", "error": str(exc)[:300]}
    store.table(TABLE).update({**patch, "updated_at": datetime.now(UTC).isoformat()}).eq("id", row["id"]).execute()
    return patch["status"]


def make_llm(store: Any) -> Any | None:
    try:
        api_status.attach(store, "writing_styles")
        return LLM(ai_config.llm_for(store))
    except Exception as exc:  # noqa: BLE001
        log.warning("no LLM: %s", exc)
        return None


def run(store: Any, llm: Any = None, *, download: Any = None, reader: Any = None) -> dict[str, int]:
    counts = {"ready": 0, "error": 0}
    todo = claim(store)
    if not todo:
        return counts
    llm = llm if llm is not None else make_llm(store)
    for row in todo:
        counts[process(store, llm, row, download=download, reader=reader)] += 1
    return counts


# ---- what the caption writer is told --------------------------------------------------------------------------------------

def pick(store: Any, idea: dict[str, Any] | None, settings: dict[str, Any] | None) -> dict[str, Any] | None:
    """The writing style to write with: the idea's own (brief.writing_style; "none" = no style for this idea), else Wan's
    default (settings.writing_style.id), else None. A style that is gone, not ready or unreadable is None, never an error."""
    brief = (idea or {}).get("brief") if isinstance((idea or {}).get("brief"), dict) else {}
    chosen = str(brief.get("writing_style") or "").strip()
    if not chosen:
        chosen = str(((settings or {}).get("writing_style") or {}).get("id") or "").strip()
    if not chosen or chosen == "none":
        return None
    try:
        rows = store.table(TABLE).select("*").eq("id", chosen).execute().data or []
    except Exception as exc:  # noqa: BLE001 - 067 not applied yet
        log.info("writing style %s not read (%s): the house style alone", chosen, str(exc)[:100])
        return None
    row = rows[0] if rows else None
    if not row or row.get("status") != "ready" or len(str(row.get("instruction") or "").strip()) < 20:
        return None
    return row


def pick_for_idea(store: Any, idea_id: Any) -> dict[str, Any] | None:
    """pick() for a film made from an idea, reading the idea and the default itself. Never raises."""
    idea: dict[str, Any] | None = None
    if idea_id:
        try:
            got = store.table("semasa_ideas").select("brief").eq("id", idea_id).execute().data or []
            idea = got[0] if got else None
        except Exception:  # noqa: BLE001
            idea = None
    settings: dict[str, Any] = {}
    try:
        got = store.table("semasa_settings").select("value").eq("key", "writing_style").execute().data or []
        settings = {"writing_style": (got[0].get("value") or {}) if got else {}}
    except Exception:  # noqa: BLE001
        settings = {}
    return pick(store, idea, settings)


def block(style: dict[str, Any] | None, *, film: bool = False) -> str:
    """The writing-style block for the writer's prompt, or "" with no style. It sits after the rules and the house style and says
    it can never lift one."""
    if not style:
        return ""
    what = "the film's script" if film else "the caption"
    name = " ".join(str(style.get("name") or "My writing style").split())[:60]
    instruction = " ".join(str(style.get("instruction") or "").split())[:2000]
    traits = [" ".join(str(t).split())[:140] for t in (style.get("traits") or []) if str(t).strip()][:MAX_TRAITS]
    return (f"\n\nWRITING STYLE \"{name}\" (Wan's choice for this post). It shapes how {what} reads: the voice, the rhythm, the "
            "structure and the length. It changes nothing else: every rule above, the facts and figures, the citation, the "
            "stream's language and the required hook outrank it, and it never adds a call to action, a link, a hashtag or a "
            "claim. Write in the post's own language even when the style was learnt from posts in another.\n"
            f"{instruction}" + ("\nWhat marks it:\n- " + "\n- ".join(traits) if traits else ""))


def main() -> int:
    counts = run(db.client())
    print(f"Writing styles: {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
