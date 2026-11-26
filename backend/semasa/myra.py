"""MYRA's "Global Cosmetic Reg Daily Log" as a source (Studio's "baca Cosmetic Reg Daily Sweep" Routine, brought over
30 Sep 2026: "port all three before Friday").

MYRA writes one row a weekday to a Google Sheet (Tarikh, Task Run, Ada Update?, Markets, Ringkasan, REG/PIP No., Source
Link). Studio's reader turned each finding in the Ringkasan into an idea. Here each finding is a row in the feed
(`section = 'myra'`), read straight from the sheet with GOOGLESHEETS_BATCH_GET.

Kept from Studio's rules:
  * READ ONLY. Nothing is written to the sheet.
  * Only a row with `Ada Update? = Yes` counts. `No` and `No (separa)` are not findings ("separa" means the day was
    only partly covered, which is a fact about coverage, not news).
  * A `Ringkasan` holds findings separated by `;`: one feed row each.
  * `-`, `\\-` and an empty cell all mean "none".
  * A row's single link belongs to a finding only when the row has one finding. With several findings and one link the
    link is kept but flagged (`raw.link_shared`), and the page says so, so it is never read as the finding's own source.
  * The read uses the account that owns the sheet (`googlesheets_serau-tucker`, info@kkmhalalconsultant.com). The
    default Sheets account in For You belongs to a client and must never be used for this.

One thing Studio never met (16 Nov 2026): Google counts Sheets reads per minute for the whole project the connector runs
under, which every other user of the connector shares. A sweep that lands in a busy minute is answered "Quota exceeded for
quota metric 'Read requests' and limit 'Read requests per minute'", while the same read a minute later works. That answer
is read again after a wait (RETRY_WAITS); every other error is final at once, as before.
"""

from __future__ import annotations

import re
import time
from datetime import UTC, date, datetime, timedelta
from typing import Any

from .log import get_logger

log = get_logger("semasa.myra")

_CELL = '''
import re
OUT = {"rows": [], "error": "", "trimmed": 0}
res, err = call("GOOGLESHEETS_BATCH_GET", {"spreadsheet_id": P["id"], "ranges": [P["range"]]}, P["account"])
if err:
    OUT["error"] = str(err)[:200]
else:
    vr = (res.get("data") or {}).get("valueRanges") or []
    vals = (vr[0].get("values") if vr else None) or []
    since = P.get("since") or ""
    keep = []
    # A row grew from a sentence into a 30,000-character write-up whose first 1,500 characters are the run's own notes (26 Nov
    # 2026: MYRA read nothing for four days). So the row is cut into ONE ITEM PER REFERENCE in column F, each with the words
    # that follow that reference up to the next one; a row with no reference keeps its fragments that are not the run's notes.
    NOTES = ("tetingkap", "hari ini", "pertindihan", "permulaan", "hujungnya", "dedupe")
    def items_of(text, refs):
        low = text.lower()
        at = [(low.find(x.lower()), x) for x in refs]
        found = sorted(i for i, _ in at if i >= 0)
        out = []
        for i, ref in at:
            if i < 0:
                continue                              # a reference the text never names: column F still carries it
            later = [j for j in found if j > i]
            start = max(text.rfind(";", 0, i) + 1, i - 80)        # the sentence the reference sits in, no further back
            end = min([i + 360] + later[:1])                       # and on to the next reference
            out.append({"ref": ref, "text": " ".join(text[start:end].split()).replace(";", ",")})
        if out:
            return out[:12]
        for p in text.split(";"):
            p = " ".join(p.split())
            if len(p) >= 15 and not p.lower().startswith(NOTES) and "larian ini" not in p.lower():
                out.append({"ref": "", "text": p[:360]})
        return out[:6]
    for r in vals[1:][-150:]:
        r = [str(c) for c in r] + [""] * (7 - len(r))
        if r[2].strip().lower() != "yes":              # only a row with an update is a finding
            continue
        m = re.match(r"^\\s*(\\d{1,2})/(\\d{1,2})/(\\d{4})\\s*$", r[0])
        if m and since and "%s-%s-%s" % (m.group(3), m.group(2).zfill(2), m.group(1).zfill(2)) < since:
            continue                                   # older than the days that are read
        refs = [x.strip() for x in r[5].split(";") if x.strip() and x.strip() not in ("-", "\\\\-")]
        keep.append([r[0][:12], "", r[2][:12], r[3][:80], r[4][:300], r[5][:120], r[6][:300], items_of(r[4], refs)])
    # the workbench's answer is capped at 36,000 characters (14 Nov 2026: 46,249 failed every sweep): newest rows are kept
    while keep and len(json.dumps(keep, ensure_ascii=False)) > 30000:
        keep.pop(0)
        OUT["trimmed"] += 1
    OUT["rows"] = keep
'''


