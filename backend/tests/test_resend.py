"""Sending the failed channels of a half-sent post again (Wan, 16 Nov 2026: "move to new slot").

Two ws.regulab films lost channels to an outage on 16 Nov: one went to Instagram only (TikTok and Threads failed), the other
to Instagram and Threads (TikTok and Facebook failed). Nothing could send the missed channels: the publisher skipped a channel
with any record, blocked a moved post whole, and never looked at a `scheduled` post. The rules, each with its test below:

  1. a record the network has settled (sent, error) holds nothing in the queue and never blocks a move; a pending one does;
  2. a post a person MOVED after a failure has its failed channels handed over for the new slot, and only those;
  3. a failure for the slot the post still has is never retried by itself, and a sent channel is never sent twice;
  4. one post to a slot still holds: a moved post yields to a post already scheduled on the new slot;
  5. a record Zernio no longer holds after its moment ("Post not found") is settled as a failure, so rule 2 can apply;
  6. (18 Nov 2026) the same is found BEFORE the moment, for a LinkedIn hand-over made at least an hour ago, so the post can be
     moved while there is time;
  7. (18 Nov 2026) a LinkedIn post is handed to Zernio at most 30 hours before its slot, not days ahead.
"""

from datetime import UTC, datetime

import pytest
from fakestore import FakeStore
from test_publisher import CAP, CHANNELS, NOW
from test_zernio import FILM, ZCFG, FakeZernio

from semasa import guard, publisher, senders

OLD_DUE = "2026-09-23T00:00:00.000Z"            # 23 Sep 08:00 MYT: the slot the channels failed at (NOW is 24 Sep 10:00 MYT)
NEW_DATE, NEW_DUE = "2026-09-25", "2026-09-25T00:00:00+00:00"
ACC = {p: a["id"] for p, a in ZCFG["accounts"].items()}


def rec(ch, status, due=OLD_DUE, **kw):
    return {"id": f"{'0123456789'.index(str(len(ch)))}" * 24, "route": "zernio", "mode": "customScheduled", "status": status,
            "dueAt": due, "account": ACC[ch], "at": "2026-09-20T03:20:00+00:00", **kw}


def half_sent(date=NEW_DATE, slot="08:00", status="scheduled", **kw):
    """The 16 Nov post: a film queued to Instagram and Threads (TikTok rides with it). Instagram went out; TikTok and Threads
    failed at the old slot. `date` is where the post sits now: NEW_DATE = a person moved it."""
    p = {"id": "p1", "stream": "regulab", "lang": "bm", "status": status, "date": date, "slot": slot, "hook": "Hook",
         "channels": ["instagram", "threads"], "text": {"bm": {"instagram": CAP, "facebook": CAP, "threads": CAP}},
         "citation": "NPRA", "media_ids": ["m1"], "approved_at": "2026-09-01T00:00:00+00:00",
         "published": {"instagram": rec("instagram", "sent", url="https://ig/1"), "tiktok": rec("tiktok", "error"),
                       "threads": rec("threads", "error")},
         "errors": {"tiktok": {"message": "tiktok: Failed to download video: 402 Payment Required", "at": "x"},
                    "threads": {"message": "threads: token refresh failed", "at": "x"}}}
    p.update(kw)
    return p


def store_of(*posts, enabled=True, media=None):
    return FakeStore(
        semasa_settings=[{"key": "publishing", "value": {"enabled": enabled}},
                         {"key": "brand", "value": {"linkedin": {"slots": ["06:00", "19:00"]}}},
                         {"key": "channels", "value": {**CHANNELS, "zernio": ZCFG}}],
        semasa_posts=list(posts), media_generations=media or [dict(FILM[0], meta={**FILM[0]["meta"], "flow": "x"})],
        semasa_publish_log=[])


def post_of(store, pid="p1"):
    return next(p for p in store.tables["semasa_posts"] if p["id"] == pid)


# --- rule 1 -------------------------------------------------------------------------------------------------------------------

