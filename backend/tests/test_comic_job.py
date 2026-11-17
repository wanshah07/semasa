"""The dialogue comic as a Design job (Wan, 17 Nov 2026): the picture maker draws the words, every bubble is read back and
compared with the script, and a page that cannot be proven exact is drawn without words and printed by Semasa."""

import copy
import io
import json

import pytest
from fakestore import FakeStore
from PIL import Image

from semasa import chatgpt_login, comic, comic_sample, media_generator
from semasa.config import MediaSettings

SCRIPT = comic_sample.SCRIPT
PANELS = [[line["text"] for line in panel["lines"]] for panel in SCRIPT["panels"]]


def art() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (1024, 1024), (200, 220, 240)).save(buf, "PNG")
    return buf.getvalue()


def said(panels=None, other="") -> str:
    return "Here it is: " + json.dumps({"panels": PANELS if panels is None else panels, "other_text": other})


class Maker:
    """A picture maker that remembers what it was asked to draw."""

    def __init__(self):
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> bytes:
        self.prompts.append(prompt)
        return art()


class Reader:
    def __init__(self, *answers):
        self.answers, self.n = list(answers), 0

    def __call__(self, system, prompt, data, mime):
        assert mime == "image/jpeg" and Image.open(io.BytesIO(data)).format == "JPEG"
        out = self.answers[min(self.n, len(self.answers) - 1)]
        self.n += 1
        if isinstance(out, Exception):
            raise out
        return out


# --- the read-back ---------------------------------------------------------------------------------------------------

def test_every_bubble_exact_means_the_picture_makers_words_are_used() -> None:
    maker, reader = Maker(), Reader(said())
    made = comic.make(maker, reader, SCRIPT)
    assert made["how"] == "ai" and made["tries"] == 1 and made["notes"] == []
    assert len(maker.prompts) == 1 and "EXACTLY" in maker.prompts[0]              # drawn once, with the words in it
    assert Image.open(io.BytesIO(made["jpeg"])).size == comic.POSTER


def test_a_misspelled_bubble_is_drawn_again_and_the_second_try_can_pass() -> None:
    wrong = copy.deepcopy(PANELS)
    wrong[3][1] = "MPPHM (Domestik) 2020, Klausa 40(3)."                          # a changed clause number is a wrong fact
    maker, reader = Maker(), Reader(said(wrong), said())
    made = comic.make(maker, reader, SCRIPT)
    assert made["how"] == "ai" and made["tries"] == 2 and len(maker.prompts) == 2
    assert "Klausa 40(3)" in made["notes"][0]
    assert made["notes"][0].startswith("try 1: panel 4")


def test_a_page_that_never_matches_is_drawn_without_words_and_printed_by_semasa() -> None:
    wrong = copy.deepcopy(PANELS)
    wrong[0][0] = wrong[0][0].replace("hijau", "hijaw")
    maker, reader = Maker(), Reader(said(wrong))
    made = comic.make(maker, reader, SCRIPT)
    assert made["how"] == "printed" and len(made["notes"]) == comic.TRIES
    assert len(maker.prompts) == comic.TRIES + 1 and "NO speech bubbles" in maker.prompts[-1]
    # the printed page carries the script's words: the lettering is Semasa's own
    assert [b["text"] for b in comic.bubbles(SCRIPT)] == [t for panel in PANELS for t in panel]


@pytest.mark.parametrize("reader", [None, Reader(RuntimeError("the login was refused")), Reader("I cannot read this picture")])
def test_with_no_proof_the_words_are_never_trusted(reader) -> None:
    maker = Maker()
    made = comic.make(maker, reader, SCRIPT)
    assert made["how"] == "printed" and made["notes"]
    assert "NO speech bubbles" in maker.prompts[-1]
    if reader is None:
        assert len(maker.prompts) == 1                  # nothing wasted on drawing words nobody can check


