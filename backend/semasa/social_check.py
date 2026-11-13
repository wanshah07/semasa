"""Check a saved Facebook/Instagram login BEFORE it is uploaded as the secret PW_STORAGE_STATE_B64 (ops/SOCIAL-LOGIN.md).

Run it on your own computer, from the backend folder:

    python -m semasa.social_check storage_state.json            # tries #halalmalaysia on both
    python -m semasa.social_check storage_state.json sijilhalal  # another hashtag
    python -m semasa.social_check storage_state.json --b64 secret.txt   # also writes the base64 to paste into GitHub

It opens the same pages the Sources sweep opens, with that login, and says per platform whether it got in and how many posts it
read. It prints counts and verdicts only: never a cookie, never a token. A login wall means the session is expired or was
refused, and the sweep would have read nothing.
"""

from __future__ import annotations

import base64
import json
import sys
from datetime import UTC, datetime
from typing import Any

from . import social_web

GITHUB_SECRET_LIMIT = 48_000          # GitHub refuses an Actions secret over 48 KB
NEEDS = {"instagram": ("sessionid", "ds_user_id"), "facebook": ("c_user", "xs")}
DOMAINS = {"instagram": "instagram.com", "facebook": "facebook.com"}
# the cookies a login rests on; the last resort when even the two sites' cookies are too big for a secret
ESSENTIAL = {"sessionid", "ds_user_id", "csrftoken", "mid", "ig_did", "c_user", "xs", "datr", "sb", "fr"}


def _encoded_size(state: dict[str, Any]) -> int:
    return len(base64.b64encode(json.dumps(state, separators=(",", ":")).encode()))


def shrink(state: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """The smallest login the sweep can use: (state, what_was_dropped).
    A codegen file carries every site's localStorage (Facebook alone is tens of KB), and the sweep reads cookies only. So keep
    the Facebook and Instagram cookies and drop the rest; if that is still over GitHub's limit, keep only the login cookies."""
    cookies = [c for c in state.get("cookies") or [] if any(d in str(c.get("domain") or "") for d in DOMAINS.values())]
    slim = {"cookies": cookies, "origins": []}
    if _encoded_size(slim) <= GITHUB_SECRET_LIMIT:
        return slim, "kept the Facebook and Instagram cookies, dropped the saved page data"
    minimal = {"cookies": [c for c in cookies if c.get("name") in ESSENTIAL], "origins": []}
    return minimal, "kept only the login cookies (the full set was still too large)"


def inspect_state(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Which platforms the file holds a login cookie for, by name only: {platform: {"has": [...], "missing": [...]}}."""
    cookies = state.get("cookies") or []
    out: dict[str, dict[str, Any]] = {}
    for platform, names in NEEDS.items():
        mine = {c.get("name") for c in cookies if DOMAINS[platform] in str(c.get("domain") or "")}
        out[platform] = {"has": [n for n in names if n in mine], "missing": [n for n in names if n not in mine]}
    return out


def verdict(platform: str, held: dict[str, Any], posts: int, error: str) -> str:
    """One plain line per platform: what to do next."""
    if held["missing"]:
        return (f"{platform.title()}: this file has no {platform.title()} login ({', '.join(held['missing'])} missing). "
                f"Log in to {platform.title()} in the same codegen window, then close it and save again.")
    if "asked for a login" in error:
        return (f"{platform.title()}: LOGIN WALL. The session is expired, was refused (a security check, a new-device "
                f"prompt) or is not logged in. Log in again in the codegen window and complete any prompt.")
    if error:
        return f"{platform.title()}: could not read ({error[:140]}). Try again; if it repeats, tell Claude this line."
    if posts == 0:
        return (f"{platform.title()}: logged in, but no posts came back for that hashtag. Try another hashtag "
                f"(python -m semasa.social_check storage_state.json sijilhalal).")
    return f"{platform.title()}: OK, {posts} post(s) read."


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 2
    path = args[0]
    tag = social_web.hashtag(args[1]) if len(args) > 1 else "halalmalaysia"
    try:
        raw = open(path, "rb").read()
        state = json.loads(raw)
    except (OSError, ValueError) as exc:
        print(f"Cannot read {path} as a Playwright storage_state.json: {exc}")
        return 2
    held = inspect_state(state)
    for platform, h in held.items():
        print(f"{platform.title()} cookies: has {h['has'] or 'none'}; missing {h['missing'] or 'none'}")
    upload, dropped = shrink(state)
    encoded = base64.b64encode(json.dumps(upload, separators=(",", ":")).encode()).decode()
    too_big = "  <- STILL TOO LARGE: log in again in a fresh codegen window, and visit nothing else"
    print(f"Base64 size: {len(base64.b64encode(raw)):,} characters as saved; {len(encoded):,} to upload ({dropped}). "
          f"GitHub's limit for a secret is {GITHUB_SECRET_LIMIT:,}." + (too_big if len(encoded) > GITHUB_SECRET_LIMIT else ""))
    if "--b64" in argv:
        out = argv[argv.index("--b64") + 1] if argv.index("--b64") + 1 < len(argv) else "storage_state.b64.txt"
        with open(out, "w", encoding="ascii") as fh:
            fh.write(encoded)
        print(f"Base64 written to {out}: paste its whole content as the secret PW_STORAGE_STATE_B64.")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright is not installed: pip install playwright && python -m playwright install chromium")
        return 2
    now = datetime.now(UTC)
    results: dict[str, tuple[int, str]] = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            ctx = browser.new_context(storage_state=upload, locale="en-MY", timezone_id="UTC",
                                      viewport={"width": 1280, "height": 2400})
            page = ctx.new_page()
            for platform, reader in (("facebook", social_web.read_facebook), ("instagram", social_web.read_instagram)):
                posts, err = reader(page, tag, now)
                results[platform] = (len(posts), err)
        finally:
            browser.close()
    print()
    ok = True
    for platform in ("facebook", "instagram"):
        posts, err = results[platform]
        line = verdict(platform, held[platform], posts, err)
        ok = ok and line.split(": ", 1)[1].startswith("OK")
        print(line)
    print("\nAll good: save the base64 as the secret PW_STORAGE_STATE_B64." if ok
          else "\nFix the line(s) above, then run this again.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
