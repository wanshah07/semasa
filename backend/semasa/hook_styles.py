"""Hook styles made from screenshots (Wan, 6 Nov 2026: "add style hook bank, I can add screenshot and bot can analyze and
create the hook and instruction to replace current instruction when select"). `python -m semasa.hook_styles`, woken by the
database when a style is added (supabase/060, repository_dispatch 'hook_style') with a daily net.

Wan adds a style on the page: a name and up to 8 screenshots of hooks he likes (a post, a reel caption, a carousel cover). This
worker reads each screenshot with the picture reader, then asks the writer to turn what it saw into

  * `instruction`  how a hook of this style is written (voice, structure, length, devices, language mix, what to avoid), which
                   REPLACES the default guidance in the writer's required-hook block while the style is selected;
  * `shapes`       fill-in-the-blank patterns (`___` for every specific), the same kind as the 25 built-in ones. The writer must
                   build every post's first line on one of them, exactly as it must with the built-in 25 (hook_bank.py).

A shape is a pattern, never somebody else's sentence: the worker asks for every name, brand, number and product to become a
blank, drops anything with no blank or too much fixed wording, and keeps nothing the screenshots said word for word. The
screenshots themselves stay in Wan's own folder in `semasa-reference`; Semasa's public posts never carry them. The style's
guidance goes into the writer's prompt AFTER every rule and is told it cannot lift one; sentences in it that try to override the
rules are dropped.
"""

from __future__ import annotations

import io
import re
import sys
from datetime import UTC, datetime
from typing import Any

from PIL import Image

from . import ai_config, api_status, db, hook_bank
from .llm import LLM
from .log import get_logger

log = get_logger("semasa.hook_styles")

TABLE = hook_bank.STYLES
BUCKET = "semasa-reference"
MAX_IMAGES = 8
MAX_ATTEMPTS = 3
PER_RUN = 3
MIN_SHAPES, MAX_SHAPES = 3, 30
MAX_INSTRUCTION = 1200

READ_SYSTEM = ("You read ONE screenshot of a social-media post or reel and report only its HOOK: the first line(s) meant to stop "
               "the scroll. Answer with one JSON object and nothing else.")
READ_PROMPT = ('JSON keys: "hooks" (every hook line visible, exactly as printed, at most 6), "language" (ms, en or mixed), '
               '"format" (post, reel, carousel cover or other), "voice" (a few words: the tone, the person speaking, '
               'the register), "devices" (a few words: what makes it work, such as a question, a contrast, a number '
               'pattern, an admission, a command). If the screenshot has no hook, return {"hooks": []}.')
SYNTH_SYSTEM = ("You turn what several screenshots showed into a HOOK STYLE a social-media writer can follow. "
                "Answer with ONE JSON object and nothing else.")
SYNTH_PROMPT = """The screenshots showed these hooks and notes:
{seen}

Write the style:
{{"name": "a short name for the style, at most 40 characters",
 "summary": "one sentence on what this style is",
 "instruction": "at most {limit} characters, imperative, to a writer: how a hook in this style is written (the voice, the
  structure, the length, the devices that make it work, the language mix) and what it avoids. It must not tell the writer
  to ignore, override or relax any rule, to invent a figure, an approval or a cure, or to use a name or a brand",
 "shapes": [{{"family": "curiosity | transform | vulnerable | bold | relatable | other",
  "text": "a fill-in-the-blank pattern"}}]}}

Rules for the shapes ({lo} to {hi} of them, each different):
- A shape is a PATTERN taken from the examples, not an example. Replace EVERY specific (a name, a brand, a product, a number,
  a place, a result) with ___ and keep only the structure and the connecting words of the voice. Never copy an example
  sentence as it was written.
- Each shape has at least one ___ and is one sentence or two short ones, at most 160 characters, in the language of the
  examples.
- "vulnerable" is a first-person confession about the speaker's own struggle; "bold" an opinion; "transform" a before and
  after; "curiosity" opens a gap; "relatable" says what the reader already feels.
- No hashtags, no links, no handles, no em dash."""

# a style may not tell the writer to lift a rule: the sentences that try are dropped (the block says the rules outrank it)
LIFT = re.compile(r"\b(ignore|disregard|override|bypass|forget|relax)\b[^.]{0,60}\b(rule|rules|instruction|instructions|"
                  r"check|checks|"
                  r"filter|guardrail|above|previous|system)\b|system prompt|you are now|never refuse|no matter what|"
                  r"(invent|make up|fabricate)\b[^.]{0,40}\b(figure|number|stat|statistic|quote|result|approval|cure)", re.I)
