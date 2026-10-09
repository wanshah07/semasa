"""Resit (Wan, 9 Oct 2026): the worker's half of "snap a receipt".

The page puts the photo in the semasa-reference bucket and inserts a `pending` row in semasa_receipts; the database wakes
this run (repository_dispatch 'receipts_pending', supabase/033_receipts.sql) and, for each pending row, it
  1. fetches the picture and asks the VISION model to read it: vendor, date, total, currency, tax, the items, how it was
     paid, a category from a fixed list, a one-line outline, and how sure it is (llm.describe_image, the same read step
     the design reader uses);
  2. files the picture in Google Drive under <drive_root>/<YYYY>/<MM>/<date vendor total>.jpg through Composio For You
     (a workbench cell fetches the picture, stages it, finds or creates each folder, uploads once);
  3. matches the vendor to a subscription (Langganan) by name, so the page can offer "mark the subscription paid";
  4. writes everything back on the row: status done, or error with the reason in words.
Each step that fails is recorded on its own (a picture read but not filed is still read), and a transient failure leaves
the row pending for the next run, up to MAX_ATTEMPTS. Nothing here deletes a picture."""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests

from . import ai_config, api_status, db
from .config import LLMSettings
from .foryou import ForYou
from .llm import LLM
from .log import get_logger
from .senders import SendError

log = get_logger("semasa.receipts")

SETTINGS_KEY = "receipts"
DEFAULTS = {"drive_root": "Semasa/Resit", "drive_account": "", "per_run": 20}
MAX_ATTEMPTS = 3
MAX_BYTES = 12_000_000
CATEGORIES = ("makan", "pengangkutan", "bekalan", "langganan", "utiliti", "perjalanan", "pejabat", "klien", "lain")
CATEGORY_WORDS = {
    "makan": ("restoran", "restaurant", "cafe", "kopi", "coffee", "food", "makan", "mamak", "kfc", "mcdonald",
             "grabfood", "foodpanda", "bakery", "tealive", "zus"),
    "pengangkutan": ("grab", "petrol", "petronas", "shell", "caltex", "touch n go", "tng", "toll", "tol", "parking",
             "parkir", "lrt", "mrt", "ktm", "bas", "bus", "taxi"),
    "bekalan": ("mr diy", "mr. diy", "eco shop", "lotus", "tesco", "aeon", "giant", "mydin", "99 speedmart",
             "speedmart", "jaya grocer", "village grocer", "pharmacy", "farmasi", "guardian", "watsons", "shopee",
             "lazada"),
    "langganan": ("subscription", "langganan", "renewal", "plan", "monthly", "annual", "anthropic", "openai",
             "google workspace", "microsoft", "adobe", "canva", "apple.com", "icloud", "render", "replicate"),
    "utiliti": ("tnb", "tenaga", "air selangor", "syabas", "indah water", "unifi", "time", "celcom", "digi", "maxis",
             "umobile", "yes", "streamyx", "electric", "water bill"),
    "perjalanan": ("hotel", "airbnb", "airasia", "malaysia airlines", "mas", "batik air", "flight", "penerbangan",
             "agoda", "booking.com", "trip.com"),
    "pejabat": ("printing", "cetak", "stationery", "alat tulis", "popular", "courier", "pos laju", "poslaju", "j&t",
             "dhl", "fedex", "ninja", "office", "pejabat"),
    "klien": ("npra", "kkm", "jakim", "ssm", "mida", "sirim", "halal", "notification", "notifikasi", "trustgate",
             "digicert", "msc trustgate"),
}

SYSTEM = ("You read receipts and invoices photographed with a phone (Malaysia; Bahasa Malaysia or English). Answer ONLY with "
          "one JSON object and nothing else. Never invent a figure: when a value is not legible, use null. Dates are "
          "YYYY-MM-DD. Money is a number with two decimals, no currency sign.")
