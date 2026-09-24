"""Isu Semasa scraper. Entry point: `python -m semasa.scraper` (see .github/workflows/scrape.yml).

Flow
  1. probe the LLM (records llm_ok on the run row; a dead endpoint is a RED run, not a quiet one)
  2. read every RSS/Trends source with requests, every HTML source with one shared Chromium
  3. normalise, drop stale items, dedupe against the store
  4. annotate new rows: LLM in batches, rulebook for whatever the LLM did not answer
  5. upsert (existing URLs untouched), write the run row, print a per-source table

Exit codes: 0 fine · 2 LLM configured but not answering (rows were still written) ·
3 every source failed (nothing was read — a measurement, not a zero).
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

from . import categorize, db, fetch
from .config import LLMSettings, ScraperSettings, SupabaseSettings
from .llm import LLM
from .log import get_logger
from .sources import SOURCES, Item, Source, parse_html, parse_rss, parse_trends

log = get_logger("semasa.scraper")


def collect(sources: tuple[Source, ...], settings: ScraperSettings) -> tuple[list[Item], list[dict[str, Any]]]:
    items: list[Item] = []
    report: list[dict[str, Any]] = []

    def record(src: Source, got: list[Item] | None, error: str | None = None) -> None:
        n = len(got or [])
        report.append({"name": src.name, "kind": src.kind, "ok": error is None, "items": n, "error": error})
        log.info("%-28s %-6s %s", src.name, src.kind, f"{n} items" if error is None else f"FAILED {error}")

    for src in sources:
        if src.kind in ("rss", "trends"):
            try:
                text = fetch.get(src.url, timeout=settings.request_timeout).text
                got = (parse_rss if src.kind == "rss" else parse_trends)(src, text)[: settings.max_per_source]
                items.extend(got)
                record(src, got)
            except Exception as exc:  # noqa: BLE001 - one dead feed must not end the run
                record(src, None, f"{type(exc).__name__}: {str(exc)[:160]}")

    html_sources = [s for s in sources if s.kind == "html"]
    if html_sources and settings.use_playwright:
        with fetch.browser() as b:
            for src in html_sources:
                if b is None:
                    record(src, None, "playwright unavailable")
                    continue
                try:
                    got = parse_html(src, b.page_html(src.url))[: settings.max_per_source]
                    items.extend(got)
                    record(src, got)
                except Exception as exc:  # noqa: BLE001
                    record(src, None, f"{type(exc).__name__}: {str(exc)[:160]}")
    elif html_sources:
        for src in html_sources:
            record(src, None, "skipped (SCRAPE_USE_PLAYWRIGHT=0)")
    return items, report


def dedupe_and_filter(items: list[Item], max_age_hours: int, now: datetime | None = None) -> list[Item]:
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(hours=max_age_hours)
    seen: set[str] = set()
    out: list[Item] = []
    for it in items:
        if it.url in seen or not it.title:
            continue
        if it.published_at and it.published_at < cutoff:
            continue
        seen.add(it.url)
        out.append(it)
    return out


def annotate(items: list[Item], llm: LLM | None, batch_size: int) -> list[dict[str, Any]]:
    """Every item gets a rules verdict first; the LLM then overrides what it answers.
    `summary_source` records which one the stored row actually carries."""
    rows: list[dict[str, Any]] = []
    for it in items:
        text = f"{it.title}. {it.snippet or ''}"
        rows.append({
            "title": it.title[:500],
            "source": it.source[:120],
            "url": it.url,
            "summary": it.snippet,
            "category": categorize.rules_category(text),
            "lang": categorize.detect_lang(it.title, it.lang),
            "summary_source": "rules" if it.snippet else "none",
            "published_at": it.published_at.isoformat() if it.published_at else None,
            "tags": it.tags,
            "raw": it.raw,
        })
    if llm is None:
        return rows
    for start in range(0, len(rows), batch_size):
        batch = [{"i": i, "title": rows[i]["title"], "snippet": rows[i]["summary"], "source": rows[i]["source"]}
                 for i in range(start, min(start + batch_size, len(rows)))]
        answers = categorize.llm_annotate(llm, batch)
        for i, ans in answers.items():
            rows[i]["summary"] = ans["summary"]
            rows[i]["category"] = ans["category"]
            rows[i]["summary_source"] = "llm"
            if ans["lang"]:
                rows[i]["lang"] = ans["lang"]
        log.info("LLM batch %d–%d: %d/%d answered", start, start + len(batch) - 1, len(answers), len(batch))
    return rows


def retention_cutoff(now: datetime, keep_days: int) -> str | None:
    """ISO timestamp before which rows are deleted, or None when retention is off."""
    if keep_days <= 0:
        return None
    return (now - timedelta(days=keep_days)).isoformat()


def main() -> int:
    settings = ScraperSettings.load()
    llm_settings = LLMSettings.load()
    store = db.client(SupabaseSettings.load())
    git_sha = os.environ.get("GITHUB_SHA")
    run_id = db.start_run(store, git_sha)

    llm = LLM(llm_settings)
    llm_ok = llm.probe() if llm.configured else False
    if llm.configured and not llm_ok:
        print("::error::LLM endpoint is configured but not answering — rows will be rules-only this run")

    items, report = collect(SOURCES, settings)
    ok_sources = sum(1 for r in report if r["ok"])
    fresh = dedupe_and_filter(items, settings.max_age_hours)
    log.info("read %d items from %d/%d sources; %d after dedupe/age filter", len(items), ok_sources, len(report), len(fresh))

    already = db.existing_urls(store, [it.url for it in fresh]) if fresh else set()
    new_items = [it for it in fresh if it.url not in already]
    log.info("%d already stored, %d new", len(already), len(new_items))

    rows = annotate(new_items, llm if llm_ok else None, settings.llm_batch)
    inserted = db.upsert_trends(store, rows)
    by_source = sum(1 for r in rows if r["summary_source"] == "llm")
    log.info("inserted %d rows (%d LLM-summarised, %d rules/none)", inserted, by_source, len(rows) - by_source)

    cutoff = retention_cutoff(datetime.now(UTC), settings.keep_days)
    if cutoff:
        db.prune_older_than(store, cutoff)

    db.finish_run(store, run_id, sources=report, seen=len(items), inserted=inserted, llm_ok=llm_ok,
                  llm_model=f"{llm_settings.provider}:{llm_settings.model}" if llm.configured else None,
                  note=None if ok_sources else "every source failed")

    # GitHub Actions job summary
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write(f"## Semasa scrape\n\n- read **{len(items)}**, new **{len(rows)}**, inserted **{inserted}**\n")
            fh.write(f"- LLM: {'ok' if llm_ok else 'NOT USED'} ({llm_settings.provider}:{llm_settings.model})\n\n")
            fh.write("| source | kind | ok | items | error |\n|---|---|---|---|---|\n")
            for r in report:
                fh.write(f"| {r['name']} | {r['kind']} | {'✅' if r['ok'] else '❌'} | {r['items']} | {r['error'] or ''} |\n")

    if ok_sources == 0:
        print("::error::every source failed — nothing was measured")
        return 3
    if llm.configured and not llm_ok:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
