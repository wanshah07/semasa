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


class GhostPostBuffer(FakeBuffer):
    """A 'transient' create() that actually reached Buffer and made the post before the response timed out."""

    def create(self, channel_id, service, text, pictures, alt, due_at):
        if service == "threads" and not any(c["service"] == "threads" for c in self.created):
            pid = "ghost" + "0" * 19
            self.existing.append({"id": pid, "status": "scheduled", "dueAt": due_at, "text": text,
                                  "channelId": channel_id})
            raise senders.SendError("transient", "timeout waiting for Buffer's answer")
        return super().create(channel_id, service, text, pictures, alt, due_at)


def test_a_transient_failure_whose_post_landed_anyway_is_adopted_not_duplicated():
    # publisher.py#204: the pre-attempt view cache must be refreshed before deciding whether a failed create()
    # actually landed, or the check always misses a post made just now and resends it -> a duplicate post
    store, buf = _live(_post()), GhostPostBuffer()
    c = publisher.run(store, NOW, clients={"buffer": buf})
    p = store.tables["semasa_posts"][0]
    assert p["published"]["threads"]["id"].startswith("ghost")
    assert sum(1 for x in buf.created if x["service"] == "threads") == 0   # create() never actually ran twice
    assert c["error"] == 0


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


def test_the_tally_never_calls_a_post_posted_when_every_channel_is_switched_off():
    # Buffer errored on one channel; with all three channels then switched off in settings the tally has no channel
    # left to judge, and all([]) must not promote a post Buffer still holds
    store, buf = _live(_post()), FakeBuffer()
    publisher.run(store, NOW, clients={"buffer": buf})
    for i, p in enumerate(buf.store.values()):
        p["status"] = "error" if i == 0 else "sent"
        p["error"] = {"message": "rejected"} if i == 0 else None
    off = {**CHANNELS, "buffer": {**CHANNELS["buffer"], "enabled": {"facebook": False, "instagram": False, "threads": False}}}
    store.tables["semasa_settings"][-1]["value"] = off
    publisher.run(store, datetime(2026, 9, 25, 1, 0, tzinfo=UTC), clients={"buffer": buf})
    assert store.tables["semasa_posts"][0]["status"] == "scheduled"


def test_studio_scheduled_posts_are_tallied_too():
    rec = {"id": "b" * 24, "status": "scheduled", "dueAt": "2026-09-24T00:00:00+00:00"}
    imported = _post(id="s1", status="scheduled", published={c: rec for c in ("facebook", "instagram", "threads")})
    store, buf = _live(imported), FakeBuffer(existing=[{**rec, "status": "sent", "channelId": "fb1", "text": CAP}])
    publisher.run(store, NOW, clients={"buffer": buf})
    assert store.tables["semasa_posts"][0]["status"] == "posted"


def _li(**kw):
    kw.setdefault("text", {"en": {"linkedin": CAP}})
    return _post(id=kw.pop("id", "L1"), stream="linkedin", lang="en", **kw)


def test_linkedin_waits_for_its_slot_then_posts_with_its_card():
    store, li = _live(_li(date="2026-09-24", slot="19:00")), FakeLinkedIn()
    c = publisher.run(store, NOW, clients={"linkedin": li})
    assert c["not_yet"] == 1 and li.sent == []
    c = publisher.run(store, datetime(2026, 9, 24, 11, 20, tzinfo=UTC), clients={"linkedin": li})
    p = store.tables["semasa_posts"][0]
    assert li.sent == [(CAP, ["https://cdn/m1.png"])] and p["status"] == "posted"
    assert p["published"]["linkedin"]["id"] == "urn:li:share:1" and p["published"]["linkedin"]["route"] == "composio+image"


