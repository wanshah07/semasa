"""Semasa on Telegram, the button menu (Wan, 16 Nov 2026: "make sure all features appear in telegram semasa button").

ONE catalogue, rules/telegram_menu.json, holds every button: the page's own segments and pages (web/src/lib/tabs.js; a test
on each side fails when a tab has no entry here, or an entry names a tab that is gone), plus the bot's own reports. /start and
/menu open the home menu, a segment button opens the segment, a page that can do something in the chat opens its own short
menu, and a page that cannot is a link straight to that page.

This module only DRAWS the menu and names what each button does. A button is one of three things:
  m:<node>   another menu (home, s:<segment>, p:<tab>), drawn where the tapped one was, or the language switch
             (m:lang:bm / m:lang:en). n:<node> is the same menu as a NEW message: the way back under an answer, so the
             answer itself (a status, an ayat, "idea sent to the writer") stays in the chat;
  a:<act>    something the worker does in the chat (ACTIONS below; telegram_bot.handle_action runs it with what the bot could
             already do: read a status, list ideas, show drafts with their own approval buttons, queue a row a worker reads);
  a URL      the page itself, at its own address (#<tab>, or #<tab>/<sub> for a choice inside a page).
Nothing here approves, publishes, deletes or spends. The webhook (supabase/functions/semasa-telegram/menu.js) draws the same
menus from a generated copy of the same file, so a tap on a menu button is answered at once; rules/telegram_menu_cases.json
holds what both must draw, and both test suites check it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RULES_PATH = ROOT / "rules" / "telegram_menu.json"
CASES_PATH = ROOT / "rules" / "telegram_menu_cases.json"
RULES: dict[str, Any] = json.loads(RULES_PATH.read_text(encoding="utf-8"))

LANGS = ("bm", "en")
SEGMENTS: list[dict[str, Any]] = RULES["segments"]
HOME: dict[str, Any] = RULES["home"]
WORDS: dict[str, Any] = RULES["words"]
LOOKS: dict[str, Any] = RULES["looks"]
PER_ROW = 2                       # buttons side by side: two is what a phone shows without cutting a label
CALLBACK_MAX = 64                 # Telegram's limit for callback_data, in bytes
Button = dict[str, str]
Reply = tuple[str, list[list[Button]]]

# What each `act` in the catalogue is, in the worker's own terms (telegram_bot.handle_action). Every power here existed before
# the menu: a command the bot already answered, a question whose answer becomes a queued row, or a read.
#   cmd     the slash command of that name, as if Wan had typed it (komik_harian: asks the Motion worker for today's comic
#           episode's STORYBOARD, comic_daily.plan_today; it spends nothing, approves nothing and posts nothing)
#   drafts  the drafts of one stream, each with its own Approve / Reject (the database gate decides, as always)
#   ideas   the newest ideas of one stream, read only
#   topic   asks for words; the next plain message becomes "/<command> <words>"
#   ask     asks for words; the answer is handled by telegram_catalogue.take_answer (a queued row, or a read-only check)
#   looks   the look buttons for a poster or a carousel, then asks for the topic
#   model   the model-by-task menu (the API page's own pins)
ACTIONS: dict[str, tuple[str, ...]] = {
    "draf": ("cmd", "draf"), "status": ("cmd", "status"), "jadual": ("cmd", "jadual"), "ralat": ("cmd", "ralat"),
    "kesihatan": ("cmd", "kesihatan"), "bil": ("cmd", "bil"), "memori": ("cmd", "memori"), "help": ("cmd", "help"),
    "komik_harian": ("cmd", "komik_harian"),
    "draf_r": ("drafts", "regulab"), "draf_l": ("drafts", "linkedin"),
    "ideas_r": ("ideas", "regulab"), "ideas_l": ("ideas", "linkedin"),
    "motion": ("topic", "motion"), "laporan": ("topic", "laporan"), "ingat": ("topic", "ingat"),
    "idea_r": ("ask", "idea", ""), "idea_l": ("ask", "idea", "linkedin"),
    "repo": ("ask", "repo", ""), "style": ("ask", "style", ""), "vague": ("ask", "vague", ""), "ayat": ("ask", "ayat", ""),
    "poster": ("looks", "poster"), "karusel": ("looks", "carousel"),
    "model": ("model",),
}


def lang_of(value: Any) -> str:
    """'en' only when it was chosen; anything else is Malay, the page's own default."""
    return "en" if value == "en" else "bm"


