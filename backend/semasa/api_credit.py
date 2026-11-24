"""How much API credit is left, and until when, for the gateways Wan pays for (Wan, 23 Nov 2026: "pantau berapa banyak realtime
baki credit API tinggal dan validity for mireld, rootsys dan KioskAPI").

`check(gw)` asks one gateway's balance endpoints with ITS OWN key (never another host's, redirects are not followed) and returns
the `balance` object that goes into semasa_api_status.balance:

    {"path": "/dashboard/billing/credit_grants",       the endpoint that gave the figure (as before)
     <the scalars that endpoint answered>,              as before, for the API page's one line
     "credit": {remaining, total, used, percent_left, unit, display_scale, expires_at, grants, source, status, checked_at},
     "tried":  [{path, http, shape, keys, ms, read}],   EVERY path asked, what it answered, and the JSON KEY NAMES only
     "checked_at": ISO UTC}

`tried` is the discovery tool: a gateway whose balance is not readable yet (rootsys answers {} everywhere, KiosAPI has no
remaining figure) shows exactly what each path answered, so the right endpoint can be found without guessing. It carries names,
never values.

Nothing here writes to the database or posts anywhere: api_status.credit_main writes the row.
"""

from __future__ import annotations

import logging
import os
import re
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

import requests

log = logging.getLogger("semasa.api_credit")

CREDIT_SLUGS = ("mireld", "rootsys", "kiosapi")        # the three gateways Wan named
LOW_PERCENT = 15.0                                      # under this much left is "low" ...
LOW_DAYS = 7                                            # ... and so is under this long to run
# Mireld's dashboard (23 Nov 2026) says "88.83M credits, 93% used of 1.27B plan credits, expires 09 Dec 2026 23:31:50 MYT" while
# its API says total_available 89.11, total_granted 1275, total_used 1185.89: the dashboard counts in millions of the API's figure
# (1.275B against 1275, 88.83M against 89.11; the 0.3% gap on what is left is the time between the two readings).
DISPLAY_SCALE = {"mireld": 1_000_000}
UNLIMITED = 1_000_000                                   # a hard limit this big (KiosAPI: 100,000,000 USD) is "no limit"
MAX_TRIED = 24
MAX_KEYS = 40
MAX_GRANTS = 20

# Asked in this order; the first that gives a remaining figure is the source. A path under the base URL (which usually ends /v1)
# and a path under the host root are listed apart: New-API / One-API panels keep /api/... at the root, OpenAI's billing under /v1.
BASE_PATHS = (
    "/dashboard/billing/credit_grants",
    "/quota",                                     # rootsys.cloud/v1/quota: tokens left, total, used, expiry
    "/dashboard/billing/subscription",
    "/dashboard/billing/usage?start_date={start}&end_date={end}",
    "/credits",
    "/credit",
    "/balance",
    "/user/balance",
    "/usage",
    "/key",
    "/me",
)
ROOT_PATHS = (
    "/api/usage/token/",                          # New-API answers /api/usage/token with a 301 to this one: the slash is the fix
    "/api/usage/token",
    "/api/user/self",
    "/api/status",
    "/v1/credits",
    "/v1/me",
    "/v1/key",
    "/v1/usage",
)

REMAINING_KEYS = ("total_available", "tokens_remaining", "remaining", "remain_quota", "remaining_quota", "quota_remaining",
                  "limit_remaining",
                  "available", "available_balance", "total_balance", "balance", "credits", "credit", "left", "remain")
TOTAL_KEYS = ("total_granted", "tokens_total", "total_quota", "quota_total", "total", "limit", "hard_limit_usd",
              "system_hard_limit_usd")
USED_KEYS = ("total_used", "tokens_used", "used_quota", "used", "usage")
EXPIRY_KEYS = ("expires_at", "expire_at", "expired_at", "expiry", "expiry_date", "expire_date", "expire_time", "expires",
               "expiration", "expiration_time", "valid_until", "access_until")
