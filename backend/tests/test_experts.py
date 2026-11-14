# ruff: noqa: E501  (long literals in the fixtures)
"""Expert content (14 Nov 2026): registered handles are read, analysed, kept with their own words, filed in the AI brain for a
category that asks for it, and accounts worth following are suggested from posts actually read."""

import json
from datetime import UTC, datetime, timedelta

from fakestore import FakeStore

from semasa import experts, intake, source_lights

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
CFG = {"enabled": True, "hours": 14 * 24, "per_handle": 5, "categories": [
    {"id": "ai", "name": "AI Expert", "brain": True, "niche": "AI in practice", "keywords": ["AI agent"], "dismissed": ["spammer"],
     "handles": [{"handle": "@Karpathy", "platforms": ["threads", "instagram"]}, {"handle": "karpathy", "platforms": ["threads"]},
                 {"handle": "bad handle!", "platforms": ["threads"]}, {"handle": "x", "platforms": ["tiktok"]}]},
    {"id": "halal", "name": "Halal Expert", "brain": False, "niche": "halal certification", "keywords": [], "dismissed": [],
     "handles": [{"handle": "halalguru", "platforms": ["facebook"]}]}]}


def post(user, pid, text, hours=5, **counts):
    return {"id": pid, "username": user, "text": text, "permalink": f"https://www.threads.com/@{user}/post/{pid}",
            "timestamp": (NOW - timedelta(hours=hours)).isoformat(), "counts": counts, "shown": {k: str(v) for k, v in counts.items()}}


class Writer:
    configured = True

    def __init__(self):
        self.calls = []

    def chat_json(self, system, user, **_kw):
        self.calls.append((system, user))
        rows = [json.loads(x) for x in user.splitlines()[1:]]
        if system is experts.SUGGEST_SYSTEM:
            return {"items": [{"i": r["i"], "worth": "agent" in " ".join(r["posts"]).lower(), "why": "Mengajar cara bina agen AI."}
                              for r in rows]}
        return {"items": [{"i": r["i"], "relevant": "holiday" not in r["post"], "title": "Agen AI perlukan alat yang sempit",
                           "summary": "Pakar ini menerangkan sebabnya. Beliau memberi contoh.", "why": "Hadkan alat setiap agen."}
                          for r in rows]}


def readers(table):
    return {p: (lambda page, handle, now, p=p: table.get((p, handle.lower()), ([], ""))) for p in experts.PLATFORMS}


def store(**settings):
    rows = [{"key": k, "value": v} for k, v in settings.items()]
    return FakeStore(semasa_settings=rows, semasa_watch=[], semasa_brain_inbox=[])


def run(s, cfg=CFG, table=None, pages=None, search=None, llm=None, dry=False):
    pages = pages if pages is not None else {"threads": object(), "facebook": object(), "instagram": object()}
    return experts.sweep(s, llm or Writer(), cfg, ["wsregulab"], NOW, dry, intake.have, intake.write, pages,
                         readers(table or {}), search or (lambda page, url: ([], "")))


def test_handles_are_cleaned_and_a_name_registered_twice_or_with_no_known_platform_is_dropped():
    cats = experts.categories(CFG)
    assert [h["handle"] for h in cats[0]["handles"]] == ["Karpathy"] and cats[0]["handles"][0]["platforms"] == ["threads", "instagram"]
    assert cats[1]["handles"] == [{"handle": "halalguru", "platforms": ["facebook"]}] and cats[0]["brain"] and not cats[1]["brain"]
    assert experts.clean_handle(" @a.b_c/ ") == "a.b_c" and experts.clean_handle("two words") == ""


