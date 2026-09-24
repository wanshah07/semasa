"""Smoke test for the built site: `npm run build`, serve dist/ on :4173, then `python smoke.py`.
CHROME_PATH overrides the browser. Network errors to Supabase/fonts are filtered; anything else fails."""
import os, sys
from playwright.sync_api import sync_playwright
errors=[]
with sync_playwright() as p:
    exe=os.environ.get("CHROME_PATH"); b=p.chromium.launch(executable_path=exe, args=["--no-sandbox"]) if exe else p.chromium.launch(); pg=b.new_page(viewport={"width":1280,"height":900})
    pg.on("console", lambda m: errors.append(m.text) if m.type=="error" else None)
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto("http://localhost:4173/", wait_until="networkidle", timeout=30000)
    pg.wait_for_timeout(1500)
    print("h1:", pg.locator("h1").first.inner_text())
    print("theme attr:", pg.get_attribute("html","data-theme"))
    pg.select_option("select[aria-label=Theme]","noir"); pg.wait_for_timeout(300)
    print("after switch:", pg.get_attribute("html","data-theme"), "bg:", pg.evaluate("getComputedStyle(document.body).backgroundColor"))
    pg.screenshot(path="/tmp/semasa_shot_isu.png")
    pg.get_by_role("button", name="Makmal media").first.click(); pg.wait_for_timeout(800)
    print("media h1:", pg.locator("h1").first.inner_text())
    print("auth form present:", pg.locator("input[type=email]").count())
    pg.select_option("select[aria-label=Theme]","facerinna"); pg.wait_for_timeout(300)
    pg.screenshot(path="/tmp/semasa_shot_media.png")
    pg.set_viewport_size({"width":390,"height":800}); pg.wait_for_timeout(300)
    print("h-scroll on phone:", pg.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth"))
    b.close()
# network errors to example.supabase.co are expected (no real project); filter those
real=[e for e in errors if not any(k in e for k in ("supabase.co","Failed to fetch","ERR_NAME_NOT_RESOLVED","ERR_TUNNEL","ERR_CERT","Failed to load resource"))]
print("console errors (non-network):", real)

sys.exit(1 if real else 0)
