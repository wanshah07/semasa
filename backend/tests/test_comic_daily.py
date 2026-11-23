"""The daily comic series (Wan, 17 Nov 2026): isu semasa > halal > regulatory > fatwa, a storyboard first, the comic and its film
only after Wan approves it, a draft post and nothing approved. No picture maker, no reader, no renderer and no network is ever
called: the drawing, the reader and the render are plain functions here."""

from __future__ import annotations

import copy
import io
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fakestore import FakeStore
from PIL import Image

from semasa import (
    comic,
    comic_daily,
    comic_film,
    comic_library,
    comic_writer,
    motion,
    motion_review,
    motion_templates,
)

pytestmark = pytest.mark.storyboard_gate
NOW = datetime(2026, 11, 16, 22, 40, tzinfo=UTC)  # 06:40 on Tue 17 Nov 2026, Malaysia time
DAY = "2026-11-17"
SETTINGS = {"prompt": "", "cli": "0.8.188"}

NEWS_HALAL = {
    "id": "t1",
    "title": "Dua ditahan, guna sijil halal palsu jual pewarna rambut",
    "source": "Buletin TV3",
    "url": "https://news/1",
    "summary": "Dua individu ditahan kerana menggunakan sijil halal palsu untuk menjual pewarna rambut.",
    "category": "halal",
    "created_at": "2026-11-16T07:00:00+00:00",
    "published_at": None,
}
NEWS_PLAIN = {
    "id": "t2",
    "title": "Selangor rangka dasar lebih tegas premis sembelihan ayam",
    "source": "Bernama",
    "url": "https://news/2",
    "summary": "Selangor merangka dasar lebih tegas bagi memastikan premis sembelihan ayam memenuhi standard.",
    "category": "makanan",
    "created_at": "2026-11-16T06:00:00+00:00",
    "published_at": None,
}
NEWS_SPORT = {
    "id": "t3",
    "title": "Pasukan menang perlawanan akhir",
    "source": "Bernama",
    "url": "https://news/3",
    "summary": "Pasukan kebangsaan menang perlawanan akhir malam tadi dengan jaringan penentu.",
    "category": "sukan",
    "created_at": "2026-11-16T06:00:00+00:00",
    "published_at": None,
}


def watch(id_, section, domain, title, summary, **over):
    return {
        "id": id_,
        "section": section,
        "source": "X",
        "kind": "Announcement",
        "domain": domain,
        "title": title,
        "summary": summary,
        "why": "",
        "url": f"https://feed/{id_}",
        "raw": {},
        "relevant": True,
        "dismissed": False,
        "published_at": "2026-11-16T00:00:00+00:00",
        "created_at": "2026-11-16T05:20:00+00:00",
        **over,
    }


HSA = watch(
    "w2",
    "regulatory",
    "farmaseutikal",
    "Recall of Farganesse Injection 50mg/2ml (promethazine)",
    "HSA Singapura mengeluarkan notis penarikan balik untuk Farganesse Injection 50mg/2ml (promethazine).",
    source="HSA Singapore",
)
HALAL_ROW = watch(
    "w3",
    "regulatory",
    "halal_my",
    "Penarikan pengiktirafan badan pensijilan halal asing",
    "JAKIM menarik balik pengiktirafan tiga badan pensijilan asing berkuatkuasa 19 Februari 2025.",
    source="Portal Halal",
    created_at="2026-11-15T05:20:00+00:00",
)
FATWA_OK = watch(
    "w4",
    "folder",
    "fatwa",
    "Bolehkah produk kosmetik guna plasenta haiwan atau manusia?",
    "Irsyad al-Fatwa Siri Ke-281, Pejabat Mufti Wilayah Persekutuan (2019) memutuskan penggunaan plasenta manusia "
    "bagi tujuan kosmetik adalah haram.",
    source="OneDrive · Fatwa",
    published_at=None,
    raw={"cite": "Irsyad al-Fatwa Siri Ke-281, Pejabat Mufti Wilayah Persekutuan (2019)"},
    created_at="2026-09-30T21:11:00+00:00",
)
FATWA_NO_BODY = watch(
    "w5",
    "folder",
    "fatwa",
    "Adakah produk ini haram?",
    "Seorang pengguna bertanya sama ada produk itu haram dan hukumnya tidak jelas dalam catatan itu.",
    published_at=None,
    created_at="2026-09-30T21:11:00+00:00",
)
SOCIAL_FATWA = watch(
    "w6",
    "instagram",
    "fatwa",
    "SAFARA digunakan untuk sertu",
    "Jenama mengadakan peraduan tentang sertu dan samak yang difatwakan oleh Pejabat Mufti Wilayah (2019) kata mereka.",
)


def store_with(news=(), rows=(), settings=None, **tables):
    s = FakeStore(
        isu_semasa_trends=list(news),
        semasa_watch=list(rows),
        semasa_ideas=[],
        semasa_motions=[],
        semasa_posts=[],
        media_generations=[],
        semasa_settings=[],
        **tables,
    )
    s.now = "2026-11-17T00:00:00+00:00"
    for k, v in (settings or {}).items():
        s.tables["semasa_settings"].append({"key": k, "value": v})
    return s


def on(**over):
    return {"comic_series": {"enabled": True, **over}}


def motions(store):
    return store.tables["semasa_motions"]


# ------------------------------------------------------------------------------------------------------------ the series


def test_the_daily_series_is_a_whole_cast_of_ordinary_people_with_no_mascot_and_no_authority():
    lib = comic_library.library(None)
    series = comic_library.series_of(lib, comic_daily.RULES["series"])
    assert series and series["id"] == "isu-semasa-harian" and series["cast"]["A"]["name"] == "Pak Mat"
    text = json.dumps(series, ensure_ascii=False).lower()
    assert "mascot" not in text and "—" not in text
    for who in ("A", "B"):  # nobody is a religious authority or an officer who rules
        assert not any(w in series["cast"][who]["role"].lower() for w in ("ustaz", "mufti", "imam"))
    assert all(series["cast"][w][k] for w in "AB" for k in ("name", "look", "role", "voice")), (
        "no field refused for being over its limit"
    )
    assert "bukan pegawai agama" in series["cast"]["B"]["role"] and "tidak pernah memberi hukum" in series["cast"]["B"]["voice"]
    assert [d["id"] for d in comic_daily.RULES["lane_defs"]] == ["isu_semasa", "halal", "regulatori", "fatwa"]
    assert comic_daily.RULES["lanes"] == ["isu_semasa", "halal", "regulatori", "fatwa"]


