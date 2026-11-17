"""ONE controlled generation in the nexabot.id Creator Studio (https://nexabot.id/video-generator), by hand only
(Wan, 17 Nov 2026: "TRY TO GENERATE VIDEO"). Guide: ops/NEXABOT-LOGIN.md. Run by the manual workflow nexabot-generate.yml:

    python -m semasa.nexabot_generate OUTDIR --prompt "..." [--orientation portrait|landscape] [--resolution 720p|1080p]
                                      [--state storage_state.json]

It spends credits (0.5 each; the studio shows an UNLIMITED badge), so nothing schedules it and nothing calls it twice. It does
exactly ONE generation per process, and writes into OUTDIR: report.json, report.md, three screenshots (before Generate, while
waiting, the result) and video.mp4 (kept under 40 MB, with an ffprobe summary in the report).

What it does, in order: open the studio with the saved login (a login wall ends the run: "the saved login was refused: record it
again"); read the balance and the Generate label; stay in Text to Video mode; pick the orientation and resolution; type the
prompt; READ the Generate label again and stop if the price is above SPEND_CAP_CREDITS (`spend_decision`); click Generate ONCE;
then wait up to 15 minutes WITHOUT clicking anything, reading the page and the job list; download the finished video with the
same browser context.

What it never does, in code:
  * click anything outside an allow-list (`click_allowed`): Text to Video (the mode), the chosen orientation, the chosen
    resolution, the prompt box and Generate, which is refused after its first click. CANCEL ALL, DELETE ALL, Choose payment
    mode, the chat, every link and every other name are refused. The module has exactly one click call, behind that check;
  * retry a click, reload, go back or navigate away. If Generate seems not to have started a job it says so and stops;
  * let a write leave the browser except the one job-creating POST: `write_allowed` lets a same-origin POST under /api/ through
    only after Generate is armed, once per path, never to a payment, wallet, credits, delete, cancel, chat or key path, and aborts
    every other write (and every write to another origin) at the network;
  * keep a cookie, a header or a token, or print a query signature: the report holds methods, paths (ids masked), statuses, the
    KEYS and shape of the job JSON (values only for a few enum-like fields such as status), and secret-looking strings are
    replaced by [REDACTED] before anything is written.
The finished video goes into the one-day artifact and nowhere else: no Telegram, no Supabase, no Import call.
"""

from __future__ import annotations

import base64
import json
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

from . import nexabot_check as check
from . import nexabot_probe as pr

SPEND_CAP_CREDITS = 1.0           # a price above this on the Generate button stops the run (the studio showed 0.5)
WAIT_SECONDS = 15 * 60            # how long to wait for the finished video
POLL_SECONDS = 10
START_EVIDENCE_SECONDS = 90       # no sign of a job by then: stop and say so (never click again)
MAX_VIDEO_BYTES = 40_000_000
MAX_POSTS = 3                     # distinct /api/ POST paths let through once Generate is armed (the job, maybe a log call)
SHAPES_MAX = 40
DEFAULT_PROMPT = ("A slow cinematic push-in on a clean laboratory bench with glassware and soft morning light, "
                  "no people, no text")
ORIENTATIONS = ("portrait", "landscape")
RESOLUTIONS = ("720p", "1080p")
MODE_NAMES = ("text to video", "start frame to video", "ingredients to video", "reference video to video")
CLICK_ROLES = ("button", "menuitem", "option", "radio", "tab", "textbox")
# a write to any path containing one of these is never sent, even under /api/
WRITE_DENY = re.compile(
    r"payment|checkout|check-out|top-?up|topup|wallet|credit|commission|delete|cancel|logout|log-out|signout|sign-out|billing|"
    r"subscri|purchase|invoice|order|refund|chat|message|api-?keys?|remove|destroy|upgrade|redeem|voucher|withdraw|transfer|"
    r"settings|password|account",
    re.IGNORECASE)
GENERATE_BAD = re.compile(r"cancel|delete|payment|choose|chat|log\s*out|buy|top\s*-?up|\ball\b", re.IGNORECASE)
STATUS_KEY = re.compile(r"status|state|phase|stage", re.IGNORECASE)
ENUM_KEY = re.compile(r"^(?:mode|type|kind|orientation|aspect\w*|ratio|resolution|quality|model|duration|format|fps|status|state|"
                      r"phase|stage)$", re.IGNORECASE)
ID_KEYS = ("id", "job_id", "jobId", "uuid", "task_id", "taskId", "generation_id", "generationId")
DONE_STATUS = frozenset({"completed", "complete", "done", "succeeded", "success", "successful", "finished", "ready"})
FAILED_STATUS = frozenset({"failed", "failure", "error", "errored", "cancelled", "canceled", "rejected", "timeout",
                           "timed_out", "expired"})
VIDEO_EXT = (".mp4", ".mov", ".webm", ".m4v")


# --- pure decisions ----------------------------------------------------------------------------------------------------------

def norm(name: str) -> str:
    """A name in lower case with its spaces collapsed and any leading icon or symbol dropped."""
    return re.sub(r"^[^\w]+", "", re.sub(r"\s+", " ", str(name or "")).strip().lower())


def _num(s: str) -> float | None:
    s = s.strip().rstrip(".,")
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+", s):
        s = s.replace(",", "")
    elif "," in s and "." not in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def parse_balance(text: str) -> float | None:
    """The credit balance from header text such as 'CREDITS 0': the number AFTER the word. None when there is none."""
    m = re.search(r"\bcredits?\s*[:=]?\s*(\d[\d.,]*)", text or "", re.IGNORECASE)
    return _num(m.group(1)) if m else None


def parse_price(label: str) -> float | None:
    """The price on a Generate button such as '0.5 CREDITS': the number BEFORE the word. None when there is none."""
    m = re.search(r"(\d[\d.,]*)\s*credits?\b", label or "", re.IGNORECASE)
    return _num(m.group(1)) if m else None


def is_unlimited(*texts: str) -> bool:
    return any("unlimited" in (t or "").lower() or "♾" in (t or "") for t in texts)


@dataclass
class SpendDecision:
    allowed: bool
    why: str
    price: float | None = None
    balance: float | None = None
    unlimited: bool = False


