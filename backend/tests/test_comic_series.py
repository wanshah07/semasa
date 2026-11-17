"""Comic as a Design choice: the saved styles and series, the script writer and its refusals, the read-back of the picture
maker's words, the border trim, the frame, the episode number and the worker's job. No picture maker and no reader is ever
called: both are plain functions here."""

import copy
import io
import json
import random

import pytest
from fakestore import FakeStore
from PIL import Image, ImageDraw

from semasa import comic, comic_job, comic_library, comic_sample, comic_writer, media_generator
from semasa.config import LLMSettings, MediaSettings

LIB = comic_library.library()
SERIES = LIB["series"][0]
STYLES = LIB["styles"]
PANELS = copy.deepcopy(comic_sample.SCRIPT["panels"])
TYPED = {"title": "Logo halal bukan hijau. Palsu ke?", "panels": PANELS}
SOURCE = "MPPHM (Domestik) 2020, Klausa 40(2)"
BRIEF = ("Logo Halal Malaysia tidak semestinya hijau. MPPHM (Domestik) 2020, Klausa 40(2): pemegang SPHM dibenarkan mencetak "
         "warna logo mengikut kesesuaian selagi tidak mengubah spesifikasi logo.")


def script(stream: str = "regulab", series: dict = SERIES, **change) -> dict:
    return comic_writer.assemble({**copy.deepcopy(TYPED), **change}, series, stream, SOURCE)


def picture(side: int = 1024, colour=(200, 220, 240)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (side, side), colour).save(buf, "PNG")
    return buf.getvalue()


def reading(s: dict, **change) -> dict:
    """What a perfect reader answers for a script; `change` maps a panel number to the bubbles it reports instead."""
    return {"panels": [{"panel": n, "bubbles": change.get(f"p{n}", [line["text"] for line in panel["lines"]])}
                       for n, panel in enumerate(s["panels"], 1)], "other_text": []}


# ---------------------------------------------------------------------------------------------------------- the rules file

def test_the_rules_file_holds_six_to_eight_whole_styles_and_one_to_three_series() -> None:
    rules = comic_library.RULES
    assert 6 <= len(rules["styles"]) <= 8 and 1 <= len(rules["series"]) <= 3
    ids = [s["id"] for s in rules["styles"]] + [s["id"] for s in rules["series"]]
    assert len(set(ids)) == len(ids) and all(comic_library.ID_RE.match(i) for i in ids)
    assert rules["styles"][0]["id"] == rules["default_style"] and rules["series"][0]["id"] == rules["default_series"]
    for s in rules["styles"]:
        assert comic_library.clean_style(s) == {k: s[k] for k in ("id", "name", "about", "prompt", "lettering")}
        assert s["name"]["bm"] and s["name"]["en"] and s["about"]["bm"] and s["about"]["en"]
        # a style is a precise description, written so another picture maker draws the same look
        for part in ("LINE:", "COLOUR:", "SHADING:", "PROPORTIONS:", "FACES:", "BACKGROUND:"):
            assert part in s["prompt"], (s["id"], part)
        assert "bubble" in s["lettering"].lower() and "lettering" in s["lettering"].lower()
    for s in rules["series"]:
        assert comic_library.clean_series(s) is not None and s["setting"]
        for who in ("A", "B"):
            person = s["cast"][who]
            assert all(person[k].strip() for k in ("name", "look", "role", "voice")), (s["id"], who)
            assert "mascot" not in person["look"].lower() and "logo" not in person["look"].lower()
    text = json.dumps(rules, ensure_ascii=False)
    assert "\u2014" not in text and "\u2013" not in text               # no em dash in anything a person reads


def test_the_first_style_is_the_16_nov_look_and_the_styles_differ() -> None:
    first = STYLES[0]["prompt"].lower()
    for words in ("clean modern", "flat", "soft", "bold black outlines", "warm"):
        assert words in first
    assert comic.STYLE == STYLES[0]["prompt"] and comic.DEFAULT_STYLE["id"] == "moden-bersih"
    prompts = [s["prompt"] for s in STYLES]
    assert len(set(prompts)) == len(prompts) and len({p.split(".")[0] for p in prompts}) == len(prompts)


def test_the_page_and_the_worker_read_the_same_limits() -> None:
    assert (comic.PANELS, comic.MAX_LINES, comic.MAX_CHARS) == (4, 2, 110)
    assert comic.MAX_TITLE == comic_library.LIMITS["title"] and comic.MAX_SOURCE == comic_library.LIMITS["source"]


# ------------------------------------------------------------------------------------------- styles and cast in the prompt

@pytest.mark.parametrize("style", STYLES, ids=[s["id"] for s in STYLES])
def test_a_styles_words_reach_both_prompts_verbatim(style) -> None:
    s = script()
    full, art = comic.prompt_full(s, style), comic.prompt_art(s, style)
    assert style["prompt"] in full and style["prompt"] in art
    assert style["lettering"] in full
    assert style["lettering"] not in art and "NO speech bubbles" in art     # wordless art is told nothing about lettering
    for other in STYLES:
        if other["id"] != style["id"]:
            assert other["prompt"] not in full and other["prompt"] not in art


def test_no_style_means_the_default_style() -> None:
    s = script()
    assert comic.prompt_full(s) == comic.prompt_full(s, STYLES[0]) and comic.prompt_art(s, {}) == comic.prompt_art(s, STYLES[0])


def test_the_cast_is_repeated_word_for_word_in_every_episode() -> None:
    one = script()
    two = script(title="Notifikasi itu kelulusan ke?", setting="a small pharmacy counter",
                 panels=[{"scene": "A asks.", "lines": [{"who": "A", "text": "Notifikasi tu kelulusan ke?"}]}] * 4)
    for ep in (one, two):
        for style in (STYLES[0], STYLES[3]):
            for prompt in (comic.prompt_full(ep, style), comic.prompt_art(ep, style)):
                assert f"Character A, always on the LEFT side of a panel: {SERIES['cast']['A']['look']}\n" in prompt
                assert f"Character B, always on the RIGHT side of a panel: {SERIES['cast']['B']['look']}\n" in prompt
    assert one["cast"] == two["cast"] == comic_library.cast_of(SERIES)
    assert "a small pharmacy counter" in comic.prompt_full(two) and SERIES["setting"] in comic.prompt_full(one)