def test_the_switch_is_off_unless_exactly_true_and_the_lane_list_is_wans_order():
    assert (
        comic_daily.config({})["enabled"] is False
        and comic_daily.config({"comic_series": {"enabled": "yes"}})["enabled"] is False
    )
    cfg = comic_daily.config({"comic_series": {"enabled": True, "lanes": ["fatwa", "nope", "halal", "fatwa"], "at": "25:99"}})
    assert cfg["enabled"] and cfg["lanes"] == ["fatwa", "halal"] and cfg["at"] == "06:30", (
        "unknown and repeated lanes go, a bad time too"
    )
    assert comic_daily.config({"comic_series": {"lanes": []}})["lanes"] == [], (
        "an empty list is no lane at all, never the default"
    )
    assert comic_daily.config({})["lanes"] == ["isu_semasa", "halal", "regulatori", "fatwa"]
    assert comic_daily.config({"comic_series": {"series": "gone"}})["series"] == "isu-semasa-harian"
    assert comic_daily.config({"comic_series": {"words_mode": "auto"}})["words_mode"] == "auto"
    assert comic_daily.config({"comic_series": {"words_mode": "x"}})["words_mode"] == "art"


# --------------------------------------------------------------------------------------------------- lanes and the pick


def test_an_item_that_is_a_current_issue_and_halal_ranks_first_in_the_first_lane():
    store = store_with([NEWS_HALAL, NEWS_PLAIN], [HALAL_ROW, HSA])
    item, trail = comic_daily.pick(store, comic_daily.config(on()), NOW)
    assert (
        item["lane"] == "isu_semasa"
        and item["id"] == "t1"
        and trail == [{"lane": "isu_semasa", "read": 1, "refused": {}, "picked": True}]
    ), "a headline with no regulator or rule in it is not read"


def test_a_headline_with_no_rule_in_it_is_not_this_brands_business():
    store = store_with([NEWS_SPORT], [])
    item, trail = comic_daily.pick(store, comic_daily.config(on(lanes=["isu_semasa"])), NOW)
    assert item is None and trail[0]["read"] == 0, "sport is not even read: the lane reads headlines that name a rule"


def test_the_lanes_are_tried_in_order_and_an_empty_lane_is_skipped():
    store = store_with([], [HALAL_ROW, HSA, FATWA_OK])
    item, trail = comic_daily.pick(store, comic_daily.config(on()), NOW)
    assert item["lane"] == "halal" and item["id"] == "w3"
    assert [t["lane"] for t in trail] == ["isu_semasa", "halal"] and trail[0]["read"] == 0
    # Wan's order is honoured: regulatori first picks the regulator notice, and a lane he switched off is never read
    item, trail = comic_daily.pick(store, comic_daily.config(on(lanes=["regulatori", "halal"])), NOW)
    assert item["lane"] == "regulatori" and item["id"] == "w2" and len(trail) == 1
    item, _ = comic_daily.pick(store, comic_daily.config(on(lanes=["fatwa"])), NOW)
    assert item["lane"] == "fatwa" and item["id"] == "w4"


def test_a_day_with_no_fitting_item_in_any_lane_picks_nothing_and_says_why_in_every_lane():
    store = store_with([NEWS_SPORT], [FATWA_NO_BODY, SOCIAL_FATWA])
    item, trail = comic_daily.pick(store, comic_daily.config(on()), NOW)
    assert item is None and [t["lane"] for t in trail] == ["isu_semasa", "halal", "regulatori", "fatwa"]
    fatwa = trail[-1]
    assert fatwa["read"] == 1 and fatwa["refused"] == {"no_issuing_body_and_date": 1}, "the social row is never even read"
    words = comic_daily.trail_words(trail, ["isu_semasa", "halal", "regulatori", "fatwa"])
    assert "Fatwa: read 1, refused 1 no issuing body and date" in words and "Current issue: read 0" in words


def test_a_social_post_is_never_a_source_even_when_it_is_tagged_fatwa():
    store = store_with([], [SOCIAL_FATWA])
    item, trail = comic_daily.pick(store, comic_daily.config(on(lanes=["fatwa"])), NOW)
    assert item is None and trail[0]["read"] == 0


def test_a_story_already_told_or_already_published_is_not_told_again():
    told = {
        "id": "m0",
        "status": "done",
        "options": {"template": "comic", "series": {"item": {"title": NEWS_HALAL["title"], "url": "https://other/url"}}},
    }
    store = store_with([NEWS_HALAL], [])
    store.tables["semasa_motions"].append(told)
    item, trail = comic_daily.pick(store, comic_daily.config(on(lanes=["isu_semasa"])), NOW)
    assert item is None and trail[0]["refused"] == {"already_told": 1}
    store = store_with([NEWS_HALAL], [])
    store.tables["semasa_ideas"].append({"id": "i1", "stream": "regulab", "trend_id": "t1", "source_url": "https://news/1"})
    store.tables["semasa_posts"].append({"id": "p1", "idea_id": "i1", "status": "posted"})
    item, trail = comic_daily.pick(store, comic_daily.config(on(lanes=["isu_semasa"])), NOW)
    assert item is None and trail[0]["refused"] == {"already_published": 1}, (
        "a posted story is never recreated (Wan, 25 Sep 2026)"
    )
    store = store_with([NEWS_HALAL], [])
    store.tables["semasa_motions"].append({**told, "status": "rejected"})
    assert comic_daily.pick(store, comic_daily.config(on(lanes=["isu_semasa"])), NOW)[0] is None, (
        "a rejected one is not retold either"
    )


def test_a_story_an_idea_has_not_used_comes_before_one_it_has():
    other = {
        **NEWS_HALAL,
        "id": "t9",
        "title": "Sijil halal tiruan dirampas di pasar raya",
        "url": "https://news/9",
        "summary": "Sijil halal tiruan dirampas di sebuah pasar raya selepas pemeriksaan penguat kuasa.",
    }
    store = store_with([NEWS_HALAL, other], [])
    store.tables["semasa_ideas"].append({"id": "i1", "stream": "regulab", "source_url": "https://news/9", "status": "new"})
    item, _ = comic_daily.pick(store, comic_daily.config(on(lanes=["isu_semasa"])), NOW)
    assert item["id"] == "t1"


# --------------------------------------------------------------------------------- the ruling rules (halal and fatwa)


def test_a_ruling_is_used_only_when_the_row_gives_the_issuing_body_and_its_date():
    got = comic_daily.ruling_source(FATWA_OK)
    assert got == {"body": "Pejabat Mufti Wilayah Persekutuan", "statement": FATWA_OK["raw"]["cite"], "date": "2019"}
    assert comic_daily.ruling_source(FATWA_NO_BODY) is None
    no_date = {**FATWA_OK, "raw": {}, "summary": "Pejabat Mufti Wilayah Persekutuan memutuskan penggunaan plasenta itu haram."}
    assert comic_daily.ruling_source(no_date) is None, "a body with no date is not enough"
    dated = {**no_date, "published_at": "2026-11-10T00:00:00+00:00"}
    assert comic_daily.ruling_source(dated)["date"] == "10 Nov 2026"
    assert comic_daily.refusal(FATWA_NO_BODY, "fatwa", keys=set(), urls=set()) == "no_issuing_body_and_date"
    assert comic_daily.refusal(FATWA_OK, "fatwa", keys=set(), urls=set()) == ""
    plain = watch(
        "w7",
        "folder",
        "fatwa",
        "Tinjauan pengguna tentang produk",
        "Pejabat Mufti Wilayah Persekutuan menerbitkan tinjauan 2020 tentang kebiasaan membeli produk harian di kedai runcit.",
        published_at=None,
    )
    assert comic_daily.refusal(plain, "fatwa", keys=set(), urls=set()) == "not_a_ruling", (
        "a row tagged fatwa that rules on nothing"
    )


