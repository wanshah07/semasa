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


def test_a_sweep_is_budgeted_in_page_loads_and_the_handles_left_out_go_first_next_time():
    # threads costs 1 load: the budget's worth are read, the rest skipped, and the next sweep starts somewhere else
    n = experts.MAX_LOADS + 5
    many = {"enabled": True, "categories": [{"id": "ai", "name": "AI", "handles": [
        {"handle": f"h{i}", "platforms": ["threads"]} for i in range(n)]}]}
    seen = []
    rd = {"threads": lambda page, handle, now: (seen.append(handle) or ([], ""))}
    _, stats = experts.collect({"threads": object()}, experts.categories(many), many, NOW, rd)
    first = list(seen)
    seen.clear()
    experts.collect({"threads": object()}, experts.categories(many), many, NOW + timedelta(hours=6), rd)
    assert stats["reads"] == experts.MAX_LOADS and stats["skipped"] == 5 and stats["stopped"] == "pages"
    assert first != seen and len(seen) == experts.MAX_LOADS


def test_an_instagram_profile_counts_as_seven_loads_so_twenty_of_them_do_not_become_140_pages():
    ig = {"enabled": True, "categories": [{"id": "ai", "name": "AI", "handles": [
        {"handle": f"h{i}", "platforms": ["instagram"]} for i in range(20)]}]}
    seen = []
    _, stats = experts.collect({"instagram": object()}, experts.categories(ig), ig, NOW,
                               {"instagram": lambda page, handle, now: (seen.append(handle) or ([], ""))})
    assert len(seen) == experts.MAX_LOADS // experts.LOAD_COST["instagram"] == 8 and stats["loads"] == 56
    assert stats["skipped"] == 12 and stats["stopped"] == "pages"


def test_the_part_stops_cleanly_when_it_has_run_too_long_and_says_so():
    cfg = {"enabled": True, "categories": [{"id": "ai", "name": "AI", "handles": [
        {"handle": f"h{i}", "platforms": ["threads"]} for i in range(6)]}]}
    t = {"now": 0.0}
    seen = []

    def slow(page, handle, now):
        seen.append(handle)
        t["now"] += 400                                        # each profile takes 400 s; the budget is 600
        return [], ""
    _, stats = experts.collect({"threads": object()}, experts.categories(cfg), cfg, NOW, {"threads": slow},
                               clock=lambda: t["now"], budget_s=600)
    assert seen == ["h0", "h1"] and stats["skipped"] == 4 and stats["stopped"] == "time"


def test_an_account_that_gave_nothing_says_why_and_a_missing_account_does_not_stop_the_other_threads_reads():
    cfg = {"enabled": True, "hours": 336, "categories": [{"id": "ai", "name": "AI", "handles": [
        {"handle": "typo", "platforms": ["threads"]}, {"handle": "old", "platforms": ["threads"]},
        {"handle": "empty", "platforms": ["threads"]}, {"handle": "good", "platforms": ["threads"]}]}]}

    class Page:
        url = ""

    def read_url(page, url, scrolls=0, cap=0, keep_lines=False):
        if url.endswith("@typo"):
            return [], "Threads asked for a login"
        if url.endswith("@old"):
            return [post("old", "O1", "An old post", hours=24 * 400), post("someone", "O2", "a repost", hours=2)], ""
        if url.endswith("@good"):
            return [post("good", "G1", "A fresh post")], ""
        return [], ""
    import semasa.threads_web as tw
    real = tw.read_url
    tw.read_url = read_url
    try:
        posts, stats = experts.collect({"threads": Page()}, experts.categories(cfg), cfg, NOW)
    finally:
        tw.read_url = real
    assert [p["handle"] for p in posts] == ["good"], "the reads after the missing account still happened"
    assert any("@typo (Threads): account not found or private" in e and "Check the username" in e for e in stats["errors"])
    assert stats["notes"]["@old (Threads)"] == "newest post is 400 days old, outside the 14-day window"
    assert stats["notes"]["@empty (Threads)"] == "the profile showed no post of its own" and "@good (Threads)" not in stats["notes"]


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


# --- chains, and one owner with a different username on each platform (15 Nov 2026) ----------------------------------------

def chain_post(user, pid, text, minutes=0, hours=5):
    return post(user, pid, text, hours=hours) | {"timestamp": (NOW - timedelta(hours=hours) + timedelta(minutes=minutes)).isoformat()}


