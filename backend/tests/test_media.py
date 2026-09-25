from semasa import media_generator
from semasa.config import MediaSettings
from semasa.providers import Generated, ProviderError


def _settings(**over):
    base = dict(provider="replicate", batch=5, max_attempts=3, poll_seconds=0, max_wait_image=1, max_wait_video=1,
                replicate_token="t", replicate_image_model="a/b", replicate_video_model="c/d",
                replicate_image_input_key="input_image", replicate_video_input_key="start_image",
                openai_key=None, openai_base_url="https://api.openai.com/v1", openai_image_model="gpt-image-1",
                openai_video_model="sora-2", openai_image_size="1024x1024", openai_video_seconds="8",
                openai_video_size="1280x720")
    base.update(over)
    return MediaSettings(**base)


class FakeProvider:
    name = "fake"

    def __init__(self, result=None, exc=None):
        self.result, self.exc, self.calls = result, exc, []

    def generate(self, kind, reference_url, prompt, options):
        self.calls.append((kind, reference_url, prompt, options))
        if self.exc:
            raise self.exc
        return self.result


def _patch_db(monkeypatch):
    writes = {}
    uploads = {}
    monkeypatch.setattr(media_generator.db, "upload_generated",
                        lambda store, path, data, ct: uploads.setdefault(path, (data, ct)) and f"https://cdn/{path}")
    monkeypatch.setattr(media_generator.db, "finish_media", lambda store, rid, **f: writes.setdefault(rid, f))
    return writes, uploads


def test_done_row_carries_url_sha_and_model(monkeypatch):
    writes, uploads = _patch_db(monkeypatch)
    prov = FakeProvider(Generated(b"\x89PNG...", "image/png", "a/b", {"prediction_id": "p1"}))
    row = {"id": "r1", "type": "image", "reference_url": "https://ref/x.png", "prompt": "p", "attempts": 1,
           "meta": {"options": {"input": {"aspect_ratio": "1:1"}}}}
    assert media_generator.process_row(None, row, _settings(), {"replicate": prov}) is True
    assert prov.calls[0][3] == {"input": {"aspect_ratio": "1:1"}}
    w = writes["r1"]
    assert w["status"] == "done" and w["generated_media_url"].endswith("/r1.png") and w["model"] == "a/b"
    assert w["meta"]["sha256"] and w["meta"]["bytes"] == 7 and w["meta"]["prediction_id"] == "p1"
    assert list(uploads.values())[0][1] == "image/png"


def test_transient_failure_goes_back_to_pending_until_max(monkeypatch):
    writes, _ = _patch_db(monkeypatch)
    prov = FakeProvider(exc=TimeoutError("slow"))
    row = {"id": "r2", "type": "video", "reference_url": "https://ref/x.png", "prompt": "p", "attempts": 1,
           "provider": "replicate"}
    media_generator.process_row(None, row, _settings(max_attempts=3), {"replicate": prov})
    assert writes["r2"]["status"] == "pending" and "TimeoutError" in writes["r2"]["error"]
    writes.clear()
    row["attempts"] = 3
    media_generator.process_row(None, row, _settings(max_attempts=3), {"replicate": prov})
    assert writes["r2"]["status"] == "error"


def test_provider_refusal_is_final(monkeypatch):
    writes, _ = _patch_db(monkeypatch)
    prov = FakeProvider(exc=ProviderError("rejected"))
    row = {"id": "r3", "type": "image", "reference_url": "https://ref/x.png", "prompt": "p", "attempts": 1}
    media_generator.process_row(None, row, _settings(), {"replicate": prov})
    assert writes["r3"]["status"] == "error"


def test_unknown_provider_is_recorded_not_raised(monkeypatch):
    writes, _ = _patch_db(monkeypatch)
    row = {"id": "r4", "type": "image", "reference_url": "https://ref/x.png", "prompt": "p", "attempts": 1, "provider": "nope"}
    assert media_generator.process_row(None, row, _settings(), {}) is False
    assert writes["r4"]["status"] == "error" and "unknown provider" in writes["r4"]["error"]


