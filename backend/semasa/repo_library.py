"""Pustaka repo: a repository Wan adds by link is READ (never cloned or run), checked for the things a reading can see,
summarised and filed under a category by the AI (Wan, 23 Oct 2026: "add REPO segment, I will add repo link and AI will
analyze and ensure it safe and make summary and categorize, for example motion repo in motion category, so for AI brain
make it separately").

One table, semasa_repo_library (supabase/042_repo_library.sql); one worker, this file, woken by the database on a new
pending row (repository_dispatch 'repo_pending') and by a daily schedule that re-reads a repo whose last push moved.

What is read, through the GitHub API with REPOS_TOKEN (read-only): the repository (description, language, licence, topics,
stars, archived, pushed_at), the README, the root file listing, the manifests that name install hooks (package.json,
pyproject.toml, setup.py, requirements.txt, Makefile, Dockerfile, the install scripts a README points at), and the names
of its workflows. That is enough to say what it is and how it runs.

The static safety checks (SAFETY_RULES) look for what a reading CAN catch: an install that pipes the internet into a
shell, a postinstall hook, eval over fetched text, a Windows "iex (New-Object Net.WebClient)", base64 handed to a shell,
miner names, a request for the user's tokens or wallet, no licence, archived or stale. The AI then reads the same material
and gives its own verdict and reasons; the stricter of the two stands, so the AI can never talk a flagged repo up to
"safe". A verdict here is a reading, not an audit: "safe" means nothing in what was read looks wrong.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from . import ai_config, api_status, db
from .llm import LLM
from .repos import GitHub

log = logging.getLogger("semasa.repo_library")
TABLE = "semasa_repo_library"
SETTINGS_KEY = "repo_library"
DEFAULT_CATEGORIES = ["motion", "video", "suara", "muzik", "imej", "3d", "kemahiran-ai", "agen-ai", "mcp", "scraper", "pelayar",
                      "regulatori", "dokumen", "web", "frontend", "api", "data", "analitik", "automasi", "pemasaran",
                      "keselamatan", "devops", "terjemahan", "alatan", "lain"]
MAX_ATTEMPTS = 3
README_MAX = 12_000
MANIFEST_MAX = 4_000
MANIFESTS = ("package.json", "pyproject.toml", "setup.py", "requirements.txt", "Makefile", "Dockerfile", "install.sh",
             "install.ps1", "start.ps1", "start.sh", "setup.sh", "Cargo.toml", "go.mod")
GITHUB_RE = re.compile(r"^https?://(?:www\.)?github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?(?:[/#?].*)?$", re.I)
SEVERITY = {"unknown": 0, "safe": 1, "caution": 2, "avoid": 3}

# (code, severity, regex, where it is looked for: "any" | "manifest" | "readme")
SAFETY_RULES: list[tuple[str, str, re.Pattern[str], str]] = [
    ("pipe_to_shell", "avoid", re.compile(r"(?:curl|wget)[^\n|]*\|\s*(?:sudo\s+)?(?:ba|z|da)?sh\b", re.I), "any"),
    ("iex_download", "avoid",
     re.compile(r"\biex\b[^\n]*(?:DownloadString|WebClient|irm\b|Invoke-RestMethod)|(?:irm|Invoke-RestMethod)[^\n]*\|\s*iex",
                re.I),
     "any"),
    ("base64_to_shell", "avoid", re.compile(r"base64\s+(?:-d|--decode)[^\n]*\|\s*(?:ba|z)?sh\b", re.I), "any"),
    ("eval_fetched", "avoid", re.compile(r"\beval\s*\(\s*(?:requests\.|urllib|fetch\(|await\s+fetch|open\(|http)", re.I), "any"),
    ("miner", "avoid", re.compile(r"\b(?:xmrig|stratum\+tcp|cryptonight|minerd|coinhive)\b", re.I), "any"),
    ("wallet_or_seed", "avoid", re.compile(r"\b(?:seed phrase|private key|wallet\.dat|metamask vault)\b", re.I), "any"),
    ("install_hook", "caution", re.compile(r"\"(?:pre|post)install\"\s*:", re.I), "manifest"),
    ("setup_runs_shell", "caution", re.compile(r"(?:os\.system|subprocess\.(?:run|call|Popen))\s*\(", re.I), "manifest"),
    ("asks_for_token", "caution",
     re.compile(r"\b(?:paste|enter|provide)\s+your\s+(?:github|openai|api|access)\s+(?:token|key)\b", re.I), "readme"),
    ("sudo_install", "caution", re.compile(r"\bsudo\s+(?:bash|sh|python\d?)\b", re.I), "any"),
    ("obfuscated", "caution", re.compile(r"[A-Za-z0-9+/]{200,}={0,2}"), "manifest"),
]
STALE_DAYS = 730

SYSTEM = """You read a GitHub repository for a Malaysian regulatory-affairs consultancy's content system (Semasa) and file it.
You are given its metadata, README, root files, manifests and workflow names. Nothing was run. Answer with ONE JSON object:
{"summary_bm": "<2 to 3 sentences in Malaysian Malay (never Indonesian): what it is, what it does, who it is for>",
 "summary_en": "<the same in English>",
 "category": "<one of: {categories}>",
 "tags": ["<3 to 6 short lowercase tags>"],
 "functions": ["<3 to 8 short lines: each thing the repo can do>"],
 "use_for": "<one or two sentences: how Semasa, Wan's consultancy work or his other systems could use it, or 'none'>",
 "how_to_run": "<the install and run steps the README gives, as one short paragraph; say which OS, runtime and keys it needs>",
 "safety": "safe" | "caution" | "avoid",
 "safety_reasons": ["<each concrete thing you saw that supports the verdict: a licence missing, an install that pipes to a
   shell, a postinstall hook, telemetry, a login to a third-party account, secrets asked for, an archived or unmaintained repo;
   or 'nothing of concern seen'>"]}
Rules for category (file by what the repo DOES, whatever it is; "motion" is only one of many): "motion" is motion graphics /
animated video made from code (HTML, GSAP, Remotion, HyperFrames); "video" is video editing, cutting, dubbing or generation;
"suara" is speech, voice cloning, TTS, transcription; "muzik" is music and sound effects; "imej" is image generation or editing;
"3d" is 3D, CAD, models; "kemahiran-ai" is agent skills, prompts, plugins for coding agents; "agen-ai" is AI agents, LLM apps,
RAG, chatbots; "mcp" is MCP servers and connectors; "scraper" is scraping or data collection; "pelayar" is browser automation
and testing; "regulatori" is regulatory, halal, cosmetics or pharma content; "dokumen" is PDF, OCR, Word, Excel, slides;
"web" is a site or web app; "frontend" is UI components and design systems; "api" is a backend, server or API framework;
"data" is datasets or databases; "analitik" is analytics, charts, dashboards; "automasi" is workflows, bots, schedulers;
"pemasaran" is social media, SEO, email, CRM; "keselamatan" is security tooling; "devops" is CI/CD, hosting, deployment;
"terjemahan" is translation and language; "alatan" is a developer tool or library; "lain" is anything else.
"functions" lists what the repo can DO, one short concrete line each (3 to 8), taken from the README, never invented.
"use_for" says how Semasa, Wan's regulatory consultancy work or his other systems could use it, or 'none'.
Be concrete and short. Never invent a feature the README does not state. If the README is empty, say so and file by the files."""


def parse_github(url: str) -> str | None:
    """owner/name from a github.com link, or None for anything else (only GitHub is read for now)."""
    m = GITHUB_RE.match((url or "").strip())
    return f"{m.group(1)}/{m.group(2)}" if m else None


def load_settings(store: Any) -> dict[str, Any]:
    rows = store.table(db.SETTINGS).select("key,value").eq("key", SETTINGS_KEY).execute().data or []
    raw = rows[0]["value"] if rows and isinstance(rows[0].get("value"), dict) else {}
    cats = [str(c).strip().lower() for c in (raw.get("categories") or []) if str(c).strip()]
    cats = list(dict.fromkeys(cats)) or list(DEFAULT_CATEGORIES)
    if "lain" not in cats:
        cats.append("lain")
    return {"categories": cats}


# --- reading ----------------------------------------------------------------------------------------------------------

def read_repo(gh: GitHub, full_name: str) -> dict[str, Any]:
    """Everything the summary is written from. Raises on a repo the token cannot see."""
    owner, name = full_name.split("/", 1)
    base = f"/repos/{owner}/{name}"
    repo = gh.get(base)
    branch = repo.get("default_branch") or "main"
    readme = gh.maybe(f"{base}/readme", raw=True, default="") or ""
    tree = gh.maybe(f"{base}/git/trees/{branch}", default={}) or {}
    files = [{"path": t.get("path"), "type": t.get("type"), "size": t.get("size") or 0}
             for t in tree.get("tree") or []][:200]
    manifests: dict[str, str] = {}
    for f in files:
        if f["type"] == "blob" and f["path"] in MANIFESTS:
            text = gh.maybe(f"{base}/contents/{f['path']}", {"ref": branch}, raw=True, default="") or ""
            if text:
                manifests[f["path"]] = text[:MANIFEST_MAX]
    wf = (gh.maybe(f"{base}/actions/workflows", default={}) or {}).get("workflows") or []
    workflows = [w.get("name") or w.get("path") for w in wf]
    languages = gh.maybe(f"{base}/languages", default={}) or {}
    head = gh.maybe(f"{base}/commits/{branch}", default={}) or {}
    return {
        "full_name": repo.get("full_name") or full_name,
        "name": repo.get("name") or name,
        "description": repo.get("description") or "",
        "html_url": repo.get("html_url") or f"https://github.com/{full_name}",
        "default_branch": branch,
        "language": repo.get("language") or "",
        "languages": languages,
        "license": ((repo.get("license") or {}).get("spdx_id") or (repo.get("license") or {}).get("name") or ""),
        "topics": repo.get("topics") or [],
        "stars": int(repo.get("stargazers_count") or 0),
        "forks": int(repo.get("forks_count") or 0),
        "archived": bool(repo.get("archived")),
        "pushed_at": repo.get("pushed_at"),
        "last_sha": (head.get("sha") or "")[:12],
        "files": files,
        "readme": readme[:README_MAX],
        "manifests": manifests,
        "workflows": workflows,
    }


# --- the static safety reading ------------------------------------------------------------------------------------------

def static_checks(info: dict[str, Any], now: datetime | None = None) -> list[dict[str, Any]]:
    """[{code, severity, where, detail}] for everything the rules find; an empty list is "nothing seen", not "safe"."""
    now = now or datetime.now(UTC)
    flags: list[dict[str, Any]] = []
    texts = {"readme": [("README", info.get("readme") or "")],
             "manifest": list((info.get("manifests") or {}).items())}
    texts["any"] = texts["readme"] + texts["manifest"]
    for code, sev, rx, where in SAFETY_RULES:
        for fname, text in texts[where]:
            m = rx.search(text)
            if m:
                end = text.find("\n", m.end())
                line = text[max(0, text.rfind("\n", 0, m.start()) + 1): end if end != -1 else None]
                flags.append({"code": code, "severity": sev, "where": fname, "detail": line.strip()[:200]})
                break
    if not info.get("license"):
        flags.append({"code": "no_license", "severity": "caution", "where": "repo",
                      "detail": "no licence: using it needs the author's permission"})
    if info.get("archived"):
        flags.append({"code": "archived", "severity": "caution", "where": "repo", "detail": "archived: no fixes will come"})
    pushed = _parse(info.get("pushed_at"))
    if pushed and now - pushed > timedelta(days=STALE_DAYS):
        flags.append({"code": "stale", "severity": "caution", "where": "repo",
                      "detail": f"last push {pushed.date().isoformat()}"})
    return flags


def _parse(s: Any) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return None


def worst(flags: list[dict[str, Any]]) -> str:
    return max((f.get("severity") or "unknown" for f in flags), key=lambda s: SEVERITY.get(s, 0), default="unknown")


# --- the AI reading ----------------------------------------------------------------------------------------------------

def build_prompt(info: dict[str, Any], flags: list[dict[str, Any]], note: str) -> str:
    parts = [
        f"Repository: {info['full_name']}  ({info.get('html_url')})",
        f"Description: {info.get('description') or '(none)'}",
        f"Language: {info.get('language') or '?'} · languages: "
        f"{', '.join(list((info.get('languages') or {}).keys())[:6]) or '?'}",
        f"Licence: {info.get('license') or 'NONE'} · stars {info.get('stars')} · archived {info.get('archived')} · "
        f"last push {info.get('pushed_at')}",
        f"Topics: {', '.join(info.get('topics') or []) or '(none)'}",
        f"Workflows: {', '.join(info.get('workflows') or []) or '(none)'}",
        "Root files: " + ", ".join(f["path"] for f in (info.get("files") or [])[:80]),
    ]
    if note:
        parts.append(f"Wan's note when adding it: {note}")
    if flags:
        parts.append("Static checks found: " + "; ".join(f"{f['code']} in {f['where']}: {f['detail']}" for f in flags))
    for fname, text in (info.get("manifests") or {}).items():
        parts.append(f"--- {fname} ---\n{text}")
    parts.append(f"--- README ---\n{info.get('readme') or '(empty)'}")
    return "\n".join(parts)


def clean(out: dict[str, Any], cats: list[str], flags: list[dict[str, Any]]) -> dict[str, Any]:
    cat = str(out.get("category") or "lain").strip().lower()
    if cat not in cats:
        cat = "lain"
    tags = [str(t).strip().lower()[:30] for t in (out.get("tags") or []) if str(t).strip()][:8]
    ai_safety = str(out.get("safety") or "unknown").strip().lower()
    if ai_safety not in SEVERITY:
        ai_safety = "unknown"
    reasons = [str(r).strip() for r in (out.get("safety_reasons") or []) if str(r).strip()][:8]
    all_flags = list(flags) + [{"code": "ai", "severity": ai_safety, "where": "AI", "detail": r[:200]} for r in reasons]
    # the stricter verdict stands: the AI may add concern, never remove a flag the rules found
    safety = max((worst(flags), ai_safety), key=lambda s: SEVERITY[s])
    if safety == "unknown":
        safety = "safe" if not flags else worst(flags)
    return {
        "summary_bm": str(out.get("summary_bm") or "").strip()[:1200],
        "summary_en": str(out.get("summary_en") or "").strip()[:1200],
        "category": cat, "tags": tags,
        "functions": [str(f).strip()[:160] for f in (out.get("functions") or []) if str(f).strip()][:8],
        "use_for": str(out.get("use_for") or "").strip()[:600],
        "how_to_run": str(out.get("how_to_run") or "").strip()[:1200],
        "safety": safety, "safety_flags": all_flags,
    }


# --- the worker --------------------------------------------------------------------------------------------------------

def claim(store: Any, limit: int = 10) -> list[dict[str, Any]]:
    q = store.table(TABLE).select("*").eq("status", "pending").order("created_at").limit(limit)
    out = []
    for r in q.execute().data or []:
        attempts = int(r.get("attempts") or 0) + 1
        got = store.table(TABLE).update({"status": "working", "attempts": attempts}) \
            .eq("id", r["id"]).eq("status", "pending").execute().data
        if got:
            out.append({**r, "attempts": attempts})
    return out


def process(store: Any, gh: GitHub, llm: Any, row: dict[str, Any], cats: list[str], now: datetime | None = None) -> bool:
    now = now or datetime.now(UTC)
    full = parse_github(row.get("url") or "")
    try:
        if not full:
            raise ValueError("only a github.com link can be read for now")
        info = read_repo(gh, full)
        flags = static_checks(info, now)
        keep = ("full_name", "name", "description", "html_url", "default_branch", "language", "languages", "license", "topics",
                "stars", "forks", "archived", "pushed_at", "last_sha", "files")
        fields: dict[str, Any] = {k: info[k] for k in keep}
        fields["readme_excerpt"] = (info.get("readme") or "")[:1500]
        out = llm.chat_json(SYSTEM.replace("{categories}", ", ".join(cats)), build_prompt(info, flags, row.get("note") or ""),
                            max_tokens=1200) if llm is not None else None
        if not isinstance(out, dict):
            # no writer: the reading still lands, with the rules' verdict, so the row is not stuck
            fields.update(safety=worst(flags) if flags else "unknown", safety_flags=flags,
                          error=("the AI gave no answer: summary missing, the static checks stand" if llm is not None
                                 else "no AI key: static checks only"))
        else:
            got = clean(out, cats, flags)
            if row.get("category_by") == "wan":
                got.pop("category")                     # Wan's own filing survives a re-read
            fields.update(got, error="", model=getattr(llm, "last_model", "") or "")
        fields.update(status="done", checked_at=now.isoformat())
        store.table(TABLE).update(fields).eq("id", row["id"]).execute()
        log.info("%s: %s · %s · %s", full, fields.get("category", row.get("category")), fields.get("safety"),
                 fields.get("model") or "rules")
        return True
    except Exception as exc:  # noqa: BLE001 - one bad repo never stops the batch
        err = f"{type(exc).__name__}: {str(exc)[:200]}"
        if "404" in err:
            err = "GitHub answered 404: the repo does not exist, or REPOS_TOKEN cannot see it"
        status = "pending" if int(row.get("attempts") or 0) < MAX_ATTEMPTS and "404" not in err else "error"
        store.table(TABLE).update({"status": status, "error": err, "checked_at": now.isoformat()}).eq("id", row["id"]).execute()
        log.warning("%s: %s (%s)", row.get("url"), err, status)
        return False


def requeue_moved(store: Any, gh: GitHub, now: datetime | None = None) -> int:
    """A done repo whose default branch moved since its summary goes back to pending, so the summary follows the repo."""
    n = 0
    rows = store.table(TABLE).select("id,url,full_name,default_branch,last_sha").eq("status", "done").execute().data or []
    for r in rows:
        full = parse_github(r.get("url") or "")
        if not full or not r.get("last_sha"):
            continue
        head = gh.maybe(f"/repos/{full}/commits/{r.get('default_branch') or 'main'}", default={}) or {}
        sha = (head.get("sha") or "")[:12]
        if sha and sha != r["last_sha"]:
            store.table(TABLE).update({"status": "pending", "attempts": 0}).eq("id", r["id"]).execute()
            n += 1
    return n


def run(store: Any, gh: GitHub, llm: Any, now: datetime | None = None, *, recheck: bool = False) -> dict[str, int]:
    now = now or datetime.now(UTC)
    cats = load_settings(store)["categories"]
    moved = requeue_moved(store, gh, now) if recheck else 0
    rows = claim(store)
    done = sum(process(store, gh, llm, r, cats, now) for r in rows)
    counts = {"claimed": len(rows), "done": done, "failed": len(rows) - done, "requeued": moved}
    if rows:
        db.log_event(store, "warn" if counts["failed"] else "info", "repos", "repo_library",
                     f"Pustaka repo: {done} dibaca, {counts['failed']} gagal" + (f", {moved} disemak semula" if moved else ""),
                     detail=counts)
    return counts


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    store = db.client()
    token = os.environ.get("REPOS_TOKEN") or os.environ.get("LANDING_REPO_TOKEN") or os.environ.get("GITHUB_TOKEN")
    llm = None
    try:
        api_status.attach(store, "repos")
        llm = LLM(ai_config.llm_for(store))
    except Exception as exc:  # noqa: BLE001 - no key is "static checks only", never a crash
        log.warning("no LLM: %s", exc)
    counts = run(store, GitHub(token), llm, recheck=os.environ.get("GITHUB_EVENT_NAME") != "repository_dispatch")
    log.info("repo library: %s", counts)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as fh:
            fh.write("## Pustaka repo\n" + "\n".join(f"- {k}: {v}" for k, v in counts.items()) + "\n")
    print(json.dumps(counts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
