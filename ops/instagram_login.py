"""Save a throwaway Instagram + Facebook login for Semasa's viral-post sweep. ONE file, nothing else to download.

INSTAGRAM ALONE (Wan, 24 Nov 2026: "add instagram live without kacau other platforms"): add the word `instagram` after the file name
(`python instagram_login.py instagram`). It asks for the Instagram login only and writes `secret-instagram.txt`, to be saved as a SECOND
secret, PW_STORAGE_STATE_IG_B64. The worker merges it over PW_STORAGE_STATE_B64 when it runs, so the secret Facebook (and anything
else) already reads with is never rewritten and nothing else changes.

Run it on your own computer (Windows PowerShell is fine), from any folder:

    python -m pip install playwright
    python -m playwright install chromium
    python instagram_login.py

On a Mac, type python3 wherever it says python. It opens a browser. Log in to the throwaway INSTAGRAM account (finish any code or "is this you" prompt, wait for the feed), press
Enter here, then log in to the throwaway FACEBOOK account the same way and press Enter again. It then writes `secret.txt`: paste the
WHOLE text of that file as the GitHub secret PW_STORAGE_STATE_B64 (repo wanshah07/semasa, Settings, Secrets and variables, Actions).
It prints names and sizes only, never a cookie. Never use ws.regulab, Valorith, FACERINNA or a personal account. See
ops/SOCIAL-LOGIN.md. (backend/semasa/social_check.py does the same checks and also reads a hashtag page, but needs the repo.)
"""

from __future__ import annotations

import base64
import json
import sys

LIMIT = 48_000                                  # GitHub refuses an Actions secret over 48 KB
NEEDS = {"instagram": ("sessionid", "ds_user_id"), "facebook": ("c_user", "xs")}
DOMAINS = {"instagram": "instagram.com", "facebook": "facebook.com"}
ESSENTIAL = {"sessionid", "ds_user_id", "csrftoken", "mid", "ig_did", "c_user", "xs", "datr", "sb", "fr"}


def encoded(state: dict) -> str:
    return base64.b64encode(json.dumps(state, separators=(",", ":")).encode()).decode()


def slim(state: dict, only: str = "") -> dict:
    """Only the Facebook and Instagram cookies (the sweep reads cookies only), or one platform's when `only` names it; the login
    cookies alone if still too large."""
    keep = [DOMAINS[only]] if only in DOMAINS else list(DOMAINS.values())
    cookies = [c for c in state.get("cookies") or [] if any(d in str(c.get("domain") or "") for d in keep)]
    out = {"cookies": cookies, "origins": []}
    if len(encoded(out)) > LIMIT:
        out = {"cookies": [c for c in cookies if c.get("name") in ESSENTIAL], "origins": []}
    return out


def held(state: dict) -> dict:
    cookies = state.get("cookies") or []
    out = {}
    for platform, names in NEEDS.items():
        mine = {c.get("name") for c in cookies if DOMAINS[platform] in str(c.get("domain") or "")}
        out[platform] = [n for n in names if n not in mine]            # what is MISSING
    return out


def main(argv: list[str] | None = None) -> int:
    only = "instagram" if "instagram" in [a.lower() for a in (sys.argv[1:] if argv is None else argv)] else ""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright is not installed. Run these two lines, then this file again:\n"
              "    python -m pip install playwright\n    python -m playwright install chromium")
        return 2
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        ctx = browser.new_context(locale="en-MY", viewport={"width": 1100, "height": 900})
        page = ctx.new_page()
        page.goto("https://www.instagram.com/")
        input("\n1) Log in to the throwaway INSTAGRAM account in the browser (finish any prompt, wait for the feed).\n"
              "   Then come back here and press Enter... ")
        if not only:
            page.goto("https://www.facebook.com/")
            input("\n2) Now log in to the throwaway FACEBOOK account the same way (do NOT use 'Log in with Facebook').\n"
                  "   Wait for the feed, then press Enter here... ")
        state = ctx.storage_state()
        browser.close()
    missing = {k: v for k, v in held(state).items() if not only or k == only}
    for platform, gone in missing.items():
        print(f"{platform.title()}: " + ("login cookie found" if not gone else f"NOT logged in ({', '.join(gone)} missing)"))
    upload = slim(state, only)
    text = encoded(upload)
    print(f"Secret size: {len(text):,} characters (GitHub's limit is {LIMIT:,}).")
    if len(text) > LIMIT:
        print("STILL TOO LARGE: run this again and visit nothing but the two logins.")
        return 1
    out_file, secret = ("secret-instagram.txt", "PW_STORAGE_STATE_IG_B64") if only else ("secret.txt", "PW_STORAGE_STATE_B64")
    with open(out_file, "w", encoding="ascii") as fh:
        fh.write(text)
    print(f"\nWrote {out_file}. Open it, select ALL, copy, and paste it as the secret {secret} on GitHub.")
    if any(missing.values()):
        print("One platform is not logged in: run this again and finish its login before pressing Enter.")
        return 1
    print(f"Then delete {out_file} from this computer. Never paste it in chat.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
