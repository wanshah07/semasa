"""Semasa on Telegram, the button menu (Wan, 16 Nov 2026: "make sure all features appear in telegram semasa button").

One catalogue (rules/telegram_menu.json) holds every button. These tests hold it to the page (web/src/lib/tabs.js: a tab with no
entry fails, and so does an entry for a tab that is gone), to Telegram's limits, to the worker's renderer and to what the bot is
allowed to do: a button reads, shows drafts with their own approval buttons, or queues a row. None approves or publishes."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from test_telegram_bot import CHAT, NOW, PIC, Bot, msg, post, tap  # noqa: E402
from test_telegram_tools import run, team_store  # noqa: E402

from semasa import db, ideas  # noqa: E402
from semasa import telegram_bot as tb
from semasa import telegram_catalogue as cat
from semasa import telegram_menu as menu
from semasa import telegram_tools as tt

ROOT = Path(__file__).resolve().parents[2]
SITE = "https://semasa.example"
TABS_JS = (ROOT / "web" / "src" / "lib" / "tabs.js").read_text(encoding="utf-8")
SYSTEM = "system"                 # the one group the sidebar does not have: Settings and the bot's own reports


# ---- the page's own list of tabs, read from its source ----------------------------------------------------------------------

def _label(expr: str) -> tuple[str, str]:
    """t("Papan", "Dashboard") → both; a bare "CRM" is the same word in both languages."""
    both = re.fullmatch(r't\("([^"]*)",\s*"([^"]*)"\)', expr.strip())
    if both:
        return both.group(1), both.group(2)
    one = re.fullmatch(r'"([^"]*)"', expr.strip())
    assert one, f"a label this test cannot read: {expr}"
    return one.group(1), one.group(1)


def page_tabs() -> list[dict[str, str]]:
    body = TABS_JS[TABS_JS.index("export function tabsOf"):TABS_JS.index("export function segmentsOf")]
    out = []
    row = r'\{\s*id:\s*"([^"]+)",\s*label:\s*(t\("[^"]*",\s*"[^"]*"\)|"[^"]*"),.*?segment:\s*"([^"]*)"\s*\}'
    for m in re.finditer(row, body):
        bm, en = _label(m.group(2))
        out.append({"id": m.group(1), "bm": bm, "en": en, "segment": m.group(3)})
    return out


def page_segments() -> list[dict[str, str]]:
    body = TABS_JS[TABS_JS.index("export function segmentsOf"):TABS_JS.index("export function segmentOf")]
    out = []
    for m in re.finditer(r'seg\("([^"]+)",\s*(t\("[^"]*",\s*"[^"]*"\)|"[^"]*"),', body):
        bm, en = _label(m.group(2))
        out.append({"id": m.group(1), "bm": bm, "en": en})
    return out


def test_the_reader_of_tabs_js_reads_every_tab_the_app_routes():
    app = (ROOT / "web" / "src" / "App.jsx").read_text(encoding="utf-8")
    ids = json.loads("[" + re.search(r"const TAB_IDS = \[([^\]]*)\]", app).group(1) + "]")
    assert sorted(t["id"] for t in page_tabs()) == sorted(ids) and len(ids) > 30
    assert len(page_segments()) >= 13


def test_every_tab_of_the_page_is_in_the_menu_and_every_menu_page_is_a_tab():
    page = {t["id"]: t for t in page_tabs()}
    held = menu.tabs()
    assert len(held) == len(set(held)), "a page is in the menu twice"
    assert sorted(page) == sorted(held), (
        f"in web/src/lib/tabs.js but not in rules/telegram_menu.json: {sorted(set(page) - set(held))}; "
        f"in the menu but no longer a tab: {sorted(set(held) - set(page))}")
    for seg in menu.SEGMENTS:
        for p in seg["pages"]:
            t = page[p["tab"]]
            assert (t["segment"] or SYSTEM) == seg["id"], f"{p['tab']} sits in {t['segment'] or 'no segment'} on the page"
            assert (p["bm"], p["en"]) == (t["bm"], t["en"]), f"{p['tab']} is named differently on the page"


def test_the_segments_are_the_pages_own_in_the_same_order_plus_the_bots_own_last():
    want = page_segments()
    got = [{"id": s["id"], "bm": s["bm"], "en": s["en"]} for s in menu.SEGMENTS]
    assert got[:-1] == want
    assert got[-1]["id"] == SYSTEM and [p["tab"] for p in menu.segment(SYSTEM)["pages"]] == ["tetapan"]
    for seg in menu.SEGMENTS[:-1]:
        on_page = [t["id"] for t in page_tabs() if t["segment"] == seg["id"]]
        assert [p["tab"] for p in seg["pages"]] == on_page, f"{seg['id']}: the pages are in the page's own order"


# ---- the tree ---------------------------------------------------------------------------------------------------------------

def buttons_of(node: str, lang: str = "bm") -> list[dict[str, str]]:
    return [b for row in menu.render(node, lang, SITE, "Wan")[1] for b in row]


def test_every_menu_is_reached_from_home_and_every_button_leads_somewhere():
    seen, todo = set(), ["home"]
    tabs = set(menu.tabs())
    while todo:
        node = todo.pop()
        if node in seen:
            continue
        seen.add(node)
        for b in buttons_of(node):
            assert ("callback_data" in b) != ("url" in b), f"{node}: {b['text']} is neither a tap nor a link"
            if "url" in b:
                assert b["url"].startswith(SITE + "/"), b
                target = b["url"][len(SITE) + 1:].lstrip("#")
                assert target == "" or target.split("/")[0] in tabs, f"{node}: {b['text']} links to no page ({target})"
                assert re.fullmatch(r"[a-z-]+(/[a-z][a-z0-9-]{0,23})?", target) or target == "", target
                continue
            kind, _, rest = b["callback_data"].partition(":")
            if kind == "a":
                assert rest in menu.ACTIONS, f"{node}: {b['text']} names an action the worker does not have ({rest})"
            else:
                assert kind == "m", b
                if not rest.startswith("lang:"):
                    assert rest in menu.nodes(), f"{node}: {b['text']} opens a menu that does not exist ({rest})"
                    todo.append(rest)
    assert seen == set(menu.nodes()), f"menus no button opens: {sorted(set(menu.nodes()) - seen)}"


def test_every_page_is_reachable_and_every_leaf_does_something_or_opens_its_page():
    reached = set()
    for node in menu.nodes():
        for b in buttons_of(node):
            if "url" in b and "#" in b["url"]:
                reached.add(b["url"].split("#", 1)[1].split("/")[0])
    assert reached | {"papan"} == set(menu.tabs()), "every page has a button that opens it (the dashboard is Open Semasa)"
    assert any(b.get("url") == SITE + "/" for b in buttons_of("home"))
    for seg in menu.SEGMENTS:
        for p in seg["pages"]:
            if not p.get("items"):
                continue                                    # a page with nothing to do in the chat is a link in its segment
            texts = [b for b in buttons_of(f"p:{p['tab']}")]
            assert any(b.get("url") == menu.page_url(SITE, p["tab"]) for b in texts), f"{p['tab']}: its own page is one tap away"
            for item in p["items"]:
                assert bool(item.get("act")) != bool(item.get("link")), f"{p['tab']}: an item is an action or a link, one of them"


def test_no_dead_ends_every_menu_but_home_has_a_way_back():
    for node in menu.nodes():
        datas = [b.get("callback_data") for b in buttons_of(node)]
        if node == "home":
            assert "m:lang:en" in datas and all(f"m:s:{s['id']}" in datas for s in menu.SEGMENTS)
            continue
        assert "m:home" in datas, f"{node} has no way back to the menu"
        if node.startswith("p:"):
            seg, _pg = menu.page(node[2:])
            assert f"m:s:{seg['id']}" in datas, f"{node} has no way back to its segment"
    assert menu.render("s:nothing", "bm", SITE)[0] == menu.render("home", "bm", SITE)[0], "an unknown menu is the home menu"
    assert menu.render("p:isu", "bm", SITE)[0].startswith("📰 Kandungan"), "a page with no menu of its own shows its segment"


def _strings(node, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _strings(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _strings(v, f"{path}[{i}]")
    elif isinstance(node, str):
        yield path, node


def test_both_languages_are_there_and_nothing_a_person_reads_has_an_em_dash():
    def both(item, where):
        assert str(item.get("bm") or "").strip() and str(item.get("en") or "").strip(), f"{where} needs both languages"
    both(menu.HOME["text"], "home text")
    both(menu.HOME["open"], "home open")
    both(menu.HOME["lang"], "home lang")
    for key, words in menu.WORDS.items():
        both(words, f"words.{key}")
    for item in menu.HOME["quick"]:
        both(item, "a quick button")
    for seg in menu.SEGMENTS:
        both(seg, seg["id"])
        for item in seg.get("items", []):
            both(item, f"{seg['id']} item")
        for p in seg["pages"]:
            both(p, p["tab"])
            both(p["about"], f"{p['tab']} about")
            for item in p.get("items", []):
                both(item, f"{p['tab']} item")
    for key, name in menu.LOOKS["names"].items():
        both(name, f"look {key}")
    for group in (menu.PROMPTS, menu.TOPICS):
        for key, words in group.items():
            both(words, key)
    said = [s for _p, s in _strings(menu.RULES) if not _p.endswith("._about")]
    said += [s for g in (menu.PROMPTS, menu.TOPICS) for w in g.values() for s in w.values()]
    for kind in ("poster", "carousel"):
        for lang in menu.LANGS:
            said.append(menu.looks_menu(kind, lang)[0])
    assert not [s for s in said if "—" in s or "–" in s], "no em dash in anything a person reads"
    indo = re.compile(r"\b(bisa|kamu|silakan|unggah|mengunduh|kirim|tautan|ponsel|gratis)\b", re.I)
    assert not [s for s in said if indo.search(s)], "Malaysian Malay only"
    # the two languages really are two: a Malay label is not just the English one again, except a name that is the same in both
    same = [p["tab"] for s in menu.SEGMENTS for p in s["pages"] if p["bm"] == p["en"]]
    assert set(same) <= {"crm", "api", "faq", "log"}


# ---- Telegram's limits ------------------------------------------------------------------------------------------------------

def _check_keyboard(rows, where):
    assert 1 <= len(rows) <= 12, f"{where}: {len(rows)} rows is too tall for a phone"
    assert sum(len(r) for r in rows) <= 100
    for row in rows:
        assert 1 <= len(row) <= menu.PER_ROW, f"{where}: {len(row)} buttons in one row"
        for b in row:
            assert 1 <= len(b["text"]) <= 40, f"{where}: a label of {len(b['text'])} characters is cut on a phone: {b['text']}"
            if "callback_data" in b:
                size = len(b["callback_data"].encode("utf-8"))
                assert 1 <= size <= menu.CALLBACK_MAX, f"{where}: callback_data of {size} bytes ({b['callback_data']})"
            else:
                assert b["url"].startswith("https://") and len(b["url"]) < 200


def test_every_menu_fits_telegrams_limits_in_both_languages():
    for node in menu.nodes():
        for lang in menu.LANGS:
            text, rows = menu.render(node, lang, SITE, "W" * 40)
            assert 0 < len(text) <= 1500, f"{node} ({lang}): a menu's text stays short"
            _check_keyboard(rows, f"{node} ({lang})")
    for kind in ("poster", "carousel"):
        for lang in menu.LANGS:
            _check_keyboard(menu.looks_menu(kind, lang)[1], f"looks {kind}")
    for group, fn in ((menu.PROMPTS, None), (menu.TOPICS, None)):
        for words in group.values():
            assert all(len(w) < 900 for w in words.values()) and fn is None
    uuid = "c6d0ceeb-c079-4b57-9f9a-8f81f064cccd"                    # the longest thing a draft card puts in a button
    for data in (f"c:pcgo:{uuid}:threads:post", f"c:scgo:{uuid}:classic:none", f"msk:{uuid}:?en"):
        assert len(data.encode()) <= menu.CALLBACK_MAX


def test_the_menu_stays_short_enough_to_use_on_a_phone():
    home = menu.render("home", "bm", SITE)[1]
    assert len(home) <= 9, "the home menu is two quick buttons, the segments two to a row, and one closing row"
    assert [b["callback_data"] for b in home[0]] == ["a:draf", "a:idea_r"], "what Wan does most is on the first row"
    deepest = max(len(menu.render(n, "bm", SITE)[1]) for n in menu.nodes() if n != "home")
    assert deepest <= 8


# ---- the generated copies ---------------------------------------------------------------------------------------------------

def test_the_cases_file_and_the_webhooks_copy_are_what_the_catalogue_gives_now():
    held = json.loads(menu.CASES_PATH.read_text(encoding="utf-8"))
    assert held == menu.cases(), "rules/telegram_menu_cases.json is behind: run `python ops/telegram_menu_copy.py`"
    assert len(held["cases"]) == 2 * len(menu.nodes())
    copy = (ROOT / "supabase" / "functions" / "semasa-telegram" / "menu_data.js").read_text(encoding="utf-8")
    body = copy[copy.index("export default ") + len("export default "):].rstrip().rstrip(";")
    assert json.loads(body) == menu.RULES, "menu_data.js is behind: run `python ops/telegram_menu_copy.py`"


def test_the_looks_offered_are_looks_the_idea_worker_draws():
    for kind in ("poster", "carousel"):
        keys = menu.LOOKS[kind]
        assert set(keys) <= set(ideas.LOOKS) and set(keys) <= set(menu.LOOKS["names"])
    assert menu.LOOKS["poster"][0] == ideas.POSTER_DEFAULT_LOOK and menu.LOOKS["carousel"][0] == ideas.DEFAULT_LOOK
    assert menu.LOOKS["poster"][1:] == ["marker", "torn", "block", "neon", "deck", "chalk", "metro", "strip"], "the eight"


# ---- the worker behind the buttons --------------------------------------------------------------------------------------------

def test_the_catalogue_and_the_worker_name_the_same_actions():
    assert set(menu.acts()) == set(menu.ACTIONS), (set(menu.acts()) ^ set(menu.ACTIONS))
    assert {spec[0] for spec in menu.ACTIONS.values()} == {"cmd", "drafts", "ideas", "topic", "ask", "looks", "model"}


def menu_store(**extra):
    posts = [post("p1"), post("p2", stream="linkedin", lang="en", angle="A", domain=None,
                              text={"en": {"linkedin": "SI 2026/109 Schedule 2 entry 325 sets a 0.5% limit from 1 March 2027."}})]
    return team_store(**{db.POSTS: posts, db.MEDIA: [PIC], "semasa_repo_library": [], "semasa_writing_styles": [], **extra})


def chat_state(st):
    return tt.chat_state(st)


def test_menu_and_start_show_the_home_menu_in_malay_until_english_is_chosen():
    st, bot = menu_store(**{tb.INBOX: [msg(1, "/menu")]}), Bot()
    run(st, bot)
    m = bot.sent()[0]
    assert m["text"].startswith("Hai wan 👋")
    assert m["reply_markup"]["inline_keyboard"] == menu.render("home", "bm", tb.SITE, "wan")[1]
    st.tables[tb.INBOX].append(tap(2, "m:lang:en"))
    run(st, bot)
    assert chat_state(st)["lang"] == "en"
    edits = [p for name, p in bot.calls if name == "editMessageText"]
    assert edits[-1]["message_id"] == 700 and edits[-1]["text"].startswith("Hi wan 👋"), "the menu is redrawn where it was"
    assert edits[-1]["reply_markup"]["inline_keyboard"] == menu.render("home", "en", tb.SITE, "wan")[1]
    st.tables[tb.INBOX].append(msg(3, "/start"))
    run(st, bot)
    assert bot.sent()[-1]["text"].startswith("Hi wan 👋"), "the choice is kept"


def test_a_segment_and_a_page_open_in_place_and_an_old_menu_button_still_leads_home():
    st, bot = menu_store(**{tb.INBOX: [tap(1, "m:s:linkedin"), tap(2, "m:p:li-post"), tap(3, "m:home")]}), Bot()
    run(st, bot)
    edits = [p for name, p in bot.calls if name == "editMessageText"]
    assert [e["text"].split("\n")[0] for e in edits] == ["💼 LinkedIn", "📝 Post LinkedIn", "Hai wan 👋 Semasa di sini."]
    assert not bot.sent(), "nothing new is sent while he only moves through the menu"
    for old in ("c:home", "menu:home", "menug:1", "m:s:gone", "a:gone"):
        st.tables[tb.INBOX].append(tap(10 + len(st.tables[tb.INBOX]), old))
    run(st, bot)
    shown = [p["text"] for name, p in bot.calls if name in ("editMessageText", "sendMessage")][-5:]
    assert all(t.startswith("Hai wan 👋") for t in shown), "a button from an older menu, or one nobody knows, opens the menu"


def test_the_way_back_under_an_answer_sends_the_menu_and_leaves_the_answer_where_it_is():
    st, bot = menu_store(**{tb.INBOX: [tap(1, "a:status"), tap(2, "n:home"), tap(3, "n:p:post")]}), Bot()
    run(st, bot)
    assert not [1 for name, _ in bot.calls if name == "editMessageText"], "the status he just read is not overwritten"
    texts = [m["text"].split("\n")[0] for m in bot.sent()]
    assert texts == [texts[0], "Hai wan 👋 Semasa di sini.", "📝 Bank post"] and texts[0].startswith("Semasa sekarang")
    assert menu.node_of("n:p:post") == "p:post" and menu.node_of("m:lang:en") is None and menu.node_of("a:status") is None
    assert [b["callback_data"] for b in menu.back_row("bm", "post", keep=True)] == ["n:p:post", "n:home"]
    assert [b["callback_data"] for b in menu.back_row("bm", "isu")] == ["m:s:content", "m:home"], "no page menu: its segment"
    # an idea that was queued is an answer and stays; a question that was not answered is still a question
    done = cat.take_answer(st, {"user_id": "u-wan"}, "idea", "https://example.com/x a topic to write about", 77)
    again = cat.take_answer(st, {"user_id": "u-wan"}, "idea", "x", 78)
    assert [b["callback_data"] for b in done[1][0]] == ["n:p:idea", "n:home"]
    assert [b["callback_data"] for b in again[1][0]] == ["m:p:idea", "m:home"]


def test_a_menu_that_cannot_be_redrawn_is_sent_and_a_menu_already_on_screen_is_left_alone():
    class Stuck(Bot):
        why = "Bad Request: message can't be edited"

        def call(self, method, **p):
            if method == "editMessageText":
                self.calls.append((method, p))
                raise tb.TelegramError(f"editMessageText: {self.why}")
            return super().call(method, **p)
    st, bot = menu_store(**{tb.INBOX: [tap(1, "m:s:poster")]}), Stuck()
    run(st, bot)
    assert bot.sent()[0]["text"].startswith("🎨 Poster")
    bot.why = "Bad Request: message is not modified"
    st.tables[tb.INBOX].append(tap(2, "m:s:poster"))
    run(st, bot)
    assert len(bot.sent()) == 1, "the same menu tapped twice is not sent a second time"


def test_a_menu_button_drops_the_question_an_earlier_button_asked():
    st, bot = menu_store(**{tb.INBOX: [tap(1, "a:idea_l")]}), Bot()
    run(st, bot)
    assert chat_state(st)["pending"] == "cat:idea:linkedin"
    st.tables[tb.INBOX].append(tap(2, "m:home"))
    run(st, bot)
    assert chat_state(st)["pending"] is None
    st.tables[tb.INBOX] += [tap(3, "a:motion"), tap(4, "a:status")]
    run(st, bot)
    assert chat_state(st)["pending"] is None, "another button drops the topic a button was waiting for"


def test_every_action_answers_with_a_way_back_and_none_approves_or_publishes():
    for i, act in enumerate(menu.ACTIONS, 1):
        st, bot = menu_store(**{tb.INBOX: [tap(i, f"a:{act}")]}), Bot()
        before = json.dumps(st.tables[db.POSTS], sort_keys=True)
        out = run(st, bot)
        assert out["errors"] == 0, f"{act} failed"
        assert bot.sent(), f"{act} said nothing"
        last = bot.sent()[-1]
        datas = [b.get("callback_data") for row in (last.get("reply_markup") or {}).get("inline_keyboard", []) for b in row]
        assert any(d and d.startswith(("m:", "n:")) for d in datas), f"{act}: the last message has no way back to the menu"
        asks = menu.ACTIONS[act][0] in ("topic", "ask", "looks", "model")
        assert any(d and d.startswith("m:" if asks else "n:") for d in datas), (
            f"{act}: a question's Back redraws it; an answer's Back sends the menu below and leaves the answer in the chat")
        assert json.dumps(st.tables[db.POSTS], sort_keys=True) == before, f"{act} changed a post"
        assert st.rpcs == [], f"{act} reached the approval gate without Wan's own tap on a draft"


def test_drafts_come_one_stream_at_a_time_with_their_own_gate_buttons_and_the_right_page_link():
    st, bot = menu_store(**{tb.INBOX: [tap(1, "a:draf_l")]}), Bot()
    run(st, bot)
    cards = [m for m in bot.sent() if m["text"].startswith("📝 Draf")]
    assert len(cards) == 1 and "LinkedIn" in cards[0]["text"]
    flat = [b for row in cards[0]["reply_markup"]["inline_keyboard"] for b in row]
    assert "ok:p2" in [b.get("callback_data") for b in flat], "Approve is the draft card's own button, through the gate"
    assert [b["url"] for b in flat if "url" in b] == [tb.SITE.rstrip("/") + "/#li-post"]
    assert "#posts" not in json.dumps(bot.calls), '"#posts" is not a page: it opened the dashboard'
    assert bot.sent()[-1]["text"] == "⬆ 1 draf (LinkedIn)."
    st2, bot2 = menu_store(**{tb.INBOX: [tap(1, "a:draf_r"), tap(2, "a:draf")]}), Bot()
    run(st2, bot2)
    cards = [m["text"] for m in bot2.sent() if m["text"].startswith("📝 Draf")]
    assert len(cards) == 3 and "LinkedIn" not in cards[0], "ws.regulab alone, then every stream"
    empty, bot3 = menu_store(**{db.POSTS: [], tb.INBOX: [tap(1, "a:draf_l")]}), Bot()
    run(empty, bot3)
    assert bot3.sent()[0]["text"] == "Tiada draf menunggu kelulusan (LinkedIn). 👍"


def test_a_linkedin_idea_and_a_ws_regulab_idea_are_queued_for_the_writer_and_listed():
    said = "https://www.legislation.gov.uk/uksi/2026/109 annex change"
    st, bot = menu_store(**{tb.INBOX: [tap(1, "a:idea_l"), msg(2, said)]}), Bot()
    run(st, bot)
    assert "LinkedIn" in bot.sent()[0]["text"]
    idea = st.tables[db.IDEAS][0]
    assert (idea["stream"], idea["status"], idea["make_slides"]) == ("linkedin", "new", False)
    assert idea["brief"]["hook_required"] and idea["brief"]["source_required"] and "format" not in idea["brief"]
    assert "LinkedIn" in bot.sent()[1]["text"] and chat_state(st)["pending"] is None
    st.tables[tb.INBOX] += [tap(3, "a:idea_r"), msg(4, "label amaran krim pemutih"), tap(5, "a:ideas_l"), tap(6, "a:ideas_r")]
    run(st, bot)
    assert [i["stream"] for i in st.tables[db.IDEAS]] == ["linkedin", "regulab"]
    li, reg = bot.sent()[-2], bot.sent()[-1]
    assert "annex change" in li["text"] and "krim pemutih" not in li["text"], "one stream to a list"
    assert "krim pemutih" in reg["text"] and li["reply_markup"]["inline_keyboard"][0][0]["url"].endswith("/#li-idea")
    assert st.tables[db.POSTS] == menu_store().tables[db.POSTS], "an idea is not a post"


def test_a_poster_and_a_carousel_ask_for_the_look_first_and_the_idea_carries_it():
    st, bot = menu_store(**{tb.INBOX: [tap(1, "a:poster")]}), Bot()
    run(st, bot)
    looks = [b["callback_data"] for row in bot.sent()[0]["reply_markup"]["inline_keyboard"] for b in row]
    assert looks[:9] == [f"a:lk:poster:{k}" for k in menu.LOOKS["poster"]]
    st.tables[tb.INBOX] += [tap(2, "a:lk:poster:neon"), msg(3, "3 perkara sebelum notifikasi kosmetik")]
    run(st, bot)
    assert "Neon" in bot.sent()[1]["text"]
    idea = st.tables[db.IDEAS][0]
    brief = idea["brief"]
    assert (brief["format"], brief["look"], idea["make_slides"], idea["stream"]) == ("poster", "neon", False, "regulab")
    assert ideas.look_of(idea) == "neon" and ideas.format_of(idea) == "poster"
    st.tables[tb.INBOX] += [tap(4, "a:karusel"), tap(5, "a:lk:carousel:era"), msg(6, "https://www.npra.gov.my/x direktif baharu")]
    run(st, bot)
    idea = st.tables[db.IDEAS][1]
    assert idea["make_slides"] is True and idea["brief"]["look"] == "era" and "format" not in idea["brief"]
    assert ideas.look_of(idea) == "era" and ideas.format_of(idea) == "carousel"
    st.tables[tb.INBOX].append(tap(7, "a:lk:poster:nothing"))
    run(st, bot)
    assert len(st.tables[db.IDEAS]) == 2 and chat_state(st)["pending"] is None, "a look nobody knows asks nothing"


def test_the_vague_wording_check_is_the_publishers_own_rule_and_changes_nothing():
    text = "The regulator updates Annex III regularly. Brands should follow recent changes."
    st, bot = menu_store(**{tb.INBOX: [tap(1, "a:vague"), msg(2, text)]}), Bot()
    run(st, bot)
    reply = bot.sent()[1]["text"]
    assert '"regularly"' in reply and '"recent changes"' in reply and reply.startswith("🔎 Frasa kabur (2)")
    assert st.tables[db.IDEAS] == [] and chat_state(st)["pending"] is None
    assert cat.check_vague("Annex III entry 325 changes on 1 March 2027.", "en")[0].startswith("🔎 No vague phrase found")
    assert cat.check_vague("   ", "en") == ("Paste the text to check.", False)


def test_an_ayat_is_fetched_from_the_published_source_never_typed(monkeypatch):
    from semasa import quran
    asked = []

    def fetch(ref, stream, client=None):
        asked.append((ref, stream))
        return {"ayat": "2:168", "ayat_ar": "يَٰٓأَيُّهَا ٱلنَّاسُ", "ayat_tr": "Wahai sekalian manusia",
                "ayat_ed": "ms.basmeih@alquran.cloud"}
    monkeypatch.setattr(quran, "fetch", fetch)
    st, bot = menu_store(**{tb.INBOX: [tap(1, "a:ayat"), msg(2, "al-baqarah 168"), msg(3, "2:168")]}), Bot()
    run(st, bot)
    assert "surah:ayat" in bot.sent()[1]["text"]
    assert asked == [("2:168", "regulab")], "words that are not a reference fetch nothing"
    reply = bot.sent()[2]["text"]
    assert "Al-Baqarah 2:168" in reply and "Wahai sekalian manusia" in reply and "ms.basmeih@alquran.cloud" in reply
    assert "tandakan sendiri" in reply, "the tick that a verse was checked stays Wan's, on the page"

    def refuse(ref, stream, client=None):
        raise quran.QuranError("the two published sources do not give the same Arabic for Al-Baqarah 2:168. It is not used.")
    monkeypatch.setattr(quran, "fetch", refuse)
    assert "It is not used" in cat.lookup_ayat("2:168", "en")[0]


def test_the_older_buttons_and_commands_still_work_beside_the_menu():
    rows = [tap(1, "c:idea"), msg(2, "https://example.com/source a useful topic"), tap(3, "menu:status"), tap(4, "c:model"),
            msg(5, "/draf")]
    st, bot = menu_store(**{tb.INBOX: rows}), Bot()
    out = run(st, bot)
    assert out["errors"] == 0 and st.tables[db.IDEAS][0]["stream"] == "regulab"
    texts = [m["text"] for m in bot.sent()]
    assert any(t.startswith("Semasa sekarang") for t in texts) and any("Model by task" in t for t in texts)
    assert sum(1 for t in texts if t.startswith("📝 Draf")) == 2 and not texts[-1].startswith("⬆"), "/draf itself is as it was"
    assert CHAT == 111 and NOW.year == 2026