def test_non_image_reference_is_refused_before_any_provider_call(monkeypatch):
    writes, _ = _patch_db(monkeypatch)
    prov = FakeProvider(Generated(b"x", "image/png", "a/b"))
    for rid, row in {
        "pdf": {"reference_url": "https://s/ref/x.pdf", "meta": {"mime": "application/pdf"}},
        "txt": {"reference_url": "https://s/ref/notes.txt"},
    }.items():
        row.update(id=rid, type="image", prompt="p", attempts=1)
        assert media_generator.process_row(None, row, _settings(), {"replicate": prov}) is False
        assert writes[rid]["status"] == "error" and "must be an image" in writes[rid]["error"]
    assert prov.calls == []                                # no credits spent on a doomed job


def test_image_reference_detection():
    assert media_generator.reference_is_image({"meta": {"mime": "image/webp"}, "reference_url": "u"})
    assert media_generator.reference_is_image({"reference_url": "https://s/r/a.JPG?token=1"})
    assert not media_generator.reference_is_image({"reference_url": "https://s/r/a.pdf"})


class TextProvider(FakeProvider):
    def __init__(self, result):
        super().__init__(result)
        self.text_calls = []

    def generate_from_text(self, prompt, options):
        self.text_calls.append(prompt)
        return self.result


def _db_all(monkeypatch):
    writes, uploads = {}, {}
    monkeypatch.setattr(media_generator.db, "upload_generated",
                        lambda store, path, data, ct: uploads.setdefault(path, (data, ct)) and f"https://cdn/{path}")
    monkeypatch.setattr(media_generator.db, "finish_media", lambda store, rid, **f: writes.setdefault(rid, f))
    monkeypatch.setattr(media_generator.db, "attach_media_to_draft",
                        lambda store, pid, mid: writes.setdefault("attach", (pid, mid)))
    return writes, uploads


def test_prompt_only_image_uses_words_alone(monkeypatch):
    writes, _ = _db_all(monkeypatch)
    prov = TextProvider(Generated(b"img", "image/png", "flux"))
    row = {"id": "t1", "type": "image", "mode": "prompt", "prompt": "kucing di makmal", "reference_url": None,
           "attempts": 1, "post_id": "p9"}
    assert media_generator.process_row(None, row, _settings(), {"replicate": prov}) is True
    assert prov.text_calls == ["kucing di makmal"] and prov.calls == []
    assert writes["t1"]["status"] == "done" and writes["attach"] == ("p9", "t1")


def test_prompt_only_video_makes_a_still_then_animates_it(monkeypatch):
    writes, uploads = _db_all(monkeypatch)
    prov = TextProvider(Generated(b"x", "image/png", "flux"))
    prov.generate = lambda kind, ref, prompt, opt: prov.calls.append((kind, ref)) or Generated(b"vid", "video/mp4", "kling")
    row = {"id": "t2", "type": "video", "mode": "prompt", "prompt": "kamera bergerak", "attempts": 1}
    assert media_generator.process_row(None, row, _settings(), {"replicate": prov}) is True
    assert prov.calls == [("video", "https://cdn/" + next(p for p in uploads if p.endswith("-still.png")))]
    assert writes["t2"]["meta"]["still_url"].endswith("-still.png") and writes["t2"]["generated_media_url"].endswith(".mp4")


def test_flow_a_news_picture_is_read_never_sent_to_the_edit_model(monkeypatch):
    writes, _ = _db_all(monkeypatch)
    monkeypatch.setattr(media_generator, "read_reference", lambda llm, url: {"description": "A shelf of jars."})
    prov = TextProvider(Generated(b"img", "image/png", "flux"))
    row = {"id": "t3", "type": "image", "mode": "recreate", "reference_url": "https://news/p.jpg",
           "prompt": "bottles", "attempts": 1, "meta": {"flow": "A", "mime": "image/og"}}
    assert media_generator.process_row(None, row, _settings(), {"replicate": prov}) is True
    assert prov.calls == []                                  # no pixels of the publisher's photo went anywhere
    p = prov.text_calls[0]
    assert "A shelf of jars." in p and "bottles" in p and "No logos" in p
    assert writes["t3"]["reference_read"] == "A shelf of jars."