def test_a_settled_record_never_blocks_a_move_and_a_pending_one_still_does():
    due = publisher.due_utc(NEW_DATE, "08:00")
    settled = {"instagram": rec("instagram", "sent"), "threads": rec("threads", "error")}
    assert publisher.moved_since_handed_over(settled, due) == []
    pending = {**settled, "facebook": rec("facebook", "scheduled")}
    assert publisher.moved_since_handed_over(pending, due) == ["facebook 2026-09-23 08:00"]
    assert publisher.moved_since_handed_over({"facebook": rec("facebook", "sending")}, due) == ["facebook 2026-09-23 08:00"]


def test_which_records_are_dead_only_a_failure_for_another_moment():
    due_new, due_old = publisher.due_utc(NEW_DATE, "08:00"), publisher.due_utc("2026-09-23", "08:00")
    pub = half_sent()["published"]
    assert publisher.stale_failures(pub, due_new) == ["threads", "tiktok"]             # moved: both failures go again
    assert publisher.stale_failures(pub, due_old) == []                                # not moved: nothing by itself
    assert publisher.stale_failures({"instagram": rec("instagram", "sent")}, due_new) == []       # sent is never looked at
    assert publisher.stale_failures({"threads": rec("threads", "scheduled")}, due_new) == []      # pending is not a failure
    assert publisher.stale_failures({"threads": {"status": "error", "route": "zernio"}}, due_new) == []   # no moment: a person
    assert publisher.stale_failures({"linkedin": {"status": "error", "route": "composio", "dueAt": OLD_DUE}}, due_new) == []
    # a send-now fired up to 45 minutes after its slot: the same slot, never a re-send; a later slot is
    now_rec = {"status": "error", "route": "zernio", "mode": "shareNow", "dueAt": None, "at": "2026-09-23T00:30:00+00:00"}
    assert publisher.stale_failures({"threads": now_rec}, due_old) == []
    assert publisher.stale_failures({"threads": now_rec}, due_new) == ["threads"]
    assert publisher.resend_due({"date": "2026-09-25", "slot": "8h00", "published": pub}) == []     # unreadable: never raises


# --- rule 2 -------------------------------------------------------------------------------------------------------------------

def test_a_moved_half_sent_post_sends_only_its_failed_channels_at_the_new_slot_and_ends_posted():
    store, z = store_of(half_sent()), FakeZernio()
    c = publisher.run(store, NOW, clients={"zernio": z})
    assert sorted(x["service"] for x in z.created) == ["threads", "tiktok"]            # Instagram went out: never again
    assert {x["due_at"] for x in z.created} == {NEW_DUE} and all(x.get("video") for x in z.created)
    assert c["scheduled"] == 2 and c["resent"] == 2 and c["blocked"] == 0
    p = post_of(store)
    assert p["published"]["instagram"] == rec("instagram", "sent", url="https://ig/1")          # untouched, to the letter
    for ch in ("tiktok", "threads"):
        assert p["published"][ch]["status"] == "scheduled" and p["published"][ch]["dueAt"] == NEW_DUE
        assert p["published"][ch]["replaces"] == rec(ch, "error")["id"]                # which failed hand-over it replaces
    assert p["errors"] == {} and p["status"] == "scheduled"
    logs = [r for r in store.tables["semasa_publish_log"] if r["action"] == "scheduled"]
    assert {r["channel"] for r in logs} == {"tiktok", "threads"} and all(r["detail"]["failed_due_at"] == OLD_DUE for r in logs)

    publisher.run(store, NOW, clients={"zernio": z})                                    # a later run sends nothing twice
    assert len(z.created) == 2

    for made in z.store.values():                                                      # the new slot comes: both go out
        made["status"] = "sent"
    publisher.run(store, datetime(2026, 9, 25, 1, 0, tzinfo=UTC), clients={"zernio": z})
    p = post_of(store)
    assert p["status"] == "posted" and all(r["status"] == "sent" for r in p["published"].values())
    assert len(z.created) == 2