def page_of(*rows, error=""):
    """What a post's own page returns: the rows in the order the page lists them."""
    return lambda page, url, scrolls=0, cap=0, keep_lines=False: ([] if error else list(rows), error)


def test_a_threads_chain_is_one_post_with_every_part_in_order_and_the_roots_address():
    root = chain_post("a", "R1", "Part one makes the claim.")
    two = chain_post("a", "R2", "Part two gives the evidence.", minutes=0)
    other = chain_post("a", "SOLO", "A different post much later.", hours=1)
    out = experts.merge_chains(object(), [root, two, other], page_of(
        root | {"text": "Part one makes the claim, in full."}, two | {"text": "Part two gives the evidence, in full."}))
    assert [p["permalink"].rsplit("/", 1)[-1] for p in out] == ["R1", "SOLO"]
    chain = out[0]
    assert chain["parts"] == 2 and chain["chain_urls"] == [root["permalink"], two["permalink"]]
    assert chain["text"] == "Part one makes the claim, in full.\n\n— 2/2 —\n\nPart two gives the evidence, in full."
    assert out[1].get("parts") is None, "a post a long way from the chain is not part of it"


def test_the_listing_order_not_the_timestamps_says_which_part_is_first_and_a_part_not_confirmed_stays_alone():
    # the same second on two parts, and the later part carrying the earlier clock, as Threads really does
    first = chain_post("a", "F1", "One.", minutes=1)
    second = chain_post("a", "F2", "Two.", minutes=0)
    stray = chain_post("a", "F3", "A reply to a commenter, not a part.", minutes=3)
    out = experts.merge_chains(object(), [first, second, stray], page_of(
        first, second, {**chain_post("fan", "X1", "Great post"), "username": "fan"}, stray))
    assert [p["permalink"].rsplit("/", 1)[-1] for p in out] == ["F1", "F3"] and out[0]["parts"] == 2
    assert out[0]["text"].startswith("One.") and "— 2/2 —\n\nTwo." in out[0]["text"], "the first part listed is the root"


def test_a_page_that_cannot_be_read_leaves_the_posts_exactly_as_read():
    a, b = chain_post("a", "E1", "One."), chain_post("a", "E2", "Two.")
    assert [p["permalink"] for p in experts.merge_chains(object(), [a, b], page_of(error="timed out"))] == [a["permalink"], b["permalink"]]
    assert len(experts.merge_chains(object(), [a, b], page_of(a))) == 2, "a page that lists no continuation confirms nothing"


def test_the_threads_page_reader_keeps_paragraphs_drops_its_labels_and_never_cuts_a_long_post_at_500():
    from semasa import threads_web
    row = {"href": "/@a/post/LONG1", "datetime": "2026-11-14T10:00:00.000Z", "counts": {}, "shown": {},
           "body": ["x"], "lines": ["·", "Author", "First paragraph.\n\nSecond paragraph about\n@muse\n, and a link Translate", "y" * 3000]}
    got = threads_web._post(row, cap=4000, keep_lines=True)
    assert got["text"].startswith("First paragraph.\n\nSecond paragraph about @muse, and a link\n\n") and len(got["text"]) < 3100
    assert "Author" not in got["text"] and "Translate" not in got["text"] and len(got["text"]) > 3000
    assert len(threads_web._post(row, cap=500)["text"]) <= 500 and threads_web._post(row)["text"] == "x", "the other readers are unchanged"


def test_a_chain_comes_through_a_sweep_as_one_row_that_keeps_every_part_and_says_how_many():
    s = store()
    root = chain_post("karpathy", "C1", "An agent needs narrow tools.")
    two = chain_post("karpathy", "C2", "Measure the failure rate first.")
    posts = [root | {"text": root["text"] + "\n\n— 2/2 —\n\n" + two["text"], "parts": 2, "chain_urls": [root["permalink"], two["permalink"]]}]
    rep = run(s, table={("threads", "karpathy"): (posts, "")})
    row = s.tables["semasa_watch"][0]
    assert rep["shown"] == 1 and row["raw"]["parts"] == 2 and "Measure the failure rate first." in row["raw"]["original"]
    assert row["raw"]["chain_urls"][1].endswith("/C2")
    assert "(a chain of 2 posts)" in s.tables["semasa_brain_inbox"][0]["body"]