def test_a_script_cannot_bring_its_own_cast_and_a_speaker_may_be_named() -> None:
    panels = copy.deepcopy(PANELS)
    panels[0]["lines"][0]["who"] = "Kak Lin"
    panels[1]["lines"][1]["who"] = "encik adam"
    s = comic_writer.assemble({"title": "Tajuk", "panels": panels, "cast": {"A": "a robot", "B": "a cat"}}, SERIES, "regulab")
    assert s["cast"] == comic_library.cast_of(SERIES) and "robot" not in comic.prompt_full(s)
    assert s["panels"][0]["lines"][0]["who"] == "A" and s["panels"][1]["lines"][1]["who"] == "B"
    assert s["names"] == {"A": "Kak Lin", "B": "Encik Adam"} and s["lang"] == "bm"
    assert comic_writer.assemble(TYPED, SERIES, "linkedin")["lang"] == "en"
    assert "The words are in English." in comic.prompt_full(comic_writer.assemble(TYPED, SERIES, "linkedin"))
    assert "The words are in Malay." in comic.prompt_full(s)


# ------------------------------------------------------------------------------------------------- Wan's own, merged over

OWN_STYLE = {"id": "pensel-kasar", "name": "Pensel kasar", "about": "Lakaran pensel.",
             "prompt": "Rough graphite pencil sketch on cream paper, heavy cross hatching, no colour at all, tall thin people.",
             "lettering": "Hand-written pencil capitals in rough bubbles."}


def test_wans_styles_and_series_are_merged_over_the_built_in_ones_by_id() -> None:
    edited = {**comic_library.RULES["styles"][1], "prompt": "A different newspaper look, written by Wan, with thick lines."}
    own_series = {**copy.deepcopy(comic_library.RULES["series"][0]), "id": "kedai-runcit", "name": "Kedai Runcit Pak Mat"}
    lib = comic_library.library({"styles": [OWN_STYLE, edited, {"id": "x"}, {"id": "Bad Id", "prompt": "y" * 50, "name": "n"}],
                                 "series": [own_series, {"id": "tiada-pelakon", "name": "Tiada", "cast": {}}],
                                 "default_style": "pensel-kasar", "default_series": "tiada-pelakon"})
    assert [s["id"] for s in lib["styles"]] == [s["id"] for s in comic_library.RULES["styles"]] + ["pensel-kasar"]
    assert lib["styles"][1]["prompt"].startswith("A different newspaper look") and lib["styles"][1]["edited"] is True
    assert lib["styles"][-1]["own"] is True and lib["styles"][-1]["name"] == {"bm": "Pensel kasar", "en": "Pensel kasar"}
    assert [s["id"] for s in lib["series"]][-1] == "kedai-runcit" and len(lib["series"]) == len(LIB["series"]) + 1
    assert lib["default_style"] == "pensel-kasar"
    assert lib["default_series"] == comic_library.RULES["default_series"]       # his default named a series that is not whole
    # a deleted style is drawn from the copy the job carried; one nobody knows is nothing
    assert comic_library.style_of(LIB, "pensel-kasar", OWN_STYLE)["prompt"] == OWN_STYLE["prompt"]
    assert comic_library.style_of(LIB, "tiada", None) is None and comic_library.library("rubbish") == LIB
    # an over-long description is refused whole, never cut: a cut style is a different style
    assert comic_library.clean_style({**OWN_STYLE, "prompt": "x " * 2000}) is None


def test_the_episode_line() -> None:
    assert comic_library.episode_line("Kak Lin Tanya", 4) == "Siri Kak Lin Tanya · Episod 4"
    assert comic_library.episode_line("Kak Lin Tanya", 4, "en") == "Kak Lin Tanya · Episode 4"
    assert comic_library.episode_line("", 4) == "" and comic_library.episode_line("Nota Makmal", None) == "Siri Nota Makmal"


# ---------------------------------------------------------------------------------------------------------- the script writer

class Writer:
    """Answers with each item of `answers` in turn (the last one again after that)."""

    configured = True

    def __init__(self, *answers):
        self.answers, self.seen, self.last_model = list(answers), [], "writer-m"
        self.s = LLMSettings(provider="openai", api_key="k", base_url="https://rootsys.cloud/v1", model="m", timeout=5)

    def why_off(self):
        return "off"

    def chat_json(self, system, user, max_tokens=0, **_k):
        self.seen.append((system, user))
        return copy.deepcopy(self.answers[min(len(self.seen), len(self.answers)) - 1])


GOOD = {"title": "Logo halal bukan *hijau*. Palsu ke?", "setting": "", "panels": PANELS, "citation": SOURCE}


def with_bubble(text: str, panel: int = 3, line: int = 0) -> dict:
    out = copy.deepcopy(GOOD)
    out["panels"][panel]["lines"][line]["text"] = text
    return out


def test_the_writer_gets_the_rules_the_voice_the_cast_and_the_brief() -> None:
    llm = Writer(GOOD)
    out = comic_writer.write(llm, BRIEF, "regulab", SERIES)
    system, user = llm.seen[0]
    assert "No call to action of any kind" in system and "Malaysian Malay" in system        # design.COMMON, design.VOICE
    assert "Kak Lin" in system and "Encik Adam" in system and SERIES["cast"]["A"]["voice"] in system
    assert f"at most {comic.MAX_CHARS}" in system and "WRITE LIKE A PERSON" in system        # the anti-slop block
    assert BRIEF in user and len(llm.seen) == 1
    assert out["title"] == "Logo halal bukan hijau. Palsu ke?" and out["citation"] == SOURCE  # no emphasis marks in a comic
    assert "English for regulatory" in comic_writer.system_prompt("linkedin", SERIES)