def test_a_halal_row_that_talks_about_a_ruling_needs_the_body_and_date_too():
    row = watch(
        "w8",
        "regulatory",
        "halal_my",
        "Produk itu dinyatakan haram oleh seorang ustaz",
        "Seorang ustaz menyatakan produk itu haram dalam satu video, kata laporan.",
    )
    assert (
        comic_daily.sensitive(row, "halal")
        and comic_daily.refusal(row, "halal", keys=set(), urls=set()) == "no_issuing_body_and_date"
    )
    assert comic_daily.refusal(HALAL_ROW, "halal", keys=set(), urls=set()) == "", "a halal notice that rules on nothing is fine"


def test_the_source_line_is_built_from_the_row_never_by_the_writer():
    assert comic_daily.source_line(FATWA_OK, comic_daily.ruling_source(FATWA_OK)) == FATWA_OK["raw"]["cite"]
    assert comic_daily.source_line(HSA, None).startswith("HSA: Recall of Farganesse") and HSA["raw"] == {}
    assert (
        comic_daily.source_line({**NEWS_HALAL, "section": "news", "published_at": "2026-11-16T07:00:00+00:00"}, None)
        == "Buletin TV3, 16 Nov 2026"
    )
    ruled = comic_daily.ruling_source({**FATWA_OK, "raw": {}, "published_at": "2026-11-10T00:00:00+00:00"})
    assert comic_daily.source_line({**FATWA_OK, "raw": {}}, ruled).startswith("Pejabat Mufti Wilayah Persekutuan: ")


RULING = {"body": "Pejabat Mufti Wilayah Persekutuan", "statement": "Irsyad al-Fatwa Siri Ke-281", "date": "2019"}


@pytest.mark.parametrize(
    "text, ruling, expect",
    [
        ("Pejabat Mufti Wilayah Persekutuan menyatakan plasenta manusia haram untuk kosmetik.", RULING, 0),
        ("Haram tu, Pak Mat.", RULING, 1),  # a ruling, no body named
        ("Hukumnya haram.", None, 1),  # a ruling and the row has none
        ("Saya putuskan produk ini halal.", RULING, 1),  # a character rules
        ("Hukumnya ialah haram, saya fatwakan.", RULING, 1),
        ("Dalam surah Al-Baqarah ayat 168 Allah berfirman.", RULING, 1),  # a verse, never typed
        ("بسم الله", RULING, 1),  # Arabic script, never typed
        ("Hadis riwayat Bukhari menyebut perkara itu.", RULING, 1),
        ("Sijil halal itu palsu dan dua orang ditahan.", None, 0),  # a halal certificate is not a ruling
        ("Notis itu menyatakan tarikh berkuat kuasa ialah 19 Februari 2025.", None, 0),
    ],
)
def test_a_character_never_rules_and_a_reported_position_names_who_issued_it(text, ruling, expect):
    assert len(comic_daily.ruling_problems([text], ruling)) == expect


# ------------------------------------------------------------------------------------------------ the plan, once a day


def planned(store, **kw):
    return comic_daily.plan_today(
        store,
        comic_daily.load_settings(store)
        if hasattr(comic_daily, "load_settings")
        else {r["key"]: r["value"] for r in store.tables["semasa_settings"]},
        NOW,
        **kw,
    )


def test_the_series_is_off_by_default_and_a_paused_one_makes_nothing():
    store = store_with([NEWS_HALAL], [])
    assert planned(store)["status"] == "off" and motions(store) == []
    store = store_with([NEWS_HALAL], [], on(paused=True))
    assert planned(store)["status"] == "paused" and motions(store) == []


def test_nothing_is_planned_before_the_hour_and_a_late_run_still_plans_it():
    early = datetime(2026, 11, 16, 21, 59, tzinfo=UTC)  # 05:59 MYT, before 06:30
    store = store_with([NEWS_HALAL], [], on())
    assert comic_daily.plan_today(store, {"comic_series": {"enabled": True}}, early)["status"] == "early"
    assert (
        comic_daily.plan_today(store, {"comic_series": {"enabled": True}}, datetime(2026, 11, 17, 9, 0, tzinfo=UTC))["status"]
        == "planned"
    ), "GitHub's late schedule: the hourly run at 17:00 MYT still makes the day's episode"


def test_one_episode_a_malaysian_day_and_a_rerun_makes_nothing_new():
    store = store_with([NEWS_HALAL, NEWS_PLAIN], [], on())
    first = planned(store)
    assert first["status"] == "planned" and first["lane"] == "isu_semasa" and first["episode"] == 1
    row = motions(store)[0]
    assert row["status"] == "pending" and row["stream"] == "regulab" and row["options"]["template"] == "comic"
    sx = row["options"]["series"]
    assert sx["day"] == DAY and sx["id"] == "isu-semasa-harian" and sx["item"]["title"] == NEWS_HALAL["title"]
    assert sx["source"] == "Buletin TV3" or sx["source"].startswith("Buletin TV3"), "the source is built from the row"
    again = planned(store)
    assert again["status"] == "exists" and len(motions(store)) == 1, "a re-run the same MYT day makes nothing new"
    # the next Malaysian day (22:40 UTC is 06:40 MYT) is a new day with the next episode number
    later = datetime(2026, 11, 17, 22, 40, tzinfo=UTC)
    motions(store)[0]["status"] = "done"
    store.tables["isu_semasa_trends"].append(
        {
            **NEWS_HALAL,
            "id": "t8",
            "url": "https://news/8",
            "created_at": "2026-11-17T20:00:00+00:00",
            "title": "Sijil halal tiruan dirampas di pasar raya selepas pemeriksaan",
        }
    )
    res = comic_daily.plan_today(store, {"comic_series": {"enabled": True}}, later)
    assert res["status"] == "planned" and res["episode"] == 2 and len(motions(store)) == 2


def test_the_day_is_the_malaysian_day_not_the_utc_one():
    assert comic_daily.myt_day(datetime(2026, 11, 16, 16, 30, tzinfo=UTC)) == "2026-11-17"
    assert comic_daily.myt_day(datetime(2026, 11, 16, 15, 59, tzinfo=UTC)) == "2026-11-16"


def test_a_skipped_day_is_recorded_with_its_reason_and_looked_at_once():
    store = store_with([NEWS_SPORT], [FATWA_NO_BODY], on())
    res = planned(store)
    assert res["status"] == "skipped" and "Fatwa: read 1" in res["reason"] and motions(store) == []
    state = {r["key"]: r["value"] for r in store.tables["semasa_settings"]}[comic_daily.STATE_KEY]
    assert state["last"]["day"] == DAY and state["last"]["status"] == "skipped" and "Fatwa" in state["last"]["reason"]
    log = [r for r in store.tables.get("semasa_log", []) if r["event"] == "comic.daily.skipped"]
    assert len(log) == 1 and DAY in log[0]["title"]
    assert planned(store)["status"] == "exists", "the day was looked at; the hourly run does not look again"
    # Wan's button looks again (a new item may have come in) and still obeys the one-a-day rule
    store.tables["isu_semasa_trends"].append(NEWS_HALAL)
    assert planned(store, force=True)["status"] == "planned"
    assert planned(store, force=True)["status"] == "exists"