def test_one_owner_can_have_a_different_username_on_each_platform_and_each_is_read_by_its_own_name():
    cfg = {"enabled": True, "hours": 336, "per_handle": 5, "categories": [
        {"id": "ai", "name": "AI Expert", "brain": True, "niche": "AI", "keywords": [], "dismissed": [], "handles": [
            {"handle": "aiman", "platforms": ["threads", "instagram", "facebook"],
             "names": {"instagram": "dr.aiman", "facebook": "Aiman AI", "tiktok": "x", "threads": "AIMAN"}}]}]}
    cats = experts.categories(cfg)
    assert cats[0]["handles"] == [{"handle": "aiman", "platforms": ["threads", "instagram", "facebook"], "names": {"instagram": "dr.aiman"}}]
    asked = []
    seen = {p: (lambda page, name, now, p=p: (asked.append((p, name)) or ([post(name, f"{p}1", "An agent needs narrow tools.")]
                                                                           if p != "facebook" else [], ""))) for p in experts.PLATFORMS}
    s = store()
    rep = experts.sweep(s, Writer(), cfg, [], NOW, False, intake.have, intake.write,
                        {"threads": object(), "facebook": object(), "instagram": object()}, seen, lambda page, url: ([], ""))
    # "Aiman AI" is not a username (a space), so Facebook is read by the owner's main name rather than by a name that cannot work
    assert sorted(asked) == [("facebook", "aiman"), ("instagram", "dr.aiman"), ("threads", "aiman")]
    rows = {r["source"]: r for r in s.tables["semasa_watch"]}
    ig = rows["Instagram · @dr.aiman"]
    assert ig["raw"]["handle"] == "dr.aiman" and ig["raw"]["owner"] == "aiman" and rep["handles"] == 1
    assert rows["Threads · @aiman"]["raw"]["owner"] == "aiman"


def test_an_account_listed_twice_on_a_platform_is_read_once_and_every_name_of_an_owner_keeps_it_off_the_suggestions():
    cfg = {"enabled": True, "categories": [
        {"id": "ai", "name": "AI", "handles": [{"handle": "a", "platforms": ["threads"]}]},
        {"id": "other", "name": "Other", "handles": [{"handle": "A", "platforms": ["threads"]}]}]}
    asked = []
    experts.collect({"threads": object()}, experts.categories(cfg), cfg, NOW, {"threads": lambda p, n, now: (asked.append(n) or ([], ""))})
    assert asked == ["a"]
    cat = experts.categories({"categories": [{"id": "ai", "name": "AI", "dismissed": ["gone"], "handles": [
        {"handle": "aiman", "platforms": ["instagram"], "names": {"instagram": "dr.aiman"}}]}]})[0]
    found = [post("dr.aiman", "S1", "agent"), post("aiman", "S2", "agent"), post("gone", "S3", "agent"), post("fresh", "S4", "agent")]
    assert [c["handle"] for c in experts.candidates(found, cat, [])] == ["fresh"]


def test_a_chain_already_in_the_feed_part_by_part_is_replaced_by_one_row_once():
    s = store()
    root = chain_post("karpathy", "H1", "Sediakan folder video.")
    two = chain_post("karpathy", "H2", "Arahan setup khas.")
    for p in (root, two):
        s.tables["semasa_watch"].append({"section": "expert", "url": p["permalink"], "raw": {"category": "ai", "handle": "karpathy"}})
    s.tables["semasa_watch"].append({"section": "expert", "url": "https://www.threads.com/@karpathy/post/OTHER", "raw": {"handle": "karpathy"}})
    s.tables["semasa_brain_inbox"].append({"url": root["permalink"]})            # the old first part is already in the brain
    joined = root | {"text": "Sediakan folder video.\n\n— 2/2 —\n\nArahan setup khas.", "parts": 2,
                     "chain_urls": [root["permalink"], two["permalink"]]}
    table = {("threads", "karpathy"): ([joined], "")}
    dry = run(s, table=table, dry=True)
    assert dry["healed"] == 1 and len(s.tables["semasa_watch"]) == 3, "a dry run says what it would do and deletes nothing"
    rep = run(s, table=table)
    urls = sorted(r["url"].rsplit("/", 1)[-1] for r in s.tables["semasa_watch"])
    assert urls == ["H1", "OTHER"] and rep["healed"] == 1 and rep["chains"] == 1, "both old rows went, the unrelated one stayed, one new row came"
    new = next(r for r in s.tables["semasa_watch"] if r["url"].endswith("/H1"))
    assert new["raw"]["parts"] == 2 and "Arahan setup khas." in new["raw"]["original"]
    assert [r["url"].rsplit("/", 1)[-1] for r in s.tables["semasa_brain_inbox"]] == ["H1", "H1#thread-2"], "the brain gets the whole chain too (a row that is not the sweep's own is left alone)"
    again = run(s, table=table)
    assert again["healed"] is None and again["new"] == 0 and len(s.tables["semasa_watch"]) == 2, "healed once, never again"