URLISH = re.compile(r"https?://|www\.|@\w|#\w")
BLANKISH = re.compile(r"_{2,}|\[[^\]\n]{0,24}\]|\{[^}\n]{0,24}\}|<[^>\n]{0,24}>|…{1,2}|\.{3,}")


def clean_shape(text: Any) -> str:
    """One pattern in the house form, or "" when it is not a usable one: blanks written any way become ___, there is at least one
    and not more than five, a fixed part that is neither empty nor most of a sentence, no link or handle, no em dash."""
    t = " ".join(str(text or "").replace("—", ", ").replace("–", " - ").split())
    if not t or URLISH.search(t):
        return ""
    t = BLANKISH.sub("___", t)
    t = re.sub(r"(___[\s,/&+-]*){2,}", "___ ", t) if re.search(r"(___[\s,]*){3,}", t) else t
    t = " ".join(t.split())
    blanks = t.count("___")
    fixed = re.sub(r"[\W_]+", " ", t.replace("___", " ")).strip()
    if blanks < 1 or blanks > 5 or len(t) < 12 or len(t) > 160 or len(fixed) < 6 or len(fixed) > 110:
        return ""
    return t


def clean_shapes(raw: Any) -> list[dict[str, str]]:
    out, seen = [], set()
    for item in raw if isinstance(raw, list) else []:
        text = clean_shape(item.get("text") if isinstance(item, dict) else item)
        key = re.sub(r"\W+", "", text.lower())
        if not text or key in seen:
            continue
        seen.add(key)
        fam = str((item.get("family") if isinstance(item, dict) else "") or "other").strip().lower()
        out.append({"family": fam if fam in hook_bank.FAMILY_NAMES else "other", "text": text})
        if len(out) >= MAX_SHAPES:
            break
    return out


def clean_instruction(raw: Any) -> str:
    """The guidance, minus any sentence that tries to lift a rule, at most MAX_INSTRUCTION characters."""
    sentences = re.split(r"(?<=[.!?])\s+", " ".join(str(raw or "").replace("—", ", ").split()))
    kept = [s for s in sentences if s and not LIFT.search(s)]
    text = " ".join(kept)
    return text[:MAX_INSTRUCTION].rsplit(" ", 1)[0] if len(text) > MAX_INSTRUCTION else text


def shrink(data: bytes) -> tuple[bytes, str]:
    """The screenshot as a JPEG of at most 1600 px: a phone screenshot is megabytes, and a reader needs none of it."""
    im = Image.open(io.BytesIO(data))
    im.load()
    im = im.convert("RGB")
    im.thumbnail((1600, 1600))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return buf.getvalue(), "image/jpeg"


def read_screens(llm: Any, images: list[bytes]) -> tuple[list[dict[str, Any]], list[str]]:
    """([what each screenshot showed], [notes about screenshots that could not be read])."""
    seen, notes = [], []
    for i, data in enumerate(images, 1):
        try:
            small, ct = shrink(data)
        except Exception as exc:  # noqa: BLE001 - one bad file does not stop the others
            notes.append(f"screenshot {i} is not a readable picture ({type(exc).__name__})")
            continue
        got = llm.describe_image(READ_SYSTEM, READ_PROMPT, small, ct, max_tokens=900)
        if not isinstance(got, dict):
            notes.append(f"screenshot {i} could not be read")
            continue
        hooks = [" ".join(str(h).split())[:240] for h in (got.get("hooks") or []) if str(h).strip()][:6]
        if hooks:
            keys = ("language", "format", "voice", "devices")
            seen.append({"hooks": hooks, **{k: " ".join(str(got.get(k) or "").split())[:80] for k in keys}})
        else:
            notes.append(f"screenshot {i} showed no hook")
    return seen, notes


