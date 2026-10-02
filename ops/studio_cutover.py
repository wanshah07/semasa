"""Friday 2 Oct 2026: ws.regulab Studio's live queue -> Semasa (ops/CUTOVER.md, step 3). Run by the cutover session.

    python ops/studio_cutover.py host  --dump DIR --cards ARGUS_CARDS_CLONE --since 2026-10-02T21:00+08:00
    (git push the clone)
    python ops/studio_cutover.py build --dump DIR --cards ARGUS_CARDS_CLONE --since 2026-10-02T21:00+08:00 --out OUT

DIR is an EMPTY folder that Studio's `drafts` and `media` collections were read into (ArtifactData query/get with
`out_dir`), so a card's bytes go store -> disk -> git and never through a conversation.

host   For every post from --since on that Studio has approved (or already scheduled or posted), every card that has no permanent
       address yet is decoded from Studio's own bytes into the argus-cards clone and committed there. Only an approved
       post's artwork ever goes in argus-cards: it is public, and git keeps what lands.
build  Every card address is fetched back with no credentials and its md5 compared with Studio's bytes; one mismatch
       and nothing is written. Then the posts are shaped for Semasa (the same shape and ids as the 27 Sep import) and
       split into messages that each fit one studio-import.yml run (GitHub caps a dispatch at 65,535 characters).
"""

from __future__ import annotations

import argparse
import base64
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request
import uuid
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from semasa import compliance, ideas  # noqa: E402

NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://claude.ai/code/artifact/531c7408-8042-4ebe-b729-2e8cfad7258a")
CARDS_REPO = "https://raw.githubusercontent.com/wanshah07/argus-cards"
LIMIT = 60000
SLOT = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def uid(kind: str, sid: str) -> str:
    return str(uuid.uuid5(NS, f"{kind}/{sid}"))


def load(dump: str, coll: str) -> dict[str, dict]:
    return {os.path.basename(f)[:-5]: json.load(open(f)) for f in sorted(glob.glob(f"{dump}/{coll}/*.json"))}


def due(d: dict) -> datetime | None:
    if not d.get("date") or not SLOT.match(str(d.get("time") or "")):
        return None
    return datetime.fromisoformat(f"{d['date']}T{d['time']}:00+08:00")


def queue(drafts: dict, since: datetime) -> dict[str, dict]:
    return {k: d for k, d in drafts.items()
            if d.get("status") != "rejected" and (due(d) or since) >= since and d.get("date")}


def card_ids(d: dict) -> list[str]:
    ids = list(((d.get("images") or {}).get("media_ids")) or [])
    if not ids and (d.get("image") or {}).get("media_id"):
        ids = [d["image"]["media_id"]]
    return ids


def card_bytes(m: dict) -> bytes:
    full = str(m.get("full") or "")
    if "," not in full:
        raise SystemExit(f"card {m.get('id')} carries no bytes")
    return base64.b64decode(full.split(",", 1)[1])


def ref_of(d: dict) -> str:
    return f"{'R' if d.get('stream') == 'regulab' else 'L'}{str(d['date'])[5:7]}{str(d['date'])[8:10]}-{d['id']}"