def test_linkedin_daily_cap_and_a_missed_day_is_never_sent():
    # earlier posts of the day carry their own words: the same words twice are blocked (guard.py), not capped
    posted = [_li(id=f"x{i}", status="posted", published={"linkedin": {"at": "2026-09-24T00:00:00+00:00"}},
                  updated_at="2026-09-24T00:00:05+00:00",
                  text={"en": {"linkedin": f"Earlier post number {i} of the day, about something else entirely."}})
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


def test_a_transient_linkedin_error_is_never_retried_in_the_same_run_but_is_by_the_next():
    # By the senders' contract a TRANSIENT LinkedIn failure happened before the post call (account lookup, picture
    # fetch/upload): nothing can be on LinkedIn. It is not retried within the run, it closes its "sending" line (so the
    # unanswered-attempt guard does not fire) and the next run sends it. A failure after the post call is a refusal.
    store = _live(_li(date="2026-09-24", slot="06:00"))
    li = FakeLinkedIn(fail="transient")
    c = publisher.run(store, NOW, clients={"linkedin": li})
    assert li.sent == [] and c["sent"] == 0 and c["retry"] == 1 and c["error"] == 0
    rec = store.tables["semasa_posts"][0]["errors"]["linkedin"]
    assert rec["kind"] == "transient" and rec["attempts"] == 1 and rec["retry"] is True
    log = store.tables["semasa_publish_log"]
    assert [r["action"] for r in log] == ["sending", "error"] and log[1]["detail"]["before_post"] is True
    li.fail = None
    c = publisher.run(store, datetime(2026, 9, 24, 3, 20, tzinfo=UTC), clients={"linkedin": li})
    p = store.tables["semasa_posts"][0]
    assert len(li.sent) == 1 and c["sent"] == 1 and p["status"] == "posted" and "linkedin" not in p["errors"]


def test_a_linkedin_refusal_is_final_for_those_words():
    store, li = _live(_li(date="2026-09-24", slot="06:00")), FakeLinkedIn(fail="refused")
    publisher.run(store, NOW, clients={"linkedin": li})
    li.fail = None
    c = publisher.run(store, datetime(2026, 9, 24, 3, 20, tzinfo=UTC), clients={"linkedin": li})
    assert li.sent == [] and c["sent"] == 0 and store.tables["semasa_posts"][0]["errors"]["linkedin"]["kind"] == "refused"


def test_the_switch_opens_by_itself_at_enabled_from_and_pause_wins():
    s = {"publishing": {"enabled": False, "enabled_from": "2026-10-02T12:00:00Z"}}
    assert not publisher.publishing_on(s, datetime(2026, 10, 2, 11, 59, tzinfo=UTC))
    assert publisher.publishing_on(s, datetime(2026, 10, 2, 12, 0, tzinfo=UTC))
    assert not publisher.publishing_on({"publishing": {**s["publishing"], "paused": True}},
                                       datetime(2026, 10, 3, tzinfo=UTC))
    assert not publisher.publishing_on({"publishing": {"enabled_from": "2026-10-02 12:00"}},  # no zone: never
                                       datetime(2026, 10, 3, tzinfo=UTC))


# --- a Motion film queued to chosen platforms (Wan, 26 Oct 2026) ----------------------------------------------------

VIDEO = {"id": "m1", "status": "done", "type": "video", "mode": "clip", "generated_media_url": "https://cdn/film.mp4",
         "meta": {"poster_url": "https://cdn/film.jpg", "width": 1080, "height": 1920}}


class VideoBuffer(FakeBuffer):
    def create_video(self, channel_id, service, text, video, due_at):
        pid = f"{len(self.created) + 1:024x}"
        p = {"id": pid, "status": "sending" if due_at is None else self.status, "dueAt": due_at, "text": text,
             "channelId": channel_id}
        self.created.append({"channel": channel_id, "service": service, "text": text, "video": video, "due_at": due_at})
        self.store[pid] = p
        return p


class VideoLinkedIn(FakeLinkedIn):
    def post_video(self, text, video_url):
        self.sent.append((text, video_url))
        return senders.LinkedInResult(urn="urn:li:share:77", url="u")


def _film(post):
    store = _live(post)
    store.tables["media_generations"][0].update(VIDEO)
    return store


def test_a_film_goes_only_to_the_platforms_it_was_queued_to_as_a_video_never_as_a_picture():
    store, buf = _film(_post(channels=["instagram", "threads"])), VideoBuffer()
    c = publisher.run(store, NOW, clients={"buffer": buf})
    assert c["scheduled"] == 2 and {x["service"] for x in buf.created} == {"instagram", "threads"}
    assert all(x["video"] == {"url": "https://cdn/film.mp4", "thumbnail": "https://cdn/film.jpg", "vertical": True}
               for x in buf.created)
    p = store.tables["semasa_posts"][0]
    assert set(p["published"]) == {"instagram", "threads"} and p["status"] == "scheduled", "done when the CHOSEN ones are"
    publisher.run(store, NOW, clients={"buffer": buf})
    assert len(buf.created) == 2


def test_a_film_post_with_no_channels_chosen_goes_to_all_three():
    store, buf = _film(_post()), VideoBuffer()
    publisher.run(store, NOW, clients={"buffer": buf})
    assert {x["service"] for x in buf.created} == {"instagram", "facebook", "threads"}


def test_a_film_to_linkedin_posts_as_a_native_video_once():
    store, li = _film(_li(date="2026-09-24", slot="06:00")), VideoLinkedIn()
    publisher.run(store, datetime(2026, 9, 24, 11, 20, tzinfo=UTC), clients={"linkedin": li})
    p = store.tables["semasa_posts"][0]
    assert li.sent == [(CAP, "https://cdn/film.mp4")] and p["published"]["linkedin"]["route"] == "composio+video"
    publisher.run(store, datetime(2026, 9, 24, 11, 40, tzinfo=UTC), clients={"linkedin": li})
    assert len(li.sent) == 1


def test_a_picture_post_is_still_sent_as_pictures():
    store, buf = _live(_post()), VideoBuffer()
    publisher.run(store, NOW, clients={"buffer": buf})
    assert all("video" not in x and x["pictures"] == ["https://cdn/m1.png"] for x in buf.created)


def test_the_channels_of_a_post_never_widen_what_settings_switched_off():
    settings = {"channels": {"buffer": {"enabled": {"threads": False}}}}
    assert publisher.post_channels(settings, {"stream": "regulab", "channels": ["instagram", "threads"]}) == ["instagram"]
    assert publisher.post_channels(settings, {"stream": "regulab", "channels": ["linkedin"]}) == ["instagram", "facebook"]
    assert publisher.post_channels(settings, {"stream": "regulab"}) == ["instagram", "facebook"]


# --- review fixes, 7 Nov 2026 (scratchpad bugA t1-t3) -----------------------------------------------------------------

class Outage(FakeBuffer):
    """Buffer down (503) on create, or on the posts listing, until `down` is cleared."""

    def __init__(self, where="create", **kw):
        super().__init__(**kw)
        self.down, self.where = True, where

    def create(self, *a, **k):
        if self.down and self.where == "create":
            raise senders.SendError("transient", "Buffer answered 503")
        return super().create(*a, **k)

    def posts(self, *a):
        if self.down and self.where == "posts":
            raise senders.SendError("transient", "Buffer rate limit (429)")
        return super().posts(*a)


def test_a_transient_buffer_outage_is_retried_by_the_next_run_not_parked_for_ever():
    for where in ("create", "posts"):
        store, buf = _live(_post()), Outage(where)
        c = publisher.run(store, NOW, clients={"buffer": buf})
        p = store.tables["semasa_posts"][0]
        assert c["retry"] == 3 and c["error"] == 0 and p["status"] == "approved", where
        assert {k: v["attempts"] for k, v in p["errors"].items() if k in CHANNELS["buffer"]["enabled"]} == \
            {"facebook": 1, "instagram": 1, "threads": 1}
        buf.down = False
        publisher.run(store, NOW, clients={"buffer": buf})
        p = store.tables["semasa_posts"][0]
        assert p["status"] == "scheduled" and len(buf.created) == 3, where
        assert not any(k in p["errors"] for k in ("facebook", "instagram", "threads"))


def test_a_transient_failure_gives_up_after_five_runs_and_says_so():
    store, buf = _live(_post()), Outage()
    for _ in range(publisher.TRANSIENT_GIVE_UP):
        publisher.run(store, NOW, clients={"buffer": buf})
    rec = store.tables["semasa_posts"][0]["errors"]["threads"]
    assert rec["attempts"] == 5 and rec["gave_up"] is True and "5 runs" in rec["message"]
    buf.down = False
    c = publisher.run(store, NOW, clients={"buffer": buf})       # final now: Wan edits and approves to send again
    assert len(buf.created) == 0 and c["retry"] == 0


def test_a_transient_error_parked_by_the_old_publisher_is_tried_again():
    # before this fix a transient failure was stored with its fingerprint and skipped for ever; such a record has no
    # `attempts`, and the channel must now be retried instead of staying parked
    store, buf = _live(_post()), Outage()
    publisher.run(store, NOW, clients={"buffer": buf})
    p = store.tables["semasa_posts"][0]
    for ch in ("facebook", "instagram", "threads"):
        p["errors"][ch] = {k: v for k, v in p["errors"][ch].items() if k not in ("attempts", "retry")}
    buf.down = False
    publisher.run(store, NOW, clients={"buffer": buf})
    assert store.tables["semasa_posts"][0]["status"] == "scheduled" and len(buf.created) == 3


PREFIX = "KENYATAAN MEDIA KKM: Notifikasi kosmetik bukan kelulusan produk dan NPRA menyemak dokumen selepas pa"


def test_a_different_post_with_the_same_opening_is_never_adopted():
    assert len(PREFIX) == 100
    a = PREFIX + "sar. Produk A dibatalkan kerana mengandungi merkuri."
    b = PREFIX + "sar. Produk B dibatalkan kerana mengandungi hidrokuinon dan tretinoin."
    existing = [{"id": f"{i:x}" * 24, "status": "scheduled", "dueAt": "2026-09-25T00:00:00+00:00", "text": a,
                 "channelId": ch} for i, ch in enumerate(("fb1", "ig1", "th1"), 10)]
    store = _live(_post(text={"bm": {"instagram": b, "facebook": b, "threads": b}}))
    buf = FakeBuffer(existing=existing)
    c = publisher.run(store, NOW, clients={"buffer": buf})
    p = store.tables["semasa_posts"][0]
    assert c["adopted"] == 0 and c["scheduled"] == 3 and len(buf.created) == 3
    assert all(r["route"] == "buffer" for r in p["published"].values())


def test_the_same_words_at_another_time_are_not_adopted():
    # same caption, but Buffer holds it 13 hours away from this post's slot: not this post's channel
    other = {"id": "c" * 24, "status": "scheduled", "dueAt": "2026-09-25T13:00:00+00:00", "text": CAP, "channelId": "fb1"}
    store, buf = _live(_post()), FakeBuffer(existing=[other])
    c = publisher.run(store, NOW, clients={"buffer": buf})
    assert c["adopted"] == 0 and {x["service"] for x in buf.created} == {"facebook", "instagram", "threads"}


def test_a_buffer_post_another_post_already_records_is_not_adopted():
    # another post (since moved to 13:00 in Semasa) still records that Buffer post as its own Facebook channel
    rec = {"id": "d" * 24, "status": "scheduled", "dueAt": "2026-09-25T00:00:00+00:00"}
    holder = _post(id="p0", status="scheduled", date="2026-09-25", slot="13:00",
                   text={"bm": {"instagram": "x", "facebook": "x", "threads": "x"}}, published={"facebook": rec})
    store = _live(_post(), extra_posts=[holder])
    buf = FakeBuffer(existing=[{**rec, "text": CAP, "channelId": "fb1"}])
    c = publisher.run(store, NOW, clients={"buffer": buf})
    p = store.tables["semasa_posts"][0]
    assert c["adopted"] == 0 and c["scheduled"] == 3
    assert p["published"]["facebook"]["id"] != "d" * 24


class EditedMidRun(FakeBuffer):
    """Wan edits the post in the page (back to draft, updated_at moves) while the run is sending its first channel."""

    def __init__(self, store, **kw):
        super().__init__(**kw)
        self.db = store

    def create(self, *a, **k):
        out = super().create(*a, **k)
        if len(self.created) == 1:
            row = self.db.tables["semasa_posts"][0]
            row.update(status="draft", updated_at="2026-09-24T02:00:30+00:00")
        return out


def test_a_post_changed_while_the_run_sends_it_is_left_alone_and_keeps_what_buffer_holds():
    store = _live(_post(updated_at="2026-09-24T01:00:00+00:00"))
    buf = EditedMidRun(store)
    c = publisher.run(store, NOW, clients={"buffer": buf})
    p = store.tables["semasa_posts"][0]
    assert len(buf.created) == 1 and c["changed"] == 1               # the second channel was not sent
    assert p["status"] == "draft"                                    # the run's final write never overwrote the edit
    assert list(p["published"]) == [buf.created[0]["service"]]       # and the channel Buffer holds is recorded


def test_a_post_changed_since_the_run_read_it_is_not_sent():
    store, buf = _live(_post(updated_at="2026-09-24T01:00:00+00:00")), FakeBuffer()
    real = publisher.media_for

    def media_then_edit(st, ids):
        st.tables["semasa_posts"][0]["updated_at"] = "2026-09-24T02:00:10+00:00"     # saved in the page meanwhile
        return real(st, ids)

    publisher.media_for = media_then_edit
    try:
        c = publisher.run(store, NOW, clients={"buffer": buf})
    finally:
        publisher.media_for = real
    assert buf.created == [] and c["changed"] == 1
    c = publisher.run(store, NOW, clients={"buffer": buf})          # the next run reads the new version and sends it
    assert len(buf.created) == 3 and store.tables["semasa_posts"][0]["status"] == "scheduled"


def test_a_missed_final_write_is_healed_by_the_next_run():
    # every channel is in Buffer but the status write missed its pin: the next run promotes it with nothing to send
    rec = {"id": "e" * 24, "status": "scheduled", "dueAt": "2026-09-25T00:00:00+00:00"}
    store, buf = _live(_post(published={c: rec for c in ("facebook", "instagram", "threads")})), FakeBuffer()
    publisher.run(store, NOW, clients={"buffer": buf})
    assert store.tables["semasa_posts"][0]["status"] == "scheduled" and buf.created == []


def test_one_post_that_crashes_never_stops_the_others_or_the_tally():
    bad = _post(id="bad", date="2026-09-25", slot="8h00",
                text={"bm": {k: "Satu post lain yang rosak slotnya, dengan perkataan berbeza." for k in
                             ("instagram", "facebook", "threads")}})
    store, buf = _live(_post(), extra_posts=[bad]), FakeBuffer()
    store.tables["semasa_posts"].reverse()                           # the broken one is read first
    tallied = []
    real = publisher.tally
    publisher.tally = lambda *a, **k: tallied.append(1)
    try:
        c = publisher.run(store, NOW, clients={"buffer": buf})
    finally:
        publisher.tally = real
    assert c["failed"] == 1 and c["scheduled"] == 3 and tallied == [1]


class ConfirmDown(FakeBuffer):
    def confirm(self, pid):
        raise senders.SendError("transient", "Buffer unreachable: read timed out")


def test_a_share_now_whose_read_back_fails_is_recorded_unconfirmed_and_never_sent_twice():
    store, buf = _live(_post(date="2026-09-24", slot="10:00")), ConfirmDown()
    c = publisher.run(store, NOW, clients={"buffer": buf})
    p = store.tables["semasa_posts"][0]
    assert c["error"] == 0 and len(buf.created) == 3
    assert all(r["unconfirmed"] is True and r["id"] for r in p["published"].values())
    publisher.run(store, NOW, clients={"buffer": buf})
    assert len(buf.created) == 3                                     # recorded: never created a second time
    for bp in buf.store.values():
        bp["status"] = "sent"
    publisher.run(store, datetime(2026, 9, 24, 3, 0, tzinfo=UTC), clients={"buffer": buf})
    assert store.tables["semasa_posts"][0]["status"] == "posted"     # the tally settled it


def test_the_linkedin_cap_counts_today_even_past_the_1000_row_read_limit():
    old = [_li(id=f"o{i}", status="posted", date="2026-08-01", published={"linkedin": {"at": "2026-08-01T00:00:00+00:00"}},
               updated_at="2026-08-02T00:00:00+00:00", text={"en": {"linkedin": f"Old post {i} about another thing."}})
           for i in range(8)]
    today = [_li(id=f"t{i}", status="posted", published={"linkedin": {"at": "2026-09-24T00:10:00+00:00"}},
                 updated_at="2026-09-24T00:10:01+00:00", text={"en": {"linkedin": f"Today's post {i}, unrelated words."}})
             for i in range(2)]
    store = _live(_li(date="2026-09-24", slot="06:00"), extra_posts=old + today)
    store.max_rows = 5                                               # PostgREST's cap, shrunk: the old posts fill it
    assert publisher.linkedin_sent_on(store, publisher.myt_date(NOW)) == 2


def test_a_linkedin_slot_after_the_last_run_goes_at_the_first_run_next_day_not_overdue():
    en = "Cosmetic notification is not product approval. The regulator reviews the file after the product reaches the market."
    store = _live(_li(date="2026-09-24", slot="20:00", text={"en": {"linkedin": en}}, media_ids=[]))
    store.tables["semasa_settings"][1]["value"] = {"linkedin": {"slots": ["20:00"]}}
    li = FakeLinkedIn()
    for h in (3, 11):                                                # 11:20 and 19:20 MYT: not yet
        assert publisher.run(store, datetime(2026, 9, 24, h, 20, tzinfo=UTC), clients={"linkedin": li})["not_yet"] == 1
    c = publisher.run(store, datetime(2026, 9, 24, 22, 20, tzinfo=UTC), clients={"linkedin": li})   # 06:20 next day
    assert c["sent"] == 1 and c["overdue"] == 0 and store.tables["semasa_posts"][0]["status"] == "posted"
    # one day later still is overdue, as before
    late = _live(_li(date="2026-09-23", slot="20:00", text={"en": {"linkedin": en}}, media_ids=[]))
    assert publisher.run(late, datetime(2026, 9, 24, 22, 20, tzinfo=UTC), clients={"linkedin": li})["overdue"] == 1


def test_li_send_day():
    from datetime import date
    d = publisher.due_utc
    assert publisher.li_send_day(d("2026-09-24", "06:00")) == date(2026, 9, 24)
    assert publisher.li_send_day(d("2026-09-24", "19:20")) == date(2026, 9, 24)
    assert publisher.li_send_day(d("2026-09-24", "19:21")) == date(2026, 9, 25)
    assert publisher.li_send_day(d("2026-09-24", "23:59")) == date(2026, 9, 25)


def test_a_half_sent_post_moved_afterwards_does_not_send_the_rest_at_the_new_slot():
    # scratchpad bugA t3: Facebook went to Buffer for 25 Sep 08:00, then the post was moved to 26 Sep 13:00 and approved
    # again. Buffer still holds 25 Sep 08:00: the other channels must not go out at the new slot.
    store, buf = _live(_post()), FakeBuffer(fail={"threads": ["full"], "instagram": ["full"]})
    publisher.run(store, NOW, clients={"buffer": buf})
    p = store.tables["semasa_posts"][0]
    assert list(p["published"]) == ["facebook"]
    p.update(date="2026-09-26", slot="13:00", status="approved")
    c = publisher.run(store, NOW, clients={"buffer": buf})
    p = store.tables["semasa_posts"][0]
    assert len(buf.created) == 1 and c["blocked"] == 2
    assert "facebook 2026-09-25 08:00" in " ".join(p["errors"]["scan"])


# ---- Instagram needs the branded cover (Wan, 11 Nov 2026: "untuk instagram saja, wajib ada cover image macam dipersetujui")
def _cover_store(meta, mtype="image", mode="slides", reports=None, stream="regulab"):
    media = {"id": "m1", "status": "done", "generated_media_url": "https://cdn/m1.png", "type": mtype, "mode": mode, "meta": meta}
    return FakeStore(
        semasa_settings=[{"key": "publishing", "value": {"enabled": False}}, {"key": "brand", "value": {}}],
        semasa_posts=[_post(stream=stream)], media_generations=[media], semasa_publish_log=[],
        semasa_motions=[{"id": k, "check_report": v} for k, v in (reports or {}).items()])


def _blocked(store):
    return {(r["channel"], r["action"]) for r in store.tables["semasa_publish_log"]}


def test_a_carousel_without_its_cover_is_held_back_from_instagram_only():
    store = _cover_store({"alt": "x", "cover": False, "slide_urls": ["https://cdn/1.jpg", "https://cdn/2.jpg"]})
    c = publisher.run(store, NOW)
    got = _blocked(store)
    assert ("instagram", "blocked") in got and ("instagram", "dry_run") not in got
    assert ("facebook", "dry_run") in got and ("threads", "dry_run") in got, "the other platforms are not held"
    why = [r for r in store.tables["semasa_publish_log"] if r["channel"] == "instagram"][0]["detail"]["why"][0]
    assert "branded cover" in why and c["blocked"] == 1


def test_a_carousel_with_its_cover_goes_to_instagram():
    store = _cover_store({"alt": "x", "cover": True, "slide_urls": ["https://cdn/1.jpg", "https://cdn/2.jpg"]})
    publisher.run(store, NOW)
    assert ("instagram", "dry_run") in _blocked(store) and ("instagram", "blocked") not in _blocked(store)


def test_a_film_needs_the_cover_in_its_report_or_added_afterwards():
    base = {"alt": "x", "flow": "motion", "motion_id": "f1"}
    no = _cover_store(base, mtype="video", mode="clip", reports={"f1": {}})
    publisher.run(no, NOW)
    assert ("instagram", "blocked") in _blocked(no)
    native = _cover_store(base, mtype="video", mode="clip", reports={"f1": {"cover": {"seconds": 1.1}}})
    publisher.run(native, NOW)
    assert ("instagram", "dry_run") in _blocked(native), "a film made with the cover"
    added = _cover_store({**base, "cover_added_at": "2026-11-11T05:00:00+00:00"}, mtype="video", mode="clip", reports={"f1": {}})
    publisher.run(added, NOW)
    assert ("instagram", "dry_run") in _blocked(added), "a film the cover was added to afterwards"


def test_a_single_card_and_a_design_artwork_need_no_cover():
    single = _cover_store({"alt": "x"}, mode="prompt")
    publisher.run(single, NOW)
    assert ("instagram", "dry_run") in _blocked(single)
    design = _cover_store({"alt": "x", "design": True, "cover": False, "slide_urls": ["https://cdn/1.jpg"]})
    publisher.run(design, NOW)
    assert ("instagram", "dry_run") in _blocked(design)


def test_the_gap_helper_names_the_missing_cover_and_a_film_report_that_cannot_be_read_blocks_safely():
    carousel = {"mode": "slides", "type": "image", "meta": {"cover": False}}
    film = {"mode": "clip", "type": "video", "meta": {"flow": "motion", "motion_id": "f9"}}
    assert "carousel" in publisher.instagram_cover_gap([carousel], {}) and "film" in publisher.instagram_cover_gap([film], {})
    assert publisher.instagram_cover_gap([{"mode": "prompt", "type": "image", "meta": {}}], {}) == ""
    assert publisher.film_has_cover({"cover_added_at": "x"}, None) and not publisher.film_has_cover({}, {})