def test_the_comparison_ignores_spacing_curly_quotes_and_bubble_order_but_nothing_else() -> None:
    script = copy.deepcopy(SCRIPT)
    script["panels"][1]["lines"] = [{"who": "A", "text": "Dia kata \"ok\"."}, {"who": "B", "text": "Baik  sangat."}]
    got = {"panels": [PANELS[0], ["Baik sangat.", "Dia kata “ok”."], PANELS[2], PANELS[3]], "other_text": ""}
    assert comic.compare(script, got) == []
    changed = {**got, "panels": [PANELS[0], ["baik sangat.", "Dia kata “ok”."], PANELS[2], PANELS[3]]}
    assert "panel 2" in comic.compare(script, changed)[0]                        # a changed capital is a change
    assert comic.compare(script, {**got, "other_text": "SALE"})[0].startswith("text outside a bubble")
    assert comic.compare(script, {"panels": PANELS[:3]})[0].startswith("3 panels")
    assert comic.compare(script, None) == ["the picture could not be read back"]


# --- the script is written under the post rules -----------------------------------------------------------------------

class Writer:
    configured = True
    last_model = "w-1"

    def __init__(self, out):
        self.out, self.seen = out, []

    def why_off(self) -> str:
        return "off"

    def chat_json(self, system, user, max_tokens=0, **k):
        self.seen.append((system, user))
        return self.out


def test_the_writer_gets_the_rules_and_its_script_is_checked_as_a_page() -> None:
    writer = Writer(SCRIPT)
    brief = "Logo halal bukan hijau, palsu ke? MPPHM (Domestik) 2020, Klausa 40(2)."
    out = comic.write(writer, brief, "regulab", "lebih ringkas")
    system, user = writer.seen[0]
    assert "No call to action" in system and "never Bahasa Indonesia" in system and "four-panel" in system
    assert "lebih ringkas" in user and "Klausa 40(2)" in user
    assert comic.check(out) and out["panels"][3]["lines"][1]["text"] == "MPPHM (Domestik) 2020, Klausa 40(2)."
    li = Writer(SCRIPT)
    comic.write(li, "x", "linkedin")
    assert "in English" in li.seen[0][0] and "No company identity" in li.seen[0][0]    # the stream picks the spoken language


@pytest.mark.parametrize("llm, message", [
    (None, "writer is off"), (Writer(None), "did not answer"),
    (Writer({"title": "T", "panels": []}), "exactly 4 panels"), (Writer({"title": "", "panels": []}), "no title")])
def test_a_script_that_cannot_be_used_is_refused_with_the_reason(llm, message) -> None:
    with pytest.raises(comic.ComicError, match=message):
        comic.write(llm, "idea", "regulab")


def test_the_comics_words_are_scanned_like_a_poster() -> None:
    words = comic.as_words(SCRIPT)
    assert len(words) == 1 and words[0]["title"] == SCRIPT["title"] and len(words[0]["points"]) == 6


# --- the job ----------------------------------------------------------------------------------------------------------

def _settings():
    return MediaSettings(provider="cloudflare", batch=5, max_attempts=3, poll_seconds=0, max_wait_image=1,
                         max_wait_video=1, replicate_token=None, replicate_image_model="a/b",
                         replicate_video_model="c/d", replicate_image_input_key="input_image",
                         replicate_video_input_key="start_image", openai_key=None,
                         openai_base_url="https://api.openai.com/v1", openai_image_model="gpt-image-1",
                         openai_video_model="sora-2", openai_image_size="1024x1024", openai_video_seconds="8",
                         openai_video_size="1280x720")


def _store(meta, attempts=1):
    job = {"id": "c1", "mode": "slides", "type": "image", "status": "processing", "attempts": attempts, "post_id": "p1",
           "created_at": "2099-01-01T00:00:00+00:00", "meta": {"stream": "regulab", "design": "comic", **meta}}
    return FakeStore(semasa_settings=[], semasa_posts=[{"id": "p1", "status": "draft", "media_ids": []}],
                     media_generations=[job])


