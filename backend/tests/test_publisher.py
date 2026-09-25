from datetime import UTC, datetime

from fakestore import FakeStore

from semasa import publisher

NOW = datetime(2026, 9, 24, 2, 0, tzinfo=UTC)            # 10:00 MYT
CAP = "Notifikasi kosmetik bukan kelulusan produk. NPRA menyemak dokumen selepas produk dipasarkan."


def _post(**kw):
    p = {"id": "p1", "stream": "regulab", "lang": "bm", "status": "approved", "date": "2026-09-25", "slot": "08:00",
         "text": {"bm": {"instagram": CAP, "facebook": CAP, "threads": CAP}}, "citation": "NPRA",
         "media_ids": ["m1"], "published": {}, "errors": {}}
    p.update(kw)
    return p


def _store(post, enabled=False, media_status="done"):
    return FakeStore(
        semasa_settings=[{"key": "publishing", "value": {"enabled": enabled}}, {"key": "brand", "value": {}}],
        semasa_posts=[post],
        media_generations=[{"id": "m1", "status": media_status, "generated_media_url": "https://cdn/m1.png",
                            "meta": {"alt": "botol"}}],
        semasa_publish_log=[])


def test_dry_run_logs_what_it_would_send_once_and_sends_nothing():
    store = _store(_post())
    c = publisher.run(store, NOW)
    assert c["dry_run"] == 3 and c["error"] == 0
    logs = store.tables["semasa_publish_log"]
    assert {r["channel"] for r in logs} == {"instagram", "facebook", "threads"}
    assert all(r["action"] == "dry_run" for r in logs)
    assert logs[0]["detail"]["would_send"]["media"] == ["https://cdn/m1.png"]
    assert logs[0]["detail"]["would_send"]["due_at"] == "2026-09-25T00:00:00+00:00"
    publisher.run(store, NOW)
    assert len(store.tables["semasa_publish_log"]) == 3                  # no repeat for the same content
    assert store.tables["semasa_posts"][0]["published"] == {} and store.tables["semasa_posts"][0]["status"] == "approved"


def test_a_changed_caption_is_logged_again():
    store = _store(_post())
    publisher.run(store, NOW)
    store.tables["semasa_posts"][0]["text"]["bm"]["threads"] = CAP + " Semak label."
    publisher.run(store, NOW)
    assert len(store.tables["semasa_publish_log"]) == 4


def test_hard_flags_block_even_an_approved_post():
    store = _store(_post(text={"bm": {"instagram": CAP + " Hubungi kami.", "facebook": CAP, "threads": CAP}}))
    c = publisher.run(store, NOW)
    assert c["blocked"] == 3 and c["dry_run"] == 0
    assert "hubungi kami" in " ".join(store.tables["semasa_posts"][0]["errors"]["scan"])


def test_ungenerated_picture_blocks():
    c = publisher.run(_store(_post(), media_status="processing"), NOW)
    assert c["blocked"] == 3


def test_overdue_is_never_fired():
    c = publisher.run(_store(_post(date="2026-09-23", slot="08:00")), NOW)
    assert c["overdue"] == 3 and c["dry_run"] == 0


def test_far_future_and_drafts_are_ignored():
    assert publisher.run(_store(_post(date="2026-12-01")), NOW)["considered"] == 0
    assert publisher.run(_store(_post(status="draft")), NOW)["considered"] == 0


def test_enabled_without_a_sender_records_an_error_and_sends_nothing():
    store = _store(_post(), enabled=True)
    c = publisher.run(store, NOW)
    assert c["error"] == 3
    assert all("nothing was sent" in r["detail"]["why"] for r in store.tables["semasa_publish_log"])
    assert store.tables["semasa_posts"][0]["published"] == {}


def test_a_channel_already_published_is_skipped():
    c = publisher.run(_store(_post(published={"instagram": {"status": "sent"}})), NOW)
    assert c["dry_run"] == 2
