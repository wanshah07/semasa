"""Copywriting frameworks for every post, films included (Wan, 10 Nov 2026: "copywriting for all post including motion").

The source is the list Wan sent (a Threads post, "The best copywriting frameworks for marketing"), which gives a sequence of
steps per kind of writing. Each kind of Semasa post takes the sequence that fits it:

  a single card's caption    HOOK - STORY - LESSON - CTA                      (its "Instagram caption")
  a carousel                 HOOK - PROBLEM - SOLUTION - PROOF - CTA           (its "Facebook ad")
  a LinkedIn post            HOOK - STORY - INSIGHT - ACTION                   (its "email newsletter")
  a case study, any stream   PROBLEM - PROCESS - RESULT - PROOF - LESSON       (its "case study")
  a Motion film              HOOK - PROBLEM - SOLUTION - PROOF - CTA, laid over the film's own scenes

A framework orders the writing. It never loosens a rule: PROOF is only what the source in hand says (the instrument, the
notice, the paper), never a testimonial, a result or a figure that was not read; and the CTA or ACTION step is whatever
closing the house rules of that stream allow, never a sales line, a link or a promise.
"""

from __future__ import annotations

from typing import Any

STEPS = {
    "caption": ("HOOK", "STORY", "LESSON", "CTA"),
    "carousel": ("HOOK", "PROBLEM", "SOLUTION", "PROOF", "CTA"),
    "linkedin": ("HOOK", "STORY", "INSIGHT", "ACTION"),
    "case": ("PROBLEM", "PROCESS", "RESULT", "PROOF", "LESSON"),
    "film": ("HOOK", "PROBLEM", "SOLUTION", "PROOF", "CTA"),
}
MEANS = {
    "HOOK": "the opening line that stops the reader (the required hook shape still decides how it is built)",
    "STORY": "what happened, told plainly, in the order it happened",
    "LESSON": "the one thing the reader should now do or know",
    "PROBLEM": "the problem as the reader meets it",
    "SOLUTION": "what the rule or the evidence says to do about it",
    "PROOF": "the source in hand: the instrument, notice or paper, named exactly",
    "INSIGHT": "what a practitioner takes from it that is not obvious from the headline",
    "ACTION": "what the reader can check or do next in their own work",
    "PROCESS": "what was done, step by step, and by whom",
    "RESULT": "what came of it, in the source's own figures",
    "CTA": "the closing the house rules allow for this stream",
}
GUARD = ("The framework only ORDERS the writing; every rule above outranks it. PROOF is only what the source says: never a "
         "testimonial, a result or a figure you were not given. The closing step is the closing the rules above allow, "
         "never a sales line, a link or a promise. Do not print the step names.")
FILM = ("Lay it over the film's own scenes: scene 1 is the HOOK; scene 2 carries the PROBLEM inside its story and fact; "
        "scene 3 carries the SOLUTION and its PROOF as what was missed out; the last scene is the CTA.")


def kind_of(idea: dict[str, Any] | None, stream: str, fmt: str = "post") -> str:
    """Which framework a post takes: a case study wherever it appears, then the carousel, then the stream's own."""
    idea = idea or {}
    brief = idea.get("brief") if isinstance(idea.get("brief"), dict) else {}
    if idea.get("domain") == "kajian_kes" or idea.get("angle") == "E" or brief.get("pillar") == "kajian_kes":
        return "case"
    if fmt == "carousel":
        return "carousel"
    return "linkedin" if stream == "linkedin" else "caption"


def block(kind: str) -> str:
    """The framework block for a writer's prompt; "" for a kind nobody knows."""
    steps = STEPS.get(kind)
    if not steps:
        return ""
    lines = "\n".join(f"{i}. {s}: {MEANS[s]}" for i, s in enumerate(steps, 1))
    return (f"\n\nCOPYWRITING FRAMEWORK ({' - '.join(steps)}). Build the writing in this order:\n{lines}\n"
            + (FILM + "\n" if kind == "film" else "") + GUARD)