def test_the_button_ignores_the_switch_and_the_clock_but_never_the_one_a_day_rule():
    second = {
        **NEWS_HALAL,
        "id": "t8",
        "url": "https://news/8",
        "title": "Sijil halal tiruan dirampas di pasar raya selepas pemeriksaan",
    }
    store = store_with([NEWS_HALAL, second], [], {})  # no switch at all
    assert planned(store)["status"] == "off"
    first = planned(store, force=True)
    assert first["status"] == "planned" and len(motions(store)) == 1
    assert planned(store, force=True)["status"] == "exists" and len(motions(store)) == 1
    motions(store)[0]["status"] = "rejected"  # Wan rejected today's storyboard: it is no episode
    again = planned(store, force=True)
    assert again["status"] == "planned" and len(motions(store)) == 2
    assert motions(store)[1]["options"]["series"]["item"]["id"] == "t8", "a rejected story is not offered again"
    assert planned(store)["status"] == "off", "and the scheduled run still never makes a second one by itself"


def test_the_episode_number_is_the_count_so_far_plus_one_and_a_waiting_storyboard_holds_its_number():
    store = store_with([NEWS_HALAL, NEWS_PLAIN], [], on())
    for n in (1, 2, 3):
        store.tables["media_generations"].append(
            {
                "id": f"c{n}",
                "mode": "slides",
                "status": "done",
                "meta": {"design": "comic", "comic": {"series": "isu-semasa-harian", "episode": n}},
            }
        )
    assert planned(store)["episode"] == 4
    store.tables["media_generations"].append(
        {
            "id": "o",
            "mode": "slides",
            "status": "done",
            "meta": {"design": "comic", "comic": {"series": "kak-lin-tanya", "episode": 40}},
        }
    )
    assert comic_daily.episode_number(store, "isu-semasa-harian") == 5, (
        "a waiting storyboard (4) holds its number; another series does not count"
    )


def test_the_makenow_button_is_answered_once_and_recorded():
    store = store_with([NEWS_HALAL], [], {"comic_series": {"make_now": "2026-11-16T22:00:00Z"}})
    settings = {"comic_series": {"make_now": "2026-11-16T22:00:00Z"}}
    assert comic_daily.make_now_due(store, settings)
    assert "make now: planned" in comic_daily.run(store, settings, NOW) and len(motions(store)) == 1
    assert not comic_daily.make_now_due(store, settings)
    assert comic_daily.run(store, settings, NOW) == "", "the same press is never answered twice"
    state = {r["key"]: r["value"] for r in store.tables["semasa_settings"]}[comic_daily.STATE_KEY]
    assert state["make_now_done"] == "2026-11-16T22:00:00Z" and state["make_now_result"] == "planned"


# ----------------------------------------------------------------------------------------------------- the storyboard

GOOD = {
    "title": "Sijil halal palsu: apa yang dilaporkan?",
    "setting": "",
    "citation": "",
    "panels": [
        {
            "scene": "Pak Mat reads a newspaper at the counter, worried; Hana listens.",
            "lines": [{"who": "A", "text": "Hana, ada berita dua orang ditahan guna sijil halal palsu."}],
        },
        {
            "scene": "Hana answers calmly.",
            "lines": [
                {"who": "B", "text": "Buletin TV3 melaporkan dua individu ditahan kerana guna sijil itu."},
                {"who": "A", "text": "Mereka jual apa?"},
            ],
        },
        {"scene": "Hana points at her tablet.", "lines": [{"who": "B", "text": "Pewarna rambut, Pak Mat."}]},
        {"scene": "Both nod.", "lines": [{"who": "A", "text": "Oh, begitu."}, {"who": "B", "text": "Itu yang dilaporkan."}]},
    ],
}


def rewritten(answer, **panel_text):
    out = copy.deepcopy(answer)
    for n, text in panel_text.items():
        out["panels"][int(n[1]) - 1]["lines"][0]["text"] = text
    return out


class Writer:
    configured = True
    last_model = "m1"

    def __init__(self, *answers):
        self.answers, self.asked = list(answers), []

    def chat_json(self, system, user, **kw):
        self.asked.append((system, user))
        return copy.deepcopy(self.answers.pop(0)) if self.answers else None


def planned_row(store, item=NEWS_HALAL, lane="isu_semasa", **opts):
    ruling = comic_daily.ruling_source(item) if comic_daily.sensitive(item, lane) else None
    sec = item.get("section") or "news"
    snap = comic_daily.snapshot({**item, "section": sec, "lane": lane})
    return (
        store.table("semasa_motions")
        .insert(
            {
                "status": "working",
                "stream": "regulab",
                "language": "bm",
                "attempts": 1,
                "brief": "x",
                "options": {
                    "template": "comic",
                    "series": {
                        "id": "isu-semasa-harian",
                        "episode": 12,
                        "day": DAY,
                        "lane": lane,
                        "words_mode": "art",
                        "style": "",
                        "item": snap,
                        "ruling": ruling,
                        "source": comic_daily.source_line({**item, "section": sec}, ruling),
                    },
                },
            }
        )
        .execute()
        .data[0]
    )


def test_the_storyboard_is_one_text_call_under_the_halal_fatwa_and_comic_rules_and_the_source_is_not_the_writers():
    store = store_with([NEWS_HALAL], [])
    row = planned_row(store)
    llm = Writer({**GOOD, "citation": "Sumber rekaan oleh penulis"})
    sb, note = comic_daily.write_storyboard(store, row, llm, {})
    assert len(llm.asked) == 1, "one text call and nothing else is spent before the approval"
    system, user = llm.asked[0]
    assert "HALAL, FATWA AND RELIGION ARE SENSITIVE" in system and "never says" in system and "No call to action" in system
    assert "Pak Mat" in system and "Hana" in system and "ISU: Dua ditahan" in user and "sijil halal palsu" in user
    assert sb["title"] == GOOD["title"] and len(sb["panels"]) == 4 and sb["episode"] == 12 and sb["lane"] == "isu_semasa"
    assert sb["source"] == row["options"]["series"]["source"] and "rekaan" not in sb["source"], "the source is built from the row"
    assert sb["names"] == {"A": "Pak Mat", "B": "Hana"} and "Episod 12" in note and "Isu Semasa di Kedai" in note


def test_a_script_that_rules_without_the_row_naming_a_body_is_asked_again_once_then_refused():
    store = store_with([], [FATWA_NO_BODY])
    row = planned_row(store, NEWS_HALAL)  # a row with no ruling in it
    bad = rewritten(GOOD, p1="Hukumnya haram, Pak Mat.")
    llm = Writer(bad, GOOD)
    sb, _ = comic_daily.write_storyboard(store, row, llm, {})
    assert len(llm.asked) == 2 and "states a ruling" in llm.asked[1][1] and "refused" in llm.asked[1][1]
    assert sb["panels"][0]["lines"][0]["text"] == GOOD["panels"][0]["lines"][0]["text"]
    with pytest.raises(comic.ComicError, match="refused twice.*ruling"):
        comic_daily.write_storyboard(store, row, Writer(bad, bad), {})