GRANT_AMOUNT = ("grant_amount", "amount", "total_granted", "granted")
GRANT_USED = ("used_amount", "used", "total_used")


# ---- reading numbers and dates ------------------------------------------------------------------------------------------------

def num(v: Any) -> float | None:
    """A number from a JSON number or a numeric string; never a bool, never NaN or infinity."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        f = float(v)
    elif isinstance(v, str):
        try:
            f = float(v.strip().replace(",", ""))
        except ValueError:
            return None
    else:
        return None
    return f if f == f and abs(f) != float("inf") else None


def parse_expiry(v: Any) -> str | None:
    """An expiry as ISO UTC (`2026-12-09T15:31:50Z`), or None. Epoch seconds, epoch milliseconds, ISO text; 0, empty and a year
    outside 2000-2200 (0001-01-01, 9999-12-31 and other "never" stand-ins) mean no expiry."""
    if v is None or isinstance(v, bool) or v == "":
        return None
    n = num(v)
    when: datetime | None = None
    if n is not None:
        if n <= 0:
            return None
        try:
            when = datetime.fromtimestamp(n / 1000 if n > 1e11 else n, UTC)
        except (OverflowError, OSError, ValueError):
            return None
    elif isinstance(v, str):
        text = v.strip().replace(" ", "T", 1) if re.match(r"^\d{4}-\d\d-\d\d \d", v.strip()) else v.strip()
        try:
            when = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        when = when.replace(tzinfo=UTC) if when.tzinfo is None else when.astimezone(UTC)
    if when is None or not 2000 <= when.year <= 2200:
        return None
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def _dt(iso: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")) if iso else None
    except ValueError:
        return None


# ---- what an answer says ------------------------------------------------------------------------------------------------------

def _name_ok(k: str) -> str:
    """A key NAME that is safe to show: long or token-like names (an id used as a key) are hidden."""
    k = str(k)
    tokenish = re.fullmatch(r"[A-Za-z0-9_-]{20,}", k) and re.search(r"\d", k)
    if k.lower().startswith(("sk-", "sk_", "eyj")) or len(k) > 32 or tokenish:
        return "(id)"
    return k


def key_names(j: Any, limit: int = MAX_KEYS) -> list[str]:
    """The JSON key NAMES of an answer, never a value: `data.quota`, `grants.data[].expires_at`. A map with many keys (models,
    ids) is shown as `name{N keys}`. Capped, so a big answer cannot flood the row."""
    out: list[str] = []

    def walk(x: Any, prefix: str, depth: int) -> None:
        if len(out) >= limit or depth > 4:
            return
        if isinstance(x, dict):
            if len(x) > 30:
                out.append(f"{prefix or 'root'}{{{len(x)} keys}}")
                return
            for k, v in x.items():
                name = f"{prefix}.{_name_ok(k)}" if prefix else _name_ok(k)
                if isinstance(v, (dict, list)):
                    if isinstance(v, dict) and not v:
                        out.append(f"{name}{{}}")
                    else:
                        walk(v, name, depth + 1)
                else:
                    out.append(name)
                if len(out) >= limit:
                    return
        elif isinstance(x, list):
            if x:
                walk(x[0], f"{prefix}[]", depth + 1)
            else:
                out.append(f"{prefix}[]")

    walk(j, "", 0)
    return out[:limit]


def _dicts(j: Any) -> list[dict[str, Any]]:
    """The dicts worth reading a figure from: the answer, and its `data` object (New-API wraps everything in {success, data})."""
    if not isinstance(j, dict):
        return []
    out = [j]
    if isinstance(j.get("data"), dict):
        out.append(j["data"])
    return out


def _first(ds: list[dict[str, Any]], keys: tuple[str, ...], skip: set[str] | None = None) -> tuple[str, float] | None:
    for d in ds:
        for k in keys:
            if skip and k in skip:
                continue
            v = num(d.get(k))
            if v is not None:
                return k, v
    return None


def _grants(j: Any) -> list[dict[str, Any]]:
    """OpenAI-style `grants.data[]` (also `data[]` or `grants[]`): an amount, what is used, when it starts and when it ends."""
    cands: list[Any] = []
    if isinstance(j, dict):
        g = j.get("grants")
        cands += [g.get("data") if isinstance(g, dict) else g, j.get("data") if isinstance(j.get("data"), list) else None]
    out = []
    for lst in cands:
        if not isinstance(lst, list):
            continue
        for item in lst:
            if not isinstance(item, dict):
                continue
            amount = next((v for k in GRANT_AMOUNT if (v := num(item.get(k))) is not None), None)
            used = next((v for k in GRANT_USED if (v := num(item.get(k))) is not None), None)
            exp = next((v for k in EXPIRY_KEYS if (v := parse_expiry(item.get(k)))), None)
            eff = parse_expiry(item.get("effective_at") or item.get("start_at") or item.get("created_at"))
            if amount is None and exp is None:
                continue
            out.append({"amount": amount, "used": used, "effective_at": eff, "expires_at": exp})
        if out:
            break
    return out[:MAX_GRANTS]


def facts_of(j: Any) -> dict[str, Any]:
    """What one answer says, as far as it says it: remaining, total, used, unit, expires_at, grants, unlimited. {} when it says
    nothing about credit. Pure: the same answer always reads the same."""
    ds = _dicts(j)
    if not ds:
        return {}
    f: dict[str, Any] = {}
    unit = ""
    keys_in = {k for d in ds for k in d}
    # New-API's /api/user/self: `quota` is what is LEFT when `used_quota` sits beside it
    rem = _first(ds, REMAINING_KEYS)
    if rem is None and "used_quota" in keys_in:
        rem = _first(ds, ("quota",))
    # a New-API KEY with no limit of its own: its figures say nothing about the account's top-up, so they are not a balance
    limitless = any(d.get("unlimited_quota") is True for d in ds)
    if limitless:
        rem = None
    tot = None if limitless else _first(ds, TOTAL_KEYS)
    if tot and tot[0].endswith("_usd"):
        unit = "USD"
        if tot[1] >= UNLIMITED:                       # a sentinel for "no limit", not a figure to compute a percentage from
            tot = None
    used = None if limitless else _first(ds, USED_KEYS)
    if rem and rem[0] == "tokens_remaining":
        unit = "tokens"                              # rootsys counts in tokens (its dashboard: "545.1M left")
    cents = _first(ds, ("total_usage",))             # /dashboard/billing/usage: hundredths of a US dollar, spent this period
    if used is None and cents is not None:
        used, unit = ("total_usage", cents[1] / 100), unit or "USD"
    if rem and rem[0] in ("balance", "credits", "credit") and "currency" in keys_in:
        cur = next((str(d.get("currency")) for d in ds if d.get("currency")), "")
        unit = unit or cur[:8].upper()
    if rem:
        f["remaining"] = rem[1]
    if tot:
        f["total"] = tot[1]
    if used:
        f["used"] = used[1]
    if any(d.get("unlimited") is True for d in ds):
        f["unlimited"] = True
    grants = _grants(j)
    if grants:
        f["grants"] = grants
    exp = [e for d in ds for k in EXPIRY_KEYS if (e := parse_expiry(d.get(k)))]
    exp += [g["expires_at"] for g in grants if g["expires_at"]]
    if exp:
        f["expiries"] = sorted(set(exp))
        # a grant already used up holds no credit: its date is not the validity
        live = [g["expires_at"] for g in grants if g["expires_at"] and not _spent(g)]
        f["live_expiries"] = sorted(set(live)) if grants else f["expiries"]
    if not f:                                         # nothing about credit (an access_until of 0 and a sentinel limit say none)
        return {}
    if unit:
        f["unit"] = unit
    return f


def _spent(g: dict[str, Any]) -> bool:
    return bool(g.get("amount")) and g.get("used") is not None and g["used"] >= g["amount"]


def pick_expiry(expiries: list[str], now: datetime) -> str | None:
    """The date that decides validity: the earliest one still ahead; with none ahead, the latest that has gone."""
    dated = [(d, e) for e in expiries if (d := _dt(e))]
    if not dated:
        return None
    future = sorted(e for d, e in dated if d > now)
    return future[0] if future else sorted(e for _d, e in dated)[-1]


def percent_left(remaining: float | None, total: float | None) -> float | None:
    if remaining is None or not total or total <= 0:
        return None
    return round(max(0.0, min(100.0, 100.0 * remaining / total)), 1)


def status_of(credit: dict[str, Any], now: datetime | None = None) -> str:
    """ok | low | expired | unknown, from the stored figures and the clock (so a reading ages into `expired` on its own).
    expired: the validity date has passed. low: under LOW_PERCENT left, nothing left, or under LOW_DAYS to run.
    unknown: no figure and no date could be read."""
    now = now or datetime.now(UTC)
    exp = _dt(credit.get("expires_at"))
    if exp and exp <= now:
        return "expired"
    rem, pct = num(credit.get("remaining")), num(credit.get("percent_left"))
    if rem is None and exp is None and not credit.get("unlimited"):
        return "unknown"
    if rem is not None and (rem <= 0 or (pct is not None and pct < LOW_PERCENT)):
        return "low"
    if exp and exp - now < timedelta(days=LOW_DAYS):
        return "low"
    return "ok"


def credit_from(slug: str, found: list[tuple[str, dict[str, Any]]], now: datetime | None = None) -> dict[str, Any]:
    """The normalised `credit` object from what each path said ([(path, facts)], in the order they were asked)."""
    now = now or datetime.now(UTC)
    source = next(((p, f) for p, f in found if f.get("remaining") is not None), None)
    if source is None:                                # no remaining figure: a total and what is used give one
        source = next(((p, f) for p, f in found if f.get("total") is not None and f.get("used") is not None), None)
    c: dict[str, Any] = {"remaining": None, "total": None, "used": None, "percent_left": None, "unit": "credit",
                         "display_scale": DISPLAY_SCALE.get(slug), "expires_at": None, "grants": [], "source": None,
                         "unlimited": False, "status": "unknown", "checked_at": now.strftime("%Y-%m-%dT%H:%M:%SZ")}
    if source:
        path, f = source
        rem, tot, used = f.get("remaining"), f.get("total"), f.get("used")
        if rem is None and tot is not None and used is not None:
            rem = max(0.0, tot - used)
        if tot is None and rem is not None and used is not None:
            tot = rem + used
        if used is None and tot is not None and rem is not None:
            used = max(0.0, tot - rem)
        c.update(remaining=_r(rem), total=_r(tot), used=_r(used), percent_left=percent_left(rem, tot), source=path,
                 unit=f.get("unit") or "credit", unlimited=bool(f.get("unlimited")), grants=f.get("grants") or [])
        if c["unit"] != "credit":
            c["display_scale"] = None                 # the dashboard factor is known only for Mireld's own credit units
    exps = (source[1].get("live_expiries") if source else None) or [e for _p, f in found for e in f.get("live_expiries", [])]
    c["expires_at"] = pick_expiry(exps, now)
    if c["source"] is None and any(f.get("unlimited") for _p, f in found):
        c["unlimited"] = True
    c["status"] = status_of(c, now)
    return c


def _r(v: float | None) -> float | None:
    return None if v is None else round(v, 6)


def keep_if_unreachable(new: dict[str, Any], prev: dict[str, Any] | None) -> dict[str, Any]:
    """A check that could not reach ANY endpoint (a network error, a 5xx) must not wipe the last good figure: it is kept, marked
    stale, with the new `tried` list. A gateway that answered but no longer shows a figure is honest: unknown."""
    credit = new.get("credit") or {}
    old = (prev or {}).get("credit") if isinstance(prev, dict) else None
    answered = any((t.get("http") or 0) in range(200, 500) for t in new.get("tried", []))
    if credit.get("remaining") is None and isinstance(old, dict) and old.get("remaining") is not None and not answered:
        kept = {**old, "stale": True, "stale_since": old.get("stale_since") or old.get("checked_at")}
        kept["status"] = status_of(kept)
        return {**new, "credit": kept}
    return new


# ---- asking the gateway --------------------------------------------------------------------------------------------------------

def _urls(base_url: str, now: datetime) -> list[tuple[str, str]]:
    """[(label, url)] for every candidate path: under the base URL first, then under the host root (the gateway's own host)."""
    base = base_url.rstrip("/")
    parts = urlsplit(base)
    root = f"{parts.scheme}://{parts.netloc}"
    fill = {"start": now.strftime("%Y-%m-01"), "end": (now + timedelta(days=1)).strftime("%Y-%m-%d")}
    out = [(p.format(**fill), base + p.format(**fill)) for p in BASE_PATHS]
    seen = {u for _l, u in out}
    for p in ROOT_PATHS:
        u = root + p
        if u not in seen:                              # /v1/credits is the same address when the base URL already ends /v1
            out.append((p, u))
            seen.add(u)
    return out


def ask(url: str, key: str, timeout: float, get: Any = None, headers: dict[str, str] | None = None) -> dict[str, Any]:
    """One GET with the gateway's own key: {http, shape, keys, ms, json}. The key is sent to this URL alone and a redirect is not
    followed (it could lead to another host). `headers` replaces the bearer key (an account's access token, below)."""
    get = get or requests.get
    t0 = time.monotonic()
    try:
        r = get(url, headers=headers or {"Authorization": f"Bearer {key}", "Accept": "application/json"}, timeout=timeout,
                allow_redirects=False)
    except requests.RequestException as exc:
        ms = int((time.monotonic() - t0) * 1000)
        return {"http": None, "shape": f"error: {type(exc).__name__}", "keys": [], "ms": ms, "json": None}
    ms = int((time.monotonic() - t0) * 1000)
    code = int(getattr(r, "status_code", 0) or 0)
    if 300 <= code < 400:
        return {"http": code, "shape": "redirect", "keys": [], "ms": ms, "json": None}
    try:
        j = r.json()
    except ValueError:
        return {"http": code, "shape": "not JSON", "keys": [], "ms": ms, "json": None}
    shape = "{}" if j == {} else "[]" if j == [] else "json"
    return {"http": code, "shape": shape, "keys": key_names(j), "ms": ms, "json": j if code == 200 else None}


ACCOUNT_PATH = "/api/user/self"


ACCOUNTS_TABLE = "semasa_credit_accounts"
# slug -> {"token", "user_id"}: the account keys Wan typed on the API credit page (supabase/096), read once a run by
# load_accounts. Held in memory only, for the run; sent only to that gateway's own host (check()).
_ACCOUNTS: dict[str, dict[str, str]] = {}


def load_accounts(store: Any) -> list[str]:
    """Read the account keys typed into Semasa (supabase/096) for this run. Returns the slugs that have one; [] when the table
    is not there or cannot be read (the GitHub secrets, if any, still work). Never logs a token."""
    _ACCOUNTS.clear()
    try:
        rows = store.table(ACCOUNTS_TABLE).select("slug,access_token,user_id").execute().data or []
    except Exception as exc:  # noqa: BLE001 - no table is no typed key
        log.info("account keys not read (%s)", str(exc)[:120])
        return []
    for r in rows:
        token, uid = str(r.get("access_token") or "").strip(), str(r.get("user_id") or "").strip()
        if r.get("slug") in CREDIT_SLUGS and token and uid:
            _ACCOUNTS[str(r["slug"])] = {"token": token, "user_id": uid}
    return sorted(_ACCOUNTS)


def account_headers(slug: str, env: Any = None) -> dict[str, str] | None:
    """New-API panels (KiosAPI) keep the top-up on the ACCOUNT, which an API key cannot read: it takes the access token made
    in the panel (Personal settings, Security) plus the user id. The pair comes from the optional secrets
    `<SLUG>_ACCESS_TOKEN` and `<SLUG>_USER_ID`, else from what Wan typed on the API credit page (load_accounts); with neither
    the account is not asked and the card says so."""
    env = os.environ if env is None else env
    token, uid = str(env.get(f"{slug.upper()}_ACCESS_TOKEN") or "").strip(), str(env.get(f"{slug.upper()}_USER_ID") or "").strip()
    if not token or not uid:
        typed = _ACCOUNTS.get(slug) or {}
        token, uid = typed.get("token", ""), typed.get("user_id", "")
    if not token or not uid:
        return None
    return {"Authorization": f"Bearer {token}", "New-Api-User": uid, "Accept": "application/json"}


def _per_unit(j: Any) -> float | None:
    """quota_per_unit from the panel's public /api/status: how many quota points are one US dollar (500000 by default)."""
    d = j.get("data") if isinstance(j, dict) else None
    v = num(d.get("quota_per_unit")) if isinstance(d, dict) else None
    return v if v and v > 0 else None


def _in_dollars(facts: dict[str, Any], per: float) -> dict[str, Any]:
    out = dict(facts)
    for k in ("remaining", "total", "used"):
        if out.get(k) is not None:
            out[k] = out[k] / per
    out["unit"] = "USD"
    return out


def check(gw: dict[str, Any], timeout: float = 10, budget: float = 60, prev: dict[str, Any] | None = None,
          now: datetime | None = None, get: Any = None) -> dict[str, Any]:
    """The `balance` object for one gateway (see the module docstring). Stops asking once a remaining figure AND a validity date
    are known, or when `budget` seconds are spent, so a slow gateway cannot hold the run."""
    now = now or datetime.now(UTC)
    found: list[tuple[str, dict[str, Any]]] = []
    tried: list[dict[str, Any]] = []
    legacy: dict[str, Any] = {}
    started = time.monotonic()
    per_unit: float | None = None
    hdr = account_headers(gw["slug"])
    for label, url in _urls(gw["base_url"], now):
        if hdr and label == ACCOUNT_PATH:               # asked below with the access token instead: a key gets a 401 there
            continue
        if len(tried) >= MAX_TRIED or time.monotonic() - started > budget:
            break
        a = ask(url, gw["key"], min(timeout, 15), get)
        facts = facts_of(a["json"]) if a["http"] == 200 else {}
        tried.append({"path": label.split("?")[0], "http": a["http"], "shape": a["shape"], "keys": a["keys"], "ms": a["ms"],
                      "read": bool(facts)})
        if facts:
            found.append((label.split("?")[0], facts))
            if not legacy and facts.get("remaining") is not None and isinstance(a["json"], dict):
                legacy = {"path": label.split("?")[0],
                          **{k: v for k, v in a["json"].items() if isinstance(v, (int, float, str)) and len(str(v)) < 80}}
        if label == "/api/status" and a["http"] == 200:
            per_unit = _per_unit(a["json"]) or per_unit
        cred = credit_from(gw["slug"], found, now)
        if cred["remaining"] is not None and cred["expires_at"]:
            break
    if hdr and not any(f.get("remaining") is not None for _p, f in found):
        parts = urlsplit(gw["base_url"].rstrip("/"))
        root = f"{parts.scheme}://{parts.netloc}"
        a = ask(root + ACCOUNT_PATH, gw["key"], min(timeout, 15), get, headers=hdr)
        facts = facts_of(a["json"]) if a["http"] == 200 else {}
        tried.append({"path": ACCOUNT_PATH + " (account)", "http": a["http"], "shape": a["shape"], "keys": a["keys"],
                      "ms": a["ms"], "read": bool(facts)})
        if facts:
            found.append((ACCOUNT_PATH + " (account)", _in_dollars(facts, per_unit or 500000.0)))
    credit = credit_from(gw["slug"], found, now)
    out = {**legacy, "credit": credit, "tried": tried, "checked_at": now.strftime("%Y-%m-%dT%H:%M:%SZ")}
    return keep_if_unreachable(out, prev)