def spend_decision(balance_text: str, label: str, cap: float = SPEND_CAP_CREDITS) -> SpendDecision:
    """The hard spend guard, over the balance text and the Generate button's label. Stops when the price cannot be read and
    nothing says UNLIMITED, when it is above `cap` (even with an UNLIMITED badge: the badge may not cover this option), or when
    the balance is known and below the price and nothing says UNLIMITED. Pure: no page, no network."""
    price, balance, unlimited = parse_price(label), parse_balance(balance_text), is_unlimited(balance_text, label)
    base = {"price": price, "balance": balance, "unlimited": unlimited}
    if price is None and not unlimited:
        return SpendDecision(False, f"the price on the Generate button could not be read ({label.strip()[:60]!r}) and no "
                                    "UNLIMITED marker is shown", **base)
    if price is not None and price > cap:
        return SpendDecision(False, f"the Generate button shows {price:g} credits, above the cap of {cap:g} "
                                    f"(SPEND_CAP_CREDITS in nexabot_generate.py)", **base)
    if not unlimited and price is not None and balance is not None and balance < price:
        return SpendDecision(False, f"the balance is {balance:g} credits, below the price of {price:g}, and no UNLIMITED "
                                    "marker is shown", **base)
    if unlimited:
        return SpendDecision(True, "an UNLIMITED marker is shown"
                             + (f" (the button shows {price:g} credits, within the cap of {cap:g})" if price is not None else ""),
                             **base)
    return SpendDecision(True, f"{price:g} credits is within the cap of {cap:g} and the balance covers it", **base)


@dataclass
class ClickState:
    orientation: str
    resolution: str
    generate_clicks: int = 0
    menu_open: bool = False       # the mode menu is open: only its Text to Video item may be chosen


GENERATE_REST = re.compile(r"[\d.,]+|credits?|unlimited|free|video|\W+")


def is_generate_name(name: str) -> bool:
    """The Generate button: its name is 'Generate' plus at most a price, 'credits', 'unlimited', 'free' or 'video'. Any other
    word after it ('Generate all', 'Generate and pay') is some other control."""
    n = norm(name)
    return bool(re.match(r"^generate(\s|$)", n)) and not GENERATE_BAD.search(n) \
        and not GENERATE_REST.sub("", n[len("generate"):]).strip()


def click_allowed(role: str, name: str, st: ClickState) -> tuple[bool, str]:
    """(allowed, why) for clicking one control, by an ALLOW-LIST: the Text to Video mode, the chosen orientation, the chosen
    resolution, the prompt box, and Generate (only while it has not been clicked). Everything else is refused, whatever its
    name: CANCEL ALL, DELETE ALL, Choose payment mode, the chat, links, every other mode, the other orientation or resolution."""
    r, n = norm(role), norm(name)
    if r not in CLICK_ROLES:
        return False, f"role {r or '?'} is not clickable here"
    if r == "textbox":
        return True, "the prompt box"
    if is_generate_name(name):
        if st.generate_clicks >= 1:
            return False, "Generate was already clicked once in this run: never again"
        return True, "Generate, the one click of this run"
    if re.match(r"^text to video(\s|$)", n):
        return True, "the Text to Video mode"
    if any(n.startswith(m) for m in MODE_NAMES):
        if st.menu_open:
            return False, "another mode: only Text to Video may be chosen"
        return True, "the mode button, to open its menu"
    if re.match(rf"^{re.escape(st.orientation)}(\s|$)", n):
        return True, f"the {st.orientation} orientation"
    if re.match(rf"^{re.escape(st.resolution)}(\s|$)", n):
        return True, f"the {st.resolution} resolution"
    return False, f"{name.strip()[:40]!r} is not on the allow-list"


@dataclass
class GuardState:
    armed: bool = False                                  # set just before the one Generate click
    posts: set[str] = field(default_factory=set)         # POST paths already let through


def write_allowed(method: str, url: str, g: GuardState, origin: str = check.ORIGIN) -> tuple[bool, str]:
    """(allowed, why) for one network request. Reads go through (except the owner's keys page and sign-out addresses). A write is
    allowed only as the job-creating POST: same origin, a path under /api/, no payment/wallet/credits/commission/delete/cancel/
    logout/chat/key word in it, only after Generate is armed, once per path, at most MAX_POSTS paths."""
    m = method.upper()
    parts = urlsplit(url)
    if pr.private_url(url, origin):
        return False, "a private page (the account's keys, a sign-out)"
    if m in pr.SAFE_METHODS:
        return True, "a read"
    want = urlsplit(origin)
    if (parts.scheme, parts.netloc) != (want.scheme, want.netloc):
        return False, "a write to another origin"
    path = parts.path or "/"
    if not path.startswith("/api/"):
        return False, "a write outside /api/"
    if WRITE_DENY.search(path):
        return False, "a write to a payment, wallet, credits, delete, cancel, chat or key path"
    if m != "POST":
        return False, f"{m} is never sent"
    if not g.armed:
        return False, "a write before Generate was armed"
    key = pr.clean_path(url, origin) or path
    key = key.split("?")[0]
    if key in g.posts:
        return False, "this path already took its one POST"
    if len(g.posts) >= MAX_POSTS:
        return False, f"more than {MAX_POSTS} different POST paths"
    g.posts.add(key)
    return True, "the job-creating write, once"


def guard_route(g: GuardState, blocked: list[str], allowed: list[str]) -> Any:
    """A Playwright route handler over `write_allowed`: allowed requests continue, the rest are aborted and listed."""
    def handler(route: Any) -> None:
        req = route.request
        ok, why = write_allowed(req.method, req.url, g)
        parts = urlsplit(req.url)
        tag = f"{req.method.upper()} {parts.netloc}{pr.clean_path(req.url, f'{parts.scheme}://{parts.netloc}') or ''}"
        if not ok:
            if req.method.upper() not in pr.SAFE_METHODS or "private" in why:
                blocked.append(f"{tag.split('?')[0]} ({why})")
            route.abort()
            return
        if req.method.upper() not in pr.SAFE_METHODS:
            allowed.append(tag.split("?")[0])
        route.fallback()
    return handler


# --- reading the job JSON: shapes, statuses, video links --------------------------------------------------------------------

