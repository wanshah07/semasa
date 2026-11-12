"""The 25 hook shapes, and the rule that every post's first line is built on one of them (Wan, 6 Nov 2026: "make sure 25 hook tu
wajib dalam ayat").

Before this the bank was an optional scaffold: the writer saw one family only when an idea happened to name `hook_family`, and
nothing in the page sets that, so no post ever used a shape. Now the writer is ALWAYS given the shapes its stream may use (all
25 on LinkedIn, the 20 that are not first-person confession on ws.regulab), must lead the caption with one of them, and must say
which in `"hook_shape"` (1 to 25, series order). An answer without a valid number is asked for again once; a second miss fails
the idea with a plain sentence, so a post never leaves here without one.

What stays true: the shapes are scaffolds, every rule above them outranks them, and a blank is never filled with a figure, a
duration, an approval or a cure the SOURCE does not give. When no shape can be filled without inventing a fact, the writer takes a
RELATABLE or CURIOSITY shape, which assert nothing and can always be filled. `.claude/skills/hook-bank/SKILL.md` is the reference
copy of the same list; if one changes the other changes.

The shapes are Malaysian Malay. A Malay post uses a shape as written (the casual spellings are the voice). An English post (the
LinkedIn stream) translates the shape faithfully, keeping its structure and its blanks' roles, never its words.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .log import get_logger

log = get_logger("semasa.hook_bank")

FAMILIES = {
    "curiosity": ["Takde sapa cakap pasal ___ tapi ni sebab aku ___",
                  "Aku ignore ___ berbulan-bulan. Lepas tu aku cuba, dan ___",
                  "Soalan yang takde sapa tanya pasal ___: ___. Jawapannya, ___",
                  "Ni apa sebenarnya jadi bila kau ___",
                  "Aku harap ada orang bagitau aku ___ sebelum aku mula ___"],
    "transform": ["Enam bulan lepas aku tak boleh ___. Hari ni aku ___",
                  "Aku dulu fikir ___ mustahil, sampai lah ___",
                  "Hari aku berhenti buat ___, semua berubah",
                  "Dulu ___ vs sekarang ___: ni apa yang berubah",
                  "Aku dari ___ ke ___ sebab buat satu benda je"],
    "vulnerable": ["Aku takut nak kongsi ___ tapi ni kenapa penting",
                   "Kegagalan terbesar aku dengan ___ ajar aku ___",
                   "Aku hampir give up bila ___, tapi lepas tu ___",
                   "Takde sapa nampak part mana aku ___",
                   "Aku struggle ___ bulan dengan ___ sebelum aku jumpa jalan ___"],
    "bold": ["Semua orang cakap ___, tapi realitinya ___",
             "Berhenti buat ___ kalau kau nak ___",
             "___ dah mati. Ni apa yang sebenarnya berkesan sekarang",
             "Sebab sebenar kenapa kau masih tak ___ lagi",
             "Berani aku cakap: ___ tak penting mana pun berbanding ___"],
    "relatable": ["POV: kau ___ tapi ___",
                  "Perasaan tu bila kau dah ___ tapi masih ___",
                  "Aku: esok lah aku ___. Lepas tu aku: ___",
                  "Cuba nak ___ sambil ___ memang macam ni",
                  "Orang lain: ___. Aku: masih pikir ___"],
}
# Order matters: a brand account opens with recognition and only earns the assertive families later.
ORDER = ("relatable", "curiosity", "bold", "transform")
# Series order, which is also the number the writer reports: CURIOSITY 1-5, TRANSFORM 6-10, VULNERABLE 11-15, BOLD 16-20,
# RELATABLE 21-25
SERIES = ("curiosity", "transform", "vulnerable", "bold", "relatable")
# Wan's own voice is first person about a named human, so it never runs on the company account.
OFF_BRAND = {"vulnerable"}


@dataclass(frozen=True)
class Bank:
    """The shapes a writer must lead with, and the guidance for using them. The default is the built-in 25; a style Wan made from
    screenshots (hook_styles.py) is a Bank with its own shapes and its own instruction, which REPLACES the default guidance."""
    id: str = "builtin"
    name: str = "25 built-in hook shapes"
    instruction: str = ""
    shapes: tuple[tuple[int, str, str], ...] = ()


def numbered() -> list[tuple[int, str, str]]:
    """[(number, family, shape)] for all 25, numbered 1 to 25 in series order."""
    out, n = [], 0
    for family in SERIES:
        for shape in FAMILIES[family]:
            n += 1
            out.append((n, family, shape))
    return out


def allowed(stream: str, family: str | None = None, bank: Bank | None = None) -> list[tuple[int, str, str]]:
    """The shapes a stream may lead with: every one on LinkedIn, all but the first-person confessions on ws.regulab; only
    `family` when an idea names one (a family the stream may not use falls back to everything the stream may use)."""
    pool = list(bank.shapes) if bank and bank.shapes else numbered()
    rows = [r for r in pool if stream == "linkedin" or r[1] not in OFF_BRAND]
    only = [r for r in rows if family and r[1] == str(family).strip().lower()]
    return only or rows


DEFAULT_GUIDANCE = ("Write a Malay post's hook as the shape is written; write an English post's hook as a faithful translation "
                    "that keeps the shape's structure and what each blank is for. If no shape can be filled without inventing a "
                    "fact, take a RELATABLE or CURIOSITY shape: they assert nothing and always fit. "
                    "A strong hook leans on the S.T.O.P. formula (Wan, 12 Nov 2026: saved and applied): S - Shock (a bold claim "
                    "or reality check that surprises), T - Target (name the reader: founders, mak-mak, pekerja 9 to 5), O - Open "
                    "loop (hold a little back so the reader wants the rest), P - Proof (result first, then how). Fold whichever "
                    "of these fit into the shape's blanks; you never need all four, and never a fact the SOURCE does not give.")


def block(family: str | None, stream: str, bank: Bank | None = None, hint: str = "") -> str:
    """The required-hook block appended to the writer's system prompt, after the house style, so it can never lift a rule. A style
    made from screenshots replaces the default guidance with its own instruction; the requirement and the guardrails stay."""
    rows = allowed(stream, family, bank)
    lines, last = [], ""
    for n, fam, shape in rows:
        if fam != last:
            lines.append(f"{fam.upper()}:")
            last = fam
        lines.append(f"  {n}. {shape}")
    custom = bool(bank and bank.instruction.strip())
    guidance = (f"HOOK STYLE \"{bank.name}\" (Wan's own, it replaces the default guidance): {bank.instruction.strip()} "
                "Write the hook in the post's own language: a shape in another language is translated faithfully, keeping its "
                "structure and what each blank is for.") if custom else DEFAULT_GUIDANCE
    return ("\n\nHOOK SHAPE (REQUIRED, and the rules above outrank it). The first line of every caption MUST be built on exactly "
            "one of the numbered shapes below, with the blanks filled from the SOURCE, and \"hook_shape\" in your answer MUST be "
            f"that shape's number. A post without one is rejected. {guidance} "
            "Choose the shape that fits the story best. Never fill a blank with a figure, a duration, an approval or a cure the "
            "SOURCE does not give, never keep the underscores in the finished hook, and never copy an example sentence. "
            "If no shape can be filled without inventing a fact, take the shape that asserts the least. "
            "The hook is the caption's own first line, not a title above it.\n"
            + (f"{hint}\n" if hint else "") + "Shapes you may use:\n" + "\n".join(lines))


def film_block(stream: str, bank: Bank | None = None, hint: str = "") -> str:
    """The required-hook block for a Motion film's script (Wan, 7 Nov 2026: "do 1,2,3", the third being that the film's hook scene
    also uses the 25 shapes instead of Tahukah anda / Amaran / Berita terkini). Same shapes, same stream rule, same guardrails as
    block(); the hook is the first scene's heading, which is also the first words said, and "hook_shape" / "hook" sit beside
    "title" in the script's JSON."""
    rows = allowed(stream, None, bank)
    lines, last = [], ""
    for n, fam, shape in rows:
        if fam != last:
            lines.append(f"{fam.upper()}:")
            last = fam
        lines.append(f"  {n}. {shape}")
    custom = bool(bank and bank.instruction.strip())
    guidance = (f"HOOK STYLE \"{bank.name}\" (Wan's own, it replaces the default guidance): {bank.instruction.strip()} "
                "Write the hook in the film's own language: a shape in another language is translated faithfully, keeping its "
                "structure and what each blank is for.") if custom else DEFAULT_GUIDANCE
    return ("THE HOOK (REQUIRED, and every rule above outranks it). Scene 1's heading is a hook built on exactly one of the "
            "numbered shapes below, the blanks filled from the BRIEF; its words are the first words read and, when there is a "
            "narrator, the first words said. Put that shape's number in \"hook_shape\" and the finished hook line in \"hook\", "
            "equal to scene 1's heading. A script without one is rejected. The hook may run to 14 words, "
            f"the one exception to the short heading limit. {guidance} "
            "Choose the shape that fits the story best. "
            "Never fill a blank with a figure, a duration, an approval or a cure the BRIEF does not give, never keep the "
            "underscores, never copy an example sentence, and never open with "
            "'Tahukah anda', 'Amaran' or 'Berita terkini' in place of a shape. If no shape can be filled without inventing a "
            "fact, take the shape that asserts the least.\n"
            + (f"{hint}\n" if hint else "") + "Shapes you may use:\n" + "\n".join(lines))