def label(item: dict[str, Any], lang: str) -> str:
    return (f"{item['icon']} " if item.get("icon") else "") + str(item[lang])


def page_url(site: str, target: str = "") -> str:
    """The page's address for a tab ("post") or a choice inside one ("design/comic"). The dashboard is the bare address."""
    base = str(site or "").rstrip("/") + "/"
    return base if target in ("", "papan") else f"{base}#{target}"


def segment(seg_id: str) -> dict[str, Any] | None:
    return next((s for s in SEGMENTS if s["id"] == seg_id), None)


def page(tab: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """(segment, page) for a tab id, or None."""
    for s in SEGMENTS:
        for p in s["pages"]:
            if p["tab"] == tab:
                return s, p
    return None


def tabs() -> list[str]:
    return [p["tab"] for s in SEGMENTS for p in s["pages"]]


def nodes() -> list[str]:
    """Every menu there is: home, each segment, each page that has its own menu."""
    return (["home"] + [f"s:{s['id']}" for s in SEGMENTS]
            + [f"p:{p['tab']}" for s in SEGMENTS for p in s["pages"] if p.get("items")])


def acts() -> list[str]:
    """Every `act` the catalogue names, once each, in the order met."""
    out: list[str] = []
    found = [i for i in HOME["quick"]] + [i for s in SEGMENTS for i in s.get("items", [])] \
        + [i for s in SEGMENTS for p in s["pages"] for i in p.get("items", [])]
    for i in found:
        if i.get("act") and i["act"] not in out:
            out.append(i["act"])
    return out


def _rows(buttons: list[Button], per_row: int = PER_ROW) -> list[list[Button]]:
    return [buttons[i:i + per_row] for i in range(0, len(buttons), per_row)]


def _item(item: dict[str, Any], lang: str, site: str) -> Button:
    if item.get("link"):
        return {"text": label(item, lang), "url": page_url(site, item["link"])}
    return {"text": label(item, lang), "callback_data": f"a:{item['act']}"}


def _menu(lang: str) -> Button:
    return {"text": WORDS["menu"][lang], "callback_data": "m:home"}


def home(lang: str, site: str, name: str = "Wan") -> Reply:
    other = "en" if lang == "bm" else "bm"
    rows = _rows([_item(i, lang, site) for i in HOME["quick"]])
    rows += _rows([{"text": label(s, lang), "callback_data": f"m:s:{s['id']}"} for s in SEGMENTS])
    rows.append([{"text": HOME["lang"][lang], "callback_data": f"m:lang:{other}"},
                 {"text": label(HOME["open"], lang), "url": page_url(site)}])
    return HOME["text"][lang].replace("{name}", name or "Wan"), rows


def segment_menu(seg: dict[str, Any], lang: str, site: str) -> Reply:
    lines = [f"• {p[lang]}: {p['about'][lang]}" for p in seg["pages"]]
    text = f"{label(seg, lang)}\n\n" + "\n".join(lines) + f"\n\n{WORDS['segment_hint'][lang]}"
    rows: list[list[Button]] = []
    for p in seg["pages"]:
        if p.get("items"):
            rows.append([{"text": label(p, lang), "callback_data": f"m:p:{p['tab']}"}])
        else:
            rows.append([{"text": label(p, lang), "url": page_url(site, p["tab"])}])
    rows += _rows([_item(i, lang, site) for i in seg.get("items", [])])
    rows.append([_menu(lang)])
    return text, rows


def page_menu(seg: dict[str, Any], pg: dict[str, Any], lang: str, site: str) -> Reply:
    text = f"{label(pg, lang)}\n{pg['about'][lang]}\n\n{WORDS['segment_hint'][lang]}"
    rows = [[_item(i, lang, site)] for i in pg["items"]]
    rows.append([{"text": WORDS["open_page"][lang], "url": page_url(site, pg["tab"])}])
    rows.append([{"text": f"⬅ {seg[lang]}", "callback_data": f"m:s:{seg['id']}"}, _menu(lang)])
    return text, rows


def render(node: str, lang: str, site: str, name: str = "Wan") -> Reply:
    """(text, inline keyboard) for a menu: "home", "s:<segment>" or "p:<tab>". A name nobody knows is the home menu, so an old
    button never leads nowhere."""
    lang = lang_of(lang)
    kind, _, key = str(node or "").partition(":")
    if kind == "s":
        seg = segment(key)
        if seg:
            return segment_menu(seg, lang, site)
    if kind == "p":
        found = page(key)
        if found and found[1].get("items"):
            return page_menu(found[0], found[1], lang, site)
        if found:
            return segment_menu(found[0], lang, site)
    return home(lang, site, name)


def node_of(data: str) -> str | None:
    """The menu a tapped button names ("m:s:content" and "n:s:content" → "s:content"); None for the language switch and for
    anything else."""
    if not str(data or "").startswith(("m:", "n:")):
        return None
    node = str(data)[2:]
    return None if node.startswith("lang:") else node


# ---- words the worker says around the menu --------------------------------------------------------------------------------

def back_row(lang: str, tab: str = "", keep: bool = False) -> list[Button]:
    """The way back: to the page's own menu when there is one, and always the home menu. Under a question or a picker the
    menu is drawn in its place (m:). Under an ANSWER pass `keep`: the menu comes as a new message (n:) and the answer stays."""
    found = page(tab) if tab else None
    how = "n" if keep else "m"
    row: list[Button] = []
    if found:
        seg, pg = found
        node = f"p:{pg['tab']}" if pg.get("items") else f"s:{seg['id']}"
        row.append({"text": f"⬅ {pg[lang]}", "callback_data": f"{how}:{node}"})
    row.append({"text": WORDS["menu"][lang], "callback_data": f"{how}:home"})
    return row


def open_row(lang: str, site: str, tab: str) -> list[Button]:
    """A link to the page a reply is about, with the page's own name on it."""
    found = page(tab)
    name = found[1][lang] if found else tab
    return [{"text": f"🔗 {name}", "url": page_url(site, tab)}]


TOPICS = {
    "motion": {"bm": "🎬 Idea atau pautan untuk video motion. Hantar sebagai mesej seterusnya.",
               "en": "🎬 An idea or a link for the motion video. Send it as your next message."},
    "laporan": {"bm": "📄 Laporan tentang apa? Hantar topiknya sebagai mesej seterusnya.",
                "en": "📄 A report about what? Send the topic as your next message."},
    "ingat": {"bm": "✍️ Apa yang perlu saya ingat untuk semua jawapan? Hantar sebagai mesej seterusnya.",
              "en": "✍️ What should I remember for every answer? Send it as your next message."},
}

PROMPTS = {
    "repo": {"bm": ("📚 Pustaka repo\n\nHantar pautan repositori GitHub, dengan nota selepasnya jika mahu. Semasa baca README "
                    "dan failnya, semak keselamatannya dan failkan ringkasan. Tiada apa yang diklon atau dijalankan.\n\n"
                    "Pautan lain (post, video, laman) disimpan sebagai nota sumber dan masuk barisan yang sama."),
             "en": ("📚 Repo library\n\nSend a GitHub repository link, with a note after it if you like. Semasa reads the README "
                    "and files, checks them for safety and files a summary. Nothing is cloned or run.\n\n"
                    "Another kind of link (a post, a video, a site) is saved as a source note and queued the same way.")},
    "idea": {"bm": ("💡 Idea baharu (ws.regulab)\n\nHantar pautan atau tulis ideanya. Ia pergi kepada penulis sebagai draf "
                    "ws.regulab: baris pertama dibina atas satu daripada 25 bentuk hook dan draf mesti menyebut sumbernya. "
                    "Tiada apa yang diterbitkan; anda luluskan drafnya dahulu."),
             "en": ("💡 New idea (ws.regulab)\n\nSend a link or write the idea. It goes to the idea writer as a ws.regulab "
                    "draft: the first line is built on one of the 25 hook shapes and the draft must cite its source. Nothing is "
                    "published; you approve the draft first.")},
    "idea:linkedin": {"bm": ("💡 Idea baharu (LinkedIn)\n\nHantar pautan atau tulis ideanya. Ia pergi kepada penulis sebagai "
                             "draf LinkedIn anda sendiri, dalam bahasa Inggeris, dengan sumber yang disebut. Tiada apa yang "
                             "diterbitkan; anda luluskan drafnya dahulu."),
                      "en": ("💡 New idea (LinkedIn)\n\nSend a link or write the idea. It goes to the idea writer as a draft for "
                             "your own LinkedIn, in English, with its source cited. Nothing is published; you approve the "
                             "draft first.")},
    "style": {"bm": ("✍️ Gaya penulisan\n\nHantar pautan post yang tulisannya anda suka, atau tampal teksnya (sekurang-kurangnya "
                     "80 aksara). Semasa huraikan CARA ia ditulis, bukan isinya, dan failkan di bawah Gaya penulisan."),
              "en": ("✍️ Writing style\n\nSend a link to a post whose writing you like, or paste its text (at least 80 "
                     "characters). Semasa describes how it is written, never what it says, and files it under Writing styles.")},
    "vague": {"bm": ("🔎 Semak ayat kabur\n\nTampal kapsyen atau teks slaid. Saya senaraikan frasa kabur yang tidak disokong "
                     "angka, tarikh atau nombor entri, iaitu semakan yang sama menghalang kelulusan post. Tiada apa yang "
                     "disimpan atau diubah."),
              "en": ("🔎 Vague wording check\n\nPaste a caption or a slide's text. I list the vague phrases that no figure, date "
                     "or entry number pins down: the same check that blocks a post's approval. Nothing is saved or changed.")},
    "ayat": {"bm": ("📖 Ayat al-Quran\n\nHantar rujukan sebagai surah:ayat, contohnya 2:168 atau 2:168-169. Saya ambil teks Arab "
                    "dan terjemahannya daripada sumber yang diterbitkan; ayat tidak pernah ditaip. Untuk kad, namakan rujukan "
                    "yang sama pada slaid di halaman Jana poster dan tandakan sendiri bahawa anda sudah menyemaknya."),
             "en": ("📖 Ayat al-Quran\n\nSend the reference as surah:ayat, for example 2:168 or 2:168-169. I fetch the Arabic "
                    "and its translation from a published source; a verse is never typed. For a card, name the same reference on "
                    "a slide in Generate poster and tick it as checked yourself.")},
    "poster": {"bm": "🎨 Poster · {look}\n\nHantar topik atau pautan sebagai mesej seterusnya. Semasa tulis drafnya dan lukis "
                     "poster dalam gaya ini; draf itu sampai di sini untuk anda luluskan.",
               "en": "🎨 Poster · {look}\n\nSend the topic or a link as your next message. Semasa writes the draft and draws the "
                     "poster in this look; the draft comes here for your approval."},
    "karusel": {"bm": "🖼 Carousel · {look}\n\nHantar topik atau pautan sebagai mesej seterusnya. Semasa tulis slaidnya dan lukis "
                      "dalam gaya ini; draf itu sampai di sini untuk anda luluskan.",
                "en": "🖼 Carousel · {look}\n\nSend the topic or a link as your next message. Semasa writes the slides and draws "
                      "them in this look; the draft comes here for your approval."},
}
# the page each question belongs to, for the Back button under it
ASK_TAB = {"repo": "repo", "idea": "idea", "idea:linkedin": "li-idea", "style": "gaya", "vague": "post", "ayat": "design",
           "poster": "design", "karusel": "design", "motion": "video", "laporan": "chat", "ingat": "memori"}
LOOK_KINDS = {"poster": "poster", "carousel": "karusel"}        # the catalogue's look list → the question it leads to


def look_name(look: str, lang: str) -> str:
    return str((LOOKS["names"].get(look) or {}).get(lang) or look)


def prompt(kind: str, lang: str, arg: str = "") -> Reply:
    """The question a button asks, with a way back. `arg` narrows it (the stream of an idea, the look of a poster)."""
    lang = lang_of(lang)
    key = f"{kind}:{arg}" if f"{kind}:{arg}" in PROMPTS else kind
    text = PROMPTS[key][lang].replace("{look}", look_name(arg, lang))
    return text, [back_row(lang, ASK_TAB.get(key, ""))]


def topic(action: str, lang: str) -> Reply:
    lang = lang_of(lang)
    return TOPICS[action][lang], [back_row(lang, ASK_TAB.get(action, ""))]


def looks_menu(kind: str, lang: str) -> Reply:
    """The look buttons for a poster ("poster") or a carousel ("carousel"): the default first, then two to a row."""
    lang = lang_of(lang)
    keys = list(LOOKS[kind])
    first = keys[0]
    word = "Lalai" if lang == "bm" else "Default"
    rows = [[{"text": f"✨ {word} · {look_name(first, lang)}", "callback_data": f"a:lk:{kind}:{first}"}]]
    rows += _rows([{"text": look_name(k, lang), "callback_data": f"a:lk:{kind}:{k}"} for k in keys[1:]])
    rows.append(back_row(lang, "design"))
    if kind == "poster":
        text = ("🎨 Poster daripada topik\n\nPilih gaya dahulu. Lalai ialah lukisan tangan; lapan yang lain ialah gaya poster."
                if lang == "bm" else
                "🎨 Poster from a topic\n\nPick the look first. The default is hand-drawn; the other eight are the poster looks.")
    else:
        text = ("🖼 Carousel daripada topik\n\nPilih gaya dahulu. Slaid pertama ialah muka depan poster: hook besar, teks lain "
                "bersaiz bacaan." if lang == "bm" else
                "🖼 Carousel from a topic\n\nPick the look first. The first slide is the poster front page: a large hook, the "
                "rest at reading size.")
    return text, rows


# ---- what both renderers must draw (rules/telegram_menu_cases.json) ---------------------------------------------------------

CASE_SITE = "https://semasa.example"
CASE_NAME = "Wan"


def cases() -> dict[str, Any]:
    """Every menu in both languages, in a compact form: a button is [label, "cb:<data>"] or [label, "url:<address>"]."""
    out = []
    for node in nodes():
        for lang in LANGS:
            text, rows = render(node, lang, CASE_SITE, CASE_NAME)
            out.append({"node": node, "lang": lang, "text": text,
                        "rows": [[[b["text"], f"cb:{b['callback_data']}" if "callback_data" in b else f"url:{b['url']}"]
                                  for b in row] for row in rows]})
    return {"_about": "What the Telegram menu draws for every node, in both languages (site " + CASE_SITE + ", name "
                      + CASE_NAME + "). Generated by `python ops/telegram_menu_copy.py` from rules/telegram_menu.json with the "
                      "worker's renderer (backend/semasa/telegram_menu.py); the webhook's renderer "
                      "(supabase/functions/semasa-telegram/menu.js) must draw the same, and both test suites check it.",
            "site": CASE_SITE, "name": CASE_NAME, "cases": out}