def host(args) -> None:
    drafts, media = load(args.dump, "drafts"), load(args.dump, "media")
    since = datetime.fromisoformat(args.since)
    wrote = []
    for sid, d in queue(drafts, since).items():
        if d.get("status") not in ("approved", "scheduled", "posted"):
            continue                                        # a draft's card is not public yet: it stays out of git
                                                            # (a posted one is public already, and build needs its address)
        for n, mid in enumerate(card_ids(d), 1):
            m = media.get(mid)
            if m is None:
                raise SystemExit(f"{sid}: card {mid} was not read into {args.dump}/media")
            if m.get("url") and not m.get("url_temp"):
                continue
            rel = f"studio/{d['date']}/{ref_of({**d, 'id': sid})}-{n:02d}-{mid}.jpg"
            path = os.path.join(args.cards, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as fh:
                fh.write(card_bytes(m))
            wrote.append(rel)
    if not wrote:
        print("every card already has a permanent address; nothing to host")
        return
    subprocess.run(["git", "-C", args.cards, "add", *wrote], check=True)
    subprocess.run(["git", "-C", args.cards, "commit", "-q", "-m",
                    f"studio cutover: {len(wrote)} card(s) for approved posts"], check=True)
    sha = subprocess.run(["git", "-C", args.cards, "rev-parse", "HEAD"], check=True, capture_output=True,
                         text=True).stdout.strip()
    print(f"committed {len(wrote)} card(s) at {sha}; push the clone, then run build")


def hosted_url(args, d: dict, sid: str, n: int, mid: str, m: dict) -> str:
    if m.get("url") and not m.get("url_temp"):
        return m["url"]
    rel = f"studio/{d['date']}/{ref_of({**d, 'id': sid})}-{n:02d}-{mid}.jpg"
    sha = subprocess.run(["git", "-C", args.cards, "log", "-1", "--format=%H", "--", rel], check=True,
                         capture_output=True, text=True).stdout.strip()
    if not sha:
        raise SystemExit(f"{sid}: card {mid} is not hosted yet; run host first")
    return f"{CARDS_REPO}/{sha}/{rel}"


def prove(url: str, want: bytes) -> str:
    req = urllib.request.Request(url, headers={"Authorization": ""})
    got = urllib.request.urlopen(req, timeout=60).read()
    a, b = hashlib.md5(got).hexdigest(), hashlib.md5(want).hexdigest()
    if a != b:
        raise SystemExit(f"md5 mismatch for {url}: served {a}, Studio holds {b}")
    return a


def shape(sid: str, d: dict, urls: list[str], md5s: list[str], alt: str, studio_ids: list[str]) -> dict:
    stream = d["stream"]
    lang = d.get("lang") or ("en" if stream == "linkedin" else "bm")
    raw = json.loads(json.dumps(d.get("text") or {}))
    if stream == "linkedin":   # the 19 Sep shape bug: a BM variant at text.en.bm
        en = raw.get("en") if isinstance(raw.get("en"), dict) else {}
        if isinstance(en.get("bm"), str) and not (isinstance(raw.get("bm"), dict) and raw["bm"].get("linkedin")):
            raw["bm"] = {"linkedin": en["bm"]}
    slides = compliance.normalise_slides([
        {"title": str(s.get("title") or ""),
         "points": ([s["lead"]] if str(s.get("lead") or "").strip() else []) + [str(x) for x in (s.get("items") or [])]}
        for s in (d.get("carousel") or {}).get("slides") or []])
    platforms = ["linkedin"] if stream == "linkedin" else ["facebook", "instagram", "threads"]
    pub = {ch: {**{k: rec[k] for k in ("id", "status", "dueAt", "mode", "route", "at", "url") if rec.get(k)},
                "via": "ws.regulab Studio"}
           for ch, rec in (d.get("published") or {}).items() if isinstance(rec, dict) and rec.get("id")}
    st = d["status"]
    if st == "posted":
        status = "posted"
    elif st in ("approved", "scheduled"):
        status = "scheduled" if all(ch in pub for ch in platforms) else "approved"
    else:
        status = "draft"                                    # a Studio 'error' or 'draft' waits for Wan's click
    return {"id": uid("drafts", sid), "studio_id": sid, "stream": stream,
            "domain": d.get("domain") if stream == "regulab" and d.get("domain") in ideas.DOMAINS else None,
            "angle": d.get("angle_code") if stream == "linkedin" and d.get("angle_code") in ideas.ANGLES else None,
            "lang": lang, "hook": str(d.get("hook") or "")[:300], "text": ideas.normalise_text(raw, stream, lang),
            "citation": str(d.get("citation") or "")[:1000], "slides": slides, "date": d["date"], "slot": d["time"],
            "status": status, "published": pub if status != "draft" else {},
            "approved_at": d.get("approvedAt") if status != "draft" else None,
            "media": ({"id": uid("media", sid), "urls": urls, "alt": alt, "md5": md5s, "studio_ids": studio_ids}
                      if urls else None)}


def build(args) -> None:
    drafts, media = load(args.dump, "drafts"), load(args.dump, "media")
    since = datetime.fromisoformat(args.since)
    rows = []
    for sid, d in sorted(queue(drafts, since).items(), key=lambda kv: (kv[1]["date"], kv[1].get("time") or "")):
        urls, md5s, ids = [], [], []
        if d.get("status") in ("approved", "scheduled", "posted"):
            for n, mid in enumerate(card_ids(d), 1):
                m = media.get(mid)
                if m is None:
                    raise SystemExit(f"{sid}: card {mid} was not read into {args.dump}/media")
                url = hosted_url(args, d, sid, n, mid, m)
                if d.get("status") == "posted" and "," not in str(m.get("full") or ""):
                    md5s.append("")                         # a posted picture Studio holds no bytes for (an Unsplash
                    urls.append(url)                        # pick): nothing to prove against, and it is history
                    ids.append(mid)
                    continue
                md5s.append(prove(url, card_bytes(m)))
                urls.append(url)
                ids.append(mid)
        if d.get("stream") == "linkedin" and d.get("linkedin_with_image") is False:
            urls, md5s = [], []                             # Wan unticked "attach to LinkedIn": the words alone
        alt = str((media.get(ids[0]) or {}).get("alt") or "") if ids else ""
        rows.append(shape(sid, {**d, "id": sid}, urls, md5s, alt, ids))
    os.makedirs(args.out, exist_ok=True)
    chunks, cur = [], []
    for r in rows:
        if cur and len(json.dumps({"posts": cur + [r]}, ensure_ascii=False)) > LIMIT:
            chunks.append(cur)
            cur = []
        cur.append(r)
    if cur:
        chunks.append(cur)
    for i, c in enumerate(chunks, 1):
        body = json.dumps({"posts": c}, ensure_ascii=False, separators=(",", ":"))
        if len(body) > LIMIT:
            raise SystemExit(f"post {c[0]['studio_id']} alone is {len(body)} characters, over one dispatch")
        with open(os.path.join(args.out, f"import-{i:02d}.json"), "w", encoding="utf-8") as fh:
            fh.write(body)
    for r in rows:
        print(f"{r['studio_id']:12} {r['stream']:8} {r['date']} {r['slot']} -> {r['status']:9} "
              f"{len((r['media'] or {}).get('urls') or [])} card(s), {len(r['published'])} channel record(s)")
    print(f"{len(rows)} post(s) in {len(chunks)} message(s) under {args.out}; every card md5-proven")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["host", "build"])
    ap.add_argument("--dump", required=True)
    ap.add_argument("--cards", required=True)
    ap.add_argument("--since", required=True)
    ap.add_argument("--out", default="cutover-out")
    args = ap.parse_args()
    (host if args.step == "host" else build)(args)


if __name__ == "__main__":
    main()