@pytest.mark.parametrize("bad, reason", [
    (with_bubble("Hubungi kami untuk semak kelayakan produk anda."), "Comic panel 4"),
    (with_bubble("Lawati www.kkmhalalconsultant.com untuk tahu lagi."), "Comic panel 4"),
    (with_bubble("Saya nampak dekat TikTok semalam."), "social source"),
    (with_bubble("Ada beberapa syarat penting yang perlu dipatuhi.", 3, 1), "vague"),
    (with_bubble("Kena siap dalam masa 30 hari."), "a figure the brief does not"),
    ({**GOOD, "panels": PANELS[:3]}, "exactly 4 panels"),
    (with_bubble("kata " * 30), "characters"),
])
def test_a_script_that_breaks_a_rule_is_asked_again_then_refused_with_the_reason(bad, reason) -> None:
    llm = Writer(bad)
    with pytest.raises(comic.ComicError, match="refused twice") as err:
        comic_writer.write(llm, BRIEF, "regulab", SERIES)
    assert reason in str(err.value)
    assert len(llm.seen) == 2 and "Your last script was refused" in llm.seen[1][1] and reason in llm.seen[1][1]
    # the same bad script, then a good one: the second is taken
    assert comic_writer.write(Writer(bad, GOOD), BRIEF, "regulab", SERIES)["panels"] == PANELS


def test_a_linkedin_comic_in_malay_is_refused_and_one_in_english_is_not() -> None:
    with pytest.raises(comic.ComicError, match="LinkedIn stream is English"):
        comic_writer.write(Writer(with_bubble(
            "Pemegang sijil boleh cetak logo yang sesuai dengan pembungkusan untuk produk anda kerana tidak diubah.")),
            BRIEF, "linkedin", SERIES)
    english = {"title": "A halal logo that is not green", "setting": "", "citation": SOURCE, "panels": [
        {"scene": "A studies a pack.", "lines": [{"who": "A", "text": "This halal logo is black. Should it be green?"}]},
        {"scene": "B smiles.", "lines": [{"who": "B", "text": "Colour does not decide it."}]},
        {"scene": "B points.", "lines": [{"who": "B", "text": "The holder may print it in a colour that suits the pack."}]},
        {"scene": "A nods.", "lines": [{"who": "A", "text": "Where is that written?"},
                                       {"who": "B", "text": "MPPHM (Domestik) 2020, Klausa 40(2)."}]}]}
    assert comic_writer.write(Writer(english), BRIEF, "linkedin", SERIES)["title"] == english["title"]


def test_no_writer_no_answer_and_no_brief_each_say_so() -> None:
    off = Writer(GOOD)
    off.configured = False
    for llm, brief, message in ((None, BRIEF, "writer is off"), (off, BRIEF, "writer is off"),
                                (Writer(None), BRIEF, "did not answer"), (Writer(GOOD), "  ", "no idea to write")):
        with pytest.raises(comic.ComicError, match=message):
            comic_writer.write(llm, brief, "regulab", SERIES)


def test_a_typed_script_is_judged_by_the_same_rules() -> None:
    clean = script()
    assert comic_writer.flags(clean, "regulab") == [] and comic_writer.refusal([]) == ""
    bad = script(panels=with_bubble("DM kami sekarang untuk semakan percuma.")["panels"])
    found = comic_writer.flags(bad, "regulab")
    assert any(f["hard"] and f["where"] == "Comic panel 4" for f in found) and "Comic panel 4" in comic_writer.refusal(found)
    titled = script(title="Hubungi kami untuk tahu lagi")
    assert any(f["where"] == "Comic title" for f in comic_writer.flags(titled, "regulab"))
    vague = script(panels=with_bubble("Ada beberapa syarat penting yang perlu dipatuhi.", 3, 1)["panels"])
    assert any("vague" in f["msg"] and f["hard"] for f in comic_writer.flags(vague, "regulab"))
    # the detail in the same bubble or the two after it pins the phrase down, as on a slide
    pinned = script(panels=with_bubble("Ada beberapa syarat dalam klausa itu.", 2)["panels"])
    assert not any("vague" in f["msg"] for f in comic_writer.flags(pinned, "regulab"))
    # his own figure is his own source: only a script the writer wrote is held to the brief's figures
    assert comic_writer.unsourced_figures(clean, "") == ["2020", "40", "2"]
    assert comic_writer.unsourced_figures(clean, BRIEF) == []
    # the comic's words are kept the way a design's words are, so a post it is attached to has them judged
    art = comic_writer.artwork(clean)
    assert art[0] == {"title": clean["title"], "points": []} and len(art) == 5
    assert art[2]["points"] == ["Jangan-jangan logo palsu?", "Tak semestinya. Warna bukan penentu."]


def test_the_source_line_is_labelled_in_the_streams_language() -> None:
    assert script()["source"] == f"Sumber: {SOURCE}" and script("linkedin")["source"] == f"Source: {SOURCE}"
    assert comic_writer.source_line("Sumber: JAKIM", "linkedin") == "Sumber: JAKIM"
    assert comic_writer.source_line("", "regulab") == ""


# ---------------------------------------------------------------------------------------------------------- the read-back