# Google's "slow down", in the words its APIs use: a per-minute quota, a rate limit, a 429. Never a permission or a missing sheet.
QUOTA = re.compile(r"quota|rate[ _-]?limit|too many requests|resource[ _]?exhausted|\b429\b", re.I)
# Seconds waited before the 2nd and the 3rd read. The quota is per minute: the first wait rides out a short burst, the second
# is a whole minute and a little. Three reads and 85 seconds at most, well inside the sweep's 30 minutes (sources.yml).
RETRY_WAITS = (20, 65)


def is_quota(error: Any) -> bool:
    return bool(QUOTA.search(str(error or "")))


def fetch(client: Any, cfg: dict[str, Any], now: datetime | None = None, sleep: Any = None) -> dict[str, Any]:
    """The sheet's recent rows with an update (Malaysia's date, `days` back and two more), trimmed to fit the answer.
    A quota or rate answer is read again after each of RETRY_WAITS; `tries` says how many reads it took. `sleep` is for
    tests."""
    today = ((now or datetime.now(UTC)) + timedelta(hours=8)).date()
    since = (today - timedelta(days=int(cfg.get("days") or 10) + 2)).isoformat()
    params = {"id": cfg["spreadsheet_id"], "range": cfg.get("range") or "Sheet1!A1:G500",
              "account": cfg.get("account") or None, "since": since}
    waits = list(RETRY_WAITS)
    tries = 0
    while True:
        tries += 1
        raw = client.cell(_CELL, params, thought="Semasa: read MYRA's daily regulatory log (read only)", budget=90)
        error = raw.get("error") if isinstance(raw, dict) else ""
        if not error or not is_quota(error) or not waits:
            break
        wait = waits.pop(0)
        log.info("MYRA: Google's read quota for this minute is used (read %d); reading again in %d s", tries, wait)
        (sleep or time.sleep)(wait)
    if isinstance(raw, dict):
        raw["tries"] = tries
    return raw


def _none(v: str) -> str | None:
    v = (v or "").strip()
    return None if v in ("", "-", "\\-", "—", "–") else v


def _date(v: str) -> date | None:
    m = re.match(r"^\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*$", v or "")
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))        # DD/MM/YYYY: Malaysia's order
    except ValueError:
        return None


NOTE_RE = re.compile(r"^(?:tetingkap|hari ini|pertindihan|permulaan|hujungnya|dedupe)\b|larian ini", re.I)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")[:40]


def findings(rows: list[list[Any]], today: date, days: int = 10, limit: int = 12) -> list[dict[str, Any]]:
    """Feed rows (before the writer) for the recent days that had an update, newest first. A row the cell cut into items (one
    per reference) gives one feed row each; an older-shaped row is split on `;` with the run's own notes left out."""
    out: list[dict[str, Any]] = []
    for r in rows:
        d = _date(r[0])
        if d is None or today - d > timedelta(days=days) or d > today + timedelta(days=1):
            continue
        if (r[2] or "").strip().lower() != "yes":
            continue
        link, ref, markets = _none(r[6]), _none(r[5]), _none(r[3])
        cut = r[7] if len(r) > 7 and isinstance(r[7], list) else []
        items = [(str(i.get("ref") or ""), str(i.get("text") or "").strip(), f"f{n}")
                 for n, i in enumerate(cut, 1) if isinstance(i, dict)]
        if not items:
            # no reference to cut by: the `;` fragments in their own numbering (the first-generation keys), minus the notes
            items = [("", p.strip(), str(n)) for n, p in enumerate(re.split(r";", r[4] or ""), 1)
                     if p.strip() and not NOTE_RE.search(p.strip())]
        items = [(k, t, n) for k, t, n in items if t]
        if not items or not (link or ref or markets):
            continue
        for item_ref, text, n in items:
            # a finding with a reference is keyed BY it, so an edit that moves it up or down the row does not make it a new one
            # and it never meets the date-n keys of the first-generation rows, which were written from the run's own notes
            key = f"{d.isoformat()}-{_slug(item_ref)}" if _slug(item_ref) else f"{d.isoformat()}-{n}"
            out.append({
                "section": "myra", "source": "MYRA · Daftar Peraturan Kosmetik Global", "kind": "Sapuan harian",
                "country": (markets or "").split(",")[0].strip()[:20] or None, "lang": "ms",
                "title": text[:200], "summary": text[:700] + (f" (Rujukan: {item_ref or ref})" if (item_ref or ref) else ""),
                "url": f"{link}#myra-{key}" if link else f"myra://{key}",
                "published_at": datetime(d.year, d.month, d.day, tzinfo=UTC),
                "raw": {"row_date": d.isoformat(), "ref_no": item_ref or ref, "markets": markets, "link": link,
                        "link_shared": bool(link) and len(items) > 1},
            })
    out.sort(key=lambda x: x["published_at"], reverse=True)
    return out[:limit]
