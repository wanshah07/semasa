"""rules/cases.json is shared with web/src/lib/compliance.test.mjs: both scanners must agree."""

import json
from pathlib import Path

import pytest

from semasa import compliance

CASES = json.loads((Path(compliance.RULES_PATH).parent / "cases.json").read_text(encoding="utf-8"))


def check(case, flags):
    e = case["expect"]
    hard = [f"{f['where']}: {f['msg']}" for f in flags if f["hard"]]
    soft = [f"{f['where']}: {f['msg']}" for f in flags if not f["hard"]]
    if "hard" in e:
        assert len(hard) == e["hard"], hard
    if "hard_min" in e:
        assert len(hard) >= e["hard_min"], hard
    for s in e.get("contains", []):
        assert any(s in h for h in hard), (s, hard)
    for s in e.get("not_contains", []):
        assert not any(s in h for h in hard), (s, hard)
    for s in e.get("soft_contains", []):
        assert any(s in x for x in soft), (s, soft)
    for s in e.get("soft_not_contains", []):
        assert not any(s in x for x in soft), (s, soft)


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_case(case):
    check(case, compliance.scan(case["post"], schedule=case.get("schedule")))


def test_every_rule_compiles_the_same_way():
    for r in compliance.RULES["hard"] + compliance.RULES["cta"] + compliance.RULES["soft"]:
        assert r["flags"] in ("", "i")


def test_python_and_page_scanners_agree_exactly():
    """The page decides whether Approve is offered; the publisher decides whether to send.
    If they disagree, a post can be approved that will never go, or the reverse."""
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    web = Path(compliance.RULES_PATH).parents[1] / "web"
    out = subprocess.run([node, "compliance.test.mjs", "--dump"], cwd=web, capture_output=True, text=True, check=True)
    js = json.loads(out.stdout)
    py = [compliance.scan(c["post"], schedule=c.get("schedule")) for c in CASES]
    for case, a, b in zip(CASES, py, js, strict=True):
        assert a == b, case["name"]