def test_a_sweep_keeps_the_experts_own_words_beside_the_summary_and_hides_what_is_off_the_niche():
    s = store()
    table = {("threads", "karpathy"): ([post("karpathy", "T1", "An agent needs narrow tools.\nHere is why.", likes=120),
                                        post("karpathy", "T2", "On holiday this week"),
                                        post("someoneelse", "T3", "A repost on the profile page"),
                                        post("karpathy", "OLD", "ancient", hours=24 * 40)], "")}
    rep = run(s, table=table)
    rows = {r["url"].rsplit("/", 1)[-1]: r for r in s.tables["semasa_watch"]}
    assert set(rows) == {"T1", "T2"} and rep["shown"] == 1 and rep["hidden"] == 1 and rep["read"] == 2
    shown = rows["T1"]
    assert shown["section"] == "expert" and shown["relevant"] and shown["source"] == "Threads · @Karpathy"
    assert shown["raw"]["original"].startswith("An agent needs narrow tools.") and shown["raw"]["category"] == "ai"
    assert shown["raw"]["metrics"] == "120 likes" and shown["summary"].startswith("Pakar ini") and shown["title"]
    assert rows["T2"]["relevant"] is False and rows["T2"]["summary"] is None
    again = run(s, table=table)                                 # the second sweep reads the same posts and writes nothing new
    assert again["new"] == 0 and len(s.tables["semasa_watch"]) == 2


def test_only_a_category_with_the_brain_switch_files_its_posts_in_the_ai_brain_as_references_once():
    s = store()
    table = {("threads", "karpathy"): ([post("karpathy", "T1", "An agent needs narrow tools.")], ""),
             ("facebook", "halalguru"): ([{**post("halalguru", "F1", "MPPHM 2020 explained"), "permalink": "https://www.facebook.com/x/posts/F1"}], "")}
    rep = run(s, table=table)
    inbox = s.tables["semasa_brain_inbox"]
    assert rep["brain"] == 1 and len(inbox) == 1
    row = inbox[0]
    assert row["hint"] == "reference" and row["source_kind"] == "text" and row["url"].endswith("/T1")
    assert "Original post:\nAn agent needs narrow tools." in row["body"] and "Summary: Pakar ini" in row["body"]
    assert "a reference only" in row["note"]
    by = {r["raw"]["category"]: r for r in s.tables["semasa_watch"]}
    assert by["ai"]["raw"].get("brain") is True and "brain" not in by["halal"]["raw"]
    s.tables["semasa_watch"].clear()                            # even if the feed row is gone, the brain is not filed twice
    assert run(s, table=table)["brain"] == 0 and len(s.tables["semasa_brain_inbox"]) == 1


def test_a_platform_that_cannot_be_read_is_named_per_handle_and_a_login_wall_stops_that_platform_only():
    s = store()
    pages = {"threads": object(), "instagram": None, "instagram_error": "needs a saved login", "facebook": object()}
    table = {("threads", "karpathy"): ([post("karpathy", "T1", "An agent needs narrow tools.")], ""),
             ("facebook", "halalguru"): ([], "Facebook asked for a login")}
    rep = run(s, table=table, pages=pages)
    assert rep["shown"] == 1 and any("@Karpathy (Instagram): needs a saved login" in e for e in rep["errors"])
    assert any("@halalguru (Facebook): Facebook asked for a login" in e for e in rep["errors"])


def test_a_dry_run_and_a_writer_that_is_not_set_up_write_nothing():
    s = store()
    table = {("threads", "karpathy"): ([post("karpathy", "T1", "An agent needs narrow tools.")], "")}
    run(s, table=table, dry=True)
    assert s.tables["semasa_watch"] == [] and s.tables["semasa_brain_inbox"] == []

    class Off:
        configured = False
    rep = run(s, table=table, llm=Off())
    assert rep["shown"] == 0 and s.tables["semasa_watch"] == []          # unanswered: tried again next sweep, never a guess


def test_more_pages_than_one_sweep_opens_start_somewhere_else_each_sweep():
    many = {"enabled": True, "categories": [{"id": "ai", "name": "AI", "handles": [
        {"handle": f"h{i}", "platforms": ["threads"]} for i in range(experts.MAX_READS + 5)]}]}
    seen = []
    rd = {"threads": lambda page, handle, now: (seen.append(handle) or ([], ""))}
    _, stats = experts.collect({"threads": object()}, experts.categories(many), many, NOW, rd)
    first = list(seen)
    seen.clear()
    experts.collect({"threads": object()}, experts.categories(many), many, NOW + timedelta(hours=6), rd)
    assert stats["reads"] == experts.MAX_READS and stats["skipped"] == 5 and first != seen and len(seen) == experts.MAX_READS


