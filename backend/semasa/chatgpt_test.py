"""A manual, live test of Wan's ChatGPT login (Wan, 8 Nov 2026: "test chatgpt read and generate image"): one short answer, one
picture READ and one picture DRAWN, each through the real Codex backend with the saved tokens. Run by chatgpt-test.yml (manual
only, no schedule). It spends one ChatGPT image allowance, writes nothing to the database except a refreshed token and a model the
account allows (exactly what any other call does), and saves the drawn picture to a folder the workflow uploads for Wan.

    python -m semasa.chatgpt_test [output_dir]
"""

from __future__ import annotations

import io
import logging
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from . import chatgpt_login as cl
from . import db

log = logging.getLogger("semasa.chatgpt_test")

TEXT_ON_PICTURE = "WS 4821"


def test_picture() -> bytes:
    """A picture with three things a reader must get right: a red circle, a blue square and the text WS 4821."""
    img = Image.new("RGB", (800, 460), "white")
    d = ImageDraw.Draw(img)
    d.ellipse((60, 80, 260, 280), fill=(220, 30, 30))
    d.rectangle((320, 80, 520, 280), fill=(30, 60, 220))
    try:
        font = ImageFont.load_default(size=70)
    except TypeError:                       # an older Pillow has one fixed size
        font = ImageFont.load_default()
    d.text((60, 320), TEXT_ON_PICTURE, fill="black", font=font)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def run(login: Any, out_dir: Path | None = None) -> dict[str, Any]:
    """{write, read, draw: {ok, detail}, model}. Each step is tried on its own, so one failure does not hide the others."""
    results: dict[str, Any] = {}

    def step(name: str, fn: Any) -> None:
        try:
            ok, detail = fn()
        except cl.ChatGPTError as exc:
            ok, detail = False, f"{type(exc).__name__}: {exc}"
        except Exception as exc:  # noqa: BLE001 - report it, then carry on to the next step
            ok, detail = False, f"{type(exc).__name__}: {str(exc)[:300]}"
        results[name] = {"ok": bool(ok), "detail": detail}
        log.info("%s: %s %s", name, "OK" if ok else "FAILED", detail)

    model = str((login.settings() or {}).get("model") or cl.DEFAULT_MODEL)

    def write() -> tuple[bool, str]:
        out = login.write("Answer in one short sentence.", "What is the chemical symbol for sodium?", model=model, timeout=90)
        return "na" in out.lower(), out.strip()[:200]

    def read() -> tuple[bool, str]:
        out = login.read_image("Describe pictures exactly and briefly.",
                               "List the shapes with their colours and copy any text you can read.",
                               test_picture(), "image/png", model=model, timeout=120)
        low = out.lower()
        return ("red" in low and "blue" in low and "4821" in low), out.strip()[:300]

    def draw() -> tuple[bool, str]:
        data = login.draw("A flat vector icon of a laboratory flask with blue liquid on a plain white background, no text",
                          model=model, timeout=280)
        img = Image.open(io.BytesIO(data))
        img.load()
        if out_dir is not None:
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "chatgpt-drawn.png").write_bytes(data)
        return min(img.size) >= 256, f"{img.format} {img.size[0]}x{img.size[1]}, {len(data)} bytes"

    step("write", write)
    step("read", read)
    step("draw", draw)
    results["model"] = str((login.settings() or {}).get("model") or model)      # the model that finally answered, if it moved
    return results


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    login = cl.Login(db.client())
    if not login.connected():
        print("RESULT not connected: log in on the API page first")
        return 1
    res = run(login, out_dir)
    for name in ("write", "read", "draw"):
        print(f"RESULT {name}={'OK' if res[name]['ok'] else 'FAILED'} · {res[name]['detail']}")
    print(f"RESULT model={res['model']}")
    return 0 if all(res[n]["ok"] for n in ("write", "read", "draw")) else 1


if __name__ == "__main__":
    sys.exit(main())
