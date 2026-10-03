import json

from fakestore import FakeStore

from semasa import nota


def _post(**kw):
    p = {"id": "p1", "stream": "regulab", "status": "posted", "date": "2026-10-01", "domain": "halal_my", "hook": "Hook",
         "citation": "MPPHM 2020 Klausa 4", "text": {"bm": {"instagram": "SECRET CAPTION"}},
         "published": {"instagram": {"id": "a" * 24, "status": "sent", "url": "https://www.instagram.com/p/X/"},
                       "facebook": {"id": "b" * 24, "status": "scheduled", "url": "https://fb/should-not-count"},
                       "threads": {"status": "sent", "externalLink": "https://www.threads.com/@x/post/Y"}}}
    p.update(kw)
    return p


def test_only_sent_channels_with_a_link_are_dumped_under_the_name_studio_notes_read(tmp_path):
    store = FakeStore(semasa_posts=[_post()])
    counts = nota.dump(store, tmp_path)
    d = json.loads((tmp_path / "p1.json").read_text())
    assert counts == {"posts": 1, "with_a_public_link": 1}
    assert d["published"] == {"instagram": {"status": "sent", "externalLink": "https://www.instagram.com/p/X/"},
                              "threads": {"status": "sent", "externalLink": "https://www.threads.com/@x/post/Y"}}
    assert d["stream"] == "regulab" and d["hook"] == "Hook" and d["date"] == "2026-10-01"
    assert d["citation"] == "MPPHM 2020 Klausa 4"


def test_no_caption_text_ever_reaches_the_dump(tmp_path):
    nota.dump(FakeStore(semasa_posts=[_post()]), tmp_path)
    assert "SECRET CAPTION" not in (tmp_path / "p1.json").read_text()


def test_linkedin_drafts_and_rejected_posts_are_not_dumped_and_stale_files_are_cleared(tmp_path):
    (tmp_path / "old.json").write_text("{}")
    store = FakeStore(semasa_posts=[_post(), _post(id="p2", stream="linkedin"), _post(id="p3", status="rejected"),
                                    _post(id="p4", status="draft"), _post(id="p5", status="approved")])
    counts = nota.dump(store, tmp_path)
    assert sorted(f.name for f in tmp_path.glob("*.json")) == ["p1.json"] and counts["posts"] == 1
