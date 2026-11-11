"""Zernio beside Buffer (Wan, 10 Nov 2026): three logins behind one sender, what each platform takes, a Threads chain,
TikTok for films only, and Buffer untouched while Zernio is off."""

import pytest
from fakestore import FakeStore
from test_publisher import CAP, CHANNELS, NOW, FakeBuffer, _post

from semasa import publisher, senders

ZCFG = {"enabled": True, "accounts": {"instagram": {"id": "a" * 24, "key": "1"}, "threads": {"id": "b" * 24, "key": "1"},
                                      "facebook": {"id": "c" * 24, "key": "2"}, "linkedin": {"id": "d" * 24, "key": "2"},
                                      "tiktok": {"id": "e" * 24, "key": "3"}}}


class FakeZernio(FakeBuffer):
    def create_video(self, channel_id, service, text, video, due_at):
        p = self.create(channel_id, service, text, [], "", due_at)
        self.created[-1]["video"] = video["url"]
        return p

    def get(self, pid, account_id=""):
        return super().get(pid)


def _store(post, zcfg=ZCFG, media=None):
    return FakeStore(
        semasa_settings=[{"key": "publishing", "value": {"enabled": True}},
                         {"key": "brand", "value": {"linkedin": {"slots": ["06:00", "19:00"]}}},
                         {"key": "channels", "value": {**CHANNELS, "zernio": zcfg}}],
        semasa_posts=[post],
        media_generations=media or [{"id": "m1", "status": "done", "mode": "slides", "generated_media_url": "https://cdn/s1.jpg",
                                     "meta": {"alt": "x", "slide_urls": ["https://cdn/s1.jpg", "https://cdn/s2.jpg"],
                                              "slides": []}}],
        semasa_publish_log=[])


FILM = [{"id": "m1", "status": "done", "type": "video", "generated_media_url": "https://cdn/f.mp4",
         "meta": {"width": 1080, "height": 1920}}]
CARD = [{"id": "m1", "status": "done", "generated_media_url": "https://cdn/c.png", "meta": {"alt": "x"}}]


def test_with_zernio_on_every_platform_goes_to_zernio_and_buffer_gets_nothing():
    store, buf, z = _store(_post(slides=[])), FakeBuffer(), FakeZernio()
    c = publisher.run(store, NOW, clients={"buffer": buf, "zernio": z})
    assert c["scheduled"] == 3 and buf.created == []
    assert {x["service"]: x["channel"] for x in z.created} == {"instagram": "a" * 24, "facebook": "c" * 24, "threads": "b" * 24}
    p = store.tables["semasa_posts"][0]
    assert p["status"] == "scheduled" and {r["route"] for r in p["published"].values()} == {"zernio"}
    assert p["published"]["instagram"]["account"] == "a" * 24
    publisher.run(store, NOW, clients={"buffer": buf, "zernio": z})
    assert len(z.created) == 3                                       # a later run sends nothing twice


def test_with_zernio_off_buffer_sends_as_before():
    store, buf, z = _store(_post(slides=[]), zcfg={**ZCFG, "enabled": False}), FakeBuffer(), FakeZernio()
    c = publisher.run(store, NOW, clients={"buffer": buf, "zernio": z})
    assert c["scheduled"] == 3 and len(buf.created) == 3 and z.created == []


def test_one_platform_can_move_alone_and_a_channel_buffer_already_holds_is_not_sent_again():
    only_threads = {"enabled": True, "accounts": {"threads": ZCFG["accounts"]["threads"]}}
    held = {"instagram": {"id": "1" * 24, "status": "scheduled", "route": "buffer", "dueAt": "2026-09-25T00:00:00+00:00"}}
    store, buf, z = _store(_post(slides=[], published=held), zcfg=only_threads), FakeBuffer(), FakeZernio()
    publisher.run(store, NOW, clients={"buffer": buf, "zernio": z})
    assert [x["service"] for x in z.created] == ["threads"] and [x["service"] for x in buf.created] == ["facebook"]


