"""The dialogue (comic) poster: what the picture maker is asked for in each mode, and Semasa's own lettering."""

import copy
import io

import pytest
from PIL import Image

from semasa import comic, comic_sample

SCRIPT = comic_sample.SCRIPT
WORDS = [" ".join(line["text"].split()) for panel in SCRIPT["panels"] for line in panel["lines"]]


def art(side: int = 1024) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (side, side), (200, 220, 240)).save(buf, "PNG")
    return buf.getvalue()


def test_the_sample_script_is_a_valid_page() -> None:
    assert comic.check(SCRIPT) is SCRIPT
    assert len(WORDS) == 6


def test_full_prompt_carries_every_bubble_word_for_word() -> None:
    prompt = comic.prompt_full(SCRIPT)
    for words in WORDS:
        assert f'"{words}"' in prompt
    assert "EXACTLY" in prompt and "MPPHM (Domestik) 2020, Klausa 40(2)." in prompt


def test_art_prompt_carries_no_dialogue_and_asks_for_an_empty_top() -> None:
    prompt = comic.prompt_art(SCRIPT)
    for words in WORDS:
        assert words not in prompt
    assert "NO speech bubbles" in prompt and "44 percent" in prompt
    # the title and the source are Semasa's to print, in both modes
    for p in (prompt, comic.prompt_full(SCRIPT)):
        assert SCRIPT["title"] not in p and "Sumber" not in p


def test_both_prompts_place_the_same_people_on_the_same_sides() -> None:
    for p in (comic.prompt_art(SCRIPT), comic.prompt_full(SCRIPT)):
        assert "Character A, always on the LEFT" in p and "Character B, always on the RIGHT" in p
        assert "2 by 2 grid" in p and p.count("Panel ") == 4


