"""READ-ONLY probe of the nexabot.id Creator Studio (https://nexabot.id/video-generator), Phase A (ops/NEXABOT-LOGIN.md).

    python -m semasa.nexabot_probe OUTDIR [--state storage_state.json] [--path /api-docs]

It opens the studio with the saved login (NEXABOT_STORAGE_STATE_B64, or --state), and writes into OUTDIR:
  report.json, report.md   the page's structure: final address, title, the visible text of the main areas, every button, link,
                           input, select, textarea, tab and radio (role, accessible name, placeholder, type, disabled), the
                           options a menu shows when opened, the credit or balance text if shown, and the same-origin
                           XHR/fetch calls the page made as METHOD + PATH + status
  *.png                    full-page and menu screenshots (they can show the account name and balance)

With --path PATH (default /video-generator) it reads ANY other same-origin page instead, as text only: the headings, paragraphs,
code blocks, tables and same-origin link paths of the page (used for /api-docs), after the same guarded opening of tabs and
accordions. Everything that looks like a secret in that text (bearer tokens, JWTs, key-prefixed strings, long mixed
letter-and-digit tokens, `api_key: value` pairs) is replaced with [REDACTED] before anything is written, as is every saved cookie
value. /api-keys (the page that lists the account's own keys) and sign-out addresses are refused in code (`check_path`).

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
from urllib.parse import parse_qsl, unquote, urlsplit

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

REDACTED = "[REDACTED]"
# path segments that are never opened: the page that lists the owner's own API keys, and anything that signs the session out
PRIVATE_SEGMENTS = frozenset({"api-keys", "api_keys", "apikeys", "api-key", "api_key", "apikey",
                              "logout", "log-out", "signout", "sign-out"})
PATH_OK = re.compile(r"^/[A-Za-z0-9/_\-.]*$")
TEXT_MAX = 200_000


class PathRefused(ValueError):
    """A path the probe will not open."""


def private_path(path: str) -> bool:
    """True when any segment of `path` is a private one (the owner's API keys, a sign-out address)."""
    segs = [s.lower() for s in re.split(r"[/]+", unquote(path or "")) if s]
    return any(s in PRIVATE_SEGMENTS for s in segs)


def check_path(raw: str) -> str:
    """The same-origin path the probe may open, or PathRefused. Only a plain path is accepted (no scheme, no host, no query, no
    fragment, no `..`); /api-keys in any spelling, and a sign-out address, are refused."""
    path = (raw or "").strip() or check.STUDIO_PATH
    if not PATH_OK.match(path) or path.startswith("//") or ".." in path:
        raise PathRefused(f"not a plain same-origin path: {path[:60]!r} (give a path like /api-docs)")
    if private_path(path):
        raise PathRefused(f"{path} is never opened: it lists the account's own keys or signs the session out")
    return path.rstrip("/") or "/"


def private_url(url: str, origin: str = check.ORIGIN) -> bool:
    """True when a request address is a same-origin private page (checked at the network as well, so a redirect or a script
    cannot take the browser there either)."""
    parts = urlsplit(url or "")
    want = urlsplit(origin)
    return (parts.scheme, parts.netloc) == (want.scheme, want.netloc) and private_path(parts.path)


# --- secrets in text ----------------------------------------------------------------------------------------------------------

_PLACEHOLDER = re.compile(r"your|example|placeholder|x{6,}|\*{3,}|<|>|\.\.\.|\{|\}", re.IGNORECASE)
_TYPE_WORDS = frozenset({"string", "number", "boolean", "integer", "object", "array", "null", "true", "false", "required",
                         "optional", "bearer", "basic", "token"})
_JWT = re.compile(r"(?<![A-Za-z0-9_\-])ey[A-Za-z0-9_\-]{6,}\.[A-Za-z0-9_\-]{6,}(?:\.[A-Za-z0-9_\-]*)?")
_BEARER = re.compile(r"(?i)\b(bearer|basic)(\s+)([A-Za-z0-9._~+/=\-]{8,})")
_PREFIXED = re.compile(r"(?<![A-Za-z0-9])(?:sk|pk|rk|nx|nxb|smi|ghp|gho|ghs|github_pat|xox[abp])[-_][A-Za-z0-9_\-]{8,}")
_ASSIGN = re.compile(
    r"""(?ix)
    (?P<k>(?:x-)?(?:api[-_]?key|apikey|access[-_]?token|auth[-_]?token|refresh[-_]?token|secret(?:[-_]?key)?|client[-_]?secret|
         password|passwd|token|authorization|cookie|session[-_]?id|signature)["']?)
    (?P<sep>\s*[:=]\s*)
    (?P<q>["']?)
    (?P<scheme>(?:(?:bearer|basic|token)\s+)?)
    (?P<v>[^\s"',;&<>\[\]]{6,})""")
_LONG = re.compile(r"(?<![A-Za-z0-9_\-])[A-Za-z0-9_\-]{24,}(?![A-Za-z0-9_\-])")


def _long_secretish(tok: str) -> bool:
    """A 24+ character token that mixes letters and digits and is not a slug of plain words and short numbers."""
    if not (re.search(r"[A-Za-z]", tok) and re.search(r"\d", tok)) or _PLACEHOLDER.search(tok):
        return False
    segs = [s for s in re.split(r"[-_]", tok) if s]
    slug = all((s.isalpha() and s.islower() and len(s) <= 14) or (s.isdigit() and len(s) <= 4) for s in segs)
    return not slug


def _redact_text(text: str) -> tuple[str, int]:
    n = 0

    def hit(keep: str = "") -> str:
        nonlocal n
        n += 1
        return keep + REDACTED

    text = _JWT.sub(lambda m: hit(), text)
    text = _BEARER.sub(lambda m: m.group(0) if _PLACEHOLDER.search(m.group(3)) or REDACTED in m.group(3)
                       else hit(f"{m.group(1)}{m.group(2)}"), text)
    text = _PREFIXED.sub(lambda m: m.group(0) if _PLACEHOLDER.search(m.group(0)) else hit(), text)

    def assign(m: re.Match[str]) -> str:
        v = m.group("v")
        if REDACTED in v or _PLACEHOLDER.search(v) or v.lower().strip("\"'") in _TYPE_WORDS:
            return m.group(0)
        return hit(f"{m.group('k')}{m.group('sep')}{m.group('q')}{m.group('scheme')}")

    text = _ASSIGN.sub(assign, text)
    text = _LONG.sub(lambda m: hit() if _long_secretish(m.group(0)) else m.group(0), text)
    return text, n


def redact_secrets(text: str) -> str:
    """`text` with everything that looks like a secret replaced by [REDACTED]: JWTs, bearer and basic credentials, strings with
    a key-like prefix (sk-, nx_, nxb_, smi_ ...), `api_key: value` style pairs, and any 24+ character token that mixes letters
    and digits (not a slug of plain words, not a placeholder such as YOUR_API_KEY). Plain words, paths and short ids stay."""
    return _redact_text(text or "")[0]


def redact_tree(obj: Any) -> tuple[Any, int]:
    """The same redaction over every string inside a dict/list report, BEFORE it is serialised (redacting JSON text could eat
    a backslash and break the file). Returns (clean copy, number of strings replaced)."""
    if isinstance(obj, str):
        return _redact_text(obj)
    if isinstance(obj, list):
        pairs = [redact_tree(v) for v in obj]
        return [p[0] for p in pairs], sum(p[1] for p in pairs)
    if isinstance(obj, dict):
        out: dict[Any, Any] = {}
        total = 0
        for k, v in obj.items():
            out[k], c = redact_tree(v)
            total += c
        return out, total
    return obj, 0


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


def private_marker(url: str) -> str:
    """What the report says about a refused private address: the first private segment, never the rest of the address."""
    for seg in urlsplit(url).path.split("/"):
        if seg.lower() in PRIVATE_SEGMENTS:
            return "/" + seg.lower() + " (private page)"
    return "(private page)"


def guard_route(blocked: list[str]) -> Any:
    """A Playwright route handler: reads go through, every write (POST, PUT, PATCH, DELETE) is aborted and noted."""
    def handler(route: Any) -> None:
        req = route.request
        if private_url(req.url):
            blocked.append(f"{req.method.upper()} {urlsplit(req.url).netloc}{private_marker(req.url)}")
            route.abort()             # the owner's keys page (or a sign-out) is never fetched, whoever asked
            return
        if req.method.upper() in SAFE_METHODS:
            route.fallback()          # the next handler, or the network
            return
        parts = urlsplit(req.url)
        blocked.append(f"{req.method.upper()} {parts.netloc}{clean_path(req.url, f'{parts.scheme}://{parts.netloc}') or ''}")
        route.abort()
    return handler


# Screenshots are taken for the studio page only. A docs page can show a real credential on screen, and an image cannot
# be redacted the way the text is, so reading any other page (--path) writes no picture at all.
SCREENSHOTS_ON = True


def _shot(page: Any, outdir: Path, name: str, full: bool) -> str:
    if not SCREENSHOTS_ON:
        return ""
    try:
        page.screenshot(path=str(outdir / name), full_page=full)
        return name
    except Exception:  # noqa: BLE001 - a screenshot that fails is not a failed probe
        return ""


def probe(page: Any, outdir: Path, events: list[dict[str, Any]], blocked: list[str],
          full_shot: str = "01-studio-full.png") -> dict[str, Any]:
    """Read the open studio: snapshot, then open (never choose in) each tab and menu the guard allows."""
    notes: list[str] = []
    shots: list[str] = []
    opened: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    snap = page.evaluate(SNAPSHOT_JS)
    s = _shot(page, outdir, full_shot, True)
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


# --- reading any other page as text ------------------------------------------------------------------------------------------

# The whole visible text of a page, plus its headings, code blocks (hidden tab panels included: textContent), tables and the
# same-origin paths its links point to. It reads only; it presses nothing.
PAGE_TEXT_JS = r"""
() => {
  const vis = (e) => { const r = e.getBoundingClientRect(), s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const one = (t) => (t || '').replace(/\s+/g, ' ').trim();
  const text = (document.body.innerText || '').replace(/[ \t]+/g, ' ').replace(/\n{3,}/g, '\n\n').trim().slice(0, __MAX__);
  const headings = [...document.querySelectorAll('h1,h2,h3,h4')].filter(vis)
    .map((h) => h.tagName + ' ' + one(h.textContent).slice(0, 160));
  const code = [...document.querySelectorAll('pre')].map((e) => (e.textContent || '').replace(/\s+$/g, '').slice(0, 8000))
    .filter((t) => t.trim());
  const tables = [...document.querySelectorAll('table')].map((t) => [...t.querySelectorAll('tr')]
    .map((tr) => [...tr.children].map((c) => one(c.textContent).slice(0, 240)).join(' | ')).slice(0, 80));
  const links = [];
  for (const a of document.querySelectorAll('a[href]')) {
    try { const u = new URL(a.href, location.href);
      if (u.origin === location.origin) links.push(one(a.textContent).slice(0, 60) + ' -> ' + u.pathname);
    } catch (_) {}
  }
  return {text, headings, code_blocks: code, tables, links: [...new Set(links)].slice(0, 120), title: document.title};
}
""".replace("__MAX__", str(TEXT_MAX))

SCROLL_JS = """
async () => {
  for (let i = 0; i < 15; i++) { window.scrollBy(0, window.innerHeight); await new Promise((r) => setTimeout(r, 120)); }
  window.scrollTo(0, 0);
}
"""


def page_verdict(final_url: str, status: int | None, title: str, want_path: str, names: list[str]) -> tuple[str, str]:
    """(code, line) for a read of an ordinary page: ok when the browser stayed on `want_path`, wall when it was sent to the
    login, blocked on a refusal or a bot check, other for anywhere else (the studio included: a docs address that bounces to the
    studio is not the docs)."""
    code = check.classify(final_url, status, title)
    path = (urlsplit(final_url or "").path or "/").rstrip("/") or "/"
    if code == "ok" and want_path.rstrip("/") != check.STUDIO_PATH:
        code = "other"
    elif code == "other" and urlsplit(final_url or "").hostname == check.HOST and path == want_path.rstrip("/"):
        code = "ok"
    if code == "ok":
        return code, f"nexabot.id: READ {path} with the saved login (login cookie names: {', '.join(names) or 'none'})."
    if code == "wall":
        return code, ("nexabot.id: LOGIN WALL. The saved login was refused (expired, signed out, or the site wants a new "
                      "code): record it again with the login steps in ops/NEXABOT-LOGIN.md.")
    if code == "blocked":
        return code, f"nexabot.id: BLOCKED. The site answered {status or 'a check page'} (page title {title[:60]!r})."
    where = (urlsplit(final_url or "").netloc or "?") + path
    return code, f"nexabot.id: UNEXPECTED. Asked for {want_path} and the browser ended on {where}."


def merge_unique(*lists: list[str]) -> list[str]:
    out: list[str] = []
    for lst in lists:
        for x in lst:
            if x and x not in out:
                out.append(x)
    return out


def read_page(page: Any, outdir: Path, events: list[dict[str, Any]], blocked: list[str], path: str) -> dict[str, Any]:
    """Read an opened ordinary page as text: scroll once to wake lazy content, read, open (never choose in) the tabs and
    accordions the guard allows, read again, and merge. Returns the body for `build_page_report`."""
    try:
        page.evaluate(SCROLL_JS)
    except Exception:  # noqa: BLE001 - a page that will not scroll is still read
        pass
    before = page.evaluate(PAGE_TEXT_JS)
    slug = re.sub(r"[^a-z0-9]+", "-", path.lower()).strip("-") or "page"
    body = probe(page, outdir, events, blocked, full_shot=f"01-{slug}-full.png")
    after = page.evaluate(PAGE_TEXT_JS)
    extra = [ln for ln in before["text"].splitlines() if ln and ln not in after["text"]]
    text = after["text"] + ("\n" + "\n".join(extra) if extra else "")
    tables = [t for t in after["tables"]] + [t for t in before["tables"] if t not in after["tables"]]
    return {
        "page_path": path, "page_text": text[:TEXT_MAX], "headings": merge_unique(before["headings"], after["headings"]),
        "code_blocks": merge_unique(before["code_blocks"], after["code_blocks"]), "tables": tables[:40],
        "links": merge_unique(before["links"], after["links"]), "opened": body["opened"], "skipped": body["skipped"],
        "screenshots": body["screenshots"], "notes": body["notes"], "elements": [],
    }


def build_page_report(*, started: str, final_url: str, title: str, status: int | None, code: str, line: str,
                      login_names: list[str], body: dict[str, Any], events: Iterable[dict[str, Any]],
                      blocked_writes: list[str]) -> dict[str, Any]:
    """The page read as plain data, with every string redacted. `redactions` says how many strings changed."""
    parts = urlsplit(final_url)
    safe_url = f"{parts.scheme}://{parts.netloc}{parts.path}" if parts.netloc else final_url
    rep = {
        "mode": "page", "started": started, "verdict": code, "verdict_line": line, "final_url": safe_url, "first_status": status,
        "title": title, "login_cookie_names": login_names, "page_path": body.get("page_path", ""),
        "headings": body.get("headings", []), "page_text": body.get("page_text", ""), "code_blocks": body.get("code_blocks", []),
        "tables": body.get("tables", []), "links": body.get("links", []), "opened": body.get("opened", []),
        "skipped_by_guard": body.get("skipped", []), "requests": summarise_requests(events),
        "blocked_writes": sorted(set(blocked_writes)), "screenshots": body.get("screenshots", []),
        "notes": list(body.get("notes", [])),
    }
    clean, n = redact_tree(rep)
    clean["redactions"] = n
    clean["notes"].append(f"{n} secret-looking string(s) in the text were replaced with {REDACTED} before writing")
    return clean


def _fence(text: str) -> str:
    longest = max((len(m) for m in re.findall(r"`+", text)), default=0)
    return "`" * max(3, longest + 1)


def render_page_md(rep: dict[str, Any]) -> str:
    """A readable version of a page read."""
    def block(text: str) -> list[str]:
        f = _fence(text)
        return [f, text, f, ""]

    out = [f"# Nexabot page read (read-only): {rep['page_path']}", "",
           f"- Started: {rep['started']}", f"- Verdict: **{rep['verdict']}**: {rep['verdict_line']}",
           f"- Final address: `{rep['final_url']}` (first status {rep['first_status']})", f"- Page title: {rep['title']!r}",
           f"- Secret-looking strings replaced with {REDACTED}: {rep.get('redactions', 0)}", ""]
    if rep["headings"]:
        out += ["## Headings", ""] + [f"- {h}" for h in rep["headings"]] + [""]
    out += ["## Page text (everything visible, after opening tabs and accordions)", ""] + block(rep["page_text"])
    if rep["code_blocks"]:
        out += [f"## Code blocks ({len(rep['code_blocks'])})", ""]
        for n, c in enumerate(rep["code_blocks"], 1):
            out += [f"### Block {n}", ""] + block(c)
    if rep["tables"]:
        out += [f"## Tables ({len(rep['tables'])})", ""]
        for n, t in enumerate(rep["tables"], 1):
            out += [f"### Table {n}", ""] + block("\n".join(t))
    if rep["links"]:
        out += ["## Same-origin links (text -> path; none was opened)", ""] + [f"- {x}" for x in rep["links"]] + [""]
    out += ["## Menus and tabs opened (nothing was chosen or submitted)", ""]
    out += [f"- {o.get('role')}: {o.get('name') or '(no name)'}" for o in rep["opened"]] or ["- none"]
    out += ["", "## Skipped by the guard (never clicked)", ""]
    out += [f"- {s.get('role')} {s.get('name')!r}: {s.get('why')}" for s in rep["skipped_by_guard"]] or ["- none"]
    out += ["", "## Same-origin XHR / fetch calls (method, path, status; no headers, bodies or query values)", "",
            "| method | path | status | times |", "|---|---|---|---|"]
    out += [f"| {r['method']} | `{r['path']}` | {r['status']} | {r['count']} |" for r in rep["requests"]]
    out += ["", "## Writes blocked at the network (and private pages never fetched)", ""]
    out += [f"- {b}" for b in rep["blocked_writes"]] or ["- none"]
    out += ["", "## Screenshots", ""] + [f"- `{s}`" for s in rep["screenshots"]]
    out += ["", "## Notes", ""] + [f"- {n}" for n in rep["notes"]]
    return "\n".join(out) + "\n"


def run(outdir: Path, state: dict[str, Any] | None, path: str = check.STUDIO_PATH) -> tuple[int, dict[str, Any]]:
    from playwright.sync_api import sync_playwright

    global SCREENSHOTS_ON
    path = check_path(path)
    studio = path == check.STUDIO_PATH
    SCREENSHOTS_ON = studio                      # no pictures of any other page (see SCREENSHOTS_ON)
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
            resp = page.goto(check.ORIGIN + path, wait_until="domcontentloaded", timeout=45_000)
            try:
                page.wait_for_load_state("networkidle", timeout=15_000)
            except Exception:  # noqa: BLE001
                pass
            page.wait_for_timeout(2500)
            title = page.title()
            status = resp.status if resp else None
            if studio:
                code, line = check.verdict(page.url, names, status, title)
            else:
                code, line = page_verdict(page.url, status, title, path, names)
            if code != "ok":
                shot = _shot(page, outdir, "00-not-the-page.png", False)
                body: dict[str, Any] = {
                    "areas": {}, "elements": [], "opened": [], "skipped": [], "screenshots": [shot] if shot else [],
                    "notes": ["the page did not open as asked, so nothing was read"], "page_path": path}
            elif studio:
                body = probe(page, outdir, events, blocked)
            else:
                body = read_page(page, outdir, events, blocked, path)
            if studio or code != "ok":
                report = build_report(started=started, final_url=page.url, title=title, code=code, line=line, status=status,
                                      login_names=names, events=events, blocked_writes=blocked,
                                      **{k: v for k, v in body.items() if k != "page_path"})
            else:
                report = build_page_report(started=started, final_url=page.url, title=title, status=status, code=code,
                                           line=line, login_names=names, body=body, events=events, blocked_writes=blocked)
        finally:
            browser.close()
    write_reports(outdir, report, state)
    return (0 if code == "ok" else 1), report


def write_reports(outdir: Path, report: dict[str, Any], state: dict[str, Any] | None) -> None:
    """report.json and report.md: secrets redacted in the data BEFORE it is serialised, then every saved cookie value as a
    last line of defence over the text."""
    secrets = secret_values(state)
    if report.get("mode") != "page":
        report, _n = redact_tree(report)
        md = render_md(report)
    else:
        md = render_page_md(report)
    (outdir / "report.json").write_text(redact(json.dumps(report, indent=1, ensure_ascii=False), secrets), encoding="utf-8")
    (outdir / "report.md").write_text(redact(md, secrets), encoding="utf-8")


def _opt(argv: list[str], name: str) -> str:
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else ""


def main(argv: list[str]) -> int:
    args = [a for i, a in enumerate(argv[1:], 1) if not a.startswith("--") and argv[i - 1] not in ("--state", "--path")]
    if not args:
        print(__doc__)
        return 2
    try:
        path = check_path(_opt(argv, "--path"))
    except PathRefused as exc:
        print(f"Refused: {exc}")
        return 2
    state = None
    spath = _opt(argv, "--state")
    if spath:
        state = json.loads(Path(spath).read_text())
    elif os.environ.get("NEXABOT_STORAGE_STATE_B64", "").strip():
        import base64
        try:
            state = json.loads(base64.b64decode(os.environ["NEXABOT_STORAGE_STATE_B64"].strip()))
        except ValueError:
            print("NEXABOT_STORAGE_STATE_B64 is not base64 of a storage_state.json: record the login again.")
            return 2
    else:
        print("No saved login given (no --state, no NEXABOT_STORAGE_STATE_B64): opening logged out, as a test run.")
    code, rep = run(Path(args[0]), state, path)
    print(rep["verdict_line"])
    print(f"{len(rep.get('elements') or [])} controls, {len(rep['opened'])} menus/tabs opened, "
          f"{len(rep['requests'])} distinct same-origin calls, {len(rep['blocked_writes'])} writes blocked, "
          f"{len(rep['screenshots'])} screenshots -> {args[0]}")
    if rep.get("mode") == "page":
        print(f"page text {len(rep['page_text'])} characters, {len(rep['code_blocks'])} code blocks, "
              f"{len(rep['tables'])} tables, {rep.get('redactions', 0)} secret-looking strings redacted")
    if code != 0:
        print("::error::the saved login was refused: record it again (ops/NEXABOT-LOGIN.md)" if rep["verdict"] == "wall"
              else f"::error::the page did not open as expected ({rep['verdict']}): see the report")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