def test_an_approved_post_moved_and_approved_again_sends_its_failed_channels_too():
    # from the page an APPROVED half-sent post goes back to draft when it moves and is approved again (the gate)
    store, z = store_of(half_sent(status="approved")), FakeZernio()
    publisher.run(store, NOW, clients={"zernio": z})
    assert sorted(x["service"] for x in z.created) == ["threads", "tiktok"] and post_of(store)["status"] == "scheduled"


def test_a_resend_whose_slot_has_come_goes_now_and_the_post_is_posted():
    store, z = store_of(half_sent(date="2026-09-24", slot="10:00")), FakeZernio()
    publisher.run(store, NOW, clients={"zernio": z})
    p = post_of(store)
    assert {x["due_at"] for x in z.created} == {None} and len(z.created) == 2
    assert p["status"] == "posted" and all(r["status"] == "sent" for r in p["published"].values())


# --- rule 3 -------------------------------------------------------------------------------------------------------------------

def test_a_failure_for_the_slot_the_post_still_has_is_never_sent_again_by_itself():
    before = half_sent(date="2026-09-23")                                               # not moved
    store, z = store_of(dict(before)), FakeZernio()
    c = publisher.run(store, NOW, clients={"zernio": z})
    assert z.created == [] and c["considered"] == 0
    assert post_of(store) == before                                                    # the row is not written at all


def test_a_scheduled_post_with_nothing_failed_is_never_this_loops_business():
    # every channel in the queue, and one channel (Facebook) with no record at all: switched on after it was handed over.
    # Only a moved failure makes the loop pick a scheduled post up, so nothing is sent to a channel nobody approved it for.
    pub = {"instagram": rec("instagram", "scheduled", due=NEW_DUE), "threads": rec("threads", "sent")}
    store, z = store_of(half_sent(channels=None, published=pub, errors={})), FakeZernio()
    c = publisher.run(store, NOW, clients={"zernio": z})
    assert z.created == [] and c["considered"] == 0


def test_a_channel_still_in_the_queue_for_the_old_slot_blocks_the_whole_move():
    pub = {**half_sent()["published"], "instagram": rec("instagram", "scheduled")}      # Instagram still queued for 23 Sep
    store, z = store_of(half_sent(published=pub)), FakeZernio()
    c = publisher.run(store, NOW, clients={"zernio": z})
    p = post_of(store)
    assert z.created == [] and c["blocked"] == 2
    assert "still holds instagram 2026-09-23 08:00" in " ".join(p["errors"]["scan"])
    assert p["published"] == pub and p["status"] == "scheduled"                         # the failed records stay as they were


def test_a_resend_moved_onto_a_slot_already_gone_is_overdue_not_sent():
    store, z = store_of(half_sent(date="2026-09-24", slot="08:00")), FakeZernio()      # 08:00 was two hours ago
    c = publisher.run(store, NOW, clients={"zernio": z})
    assert z.created == [] and c["overdue"] == 2
    assert post_of(store)["published"]["tiktok"]["status"] == "error"


def test_with_publishing_off_a_resend_is_a_dry_run_of_the_failed_channels_only():
    store, z = store_of(half_sent(), enabled=False), FakeZernio()
    c = publisher.run(store, NOW, clients={"zernio": z})
    assert z.created == [] and c["dry_run"] == 2
    assert {r["channel"] for r in store.tables["semasa_publish_log"]} == {"tiktok", "threads"}
    assert post_of(store)["published"] == half_sent()["published"]