def test_a_chain_that_grew_a_part_is_read_again_whole_keeps_being_hidden_and_its_old_brain_reference_goes():
    s = store()
    root = chain_post("karpathy", "G1", "One.")
    urls = [root["permalink"], root["permalink"].replace("G1", "G2"), root["permalink"].replace("G1", "G3")]
    s.tables["semasa_watch"].append({"section": "expert", "url": urls[0], "dismissed": True,
                                     "raw": {"category": "ai", "handle": "karpathy", "parts": 2, "chain_urls": urls[:2]}})
    note = "Expert content (AI Expert): a reference only, the view of one expert, not a verified fact."
    s.tables["semasa_brain_inbox"] += [{"id": "in1", "url": urls[0], "note": note}, {"id": "in2", "url": urls[0], "note": "Wan's own drop"}]
    s.tables["semasa_brain_entries"] = [
        {"id": "e1", "inbox_id": "in1", "edited": False, "pinned": False}, {"id": "e2", "inbox_id": "in1", "edited": True, "pinned": False},
        {"id": "e3", "inbox_id": "in1", "edited": False, "pinned": True}, {"id": "e4", "inbox_id": "in2", "edited": False, "pinned": False}]
    grown = root | {"text": "One.\n\n— 2/3 —\n\nTwo.\n\n— 3/3 —\n\nThree.", "parts": 3, "chain_urls": urls}
    rep = run(s, table={("threads", "karpathy"): ([grown], "")})
    row = next(r for r in s.tables["semasa_watch"] if r["url"] == urls[0])
    assert rep["healed"] == 1 and row["raw"]["parts"] == 3 and "Three." in row["raw"]["original"] and row["dismissed"] is True
    assert sorted(e["id"] for e in s.tables["semasa_brain_entries"]) == ["e2", "e3", "e4"], "an edited or pinned entry is Wan's and stays"
    kept = sorted((r["url"].rsplit("/", 1)[-1], r.get("note", "")[:6]) for r in s.tables["semasa_brain_inbox"])
    assert kept == [("G1", "Wan's "), ("G1#thread-3", "Expert")], "the sweep's own old reference went, Wan's own drop stayed"
    same = run(s, table={("threads", "karpathy"): ([grown], "")})
    assert same["healed"] is None and same["new"] == 0, "a chain of the same length is left alone"


def test_search_again_runs_the_search_before_its_day_is_up_and_the_page_is_told_what_the_search_saw():
    s = store()
    found = [post("agentsmith", "S1", "How I build an AI agent"), post("karpathy", "S2", "agent, by a followed account")]
    run(s, search=lambda page, url: (found, ""))
    value = next(r for r in s.tables["semasa_settings"] if r["key"] == "expert_suggestions")["value"]
    assert value["seen"]["ai"] == {"posts": 2, "authors": 2, "known": 1, "judged": 1, "worth": 1}
    calls = []
    search = lambda page, url: (calls.append(url) or (found, ""))            # noqa: E731
    run(s, search=search)
    assert calls == [], "not due: searched once already today"
    asked = {**CFG, "discover_request": (NOW + timedelta(seconds=1)).isoformat()}
    experts.sweep(s, Writer(), asked, [], NOW + timedelta(minutes=5), False, intake.have, intake.write,
                  {"threads": object()}, readers({}), search)
    assert len(calls) == 1, "Wan asked after the last search: it runs again"
    experts.sweep(s, Writer(), asked, [], NOW + timedelta(minutes=9), False, intake.have, intake.write,
                  {"threads": object()}, readers({}), search)
    assert len(calls) == 1, "the same request is answered once"
    assert experts.load(store(experts={"discover_request": "2026-11-14T00:00:00+00:00"}))["discover_request"].startswith("2026-11-14")
