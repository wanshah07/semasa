"""READ-ONLY probe of the nexabot.id Creator Studio (https://nexabot.id/video-generator), Phase A (ops/NEXABOT-LOGIN.md).

    python -m semasa.nexabot_probe OUTDIR [--state storage_state.json]

It opens the studio with the saved login (NEXABOT_STORAGE_STATE_B64, or --state), and writes into OUTDIR:
  report.json, report.md   the page's structure: final address, title, the visible text of the main areas, every button, link,
                           input, select, textarea, tab and radio (role, accessible name, placeholder, type, disabled), the
                           options a menu shows when opened, the credit or balance text if shown, and the same-origin
                           XHR/fetch calls the page made as METHOD + PATH + status
  *.png                    full-page and menu screenshots (they can show the account name and balance)

What it never does, in code:
  * click anything that could spend credits or submit a generation: a control whose accessible name matches `FORBIDDEN`
    is refused by `is_forbidden`, a submit button is refused, and only tabs, dropdown triggers and comboboxes are ever clicked
    (`may_open`), then Escape is pressed;
  * type into the prompt box or any field;
  * let a write leave the browser: every POST, PUT, PATCH and DELETE is aborted at the network (`guard_route`) and listed in the
    report as blocked, so even a click that slipped past the name check could not submit a generation;
  * keep a header, a cookie, a request body or a response body, or a query VALUE: a request is METHOD + PATH (long id-like
    segments masked) + status + query key names only.
Nothing is written to Supabase.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from . import nexabot_check as check

# an accessible name that could spend credits, submit, pay or leave the page: such a control is never clicked
# (English and Indonesian/Malay, because the studio may speak either). A false refusal costs nothing: the probe only reads.
FORBIDDEN = re.compile(
    r"\b(generate|generat\w*|create|creat\w*|start|submit|send|buy|pay|payment|purchase|order|checkout|check\s*out|upgrade|"
    r"subscribe|subscription|top\s*-?\s*up|recharge|redeem|confirm|run|render|produce|make|download|delete|remove|"
    r"log\s*out|logout|sign\s*out|buat|bikin|hasilkan|kirim|bayar|beli|langganan|tingkatkan|isi\s*ulang|isi\s*saldo|"
    r"mulai|proses|unduh|hapus|padam|keluar)\b",
    re.IGNORECASE,
)
SAFE_METHODS = ("GET", "HEAD", "OPTIONS")
OPENERS_MAX = 14
ELEMENTS_MAX = 500
AREA_CHARS = 4000
ID_PARTS = re.compile(r"^(?:[0-9a-fA-F-]{16,}|[\d-]{5,})$")
BALANCE_WORDS = re.compile(r"credit|kredit|saldo|balance|coin|koin|token|poin|points|wallet|dompet", re.IGNORECASE)


# --- pure decisions ----------------------------------------------------------------------------------------------------------

def is_forbidden(name: str) -> bool:
    """True when an accessible name looks like something that spends credits, submits, pays or signs out."""
    return bool(FORBIDDEN.search(name or ""))


def may_open(el: dict[str, Any]) -> tuple[bool, str]:
    """(allowed, why) for clicking one element of the page snapshot. Only non-submitting UI opens: a tab, a combobox, or a
    button that announces a popup (aria-haspopup) or an expanded state. Anything else, and anything whose name is forbidden, is
    not clicked."""
    name = str(el.get("name") or "")
    role = str(el.get("role") or "")
    if el.get("disabled"):
        return False, "disabled"
    if str(el.get("type") or "").lower() in ("submit", "reset", "image"):
        return False, "a submit button"
    if is_forbidden(name):
        return False, f"name matches the forbidden list: {name[:40]!r}"
    popup = str(el.get("haspopup") or "").lower() not in ("", "false")
    if role in ("tab", "combobox") or popup or el.get("expanded") in ("true", "false"):
        if role == "link" or el.get("href"):
            return False, "a link, not a menu"
        return True, "opens a tab or a menu"
    return False, "not a tab or a menu"


def id_like(seg: str) -> bool:
    """A path segment that may be an id or a token: long, or mixing letters with digits, or a JWT or a UUID. Masked in the report,
    so a token that rides in a path can never be copied out of it."""
    if not seg or seg.startswith(":"):
        return False
    letters, digits = bool(re.search(r"[A-Za-z]", seg)), len(re.findall(r"\d", seg))
    return bool(ID_PARTS.match(seg) or len(seg) >= 28 or seg.startswith("eyJ") or (len(seg) >= 16 and (digits or "." in seg))
                or (len(seg) >= 10 and letters and digits >= 2))


def clean_path(url: str, origin: str = check.ORIGIN) -> str | None:
    """The same-origin path of a request with every id-like segment masked and the query reduced to its key names:
    '/api/x/123456?token=abc&n=1' -> '/api/x/:id?token=&n='. None for another origin."""
    parts = urlsplit(url or "")
    want = urlsplit(origin)
    if (parts.scheme, parts.netloc) != (want.scheme, want.netloc):
        return None
    segs = [":id" if id_like(s) else s for s in (parts.path or "/").split("/")]
    path = "/".join(segs) or "/"
    keys = [k for k, _ in parse_qsl(parts.query, keep_blank_values=True)]
    return path + ("?" + "&".join(f"{k[:30]}=" for k in keys[:8]) if keys else "")


def summarise_requests(events: Iterable[dict[str, Any]], origin: str = check.ORIGIN) -> list[dict[str, Any]]:
    """[{method, path, status, count}] for the page's same-origin XHR and fetch calls. Reads only `method`, `url`, `status` and
    `resource_type` from each event: whatever else an event carries (headers, cookies, bodies) is never looked at."""
    seen: dict[tuple[str, str, Any], dict[str, Any]] = {}
    for ev in events:
        if str(ev.get("resource_type") or "").lower() not in ("xhr", "fetch"):
            continue
        path = clean_path(str(ev.get("url") or ""), origin)
        if path is None:
            continue
        key = (str(ev.get("method") or "GET").upper(), path, ev.get("status"))
        row = seen.setdefault(key, {"method": key[0], "path": path, "status": key[2], "count": 0})
        row["count"] += 1
    return sorted(seen.values(), key=lambda r: (r["path"], r["method"]))


def balance_lines(text: str) -> list[str]:
    """Short lines of visible text that mention credits, a balance or a wallet (the owner's own, for a private artifact)."""
    out: list[str] = []
    for line in re.split(r"[\n\r]+", text or ""):
        line = re.sub(r"\s+", " ", line).strip()
        if line and len(line) <= 120 and BALANCE_WORDS.search(line) and line not in out:
            out.append(line)
    return out[:15]


def redact(text: str, secrets: Iterable[str]) -> str:
    """Replace every secret value that somehow reached `text`. Defence in depth: nothing is meant to put one there."""
    for s in sorted({s for s in secrets if s and len(s) >= 6}, key=len, reverse=True):
        text = text.replace(s, "[redacted]")
    return text


def secret_values(state: dict[str, Any] | None) -> list[str]:
    """Every cookie and localStorage value in a saved login: what must never appear in a report."""
    out: list[str] = []
    for c in (state or {}).get("cookies") or []:
        out.append(str(c.get("value") or ""))
    for o in (state or {}).get("origins") or []:
        for item in o.get("localStorage") or []:
            out.append(str(item.get("value") or ""))
    return out


def build_report(*, started: str, final_url: str, title: str, status: int | None, code: str, line: str,
                 login_names: list[str], areas: dict[str, str], elements: list[dict[str, Any]],
                 opened: list[dict[str, Any]], skipped: list[dict[str, Any]], events: Iterable[dict[str, Any]],
                 blocked_writes: list[str], screenshots: list[str], notes: list[str]) -> dict[str, Any]:
    """The report as plain data. Every field is a name, a count or text the page showed to a visitor."""
    own = final_url
    parts = urlsplit(own)
    safe_url = f"{parts.scheme}://{parts.netloc}{parts.path}" if parts.netloc else own
    text = "\n".join(areas.values())
    return {
        "started": started, "verdict": code, "verdict_line": line, "final_url": safe_url, "first_status": status, "title": title,
        "login_cookie_names": login_names, "areas": areas, "balance_lines": balance_lines(text),
        "elements": elements[:ELEMENTS_MAX], "opened": opened, "skipped_by_guard": skipped,
        "requests": summarise_requests(events), "blocked_writes": sorted(set(blocked_writes)),
        "screenshots": screenshots, "notes": notes,
    }


def _cell(v: Any) -> str:
    return str(v if v not in (None, "") else "").replace("|", "/").replace("\n", " ")[:80]


def render_md(rep: dict[str, Any]) -> str:
    """A readable version of the report."""
    out = ["# Nexabot studio probe (read-only)", "",
           f"- Started: {rep['started']}", f"- Verdict: **{rep['verdict']}**: {rep['verdict_line']}",
           f"- Final address: `{rep['final_url']}` (first status {rep['first_status']})", f"- Page title: {rep['title']!r}",
           f"- Login cookie names (names only): {', '.join(rep['login_cookie_names']) or 'none'}", ""]
    if rep["balance_lines"]:
        out += ["## Credit / balance text", ""] + [f"- {b}" for b in rep["balance_lines"]] + [""]
    out += ["## Visible text of the main areas", ""]
    for name, text in rep["areas"].items():
        out += [f"### {name}", "", "```", text, "```", ""]
    out += ["## Controls", "", "| role | name | placeholder | type | disabled | options |", "|---|---|---|---|---|---|"]
    for e in rep["elements"]:
        out.append(f"| {_cell(e.get('role'))} | {_cell(e.get('name'))} | {_cell(e.get('placeholder'))} | "
                   f"{_cell(e.get('type'))} | "
                   f"{'yes' if e.get('disabled') else ''} | {_cell(', '.join(e.get('options') or []))} |")
    out += ["", "## Menus and tabs opened (nothing was chosen or submitted)", ""]
    for o in rep["opened"]:
        out += [f"### {o.get('role')}: {o.get('name') or '(no name)'}", ""]
        if o.get("options"):
            out += ["Options seen: " + "; ".join(o["options"]), ""]
        if o.get("panel"):
            out += ["```", o["panel"], "```", ""]
        if o.get("screenshot"):
            out += [f"Screenshot: `{o['screenshot']}`", ""]
    out += ["## Skipped by the guard (never clicked)", ""] + [f"- {s.get('role')} {s.get('name')!r}: {s.get('why')}"
                                                                for s in rep["skipped_by_guard"]] + [""]
    out += ["## Same-origin XHR / fetch calls (method, path, status; no headers, bodies or query values)", "",
            "| method | path | status | times |", "|---|---|---|---|"]
    out += [f"| {r['method']} | `{r['path']}` | {r['status']} | {r['count']} |" for r in rep["requests"]]
    out += ["", "## Writes blocked at the network (POST, PUT, PATCH, DELETE; never sent)", ""]
    out += [f"- {b}" for b in rep["blocked_writes"]] or ["- none"]
    out += ["", "## Screenshots", ""] + [f"- `{s}`" for s in rep["screenshots"]]
    out += ["", "## Notes", ""] + [f"- {n}" for n in rep["notes"]]
    return "\n".join(out) + "\n"


# --- in the page -------------------------------------------------------------------------------------------------------------

# Reads the page and changes nothing but a data-nbprobe marker on each control, so Python can find it again.
SNAPSHOT_JS = r"""
() => {
  const vis = (e) => { const r = e.getBoundingClientRect(), s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const txt = (e) => (e.innerText || e.textContent || '').replace(/\s+/g, ' ').trim();
  const nameOf = (e) => {
    const a = e.getAttribute('aria-label'); if (a && a.trim()) return a.trim();
    const by = e.getAttribute('aria-labelledby');
    if (by) {
      const t = by.split(/\s+/).map((i) => document.getElementById(i)).filter(Boolean).map(txt).join(' ').trim();
      if (t) return t;
    }
    if (e.labels && e.labels.length) { const t = [...e.labels].map(txt).join(' ').trim(); if (t) return t; }
    const t = txt(e); if (t) return t;
    const img = e.querySelector('img[alt]');
    const alt = img ? img.getAttribute('alt') : '';
    return (e.getAttribute('title') || e.getAttribute('alt') || e.getAttribute('placeholder') || alt || '').trim();
  };
  const roleOf = (e) => {
    const r = e.getAttribute('role'); if (r) return r;
    const t = e.tagName.toLowerCase();
    if (t === 'a') return 'link'; if (t === 'button') return 'button'; if (t === 'select') return 'combobox';
    if (t === 'textarea') return 'textbox';
    if (t === 'input') { const y = (e.type || 'text').toLowerCase();
      if (y === 'checkbox' || y === 'radio' || y === 'file') return y;
      return (y === 'submit' || y === 'button') ? 'button' : 'textbox'; }
    return t;
  };
  const sel = 'button, a[href], input, select, textarea, [role=tab], [role=radio], [role=combobox], [role=switch], '
            + '[role=checkbox], [role=menuitem], [role=option], [role=button], [aria-haspopup]';
  const out = []; let i = 0;
  for (const e of document.querySelectorAll(sel)) {
    if (e.tagName === 'INPUT' && (e.type || '').toLowerCase() === 'hidden') continue;
    if (!vis(e)) continue;
    e.setAttribute('data-nbprobe', String(i));
    let href = '';
    if (e.tagName === 'A') {
      try {
        const u = new URL(e.href, location.href);
        href = u.origin === location.origin ? u.pathname : u.hostname;
      } catch (_) {}
    }
    const row = {i, role: roleOf(e), tag: e.tagName.toLowerCase(), name: nameOf(e).slice(0, 120),
      placeholder: (e.getAttribute('placeholder') || '').slice(0, 120), type: (e.getAttribute('type') || '').toLowerCase(),
      disabled: !!(e.disabled || e.getAttribute('aria-disabled') === 'true'), href,
      haspopup: e.getAttribute('aria-haspopup') || '', expanded: e.getAttribute('aria-expanded') || '',
      checked: e.getAttribute('aria-checked') || e.getAttribute('aria-selected') || (e.checked === true ? 'true' : '')};
    if (e.tagName === 'SELECT') row.options = [...e.options].map((o) => (o.textContent || '').trim().slice(0, 60)).slice(0, 60);
    out.push(row); i++;
  }
  const areas = {};
  const grab = (label, nodes) => {
    const lines = (e) => (e.innerText || '').replace(/[ \t]+/g, ' ').replace(/\n\s*\n+/g, '\n').trim();
    const t = nodes.filter(vis).map(lines).filter(Boolean).join('\n').slice(0, __AREA__);
    if (t) areas[label] = t;
  };
  grab('header', [...document.querySelectorAll('header')]);
  grab('nav', [...document.querySelectorAll('nav, aside')]);
  grab('main', [...document.querySelectorAll('main, [role=main]')]);
  grab('dialog', [...document.querySelectorAll('[role=dialog], [role=alertdialog]')]);
  grab('footer', [...document.querySelectorAll('footer')]);
  if (!areas.main) grab('body', [document.body]);
  const headings = [...document.querySelectorAll('h1,h2,h3')].filter(vis).map((h) => txt(h).slice(0, 100)).slice(0, 40);
  return {elements: out, areas, headings};
}
""".replace("__AREA__", str(AREA_CHARS))

# What an opened menu shows: its options and panels, text only. Nothing is chosen.
POPUP_JS = r"""
() => {
  const vis = (e) => { const r = e.getBoundingClientRect(), s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const txt = (e) => (e.innerText || e.textContent || '').replace(/\s+/g, ' ').trim();
  const opts = [...document.querySelectorAll('[role=option], [role=menuitem], [role=menuitemradio], [role=menuitemcheckbox]')]
    .filter(vis).map((e) => txt(e).slice(0, 80)).filter(Boolean);
  const panels = [...document.querySelectorAll('[role=listbox], [role=menu], [role=dialog], [role=tabpanel], '
                                              + '[data-radix-popper-content-wrapper]')]
    .filter(vis).map((e) => txt(e).slice(0, 1200)).filter(Boolean);
  return {options: [...new Set(opts)].slice(0, 80), panel: [...new Set(panels)].join('\n---\n').slice(0, 2400)};
}
"""


def guard_route(blocked: list[str]) -> Any:
    """A Playwright route handler: reads go through, every write (POST, PUT, PATCH, DELETE) is aborted and noted."""
    def handler(route: Any) -> None:
        req = route.request
        if req.method.upper() in SAFE_METHODS:
            route.fallback()          # the next handler, or the network
            return
        parts = urlsplit(req.url)
        blocked.append(f"{req.method.upper()} {parts.netloc}{clean_path(req.url, f'{parts.scheme}://{parts.netloc}') or ''}")
        route.abort()
    return handler


def _shot(page: Any, outdir: Path, name: str, full: bool) -> str:
    try:
        page.screenshot(path=str(outdir / name), full_page=full)
        return name
    except Exception:  # noqa: BLE001 - a screenshot that fails is not a failed probe
        return ""


def probe(page: Any, outdir: Path, events: list[dict[str, Any]], blocked: list[str]) -> dict[str, Any]:
    """Read the open studio: snapshot, then open (never choose in) each tab and menu the guard allows."""
    notes: list[str] = []
    shots: list[str] = []
    opened: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    snap = page.evaluate(SNAPSHOT_JS)
    s = _shot(page, outdir, "01-studio-full.png", True)
    if s:
        shots.append(s)
    start_url = page.url
    todo = []
    for el in snap["elements"]:
        ok, why = may_open(el)
        if ok:
            todo.append(el)
        elif el.get("role") in ("tab", "combobox") or el.get("haspopup") or is_forbidden(el.get("name", "")):
            skipped.append({"role": el.get("role"), "name": el.get("name"), "why": why})
    notes.append(f"{len(snap['elements'])} controls seen; {len(todo)} tab/menu controls are allowed to open; "
                 f"{len(skipped)} refused by the guard")
    for n, el in enumerate(todo[:OPENERS_MAX], 1):
        ok, _why = may_open(el)                       # asked again at the moment of the click
        if not ok:
            continue
        try:
            page.locator(f'[data-nbprobe="{el["i"]}"]').first.click(timeout=4000)
            page.wait_for_timeout(500)
            if page.url.split("#")[0] != start_url.split("#")[0]:
                notes.append(f"opening {el.get('name')!r} changed the address; went back")
                page.goto(start_url, wait_until="domcontentloaded", timeout=30_000)
                page.wait_for_timeout(1500)
                snap_after = page.evaluate(SNAPSHOT_JS)       # the markers were lost with the page
                snap["elements"] = snap_after["elements"]
                continue
            popup = page.evaluate(POPUP_JS)
            slug = re.sub(r"[^a-z0-9]+", "-", str(el.get("name")).lower())[:24] or "control"
            shot = _shot(page, outdir, f"{n + 1:02d}-open-{slug}.png", False)
            if shot:
                shots.append(shot)
            opened.append({"role": el.get("role"), "name": el.get("name"), "options": popup["options"], "panel": popup["panel"],
                           "screenshot": shot})
        except Exception as exc:  # noqa: BLE001 - one control that will not open does not end the probe
            notes.append(f"could not open {el.get('name')!r}: {str(exc).splitlines()[0][:100]}")
        finally:
            try:
                page.keyboard.press("Escape")
                page.wait_for_timeout(250)
            except Exception:  # noqa: BLE001
                pass
    final = page.evaluate(SNAPSHOT_JS)       # what is on the page after the tabs were visited, for the areas of the report
    areas = {**snap["areas"], **{f"{k} (after opening tabs)": v for k, v in final["areas"].items() if v != snap["areas"].get(k)}}
    if snap.get("headings"):
        areas = {"headings": "\n".join(snap["headings"]), **areas}
    return {"areas": areas, "elements": snap["elements"], "opened": opened, "skipped": skipped,
            "screenshots": shots, "notes": notes}


def run(outdir: Path, state: dict[str, Any] | None) -> tuple[int, dict[str, Any]]:
    from playwright.sync_api import sync_playwright

    outdir.mkdir(parents=True, exist_ok=True)
    started = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    events: list[dict[str, Any]] = []
    blocked: list[str] = []
    names = check.login_cookie_names(state or {})
    with sync_playwright() as pw:
        browser = check.launch_browser(pw)
        try:
            ctx = browser.new_context(storage_state=state, locale="en-MY", timezone_id="Asia/Kuala_Lumpur",
                                      viewport={"width": 1366, "height": 900})
            ctx.route("**/*", guard_route(blocked))
            ctx.on("response", lambda r: events.append({"method": r.request.method, "url": r.url, "status": r.status,
                                                        "resource_type": r.request.resource_type}))
            page = ctx.new_page()
            page.on("dialog", lambda d: d.dismiss())            # a confirm() is never accepted
            resp = page.goto(check.STUDIO_URL, wait_until="domcontentloaded", timeout=45_000)
            try:
                page.wait_for_load_state("networkidle", timeout=15_000)
            except Exception:  # noqa: BLE001
                pass
            page.wait_for_timeout(2500)
            title = page.title()
            code, line = check.verdict(page.url, names, resp.status if resp else None, title)
            if code != "ok":
                shot = _shot(page, outdir, "00-not-the-studio.png", False)
                body = {"areas": {}, "elements": [], "opened": [], "skipped": [], "screenshots": [shot] if shot else [],
                        "notes": ["the studio did not open, so nothing was probed"]}
            else:
                body = probe(page, outdir, events, blocked)
            report = build_report(started=started, final_url=page.url, title=title, code=code, line=line,
                                  status=resp.status if resp else None, login_names=names, events=events,
                                  blocked_writes=blocked, **body)
        finally:
            browser.close()
    secrets = secret_values(state)
    (outdir / "report.json").write_text(redact(json.dumps(report, indent=1, ensure_ascii=False), secrets), encoding="utf-8")
    (outdir / "report.md").write_text(redact(render_md(report), secrets), encoding="utf-8")
    return (0 if code == "ok" else 1), report


def main(argv: list[str]) -> int:
    args = [a for i, a in enumerate(argv[1:], 1) if not a.startswith("--") and argv[i - 1] != "--state"]
    if not args:
        print(__doc__)
        return 2
    state = None
    path = argv[argv.index("--state") + 1] if "--state" in argv and argv.index("--state") + 1 < len(argv) else ""
    if path:
        state = json.loads(Path(path).read_text())
    elif os.environ.get("NEXABOT_STORAGE_STATE_B64", "").strip():
        import base64
        try:
            state = json.loads(base64.b64decode(os.environ["NEXABOT_STORAGE_STATE_B64"].strip()))
        except ValueError:
            print("NEXABOT_STORAGE_STATE_B64 is not base64 of a storage_state.json: record the login again.")
            return 2
    else:
        print("No saved login given (no --state, no NEXABOT_STORAGE_STATE_B64): opening logged out, as a test run.")
    code, rep = run(Path(args[0]), state)
    print(rep["verdict_line"])
    print(f"{len(rep['elements'])} controls, {len(rep['opened'])} menus/tabs opened, "
          f"{len(rep['requests'])} distinct same-origin calls, {len(rep['blocked_writes'])} writes blocked, "
          f"{len(rep['screenshots'])} screenshots -> {args[0]}")
    if code != 0:
        print("::error::the saved login was refused: record it again (ops/NEXABOT-LOGIN.md)" if rep["verdict"] == "wall"
              else f"::error::the studio did not open as expected ({rep['verdict']}): see the report")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