def test_flow_a_unreadable_picture_without_words_is_refused(monkeypatch):
    writes, _ = _db_all(monkeypatch)
    monkeypatch.setattr(media_generator, "read_reference", lambda llm, url: None)
    prov = TextProvider(Generated(b"img", "image/png", "flux"))
    row = {"id": "t4", "type": "image", "mode": "recreate", "reference_url": "https://news/p.jpg", "prompt": "",
           "attempts": 1, "meta": {"flow": "A", "mime": "image/og"}}
    assert media_generator.process_row(None, row, _settings(), {"replicate": prov}) is False
    assert "VISION_MODEL" in writes["t4"]["error"] and prov.text_calls == []


def test_flow_b_recreate_sends_the_reference_with_the_read(monkeypatch):
    writes, _ = _db_all(monkeypatch)
    monkeypatch.setattr(media_generator, "read_reference", lambda llm, url: {"description": "Serum bottle on marble."})
    prov = TextProvider(Generated(b"img", "image/png", "kontext"))
    row = {"id": "t5", "type": "image", "mode": "recreate", "reference_url": "https://ref/own.png",
           "prompt": "latar biru", "attempts": 1}
    assert media_generator.process_row(None, row, _settings(), {"replicate": prov}) is True
    kind, ref, prompt, _ = prov.calls[0]
    assert ref == "https://ref/own.png" and prompt.startswith("Recreate the reference picture. Changes wanted: latar biru")
    assert "Serum bottle on marble." in prompt and "No logos" not in prompt
    assert prompt.count("latar biru") == 1


def test_prompt_mode_without_words_is_refused(monkeypatch):
    writes, _ = _db_all(monkeypatch)
    row = {"id": "t6", "type": "image", "mode": "prompt", "prompt": "  ", "attempts": 1}
    assert media_generator.process_row(None, row, _settings(), {}) is False
    assert "needs a prompt" in writes["t6"]["error"]


def test_shrink_for_read_fits_the_budget():
    import io

    from PIL import Image
    buf = io.BytesIO()
    Image.effect_noise((2400, 1800), 90).convert("RGB").save(buf, "PNG")
    data, ct = media_generator.shrink_for_read(buf.getvalue(), "image/png", budget=200_000)
    assert ct == "image/jpeg" and len(data) <= 200_000
    small = b"\xff\xd8" + b"0" * 10
    assert media_generator.shrink_for_read(small, "image/jpeg") == (small, "image/jpeg")


def test_stale_processing_rows_go_back_to_pending():
    from fakestore import FakeStore

    from semasa import db
    store = FakeStore(media_generations=[
        {"id": "old", "status": "processing", "updated_at": "2026-09-23T00:00:00+00:00"},
        {"id": "new", "status": "processing", "updated_at": "2999-01-01T00:00:00+00:00"},
        {"id": "done", "status": "done", "updated_at": "2026-09-23T00:00:00+00:00"}])
    assert db.recover_stale_media(store, 60) == 1
    st = {r["id"]: r["status"] for r in store.tables["media_generations"]}
    assert st == {"old": "pending", "new": "processing", "done": "done"}


def test_attach_only_to_a_draft():
    from fakestore import FakeStore

    from semasa import db
    store = FakeStore(semasa_posts=[{"id": "d", "status": "draft", "media_ids": []},
                                    {"id": "a", "status": "approved", "media_ids": ["x"]}])
    db.attach_media_to_draft(store, "d", "m1")
    db.attach_media_to_draft(store, "d", "m1")
    db.attach_media_to_draft(store, "a", "m2")
    rows = {r["id"]: r["media_ids"] for r in store.tables["semasa_posts"]}
    assert rows == {"d": ["m1"], "a": ["x"]}


def test_a_failure_keeps_the_provider_the_job_was_given(monkeypatch):
    """Writing the runner's default onto a failed row pinned every later Retry to it (25 Sep 2026)."""
    writes, _ = _patch_db(monkeypatch)
    row = {"id": "r9", "type": "image", "mode": "prompt", "prompt": "p", "attempts": 1}      # no provider: the default
    media_generator.process_row(None, row, _settings(replicate_token=None), {})
    assert writes["r9"]["status"] == "error" and "REPLICATE_API_TOKEN" in writes["r9"]["error"]
    assert writes["r9"]["provider"] is None
    writes.clear()
    chosen = {**row, "id": "r10", "provider": "openai"}
    media_generator.process_row(None, chosen, _settings(), {})
    assert writes["r10"]["provider"] == "openai"