def pick_for_idea(store: Any, idea_id: Any) -> Bank | None:
    """The hook style for a film made from an idea: the idea's own choice (brief.hook_style), else Wan's default
    (settings.hook_style), else None, the built-in 25. Never raises: a film is still written when nothing can be read."""
    idea: dict[str, Any] | None = None
    if idea_id:
        try:
            rows = store.table("semasa_ideas").select("brief").eq("id", idea_id).execute().data or []
            idea = rows[0] if rows else None
        except Exception as exc:  # noqa: BLE001
            log.info("hook style: idea %s not read (%s)", idea_id, str(exc)[:100])
    settings: dict[str, Any] = {}
    try:
        rows = store.table("semasa_settings").select("value").eq("key", "hook_style").execute().data or []
        settings = {"hook_style": (rows[0].get("value") or {}) if rows else {}}
    except Exception as exc:  # noqa: BLE001
        log.info("hook style: default not read (%s)", str(exc)[:100])
    return pick(store, idea, settings)


def _shape_stem(shape: str) -> list[str]:
    """The shape's literal opening words before its first blank, lowercased. A finished hook must open on these words, so a
    writer cannot declare one number while writing another shape. A shape that starts with a blank ("___ dah mati") has no
    stem and is left unchecked."""
    head = shape.split("___", 1)[0].strip()
    return [w.lower() for w in re.findall(r"[A-Za-z0-9]+", head)][:4]


