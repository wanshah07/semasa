"""Two posts in one slot, and the same words twice, never reach Buffer or LinkedIn (guard.py, publisher.run)."""
import json
from datetime import UTC, datetime
from pathlib import Path

from test_publisher import CAP, CHANNELS, FakeBuffer, FakeLinkedIn, _live, _post

from semasa import guard, publisher

NOW = datetime(2026, 9, 24, 2, 0, tzinfo=UTC)                      # 10:00 MYT
OTHER = "Halal logo boleh dicetak dalam warna lain selagi spesifikasi logo tidak berubah, kata Klausa 40(2)."


def _p(id_, **kw):
    kw.setdefault("approved_at", f"2026-09-2{id_[-1]}T01:00:00+00:00")
    return _post(id=id_, created_at="2026-09-20T00:00:00+00:00", **kw)


def test_caption_keys_agree_with_the_page_and_the_database_rule():
    # the same cases web/slots.test.mjs runs against captionKey; supabase/026 semasa_caption_keys implements the same rule
    cases = json.loads((Path(__file__).resolve().parents[2] / "rules" / "caption_keys.json").read_text(encoding="utf-8"))["cases"]
    assert len(cases) >= 6
    for c in cases:
        assert guard.caption_key(c["text"]) == c["key"], c["text"][:40]


def test_caption_key_ignores_case_punctuation_and_spaces_and_short_text():
    a = guard.caption_key("Notifikasi KOSMETIK, bukan kelulusan produk! NPRA menyemak dokumen.")
    b = guard.caption_key("notifikasi kosmetik bukan   kelulusan produk NPRA menyemak dokumen")
    assert a == b and a
    assert guard.caption_key("Ok juga") == ""                         # too little to call a copy
    assert len(guard.caption_key("x" * 400)) == guard.KEY_LEN


def test_a_post_scheduled_or_posted_outranks_an_approved_one_and_ties_go_to_the_first_approved():
    first, second = _p("p1", status="approved"), _p("p2", status="approved")
    live = [first, second]
    assert guard.blockers(first, live) == [] and guard.blockers(second, live)
    sent = _p("p9", status="scheduled", published={"facebook": {}})
    assert guard.blockers(first, [first, sent])                        # the sent one wins even though it is newer
    half = _p("p3", status="approved", published={"instagram": {"status": "sent"}})
    late = _p("p4", status="approved", approved_at="2026-09-19T00:00:00+00:00")
    assert guard.blockers(late, [late, half])                          # half sent is not undone by an earlier approval


def test_other_streams_other_slots_and_far_dates_do_not_block():
    me = _p("p1", status="approved")
    assert not guard.blockers(me, [me, _p("p0", status="scheduled", stream="linkedin")])
    assert not guard.blockers(me, [me, _p("p0", status="scheduled", slot="13:00", text={"bm": {"instagram": OTHER}})])
    far = _p("p0", status="posted", date="2026-05-01", slot="13:00")
    assert not guard.blockers(me, [me, far])                           # same words, but five months apart


def test_the_slot_clash_lets_exactly_one_post_go():
    store = _live(_p("p1", status="approved"), extra_posts=[_p("p2", status="approved")])
    buf = FakeBuffer()
    c = publisher.run(store, NOW, clients={"buffer": buf})
    assert c["scheduled"] == 3 and len(buf.created) == 3               # p1 only
    first, second = store.tables["semasa_posts"]
    assert first["status"] == "scheduled" and second["status"] == "approved" and second["published"] == {}
    assert "slot clash" in " ".join(second["errors"]["scan"])
    publisher.run(store, NOW, clients={"buffer": buf})
    assert len(buf.created) == 3                                       # nothing is sent on a later run either


def test_a_duplicate_of_a_post_already_sent_is_blocked_with_its_reason():
    done = _p("p8", status="posted", date="2026-09-22", slot="13:00", published={"facebook": {"status": "sent"}},
              hook="Notifikasi bukan kelulusan")
    store = _live(_p("p1", status="approved"), extra_posts=[done])
    buf = FakeBuffer()
    c = publisher.run(store, NOW, clients={"buffer": buf})
    assert c["blocked"] == 3 and not buf.created
    assert "duplicate" in " ".join(store.tables["semasa_posts"][0]["errors"]["scan"])
    assert "Notifikasi bukan kelulusan" in " ".join(store.tables["semasa_posts"][0]["errors"]["scan"])


def test_the_block_clears_when_the_other_post_is_rejected():
    holder = _p("p2", status="scheduled", slot="08:00", published={"x": {}})
    store = _live(_p("p1", status="approved"), extra_posts=[holder])
    buf = FakeBuffer()
    publisher.run(store, NOW, clients={"buffer": buf})
    assert not buf.created and store.tables["semasa_posts"][0]["errors"]["scan"]
    store.tables["semasa_posts"][1]["status"] = "rejected"
    c = publisher.run(store, NOW, clients={"buffer": buf})
    assert c["scheduled"] == 3 and store.tables["semasa_posts"][0]["errors"] == {}


def test_linkedin_clash_sends_one_post_to_the_profile():
    base = dict(stream="linkedin", lang="en", date="2026-09-24", slot="06:00",
                text={"en": {"linkedin": "The notification is not an approval: NPRA reads the file after it is on the shelf."}})
    store = _live(_p("p1", status="approved", **base), extra_posts=[_p("p2", status="approved", **base)])
    li = FakeLinkedIn()
    publisher.run(store, NOW, clients={"linkedin": li})
    assert len(li.sent) == 1
    assert store.tables["semasa_posts"][1]["published"] == {} and store.tables["semasa_posts"][1]["errors"]["scan"]
    assert CHANNELS and CAP
