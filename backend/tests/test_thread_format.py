"""Wan, 10 Nov 2026: Threads is a thread with a continuation (hook post with the picture, then list posts), not one post."""
from semasa import antislop, compliance, ideas, proofread, senders

THREAD = ("Run bisnes secara solo?\n\nIni 5 tools yang diguna.\n\nPenjelasan penuh di bawah.\n\n---\n\n"
          "Research:\n1. A\n2. B\n\n---\n\n"
          "Marketing:\n1. C\n2. D\n\n---\n\nSumber:\n1. NPRA")


def test_the_writers_are_told_to_write_a_thread_with_the_separator():
    assert "THREADS FORMAT" in ideas.REGULAB_SYSTEM and "line holding only ---" in ideas.REGULAB_SYSTEM
    assert "3 to 5 posts" in ideas.REGULAB_SYSTEM and "Post 1 carries the picture" in ideas.REGULAB_SYSTEM


def test_the_separator_survives_the_slop_cleaner_and_the_proofreader():
    assert antislop.clean(THREAD) == THREAD                       # a dash is slop, a line holding only --- is not
    assert antislop.clean("a — b\n\n---\n\nc – d") == "a, b\n\n---\n\nc, d"
    assert not proofread.safe(THREAD, THREAD.replace("\n\n---\n\n", "\n\n", 1))       # a proofreader may not merge two posts
    assert proofread.safe(THREAD, THREAD.replace("Marketing:", "Pemasaran:"))


def test_zernio_gets_each_post_as_one_level_and_the_first_carries_the_picture():
    levels = senders.thread_levels(THREAD)
    assert len(levels) == 4 and levels[0].startswith("Run bisnes secara solo?") and "Penjelasan penuh di bawah." in levels[0]
    assert levels[1].startswith("Research:") and levels[3].startswith("Sumber:")
    body = {}

    class Http:
        def request(self, method, url, json=None, **kw):
            body.update(json)
            from types import SimpleNamespace
            return SimpleNamespace(status_code=201, json=lambda: {"post": {"_id": "p1", "status": "scheduled",
                                   "platforms": [{"platform": "threads", "accountId": "a1", "status": "scheduled"}]}})
    z = senders.Zernio("k", session=Http())
    z.create("a1", "threads", THREAD, ["https://x/1.jpg", "https://x/2.jpg"], "alt", "2026-11-12T00:00:00Z")
    items = body["platforms"][0]["platformSpecificData"]["threadItems"]
    assert [bool(i["mediaItems"]) for i in items] == [True, False, False, False]
    assert items[0]["content"].startswith("Run bisnes") and items[2]["content"].startswith("Marketing:")
    assert "---" not in "".join(i["content"] for i in items)
    assert senders.thread_levels("one paragraph") == ["one paragraph"]
    legacy = senders.thread_levels("a\n\nb\n\nc")
    assert legacy[0] == "a"                                          # a caption with no separator keeps the old behaviour


def test_each_post_of_a_thread_has_the_limit_and_the_thread_has_at_most_five():
    post = {"stream": "regulab", "lang": "bm", "media": [{"id": "m1", "alt": "Botol produk di rak"}],
            "text": {"bm": {"instagram": "x" * 10, "facebook": "x" * 10, "threads": THREAD}}}
    assert compliance.hard_count(compliance.scan(post)) == 0
    post["text"]["bm"]["threads"] = "Hook\n\n---\n\n" + "a" * 501
    assert any("post 2 of the thread is 501" in f["msg"] for f in compliance.scan(post))
    post["text"]["bm"]["threads"] = "\n\n---\n\n".join(str(i) for i in range(6))
    assert any("6 posts in the thread" in f["msg"] for f in compliance.scan(post))
    assert compliance.thread_parts("a\n---\nb\n  ---  \nc") == ["a", "b", "c"]