PROMPT = ("Read this receipt. Return JSON with exactly these keys:\n"
          "vendor (the shop or company as printed), date, total (the final amount paid), currency (ISO code, MYR when RM), "
          "tax (SST/GST amount or null), items (list of {name, qty, price}; price is the line amount), payment_method "
          "(cash | card | ewallet | transfer | unknown), category (one of: makan, pengangkutan, bekalan, langganan, utiliti, "
          "perjalanan, pejabat, klien, lain), summary (one line in Bahasa Malaysia: what was bought, where, for how much), "
          "confidence (0 to 1: how legible and complete the receipt is).")


# ---- settings and small helpers ------------------------------------------------------------------------------------------
def load_settings(store: Any) -> dict[str, Any]:
    rows = store.table(db.SETTINGS).select("key,value").eq("key", SETTINGS_KEY).execute().data or []
    raw = rows[0]["value"] if rows and isinstance(rows[0].get("value"), dict) else {}
    return {**DEFAULTS, **raw}


def money(v: Any) -> float | None:
    """A number out of whatever the reader wrote: 'RM 1,234.50' → 1234.5; None when it is not a number."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return round(float(v), 2)
    m = re.search(r"-?\d[\d,]*(?:\.\d+)?", str(v))
    if not m:
        return None
    try:
        return round(float(m.group(0).replace(",", "")), 2)
    except ValueError:
        return None


def iso_date(v: Any) -> str | None:
    """YYYY-MM-DD out of the reader's date; DD/MM/YYYY and DD-MM-YYYY are read as Malaysian (day first)."""
    s = str(v or "").strip()
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        m = re.match(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})", s)
        if not m:
            return None
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000
    try:
        return datetime(y, mo, d).date().isoformat()
    except ValueError:
        return None


def category_of(vendor: str, said: Any, items: list[dict[str, Any]] | None = None) -> str:
    """The reader's category when it is one of ours; otherwise the first keyword list the vendor or an item matches;
    otherwise 'lain'."""
    s = str(said or "").strip().lower()
    if s in CATEGORIES:
        return s
    hay = " ".join([vendor or ""] + [str(i.get("name") or "") for i in (items or [])]).lower()
    for cat, words in CATEGORY_WORDS.items():
        if any(w in hay for w in words):
            return cat
    return "lain"


def parse_read(raw: dict[str, Any] | None) -> dict[str, Any]:
    """The reader's answer as the row takes it. Every field is checked; a bad one is dropped, never guessed."""
    r = raw if isinstance(raw, dict) else {}
    items_in = r.get("items") if isinstance(r.get("items"), list) else []
    items = []
    for it in items_in[:60]:
        if not isinstance(it, dict):
            continue
        name = str(it.get("name") or it.get("description") or "").strip()[:120]
        if not name:
            continue
        items.append({"name": name, "qty": money(it.get("qty")) or 1, "price": money(it.get("price") or it.get("amount"))})
    vendor = str(r.get("vendor") or r.get("merchant") or "").strip()[:120]
    cur = str(r.get("currency") or "MYR").strip().upper()[:3] or "MYR"
    if cur == "RM":
        cur = "MYR"
    conf = money(r.get("confidence"))
    pm = str(r.get("payment_method") or "unknown").strip().lower()[:20]
    return {
        "vendor": vendor, "doc_date": iso_date(r.get("date")), "total": money(r.get("total")), "currency": cur,
        "tax": money(r.get("tax")), "items": items, "payment_method": pm,
        "category": category_of(vendor, r.get("category"), items),
        "summary": str(r.get("summary") or "").strip()[:300],
        "confidence": None if conf is None else max(0.0, min(1.0, conf)),
    }