def test_the_comparison_evens_out_case_spaces_and_punctuation_spacing_only() -> None:
    assert comic_job.norm(" MPPHM (Domestik)  2020 , Klausa 40 (2) . ") == comic_job.norm("mpphm (domestik) 2020, klausa 40(2).")
    assert comic_job.norm("Jangan - jangan logo palsu ?") == comic_job.norm("Jangan-jangan logo palsu?")
    assert comic_job.norm("\u201cTak semestinya.\u201d") == comic_job.norm('"tak semestinya."')
    assert comic_job.norm("Klausa 40(2).") != comic_job.norm("Klausa 40(3).")
    assert comic_job.norm("pembungkusan") != comic_job.norm("pembukusan")
    s = script()
    assert comic_job.compare(s, reading(s)) == []
    assert comic_job.compare(s, reading(s, p2=["TAK SEMESTINYA.  Warna bukan penentu .", "jangan - jangan logo palsu?"])) == []
    wrong = comic_job.compare(s, reading(s, p4=["Mana tulis tu?", "MPPHM (Domestik) 2020, Klausa 40(3)."]))
    assert [d["panel"] for d in wrong] == [4] and wrong[0]["got"][1].endswith("40(3).")
    assert [d["panel"] for d in comic_job.compare(s, reading(s, p1=[]))] == [1]             # a missing bubble
    assert [d["panel"] for d in comic_job.compare(s, reading(s, p3=[PANELS[2]["lines"][0]["text"], "Betul!"]))] == [3]
    for unreadable in (None, {}, {"panels": "none"}, {"panels": [{"panel": 1, "bubbles": []}]}, "text"):
        assert len(comic_job.compare(s, unreadable)) == 4                                  # an unreadable check never passes


class Maker:
    def __init__(self):
        self.prompts = []

    def __call__(self, prompt: str) -> bytes:
        self.prompts.append(prompt)
        return picture()

    @property
    def kinds(self) -> list[str]:
        return ["art" if "NO speech bubbles" in p else "full" for p in self.prompts]


def test_words_that_match_keep_the_picture_makers_own_lettering() -> None:
    s, draw = script(), Maker()
    img, words = comic_job.make(s, STYLES[2], draw, lambda _jpeg: reading(s))
    assert draw.kinds == ["full"] and STYLES[2]["prompt"] in draw.prompts[0]
    assert words == {"path": "full", "checked": True, "exact": True, "by": "maker", "draws": 1, "why": "", "tries": []}
    assert img.size == (1024, 1024) and img.getpixel((40, 40)) == (200, 220, 240)          # nothing was lettered over it


def test_a_mismatch_is_drawn_once_more_and_a_second_match_is_kept() -> None:
    s, draw = script(), Maker()
    answers = [reading(s, p4=["Mana tulis tu?", "MPPHM (Domestik) 2020, Klausa 4(2)."]), reading(s)]
    _img, words = comic_job.make(s, None, draw, lambda _jpeg: answers.pop(0))
    assert draw.kinds == ["full", "full"]
    assert (words["path"], words["checked"], words["draws"], words["why"]) == ("full", True, 2, "")
    assert len(words["tries"]) == 1 and "panel 4" in words["tries"][0][0] and "Klausa 4(2)." in words["tries"][0][0]