def test_a_film_also_goes_to_tiktok_and_a_carousel_never_does():
    store, z = _store(_post(), media=FILM), FakeZernio()
    publisher.run(store, NOW, clients={"zernio": z})
    assert sorted(x["service"] for x in z.created) == ["facebook", "instagram", "threads", "tiktok"]
    assert all(x.get("video") == "https://cdn/f.mp4" for x in z.created)
    assert next(x for x in z.created if x["service"] == "tiktok")["text"] == CAP        # Instagram's caption
    store, z = _store(_post(slides=[])), FakeZernio()
    publisher.run(store, NOW, clients={"zernio": z})
    assert "tiktok" not in {x["service"] for x in z.created}


def _linkedin(**kw):
    return _post(stream="linkedin", lang="en", slot="06:00", citation="EC 1223/2009",
                 text={"en": {"linkedin": "A regulation changed. Here is what it means for a formulator."}}, **kw)


def test_linkedin_is_scheduled_ahead_through_zernio_and_takes_a_card_a_carousel_or_a_film_but_not_words_alone():
    store, z = _store(_linkedin(slides=[])), FakeZernio()              # two slides: a carousel
    c = publisher.run(store, NOW, clients={"zernio": z})
    assert c["scheduled"] == 1 and z.created[0]["channel"] == "d" * 24 and z.created[0]["due_at"]   # no waiting for the slot
    store, z = _store(_linkedin(), media=CARD), FakeZernio()          # a single card goes (Wan, 11 Nov: remove the blocker)
    c = publisher.run(store, NOW, clients={"zernio": z})
    assert c["scheduled"] == 1 and len(z.created[0]["pictures"]) == 1
    store, z = _store(_linkedin(media_ids=[])), FakeZernio()                   # no picture at all
    c = publisher.run(store, NOW, clients={"zernio": z})
    assert z.created == [] and c["error"] == 1                       # words only is still refused (Wan, 10 Nov)
    assert "linkedin takes a carousel or a single card or a Motion film; this post is words only" in \
        store.tables["semasa_posts"][0]["errors"]["linkedin"]["message"]


def test_the_tally_reads_each_record_back_from_the_service_that_holds_it():
    rec = {"id": "9" * 24, "status": "scheduled", "route": "zernio", "account": "b" * 24, "dueAt": "2026-09-23T00:00:00+00:00"}
    store = _store(_post(status="scheduled", channels=["threads"], published={"threads": rec}))
    z = FakeZernio(existing=[{"id": "9" * 24, "status": "sent", "channelId": "b" * 24, "externalLink": "https://t/1"}])
    counts = {}
    publisher.tally(store, None, NOW, counts, publisher.load_settings(store), zernio=z)
    p = store.tables["semasa_posts"][0]
    assert p["published"]["threads"]["status"] == "sent" and p["published"]["threads"]["url"] == "https://t/1"
    assert p["status"] == "posted" and counts["confirmed"] == 1


# --- the sender ----------------------------------------------------------------------------------------------------------------

def test_a_caption_becomes_the_levels_of_one_chain_and_joins_back_to_itself():
    cap = "Hook line.\n\nSecond paragraph.\n\nThird paragraph.\n\n#tag"
    levels = senders.thread_levels(cap)
    assert levels[0] == "Hook line." and len(levels) == 2
    assert senders.text_key("\n\n".join(levels)) == senders.text_key(cap)
    assert senders.thread_levels("One paragraph only.") == ["One paragraph only."]
    long = "\n\n".join(f"Paragraph {i} " + "x" * 300 for i in range(9))
    assert len(senders.thread_levels(long)) == senders.THREAD_LEVELS


class Resp:
    def __init__(self, body, status=201):
        self._body, self.status_code = body, status

    def json(self):
        return self._body


class Http:
    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def request(self, method, url, **kw):
        self.calls.append((method, url, kw.get("json") or kw.get("params")))
        return self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]


def _made(top="scheduled", **plat):
    return {"post": {"_id": "p" * 24, "status": top, "content": "c", "scheduledFor": "2026-09-25T00:00:00.000Z",
                     "platforms": [{"platform": "threads", "accountId": {"_id": "b" * 24}, **{"status": "pending", **plat}}]}}