def _declared_shape(n: int, stream: str, family: str | None, bank: Bank | None) -> tuple[int, str, str] | None:
    for row in allowed(stream, family, bank):
        if row[0] == n:
            return row
    return None


def declared(out: Any, stream: str, family: str | None = None, bank: Bank | None = None) -> int | None:
    """The shape number the writer declared, when it is one this stream may use, the hook has no blanks left, and the hook
    actually opens on that shape's own words; else None."""
    if not isinstance(out, dict):
        return None
    try:
        n = int(out.get("hook_shape"))
    except (TypeError, ValueError):
        return None
    row = _declared_shape(n, stream, family, bank)
    if row is None:
        return None
    hook = str(out.get("hook") or "")
    if not hook.strip() or "___" in hook or re.search(r"_{2,}", hook):
        return None
    # The hook must open on this shape's own leading words. On LinkedIn the hook is a faithful TRANSLATION of the shape, so a
    # Malay stem cannot fingerprint it and the check is skipped there. A custom bank's shapes are Wan's own wording and the
    # writer may paraphrase them, so the stem check applies only to the built-in 25 (bank is None). Only the FIRST TWO words of
    # the shape are the fingerprint: they are the part a writer cannot vary ("Sebab sebenar", "Semua orang"), while later words
    # shift naturally (kau -> korang/anda, aku -> saya). A hook under four words is too short to judge. (Caught 12 Nov 2026: a
    # dry-run declared shape 3 while writing a "Semua orang cakap ... tapi realitinya ..." hook, and a shape-19 hook that said
    # "korang" instead of the shape's "kau".)
    if stream != "linkedin" and bank is None:
        hook_words = [w.lower() for w in re.findall(r"[A-Za-z0-9]+", hook)]
        stem = _shape_stem(row[2])
        if stem and len(stem) >= 2 and len(hook_words) >= 4 and hook_words[:2] != stem[:2]:
            return None
    return n


def asks_again(stream: str, family: str | None = None, bank: Bank | None = None) -> str:
    """What the second ask says when the first answer did not name a usable shape."""
    ok = ", ".join(str(r[0]) for r in allowed(stream, family, bank))
    return ("\n\nYOUR LAST ANSWER DID NOT USE A HOOK SHAPE. Answer again in the same JSON, with \"hook_shape\" set to the number "
            f"of ONE shape from the list ({ok}), the hook built on it with every blank filled and no underscores left, and the "
            "caption's first line equal to that hook.")


