"""Which hook shapes earn views and interaction, and what the writers are told because of it (Wan, 7 Nov 2026: "make sure
all apply the 25 Hooks, and will update the instructions automatically based on top viewers and interaction post").

A daily run (after metrics.py has refreshed `semasa_post_metrics`) measures every published post and film of the last
WINDOW_DAYS: its views and its interaction rate (reactions, comments, shares, saves, reposts, quotes, clicks over the
views, or the reach when the network gives no views), joined back to the hook shape it was written on (the idea's
`brief.hook_shape`, or a film's `check_report.hook.shape`) and the hook style it came from. Shapes are ranked on their
average views and interaction rate together; only a shape with MIN_POSTS or more results is ranked, because one lucky
post is not a pattern. The ranking is written to settings.hook_learning, and `hint()` turns the best of it into a
sentence appended to every writer's required-hook block, after every rule, so it can never lift one.

IT IS A HINT, NOT A RULE, and it is built so the learning cannot lock itself in:
  * every one of the 25 shapes (or the style's own) stays allowed; the writer is told to prefer a top shape WHEN IT
    FITS the story;
  * it is told to try a shape with fewer than MIN_POSTS results now and then, so unranked shapes keep getting
    evidence;
  * nothing of any post's own words goes into the hint (no hook is quoted or copied), only shape numbers and counts;
  * the numbers it is built from are on the card in Tetapan, and a switch (settings.hook_learning_on) turns it off;
  * LinkedIn has no figures (the connection reads none), so its posts add nothing: the ranking comes from the channels
    Buffer reads. It writes only to settings.hook_learning. It changes no post, no idea, no setting of Wan's.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from typing import Any

from . import db
from .log import get_logger

log = get_logger("semasa.hook_learning")

KEY = "hook_learning"            # the worker's result: the ranking
SWITCH_KEY = "hook_learning_on"  # Wan's switch ({"enabled": false} turns the hint off); on when absent
WINDOW_DAYS = 60
MIN_POSTS = 3                    # results a shape needs before it is ranked
TOP = 3                          # shapes named in the hint
MIN_RANKED = 2                   # shapes that must be ranked before there is anything to say


def _int(x: Any) -> int:
    try:
        return max(0, int(x or 0))
    except (TypeError, ValueError):
        return 0


def _parse(stamp: Any) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return None


def per_post(rows: list[dict[str, Any]], since: datetime) -> dict[str, dict[str, float]]:
    """{post id: {views, interactions}} summed over the post's channels, for results sent since `since`. A post with no base to
    divide by (no views, reach or impressions anywhere) is left out: a rate of nothing over nothing says nothing."""
    out: dict[str, dict[str, float]] = {}
    for m in rows:
        pid = str(m.get("post_id") or "")
        sent = _parse(m.get("sent_at"))
        if not pid or (sent and sent < since):
            continue
        base = _int(m.get("views")) or _int(m.get("reach")) or _int(m.get("impressions"))
        if not base:
            continue               # interactions with nothing to divide them by would only inflate the rate
        acts = sum(_int(m.get(k)) for k in ("reactions", "comments", "shares", "saves", "reposts", "quotes", "clicks"))
        cur = out.setdefault(pid, {"views": 0, "interactions": 0})
        cur["views"] += base
        cur["interactions"] += acts
    return {k: v for k, v in out.items() if v["views"] > 0}


def collect(store: Any, now: datetime) -> list[dict[str, Any]]:
    """[{shape, style, kind, views, rate}] for every measured post and film that carries a hook shape. Reads only; a table that
    cannot be read means no results, never an error."""
    since = now - timedelta(days=WINDOW_DAYS)

    def rows(table: str, cols: str) -> list[dict[str, Any]]:
        try:
            return store.table(table).select(cols).execute().data or []
        except Exception as exc:  # noqa: BLE001
            log.info("hook learning: %s not read (%s)", table, str(exc)[:100])
            return []

    cols = "post_id,sent_at,views,reach,impressions,reactions,comments,shares,saves,reposts,quotes,clicks"
    posts_m = per_post(rows("semasa_post_metrics", cols), since)
    if not posts_m:
        return []
    posts = {str(p["id"]): p for p in rows(db.POSTS, "id,idea_id,media_ids") if str(p.get("id")) in posts_m}
    ideas = {str(i["id"]): i for i in rows(db.IDEAS, "id,brief")}
    media = {str(g["id"]): g for g in rows(db.MEDIA, "id,meta")}
    motions = {str(f["id"]): f for f in rows("semasa_motions", "id,check_report")}
    out: list[dict[str, Any]] = []
    for pid, fig in posts_m.items():
        post = posts.get(pid) or {}
        brief = (ideas.get(str(post.get("idea_id"))) or {}).get("brief")
        brief = brief if isinstance(brief, dict) else {}
        shape, style, kind = brief.get("hook_shape"), str(brief.get("hook_style") or ""), "post"
        if not shape:                      # a film's post: post -> its media job -> the film -> the shape it was written on
            for mid in post.get("media_ids") or []:
                film = motions.get(str(((media.get(str(mid)) or {}).get("meta") or {}).get("motion_id") or ""))
                hook = ((film or {}).get("check_report") or {}).get("hook") or {}
                if hook.get("shape"):
                    shape, style, kind = hook["shape"], str(hook.get("style") or ""), "film"
                    break
        try:
            shape = int(shape)
        except (TypeError, ValueError):
            continue
        out.append({"shape": shape, "style": style, "kind": kind, "views": fig["views"],
                    "rate": fig["interactions"] / fig["views"]})
    return out


def rank(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The ranking: one entry per (style, shape) with MIN_POSTS or more results, best first. The score is the mean of the shape's
    average views and its average interaction rate, each as a share of the best shape's, so neither a viral outlier of views nor a
    tiny audience of fans decides alone."""
    groups: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for r in results:
        groups.setdefault((r["style"], r["shape"]), []).append(r)
    stats = []
    for (style, shape), items in groups.items():
        if len(items) < MIN_POSTS:
            continue
        stats.append({"style": style, "shape": shape, "n": len(items), "views": sum(i["views"] for i in items) / len(items),
                      "rate": sum(i["rate"] for i in items) / len(items),
                      "films": sum(1 for i in items if i["kind"] == "film")})
    if not stats:
        return []
    top_v, top_r = max(s["views"] for s in stats) or 1.0, max(s["rate"] for s in stats) or 1.0
    for s in stats:
        s["score"] = round((s["views"] / top_v + s["rate"] / top_r) / 2, 4)
        s["views"], s["rate"] = round(s["views"], 1), round(s["rate"], 4)
    return sorted(stats, key=lambda s: (-s["score"], -s["n"], s["shape"]))