def test_threads_is_sent_as_a_chain_with_the_pictures_on_the_first_level():
    http = Http(Resp(_made()))
    z = senders.Zernio("k", session=http)
    pics = ["https://cdn/1.jpg", "https://cdn/2.jpg"]
    out = z.create("b" * 24, "threads", "Hook.\n\nMore.\n\n#t", pics, "", "2026-09-25T00:00:00+00:00")
    body = http.calls[0][2]
    items = body["platforms"][0]["platformSpecificData"]["threadItems"]
    assert body["content"] == "Hook." and [i["content"] for i in items] == ["Hook.", "More.\n\n#t"]
    assert len(items[0]["mediaItems"]) == 2 and items[1]["mediaItems"] == []
    assert body["scheduledFor"] == "2026-09-25T00:00:00+00:00" and "publishNow" not in body
    assert out["id"] == "p" * 24 and out["status"] == "scheduled" and out["channelId"] == "b" * 24


def test_tiktok_takes_a_film_with_its_settings_and_never_a_picture_and_a_film_is_a_reel():
    http = Http(Resp(_made()))
    z = senders.Zernio("k", session=http)
    z.create_video("e" * 24, "tiktok", "cap", {"url": "https://cdn/f.mp4", "vertical": True}, None)
    body = http.calls[0][2]
    assert body["publishNow"] is True and body["tiktokSettings"]["privacy_level"] == "PUBLIC_TO_EVERYONE"
    assert body["mediaItems"] == [{"type": "video", "url": "https://cdn/f.mp4"}]
    with pytest.raises(senders.SendError, match="Motion film only"):
        z.create("e" * 24, "tiktok", "cap", ["https://cdn/1.jpg"], "", None)
    z.create_video("a" * 24, "instagram", "cap", {"url": "u", "vertical": True}, None)
    assert http.calls[-1][2]["platforms"][0]["platformSpecificData"] == {"contentType": "reels"}


def test_a_chain_already_in_zernio_reads_back_as_the_whole_caption_and_statuses_are_buffers():
    chain = {"threadItems": [{"content": "Hook."}, {"content": "More."}]}
    got = senders.Zernio.shape(_made(platformSpecificData=chain)["post"], "b" * 24)
    assert got["text"] == "Hook.\n\nMore."
    sent = senders.Zernio.shape(_made("published", status="published", platformPostUrl="https://t/1")["post"])
    assert sent["status"] == "sent" and sent["externalLink"] == "https://t/1"
    bad = senders.Zernio.shape(_made("failed", status="failed", errorMessage="token expired")["post"])
    assert bad["status"] == "error" and bad["error"]["message"] == "token expired"


def test_a_refusal_an_outage_and_a_missing_login_are_told_apart():
    with pytest.raises(senders.SendError) as e:
        senders.Zernio("k", session=Http(Resp({"error": "Invalid media"}, 400))).create("a" * 24, "instagram", "c", [], "", None)
    assert e.value.kind == "refused" and "Invalid media" in e.value.message
    with pytest.raises(senders.SendError) as e:
        senders.Zernio("k", session=Http(Resp({}, 503))).create("a" * 24, "instagram", "c", [], "", None)
    assert e.value.kind == "transient"
    with pytest.raises(senders.SendError, match="no Zernio key"):
        senders.ZernioHub({}).create("a" * 24, "instagram", "c", [], "", None)


def test_the_hub_is_built_only_from_logins_whose_secret_is_set_and_only_when_switched_on(monkeypatch):
    monkeypatch.setenv("ZERNIO_API_KEY_1", "k1")
    monkeypatch.delenv("ZERNIO_API_KEY_2", raising=False)
    monkeypatch.delenv("ZERNIO_API_KEY_3", raising=False)
    hub = publisher.zernio_hub(ZCFG)
    assert set(hub.by_account) == {"a" * 24, "b" * 24}
    assert hub.by_account["a" * 24] is hub.by_account["b" * 24]            # one login, one client
    assert publisher.zernio_hub({**ZCFG, "enabled": False}) is None
    assert publisher.zernio_accounts({"enabled": True, "accounts": {"threads": {"id": "x", "on": False}}}) == {}
