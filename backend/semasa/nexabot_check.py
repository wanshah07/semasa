"""Check a saved nexabot.id login BEFORE it is uploaded as the secret NEXABOT_STORAGE_STATE_B64 (ops/NEXABOT-LOGIN.md).

Run it on your own computer, from the backend folder:

    python -m semasa.nexabot_check storage_state.json
    python -m semasa.nexabot_check storage_state.json --b64 secret.txt     # also writes the base64 to paste into GitHub

It opens https://nexabot.id/video-generator with that login and prints ONE verdict line: logged in, login wall, or blocked.
It prints cookie NAMES and counts only: never a cookie value, never a token. It opens the page and nothing else: it does not
press anything and spends no credits.

Why the names are matched, not listed: nobody here has seen a logged-in nexabot.id cookie yet, so no name is hardcoded. Any
cookie on nexabot.id whose name contains "session", "token" or "auth" is treated as the login.
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
from typing import Any
from urllib.parse import urlsplit

GITHUB_SECRET_LIMIT = 48_000          # GitHub refuses an Actions secret over 48 KB
ORIGIN = "https://nexabot.id"
HOST = "nexabot.id"
STUDIO_PATH = "/video-generator"
STUDIO_URL = ORIGIN + STUDIO_PATH
LOGIN_NAME = re.compile(r"session|token|auth", re.IGNORECASE)
# localStorage is kept only when the whole file stays comfortably under the limit (cookies alone are normally a few hundred bytes)
STORAGE_BUDGET = 40_000
WALL_PATHS = ("/login", "/signin", "/sign-in", "/auth/", "/api/auth/signin", "/register")
BLOCK_STATUSES = (401, 403, 429, 451, 503)
BLOCK_TITLES = re.compile(r"just a moment|attention required|access denied|are you a robot|captcha|blocked", re.IGNORECASE)


def _encoded_size(state: dict[str, Any]) -> int:
    return len(base64.b64encode(json.dumps(state, separators=(",", ":")).encode()))


def on_site(domain: str) -> bool:
    """True for nexabot.id and any subdomain of it, with or without the cookie's leading dot."""
    d = str(domain or "").lstrip(".").lower()
    return d == HOST or d.endswith("." + HOST)


def login_cookie_names(state: dict[str, Any]) -> list[str]:
    """NAMES of the nexabot.id cookies that look like the login (contain session, token or auth). Never a value."""
    names = [str(c.get("name") or "") for c in state.get("cookies") or [] if on_site(c.get("domain"))]
    return sorted({n for n in names if n and LOGIN_NAME.search(n)})