def test_two_mismatches_fall_back_to_wordless_art_and_semasas_own_lettering() -> None:
    s, draw = script(), Maker()
    img, words = comic_job.make(s, STYLES[0], draw, lambda _jpeg: reading(s, p1=["Eh, logo halal kat paket ni warna hijau."]))
    assert draw.kinds == ["full", "full", "art"] and STYLES[0]["prompt"] in draw.prompts[2]
    assert (words["path"], words["by"], words["exact"], words["checked"], words["draws"]) == ("art", "semasa", True, False, 3)
    assert "differed from the script" in words["why"] and len(words["tries"]) == 2
    assert img.size == (comic.SIDE, comic.SIDE)
    box = comic.bubbles(s)[0]["box"]
    assert img.getpixel(((box[0] + box[2]) // 2, box[1] + 6)) == (255, 255, 255)           # Semasa's bubble is on it


def test_no_reader_or_a_silent_reader_falls_back_at_once() -> None:
    s = script()
    draw = Maker()
    _img, words = comic_job.make(s, None, draw, None)
    assert draw.kinds == ["art"] and (words["path"], words["checked"], words["draws"]) == ("art", False, 1)
    assert "no picture reader" in words["why"]
    draw = Maker()
    _img, words = comic_job.make(s, None, draw, lambda _jpeg: None)
    assert draw.kinds == ["full", "art"] and words["path"] == "art" and "gave no answer" in words["why"]
    draw = Maker()
    _img, words = comic_job.make(s, None, draw, lambda _jpeg: reading(s), mode="art")
    assert draw.kinds == ["art"] and words["path"] == "art" and "asked to print" in words["why"]


def test_other_text_the_reader_saw_is_recorded() -> None:
    s = script()
    _img, words = comic_job.make(s, None, Maker(), lambda _jpeg: {**reading(s), "other_text": ["HALAL", ""]})
    assert words["path"] == "full" and words["other_text"] == ["HALAL"]


# ------------------------------------------------------------------------------------------------------------- the trim

def bordered(border: int = 14, side: int = 1024, speckle: bool = True, frame_w: int = 5) -> Image.Image:
    """A 2 by 2 comic the way a picture maker returns it: a speckled coloured edge, then the panels' black outlines."""
    rnd = random.Random(7)
    img = Image.new("RGB", (side, side), (255, 255, 255))
    px = img.load()
    if speckle:
        for _ in range(side * border * 3):
            x, y = rnd.randrange(side), rnd.randrange(side)
            if min(x, y, side - 1 - x, side - 1 - y) < border or abs(x - side // 2) < 6 or abs(y - side // 2) < 6:
                px[x, y] = rnd.choice([(230, 30, 30), (250, 220, 20), (20, 20, 20)])
    d = ImageDraw.Draw(img)
    half, gap = side // 2, 8
    for cx in (0, 1):
        for cy in (0, 1):
            x0 = border if cx == 0 else half + gap
            y0 = border if cy == 0 else half + gap
            x1 = half - gap if cx == 0 else side - border - 1
            y1 = half - gap if cy == 0 else side - border - 1
            d.rectangle([x0, y0, x1, y1], fill=(215, 200, 185), outline=(10, 10, 10), width=frame_w)
    return img


def test_the_stray_border_is_trimmed_to_the_panel_outline() -> None:
    raw = bordered()
    out = comic.trim(raw)
    assert out.size == (1024 - 28, 1024 - 28)
    w, h = out.size
    for x, y in ((0, h // 4), (w - 1, h // 4), (w // 4, 0), (w // 4, h - 1)):
        assert max(out.getpixel((x, y))) < 40                           # the outline itself is now the edge
    edge = [out.getpixel((x, 0)) for x in range(0, w, 3)] + [out.getpixel((0, y)) for y in range(0, h, 3)]
    assert not any(max(p) - min(p) > 120 for p in edge)                 # no red or yellow speckle is left on the edge
    assert comic.trim(_png(raw)).size == out.size                       # bytes or a picture, the same


def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def test_the_gutter_between_the_panels_is_cleaned_too() -> None:
    out = comic.trim(bordered())
    w, h = out.size
    assert all(out.getpixel((w // 2, y)) == (255, 255, 255) for y in range(0, h, 5))
    assert all(out.getpixel((x, h // 2)) == (255, 255, 255) for x in range(0, w, 5))
    assert out.getpixel((w // 4, h // 4)) == (215, 200, 185)            # the drawing is untouched


def test_a_picture_with_no_border_comes_back_whole() -> None:
    clean = bordered(border=0, speckle=False)
    assert comic.trim(clean).size == clean.size
    photo = Image.new("RGB", (800, 800), (120, 160, 200))
    ImageDraw.Draw(photo).ellipse([200, 200, 600, 600], fill=(240, 200, 60))
    assert comic.trim(photo).size == (800, 800)                         # a flat picture is not all margin
    # a plain margin of one flat colour, with no outline anywhere (a style without outlines)
    soft = Image.new("RGB", (1000, 1000), (128, 128, 128))
    ImageDraw.Draw(soft).rectangle([20, 20, 979, 979], fill=(240, 228, 210))
    ImageDraw.Draw(soft).ellipse([300, 300, 700, 700], fill=(200, 90, 70))
    assert comic.trim(soft).size == (960, 960)
    # never more than the band, however deep a border looks
    deep = Image.new("RGB", (1000, 1000), (128, 128, 128))
    ImageDraw.Draw(deep).rectangle([300, 300, 699, 699], fill=(240, 228, 210))
    assert min(comic.trim(deep).size) >= 1000 - 2 * round(1000 * comic.TRIM_BAND) - 2


# ------------------------------------------------------------------------------------------------------------ the frame

LONG_TITLE = "Betulkah logo Halal Malaysia mesti dicetak hijau pada setiap pembungkusan produk makanan?"[:comic.MAX_TITLE]
LONG_SOURCE = ("Sumber: Manual Prosedur Pensijilan Halal Malaysia (Domestik) 2020, Klausa 40(2), Jabatan Kemajuan Islam "
               "Malaysia; Perintah Perihal Dagangan (Perakuan dan Penandaan Halal) 2011, perenggan 4(1)")


def boxes(plan: dict) -> dict:
    out = {}
    for key in ("episode", "title", "source", "website", "logo"):
        b = plan[key]
        if b:
            widest = max((b["font"].getlength(r) for r in b["rows"]), default=0) if key != "logo" else b["w"]
            x = b["x"] + ((b["w"] - widest) / 2 if b.get("align") == "centre" else 0)
            out[key] = (x, b["y"], x + widest, b["y"] + b["h"])
    return out


def overlap(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


@pytest.mark.parametrize("stream", ["regulab", "linkedin", None])
@pytest.mark.parametrize("title", ["Logo halal bukan hijau. Palsu ke?", LONG_TITLE, "Pembungkusankosmetik" * 4])
def test_the_frames_words_fit_and_never_overlap(stream, title) -> None:
    s = {**script(), "title": title, "source": LONG_SOURCE}
    episode = comic_library.episode_line("Siri yang namanya panjang sungguh untuk diuji di sini ya", 128)
    plan = comic.layout(s, episode=episode, stream=stream, website="www.kkmhalalconsultant.com")
    got = boxes(plan)
    w, h = comic.POSTER
    comic_box = (0, comic.TITLE_H, w, comic.TITLE_H + comic.SIDE)
    for key, box in got.items():
        assert box[0] >= comic.PAD - 1 and box[2] <= w - comic.PAD + 1 and box[1] >= 0 and box[3] <= h, (key, box)
        assert not overlap(box, comic_box), key
    keys = list(got)
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            assert not overlap(got[a], got[b]), (a, b)
    assert " ".join(plan["title"]["rows"]).replace(" ", "") == title.replace(" ", "")       # no word cut or dropped
    assert " ".join(plan["source"]["rows"]) == LONG_SOURCE and len(plan["title"]["rows"]) <= 3
    # ws.regulab carries the logo and the website; LinkedIn and the bare sample frame carry no brand identity
    assert (plan["logo"] is not None, plan["website"] is not None) == ((True, True) if stream == "regulab" else (False, False))
    poster = Image.open(io.BytesIO(comic.frame(picture(), s, episode=episode, stream=stream,
                                               website="www.kkmhalalconsultant.com")))
    assert poster.size == comic.POSTER and poster.format == "JPEG"


def test_a_short_title_is_larger_than_a_long_one_and_too_long_is_refused_by_name() -> None:
    short = comic.layout({**script(), "title": "Palsu ke?"})["title"]["font"].size
    long = comic.layout({**script(), "title": LONG_TITLE})["title"]["font"].size
    assert short > long >= 22
    with pytest.raises(comic.ComicError, match="title has"):
        script(title="kata " * 30)
    with pytest.raises(comic.ComicError, match="source has"):
        comic.check({**script(), "source": "s" * (comic.MAX_SOURCE + 1)})
    with pytest.raises(comic.ComicError, match="needs a title"):
        script(title="  ")


def test_the_brand_is_drawn_on_ws_regulab_only() -> None:
    s = {**script(), "source": ""}
    line = comic_library.episode_line(SERIES["name"], 4)
    plain = Image.open(io.BytesIO(comic.frame(picture(), s, episode=line, stream="linkedin", website="www.x.my"))).convert("L")
    brand = Image.open(io.BytesIO(comic.frame(picture(), s, episode=line, stream="regulab", website="www.x.my"))).convert("L")
    plan = comic.layout(s, episode=line, stream="regulab", website="www.x.my")
    for key in ("logo", "website"):
        b = plan[key]
        region = (b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"])
        assert plain.crop(region).getextrema()[0] > 240, key              # LinkedIn: bare paper where it would be
        assert brand.crop(region).getextrema()[0] < 200, key              # ws.regulab: it is there


# ------------------------------------------------------------------------------------------------------- the worker's job

def settings() -> MediaSettings:
    return MediaSettings(provider="cloudflare", batch=5, max_attempts=3, poll_seconds=0, max_wait_image=1,
                         max_wait_video=1, replicate_token=None, replicate_image_model="a/b",
                         replicate_video_model="c/d", replicate_image_input_key="input_image",
                         replicate_video_input_key="start_image", openai_key=None,
                         openai_base_url="https://api.openai.com/v1", openai_image_model="gpt-image-1",
                         openai_video_model="sora-2", openai_image_size="1024x1024", openai_video_seconds="8",
                         openai_video_size="1280x720")


def job(row_id: str = "c1", stream: str = "regulab", comic_meta: dict | None = None, **row) -> dict:
    meta = {"flow": "design", "design": "comic", "stream": stream, "citation": SOURCE,
            "comic": {"series": SERIES["id"], "style": STYLES[0]["id"], "script": copy.deepcopy(TYPED), **(comic_meta or {})}}
    return {"id": row_id, "mode": "slides", "type": "image", "status": "processing", "attempts": 1,
            "created_at": "2099-01-01T00:00:00+00:00", "meta": meta, **row}


def store_with(*rows: dict, comic_setting: dict | None = None) -> FakeStore:
    keys = [{"key": "brand", "value": {"regulab": {"website": "www.kkmhalalconsultant.com"}}}]
    if comic_setting is not None:
        keys.append({"key": "comic", "value": comic_setting})
    return FakeStore(semasa_settings=keys, semasa_posts=[{"id": "p1", "status": "draft", "media_ids": []}],
                     media_generations=list(rows))


@pytest.fixture(autouse=True)
def uploads(monkeypatch):
    got = {}
    monkeypatch.setattr(comic_job.db, "upload_generated",
                        lambda _store, path, data, _ct: got.setdefault(path, data) and f"https://cdn/{path}")
    return got


def run(store: FakeStore, row_id: str = "c1", *, read="match", llm=None, draw=None):
    row = next(r for r in store.tables["media_generations"] if r["id"] == row_id)
    draw = draw or Maker()
    if read == "match":
        def read(_jpeg):  # noqa: ANN001, ANN202
            s = comic_writer.assemble(next(r for r in store.tables["media_generations"]
                                           if r["id"] == row_id)["meta"]["comic"]["script"], SERIES, "regulab", SOURCE)
            return reading(s)
    ok = comic_job.process(store, copy.deepcopy(row), settings(), llm, draw=draw, read=read)
    return ok, next(r for r in store.tables["media_generations"] if r["id"] == row_id), draw


def test_a_typed_comic_is_drawn_checked_framed_and_kept_like_any_design(uploads) -> None:
    store = store_with(job(post_id="p1"))
    ok, done, draw = run(store)
    assert ok is True and done["status"] == "done" and done["error"] is None
    m, c = done["meta"], done["meta"]["comic"]
    assert draw.kinds == ["full"] and STYLES[0]["prompt"] in draw.prompts[0]
    assert (c["words"]["path"], c["words"]["checked"], c["episode"], c["stage"]) == ("full", True, 1, "done")
    assert c["episode_line"] == "Siri Kak Lin Tanya · Episod 1" and c["series_name"] == "Kak Lin Tanya"
    assert m["slide_urls"] == [done["generated_media_url"]] and m["count"] == 1 and m["look"] == "comic"
    assert m["slides"][0]["title"] == TYPED["title"] and m["flags"] == []
    assert Image.open(io.BytesIO(next(iter(uploads.values())))).size == comic.POSTER
    assert store.tables["semasa_posts"][0]["media_ids"] == ["c1"]         # attached to its draft, as a poster is
    # the publisher and the page read a design's words from meta.slides: a comic's are there
    from semasa import publisher
    assert publisher.scan_entry(done)["artwork"] == m["slides"] and publisher.pictures_of(done) == m["slide_urls"]


def test_the_worker_hands_a_comic_to_its_own_job(monkeypatch) -> None:
    seen = []
    monkeypatch.setattr(comic_job, "process", lambda store, row, s, llm, **k: seen.append((row["id"], sorted(k))) or True)
    store = store_with(job())
    assert media_generator.process_row(store, store.tables["media_generations"][0], settings(), {}, None) is True
    assert seen == [("c1", ["deadline", "providers"])]
    plain = {"mode": "slides", "meta": {}}
    assert media_generator.need_seconds(job(), settings()) > media_generator.need_seconds(plain, settings())


def test_an_episode_is_the_series_count_so_far_plus_one_and_survives_a_redraw() -> None:
    def old(row_id: str, series: str, episode, status: str = "done") -> dict:
        return {"id": row_id, "mode": "slides", "status": status,
                "meta": {"design": "comic", "comic": {"series": series, "episode": episode}}}
    store = store_with(job(), old("a", SERIES["id"], 1), old("b", SERIES["id"], 2), old("c", SERIES["id"], 3),
                       old("d", "nota-makmal", 9), old("e", SERIES["id"], 7, "error"), old("f", SERIES["id"], None),
                       {"id": "g", "mode": "slides", "status": "done", "meta": {"design": "poster"}})
    assert comic_job.episodes_so_far(store, SERIES["id"], "c1") == 3
    assert comic_job.episodes_so_far(store, "nota-makmal", "c1") == 9
    assert comic_job.episodes_so_far(store, "siri-baharu", "c1") == 0
    _ok, done, _ = run(store)
    assert done["meta"]["comic"]["episode"] == 4 and done["meta"]["comic"]["episode_line"] == "Siri Kak Lin Tanya · Episod 4"
    # drawn again (a redraw, or an edited script): the same episode, not a fifth
    store.tables["media_generations"].append(old("h", SERIES["id"], 5))
    _ok, again, _ = run(store)
    assert again["meta"]["comic"]["episode"] == 4
    # a deleted episode's number is not handed out again while a later one exists
    store = store_with(job(), old("a", SERIES["id"], 1), old("c", SERIES["id"], 3))
    assert run(store)[1]["meta"]["comic"]["episode"] == 4
    # a number Wan typed is his
    assert run(store_with(job(comic_meta={"episode": 12})))[1]["meta"]["comic"]["episode"] == 12


def test_the_fallback_path_is_recorded_on_the_job(uploads) -> None:
    store = store_with(job())
    ok, done, draw = run(store, read=lambda _jpeg: {"panels": [{"panel": n, "bubbles": ["salah"]} for n in range(1, 5)]})
    words = done["meta"]["comic"]["words"]
    assert ok and draw.kinds == ["full", "full", "art"]
    assert (words["path"], words["by"], words["checked"], words["exact"], words["draws"]) == ("art", "semasa", False, True, 3)
    store = store_with(job())
    ok, done, draw = run(store, read=None)
    assert ok and draw.kinds == ["art"] and "no picture reader" in done["meta"]["comic"]["words"]["why"]
    store = store_with(job(comic_meta={"words_mode": "art"}))
    assert run(store)[2].kinds == ["art"]


def test_a_script_that_breaks_a_rule_is_refused_before_anything_is_drawn() -> None:
    bad = {**copy.deepcopy(TYPED), "panels": with_bubble("Hubungi kami untuk semakan percuma.")["panels"]}
    store = store_with(job(comic_meta={"script": bad}))
    ok, done, draw = run(store)
    assert ok is False and done["status"] == "error" and draw.prompts == []
    assert "Comic panel 4" in done["error"] and "nothing was drawn" in done["error"]
    crowded = {**copy.deepcopy(TYPED), "panels": TYPED["panels"][:2]}
    ok, done, draw = run(store_with(job(comic_meta={"script": crowded})))
    assert ok is False and "exactly 4 panels" in done["error"] and draw.prompts == []


def test_an_idea_is_written_into_a_script_first_and_waits_for_wan_when_asked(uploads) -> None:
    waiting = job(comic_meta={"script": None, "review": True})
    waiting["meta"].update(brief=BRIEF, citation="")
    store = store_with(waiting)
    llm = Writer(GOOD)
    ok, row, draw = run(store, llm=llm)
    c = row["meta"]["comic"]
    assert ok and row["status"] == "done" and draw.prompts == [] and not uploads          # nothing drawn, nothing paid
    assert c["stage"] == "script" and c["script"]["panels"] == PANELS and c["written_by"] == "writer-m"
    assert row["meta"]["citation"] == SOURCE and row["meta"]["slides"][0]["title"] == "Logo halal bukan hijau. Palsu ke?"
    assert not row.get("generated_media_url")
    # Wan edits a bubble and presses Draw: the page puts the row back in the queue with his script
    c["script"]["panels"][0]["lines"][0]["text"] = "Eh, logo halal ni hitam. Betul ke?"
    row.update(status="processing", meta={**row["meta"], "comic": {**c, "stage": "draw"}})
    ok, done, draw = run(store, llm=llm)
    assert ok and draw.kinds == ["full"] and '"Eh, logo halal ni hitam. Betul ke?"' in draw.prompts[0]
    assert len(llm.seen) == 1 and done["meta"]["comic"]["stage"] == "done" and done["generated_media_url"]


def test_an_idea_without_review_is_written_and_drawn_in_one_go_and_a_refused_script_fails_with_the_reason() -> None:
    straight = job(comic_meta={"script": None})
    straight["meta"]["brief"] = BRIEF
    ok, done, draw = run(store_with(straight), llm=Writer(GOOD))
    assert ok and draw.kinds == ["full"] and done["meta"]["comic"]["script"]["title"] == "Logo halal bukan hijau. Palsu ke?"
    refused = job(comic_meta={"script": None})
    refused["meta"]["brief"] = BRIEF
    ok, done, draw = run(store_with(refused), llm=Writer(with_bubble("Klik link di bio untuk tahu lagi.")))
    assert ok is False and done["status"] == "error" and "refused twice" in done["error"] and draw.prompts == []
    nothing = job(comic_meta={"script": None})
    ok, done, _ = run(store_with(nothing))
    assert ok is False and "no script" in done["error"]


def test_wans_own_style_and_series_are_used_and_an_edit_reaches_the_next_episode() -> None:
    own_series = {**copy.deepcopy(comic_library.RULES["series"][0]), "id": "kedai-runcit", "name": "Kedai Runcit Pak Mat"}
    own_series["cast"]["A"]["look"] = "an elderly Malaysian shopkeeper in a white kopiah and a checked sarong, thin and smiling"
    row = job(comic_meta={"series": "kedai-runcit", "style": "pensel-kasar"})
    store = store_with(row, comic_setting={"styles": [OWN_STYLE], "series": [own_series]})
    assert comic_job.process(store, copy.deepcopy(row), settings(), None, draw=Maker(), read=None) is True
    done = store.tables["media_generations"][0]
    assert done["meta"]["comic"]["episode_line"] == "Siri Kedai Runcit Pak Mat · Episod 1"
    assert done["meta"]["comic"]["style_name"] == {"bm": "Pensel kasar", "en": "Pensel kasar"}
    maker = Maker()
    comic_job.process(store, copy.deepcopy(row), settings(), None, draw=maker, read=None)
    assert OWN_STYLE["prompt"] in maker.prompts[0] and "white kopiah and a checked sarong" in maker.prompts[0]
    # a series deleted from the library since: the copy the job carried is used; with no copy the job says so
    gone = job(comic_meta={"series": "kedai-runcit", "series_copy": own_series})
    assert comic_job.process(store_with(gone), copy.deepcopy(gone), settings(), None, draw=Maker(), read=None) is True
    lost = job(comic_meta={"series": "kedai-runcit"})
    s2 = store_with(lost)
    assert comic_job.process(s2, copy.deepcopy(lost), settings(), None, draw=Maker(), read=None) is False
    assert "not in the library" in s2.tables["media_generations"][0]["error"]


def test_a_linkedin_comic_is_in_english_and_carries_no_brand(uploads) -> None:
    english = {"title": "A halal logo that is not green", "panels": [
        {"scene": "A studies a pack.", "lines": [{"who": "A", "text": "This halal logo is black. Should it be green?"}]},
        {"scene": "B smiles.", "lines": [{"who": "B", "text": "Colour does not decide it."}]},
        {"scene": "B points.", "lines": [{"who": "B", "text": "The holder may print it in a colour that suits the pack."}]},
        {"scene": "A nods.", "lines": [{"who": "A", "text": "Where is that written?"},
                                       {"who": "B", "text": "MPPHM (Domestik) 2020, Klausa 40(2)."}]}]}
    row = job(stream="linkedin", comic_meta={"script": english})
    store = store_with(row)
    maker = Maker()
    assert comic_job.process(store, copy.deepcopy(row), settings(), None, draw=maker, read=None) is True
    c = store.tables["media_generations"][0]["meta"]["comic"]
    assert c["episode_line"] == "Kak Lin Tanya · Episode 1"
    poster = Image.open(io.BytesIO(next(iter(uploads.values())))).convert("RGB")
    logo = comic.layout(script(), episode="x", stream="regulab")["logo"]
    region = (logo["x"], logo["y"], logo["x"] + logo["w"], logo["y"] + logo["h"])
    assert poster.convert("L").crop(region).getextrema()[0] > 240


# ------------------------------------------------------------------------------------ a comic as an idea's one picture

def test_an_idea_can_ask_for_a_comic_as_its_posts_picture(monkeypatch) -> None:
    from semasa import ideas
    from semasa.llm import LLM

    assert ideas.format_of({"brief": {"format": "comic"}}) == "comic" and ideas.format_of({"brief": {}}) == "post"

    class IdeaWriter(LLM):
        def __init__(self, answer):
            super().__init__(LLMSettings(provider="openai", api_key="k", base_url="https://x/v1", model="m", timeout=5))
            self.answer = answer

        def chat_json(self, system, user, **_k):
            return self.answer

    monkeypatch.setattr(ideas, "read_source", lambda _url: {"ok": False, "why": "no link", "image": "https://news/p.jpg"})
    caption = "Logo halal tidak semestinya hijau. MPPHM (Domestik) 2020, Klausa 40(2) membenarkan warna ikut pembungkusan."
    brand = {"regulab": {"slots": ["08:00", "13:00", "21:00"], "schedule": {str(d): ["halal_my"] for d in range(7)}}}
    store = FakeStore(semasa_settings=[{"key": "brand", "value": brand}], semasa_posts=[], media_generations=[], semasa_ideas=[])
    llm = IdeaWriter({"fit": True, "hook": "Hijau ke?", "hook_shape": 21, "domain": "halal_my",
                      "citation": SOURCE, "text": {"bm": {"instagram": caption, "facebook": caption, "threads": caption}},
                      "visual_prompt": "a packet on a shelf", "alt": "paket"})
    idea = {"id": "i1", "stream": "regulab", "source_title": "T", "created_by": "u", "make_media": "image",
            "brief": {"format": "comic", "comic": {"series": "nota-makmal", "style": "chibi-comel"}}}
    store.tables["semasa_ideas"].append({**idea, "status": "working"})
    pid = ideas.process_idea(store, llm, idea, ideas.load_settings(store))
    jobs = store.tables["media_generations"]
    assert len(jobs) == 1                                               # the comic is the picture: no other picture is made
    m = jobs[0]["meta"]
    assert (jobs[0]["mode"], jobs[0]["post_id"], m["design"], m["stream"]) == ("slides", pid, "comic", "regulab")
    assert m["comic"] == {"series": "nota-makmal", "style": "chibi-comel", "words_mode": "auto"} and "script" not in m["comic"]
    assert caption in m["brief"] and m["brief"].startswith("Hijau ke?") and m["citation"] == SOURCE
    assert "review" not in m["comic"]                                    # the draft itself is what waits for Wan
    # a citation too long for the foot of a comic is left to the comic's writer, never cut
    long = ideas.comic_job(idea, {"stream": "linkedin", "lang": "en", "hook": "h", "citation": "c" * 400,
                                  "text": {"en": {"linkedin": "The caption."}}}, "p9")
    assert long["meta"]["citation"] == "" and "The caption." in long["meta"]["brief"] and ("c" * 400) in long["meta"]["brief"]


def test_a_job_that_names_no_series_or_style_takes_the_librarys_defaults() -> None:
    row = job(comic_meta={"series": "", "style": ""})
    store = store_with(row)
    maker = Maker()
    assert comic_job.process(store, copy.deepcopy(row), settings(), None, draw=maker, read=None) is True
    c = store.tables["media_generations"][0]["meta"]["comic"]
    assert (c["series"], c["style"]) == (comic_library.RULES["default_series"], comic_library.RULES["default_style"])
    assert STYLES[0]["prompt"] in maker.prompts[0] and c["episode_line"] == "Siri Kak Lin Tanya · Episod 1"