def shape_of(obj: Any, key: str = "", depth: int = 0) -> Any:
    """The structure of a JSON value without its data: field names and types. Short enum-like strings (status, mode,
    orientation, resolution ...) keep their value, because the status values ARE the finding; every other string is just 'str'."""
    if depth > 6:
        return "..."
    if isinstance(obj, dict):
        return {str(k)[:40]: shape_of(v, str(k), depth + 1) for k, v in list(obj.items())[:40]}
    if isinstance(obj, list):
        return {"list": len(obj), "item": shape_of(obj[0], key, depth + 1) if obj else None}
    if isinstance(obj, bool):
        return "bool"
    if isinstance(obj, (int, float)):
        return "number"
    if obj is None:
        return "null"
    if isinstance(obj, str):
        if ENUM_KEY.match(key) and len(obj) <= 32 and re.fullmatch(r"[\w .:/\-]+", obj):
            return obj
        return "str"
    return type(obj).__name__


def walk_dicts(obj: Any, in_list: bool = False) -> list[tuple[dict[str, Any], bool]]:
    out: list[tuple[dict[str, Any], bool]] = []
    if isinstance(obj, dict):
        out.append((obj, in_list))
        for v in obj.values():
            out += walk_dicts(v, False)
    elif isinstance(obj, list):
        for v in obj:
            out += walk_dicts(v, True)
    return out


def rec_id(d: dict[str, Any]) -> str:
    for k in ID_KEYS:
        if d.get(k) not in (None, ""):
            return str(d[k])
    return ""


def status_of(d: dict[str, Any]) -> str:
    for k, v in d.items():
        if STATUS_KEY.search(str(k)) and isinstance(v, str) and len(v) <= 32:
            return v
    return ""


def classify_status(s: str) -> str:
    s = norm(s).replace(" ", "_")
    return "done" if s in DONE_STATUS else "failed" if s in FAILED_STATUS else "pending" if s else ""


def find_video_urls(obj: Any, key: str = "") -> list[str]:
    """Video links in a JSON value, best first: an address ending .mp4/.mov/.webm, then one under a key named like video, mp4,
    download, output or result (never a thumbnail, poster, cover or image)."""
    first: list[str] = []
    second: list[str] = []

    def go(o: Any, k: str) -> None:
        if isinstance(o, dict):
            for kk, v in o.items():
                go(v, str(kk))
        elif isinstance(o, list):
            for v in o:
                go(v, k)
        elif isinstance(o, str) and re.match(r"^https?://", o):
            path = urlsplit(o).path.lower()
            if path.endswith(VIDEO_EXT):
                first.append(o)
            elif re.search(r"video|mp4|download|output|result", k, re.IGNORECASE) \
                    and not re.search(r"thumb|poster|cover|image|img|avatar", k, re.IGNORECASE):
                second.append(o)

    go(obj, key)
    return list(dict.fromkeys(first + second))


def mask_url(url: str) -> str:
    """host + path with id-like segments masked and no query: a signature never reaches the report."""
    p = urlsplit(url)
    segs = []
    for seg in p.path.split("/"):
        stem, dot, ext = seg.rpartition(".")
        if dot and f".{ext.lower()}" in VIDEO_EXT:
            segs.append((":id" if pr.id_like(stem) else stem) + "." + ext)
        else:
            segs.append(":id" if pr.id_like(seg) else seg)
    return f"{p.scheme}://{p.hostname or ''}{'/'.join(segs)}" + (" (query signature dropped)" if p.query else "")


class Tracker:
    """What the job JSON says. `feed` takes a parsed response; records seen before Generate (`live` False) are the baseline, so
    an older job in the list is never taken for ours."""

    def __init__(self) -> None:
        self.live = False
        self.baseline: set[str] = set()
        self.records: dict[str, dict[str, Any]] = {}
        self.shapes: list[dict[str, Any]] = []
        self.statuses: list[str] = []
        self._seen: set[str] = set()

    def feed(self, method: str, path: str, status: int | None, obj: Any, request_obj: Any = None) -> None:
        shape = shape_of(obj)
        sig = f"{method} {path} {status} {json.dumps(shape, sort_keys=True)}"
        if sig not in self._seen and len(self.shapes) < SHAPES_MAX:
            self._seen.add(sig)
            row: dict[str, Any] = {"method": method, "path": path, "status": status, "shape": shape,
                                   "has_video_url": bool(find_video_urls(obj))}
            if request_obj is not None:
                row["request_shape"] = shape_of(request_obj)
            self.shapes.append(row)
        cands = walk_dicts(obj)
        with_id = [d for d, _ in cands if status_of(d) and rec_id(d)]
        pool = with_id or [d for d, in_list in cands if in_list and status_of(d)]
        for d in pool:
            ident = rec_id(d) or json.dumps(d, sort_keys=True, default=str)[:300]
            if not self.live:
                self.baseline.add(ident)
                continue
            if ident in self.baseline:
                continue
            st = status_of(d)
            rec = self.records.setdefault(ident, {"status": st, "urls": []})
            rec["status"] = st
            rec["urls"] = list(dict.fromkeys(rec["urls"] + find_video_urls(d)))
            if st and st not in self.statuses:
                self.statuses.append(st)

    def outcome(self) -> tuple[str, str, str]:
        """('done'|'failed'|'pending'|'none', status text, video url or '') over the new records."""
        for rec in self.records.values():
            if classify_status(rec["status"]) == "failed":
                return "failed", rec["status"], ""
        for rec in self.records.values():
            if classify_status(rec["status"]) == "done":
                return "done", rec["status"], (rec["urls"] or [""])[0]
        if self.records:
            return "pending", next(iter(self.records.values()))["status"], ""
        return "none", "", ""


# --- in the page -------------------------------------------------------------------------------------------------------------

