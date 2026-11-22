"""Every caption inside its platform's hard limit (Wan, 22 Nov 2026: "Make sure caption untuk semua platform di bawah maksimum
aksara dibenarkan").

The limits are rules/compliance.json `limits` (Instagram 2,200, Threads 500 a post and 5 posts, LinkedIn 3,000, Facebook 63,206)
plus TikTok's 2,200 (it sends the Instagram caption). One rule, used wherever a caption is written (the idea writer, a revision,
a Motion film's draft, an imported video, the daily comic, a Telegram edit) and once more by the publisher just before it hands a
post over, so nothing over a limit ever reaches a platform. The page carries the same rule (web/src/lib/captionFit.js).

How a caption is brought under its limit, never by cutting a sentence in half where it can be helped:
  * the hashtags and the follow line at the end stay;
  * whole paragraphs come out of the END of the body (the hook, which opens it, is the last to go);
  * only a single paragraph that is itself over the limit is cut, at the last full sentence (else the last whole word).
A Threads caption becomes a chain of at most 5 posts, each inside 500, separated by a line holding only `---` (the form the page,
the scan and the sender all read the same way); the hashtags ride on the last post, never alone (Threads refuses a post of tags).

Lengths are counted in UTF-16 units, which is what the platforms count and is never less than the characters the scan counts, so
an emoji can never tip a fitted caption back over.
"""

from __future__ import annotations

import re
from typing import Any

from . import compliance

TIKTOK_MAX = 2200
SEP = "---"
_SEP_LINE = re.compile(rf"(?m)^[ \t]*{re.escape(SEP)}[ \t]*$")
_TAGS_ONLY = re.compile(r"^(?:\s*#[^\s#]+)+\s*$")
_FOLLOW = re.compile(r"\b(follow|ikuti|ikut kami|ikut saya)\b", re.I)


def units(text: str) -> int:
    """The caption's length as the platforms count it (UTF-16 code units)."""
    return len(str(text or "").encode("utf-16-le")) // 2


def _split(para: str, limit: int) -> tuple[str, str]:
    """(head, rest): `head` is the paragraph up to its last full sentence or line inside `limit` (else its last whole word,
    else a hard cut), with its own line breaks kept; `rest` is what is left over."""
    if units(para) <= limit:
        return para, ""
    best = 0
    for m in re.finditer(r"[.!?\u2026](?=\s)|\n", para):
        end = m.start() if m.group() == "\n" else m.end()
        if units(para[:end].rstrip()) > limit:
            break
        best = end
    if not best:
        for m in re.finditer(r"\s+", para):
            if units(para[:m.start()]) > limit:
                break
            best = m.start()
    if not best:
        best = len(para)
        while best and units(para[:best]) > limit:
            best -= 1
    return para[:best].rstrip(), para[best:].strip()


def _cut(para: str, limit: int) -> str:
    return _split(para, limit)[0]


def _tail(paras: list[str]) -> tuple[list[str], list[str]]:
    """(body, tail): the hashtag and follow paragraphs at the end are the tail, kept whatever else comes out."""
    body, tail = list(paras), []
    while len(body) > 1 and (_TAGS_ONLY.match(body[-1]) or _FOLLOW.search(body[-1]) and units(body[-1]) <= 200):
        tail.insert(0, body.pop())
    return body, tail


def _trim_tags(tags: str, room: int) -> str:
    """As many of the hashtags as fit in `room`, in their order."""
    out = ""
    for tag in tags.split():
        nxt = f"{out} {tag}" if out else tag
        if units(nxt) > room:
            break
        out = nxt
    return out