def synthesise(llm: Any, seen: list[dict[str, Any]]) -> dict[str, Any]:
    """{name, summary, instruction, shapes} from what the screenshots showed; raises ValueError with a reason when it cannot."""
    lines = []
    for i, s in enumerate(seen, 1):
        lines.append(f"Screenshot {i} ({s.get('format') or '?'}, {s.get('language') or '?'}; voice: {s.get('voice') or '?'}; "
                     f"devices: {s.get('devices') or '?'}):\n" + "\n".join(f"  - {h}" for h in s["hooks"]))
    user = SYNTH_PROMPT.format(seen="\n".join(lines), limit=MAX_INSTRUCTION, lo=min(8, MAX_SHAPES), hi=MAX_SHAPES)
    out = None
    for _ in range(2):
        out = llm.chat_json(SYNTH_SYSTEM, user, max_tokens=3000)
        if isinstance(out, dict) and len(clean_shapes(out.get("shapes"))) >= MIN_SHAPES:
            break
        user += (f"\n\nYOUR LAST ANSWER HAD FEWER THAN {MIN_SHAPES} USABLE SHAPES. Each shape needs a ___ for every specific and "
                 "a short fixed part. Answer again.")
    shapes = clean_shapes((out or {}).get("shapes") if isinstance(out, dict) else None)
    if len(shapes) < MIN_SHAPES:
        raise ValueError(f"the screenshots gave fewer than {MIN_SHAPES} usable hook shapes: "
                         "add clearer screenshots of the hook line")
    return {"name": " ".join(str(out.get("name") or "").split())[:40],
            "summary": " ".join(str(out.get("summary") or "").split())[:300],
            "instruction": clean_instruction(out.get("instruction")), "shapes": shapes}


def claim(store: Any, limit: int = PER_RUN) -> list[dict[str, Any]]:
    """New styles, oldest first, each marked working before it is read (a second run cannot take the same one)."""
    rows = (store.table(TABLE).select("*").eq("status", "new").order("created_at").limit(limit).execute().data or [])
    got = []
    for r in rows:
        if int(r.get("attempts") or 0) >= MAX_ATTEMPTS:
            store.table(TABLE).update({"status": "error", "error": "gave up after 3 tries: add the screenshots again"}) \
                .eq("id", r["id"]).execute()
            continue
        hit = store.table(TABLE).update({"status": "working", "attempts": int(r.get("attempts") or 0) + 1, "error": None}) \
            .eq("id", r["id"]).eq("status", "new").execute().data
        if hit:
            got.append(hit[0])
    return got


def own_paths(row: dict[str, Any]) -> list[str]:
    """The screenshots of a style that sit in its creator's own folder (a path anywhere else is never read)."""
    owner = str(row.get("created_by") or "")
    out = []
    for p in row.get("images") or []:
        p = str(p)
        if owner and p.startswith(f"{owner}/") and ".." not in p:
            out.append(p)
    return out[:MAX_IMAGES]


def process(store: Any, llm: Any, row: dict[str, Any], *, download: Any = None) -> str:
    """Reads one style's screenshots and saves what they gave. Returns "ready" or "error"; never raises."""
    download = download or (lambda path: store.storage.from_(BUCKET).download(path))
    patch: dict[str, Any]
    try:
        if llm is None or not getattr(llm, "can_see", getattr(llm, "configured", False)):
            raise ValueError("no picture reader is set: add a vision model in the AI tab, then press Try again")
        paths = own_paths(row)
        if not paths:
            raise ValueError("this style has no screenshots of its own")
        images = []
        for p in paths:
            try:
                images.append(download(p))
            except Exception as exc:  # noqa: BLE001 - one missing file does not stop the others
                log.info("hook style %s: %s not downloaded (%s)", row.get("id"), p, str(exc)[:100])
        seen, notes = read_screens(llm, images)
        if not seen:
            raise ValueError("no hook could be read from the screenshots" + (f" ({'; '.join(notes[:3])})" if notes else ""))
        made = synthesise(llm, seen)
        patch = {"status": "ready", "error": None, "summary": made["summary"], "instruction": made["instruction"],
                 "shapes": made["shapes"], "name": (row.get("name") or "").strip() or made["name"] or "My hook style"}
        if notes:
            patch["error"] = "Some screenshots were skipped: " + "; ".join(notes[:4])
    except Exception as exc:  # noqa: BLE001 - the reason goes on the style, the page shows it
        log.warning("hook style %s failed: %s", row.get("id"), str(exc)[:200])
        patch = {"status": "error", "error": str(exc)[:300]}
    store.table(TABLE).update({**patch, "updated_at": datetime.now(UTC).isoformat()}).eq("id", row["id"]).execute()
    return patch["status"]


def make_llm(store: Any) -> Any | None:
    try:
        api_status.attach(store, "hook_styles")
        return LLM(ai_config.llm_for(store))
    except Exception as exc:  # noqa: BLE001 - no key is "not read", never a crash
        log.warning("no LLM: %s", exc)
        return None


def run(store: Any, llm: Any = None, *, download: Any = None) -> dict[str, int]:
    counts = {"ready": 0, "error": 0}
    todo = claim(store)
    if not todo:
        return counts
    llm = llm if llm is not None else make_llm(store)
    for row in todo:
        counts[process(store, llm, row, download=download)] += 1
    return counts


def main() -> int:
    counts = run(db.client())
    print(f"Hook styles: {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
