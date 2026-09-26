"""ws.regulab Studio's card designs (Grid, Info ERA, Photo), drawn by Studio's own JavaScript in headless Chrome.

Wan, 26 Sep 2026: "for post and idea carousel, copy the code design that already in ws.regulab studio, so we can
choose the design". The designs are canvas code, so they are not rewritten in Pillow: the page's module
web/src/lib/cards/studio.js (Studio's renderer, copied verbatim) is loaded into a headless Chrome and asked to draw.
The page previews with the very same file, so the look Wan picks is the look the post gets.

Nothing is fetched from the internet: the page, the module, the fonts and the logo are served from this checkout
through a routed origin, and the background picture goes in as a data URL. A slide that Studio says is fuller than
the card FAILS the render with the slide named, Semasa's rule ("never cut"), never ships clipped.
"""

from __future__ import annotations

import base64
import mimetypes
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from .log import get_logger
from .slides import SlideError

log = get_logger("semasa.studio_cards")

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "web" / "src" / "lib" / "cards" / "studio.js"
ASSETS = ROOT / "web" / "public" / "cards"
ORIGIN = "https://cards.semasa.invalid"
LOOKS = ("grid", "era", "photo")

PAGE = """<!doctype html><html><head><meta charset="utf-8"></head><body>
<script type="module">import * as C from "/studio.js"; window.__cards = C; window.__ready = true;</script>
</body></html>"""


def is_studio_look(look: Any) -> bool:
    return str(look or "") in LOOKS


def _serve(route: Any) -> None:
    """The routed origin: the page, the module and web/public/cards/*. Anything else is refused."""
    path = route.request.url[len(ORIGIN):].split("?", 1)[0]
    if path in ("/", "/index.html"):
        return route.fulfill(status=200, content_type="text/html", body=PAGE)
    if path == "/studio.js":
        return route.fulfill(status=200, content_type="application/javascript", body=MODULE.read_text("utf-8"))
    if path.startswith("/cards/"):
        target = (ASSETS / path[len("/cards/"):]).resolve()
        if ASSETS.resolve() in target.parents and target.is_file():
            kind = "font/woff2" if target.suffix == ".woff2" else mimetypes.guess_type(target.name)[0]
            kind = kind or "application/octet-stream"
            return route.fulfill(status=200, content_type=kind, body=target.read_bytes())
    return route.fulfill(status=404, body="not here")


def _launch(p: Any) -> Any:
    """The runner's own Google Chrome first (ubuntu-latest carries one, so nothing is downloaded), then Playwright's
    Chromium, then install that Chromium and try once more. Says which one drew."""
    errors = []
    tries: list[tuple[str, dict[str, Any]]] = [("Google Chrome", {"channel": "chrome"}), ("Playwright Chromium", {})]
    if os.environ.get("SEMASA_CHROME"):
        # a named browser binary wins (a local run, or a runner image with Chrome elsewhere)
        tries.insert(0, ("SEMASA_CHROME", {"executable_path": os.environ["SEMASA_CHROME"]}))
    for how, kwargs in tries:
        try:
            browser = p.chromium.launch(**kwargs)
            log.info("studio cards: drawing in %s", how)
            return browser
        except Exception as exc:  # noqa: BLE001 - try the next one
            errors.append(f"{how}: {str(exc).splitlines()[0][:160]}")
    log.warning("studio cards: no browser (%s); installing Playwright Chromium", "; ".join(errors))
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=False, timeout=600)
    try:
        return p.chromium.launch()
    except Exception as exc:  # noqa: BLE001
        raise SlideError("the Studio designs need Chrome on the runner and none could start: "
                         + "; ".join(errors + [str(exc).splitlines()[0][:160]])) from exc


def render(items: list[dict[str, Any]], *, look: str, stream: str, eyebrow: str = "", source: str = "",
           ground: bytes | None = None, ground_mime: str = "image/jpeg",
           size: tuple[int, int] | None = None) -> list[bytes]:
    """JPEG bytes per slide, drawn in the chosen Studio look. Raises SlideError with a message for the page."""
    if look not in LOOKS:
        raise SlideError(f"unknown look {look!r}")
    if look == "photo" and not ground:
        raise SlideError("the Photo look is drawn on a picture and there is none: choose a background "
                         "(the post's picture or an upload), or pick Grid or Info ERA")
    if not MODULE.is_file() or not (ASSETS / "fonts.css").is_file():
        raise SlideError("the Studio card files are missing from this checkout (web/src/lib/cards/studio.js, "
                         "web/public/cards/)")
    from playwright.sync_api import sync_playwright

    opts: dict[str, Any] = {"look": look, "stream": stream, "eyebrow": eyebrow, "citation": source}
    if ground:
        opts["bg"] = f"data:{ground_mime};base64," + base64.b64encode(ground).decode("ascii")
    if size:
        opts["size"] = [int(size[0]), int(size[1])]
    with sync_playwright() as p:
        browser = _launch(p)
        try:
            page = browser.new_page()
            page.route(f"{ORIGIN}/**", _serve)
            page.goto(f"{ORIGIN}/index.html")
            page.wait_for_function("window.__ready === true", timeout=30_000)
            fonts = page.evaluate("""async (base) => { window.__cards.setLogo(base + "logo.png");
                                     return await window.__cards.ensureFonts(base); }""", f"{ORIGIN}/cards/")
            if fonts.get("missing"):
                raise SlideError("the Studio fonts did not load: " + ", ".join(fonts["missing"]))
            out = page.evaluate("async ([s, o]) => await window.__cards.renderSlides(s, o)", [items, opts])
        finally:
            browser.close()
    pics = []
    for i, r in enumerate(out, 1):
        if r.get("warn"):
            raise SlideError(f"slide {i} ({r.get('template')}): " + " ".join(r["warn"])
                             + " Shorten it, split it into two slides, or pick another look.")
        url = str(r.get("url") or "")
        if not url.startswith("data:image/jpeg;base64,"):
            raise SlideError(f"slide {i}: the browser did not hand back a JPEG")
        pics.append(base64.b64decode(url.split(",", 1)[1]))
    if len(pics) != len(items):
        raise SlideError(f"{len(items)} slides written but {len(pics)} drawn")
    return pics
