"""Composio For You as a place to READ from: run a small Python cell in Composio's workbench, get JSON back.

The three source readers (community.py, folders.py, myra.py) all work the same way: the work that needs Wan's connections
(Reddit, YouTube, OneDrive, Google Sheets) happens INSIDE the workbench with `run_composio_tool`, where the connection
already lives, and only a compact result comes back. Two facts about that road decide the shape of every cell:

  * the workbench cuts what a cell prints at about 40,000 characters, so a cell trims its own answer (the wrapper below
    refuses to print more than 36,000 and says so, rather than let the JSON be cut in half), and
  * a cell may run 180 seconds at most, so a cell that walks many files keeps to a time budget and returns what it
    finished, and the caller asks again for the rest.

Nothing here writes to any Wan account: the cells only read. (Posting is senders.LinkedInMCP's job.)
"""

from __future__ import annotations

import base64
import json
import textwrap
from typing import Any

from .senders import _MARK, ComposioMCP, SendError

MAX_ANSWER = 36_000

_WRAP = '''
import json, base64, time
_T0 = time.time()
P = json.loads(base64.b64decode("{params}").decode())

def call(slug, args, acct=None):
    """One Composio app tool. (data, error): error is "" when it worked. No retries: a quota answer is an answer."""
    res, err = run_composio_tool(slug, args, account=acct, print_schema_for_tool=False, retry_params={{"max_retries": 0}})
    return (res or {{}}), (err or "")

def left():
    """Seconds of this cell's budget still unspent."""
    return {budget} - (time.time() - _T0)

def _main():
    OUT = {{}}
{body}
    return OUT

try:
    _r = {{"ok": True, "out": _main()}}
except Exception as _e:
    _r = {{"ok": False, "message": f"{{type(_e).__name__}}: {{_e}}"}}
_s = json.dumps(_r, ensure_ascii=False, default=str)
if len(_s) > {limit}:
    _s = json.dumps({{"ok": False, "message": "the answer was " + str(len(_s)) + " characters, over the workbench limit"}})
print("{mark}" + _s)
'''


def render(body: str, params: dict[str, Any] | None = None, budget: int = 140) -> str:
    """The exact Python the workbench runs. Split out so a test can run it against a stub `run_composio_tool`."""
    b64 = base64.b64encode(json.dumps(params or {}, ensure_ascii=False).encode()).decode()
    return _WRAP.format(params=b64, budget=budget, limit=MAX_ANSWER, mark=_MARK,
                        body=textwrap.indent(textwrap.dedent(body).strip("\n"), "    "))


class ForYou(ComposioMCP):
    """A For You workbench you can ask questions of."""

    def cell(self, body: str, params: dict[str, Any] | None = None, thought: str = "Semasa: read a source",
             budget: int = 140) -> Any:
        """Run `body` (Python that fills OUT, a dict) in the workbench; return OUT. `call(slug, args, acct)` and
        `left()` are there for the body, and its parameters arrive as `P`."""
        code = render(body, params, budget)
        try:
            r = self._cell(code, thought)
        except ValueError as exc:                # the marker line was cut: the answer was bigger than the workbench prints
            raise SendError("transient", f"the workbench's answer was cut short: {exc}") from exc
        if not r.get("ok"):
            raise SendError("transient", f"workbench cell failed: {r.get('message')}")
        return r.get("out")
