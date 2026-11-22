"""Every caption inside its platform's limit (Wan, 22 Nov 2026: "Make sure caption untuk semua platform di bawah maksimum
aksara dibenarkan")."""

from datetime import UTC, datetime

from fakestore import FakeStore

from semasa import caption_fit, compliance, motion_captions, publisher, senders

HOOK = "Notifikasi kosmetik bukan kelulusan produk."
FOLLOW = "Follow untuk tip regulatori yang senang faham."
TAGS = "#halal #npra #kosmetik"


def _long(n: int, size: int = 300) -> str:
    body = "\n\n".join(f"{i}. Fakta {i}. " + ("Ayat penuh di sini. " * (size // 20)).strip() for i in range(1, n + 1))
    return f"{HOOK}\n\n{body}\n\n{FOLLOW}\n\n{TAGS}"


def test_a_caption_inside_its_limit_is_returned_exactly():
    for p in ("instagram", "facebook", "threads"):
        assert caption_fit.fit(HOOK, p, "regulab") == HOOK
    assert caption_fit.fit("A short post.", "linkedin", "linkedin") == "A short post."


def test_every_platform_ends_inside_its_limit_keeping_hook_follow_and_tags():
    cap = _long(20)
    for stream, plats in (("regulab", ("instagram", "facebook", "threads", "tiktok")), ("linkedin", ("linkedin",))):
        for p in plats:
            lim = caption_fit.limit_of(stream, p)
            out = caption_fit.fit(cap * 30 if p == "facebook" else cap, p, stream)
            parts = compliance.thread_parts(out) if lim.get("parts") else [out]
            assert len(parts) <= (lim.get("parts") or 1), p
            assert all(caption_fit.units(x) <= lim["max"] for x in parts), p
            assert out.startswith(HOOK) and out.rstrip().endswith(TAGS.split()[-1]), p
            assert not compliance.hard_count([f for f in compliance.scan(
                {"stream": stream, "lang": "bm" if stream == "regulab" else "en",
                 "text": {"bm" if stream == "regulab" else "en": {p: out}}, "channels": [p]}) if "limit" in f["msg"]]), p


def test_whole_paragraphs_come_out_never_half_a_sentence():
    cap = _long(12)
    out = caption_fit.fit(cap, "instagram", "regulab")
    assert caption_fit.units(out) <= 2200
    assert all(p in cap for p in out.split("\n\n")), "no paragraph is cut in the middle"
    assert FOLLOW in out


def test_one_huge_paragraph_is_cut_at_its_last_full_sentence():
    para = " ".join(f"Ayat nombor {i} lengkap." for i in range(400))
    out = caption_fit.fit_caption(para, 2200)
    assert caption_fit.units(out) <= 2200 and out.endswith("lengkap.")


def test_emoji_are_counted_as_the_platforms_count_them():
    cap = "🔥" * 1500                                        # 1,500 characters, 3,000 UTF-16 units
    out = caption_fit.fit(cap, "instagram", "regulab")
    assert caption_fit.units(out) <= 2200


def test_a_thread_written_without_separators_becomes_a_chain_the_sender_and_scan_agree_on():
    cap = f"{HOOK}\n\n" + "\n\n".join("Perenggan " + "panjang " * 30 for _ in range(4)) + f"\n\n{TAGS}"
    out = caption_fit.fit(cap, "threads", "regulab")
    parts = compliance.thread_parts(out)
    assert parts == senders.thread_levels(out), "the page, the scan and the sender read one chain"
    assert 1 < len(parts) <= 5 and all(len(x) <= 500 for x in parts)
    assert parts[0] == HOOK, "the hook stands alone above the pictures"
    assert not senders.has_loose_tags(out), "the hashtags never make a post of their own"


def test_a_thread_with_too_many_posts_is_packed_and_trimmed_to_five():
    cap = "\n\n---\n\n".join(f"Post {i}. " + "kata " * 60 for i in range(9))
    out = caption_fit.fit(cap, "threads", "regulab")
    parts = compliance.thread_parts(out)
    assert len(parts) <= 5 and all(len(x) <= 500 for x in parts) and parts[0].startswith("Post 0.")


def test_a_thread_that_already_fits_is_untouched():
    cap = f"{HOOK}\n\n---\n\nPost dua."
    assert caption_fit.fit(cap, "threads", "regulab") == cap


def test_motion_captions_end_inside_the_limit_too():
    out = motion_captions.fit(_long(20), "regulab", "threads")
    assert all(len(x) <= 500 for x in compliance.thread_parts(out))


NOW = datetime(2026, 9, 24, 2, 0, tzinfo=UTC)


def _store(post):
    return FakeStore(
        semasa_settings=[{"key": "publishing", "value": {"enabled": False}}, {"key": "brand", "value": {}}],
        semasa_posts=[post],
        media_generations=[{"id": "m1", "status": "done", "generated_media_url": "https://cdn/m1.png", "meta": {}}],
        semasa_publish_log=[], semasa_log=[])


def _post(text, **kw):
    p = {"id": "p1", "stream": "regulab", "lang": "bm", "status": "approved", "date": "2026-09-25", "slot": "08:00",
         "text": {"bm": text}, "citation": "NPRA", "media_ids": ["m1"], "published": {}, "errors": {},
         "updated_at": "2026-09-24T01:00:00+00:00"}
    p.update(kw)
    return p


def test_the_publisher_fits_an_over_long_caption_saves_it_and_sends_it_instead_of_blocking():
    cap = _long(20)
    store = _store(_post({"instagram": cap, "facebook": HOOK, "threads": cap}))
    c = publisher.run(store, NOW)
    assert c["blocked"] == 0 and c["dry_run"] == 3
    row = store.tables["semasa_posts"][0]
    assert row["status"] == "approved", "the approval stands"
    assert caption_fit.units(row["text"]["bm"]["instagram"]) <= 2200
    assert all(len(x) <= 500 for x in compliance.thread_parts(row["text"]["bm"]["threads"]))
    sent = {r["channel"]: r["detail"]["would_send"]["text"] for r in store.tables["semasa_publish_log"]}
    assert sent["instagram"] == row["text"]["bm"]["instagram"], "what is sent is what is saved"


def test_a_channel_a_platform_already_holds_keeps_its_caption():
    cap = _long(20)
    post = _post({"instagram": cap, "facebook": HOOK, "threads": HOOK},
                 published={"instagram": {"id": "b1", "status": "scheduled"}})
    out = publisher.fit_before_send(FakeStore(semasa_posts=[dict(post)], semasa_log=[]), post)
    assert out["text"]["bm"]["instagram"] == cap


def test_an_edit_made_meanwhile_wins_over_the_fit():
    cap = _long(20)
    post = _post({"instagram": cap, "facebook": HOOK, "threads": HOOK})
    store = FakeStore(semasa_posts=[{**post, "updated_at": "2026-09-24T01:30:00+00:00"}], semasa_log=[])
    out = publisher.fit_before_send(store, post)
    assert out["text"]["bm"]["instagram"] == cap and store.tables["semasa_posts"][0]["text"]["bm"]["instagram"] == cap