def test_a_reported_position_must_name_the_body_the_row_gives():
    store = store_with([], [FATWA_OK])
    row = planned_row(store, FATWA_OK, "fatwa")
    assert row["options"]["series"]["ruling"]["body"] == "Pejabat Mufti Wilayah Persekutuan"
    anon = rewritten(GOOD, p2="Ulama kata plasenta manusia haram untuk kosmetik.")
    named = rewritten(GOOD, p2="Pejabat Mufti Wilayah Persekutuan menyatakan plasenta manusia haram untuk kosmetik.")
    llm = Writer(anon, named)
    sb, _ = comic_daily.write_storyboard(store, row, llm, {})
    assert "Pejabat Mufti Wilayah Persekutuan menyatakan" in sb["panels"][1]["lines"][0]["text"]
    assert "issued by Pejabat Mufti Wilayah Persekutuan on 2019" in llm.asked[0][0]
    assert sb["source"] == FATWA_OK["raw"]["cite"], "the episode's source line names the body, the instrument and the year"


@pytest.mark.parametrize(
    "bad, why",
    [
        (rewritten(GOOD, p1="Klik www.kkmhalalconsultant.com untuk semak."), "website"),
        (rewritten(GOOD, p1="Produk ini dijamin lulus NPRA, semak sijil anda."), "approval promise"),
        (rewritten(GOOD, p1="Berita reddit kata dua orang ditahan guna sijil palsu."), "reddit"),
        (rewritten(GOOD, p1="Dalam surah Al-Baqarah ayat 168 ada perintah makan yang baik."), "verse"),
    ],
)
def test_no_call_to_action_no_url_no_social_source_no_scripture_even_when_the_writer_tries(bad, why):
    store = store_with([NEWS_HALAL], [])
    row = planned_row(store)
    with pytest.raises(comic.ComicError, match="refused twice"):
        comic_daily.write_storyboard(store, row, Writer(bad, bad), {})


def test_a_figure_the_row_does_not_give_is_refused_and_one_it_gives_is_fine():
    store = store_with([NEWS_HALAL], [])
    row = planned_row(store)
    invented = rewritten(GOOD, p3="Denda sehingga RM50,000 untuk setiap kesalahan, Pak Mat.")
    with pytest.raises(comic.ComicError, match="figure"):
        comic_daily.write_storyboard(store, row, Writer(invented, invented), {})


def test_the_approved_storyboard_is_checked_again_with_the_same_rules_and_the_source_cannot_be_edited():
    store = store_with([NEWS_HALAL], [])
    row = planned_row(store)
    sb, _ = comic_daily.write_storyboard(store, row, Writer(GOOD), {})
    assert comic_daily.recheck(sb, {})["title"] == sb["title"]
    edited = copy.deepcopy(sb)
    edited["panels"][0]["lines"][0]["text"] = "Saya putuskan sijil ini halal."
    with pytest.raises(motion_templates.StoryboardError, match="rule"):
        comic_daily.recheck(edited, {})
    edited["panels"][0]["lines"][0]["text"] = "Layari www.kkmhalalconsultant.com sekarang."
    with pytest.raises(motion_templates.StoryboardError):
        comic_daily.recheck(edited, {})
    edited = {**sb, "panels": sb["panels"][:3]}
    with pytest.raises(motion_templates.StoryboardError, match="4 panels"):
        comic_daily.recheck(edited, {})


# --------------------------------------------------------------------------------------------------- the approval gate


class Bucket:
    def __init__(self):
        self.files = {}

    def upload(self, path, data, opts):
        self.files[path] = (data, opts["content-type"])

    def download(self, path):
        return self.files[path][0]

    def remove(self, paths):
        for p in paths:
            self.files.pop(p, None)

    def get_public_url(self, path):
        return f"https://cdn/{path}"


class Store(FakeStore):
    def __init__(self, **tables):
        super().__init__(**tables)
        self.bucket = Bucket()
        self.storage = SimpleNamespace(from_=lambda name: self.bucket)


def comic_store(news=(NEWS_HALAL,), rows=(), settings=None):
    s = Store(
        isu_semasa_trends=list(news),
        semasa_watch=list(rows),
        semasa_ideas=[],
        semasa_motions=[],
        semasa_posts=[],
        media_generations=[],
        semasa_settings=[],
    )
    s.now = "2026-11-17T00:00:00+00:00"
    for k, v in (settings or {}).items():
        s.tables["semasa_settings"].append({"key": k, "value": v})
    return s