def test_accounts_worth_following_come_only_from_posts_read_and_never_a_registered_dismissed_or_own_account():
    s = store()
    found = [post("agentsmith", "S1", "How I build an AI agent with three tools", replies=40),
             post("agentsmith", "S2", "Agent memory, step by step"),
             post("joker", "S3", "lol AI"), post("karpathy", "S4", "agent post by a registered handle"),
             post("spammer", "S5", "buy my agent course"), post("wsregulab", "S6", "our own agent post")]
    asked = []
    rep = run(s, search=lambda page, url: (asked.append(url) or (found, "")))
    lists = next(r for r in s.tables["semasa_settings"] if r["key"] == "expert_suggestions")["value"]
    assert [x["handle"] for x in lists["lists"]["ai"]] == ["agentsmith"] and rep["suggested"] == 1
    one = lists["lists"]["ai"][0]
    assert one["why"] and one["posts"] == 2 and one["platform"] == "threads" and "AI agent" in one["sample"]
    assert len(asked) == 1 and "search?q=AI%20agent" in asked[0] and lists["lists"]["halal"] == []     # halal has no search words

    again = run(s, search=lambda page, url: (_ for _ in ()).throw(AssertionError("searched twice in a day")))
    assert again["suggested"] == 0
    added = {**CFG, "categories": [{**CFG["categories"][0], "handles": [*CFG["categories"][0]["handles"],
                                                                         {"handle": "AgentSmith", "platforms": ["threads"]}]},
                                   CFG["categories"][1]]}
    run(s, cfg=added, search=lambda page, url: ([], ""))        # Wan added it: the name leaves the list at the next sweep
    lists = next(r for r in s.tables["semasa_settings"] if r["key"] == "expert_suggestions")["value"]
    assert lists["lists"]["ai"] == []


def test_the_sweep_part_opens_no_browser_with_nothing_registered_and_keeps_the_other_parts_reports():
    before = {"last_run": (NOW - timedelta(hours=3)).isoformat(),
              "report": {"community": {"ok": True, "read": {"threads": 4}}, "myra": {"ok": True, "new": 1}}}
    empty = {"enabled": True, "categories": [{"id": "ai", "name": "AI Expert", "handles": [], "keywords": []}]}
    s = store(sources=before, experts=empty)
    rep = intake.run(s, Writer(), None, now=NOW, only=["experts"])
    assert rep["experts"]["ok"] and rep["experts"]["handles"] == 0
    saved = next(r for r in s.tables["semasa_settings"] if r["key"] == "sources")["value"]
    assert saved["report"]["community"]["read"] == {"threads": 4}, "a sweep of one part must not wipe the others"
    assert saved["report"]["community"]["at"] == before["last_run"] and saved["report"]["experts"]["at"] == NOW.isoformat()
    lights = next(r for r in s.tables["semasa_settings"] if r["key"] == "source_lights")["value"]["lights"]
    assert lights["threads"]["light"] == "green" and lights["threads"]["checked"] == before["last_run"]
    assert lights["expert"]["light"] == "orange" and "no handle registered" in lights["expert"]["why"]
    assert not any("Expert" in p["area"] for p in source_lights.problems(lights))


def test_the_expert_light_is_green_when_posts_were_read_and_asks_for_help_when_handles_gave_nothing():
    base = {"enabled": True, "community": {"enabled": True}, "folders": {"enabled": True}, "myra": {"enabled": True},
            "experts": {"enabled": True}}
    at = (NOW - timedelta(hours=1)).isoformat()

    def light(rep):
        st = {"last_run": at, "report": {"experts": {"ok": True, "at": at, **rep}}}
        return source_lights.evaluate(base, st, {}, {}, {}, NOW)["expert"]
    good = light({"handles": 3, "read": 7, "shown": 2})
    assert good["light"] == "green" and "7 post(s) read from 3 handle(s), 2 new" in good["why"] and good["checked"] == at
    stuck = light({"handles": 2, "read": 0, "errors": ["@a (Instagram): needs a saved login"]})
    assert stuck["light"] == "orange" and stuck["act"] and "needs a saved login" in stuck["why"]
    quiet = light({"handles": 2, "read": 0})
    assert quiet["light"] == "orange" and not quiet.get("act")
    failed = source_lights.evaluate(base, {"last_run": at, "report": {"experts": {"ok": False, "at": at,
                                    "error": "RuntimeError: supabase/082_expert_content.sql has not been run"}}}, {}, {}, {}, NOW)
    assert failed["expert"]["light"] == "red" and "082" in failed["expert"]["why"]