def test_a_resend_that_fails_for_a_moment_keeps_the_failed_record_and_is_tried_again_next_run():
    store, z = store_of(half_sent()), FakeZernio(fail={"threads": ["transient", "transient"]})   # both tries of the first run
    publisher.run(store, NOW, clients={"zernio": z})
    p = post_of(store)
    assert [x["service"] for x in z.created] == ["tiktok"]
    assert p["published"]["threads"] == rec("threads", "error")                         # still the failed record: evidence
    assert p["errors"]["threads"]["kind"] == "transient" and p["errors"]["threads"]["retry"] is True
    assert p["status"] == "scheduled" and "tiktok" not in p["errors"]
    publisher.run(store, NOW, clients={"zernio": z})                                    # the next run finishes the job
    p = post_of(store)
    assert sorted(x["service"] for x in z.created) == ["threads", "tiktok"]
    assert p["published"]["threads"]["dueAt"] == NEW_DUE and p["errors"] == {}


def test_a_resend_the_scheduler_refuses_is_not_hammered_and_moving_again_tries_again():
    store, z = store_of(half_sent()), FakeZernio(fail={"threads": "refused", "tiktok": "refused"})
    publisher.run(store, NOW, clients={"zernio": z})
    publisher.run(store, NOW, clients={"zernio": z})
    p = post_of(store)
    assert z.created == [] and p["errors"]["threads"]["kind"] == "refused"
    assert len([r for r in store.tables["semasa_publish_log"] if r["action"] == "error"]) == 2      # once each, not per run
    assert p["published"] == half_sent()["published"]
    z.fail.clear()
    post_of(store).update(date="2026-09-26")                                           # a person moves it once more
    publisher.run(store, NOW, clients={"zernio": z})
    assert sorted(x["service"] for x in z.created) == ["threads", "tiktok"]
    assert {x["due_at"] for x in z.created} == {"2026-09-26T00:00:00+00:00"} and post_of(store)["errors"] == {}


# --- rule 4 -------------------------------------------------------------------------------------------------------------------

def other(pid, status, **kw):
    cap = "Label makanan mesti menyatakan tarikh luput dengan jelas mengikut Peraturan Makanan 1985."
    p = {"id": pid, "stream": "regulab", "lang": "bm", "status": status, "date": NEW_DATE, "slot": "08:00", "hook": "Lain",
         "text": {"bm": {"instagram": cap, "facebook": cap, "threads": cap}}, "citation": "BKKM", "media_ids": ["m1"],
         "approved_at": "2026-09-10T00:00:00+00:00", "published": {}, "errors": {}}
    p.update(kw)
    return p


def test_a_moved_post_yields_to_a_post_already_scheduled_on_the_new_slot():
    held = {c: rec(c, "scheduled", due=NEW_DUE) for c in ("instagram", "facebook", "threads")}
    store, z = store_of(half_sent(), other("p2", "scheduled", published=held)), FakeZernio()
    c = publisher.run(store, NOW, clients={"zernio": z})
    assert z.created == [] and c["blocked"] == 2                                        # though it was approved first
    assert "slot clash" in " ".join(post_of(store)["errors"]["scan"])


def test_of_a_moved_post_and_a_newly_approved_one_on_one_slot_exactly_one_goes():
    store, z = store_of(half_sent(), other("p2", "approved")), FakeZernio()
    publisher.run(store, NOW, clients={"zernio": z})
    assert sorted(x["service"] for x in z.created) == ["threads", "tiktok"]            # the moved post, half out already
    assert post_of(store, "p2")["published"] == {} and "slot clash" in " ".join(post_of(store, "p2")["errors"]["scan"])


def test_the_guard_ranks_a_post_being_sent_again_the_same_from_both_sides():
    moved, queued = half_sent(), other("p2", "scheduled", published={"instagram": rec("instagram", "scheduled", due=NEW_DUE)})
    live, again = [moved, queued], frozenset({"p1"})
    assert guard.rank(moved)[0] == 0 and guard.rank(moved, again)[0] == 1 and guard.rank(queued, again)[0] == 0
    assert guard.blockers(queued, live, again) == [] and len(guard.blockers(moved, live, again)) == 1
    assert guard.blockers(moved, [moved], again) == []                                 # never blocked by itself


# --- rule 5 -------------------------------------------------------------------------------------------------------------------