def match_subscription(vendor: str, subs: list[dict[str, Any]]) -> str | None:
    """The subscription whose vendor or name is in the receipt's vendor (or the other way round), 4 letters at least;
    the longest match wins so 'Unifi Mobile' beats 'Unifi'."""
    v = (vendor or "").lower().strip()
    if len(v) < 3:
        return None
    best, best_len = None, 0
    for s in subs:
        if s.get("status") == "ended":
            continue
        for cand in (str(s.get("vendor") or ""), str(s.get("name") or "")):
            c = cand.lower().strip()
            if len(c) >= 4 and (c in v or v in c) and len(c) > best_len:
                best, best_len = s["id"], len(c)
    return best


def file_name(read: dict[str, Any], rid: str) -> str:
    """'2026-10-09 Petronas RM45.00.jpg', safe for Drive and for a human to read."""
    vendor = re.sub(r"\s+", " ", re.sub(r"[^A-Za-z0-9 .&'-]+", " ", read.get("vendor") or "resit")).strip()[:40] or "resit"
    total = read.get("total")
    cur = "RM" if (read.get("currency") or "MYR") == "MYR" else (read.get("currency") or "")
    amt = f" {cur}{total:.2f}" if isinstance(total, (int, float)) else ""
    return f"{read.get('doc_date') or 'tarikh-tiada'} {vendor}{amt} {rid[:6]}.jpg"


def drive_segments(root: str, doc_date: str | None, taken_at: str) -> list[str]:
    """Semasa/Resit/2026/10: the receipt's own date when it was read, else the day it was snapped (MYT)."""
    base = [p for p in (root or "Semasa/Resit").split("/") if p.strip()]
    d = doc_date or ""
    if not re.match(r"^\d{4}-\d{2}", d):
        try:
            ms = datetime.fromisoformat(str(taken_at).replace("Z", "+00:00")).timestamp()
            d = datetime.fromtimestamp(ms + 8 * 3600, UTC).strftime("%Y-%m")
        except ValueError:
            d = datetime.now(UTC).strftime("%Y-%m")
    return base + [d[:4], d[5:7]]


# ---- Google Drive through Composio For You -------------------------------------------------------------------------------
_FILE_CELL = """
import requests, os
r = requests.get(P["url"], timeout=90)
ct = (r.headers.get("content-type") or "").split(";")[0].strip()
if r.status_code != 200 or not ct.startswith("image/"):
    raise RuntimeError(f"the picture answered {r.status_code} {ct or 'no type'}")
os.makedirs("/home/user/semasa", exist_ok=True)
path = "/home/user/semasa/" + P["name"]
with open(path, "wb") as fh:
    fh.write(r.content)
res, err = upload_local_file(path)
if err:
    raise RuntimeError(f"staging the picture failed: {err}")
key = (res or {}).get("s3key") or ((res or {}).get("data") or {}).get("s3key")
if not key:
    raise RuntimeError(f"staging gave no s3key: {str(res)[:200]}")

def dig(obj, want):
    # the first value under `want` anywhere in an answer (Composio nests data/files differently per version)
    if isinstance(obj, dict):
        if want in obj:
            return obj[want]
        for v in obj.values():
            f = dig(v, want)
            if f is not None:
                return f
    elif isinstance(obj, list):
        for v in obj:
            f = dig(v, want)
            if f is not None:
                return f
    return None

acct = P.get("account") or None
parent = None
for seg in P["segments"]:
    args = {"name_exact": seg, "page_size": 20}
    if parent:
        args["parent_folder_id"] = parent
    d, e = call("GOOGLEDRIVE_FIND_FOLDER", args, acct)
    if e:
        raise RuntimeError(f"find folder {seg}: {e}")
    found = [f for f in (dig(d, "files") or []) if isinstance(f, dict) and f.get("id") and not f.get("trashed")]
    if parent is None:
        # at the top we only accept a folder that sits in My Drive's root, so a same-named folder elsewhere is not taken
        top = [f for f in found if "root" in [str(p) for p in (f.get("parents") or [])] or not f.get("parents")]
        found = top or found
    if found:
        parent = found[0]["id"]
    else:
        c, e = call("GOOGLEDRIVE_CREATE_FOLDER", {"name": seg, **({"parent_id": parent} if parent else {})}, acct)
        if e:
            raise RuntimeError(f"create folder {seg}: {e}")
        parent = dig(c, "id")
        if not parent:
            raise RuntimeError(f"create folder {seg} gave no id: {str(c)[:200]}")
u, e = call("GOOGLEDRIVE_UPLOAD_FILE", {"file_to_upload": {"name": P["name"], "mimetype": ct, "s3key": key},
                                         "folder_to_upload_to": parent}, acct)
if e:
    raise RuntimeError(f"upload: {e}")
fid = dig(u, "id")
if not fid:
    raise RuntimeError(f"upload gave no file id: {str(u)[:200]}")
OUT["file_id"] = fid
OUT["url"] = dig(u, "webViewLink") or f"https://drive.google.com/file/d/{fid}/view"
OUT["folder_id"] = parent
"""


