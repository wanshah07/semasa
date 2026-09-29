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


def test_a_cleared_block_stops_reading_as_blocked():
    # 06:20 the picture was not ready (blocked); 11:20 it is ready: the post must not keep "the publisher blocked it"
    store = _store(_post(), media_status="processing")
    publisher.run(store, NOW)
    assert store.tables["semasa_posts"][0]["errors"]["scan"]
    store.tables["media_generations"][0]["status"] = "done"
    c = publisher.run(store, NOW)
    assert c["dry_run"] == 3 and store.tables["semasa_posts"][0]["errors"] == {}


def test_a_picture_deleted_after_approval_blocks():
    store = _store(_post(media_ids=["m1", "gone"]))
    c = publisher.run(store, NOW)
    assert c["blocked"] == 3 and "no longer exist" in " ".join(store.tables["semasa_posts"][0]["errors"]["scan"])


# --- live senders (Wan, 29 Sep 2026: Semasa replaces Studio on Friday 2 Oct) -----------------------------------------

from semasa import senders  # noqa: E402

CHANNELS = {"buffer": {"organizationId": "org", "facebook": "fb1", "instagram": "ig1", "threads": "th1",
                       "enabled": {"facebook": True, "instagram": True, "threads": True}},
            "linkedin": {"author": "urn:li:person:X"}}


class FakeBuffer:
    def __init__(self, existing=None, fail=None, status="scheduled"):
        self.created, self.existing, self.fail, self.status = [], list(existing or []), dict(fail or {}), status
        self.store = {}

    def create(self, channel_id, service, text, pictures, alt, due_at):
        f = self.fail.get(service)
        if f:
            if isinstance(f, list):
                kind = f.pop(0)
                if not f:
                    self.fail.pop(service)
            else:
                kind = f
            raise senders.SendError(kind, f"{kind} on {service}")
        pid = f"{len(self.created) + 1:024x}"
        p = {"id": pid, "status": "sending" if due_at is None else self.status, "dueAt": due_at, "text": text,
             "channelId": channel_id}
        self.created.append({"channel": channel_id, "service": service, "text": text, "pictures": pictures,
                             "due_at": due_at})
        self.store[pid] = p
        return p

    def confirm(self, pid):
        return {**self.store[pid], "status": "sent"}

    def get(self, pid):
        return self.store.get(pid) or next(p for p in self.existing if p["id"] == pid)

    def posts(self, channel_ids, start, end):
        return [p for p in self.existing if p["channelId"] in channel_ids]


class FakeLinkedIn:
    def __init__(self, fail=None):
        self.sent, self.fail = [], fail

    def post(self, text, pictures):
        if self.fail:
            raise senders.SendError(self.fail, "LinkedIn refused: nope")
        self.sent.append((text, pictures))
        return senders.LinkedInResult(urn=f"urn:li:share:{len(self.sent)}", url="u")


def _live(post, enabled=True, extra_posts=()):
    s = _store(post, enabled=enabled)
    s.tables["semasa_settings"].append({"key": "channels", "value": CHANNELS})
    s.tables["semasa_settings"][1]["value"] = {"linkedin": {"slots": ["06:00", "19:00"]}}
    s.tables["semasa_posts"] += list(extra_posts)
    return s


def test_buffer_schedules_every_channel_for_its_slot_and_locks_the_post():
    store, buf = _live(_post()), FakeBuffer()
    c = publisher.run(store, NOW, clients={"buffer": buf})
    assert c["scheduled"] == 3 and len(buf.created) == 3
    assert {x["due_at"] for x in buf.created} == {"2026-09-25T00:00:00+00:00"}
    assert buf.created[0]["pictures"] == ["https://cdn/m1.png"]
    p = store.tables["semasa_posts"][0]
    assert p["status"] == "scheduled" and set(p["published"]) == {"facebook", "instagram", "threads"}
    publisher.run(store, NOW, clients={"buffer": buf})           # a later run sends nothing twice
    assert len(buf.created) == 3


def test_a_post_already_in_buffer_is_adopted_never_sent_twice():
    already = {"id": "a" * 24, "status": "scheduled", "dueAt": "2026-09-25T00:00:00+00:00", "text": CAP,
               "channelId": "fb1"}
    store, buf = _live(_post()), FakeBuffer(existing=[already])
    c = publisher.run(store, NOW, clients={"buffer": buf})
    assert c["adopted"] == 1 and c["scheduled"] == 2
    assert [x["service"] for x in buf.created] == ["instagram", "threads"]
    assert store.tables["semasa_posts"][0]["published"]["facebook"]["id"] == "a" * 24


def test_a_full_buffer_queue_is_a_wait_not_an_error():
    store, buf = _live(_post()), FakeBuffer(fail={"threads": ["full"]})
    c = publisher.run(store, NOW, clients={"buffer": buf})
    p = store.tables["semasa_posts"][0]
    assert c["waiting"] == 1 and c["error"] == 0 and "threads" not in p["errors"]
    assert p["status"] == "approved"                             # still the publisher's to finish
    publisher.run(store, NOW, clients={"buffer": buf})           # room again: the wait clears itself
    assert store.tables["semasa_posts"][0]["status"] == "scheduled"