class Login:
    """One Zernio login that holds some posts; any other id is its own "Post not found". `down` = an outage."""

    def __init__(self, holds=(), down=False):
        self.holds, self.down, self.asked = set(holds), down, []

    def _ask(self, post_id):
        self.asked.append(post_id)
        if self.down:
            raise senders.SendError("transient", "Zernio answered 503")
        if post_id not in self.holds:
            raise senders.SendError("refused", "Zernio refused (404): Post not found", status=404)

    def get(self, post_id, account_id=""):
        self._ask(post_id)
        return {"id": post_id, "status": "scheduled"}

    def gone(self, post_id):
        try:
            self._ask(post_id)
        except senders.SendError as exc:
            if exc.status == 404:
                return True
            raise
        return False


LOST_ID = "6" * 24


def li_post(**kw):
    """The 16 Nov LinkedIn post: handed to Zernio for 23 Sep 19:00 MYT (11:00 UTC), still `scheduled` hours later."""
    p = {"id": "li", "stream": "linkedin", "lang": "en", "status": "scheduled", "date": "2026-09-23", "slot": "19:00",
         "hook": "Can an air purifier stop a blood sugar spike?", "citation": "EC 1223/2009", "media_ids": ["m1"],
         "text": {"en": {"linkedin": "A regulation changed. Here is what it means for a formulator."}},
         "published": {"linkedin": {"id": LOST_ID, "route": "zernio", "mode": "customScheduled", "status": "scheduled",
                                    "dueAt": "2026-09-23T11:00:00.000Z", "account": ACC["linkedin"]}}, "errors": {}}
    p.update(kw)
    return p


def hub(*logins):
    return senders.ZernioHub({ACC["linkedin"]: logins[0], **{f"other{i}": c for i, c in enumerate(logins[1:])}})


def tally(store, z, now=NOW):
    counts = {}
    publisher.tally(store, None, now, counts, publisher.load_settings(store), zernio=z)
    return counts


CARD = [{"id": "m1", "status": "done", "generated_media_url": "https://cdn/c.png", "meta": {"alt": "x"}}]


def test_a_record_zernio_no_longer_holds_after_its_moment_is_settled_as_a_failure():
    store = store_of(li_post(), media=CARD)
    c = tally(store, hub(Login(), Login()))
    p = post_of(store, "li")
    assert c["confirmed"] == 1 and p["status"] == "scheduled"
    assert p["published"]["linkedin"]["status"] == "error" and p["published"]["linkedin"]["lost"] is True
    assert p["published"]["linkedin"]["id"] == LOST_ID                                  # the record is kept, only settled
    assert p["errors"]["linkedin"]["message"] == "linkedin: Zernio no longer holds this post and it was not sent"
    assert [r["action"] for r in store.tables["semasa_publish_log"]] == ["error"]


@pytest.mark.parametrize("why, logins, now", [
    ("its moment has not passed by 20 minutes", (Login(), Login()), datetime(2026, 9, 23, 11, 10, tzinfo=UTC)),
    ("the login that holds the account is down", (Login(down=True), Login()), NOW),
    ("another login could not be read: an outage is not proof", (Login(), Login(down=True)), NOW),
    ("another login holds the post", (Login(), Login(holds=[LOST_ID])), NOW),
])
def test_a_record_is_not_settled_as_lost(why, logins, now):
    store = store_of(li_post(), media=CARD)
    c = tally(store, hub(*logins), now)
    p = post_of(store, "li")
    assert c["confirmed"] == 0 and p["published"]["linkedin"]["status"] == "scheduled" and p["errors"] == {}, why


def test_a_record_with_no_readable_moment_is_never_settled_as_lost():
    held = dict(li_post()["published"]["linkedin"], dueAt=None)
    store = store_of(li_post(published={"linkedin": held}), media=CARD)
    assert tally(store, hub(Login(), Login()))["confirmed"] == 0