class Drive(ForYou):
    """Google Drive through the For You workbench: find/create the folder chain once and upload once."""

    def __init__(self, consumer_key: str, account_email: str = "", session: Any = None):
        super().__init__(consumer_key, session=session)
        self.expect = account_email
        self.account_id: str | None = None

    def account(self) -> str | None:
        if self.account_id or not self.expect:
            return self.account_id
        body = self._twice(lambda: self._tool("COMPOSIO_MANAGE_CONNECTIONS",
                                              {"toolkits": [{"name": "googledrive", "action": "list"}]}))
        accts = (((body.get("data") or {}).get("results") or {}).get("googledrive") or {}).get("accounts") or []
        for a in accts:
            info = a.get("user_info") or {}
            email = str((info.get("user") or {}).get("emailAddress") or info.get("email") or "")
            if str(a.get("status", "")).lower() == "active" and email.lower() == self.expect.lower():
                self.account_id = a["id"]
                return self.account_id
        raise SendError("refused", f"Composio For You: no active Google Drive connection for {self.expect}")

    def file(self, *, url: str, name: str, segments: list[str]) -> dict[str, Any]:
        out = self.cell(_FILE_CELL, {"url": url, "name": name, "segments": segments, "account": self.account()},
                        thought="Semasa: file a receipt in Google Drive", budget=150) or {}
        if not out.get("file_id"):
            raise SendError("transient", "Drive gave no file id")
        return out


# ---- the run -------------------------------------------------------------------------------------------------------------
def fetch_image(url: str) -> tuple[bytes, str]:
    r = requests.get(url, timeout=60)
    ct = (r.headers.get("content-type") or "").split(";")[0].strip() or "image/jpeg"
    if r.status_code != 200 or not ct.startswith("image/"):
        raise SendError("refused", f"the picture answered {r.status_code} {ct}")
    if len(r.content) > MAX_BYTES:
        raise SendError("refused", f"the picture is {len(r.content) // 1_000_000} MB; the page shrinks to about 1 MB")
    return r.content, ct


def claim(store: Any, limit: int) -> list[dict[str, Any]]:
    q = store.table(db.RECEIPTS).select("*").eq("status", "pending").order("created_at").limit(limit)
    out = []
    for r in q.execute().data or []:
        attempts = int(r.get("attempts") or 0) + 1
        got = store.table(db.RECEIPTS).update({"status": "working", "attempts": attempts}) \
            .eq("id", r["id"]).eq("status", "pending").execute().data
        if got:
            out.append({**r, "attempts": attempts})
    return out


