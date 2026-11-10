"""Wan, 10 Nov 2026: six posts a day with a format per slot, and Buffer resting as Zernio's backup."""
from datetime import UTC, datetime

from semasa import autofill, health, publisher

NOW = datetime(2026, 11, 10, 4, 0, tzinfo=UTC)
ZERNIO = {"enabled": True, "accounts": {p: {"id": "a" * 24, "key": "1"} for p in ("instagram", "facebook", "threads")}}
BUFFER = {"organizationId": "o", "instagram": "i", "facebook": "f", "threads": "t"}


def test_slot_format_reads_the_rota_and_ignores_unknown_words():
    brand = {"regulab": {"slot_formats": {"08:00": "video", "10:30": "carousel", "13:00": "single", "16:00": "reel"}}}
    assert autofill.slot_format(brand, "regulab", "08:00") == "video"
    assert autofill.slot_format(brand, "regulab", "10:30") == "carousel"
    assert autofill.slot_format(brand, "regulab", "13:00") == "single"
    assert autofill.slot_format(brand, "regulab", "16:00") == ""
    assert autofill.slot_format(brand, "linkedin", "08:00") == ""
    assert autofill.slot_format({}, "regulab", "08:00") == ""


def test_a_film_for_a_video_slot_waits_for_start_and_carries_its_position():
    row = autofill.film_row({"title": "KKM tarik balik produk", "summary": "Tiga produk.", "url": "https://x.my/a"},
                            "regulab", "2026-11-12", "08:00")
    assert row["status"] == "waiting"                      # nothing is made until Wan taps Start
    assert row["options"]["position"] == {"date": "2026-11-12", "slot": "08:00"}
    assert row["language"] == "bm" and row["resolution"] == "portrait"
    li = autofill.film_row({"title": "A recall", "url": "https://x.my/b"}, "linkedin", "2026-11-12", "10:00")
    assert li["language"] == "en" and li["resolution"] == "square"


def test_buffer_is_the_backup_only_when_zernio_holds_every_buffer_platform():
    assert publisher.buffer_is_backup({"channels": {"buffer": BUFFER, "zernio": ZERNIO}})
    off = {**ZERNIO, "enabled": False}
    assert not publisher.buffer_is_backup({"channels": {"buffer": BUFFER, "zernio": off}})      # Buffer alive again
    part = {"enabled": True, "accounts": {"instagram": {"id": "a" * 24, "key": "1"}}}
    assert not publisher.buffer_is_backup({"channels": {"buffer": BUFFER, "zernio": part}})
    assert not publisher.buffer_is_backup({"channels": {"buffer": BUFFER}})


def test_buffer_holds_counts_only_its_own_unfinished_records():
    posts = [{"published": {"instagram": {"route": "buffer", "status": "scheduled"},
                            "facebook": {"route": "buffer", "status": "sent"},
                            "threads": {"route": "zernio", "status": "scheduled"},
                            "linkedin": {"route": "composio", "status": "sent"}}},
             {"published": {"instagram": {"route": "buffer-adopted", "status": "scheduled"}}}, {"published": None}]
    assert publisher.buffer_holds(posts) == 2
    assert publisher.buffer_holds([]) == 0


class _Q:
    def __init__(self, rows):
        self.rows = rows

    def __getattr__(self, _):
        return lambda *a, **k: self

    def execute(self):
        return type("R", (), {"data": self.rows})()


class _Store:
    def __init__(self, rows):
        self.rows = rows

    def table(self, _):
        return _Q(self.rows)


def test_the_health_report_suggests_waking_buffer_when_zernio_keeps_failing():
    err = {"message": "instagram: Zernio refused (401): bad key"}
    rows = [{"id": "1", "date": "2026-11-12", "slot": "08:00", "errors": {"instagram": err}},
            {"id": "2", "date": "2026-11-12", "slot": "13:00", "errors": {"threads": err}}]
    out = health.check_publisher(_Store(rows))
    assert "Zernio failed on 2" in out[0]["what"] and "Buffer" in out[0]["todo"]
    one = health.check_publisher(_Store(rows[:1]))
    assert not any("Zernio failed" in p["what"] for p in one)          # one refusal is not a pattern
    fmt = {"message": "linkedin takes a carousel or a Motion film; this post is a single card"}
    gate = [{"id": str(i), "date": "d", "slot": "s", "errors": {"linkedin": fmt}} for i in range(3)]
    assert not any("Zernio failed" in p["what"] for p in health.check_publisher(_Store(gate)))


def test_autofill_asks_a_film_for_a_video_slot_a_carousel_for_a_carousel_slot_and_never_twice():
    from fakestore import FakeStore
    now = datetime(2026, 9, 24, 2, 0, tzinfo=UTC)                     # Thu 24 Sep, 10:00 MYT
    brand = {"regulab": {"slots": ["08:00", "13:00", "21:00"], "schedule": {"5": ["kosmetik"]},
                         "slot_formats": {"08:00": "video", "13:00": "carousel", "21:00": "single"}}}
    watch = [{"id": f"w{i}", "section": "regulatory", "source": "NPRA", "title": t, "url": f"https://npra.gov.my/{i}",
              "summary": "s", "domain": "kosmetik", "relevant": True, "dismissed": False,
              "created_at": "2026-09-23T00:00:00+00:00"}
             for i, t in enumerate(["Pembatalan notifikasi krim pemutih", "Garis panduan pelabelan baharu",
                                    "Amaran pewarna rambut tidak berdaftar", "Senarai bahan terlarang dikemas kini"])]
    store = FakeStore(semasa_watch=watch, semasa_ideas=[], semasa_posts=[], semasa_log=[], semasa_motions=[])
    cfg = {"brand": brand, "autofill": {"enabled": True, "days_ahead": 1, "per_run": 5, "streams": ["regulab"]}}
    out = autofill.run(store, cfg, now)
    films, ideas = store.tables["semasa_motions"], store.tables["semasa_ideas"]
    assert [f["options"]["position"]["slot"] for f in films] == ["08:00"] and films[0]["status"] == "waiting"
    by_slot = {i["brief"]["position"]["slot"]: i for i in ideas}
    assert sorted(by_slot) == ["13:00", "21:00"]
    assert by_slot["13:00"].get("make_slides") is True and by_slot["13:00"]["brief"]["format"] == "carousel"
    assert not by_slot["21:00"].get("make_slides") and by_slot["21:00"]["brief"]["slot_format"] == "single"
    assert "1 Motion film(s) waiting for Start" in out
    again = autofill.run(store, cfg, now)                              # the video slot is held by the waiting film
    assert len(store.tables["semasa_motions"]) == 1 and "Motion film" not in again