def film_asks_again(stream: str, bank: Bank | None = None) -> str:
    """The second ask for a film script whose first answer named no usable shape."""
    ok = ", ".join(str(r[0]) for r in allowed(stream, None, bank))
    return ("\n\nYOUR LAST SCRIPT DID NOT USE A HOOK SHAPE. Answer again in the same JSON, with \"hook_shape\" set to the number "
            f"of ONE shape from the list ({ok}), \"hook\" the finished hook line with every blank filled and no underscores "
            "left, and scene 1's heading equal to that hook.")


def lead_matches(hook: str, text: str) -> bool:
    """Whether the caption actually opens with the hook it reports (case, spacing and end punctuation ignored). A diagnostic kept
    on the idea, never a reason to fail one: a writer that tidies a comma still used the shape."""
    def norm(s: str) -> str:
        return re.sub(r"[\W_]+", " ", s.lower()).strip()
    h, t = norm(hook), norm(text)
    return bool(h) and t.startswith(h[: max(12, min(len(h), 60))])


def cover(items: list[dict[str, Any]], hook: str, words: int = 12) -> tuple[list[dict[str, Any]], str]:
    """The cover slide (or the poster) wears the hook (Wan, 7 Nov 2026: "make sure all apply the 25 hooks"). The first item's
    title is the hook the caption opens with: kept when the writer already did that, set to the hook when it did not and the hook
    is no longer than `words`, and left alone ("too_long") when the hook cannot fit a headline.
    Returns (items, "kept" | "set" | "too_long" | "")."""
    clean = " ".join(str(hook or "").split())
    if not items or not clean or "_" in clean:
        return items, ""
    title = str(items[0].get("title") or "")
    if lead_matches(clean, title.replace("*", "")) or lead_matches(title.replace("*", ""), clean):
        return items, "kept"
    if len(clean.split()) > words:
        return items, "too_long"
    return [{**items[0], "title": clean}, *items[1:]], "set"


# ---- a style made from screenshots (hook_styles.py) ------------------------------------------------------------------------

STYLES = "semasa_hook_styles"
FAMILY_NAMES = set(SERIES) | {"other"}


def bank_from_row(row: dict[str, Any] | None) -> Bank | None:
    """The Bank a saved style stands for, or None when the style is not ready or carries no usable shape."""
    if not isinstance(row, dict) or row.get("status") != "ready":
        return None
    shapes = []
    for item in row.get("shapes") or []:
        text = str((item.get("text") if isinstance(item, dict) else item) or "").strip()
        fam = str((item.get("family") if isinstance(item, dict) else "") or "other").strip().lower()
        if "___" in text:
            shapes.append((len(shapes) + 1, fam if fam in FAMILY_NAMES else "other", text))
    if not shapes:
        return None
    return Bank(id=str(row.get("id") or ""), name=str(row.get("name") or "My style")[:60],
                instruction=" ".join(str(row.get("instruction") or "").split())[:2000], shapes=tuple(shapes))


def pick(store: Any, idea: dict[str, Any] | None, settings: dict[str, Any] | None) -> Bank | None:
    """The style to write with: the one the idea chose (brief.hook_style), else the one Wan made the default
    (settings.hook_style), else None, which is the built-in 25. A style that is gone, not ready or unreadable is None too, never
    an error: a post is still written, with the built-in shapes."""
    brief = (idea or {}).get("brief") if isinstance((idea or {}).get("brief"), dict) else {}
    chosen = str(brief.get("hook_style") or "").strip()
    if not chosen:
        chosen = str(((settings or {}).get("hook_style") or {}).get("id") or "").strip()
    if not chosen or chosen == "builtin":
        return None
    try:
        rows = store.table(STYLES).select("*").eq("id", chosen).execute().data or []
    except Exception as exc:  # noqa: BLE001 - 060 not applied yet, or the table cannot be read
        log.info("hook style %s not read (%s): the built-in shapes are used", chosen, str(exc)[:100])
        return None
    bank = bank_from_row(rows[0] if rows else None)
    if bank is None:
        log.info("hook style %s is gone or not ready: the built-in shapes are used", chosen)
    return bank