def test_a_lost_post_stays_put_until_a_person_moves_it_then_goes_again():
    store = store_of(li_post(), media=CARD)
    tally(store, hub(Login(), Login()))
    z = FakeZernio()
    assert publisher.run(store, NOW, clients={"zernio": z})["considered"] == 0 and z.created == []   # nothing by itself
    post_of(store, "li").update(date="2026-09-25", slot="06:00")                        # Wan moves it
    publisher.run(store, NOW, clients={"zernio": z})
    p = post_of(store, "li")
    assert [x["service"] for x in z.created] == ["linkedin"] and z.created[0]["due_at"] == "2026-09-24T22:00:00+00:00"
    assert p["published"]["linkedin"]["status"] == "scheduled" and p["published"]["linkedin"]["replaces"] == LOST_ID
    assert "lost" not in p["published"]["linkedin"] and p["errors"] == {} and p["status"] == "scheduled"


# --- the sender ---------------------------------------------------------------------------------------------------------------

class Resp:
    def __init__(self, body, status):
        self._body, self.status_code = body, status

    def json(self):
        if self._body is None:
            raise ValueError("no JSON")
        return self._body


class Http:
    def __init__(self, *answers):
        self.answers = list(answers)

    def request(self, method, url, **kw):
        return self.answers.pop(0)


def test_only_zernios_own_not_found_says_gone():
    z = senders.Zernio("k", session=Http(Resp({"error": "Post not found"}, 404)))
    with pytest.raises(senders.SendError) as e:
        z.get("x")
    assert e.value.status == 404 and e.value.kind == "refused"
    assert senders.Zernio("k", session=Http(Resp({"error": "Post not found"}, 404))).gone("x") is True
    assert senders.Zernio("k", session=Http(Resp({"post": {"_id": "x", "status": "scheduled"}}, 200))).gone("x") is False
    for not_proof in (Resp({"error": "boom"}, 503), Resp(None, 404), Resp({"error": "forbidden"}, 403), Resp({}, 429)):
        with pytest.raises(senders.SendError):
            senders.Zernio("k", session=Http(not_proof)).gone("x")


def test_the_hub_asks_every_login_before_calling_a_post_gone():
    a, b = Login(), Login()
    h = senders.ZernioHub({"acc1": a, "acc2": a, "acc3": b})
    assert h.gone("x") is True and (a.asked, b.asked) == (["x"], ["x"])                # each login once
    assert senders.ZernioHub({"acc1": Login(), "acc3": Login(holds=["x"])}).gone("x") is False
    with pytest.raises(senders.SendError):
        senders.ZernioHub({"acc1": Login(), "acc3": Login(down=True)}).gone("x")
    with pytest.raises(senders.SendError):
        senders.ZernioHub({}).gone("x")


# --- rule 6: a hand-over Zernio has dropped is found before its slot ------------------------------------------------------------

EARLY_DATE, EARLY_SLOT = "2026-09-25", "06:00"          # 24 Sep 22:00 UTC: twenty hours after NOW (24 Sep 02:00 UTC)
EARLY_DUE = "2026-09-24T22:00:00.000Z"


def early_post(made="2026-09-21T03:20:00+00:00", **kw):
    held = {"id": LOST_ID, "route": "zernio", "mode": "customScheduled", "status": "scheduled", "dueAt": EARLY_DUE,
            "account": ACC["linkedin"], "at": made}
    return li_post(date=EARLY_DATE, slot=EARLY_SLOT, published={"linkedin": held}, **kw)


