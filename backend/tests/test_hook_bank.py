"""The hook bank reaches the writer, and never lifts a rule.

Each test names the behaviour, not the implementation: a family reaches the writer, the
company account never gets the first-person family, an unknown family adds nothing, and the
rules that already existed still outrank the shapes.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from semasa import ideas  # noqa: E402


def _request(stream="regulab", family=None, writer=None):
    idea = {"id": "i", "stream": stream, "source_title": "T", "hook_family": family}
    source = {"ok": False, "why": "no link", "image": None}
    return ideas.build_request(idea, source, {}, writer=writer)


def test_all_twenty_five_shapes_are_kept():
    assert sum(len(v) for v in ideas.HOOK_FAMILIES.values()) == 25
    assert set(ideas.HOOK_FAMILIES) == {"curiosity", "transform", "vulnerable", "bold", "relatable"}


def test_a_family_reaches_the_writer_with_its_shapes():
    system, _ = _request(family="bold")
    assert "HOOK SHAPE" in system
    assert "Semua org ckp ___ tapi realitinya ___" in system
    # the shapes are scaffolds, so the writer is told to drop the underscores
    assert "never keep the underscores" in system


def test_the_company_account_never_gets_the_first_person_family():
    system, _ = _request(family="vulnerable")
    assert "HOOK SHAPE" not in system
    assert "Takde sapa nampak part mana aku" not in system


def test_the_first_person_family_does_reach_the_linkedin_stream():
    system, _ = _request(stream="linkedin", family="vulnerable")
    assert "Takde sapa nampak part mana aku ___" in system


def test_no_family_and_an_unknown_family_add_nothing():
    for family in (None, "", "zzz"):
        system, _ = _request(family=family)
        assert "HOOK SHAPE" not in system


def test_the_shapes_never_lift_the_standing_rules():
    system, _ = _request(family="transform")
    # the rule that forbids an invented figure must still be present, and must be stated
    # before the block that offers the shapes
    assert system.index("no fee, duration, circular") < system.index("HOOK SHAPE")
    assert "Never fill a blank with a figure" in system


def test_house_style_still_cannot_lift_a_rule():
    writer = {"regulab": {"voice": "tenang", "never": ["halal-friendly"]}}
    system, _ = _request(family="relatable", writer=writer)
    assert "HOUSE STYLE" in system
    assert system.index("HOUSE STYLE") < system.index("HOOK SHAPE")
    assert "It adds to the rules above and never lifts one" in system