def wordless_art(side=1080):
    """A square picture whose four quarters are four colours, so a panel is known by its colour."""
    img = Image.new("RGB", (side, side), (255, 255, 255))
    for n, colour in enumerate(((220, 40, 40), (40, 200, 60), (40, 70, 220), (230, 200, 30))):
        x, y = (n % 2) * side // 2, (n // 2) * side // 2
        img.paste(Image.new("RGB", (side // 2, side // 2), colour), (x, y))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def runner(total, calls=None, render_ok=True):
    from test_motion import _runner

    return _runner(calls=calls, render_ok=render_ok, probe_seconds=total)


MEDIA = SimpleNamespace(max_attempts=3, provider="openai")


def approve(store, row):
    got = store.table("semasa_motions").select("*").eq("id", row["id"]).execute().data[0]
    fields = {"status": "pending", "storyboard_approved_at": "2026-11-17T00:00:00+00:00"}
    store.table("semasa_motions").update(fields).eq("id", row["id"]).execute()
    return {**got, **fields, "status": "working", "attempts": 1}


def drawing(counter):
    def draw(prompt):
        counter.append(prompt)
        return wordless_art()

    return draw


def test_nothing_is_drawn_voiced_rendered_or_posted_before_wan_approves_the_storyboard(tmp_path):
    store = comic_store()
    row = planned_row(store)
    row = {**row, "attempts": 1}
    calls, drawn = [], []
    assert comic_film.make_film(
        store, Writer(GOOD), row, SETTINGS, tmp_path, runner=runner(40, calls), s=MEDIA, draw=drawing(drawn), read=None
    )
    got = store.table("semasa_motions").select("*").eq("id", row["id"]).execute().data[0]
    assert got["status"] == "review" and got["stage"] == "storyboard" and got["storyboard"]["kind"] == "comic"
    assert got["storyboard_approved_at"] is None and got["storyboard"]["sb"]["title"] == GOOD["title"]
    assert drawn == [] and calls == [], "no picture maker, no HyperFrames, no ffmpeg before the approval"
    assert store.tables["media_generations"] == [] and store.tables["semasa_posts"] == []
    assert not got.get("video_url") and not store.bucket.files


def test_the_storyboard_reaches_telegram_through_the_existing_gate_and_shows_every_panel():
    store = comic_store()
    row = planned_row(store)
    sb, note = comic_daily.write_storyboard(store, row, Writer(GOOD), {})
    shown = motion_review.scenes_of({"kind": "comic", "sb": sb})
    assert [x["label"] for x in shown] == ["Tajuk", "Panel 1", "Panel 2", "Panel 3", "Panel 4"]
    assert shown[0]["heading"] == GOOD["title"] and "Sumber: " in shown[0]["lines"][1] and "Episod 12" in shown[0]["lines"][0]
    assert shown[2]["lines"] == [
        "Hana: Buletin TV3 melaporkan dua individu ditahan kerana guna sijil itu.",
        "Pak Mat: Mereka jual apa?",
    ]
    text = motion_review.telegram_text({"id": "r", "brief": "x"}, {"kind": "comic", "sb": sb, "note": note})
    assert (
        "Komik harian" in text and GOOD["title"] in text and "Panel 4" in text and "Suara dan video hanya dibuat selepas" in text
    )
    assert motion_templates.template_of({"options": {"template": "comic"}}) == "comic" and "comic" in motion_review.KINDS


def test_a_write_again_asks_for_a_new_storyboard_from_the_same_item(tmp_path):
    store = comic_store()
    row = planned_row(store)
    comic_film.make_film(store, Writer(GOOD), {**row}, SETTINGS, tmp_path, runner=runner(40), s=MEDIA, draw=None, read=None)
    store.table("semasa_motions").update({"status": "pending", "storyboard": None, "storyboard_approved_at": None}).eq(
        "id", row["id"]
    ).execute()
    second = rewritten(GOOD, p3="Bukan pewarna rambut sahaja, Pak Mat.")
    llm = Writer(second)
    again = store.table("semasa_motions").select("*").eq("id", row["id"]).execute().data[0]
    comic_film.make_film(store, llm, {**again, "status": "working"}, SETTINGS, tmp_path, runner=runner(40), s=MEDIA)
    got = store.table("semasa_motions").select("*").eq("id", row["id"]).execute().data[0]
    assert got["status"] == "review" and "Bukan pewarna rambut" in json.dumps(got["storyboard"], ensure_ascii=False)
    assert "ISU: Dua ditahan" in llm.asked[0][1], "the same item, written again"


def test_an_approved_storyboard_that_breaks_a_rule_goes_back_for_review_and_nothing_is_drawn(tmp_path):
    store = comic_store()
    row = planned_row(store)
    comic_film.make_film(store, Writer(GOOD), {**row}, SETTINGS, tmp_path, runner=runner(40), s=MEDIA)
    got = store.table("semasa_motions").select("*").eq("id", row["id"]).execute().data[0]
    got["storyboard"]["sb"]["panels"][0]["lines"][0]["text"] = "Saya putuskan sijil ini halal, Pak Mat."
    drawn = []
    asked = approve(store, {**got})
    asked["storyboard"] = got["storyboard"]
    assert comic_film.make_film(
        store, Writer(), asked, SETTINGS, tmp_path, runner=runner(40), s=MEDIA, draw=drawing(drawn), read=None
    )
    back = store.table("semasa_motions").select("*").eq("id", row["id"]).execute().data[0]
    assert back["status"] == "review" and "rule" in back["error"] and back["storyboard_approved_at"] is None and drawn == []


# --------------------------------------------------------------- after the approval: the drawing, the film, the draft post


def approved_run(tmp_path, *, store=None, draw=None, run=None, llm=None, row=None):
    store = store or comic_store()
    row = row or planned_row(store)
    first = comic_film.make_film(store, Writer(GOOD), {**row}, SETTINGS, tmp_path / "a", runner=runner(40), s=MEDIA)
    assert first
    got = store.table("semasa_motions").select("*").eq("id", row["id"]).execute().data[0]
    asked = approve(store, got)
    asked["storyboard"] = got["storyboard"]
    drawn: list = []
    llm = llm or Writer(
        {
            "captions": {
                "instagram": "Sijil halal palsu: dua ditahan.",
                "facebook": "Sijil halal palsu: dua ditahan.",
                "threads": "Sijil halal palsu: dua ditahan.",
            }
        }
    )
    total = comic_film.timeline(got["storyboard"]["sb"])["total"]  # what the writer's words (after the clean-up) take
    return store, row, asked, drawn, llm, (draw or drawing(drawn)), (run or runner(total))


def test_after_the_approval_the_comic_is_drawn_once_and_the_film_is_made_from_its_four_panels_in_reading_order(tmp_path):
    store, row, asked, drawn, llm, draw, run = approved_run(tmp_path)
    assert comic_film.make_film(store, llm, asked, SETTINGS, tmp_path / "b", runner=run, s=MEDIA, draw=draw, read=None)
    got = store.table("semasa_motions").select("*").eq("id", row["id"]).execute().data[0]
    assert got["status"] == "done" and got["video_url"].endswith(f"{row['id']}.mp4") and got["error"] == ""
    assert len(drawn) == 1, "words_mode art: ONE drawing, no picture reader"
    assert "NO speech bubbles" in drawn[0] and "Pewarna rambut, Pak Mat." not in drawn[0], "wordless art is asked for"
    comic_rows = [m for m in store.tables["media_generations"] if (m.get("meta") or {}).get("design") == "comic"]
    assert len(comic_rows) == 1 and comic_rows[0]["status"] == "done" and comic_rows[0]["meta"]["comic"]["episode"] == 12
    art = comic_rows[0]["meta"]["comic"]["art"]
    assert art["wordless"] is True and art["path"] in store.bucket.files
    index = (tmp_path / "b" / "index.html").read_text()
    assert [index.index(f"assets/panel{i}.jpg") for i in (1, 2, 3, 4)] == sorted(
        index.index(f"assets/panel{i}.jpg") for i in (1, 2, 3, 4)
    )
    # the four panels are the four quarters of the picture, in reading order
    colours = [Image.open(tmp_path / "b" / "assets" / f"panel{i}.jpg").convert("RGB").getpixel((480, 480)) for i in (1, 2, 3, 4)]
    assert colours[0][0] > 180 and colours[1][1] > 150 and colours[2][2] > 180 and colours[3][0] > 180 and colours[3][1] > 150
    assert got["check_report"]["template"] == "comic" and got["check_report"]["cover"], "the branded cover opens the film"
    assert got["social_url"] and got["poster_url"] and got["captions"]["instagram"]
    assert [s["id"] for s in got["script"]] == ["title", "p1", "p2", "p3", "p4", "end"]


def test_the_page_is_laid_out_one_clip_per_scene_with_the_bubbles_coming_in_reading_order(tmp_path):
    store, row, asked, drawn, llm, draw, run = approved_run(tmp_path)
    comic_film.make_film(store, llm, asked, SETTINGS, tmp_path / "b", runner=run, s=MEDIA, draw=draw, read=None)
    html = (tmp_path / "b" / "index.html").read_text()
    for needle in (
        'id="s0"',
        'id="s1"',
        'id="s4"',
        'id="outc"',
        "official-logo-transparent.png",
        "www.kkmhalalconsultant.com",
        "Siri Isu Semasa di Kedai · Episod 12",
        "Buletin TV3",
        'window.__timelines["main"] = tl',
    ):
        assert needle in html, needle
    tl = comic_film.timeline({"panels": GOOD["panels"]})
    times = [float(m) for m in __import__("re").findall(r'tl\.fromTo\("#b\d\d",.*?,([\d.]+)\);', html)]
    assert times == sorted(times) and len(times) == 6 == sum(len(p["lines"]) for p in GOOD["panels"]), (
        "one bubble at a time, in order"
    )
    assert [t for p in tl["panels"] for t in p["appear"]] == times
    assert tl["panels"][0]["start"] == comic_film.TITLE_SECONDS and tl["outro_start"] + comic_film.OUTRO_SECONDS == tl["total"]
    assert "Pewarna rambut, Pak Mat." in html and "Hana, ada berita" in html


def test_a_comic_the_picture_maker_lettered_is_shown_as_drawn_and_each_line_is_also_said_in_order(tmp_path):
    script = comic_writer.assemble(
        {"title": GOOD["title"], "setting": "", "panels": GOOD["panels"]},
        comic_library.series_of(comic_library.library(None), "isu-semasa-harian"),
        "regulab",
        "X",
    )
    sb = {"title": GOOD["title"], "panels": GOOD["panels"], "source": "X", "names": {"A": "Pak Mat", "B": "Hana"}}
    html, _ = comic_film.compose(
        sb,
        script,
        [f"assets/panel{i}.jpg" for i in (1, 2, 3, 4)],
        wordless=False,
        website="w.my",
        episode_line="Siri S · Episod 1",
    )
    assert 'class="bb"' not in html and 'id="y11"' in html and "Pak Mat:</b> Hana, ada berita" in html
    assert "scale:0.95" in html, "a pull-out only: a push-in would cut a word off the edge"
    wordless, _ = comic_film.compose(
        sb,
        script,
        [f"assets/panel{i}.jpg" for i in (1, 2, 3, 4)],
        wordless=True,
        website="w.my",
        episode_line="Siri S · Episod 1",
    )
    assert wordless.count('class="bb"') == 6 and 'class="say"' not in wordless.replace(".say{", "")


def test_the_draft_post_is_a_draft_on_the_next_free_slot_with_the_film_and_nothing_is_approved(tmp_path):
    store, row, asked, drawn, llm, draw, run = approved_run(tmp_path)
    # the draft starts from TOMORROW, Malaysia time, so the dates follow the real clock (a fixed date fails after midnight MYT)
    today_myt = comic_daily.myt_day(datetime.now(UTC))
    tomorrow_myt = (date.fromisoformat(today_myt) + timedelta(days=1)).isoformat()
    store.tables["semasa_posts"].append(
        {"id": "held", "stream": "regulab", "date": today_myt, "slot": "08:00", "status": "draft"}
    )
    store.tables["semasa_settings"].append({"key": "brand", "value": {"regulab": {"slots": ["08:00", "13:00"]}}})
    comic_film.make_film(store, llm, asked, SETTINGS, tmp_path / "b", runner=run, s=MEDIA, draw=draw, read=None)
    posts = [p for p in store.tables["semasa_posts"] if p["id"] != "held"]
    assert len(posts) == 1
    post = posts[0]
    assert post["status"] == "draft" and post["stream"] == "regulab" and post["lang"] == "bm"
    assert (post["date"], post["slot"]) == (tomorrow_myt, "08:00"), "the next free slot, from tomorrow"
    assert sorted(post["channels"]) == ["facebook", "instagram"] and post["text"]["bm"]["instagram"], "a film is never Threads'"
    assert post["citation"] == "Buletin TV3" or post["citation"].startswith("Buletin TV3")
    film_media = [m for m in store.tables["media_generations"] if m.get("type") == "video"]
    assert len(film_media) == 1 and post["media_ids"] == [film_media[0]["id"]] and film_media[0]["post_id"] == post["id"]
    assert film_media[0]["meta"]["flow"] == "motion" and film_media[0]["meta"]["motion_id"] == row["id"]
    got = store.table("semasa_motions").select("*").eq("id", row["id"]).execute().data[0]
    assert got["queued_post_id"] == post["id"]
    assert not any(p["status"] in ("approved", "scheduled", "posted") for p in store.tables["semasa_posts"])
    assert "approved_by" not in post and "approved_at" not in post
    assert comic_daily.queue_post(store, row, {}) is None and len(store.tables["semasa_posts"]) == 2, "never a second draft"


def test_a_caption_that_rules_or_links_is_replaced_by_the_storyboards_own_words(tmp_path):
    bad = Writer(
        {
            "captions": {
                "instagram": "Hukumnya haram. Layari www.x.com.",
                "facebook": "Dua ditahan guna sijil halal palsu.",
                "threads": "Fatwa kata haram.",
            }
        }
    )
    store, row, asked, drawn, _llm, draw, run = approved_run(tmp_path, llm=bad)
    comic_film.make_film(store, bad, asked, SETTINGS, tmp_path / "b", runner=run, s=MEDIA, draw=draw, read=None)
    got = store.table("semasa_motions").select("*").eq("id", row["id"]).execute().data[0]
    assert got["captions"]["facebook"] == "Dua ditahan guna sijil halal palsu."
    for plat in ("instagram",):
        assert (
            "Sumber: Buletin TV3" in got["captions"][plat]
            and "www." not in got["captions"][plat]
            and "Hukumnya" not in got["captions"][plat]
        )
    assert sorted(got["check_report"]["captions_from_storyboard"]) == ["instagram"]


# ------------------------------------------------------------------------------------------------ failure and resume


def test_a_film_that_fails_after_the_drawing_is_made_again_without_drawing_the_comic_a_second_time(tmp_path):
    store, row, asked, drawn, llm, draw, run = approved_run(tmp_path)
    broken = runner(40, render_ok=False)
    with pytest.raises(RuntimeError, match="render failed"):
        comic_film.make_film(store, llm, asked, SETTINGS, tmp_path / "b", runner=broken, s=MEDIA, draw=draw, read=None)
    assert len(drawn) == 1 and store.table("semasa_motions").select("*").eq("id", row["id"]).execute().data[0]["status"] != "done"
    # the retry (motion.process puts the film back to pending): same storyboard, same drawing, the film is made
    assert comic_film.make_film(
        store, llm, {**asked, "attempts": 2}, SETTINGS, tmp_path / "c", runner=run, s=MEDIA, draw=draw, read=None
    )
    assert len(drawn) == 1, "the paid drawing is never repeated for a film that failed later"
    assert len([m for m in store.tables["media_generations"] if (m.get("meta") or {}).get("design") == "comic"]) == 1
    assert store.table("semasa_motions").select("*").eq("id", row["id"]).execute().data[0]["status"] == "done"


def test_a_failed_drawing_says_why_and_a_retry_draws_it_again_on_the_same_row(tmp_path):
    store, row, asked, _drawn, llm, _draw, run = approved_run(tmp_path)

    def down(prompt):
        from semasa.providers import ProviderError

        raise ProviderError("the picture maker is down")

    with pytest.raises(RuntimeError, match="the comic was not drawn.*picture maker is down"):
        comic_film.make_film(store, llm, asked, SETTINGS, tmp_path / "b", runner=run, s=MEDIA, draw=down, read=None)
    rows = [m for m in store.tables["media_generations"] if (m.get("meta") or {}).get("design") == "comic"]
    assert len(rows) == 1 and rows[0]["status"] == "error" and "down" in rows[0]["error"]
    assert (
        not store.tables["semasa_posts"]
        and store.table("semasa_motions").select("*").eq("id", row["id"]).execute().data[0]["status"] != "done"
    )
    again: list = []
    assert comic_film.make_film(
        store, llm, {**asked, "attempts": 2}, SETTINGS, tmp_path / "c", runner=run, s=MEDIA, draw=drawing(again), read=None
    )
    assert (
        len(again) == 1
        and len([m for m in store.tables["media_generations"] if (m.get("meta") or {}).get("design") == "comic"]) == 1
    )


def test_a_new_storyboard_after_write_again_is_a_new_drawing(tmp_path):
    store, row, asked, drawn, llm, draw, run = approved_run(tmp_path)
    comic_film.make_film(store, llm, asked, SETTINGS, tmp_path / "b", runner=run, s=MEDIA, draw=draw, read=None)
    assert len(drawn) == 1
    other = copy.deepcopy(asked)
    other["storyboard"]["sb"]["panels"][2]["lines"][0]["text"] = "Bukan pewarna rambut sahaja, Pak Mat."
    store.table("semasa_motions").update({"status": "pending", "queued_post_id": None}).eq("id", row["id"]).execute()
    run2 = runner(comic_film.timeline(other["storyboard"]["sb"])["total"])
    comic_film.make_film(
        store, llm, {**other, "status": "working"}, SETTINGS, tmp_path / "c", runner=run2, s=MEDIA, draw=draw, read=None
    )
    assert len(drawn) == 2


def test_a_film_whose_post_could_not_be_drafted_gets_it_on_the_next_run():
    store = comic_store()
    row = planned_row(store)
    store.table("semasa_motions").update(
        {
            "status": "done",
            "video_url": "https://cdn/v.mp4",
            "title": "T",
            "captions": {"instagram": "a", "facebook": "b", "threads": "c"},
            "storyboard": {"kind": "comic", "sb": {"source": "Buletin TV3"}},
        }
    ).eq("id", row["id"]).execute()
    assert comic_daily.queue_finished(store, {}) == 1 and len(store.tables["semasa_posts"]) == 1
    assert comic_daily.queue_finished(store, {}) == 0, "and only once"
    assert store.tables["semasa_posts"][0]["status"] == "draft"


# --------------------------------------------------------------------------------------------- Motion runs the series


def test_motion_plans_the_day_at_the_start_of_its_run_and_a_switched_off_series_adds_nothing(monkeypatch):
    store = Store(
        isu_semasa_trends=[NEWS_HALAL],
        semasa_watch=[],
        semasa_ideas=[],
        semasa_motions=[],
        semasa_posts=[],
        media_generations=[],
        semasa_settings=[{"key": "comic_series", "value": {"enabled": True}}],
    )
    monkeypatch.setattr(motion, "process", lambda *a, **k: True)
    out = motion.run(store, None, now=NOW)
    assert out["comic_series"] == "daily: planned" and len(store.tables["semasa_motions"]) == 1 or out["claimed"] == 1
    off = Store(semasa_settings=[], semasa_motions=[])
    assert "comic_series" not in motion.run(off, None, now=NOW)


def test_the_comic_template_reaches_the_comic_path_not_the_showcase_or_the_story(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(comic_film, "make_film", lambda *a, **k: seen.append("comic") or True)
    store = comic_store()
    row = planned_row(store)
    assert motion.template_film(store, None, row, SETTINGS, tmp_path) is True and seen == ["comic"]


# ------------------------------------------------------------------------------------------------------- the migration

SQL = (Path(__file__).resolve().parents[2] / "supabase" / "086_comic_daily.sql").read_text()


def test_086_seeds_both_rows_wakes_motion_on_a_button_press_and_keeps_the_clock_and_is_safe_to_rerun():
    assert "insert into public.semasa_settings" in SQL and "'comic_series'" in SQL and "'comic_series_log'" in SQL
    assert SQL.count("on conflict (key) do nothing") >= 2, "an existing row (and what Wan saved in it) is never touched"
    assert '"enabled": false' in SQL and '"paused": false' in SQL, "off by default"
    assert "create or replace function public.semasa_clock_comic_changed" in SQL and "make_now" in SQL
    assert "drop trigger if exists semasa_clock_comic_changed" in SQL and "'motion_pending'" in SQL
    assert "cron.schedule('semasa_comic_daily'" in SQL and "Run ONCE in the SQL editor" in SQL
    assert "-- Check" in SQL and "select count(*)" in SQL.split("-- Check", 1)[1]


# ------------------------------------------------------------------------------------------------------------- Telegram


def test_a_tap_on_make_todays_episode_asks_only_for_a_storyboard_and_changes_no_post():
    from test_telegram_menu import Bot, menu_store, run, tap

    from semasa import db
    from semasa import telegram_bot as tb
    from semasa import telegram_menu as menu

    assert menu.ACTIONS["komik_harian"][0] == "cmd" and "komik_harian" in menu.acts()
    fresh = {**NEWS_HALAL, "created_at": datetime.now(UTC).isoformat()}  # the tap reads the real clock
    st = menu_store(
        **{tb.INBOX: [tap(1, "a:komik_harian")], "isu_semasa_trends": [fresh], "semasa_watch": [], "semasa_motions": []}
    )
    before = json.dumps(st.tables[db.POSTS], sort_keys=True)
    bot = Bot()
    assert run(st, bot)["errors"] == 0
    rows = st.tables["semasa_motions"]
    assert len(rows) == 1 and rows[0]["status"] == "pending" and rows[0]["options"]["template"] == "comic"
    assert rows[0]["options"]["series"]["requested"] == "telegram"
    assert "storyboard" in bot.sent()[-1]["text"] and st.rpcs == [] and json.dumps(st.tables[db.POSTS], sort_keys=True) == before
    st.tables[tb.INBOX].append(tap(2, "a:komik_harian"))
    run(st, bot)
    assert len(st.tables["semasa_motions"]) == 1 and "sudah ada" in bot.sent()[-1]["text"], "one episode a day, even by button"


def test_comic_drawing_job_uses_a_status_the_media_table_allows():
    """media_generations allows only pending / processing / done / error (supabase/001): the first real episode died on
    "working", which a stub table accepts and Postgres refuses."""
    series = comic_library.series_of(comic_library.library(None), comic_daily.RULES["series"])
    sb = {"title": "t", "setting": "s", "panels": [{"scene": "x", "lines": [{"who": "A", "text": "a"}]}], "series": series["id"]}
    job = comic_film.comic_job_row(sb, series, "Sumber", SimpleNamespace(max_attempts=3))
    assert job["status"] in ("pending", "processing", "done", "error")