def test_a_linkedin_hand_over_zernio_dropped_is_settled_before_its_slot_and_can_then_be_moved():
    store = store_of(early_post(), media=CARD)
    c = tally(store, hub(Login(), Login()))
    p = post_of(store, "li")
    rec_ = p["published"]["linkedin"]
    assert c["confirmed"] == 1 and p["status"] == "scheduled"
    assert rec_["status"] == "error" and rec_["lost"] is True and rec_["lost_early"] is True and rec_["id"] == LOST_ID
    assert p["errors"]["linkedin"]["message"] == f"linkedin: {publisher.LOST_EARLY}"
    z = FakeZernio()
    assert publisher.run(store, NOW, clients={"zernio": z})["considered"] == 0 and z.created == []   # nothing by itself
    post_of(store, "li").update(date="2026-09-26", slot="06:00")                                    # Wan moves it a day on
    publisher.run(store, datetime(2026, 9, 25, 4, 0, tzinfo=UTC), clients={"zernio": z})            # 26 Sep 06:00 is 18 h away
    p = post_of(store, "li")
    assert [x["service"] for x in z.created] == ["linkedin"] and p["published"]["linkedin"]["replaces"] == LOST_ID
    assert "lost" not in p["published"]["linkedin"] and p["errors"] == {}


@pytest.mark.parametrize("why, post, logins", [
    ("handed over only half an hour ago", early_post(made="2026-09-24T01:30:00+00:00"), (Login(), Login())),
    ("no hand-over time to judge by", early_post(made=None), (Login(), Login())),
    ("the login is down", early_post(), (Login(down=True), Login())),
    ("another login could not be read", early_post(), (Login(), Login(down=True))),
    ("another login holds it", early_post(), (Login(), Login(holds=[LOST_ID]))),
    ("this login still holds it", early_post(), (Login(holds=[LOST_ID]), Login())),
])
def test_a_hand_over_is_not_called_lost_early_without_proof(why, post, logins):
    store = store_of(post, media=CARD)
    c = tally(store, hub(*logins))
    p = post_of(store, "li")
    assert c["confirmed"] == 0 and p["published"]["linkedin"]["status"] == "scheduled" and p["errors"] == {}, why


def test_only_a_linkedin_record_is_looked_at_before_its_moment():
    held = dict(early_post()["published"]["linkedin"], account=ACC["instagram"])
    store = store_of(li_post(date=EARLY_DATE, slot=EARLY_SLOT, published={"instagram": held}, stream="regulab"), media=CARD)
    z = Login()
    assert tally(store, hub(z, Login()))["confirmed"] == 0 and z.asked == []           # not even asked


# --- rule 7: LinkedIn goes to Zernio at most 30 hours ahead ---------------------------------------------------------------------

def approved_li(date, slot):
    return li_post(date=date, slot=slot, status="approved", published={}, approved_at="2026-09-01T00:00:00+00:00")


def test_a_linkedin_post_is_handed_to_zernio_only_within_30_hours_of_its_slot():
    far = store_of(approved_li("2026-09-26", "06:00"), media=CARD)                      # 44 h after NOW
    z = FakeZernio()
    c = publisher.run(far, NOW, clients={"zernio": z})
    assert z.created == [] and c["not_yet"] == 1 and post_of(far, "li")["status"] == "approved"
    assert post_of(far, "li")["published"] == {}
    near = store_of(approved_li("2026-09-25", "06:00"), media=CARD)                     # 20 h
    z = FakeZernio()
    publisher.run(near, NOW, clients={"zernio": z})
    assert [x["service"] for x in z.created] == ["linkedin"] and post_of(near, "li")["status"] == "scheduled"
    edge = store_of(approved_li("2026-09-25", "19:00"), media=CARD)                     # 33 h: waits for the next runs
    z = FakeZernio()
    publisher.run(edge, NOW, clients={"zernio": z})
    assert z.created == []
    publisher.run(edge, datetime(2026, 9, 24, 11, 20, tzinfo=UTC), clients={"zernio": z})   # 24 Sep 19:20 MYT: 23.7 h ahead
    assert [x["service"] for x in z.created] == ["linkedin"]


def test_the_lead_does_not_apply_to_the_other_platforms():
    store, z = _store_ig(), FakeZernio()
    publisher.run(store, NOW, clients={"zernio": z})
    assert {"instagram", "threads"} <= {x["service"] for x in z.created}               # six days ahead, still handed over


def _store_ig():
    p = half_sent(date="2026-09-30", slot="08:00", status="approved", published={}, errors={})     # six days ahead
    return store_of(p)