# Reads the page and changes nothing.
STATE_JS = r"""
() => {
  const vis = (e) => { const r = e.getBoundingClientRect(), s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const one = (t) => (t || '').replace(/\s+/g, ' ').trim();
  const nm = (b) => one(b.getAttribute('aria-label') || b.innerText || '').replace(/^[^\w]+/, '');
  const body = document.body.innerText || '';
  const header = [...document.querySelectorAll('header')].filter(vis).map((e) => e.innerText || '').join('\n');
  const btns = [...document.querySelectorAll('button, [role=button]')].filter(vis);
  const attrs = (b) => ({pressed: b.getAttribute('aria-pressed') || '', checked: b.getAttribute('aria-checked') || '',
    selected: b.getAttribute('aria-selected') || '', state: b.getAttribute('data-state') || '',
    disabled: !!(b.disabled || b.getAttribute('aria-disabled') === 'true')});
  const pick = (re) => { const b = btns.find((x) => re.test(nm(x)));
    return b ? Object.assign({name: nm(b).slice(0, 60)}, attrs(b)) : null; };
  const gen = btns.find((b) => /^\s*generate(\s|$)/i.test(nm(b)) && !/cancel|delete|payment|choose/i.test(nm(b)));
  const box = document.querySelector('textarea, input[type=text]');
  return {
    header: header.slice(0, 600), balance_text: (header || body.slice(0, 1500)).slice(0, 1500),
    generate: gen ? Object.assign({label: one((gen.getAttribute('aria-label') || '') + ' ' + (gen.innerText || ''))
      .slice(0, 160)}, attrs(gen)) : null,
    options: {landscape: pick(/^landscape/i), portrait: pick(/^portrait/i), r720: pick(/^720p/i), r1080: pick(/^1080p/i)},
    mode: pick(/^(text to video|start frame to video|ingredients to video|reference video to video)/i),
    has_prompt: !!box, no_generations: /no generations yet/i.test(body),
    videos: [...document.querySelectorAll('video')]
      .map((v) => v.currentSrc || v.src || ((v.querySelector('source') || {}).src || '')).filter(Boolean),
    results_text: ((body.match(/RESULTS[\s\S]{0,500}/) || [''])[0]).replace(/\s+/g, ' ').slice(0, 400),
  };
}
"""


def read_state(page: Any) -> dict[str, Any]:
    return page.evaluate(STATE_JS)


def first_visible(loc: Any) -> Any:
    for i in range(min(loc.count(), 8)):
        if loc.nth(i).is_visible():
            return loc.nth(i)
    return None


def name_of(el: Any) -> str:
    aria = (el.get_attribute("aria-label") or "").strip()
    if aria:
        return aria
    try:
        text = el.inner_text()
    except Exception:  # noqa: BLE001
        text = ""
    return (text.strip().splitlines() or [""])[0].strip()


@dataclass
class Recorder:
    guard: GuardState = field(default_factory=GuardState)
    events: list[dict[str, Any]] = field(default_factory=list)
    captured: list[Any] = field(default_factory=list)       # responses waiting to be read
    blocked: list[str] = field(default_factory=list)
    allowed: list[str] = field(default_factory=list)
    list_urls: list[str] = field(default_factory=list)       # raw job-list addresses: used to poll, never reported
    getter: Any = None                                       # a GET function for tests; None means the context's own


def attach(ctx: Any, rec: Recorder, fake: Any = None) -> None:
    """Wire the guard and the call recorder to a browser context. `fake` (tests) is registered first, so the guard runs first."""
    if fake is not None:
        ctx.route("**/*", fake)
    ctx.route("**/*", guard_route(rec.guard, rec.blocked, rec.allowed))

    def on_response(r: Any) -> None:
        req = r.request
        rt = str(req.resource_type or "").lower()
        rec.events.append({"method": req.method, "url": r.url, "status": r.status, "resource_type": rt})
        if rt in ("xhr", "fetch") and pr.clean_path(r.url) and urlsplit(r.url).path.startswith("/api/"):
            rec.captured.append(r)
            if req.method.upper() == "GET" and urlsplit(r.url).path.startswith("/api/v1/jobs"):
                rec.list_urls.append(r.url)

    ctx.on("response", on_response)


def absorb(rec: Recorder, tr: Tracker) -> int:
    """Read every captured response that carries JSON into the tracker. Returns how many were read."""
    n = 0
    while rec.captured:
        r = rec.captured.pop(0)
        try:
            if "json" not in (r.headers.get("content-type") or "").lower():
                continue
            obj = r.json()
        except Exception:  # noqa: BLE001 - a body that is gone or not JSON is skipped
            continue
        method = r.request.method.upper()
        req_obj = None
        if method == "POST":
            try:
                req_obj = json.loads(r.request.post_data or "null")
            except Exception:  # noqa: BLE001
                req_obj = None
        tr.feed(method, pr.clean_path(r.url) or "", r.status, obj, req_obj)
        n += 1
    return n


def poll_job_list(ctx: Any, rec: Recorder, tr: Tracker) -> None:
    """Ask for the job list again with the same session (a GET, nothing else): the address the page itself used if it was seen."""
    url = rec.list_urls[-1] if rec.list_urls else check.ORIGIN + "/api/v1/jobs?limit=20"
    ok, _why = write_allowed("GET", url, rec.guard)
    if not ok:
        return
    try:
        resp = (rec.getter or ctx.request.get)(url, timeout=20_000)
        rec.events.append({"method": "GET", "url": url, "status": resp.status, "resource_type": "fetch"})
        if resp.ok and "json" in (resp.headers.get("content-type") or "").lower():
            tr.feed("GET", pr.clean_path(url) or "", resp.status, resp.json())
    except Exception:  # noqa: BLE001 - one poll that fails is not the end
        pass


