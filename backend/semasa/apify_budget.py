"""Apify as Instagram's LAST resort, and how much of it may be spent (Wan, 26 Nov 2026: "jadikan APIFY as fallback after
playwright").

The order for Instagram is: the saved Playwright login first (a login that lives about a year costs nothing), and only
when that is gone (no saved login, a login wall, no browser) the apidojo actor on Apify. That actor is billed per post
($0.0005 on the Free plan, $0.50 per 1,000) and the FREE plan runs it in "Demo Mode": 5 runs a month and 10 posts a run
(its own README, read 26 Nov 2026); full runs need a paid plan. So the limits here are RUNS as much as dollars, and every
one of them can be raised by an environment variable the day Wan pays for a plan:

    APIFY_MONTHLY_CAP_USD   dollars this system may spend in a month            (default 5)
    APIFY_MONTHLY_RUNS      runs of the actor in a month                        (default 5, the Free plan's)
    APIFY_ITEMS_PER_RUN     posts asked for in one run                          (default 10, the Free plan's)
    APIFY_MIN_GAP_HOURS     hours between two runs (one outage must not burn the month in a day)  (default 24)

THE LEDGER IS APIFY'S OWN. A meter kept in a file would be lost on every GitHub runner (a fresh checkout each run), so the
cap would never trip. Before a run this reads the account's usage (/v2/users/me/limits) and the actor's runs this month
from Apify, and a run that cannot be read refuses: no answer is never "go ahead". `python -m semasa.apify_budget` prints
that state (the "Apify check" workflow); it runs nothing and spends nothing. """

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote

from .log import get_logger

log = get_logger("semasa.apify_budget")

API = "https://api.apify.com"
ACTOR = "apidojo~instagram-scraper"
PRICE_PER_POST = 0.0005                    # the Free plan's price for one post (paid plans pay a little less)
DEFAULTS = {"cap_usd": 5.0, "runs": 5, "items": 10, "gap_hours": 24}
Get = Callable[[str, str], tuple[int, Any]]


class Unreadable(RuntimeError):
    """Apify's own numbers could not be read: the caller must refuse, not guess."""


def _num(name: str, default: float, cast: Callable[[str], float]) -> float:
    try:
        v = cast(os.environ.get(name, "").strip())
        return v if v >= 0 else default
    except ValueError:
        return default


def limits() -> dict[str, Any]:
    return {"cap_usd": _num("APIFY_MONTHLY_CAP_USD", DEFAULTS["cap_usd"], float),
            "runs": int(_num("APIFY_MONTHLY_RUNS", DEFAULTS["runs"], int)),
            "items": max(1, int(_num("APIFY_ITEMS_PER_RUN", DEFAULTS["items"], int))),
            "gap_hours": _num("APIFY_MIN_GAP_HOURS", DEFAULTS["gap_hours"], float)}


def token() -> str:
    return os.environ.get("APIFY_TOKEN", "").strip()


def http_get(path: str, tok: str) -> tuple[int, Any]:
    req = urllib.request.Request(API + path, headers={"Authorization": "Bearer " + tok, "User-Agent": "semasa-apify"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as exc:
        return exc.code, {}
    except Exception as exc:  # noqa: BLE001 - a network failure is "unreadable", never a crash
        raise Unreadable(f"{type(exc).__name__}: {str(exc)[:100]}") from exc


def _when(v: Any) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=UTC)
    except ValueError:
        return None


def month_start(now: datetime) -> datetime:
    return datetime(now.year, now.month, 1, tzinfo=UTC)


def spent(tok: str, get: Get | None = None) -> tuple[float, float | None]:
    """(dollars used this month, the account's own monthly cap) from Apify."""
    code, body = (get or http_get)("/v2/users/me/limits", tok)
    if code != 200:
        raise Unreadable(f"the account's limits answered HTTP {code}")
    d = (body or {}).get("data") or {}
    used = (d.get("current") or {}).get("monthlyUsageUsd")
    if not isinstance(used, (int, float)):
        raise Unreadable("the account's usage was not in the answer")
    cap = (d.get("limits") or {}).get("maxMonthlyUsageUsd")
    return float(used), (float(cap) if isinstance(cap, (int, float)) else None)


def runs_this_month(tok: str, now: datetime, get: Get | None = None) -> tuple[int, datetime | None]:
    """(how many runs of the actor started this month, when the latest started), from Apify's own list of the account's runs."""
    code, body = (get or http_get)(f"/v2/acts/{quote(ACTOR, safe='~')}/runs?limit=100&desc=1", tok)
    if code != 200:
        raise Unreadable(f"the actor's run list answered HTTP {code}")
    since = month_start(now)
    started = [w for w in (_when(r.get("startedAt")) for r in ((body or {}).get("data") or {}).get("items") or []) if w]
    return sum(1 for w in started if w >= since), (max(started) if started else None)


def check(items: int | None = None, now: datetime | None = None, get: Get | None = None,
          tok: str | None = None) -> tuple[bool, str, dict[str, Any]]:
    """(allowed, why, the numbers). Refuses with no token, with a month's runs or dollars used up, inside the minimum gap after
    the last run, and when Apify cannot be asked. Makes no run and spends nothing."""
    now = now or datetime.now(UTC)
    tok = token() if tok is None else tok
    lim = limits()
    n = min(max(1, int(items or lim["items"])), lim["items"])
    info: dict[str, Any] = {"limits": lim, "items": n}
    if not tok:
        return False, "no APIFY_TOKEN secret", info
    try:
        used, account_cap = spent(tok, get)
        runs, last = runs_this_month(tok, now, get)
    except Unreadable as exc:
        return False, f"Apify could not be asked ({exc})", info
    cost = round(n * PRICE_PER_POST, 4)
    info.update(used_usd=round(used, 4), account_cap_usd=account_cap, runs=runs, last_run=last.isoformat() if last else None,
                cost_usd=cost)
    if runs >= lim["runs"]:
        return False, f"{runs} of {lim['runs']} runs used this month", info
    if used + cost > lim["cap_usd"]:
        return False, f"${used:.4f} used of ${lim['cap_usd']:.2f} this month (a run costs up to ${cost})", info
    if account_cap is not None and used + cost > account_cap:
        return False, f"${used:.4f} used of the account's own ${account_cap:.2f} cap", info
    if last and now - last < timedelta(hours=lim["gap_hours"]):
        return False, f"the last run was {int((now - last).total_seconds() // 3600)} h ago (minimum {lim['gap_hours']:g} h)", info
    return True, "", info


def main() -> int:
    """The "Apify check" workflow: is the token alive and would a run be allowed now? Prints no secret and runs nothing."""
    tok = token()
    if not tok:
        print("APIFY_TOKEN: NOT SET in this repository's secrets")
        return 1
    print(f"APIFY_TOKEN: set ({len(tok)} characters)")
    ok, why, info = check(None, None, None, tok)
    lim = info["limits"]
    print(f"limits this system keeps: ${lim['cap_usd']:.2f} a month, {lim['runs']} runs, {lim['items']} posts a run, "
          f"{lim['gap_hours']:g} h between runs")
    if "used_usd" not in info:
        print(f"RESULT: Apify could not be read: {why}")
        return 1
    print(f"this month: ${info['used_usd']} used (the account's own cap: {info['account_cap_usd']}), {info['runs']} run(s), "
          f"last run {info['last_run']}")
    print("RESULT: the token is alive; a fallback run " + ("WOULD be allowed now" if ok else f"would be REFUSED now: {why}"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