def process(store: Any, settings: dict[str, Any], llm: Any, drive: Drive | None, now: datetime,
            fetch: Any = fetch_image) -> dict[str, int]:
    counts = {"read": 0, "filed": 0, "error": 0, "matched": 0}
    subs = store.table(db.SUBSCRIPTIONS).select("id,vendor,name,status").execute().data or []
    for row in claim(store, int(settings.get("per_run") or DEFAULTS["per_run"])):
        patch: dict[str, Any] = {"error": ""}
        problems: list[str] = []
        read: dict[str, Any] = {}
        try:
            data, mime = fetch(row["image_url"])
            raw = llm.describe_image(SYSTEM, PROMPT, data, mime, max_tokens=1200) if llm is not None else None
            if raw is None:
                problems.append("the picture reader gave nothing (no vision model, or the gateway refused)")
            else:
                read = parse_read(raw)
                patch.update(read)
                patch["ai"] = raw
                counts["read"] += 1
                sid = match_subscription(read.get("vendor") or "", subs)
                if sid:
                    patch["subscription_id"] = sid
                    counts["matched"] += 1
        except SendError as exc:
            problems.append(str(exc))
        except Exception as exc:                      # noqa: BLE001
            problems.append(f"read: {type(exc).__name__}: {str(exc)[:200]}")
        # filing is its own step: a receipt read but not filed is still read, and the next run files it
        if drive is None:
            problems.append("not filed: no Google Drive (COMPOSIO_CONSUMER_KEY or settings.receipts.drive_account missing)")
        elif not row.get("drive_file_id"):
            try:
                root = str(settings.get("drive_root") or DEFAULTS["drive_root"])
                when = str(row.get("taken_at") or row.get("created_at") or now.isoformat())
                segs = drive_segments(root, read.get("doc_date") or row.get("doc_date"), when)
                out = drive.file(url=row["image_url"], name=file_name({**row, **read}, row["id"]), segments=segs)
                patch.update({"drive_file_id": out["file_id"], "drive_url": out.get("url") or "", "drive_path": "/".join(segs)})
                counts["filed"] += 1
            except Exception as exc:                  # noqa: BLE001
                problems.append(f"drive: {str(exc)[:200]}")
        done = bool(read) and bool(patch.get("drive_file_id") or row.get("drive_file_id"))
        transient = problems and row["attempts"] < MAX_ATTEMPTS and not done
        patch["status"] = "done" if done else ("pending" if transient else "error")
        patch["error"] = "; ".join(problems)[:500]
        store.table(db.RECEIPTS).update(patch).eq("id", row["id"]).execute()
        if patch["status"] == "error":
            counts["error"] += 1
            who = read.get("vendor") or row["id"][:8]
            db.log_event(store, "warn", "receipt", "receipt.failed", f"{who}: {patch['error'][:200]}",
                         ref_table=db.RECEIPTS, ref_id=row["id"])
        elif done:
            what = f"{read.get('vendor') or '?'} {read.get('currency') or ''} {read.get('total') or ''}"
            title = f"Resit dibaca dan difailkan: {what}"
            db.log_event(store, "info", "receipt", "receipt.filed", title, ref_table=db.RECEIPTS, ref_id=row["id"],
                         detail={"drive": patch.get("drive_path") or row.get("drive_path")})
    return counts


def make_llm(store: Any) -> Any | None:
    try:
        api_status.attach(store, "receipt")
        return LLM(ai_config.llm_settings(LLMSettings.load(), ai_config.read(store)))
    except Exception as exc:                          # noqa: BLE001 - no key is "not read", never a crash
        log.warning("no LLM: %s", exc)
        return None


def make_drive(settings: dict[str, Any]) -> Drive | None:
    key = os.environ.get("COMPOSIO_CONSUMER_KEY", "").strip()
    if not key:
        return None
    return Drive(key, account_email=str(settings.get("drive_account") or ""), session=requests.Session())


def run(store: Any, now: datetime | None = None, llm: Any = None, drive: Drive | None = None) -> dict[str, int]:
    now = now or datetime.now(UTC)
    settings = load_settings(store)
    reader = llm if llm is not None else make_llm(store)
    return process(store, settings, reader, drive if drive is not None else make_drive(settings), now)


def main() -> int:
    store = db.client()
    counts = run(store)
    log.info("receipts: %s", counts)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as fh:
            fh.write("## Resit\n" + "\n".join(f"- {k}: {v}" for k, v in counts.items()) + "\n")
    print(json.dumps(counts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