def ffprobe_summary(path: Path) -> dict[str, Any]:
    """Duration, size, resolution and codecs as ffprobe reads them; {'error': ...} when it cannot."""
    exe = shutil.which("ffprobe")
    if not exe:
        return {"error": "ffprobe is not installed on this machine"}
    try:
        p = subprocess.run([exe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                           capture_output=True, text=True, timeout=120)
        j = json.loads(p.stdout or "{}")
    except Exception as exc:  # noqa: BLE001
        return {"error": f"ffprobe failed: {str(exc)[:100]}"}
    streams = j.get("streams") or []
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if not v:
        return {"error": "ffprobe found no picture track in the file"}
    fmt = j.get("format") or {}
    try:
        dur = float(fmt.get("duration") or v.get("duration") or 0)
    except (TypeError, ValueError):
        dur = 0.0
    return {"format": str(fmt.get("format_name") or ""), "duration_s": round(dur, 2),
            "bytes": int(fmt.get("size") or path.stat().st_size),
            "width": int(v.get("width") or 0), "height": int(v.get("height") or 0), "vcodec": str(v.get("codec_name") or ""),
            "pix_fmt": str(v.get("pix_fmt") or ""), "fps": str(v.get("r_frame_rate") or ""),
            "acodec": str((a or {}).get("codec_name") or ""), "has_audio": a is not None}


BLOB_JS = r"""
async ([src, cap]) => {
  const r = await fetch(src); const b = await r.blob();
  if (b.size > cap) return {size: b.size, b64: ''};
  const buf = new Uint8Array(await b.arrayBuffer()); let s = ''; const step = 0x8000;
  for (let i = 0; i < buf.length; i += step) s += String.fromCharCode.apply(null, buf.subarray(i, i + step));
  return {size: b.size, b64: btoa(s)};
}
"""


def download_video(ctx: Any, page: Any, url: str, dest: Path, cap: int = MAX_VIDEO_BYTES, getter: Any = None) -> dict[str, Any]:
    """Fetch the finished video with the page's own browser context (so the session applies) and save it as `dest` when it is an
    MP4 under `cap` bytes. Never raises; the result says what happened. The address is reported masked, never with its query."""
    out: dict[str, Any] = {"url": mask_url(url) if not url.startswith("blob:") else "blob: (read inside the page)",
                           "saved": False, "bytes": 0, "reason": ""}
    try:
        if url.startswith("blob:"):
            got = page.evaluate(BLOB_JS, [url, cap])
            out["bytes"] = int(got.get("size") or 0)
            if not got.get("b64"):
                out["reason"] = f"larger than {cap:,} bytes: not saved"
                return out
            body = base64.b64decode(got["b64"])
        else:
            resp = (getter or ctx.request.get)(urljoin(page.url, url), timeout=180_000)
            out["status"] = resp.status
            if not resp.ok:
                out["reason"] = f"the download answered {resp.status}"
                return out
            try:
                declared = int(resp.headers.get("content-length") or 0)
            except ValueError:
                declared = 0
            if declared > cap:
                out["bytes"], out["reason"] = declared, f"larger than {cap:,} bytes: size recorded, not saved"
                return out
            body = resp.body()
            out["bytes"] = len(body)
            if len(body) > cap:
                out["reason"] = f"larger than {cap:,} bytes: size recorded, not saved"
                return out
        if body[4:8] != b"ftyp":
            out["reason"] = f"the file is not an MP4 (starts with {body[:8].hex()}): not saved as video.mp4"
            return out
        dest.write_bytes(body)
        out["saved"] = True
    except Exception as exc:  # noqa: BLE001
        out["reason"] = f"the download failed: {str(exc).splitlines()[0][:120] if str(exc) else type(exc).__name__}"
    return out


def shot(page: Any, outdir: Path, name: str) -> str:
    return pr._shot(page, outdir, name, False)


# --- the run ------------------------------------------------------------------------------------------------------------------

@dataclass
class Config:
    prompt: str
    orientation: str = "portrait"
    resolution: str = "720p"
    wait_s: float = WAIT_SECONDS
    poll_s: float = POLL_SECONDS
    start_s: float = START_EVIDENCE_SECONDS
    cap: float = SPEND_CAP_CREDITS


def check_inputs(prompt: str, orientation: str, resolution: str) -> str:
    """The prompt, stripped, or ValueError."""
    p = (prompt or "").strip()
    if not 3 <= len(p) <= 800 or re.search(r"[\x00-\x08\x0b-\x1f]", p):
        raise ValueError("the prompt must be 3 to 800 characters of plain text")
    if orientation not in ORIENTATIONS:
        raise ValueError(f"orientation must be one of {', '.join(ORIENTATIONS)}")
    if resolution not in RESOLUTIONS:
        raise ValueError(f"resolution must be one of {', '.join(RESOLUTIONS)}")
    return p


class Clicker:
    """The only way this module clicks: every click is asked of `click_allowed` first, and a Generate click is counted BEFORE it
    is made, so even one that fails is never repeated."""

    def __init__(self, state: ClickState) -> None:
        self.state = state
        self.clicked: list[str] = []
        self.refused: list[str] = []

    def click(self, el: Any, role: str) -> bool:
        name = name_of(el)
        ok, why = click_allowed(role, name, self.state)
        if not ok:
            self.refused.append(f"{role} {name[:40]!r}: {why}")
            return False
        if is_generate_name(name):
            self.state.generate_clicks += 1
        self.clicked.append(f"{role}: {name[:40]}")
        el.click(timeout=8000)
        return True


def ensure_text_mode(page: Any, ck: Clicker, R: dict[str, Any]) -> bool:
    """Stay in Text to Video. Already there (the mode button reads it and the prompt box is shown): nothing is clicked."""
    st = read_state(page)
    if st["mode"] and norm(st["mode"]["name"]).startswith("text to video") and st["has_prompt"]:
        R["notes"].append("the studio was already in Text to Video mode: no mode control was clicked")
        return True
    trigger = None
    for m in MODE_NAMES:
        trigger = first_visible(page.get_by_role("button", name=re.compile(rf"^\W*{re.escape(m)}", re.IGNORECASE)))
        if trigger:
            break
    if not trigger or not ck.click(trigger, "button"):
        R["problems"].append("the mode button could not be found or clicked")
        return False
    ck.state.menu_open = True
    page.wait_for_timeout(600)
    item = None
    for role in ("menuitem", "option", "button"):
        item = first_visible(page.get_by_role(role, name=re.compile(r"^\W*text to video", re.IGNORECASE)))
        if item:
            ck.click(item, role)
            break
    ck.state.menu_open = False
    page.wait_for_timeout(600)
    st = read_state(page)
    ok = bool(st["mode"] and norm(st["mode"]["name"]).startswith("text to video") and st["has_prompt"])
    if not ok:
        R["problems"].append("the studio did not end up in Text to Video mode")
    return ok


def pick_option(page: Any, ck: Clicker, word: str, R: dict[str, Any]) -> bool:
    el = first_visible(page.get_by_role("button", name=re.compile(rf"^\W*{re.escape(word)}(\s|$)", re.IGNORECASE)))
    if not el:
        R["problems"].append(f"the {word} button was not found")
        return False
    if not ck.click(el, "button"):
        R["problems"].append(f"the {word} button was refused by the click allow-list")
        return False
    page.wait_for_timeout(400)
    return True


def type_prompt(page: Any, prompt: str, R: dict[str, Any]) -> bool:
    box = first_visible(page.get_by_placeholder(re.compile(r"describe your video", re.IGNORECASE)))
    if not box:
        R["problems"].append("the prompt box was not found")
        return False
    box.fill(prompt)
    page.wait_for_timeout(500)
    gen = first_visible(page.get_by_role("button", name=re.compile(r"^\W*generate(\s|$)", re.IGNORECASE)))
    if gen is not None and not gen.is_enabled():
        box.fill("")
        box.press_sequentially(prompt, delay=15)         # typed key by key, in case the page ignores a bulk fill
        page.wait_for_timeout(800)
    return True


def option_states(page: Any) -> dict[str, Any]:
    return {k: v for k, v in read_state(page)["options"].items() if v}


def drive(ctx: Any, page: Any, rec: Recorder, cfg: Config, outdir: Path) -> dict[str, Any]:
    """The one generation, on an open studio. Returns the report body (plain data)."""
    R: dict[str, Any] = {"outcome": "not_run", "outcome_line": "", "problems": [], "notes": [], "screenshots": [],
                         "clicked": [], "refused_clicks": [], "generate_clicks": 0}
    t_start = time.monotonic()
    ck = Clicker(ClickState(cfg.orientation, cfg.resolution))
    tr = Tracker()

    def finish(outcome: str, line: str) -> dict[str, Any]:
        R["outcome"], R["outcome_line"] = outcome, line
        R["clicked"], R["refused_clicks"], R["generate_clicks"] = ck.clicked, ck.refused, ck.state.generate_clicks
        R["total_s"] = round(time.monotonic() - t_start, 1)
        R["job_shapes"] = tr.shapes
        R["statuses_seen"] = tr.statuses
        R["writes_allowed"] = sorted(set(rec.allowed))
        R["blocked_writes"] = sorted(set(rec.blocked))
        try:                                          # the balance and the label once more, for the report
            after = read_state(page)
            R["balance_text_after"] = " | ".join(x.strip() for x in after["balance_text"].splitlines() if x.strip())[:200]
            R["balance_after"] = parse_balance(after["balance_text"])
            R["generate_label_after"] = (after["generate"] or {}).get("label", "")
        except Exception:  # noqa: BLE001
            R["notes"].append("the balance could not be read again at the end")
        return R

    st0 = read_state(page)
    R["balance_text_before"] = " | ".join(x.strip() for x in st0["balance_text"].splitlines() if x.strip())[:200]
    R["balance_before"] = parse_balance(st0["balance_text"])
    R["unlimited_before"] = is_unlimited(st0["balance_text"], (st0["generate"] or {}).get("label", ""))
    R["generate_label_before"] = (st0["generate"] or {}).get("label", "")
    if not st0["generate"]:
        R["problems"].append("no Generate button was found on the studio page")
        s = shot(page, outdir, "01-before-generate.png")
        R["screenshots"] += [s] if s else []
        return finish("stopped", "the Generate button was not found: nothing was clicked")

    if not (ensure_text_mode(page, ck, R) and pick_option(page, ck, cfg.orientation, R)
            and pick_option(page, ck, cfg.resolution, R) and type_prompt(page, cfg.prompt, R)):
        s = shot(page, outdir, "01-before-generate.png")
        R["screenshots"] += [s] if s else []
        return finish("stopped", "the form could not be set up as asked: Generate was NOT clicked")

    st1 = read_state(page)
    R["options_selected_attributes"] = {k: {a: v for a, v in o.items() if a in ("pressed", "checked", "selected", "state") and v}
                                        for k, o in st1["options"].items() if o}
    label = (st1["generate"] or {}).get("label", "")
    R["generate_label_ready"] = label
    dec = spend_decision(st1["balance_text"], label, cfg.cap)
    R["spend_guard"] = {"allowed": dec.allowed, "why": dec.why, "price": dec.price, "balance": dec.balance,
                        "unlimited": dec.unlimited, "cap": cfg.cap}
    s = shot(page, outdir, "01-before-generate.png")
    R["screenshots"] += [s] if s else []
    if not dec.allowed:
        return finish("stopped_spend_guard", f"stopped by the spend guard, Generate was NOT clicked: {dec.why}")
    if st1["generate"] and st1["generate"]["disabled"]:
        R["problems"].append("the Generate button stayed disabled after the prompt was typed")
        return finish("stopped", "the Generate button is disabled: Generate was NOT clicked")

    poll_job_list(ctx, rec, tr)                       # make sure the list was read once BEFORE Generate
    absorb(rec, tr)                                   # what the job list held BEFORE: never taken for ours
    base_videos = set(st1["videos"])
    base_empty = bool(st1["no_generations"])
    tr.live = True
    gen = first_visible(page.get_by_role("button", name=re.compile(r"^\W*generate(\s|$)", re.IGNORECASE)))
    if gen is None:
        R["problems"].append("the Generate button could not be located for the click")
        return finish("stopped", "Generate was NOT clicked: its button could not be located")
    rec.guard.armed = True
    t0 = time.monotonic()
    clicked = ck.click(gen, "button")
    if not clicked:
        return finish("stopped", "Generate was refused by the click allow-list and NOT clicked")

    started = False
    n_shot = 0
    next_shot = t0
    url = ""
    final_status = ""
    verdict = "none"
    done_polls = 0
    page.wait_for_timeout(1500)
    while True:
        absorb(rec, tr)
        poll_job_list(ctx, rec, tr)
        absorb(rec, tr)
        st = read_state(page)
        verdict, final_status, url = tr.outcome()
        new_videos = [v for v in st["videos"] if v not in base_videos]
        if not started and (tr.records or rec.allowed or (base_empty and not st["no_generations"])):
            started = True
            R["seconds_to_start_evidence"] = round(time.monotonic() - t0, 1)
        if started and verdict in ("none", "pending") and time.monotonic() >= next_shot and n_shot < 3:
            s = shot(page, outdir, "02-waiting.png" if n_shot == 0 else f"02-waiting-{n_shot + 1}.png")
            R["screenshots"] += [s] if s else []
            n_shot += 1
            next_shot = time.monotonic() + 300
        if verdict == "failed":
            break
        if verdict == "done" and (url or new_videos):
            url = url or new_videos[0]
            break
        if new_videos and verdict in ("none", "pending", "done"):
            url = new_videos[0]
            R["notes"].append("the video appeared in the page before the job JSON said it was done")
            break
        done_polls += 1 if verdict == "done" else 0
        if done_polls >= 6:
            break                                     # done for a minute and still no video address: stop waiting
        elapsed = time.monotonic() - t0
        if not started and elapsed >= cfg.start_s:
            break
        if elapsed >= cfg.wait_s:
            break
        page.wait_for_timeout(int(cfg.poll_s * 1000))

    R["seconds_to_ready"] = round(time.monotonic() - t0, 1)
    R["job_final_status"] = final_status
    if verdict == "failed":
        s = shot(page, outdir, "03-result.png")
        R["screenshots"] += [s] if s else []
        R["problems"].append(f"the job ended with status {final_status!r}")
        return finish("failed", f"the job failed (status {final_status!r}); nothing was retried")
    if not started:
        s = shot(page, outdir, "03-result.png")
        R["screenshots"] += [s] if s else []
        R["problems"].append("no sign that Generate started a job (no job in the list, no allowed POST, the results column "
                             "unchanged): Generate was NOT clicked again")
        return finish("not_started", "Generate was clicked once and no job seems to have started: not clicked again, "
                                     "check the studio by hand before running this again")
    if not url:
        s = shot(page, outdir, "03-result.png")
        R["screenshots"] += [s] if s else []
        R["problems"].append("no finished video within the wait" if verdict != "done"
                             else "the job says done but no video address was found in the JSON or the page")
        return finish("timeout" if verdict != "done" else "no_video_url",
                      f"no video within {int(cfg.wait_s)} seconds (last status {final_status or 'none'!r}): nothing was clicked, "
                      "the job may still finish in the studio")
    s = shot(page, outdir, "03-result.png")
    R["screenshots"] += [s] if s else []
    dl = download_video(ctx, page, url, outdir / "video.mp4", getter=rec.getter)
    R["video"] = dl
    if dl["saved"]:
        R["ffprobe"] = ffprobe_summary(outdir / "video.mp4")
        if "error" in R["ffprobe"]:
            R["problems"].append(R["ffprobe"]["error"])
    else:
        R["problems"].append(dl["reason"] or "the video was not saved")
    return finish("generated" if dl["saved"] else "generated_not_saved",
                  f"the video is ready after {R['seconds_to_ready']:g} seconds"
                  + ("" if dl["saved"] else f" but was not saved: {dl['reason']}"))


def build_report(*, started: str, final_url: str, title: str, login_names: list[str], cfg: Config, body: dict[str, Any],
                 events: list[dict[str, Any]]) -> dict[str, Any]:
    """The report as plain data, redacted. Calls are method + path + status only."""
    parts = urlsplit(final_url)
    rep = {"started": started, "final_url": f"{parts.scheme}://{parts.netloc}{parts.path}" if parts.netloc else final_url,
           "title": title, "login_cookie_names": login_names,
           "inputs": {"prompt": cfg.prompt, "orientation": cfg.orientation, "resolution": cfg.resolution,
                      "spend_cap_credits": cfg.cap, "wait_seconds": cfg.wait_s},
           "requests": pr.summarise_requests(events), **body}
    clean, n = redact_report(rep)
    return clean | {"redactions": n}


def redact_report(rep: dict[str, Any]) -> tuple[dict[str, Any], int]:
    return pr.redact_tree(rep)


def fmt(v: Any) -> str:
    return "unknown" if v is None else f"{v:g}" if isinstance(v, float) else str(v)


def render_md(rep: dict[str, Any]) -> str:
    inp = rep["inputs"]
    out = ["# Nexabot generate (ONE controlled generation)", "",
           f"- Started: {rep['started']}", f"- Outcome: **{rep['outcome']}**: {rep['outcome_line']}",
           f"- Final address: `{rep['final_url']}`", f"- Prompt: {inp['prompt']!r}",
           f"- Orientation / resolution: {inp['orientation']} / {inp['resolution']}",
           f"- Spend cap: {inp['spend_cap_credits']:g} credits per generation (SPEND_CAP_CREDITS)",
           f"- Generate clicked: **{rep.get('generate_clicks', 0)}** time(s)",
           f"- Time: {rep.get('seconds_to_ready', 'n/a')} s from the click to the result; {rep.get('total_s', 'n/a')} s in all",
           f"- Secret-looking strings replaced with {pr.REDACTED}: {rep.get('redactions', 0)}", "",
           "## Balance and the Generate button", "",
           f"- Balance text before: {rep.get('balance_text_before', '')!r} (credits {fmt(rep.get('balance_before'))}, "
           f"unlimited marker: {rep.get('unlimited_before')})",
           f"- Balance text after: {rep.get('balance_text_after', 'not read')!r} (credits {fmt(rep.get('balance_after'))})",
           f"- Generate label before: {rep.get('generate_label_before', '')!r}",
           f"- Generate label with the prompt, orientation and resolution set: {rep.get('generate_label_ready', 'not read')!r}",
           f"- Generate label after: {rep.get('generate_label_after', 'not read')!r}"]
    sg = rep.get("spend_guard")
    if sg:
        out.append(f"- Spend guard: **{'passed' if sg['allowed'] else 'STOPPED'}**: {sg['why']}")
    if rep.get("options_selected_attributes") is not None:
        shown = rep["options_selected_attributes"] or "none (see the screenshot)"
        out.append(f"- Selected-state attributes the page exposes for the options: {shown}")
    out += ["", "## Clicks (allow-list: Text to Video, the orientation, the resolution, the prompt box, Generate once)", ""]
    out += [f"- clicked: {c}" for c in rep.get("clicked", [])] or ["- nothing was clicked"]
    out += [f"- refused: {c}" for c in rep.get("refused_clicks", [])]
    out += ["", "## Job", "", f"- Final status: {rep.get('job_final_status') or 'none seen'!r}",
            f"- Status values seen, in order: {', '.join(rep.get('statuses_seen') or []) or 'none'}"]
    v = rep.get("video")
    if v:
        saved = "yes, saved as video.mp4" if v["saved"] else "NO"
        out += [f"- Video address (query dropped): `{v['url']}`",
                f"- Downloaded: {saved} ({v['bytes']:,} bytes){' - ' + v['reason'] if v['reason'] else ''}"]
    ff = rep.get("ffprobe")
    if ff:
        out += ["- ffprobe: " + (ff["error"] if "error" in ff else
                                 f"{ff['width']}x{ff['height']}, {ff['duration_s']} s, {ff['bytes']:,} bytes, {ff['format']}, "
                                 f"video {ff['vcodec']} {ff['pix_fmt']} {ff['fps']}, audio {ff['acodec'] or 'none'}")]
    out += ["", "## Job JSON shapes (field names and types; values only for status-like fields)", ""]
    for s in rep.get("job_shapes", []):
        out += [f"### {s['method']} `{s['path']}` -> {s['status']} (video address in it: {s['has_video_url']})", "", "```json",
                json.dumps(s["shape"], indent=1, ensure_ascii=False), "```", ""]
        if s.get("request_shape") is not None:
            out += ["Request body shape:", "", "```json", json.dumps(s["request_shape"], indent=1, ensure_ascii=False), "```", ""]
    out += ["## Every same-origin XHR / fetch call (method, path, status; no headers, bodies or query values)", "",
            "| method | path | status | times |", "|---|---|---|---|"]
    out += [f"| {r['method']} | `{r['path']}` | {r['status']} | {r['count']} |" for r in rep["requests"]]
    out += ["", "## Writes", "", "Let through (the job-creating POST):"]
    out += [f"- {w}" for w in rep.get("writes_allowed", [])] or ["- none"]
    out += ["", "Aborted at the network:"] + ([f"- {w}" for w in rep.get("blocked_writes", [])] or ["- none"])
    out += ["", "## What did NOT work", ""] + ([f"- {p}" for p in rep.get("problems", [])] or ["- nothing went wrong"])
    out += ["", "## Screenshots", ""] + [f"- `{s}`" for s in rep.get("screenshots", [])]
    out += ["", "## Notes", ""] + [f"- {n}" for n in rep.get("notes", [])]
    return "\n".join(out) + "\n"


def run(outdir: Path, state: dict[str, Any] | None, cfg: Config, fake: Any = None,
        getter: Any = None) -> tuple[int, dict[str, Any]]:
    """Open the studio and make the one generation. `fake` and `getter` are for tests only: a route handler and a GET function
    standing in for the network."""
    from playwright.sync_api import sync_playwright

    outdir.mkdir(parents=True, exist_ok=True)
    started = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    names = check.login_cookie_names(state or {})
    rec = Recorder(getter=getter)
    with sync_playwright() as pw:
        browser = check.launch_browser(pw)
        try:
            ctx = browser.new_context(storage_state=state, locale="en-MY", timezone_id="Asia/Kuala_Lumpur",
                                      viewport={"width": 1366, "height": 900})
            attach(ctx, rec, fake)
            page = ctx.new_page()
            page.on("dialog", lambda d: d.dismiss())             # a confirm() is never accepted
            resp = page.goto(check.STUDIO_URL, wait_until="domcontentloaded", timeout=45_000)
            try:
                page.wait_for_load_state("networkidle", timeout=15_000)
            except Exception:  # noqa: BLE001
                pass
            page.wait_for_timeout(2500)
            title = page.title()
            code, line = check.verdict(page.url, names, resp.status if resp else None, title)
            if code != "ok":
                s = shot(page, outdir, "00-not-the-studio.png")
                body: dict[str, Any] = {
                    "outcome": "login_refused" if code == "wall" else "not_the_studio", "outcome_line": line, "problems": [line],
                    "notes": ["the studio did not open, so nothing was clicked and nothing was generated"],
                    "screenshots": [s] if s else [], "clicked": [], "refused_clicks": [], "generate_clicks": 0,
                    "job_shapes": [], "statuses_seen": [], "writes_allowed": [], "blocked_writes": sorted(set(rec.blocked))}
            else:
                body = drive(ctx, page, rec, cfg, outdir)
            report = build_report(started=started, final_url=page.url, title=title, login_names=names, cfg=cfg, body=body,
                                  events=rec.events)
        finally:
            browser.close()
    write_reports(outdir, report, state)
    ok = report["outcome"] == "generated"
    return (0 if ok else 1), report


def write_reports(outdir: Path, report: dict[str, Any], state: dict[str, Any] | None) -> None:
    secrets = pr.secret_values(state)
    (outdir / "report.json").write_text(pr.redact(json.dumps(report, indent=1, ensure_ascii=False), secrets), encoding="utf-8")
    (outdir / "report.md").write_text(pr.redact(render_md(report), secrets), encoding="utf-8")


def main(argv: list[str]) -> int:
    opts = ("--prompt", "--orientation", "--resolution", "--state")
    args = [a for i, a in enumerate(argv[1:], 1) if not a.startswith("--") and argv[i - 1] not in opts]
    if not args:
        print(__doc__)
        return 2
    try:
        prompt = check_inputs(pr._opt(argv, "--prompt") or DEFAULT_PROMPT, pr._opt(argv, "--orientation") or "portrait",
                              pr._opt(argv, "--resolution") or "720p")
    except ValueError as exc:
        print(f"Refused: {exc}")
        return 2
    cfg = Config(prompt, pr._opt(argv, "--orientation") or "portrait", pr._opt(argv, "--resolution") or "720p")
    state = None
    spath = pr._opt(argv, "--state")
    if spath:
        state = json.loads(Path(spath).read_text())
    else:
        import os
        raw = os.environ.get("NEXABOT_STORAGE_STATE_B64", "").strip()
        if raw:
            try:
                state = json.loads(base64.b64decode(raw))
            except ValueError:
                print("NEXABOT_STORAGE_STATE_B64 is not base64 of a storage_state.json: record the login again.")
                return 2
        else:
            print("No saved login given (no --state, no NEXABOT_STORAGE_STATE_B64): opening logged out, as a test run.")
    code, rep = run(Path(args[0]), state, cfg)
    print(rep["outcome_line"])
    print(f"outcome {rep['outcome']}; Generate clicked {rep.get('generate_clicks', 0)} time(s); "
          f"{len(rep['requests'])} distinct same-origin calls; {len(rep.get('blocked_writes') or [])} writes aborted "
          f"-> {args[0]}")
    if rep["outcome"] == "login_refused":
        print("::error::the saved login was refused: record it again (ops/NEXABOT-LOGIN.md)")
    elif code != 0:
        print(f"::error::no finished video was saved ({rep['outcome']}): see the report")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