def test_every_bubble_sits_in_the_empty_top_of_its_own_panel() -> None:
    bs = comic.bubbles(SCRIPT)
    assert [b["text"] for b in bs] == WORDS
    assert len({b["size"] for b in bs}) == 1 and comic.FONT_MIN <= bs[0]["size"] <= comic.FONT_MAX
    half = comic.SIDE // 2
    for b in bs:
        px, py = ((b["panel"] - 1) % 2) * half, ((b["panel"] - 1) // 2) * half
        x0, y0, x1, y1 = b["box"]
        assert px < x0 < x1 < px + half and py < y0 < y1 <= py + round(half * comic.ZONE)
        assert " ".join(b["lines"]) == b["text"]                       # no word lost or changed by the wrapping
        tip = b["tail"][2]
        assert px < tip[0] < px + half and y1 < tip[1] < py + half     # the tail points down, inside the panel
        # A hangs from the left of the panel and B from the right
        assert (x0 - px < px + half - x1) == (b["who"] == "A")


def test_two_bubbles_in_one_panel_do_not_overlap() -> None:
    by_panel: dict[int, list] = {}
    for b in comic.bubbles(SCRIPT):
        by_panel.setdefault(b["panel"], []).append(b["box"])
    for boxes in by_panel.values():
        if len(boxes) == 2:
            assert boxes[0][3] < boxes[1][1]


def test_long_words_shrink_the_lettering_and_too_long_ones_are_refused() -> None:
    longer = copy.deepcopy(SCRIPT)
    longer["panels"][1]["lines"][0]["text"] = "Jangan-jangan logo palsu? Saya risau sebab warna dia lain daripada yang biasa."
    longer["panels"][1]["lines"][1]["text"] = "Tak semestinya. Warna bukan penentu sama ada logo itu sah atau tidak."
    assert comic.bubbles(longer)[0]["size"] < comic.bubbles(SCRIPT)[0]["size"]
    too_long = copy.deepcopy(SCRIPT)
    too_long["panels"][0]["lines"][0]["text"] = "kata " * 30
    with pytest.raises(comic.ComicError, match="characters"):
        comic.bubbles(too_long)
    crowded = copy.deepcopy(SCRIPT)
    crowded["panels"][1]["lines"] = [{"who": "A", "text": "pembungkusan " * 8}, {"who": "B", "text": "pembungkusan " * 8}]
    with pytest.raises(comic.ComicError, match="do not fit"):
        comic.bubbles(crowded)


@pytest.mark.parametrize("change, message", [
    (lambda s: s["panels"].pop(), "exactly 4 panels"),
    (lambda s: s["panels"][0]["lines"].clear(), "one or two speech bubbles"),
    (lambda s: s["panels"][0]["lines"][0].update(who="C"), "speaker is A or B"),
    (lambda s: s["panels"][1]["lines"][1].update(who="A"), "speaks once"),
    (lambda s: s["panels"][0]["lines"][0].update(text="  "), "no words"),
    (lambda s: s["cast"].pop("B"), "both people"),
])
def test_a_script_that_cannot_be_drawn_is_refused_with_the_reason(change, message) -> None:
    bad = copy.deepcopy(SCRIPT)
    change(bad)
    for fn in (comic.check, comic.prompt_full, comic.prompt_art, comic.bubbles):
        with pytest.raises(comic.ComicError, match=message):
            fn(bad)


def test_lettering_draws_on_the_art_and_the_frame_is_a_4_by_5_poster() -> None:
    plain = Image.open(io.BytesIO(art())).convert("RGB").resize((comic.SIDE, comic.SIDE))
    lettered = comic.letter(art(), SCRIPT)
    assert lettered.size == (comic.SIDE, comic.SIDE)
    for b in comic.bubbles(SCRIPT):
        x0, y0, x1, y1 = b["box"]
        assert lettered.getpixel(((x0 + x1) // 2, y0 + 6)) == (255, 255, 255)          # the bubble is white paper
    # below the empty top of each panel nothing is touched except by a tail
    half = comic.SIDE // 2
    for py in (0, half):
        y, xs = py + half - 20, range(0, comic.SIDE, 40)
        assert [lettered.getpixel((x, y)) for x in xs] == [plain.getpixel((x, y)) for x in xs]
    for comic_in in (lettered, art()):
        poster = Image.open(io.BytesIO(comic.frame(comic_in, SCRIPT)))
        assert poster.size == comic.POSTER and poster.format == "JPEG"


def test_the_sample_run_tries_every_picture_on_its_own() -> None:
    asked, saved = [], {}

    def chatgpt(prompt: str) -> bytes:
        asked.append(prompt)
        if "NO speech bubbles" in prompt:
            raise RuntimeError("the picture maker refused")
        return art()

    def save(name: str, data: bytes) -> str:
        saved[name] = data
        return f"https://example.test/{name}.jpg"

    out = comic_sample.run({"chatgpt": chatgpt, "gemini": "Gemini pictures are off"}, SCRIPT, save)
    assert [(r["maker"], r["mode"], r["ok"]) for r in out] == [
        ("chatgpt", "full", True), ("chatgpt", "art", False), ("gemini", "full", False), ("gemini", "art", False)]
    assert out[0]["detail"] == "https://example.test/chatgpt-full.jpg" and "refused" in out[1]["detail"]
    assert out[2]["detail"] == "Gemini pictures are off" and list(saved) == ["chatgpt-full"]
    assert len(asked) == 2 and Image.open(io.BytesIO(saved["chatgpt-full"])).size == comic.POSTER


def test_the_sample_letters_the_wordless_art_and_leaves_the_full_one_alone() -> None:
    saved = {}
    comic_sample.run({"x": lambda _p: art()}, SCRIPT, lambda n, d: saved.setdefault(n, d) and n)
    full, lettered = (Image.open(io.BytesIO(saved[k])).convert("RGB") for k in ("x-full", "x-art"))
    box = comic.bubbles(SCRIPT)[0]["box"]
    spot = ((box[0] + box[2]) // 2, comic.TITLE_H + box[1] + 6)
    near_white = lambda px: min(px) > 245                                                   # noqa: E731
    assert near_white(lettered.getpixel(spot)) and not near_white(full.getpixel(spot))