def test_a_transient_refusal_is_retried_once_and_a_real_one_is_not():
    store, buf = _live(_post()), FakeBuffer(fail={"threads": ["transient"], "facebook": "refused"})
    c = publisher.run(store, NOW, clients={"buffer": buf})
    p = store.tables["semasa_posts"][0]
    assert "threads" in p["published"] and c["error"] == 1 and "facebook" in p["errors"]
    publisher.run(store, NOW, clients={"buffer": buf})           # the same words are not tried again
    assert sum(1 for x in buf.created if x["service"] == "facebook") == 0


def test_a_slot_just_come_goes_now_and_is_confirmed_sent():
    store, buf = _live(_post(date="2026-09-24", slot="10:00")), FakeBuffer()
    publisher.run(store, NOW, clients={"buffer": buf})
    p = store.tables["semasa_posts"][0]
    assert {x["due_at"] for x in buf.created} == {None} and p["status"] == "posted"


def test_the_tally_marks_a_fired_post_posted_and_names_a_failed_channel():
    store, buf = _live(_post()), FakeBuffer()
    publisher.run(store, NOW, clients={"buffer": buf})
    for i, p in enumerate(buf.store.values()):
        p["status"] = "error" if i == 0 else "sent"
        p["error"] = {"message": "Instagram rejected the picture"} if i == 0 else None
    publisher.run(store, datetime(2026, 9, 25, 1, 0, tzinfo=UTC), clients={"buffer": buf})
    p, first = store.tables["semasa_posts"][0], buf.created[0]["service"]
    assert p["status"] == "scheduled" and p["errors"][first]["message"].endswith("rejected the picture")
    assert all(p["published"][c]["status"] == "sent" for c in p["published"] if c != first)


def test_studio_scheduled_posts_are_tallied_too():
    rec = {"id": "b" * 24, "status": "scheduled", "dueAt": "2026-09-24T00:00:00+00:00"}
    imported = _post(id="s1", status="scheduled", published={c: rec for c in ("facebook", "instagram", "threads")})
    store, buf = _live(imported), FakeBuffer(existing=[{**rec, "status": "sent", "channelId": "fb1", "text": CAP}])
    publisher.run(store, NOW, clients={"buffer": buf})
    assert store.tables["semasa_posts"][0]["status"] == "posted"


def _li(**kw):
    return _post(id=kw.pop("id", "L1"), stream="linkedin", lang="en", text={"en": {"linkedin": CAP}}, **kw)


def test_linkedin_waits_for_its_slot_then_posts_with_its_card():
    store, li = _live(_li(date="2026-09-24", slot="19:00")), FakeLinkedIn()
    c = publisher.run(store, NOW, clients={"linkedin": li})
    assert c["not_yet"] == 1 and li.sent == []
    c = publisher.run(store, datetime(2026, 9, 24, 11, 20, tzinfo=UTC), clients={"linkedin": li})
    p = store.tables["semasa_posts"][0]
    assert li.sent == [(CAP, ["https://cdn/m1.png"])] and p["status"] == "posted"
    assert p["published"]["linkedin"]["id"] == "urn:li:share:1" and p["published"]["linkedin"]["route"] == "composio+image"


def test_linkedin_daily_cap_and_a_missed_day_is_never_sent():
    posted = [_li(id=f"x{i}", status="posted", published={"linkedin": {"at": "2026-09-24T00:00:00+00:00"}})
              for i in range(2)]
    store, li = _live(_li(date="2026-09-24", slot="06:00"), extra_posts=posted), FakeLinkedIn()
    c = publisher.run(store, NOW, clients={"linkedin": li})
    assert c["waiting"] == 1 and li.sent == []
    c = publisher.run(_live(_li(date="2026-09-23", slot="19:00")), NOW, clients={"linkedin": li})
    assert c["overdue"] == 1 and li.sent == []


def test_linkedin_is_never_sent_twice_after_an_unanswered_attempt():
    store = _live(_li(date="2026-09-24", slot="06:00"))
    li = FakeLinkedIn(fail="refused")
    publisher.run(store, NOW, clients={"linkedin": li})
    assert "linkedin" in store.tables["semasa_posts"][0]["errors"]
    # a crash between "sending" and the answer: the next run must not post blind
    store2 = _live(_li(id="L2", date="2026-09-24", slot="06:00"))
    fp = [r for r in store.tables["semasa_publish_log"] if r["action"] == "sending"][0]["detail"]["fingerprint"]
    store2.tables["semasa_publish_log"].append({"post_id": "L2", "channel": "linkedin", "action": "sending",
                                                "detail": {"fingerprint": fp}, "at": "x"})
    ok = FakeLinkedIn()
    publisher.run(store2, NOW, clients={"linkedin": ok})
    assert ok.sent == [] and store2.tables["semasa_posts"][0]["errors"]["linkedin"]["unconfirmed"]


def test_the_switch_opens_by_itself_at_enabled_from_and_pause_wins():
    s = {"publishing": {"enabled": False, "enabled_from": "2026-10-02T12:00:00Z"}}
    assert not publisher.publishing_on(s, datetime(2026, 10, 2, 11, 59, tzinfo=UTC))
    assert publisher.publishing_on(s, datetime(2026, 10, 2, 12, 0, tzinfo=UTC))
    assert not publisher.publishing_on({"publishing": {**s["publishing"], "paused": True}},
                                       datetime(2026, 10, 3, tzinfo=UTC))
    assert not publisher.publishing_on({"publishing": {"enabled_from": "2026-10-02 12:00"}},  # no zone: never
                                       datetime(2026, 10, 3, tzinfo=UTC))
