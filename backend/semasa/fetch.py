"""HTTP and browser fetching with a real browser identity.

Public news sites and Google's RSS endpoints answer a plain `requests` call that
carries a Chrome User-Agent and a Malaysian Accept-Language. Sites that only render
their front page with JavaScript (Astro Awani, Sinar Harian, Bernama) go through
Playwright, which is started once per run and shared.

What this does NOT do: solve CAPTCHAs, rotate proxies, or impersonate a logged-in
user. Every source here is public and reads fine with a browser identity.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager

import requests

from .log import get_logger

log = get_logger("semasa.fetch")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ms-MY,ms;q=0.9,en-MY;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
}


def get(url: str, *, timeout: int = 25, retries: int = 2) -> requests.Response:
    """GET with a browser identity; retries on connection errors and 5xx, never on 4xx."""
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
            if r.status_code >= 500:
                raise requests.HTTPError(f"{r.status_code} from {url}", response=r)
            r.raise_for_status()
            return r
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else 0
            if 400 <= status < 500:
                raise
            last = exc
        except requests.RequestException as exc:
            last = exc
        if attempt < retries:
            time.sleep(1.5 * (attempt + 1))
    assert last is not None
    raise last


class Browser:
    """A single Chromium for the whole run. `page_html()` returns rendered HTML."""

    def __init__(self) -> None:
        self._pw = None
        self._browser = None
        self._context = None

    def start(self) -> None:
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        self._context = self._browser.new_context(
            user_agent=UA,
            locale="ms-MY",
            timezone_id="Asia/Kuala_Lumpur",
            viewport={"width": 1366, "height": 900},
            extra_http_headers={"Accept-Language": HEADERS["Accept-Language"]},
        )
        self._context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
        # pictures, fonts and media are dead weight for a headline pass
        self._context.route(
            "**/*",
            lambda route: route.abort()
            if route.request.resource_type in ("image", "media", "font", "stylesheet")
            else route.continue_(),
        )

    def page_html(self, url: str, *, timeout_ms: int = 45_000, settle_ms: int = 1500) -> str:
        assert self._context is not None, "Browser.start() first"
        page = self._context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(settle_ms)
            return page.content()
        finally:
            page.close()

    def stop(self) -> None:
        for closer in (self._context, self._browser, self._pw):
            try:
                if closer is not None:
                    (closer.close if hasattr(closer, "close") else closer.stop)()
            except Exception:  # noqa: BLE001 - shutdown must never mask the run's result
                pass


@contextmanager
def browser() -> Iterator[Browser | None]:
    b = Browser()
    try:
        b.start()
    except Exception as exc:  # noqa: BLE001
        log.warning("Playwright unavailable (%s); HTML-only sources will be skipped", exc)
        yield None
        return
    try:
        yield b
    finally:
        b.stop()
