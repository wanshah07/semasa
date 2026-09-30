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
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from typing import Any

from .log import get_logger

log = get_logger("semasa.myra")

_CELL = '''
OUT = {"rows": [], "error": ""}
res, err = call("GOOGLESHEETS_BATCH_GET", {"spreadsheet_id": P["id"], "ranges": [P["range"]]}, P["account"])
if err:
    OUT["error"] = str(err)[:200]
else:
    vr = (res.get("data") or {}).get("valueRanges") or []
    vals = (vr[0].get("values") if vr else None) or []
    for r in vals[1:][-80:]:
        r = [str(c) for c in r] + [""] * (7 - len(r))
        OUT["rows"].append([c[:700] for c in r[:7]])
'''


def fetch(client: Any, cfg: dict[str, Any]) -> dict[str, Any]:
    return client.cell(_CELL, {"id": cfg["spreadsheet_id"], "range": cfg.get("range") or "Sheet1!A1:G500",
                               "account": cfg.get("account") or None},
                       thought="Semasa: read MYRA's daily regulatory log (read only)", budget=90)


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


def findings(rows: list[list[str]], today: date, days: int = 10, limit: int = 12) -> list[dict[str, Any]]:
    """Feed rows (before the writer) for the recent days that had an update, newest first."""
    out: list[dict[str, Any]] = []
    for r in rows:
        d = _date(r[0])
        if d is None or today - d > timedelta(days=days) or d > today + timedelta(days=1):
            continue
        if (r[2] or "").strip().lower() != "yes":
            continue
        parts = [p.strip() for p in re.split(r";", r[4] or "") if p.strip()]
        link, ref, markets = _none(r[6]), _none(r[5]), _none(r[3])
        if not parts or not (link or ref or markets):
            continue
        for n, text in enumerate(parts, 1):
            key = f"{d.isoformat()}-{n}"
            out.append({
                "section": "myra", "source": "MYRA · Daftar Peraturan Kosmetik Global", "kind": "Sapuan harian",
                "country": (markets or "").split(",")[0].strip()[:20] or None, "lang": "ms",
                "title": text[:200], "summary": text[:700] + (f" (Rujukan: {ref})" if ref else ""),
                "url": f"{link}#myra-{key}" if link else f"myra://{key}",
                "published_at": datetime(d.year, d.month, d.day, tzinfo=UTC),
                "raw": {"row_date": d.isoformat(), "ref_no": ref, "markets": markets, "link": link,
                        "link_shared": bool(link) and len(parts) > 1},
            })
    out.sort(key=lambda x: x["published_at"], reverse=True)
    return out[:limit]