def learn(store: Any, now: datetime | None = None) -> dict[str, Any]:
    """Measures, ranks and writes settings.hook_learning. Returns what was written."""
    now = now or datetime.now(UTC)
    results = collect(store, now)
    ranking = rank(results)
    value = {"at": now.isoformat(), "window_days": WINDOW_DAYS, "min_posts": MIN_POSTS, "measured": len(results),
             "ranking": ranking[:30]}
    try:
        store.table(db.SETTINGS).upsert({"key": KEY, "value": value}, on_conflict="key").execute()
    except Exception as exc:  # noqa: BLE001
        log.info("hook learning not saved: %s", str(exc)[:100])
    return value


def enabled(store: Any) -> bool:
    """On unless Wan switched it off; a table that cannot be read leaves it on (the hint only ever helps)."""
    try:
        rows = store.table(db.SETTINGS).select("value").eq("key", SWITCH_KEY).execute().data or []
        return bool((rows[0].get("value") or {}).get("enabled", True)) if rows else True
    except Exception:  # noqa: BLE001
        return True


def hint(store: Any, bank: Any = None) -> str:
    """The sentence appended to a writer's required-hook block, or "" when the learning is off or has nothing to say yet. For the
    built-in 25 it uses shapes from no style; for a style Wan made it uses that style's own results."""
    if store is None or not enabled(store):
        return ""
    try:
        rows = store.table(db.SETTINGS).select("value").eq("key", KEY).execute().data or []
        value = (rows[0].get("value") or {}) if rows else {}
    except Exception:  # noqa: BLE001
        return ""
    style = str(getattr(bank, "id", "") or "")
    style = "" if style == "builtin" else style
    ranked = [r for r in value.get("ranking") or [] if str(r.get("style") or "") == style]
    if len(ranked) < MIN_RANKED:
        return ""
    top = ranked[:TOP]
    names = ", ".join(str(r["shape"]) for r in top)
    days, floor = value.get("window_days", WINDOW_DAYS), value.get("min_posts", MIN_POSTS)
    return (f"WHAT HAS WORKED FOR THIS ACCOUNT (measured on real results over the last {days} days, only a hint, and every "
            f"rule above still outranks it): shapes {names} earned the most views and interaction. Prefer one of them when it "
            f"fits the story. Use another shape when none fits, and now and then a shape with fewer than {floor} results so "
            "the learning goes on. Never reuse an earlier hook's words.")


def main() -> int:
    value = learn(db.client())
    print(f"Hook learning: {value['measured']} results measured, {len(value['ranking'])} shapes ranked")
    return 0


if __name__ == "__main__":
    sys.exit(main())