def fit_caption(text: str, limit: int) -> str:
    """A caption inside `limit`. One already inside is returned exactly as it is."""
    text = str(text or "")
    if not limit or units(text) <= limit:
        return text
    paras = [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    body, tail = _tail(paras)
    join = "\n\n".join
    while len(body) > 1 and units(join(body + tail)) > limit:
        body.pop()
    out = join(body + tail)
    if units(out) <= limit:
        return out
    # one paragraph left and still over: the tail gives way first (follow line, then tags), then the paragraph is cut
    while tail and units(join(body + tail)) > limit:
        last = tail[-1]
        room = limit - units(join(body + tail[:-1])) - 2
        if _TAGS_ONLY.match(last) and room > 0 and (short := _trim_tags(last, room)):
            tail[-1] = short
            break
        tail.pop()
    out = join(body + tail)
    if units(out) <= limit:
        return out
    room = limit - (units(join(tail)) + 2 if tail else 0)
    return join([_cut(body[0], max(1, room))] + tail) if room > 20 else _cut(body[0], limit)


def fit_thread(text: str, limit: int = 500, parts: int = 5) -> str:
    """A Threads caption as a chain of at most `parts` posts, each inside `limit`. One already inside is returned as it is
    (a caption with no `---` is judged by how the sender splits it: senders.thread_levels)."""
    from . import senders
    text = str(text or "")
    explicit = [p.strip() for p in _SEP_LINE.split(text) if p.strip()]
    if len(explicit) > 1:
        if len(explicit) <= parts and all(units(p) <= limit for p in explicit):
            return text
    elif units(text) <= limit:
        return text
    else:
        levels = senders.thread_levels(text, parts, limit)
        loose = any(_TAGS_ONLY.match(lv) for lv in levels[1:])
        if len(levels) <= parts and all(units(lv) <= limit for lv in levels) and not loose:
            # the sender would split it cleanly; written out with --- so the page and the scan read the same chain
            return f"\n\n{SEP}\n\n".join(levels)
    # the pieces to pack: each post's paragraphs, a paragraph over the limit cut at its last full sentence
    blocks: list[list[str]] = []
    for piece in (explicit if len(explicit) > 1 else [text]):
        paras = [p.strip() for p in re.split(r"\n\s*\n", piece) if p.strip()]
        blocks.append(paras)
    flat = [p for b in blocks for p in b]
    body, tail = _tail(flat)
    tags = " ".join(t for t in tail if _TAGS_ONLY.match(t))
    follow = [t for t in tail if not _TAGS_ONLY.match(t)]
    units_in: list[str] = []
    for p in body + follow:
        while units(p) > limit:
            head, p = _split(p, limit)
            units_in.append(head)
        if p:
            units_in.append(p)
    posts: list[str] = []
    hook_alone = len(explicit) <= 1
    for u in units_in:
        if posts and not (hook_alone and len(posts) == 1) and units(posts[-1]) + 2 + units(u) <= limit:
            posts[-1] += "\n\n" + u
        else:
            posts.append(u)
    if len(posts) > parts:
        keep_follow = [p for p in posts[parts:] if _FOLLOW.search(p)]
        posts = posts[:parts]
        if keep_follow and units(posts[-1]) + 2 + units(keep_follow[-1]) <= limit:
            posts[-1] += "\n\n" + keep_follow[-1]
    if tags and posts:
        room = limit - units(posts[-1]) - 2
        short = _trim_tags(tags, room) if room > 0 else ""
        if short:
            posts[-1] += "\n\n" + short
    return f"\n\n{SEP}\n\n".join(posts)


def limit_of(stream: str, platform: str) -> dict[str, Any] | None:
    """The platform's limit for the stream: {max} or, for a thread, {max, parts}. TikTok reads Instagram's rule."""
    lims = compliance.RULES["limits"].get(stream or "regulab", {})
    if platform == "tiktok":
        return {"max": TIKTOK_MAX}
    lim = lims.get(platform)
    return dict(lim) if isinstance(lim, dict) and lim.get("max") else None


def fit(text: str, platform: str, stream: str) -> str:
    """One caption inside its platform's limit."""
    lim = limit_of(stream, platform)
    if not lim or not isinstance(text, str):
        return text
    if lim.get("parts"):
        return fit_thread(text, int(lim["max"]), int(lim["parts"]))
    return fit_caption(text, int(lim["max"]))


def fit_text(text: Any, stream: str) -> Any:
    """Every caption of a post ({lang: {platform: caption}}) inside its platform's limit; anything else is returned as it is."""
    if not isinstance(text, dict):
        return text
    out: dict[str, Any] = {}
    for lg, inner in text.items():
        out[lg] = ({p: fit(t, p, stream) for p, t in inner.items()} if isinstance(inner, dict) else inner)
    return out


def over(text: Any, stream: str) -> list[str]:
    """The `lang.platform` captions that are over their limit (empty when every one fits)."""
    fitted = fit_text(text, stream)
    if not isinstance(text, dict):
        return []
    return [f"{lg}.{p}" for lg, inner in text.items() if isinstance(inner, dict)
            for p, t in inner.items() if fitted[lg][p] != t]