@pytest.fixture(autouse=True)
def _uploads(monkeypatch):
    got = {}
    monkeypatch.setattr(media_generator.db, "upload_generated",
                        lambda store, path, data, ct: got.setdefault(path, data) and f"https://cdn/{path}")
    return got


def _run(store, llm=None):
    return media_generator.process_row(store, store.tables["media_generations"][0], _settings(), {}, llm)


def _makers(monkeypatch, makers, read):
    monkeypatch.setattr(media_generator, "comic_makers", lambda store, pick="auto": (makers, read))


def test_a_comic_from_an_idea_is_written_saved_proven_and_attached(monkeypatch, _uploads) -> None:
    maker = Maker()
    _makers(monkeypatch, [("chatgpt", maker)], Reader(said()))
    store = _store({"brief": "Logo halal bukan hijau, palsu ke?"})
    assert _run(store, Writer(SCRIPT)) is True, store.tables["media_generations"][0].get("error")
    row = store.tables["media_generations"][0]
    meta = row["meta"]
    assert row["status"] == "done" and meta["comic"] == SCRIPT and meta["written_by"] == "w-1"      # saved before drawing
    assert meta["comic_how"] == "ai" and meta["comic_maker"] == "chatgpt" and meta["count"] == 1
    assert meta["citation"] == SCRIPT["source"] and meta["slides"][0]["title"] == SCRIPT["title"]
    assert Image.open(io.BytesIO(next(iter(_uploads.values())))).size == comic.POSTER
    assert store.tables["semasa_posts"][0]["media_ids"] == ["c1"]


def test_a_retry_draws_the_saved_words_and_does_not_write_new_ones(monkeypatch) -> None:
    _makers(monkeypatch, [("chatgpt", Maker())], Reader(said()))
    writer = Writer(None)                                                      # would fail if it were asked again
    store = _store({"brief": "idea", "comic": SCRIPT})
    assert _run(store, writer) is True and writer.seen == []


def test_the_next_maker_is_asked_when_the_first_one_fails(monkeypatch) -> None:
    def refused(prompt):
        raise chatgpt_login.ChatGPTError("the plan's allowance is used up", limit=True)
    gemini = Maker()
    _makers(monkeypatch, [("chatgpt", refused), ("gemini", gemini)], Reader(said()))
    store = _store({"comic": SCRIPT})
    assert _run(store) is True
    meta = store.tables["media_generations"][0]["meta"]
    assert meta["comic_maker"] == "gemini" and meta["comic_failed"][0]["maker"] == "chatgpt" and gemini.prompts


def test_no_picture_maker_or_a_bad_script_is_a_final_error_that_says_why(monkeypatch) -> None:
    _makers(monkeypatch, [], None)
    store = _store({"comic": SCRIPT})
    assert _run(store) is False
    assert store.tables["media_generations"][0]["status"] in ("pending", "error")
    assert "no picture maker" in store.tables["media_generations"][0]["error"]
    bad = copy.deepcopy(SCRIPT)
    bad["panels"].pop()
    store = _store({"comic": bad})
    assert _run(store) is False
    row = store.tables["media_generations"][0]
    assert row["status"] == "error" and "exactly 4 panels" in row["error"]


def test_a_hard_flag_is_shown_and_the_drawing_still_goes_ahead(monkeypatch) -> None:
    script = copy.deepcopy(SCRIPT)
    script["panels"][3]["lines"][0]["text"] = "Hubungi kami di www.contoh.com.my"
    read = copy.deepcopy(PANELS)
    read[3][0] = script["panels"][3]["lines"][0]["text"]
    _makers(monkeypatch, [("chatgpt", Maker())], Reader(said(read)))
    store = _store({"comic": script})
    assert _run(store) is True
    meta = store.tables["media_generations"][0]["meta"]
    assert any(f["hard"] for f in meta["flags"]) and meta["comic_how"] == "ai"