def shrink(state: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """The smallest login the probe can use: (state, what_was_decided).
    Keeps the nexabot.id cookies. Keeps nexabot.id's localStorage only if the whole file then stays under STORAGE_BUDGET
    characters of base64 (the app may hold its session there). If even the cookies are over GitHub's limit, keeps only the
    login-looking ones."""
    cookies = [c for c in state.get("cookies") or [] if on_site(c.get("domain"))]
    origins = [o for o in state.get("origins") or [] if str(o.get("origin") or "").rstrip("/") == ORIGIN]
    with_storage = {"cookies": cookies, "origins": origins}
    if origins and _encoded_size(with_storage) <= STORAGE_BUDGET:
        return with_storage, "kept the nexabot.id cookies and its saved page data (small enough)"
    slim = {"cookies": cookies, "origins": []}
    why = "dropped the saved page data (too large)" if origins else "no saved page data was in the file"
    if _encoded_size(slim) <= GITHUB_SECRET_LIMIT:
        return slim, f"kept the nexabot.id cookies, {why}"
    keep = set(login_cookie_names(state))
    minimal = {"cookies": [c for c in cookies if c.get("name") in keep], "origins": []}
    return minimal, "kept only the login-looking cookies (the full set was still too large)"


def classify(final_url: str, status: int | None = None, title: str = "") -> str:
    """'ok' (stayed on the studio), 'wall' (sent to the login), 'blocked' (refused by the site or a bot check) or 'other'.
    Pure: the decision depends on the address the browser ended on, the first response's status and the page title."""
    parts = urlsplit(final_url or "")
    host = (parts.hostname or "").lower()
    path = parts.path or "/"
    if host and not (host == HOST or host.endswith("." + HOST)):
        return "other"
    if any(path.startswith(p) for p in WALL_PATHS):
        return "wall"
    if BLOCK_TITLES.search(title or "") or (status in BLOCK_STATUSES):
        return "blocked"
    if path.rstrip("/") == STUDIO_PATH or path.startswith(STUDIO_PATH + "/"):
        return "ok"
    return "other"


def verdict(final_url: str, cookie_names: list[str], status: int | None = None, title: str = "") -> tuple[str, str]:
    """(code, one plain line). The pure verdict over a final URL, the login cookie NAMES the file holds, the first status
    and the title. Never given, and never prints, a cookie value."""
    code = classify(final_url, status, title)
    path = urlsplit(final_url or "").path or "/"
    if code == "wall":
        return code, ("nexabot.id: LOGIN WALL. The saved login was refused (expired, signed out, or the site wants a new "
                      "code): record it again with the login steps in ops/NEXABOT-LOGIN.md.")
    if code == "blocked":
        return code, (f"nexabot.id: BLOCKED. The site answered {status or 'a check page'} instead of the studio "
                      f"(page title {title[:60]!r}); a script may be refused from this address. Tell Claude this line.")
    if code == "other":
        where = (urlsplit(final_url or "").netloc or "?") + path
        return code, f"nexabot.id: UNEXPECTED. The browser ended on {where}, not the studio. Tell Claude this line."
    if not cookie_names:
        return code, ("nexabot.id: LOGGED IN (the studio stayed open), but no cookie whose name contains session, token or auth "
                      "is in the file, so the login may live in the page's saved data. Run the probe workflow to confirm.")
    return code, f"nexabot.id: LOGGED IN. The studio stayed open on {path} (login cookie names: {', '.join(cookie_names)})."


def launch_browser(pw: Any) -> Any:
    """SEMASA_CHROME if set (a local run), else Playwright's Chromium, else the machine's Google Chrome."""
    exe = os.environ.get("SEMASA_CHROME")
    tries: list[dict[str, Any]] = ([{"executable_path": exe}] if exe else []) + [{}, {"channel": "chrome"}]
    last: Exception | None = None
    for kwargs in tries:
        try:
            return pw.chromium.launch(**kwargs)
        except Exception as exc:  # noqa: BLE001 - try the next one
            last = exc
    raise RuntimeError(f"no browser could start: {str(last).splitlines()[0][:160] if last else '?'}")


def open_studio(browser: Any, state: dict[str, Any] | None, settle_ms: int = 2500) -> tuple[Any, Any, str, int | None, str]:
    """Open the studio in a fresh context holding `state`. Returns (context, page, final_url, first_status, title). Opens the
    page and waits; presses nothing."""
    ctx = browser.new_context(storage_state=state, locale="en-MY", timezone_id="Asia/Kuala_Lumpur",
                              viewport={"width": 1366, "height": 900})
    page = ctx.new_page()
    resp = page.goto(STUDIO_URL, wait_until="domcontentloaded", timeout=45_000)
    try:
        page.wait_for_load_state("networkidle", timeout=15_000)
    except Exception:  # noqa: BLE001 - a page that never goes quiet is still read
        pass
    page.wait_for_timeout(settle_ms)        # a client-side redirect to /login lands after the load
    try:
        title = page.title()
    except Exception:  # noqa: BLE001
        title = ""
    return ctx, page, page.url, (resp.status if resp else None), title


def main(argv: list[str]) -> int:
    args = [a for i, a in enumerate(argv[1:], 1) if not a.startswith("--") and (i < 2 or argv[i - 1] != "--b64")]
    if not args:
        print(__doc__)
        return 2
    path = args[0]
    try:
        raw = open(path, "rb").read()
        state = json.loads(raw)
    except (OSError, ValueError) as exc:
        print(f"Cannot read {path} as a Playwright storage_state.json: {exc}")
        return 2
    names = login_cookie_names(state)
    total = sum(1 for c in state.get("cookies") or [] if on_site(c.get("domain")))
    print(f"nexabot.id cookies in the file: {total}; login-looking names (contain session/token/auth): {names or 'none'}")
    upload, how = shrink(state)
    encoded = base64.b64encode(json.dumps(upload, separators=(",", ":")).encode()).decode()
    too_big = "  <- STILL TOO LARGE: record the login again in a fresh window and visit nothing else"
    print(f"Base64 size: {len(base64.b64encode(raw)):,} characters as saved; {len(encoded):,} to upload ({how}). "
          f"GitHub's limit for a secret is {GITHUB_SECRET_LIMIT:,}." + (too_big if len(encoded) > GITHUB_SECRET_LIMIT else ""))
    if "--b64" in argv:
        i = argv.index("--b64")
        out = argv[i + 1] if i + 1 < len(argv) and not argv[i + 1].startswith("--") else "storage_state.b64.txt"
        with open(out, "w", encoding="ascii") as fh:
            fh.write(encoded)
        print(f"Base64 written to {out}: paste its whole content as the secret NEXABOT_STORAGE_STATE_B64.")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright is not installed: pip install playwright && python -m playwright install chromium")
        return 2
    with sync_playwright() as pw:
        browser = launch_browser(pw)
        try:
            ctx, _page, url, status, title = open_studio(browser, upload)
            ctx.close()
        finally:
            browser.close()
    code, line = verdict(url, names, status, title)
    print()
    print(line)
    print("\nAll good: save the base64 as the secret NEXABOT_STORAGE_STATE_B64." if code == "ok"
          else "\nFix the line above, then run this again.")
    return 0 if code == "ok" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
