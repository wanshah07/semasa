"""Auto-fit in the browser-drawn looks (Wan, 16 Nov 2026: "for all poster, single card, comic, image make auto-fit
application"): the card renderer web/src/lib/cards/studio.js, drawn for real by the worker's own headless Chrome.

Like the other drawing tests these need a browser: they run when SEMASA_CHROME names one. Semasa's own (Pillow) drawing
has the same checks in test_autofit.py, and the search behind every family's fit is tested in web/autofit.test.mjs."""

import io
import os

import pytest
from PIL import Image

from semasa import compliance, studio_cards
from semasa.slides import SlideError

browser = pytest.mark.skipif(not os.environ.get("SEMASA_CHROME"), reason="set SEMASA_CHROME to draw in a real browser")

SLIDES = [
    {"title": "Notifikasi *bukan* kelulusan", "points": ["Nombor NOT bermaksud produk telah dinotifikasi."]},
    {"title": "Apa NPRA semak", "points": ["Maklumat pada borang.", "Bukan formula penuh.", "Bukan label."]},
    {"title": "Ingat ini", "points": ["Notifikasi ialah permulaan."]},
]


def _jpeg(w=1080, h=1080):
    b = io.BytesIO()
    Image.new("RGB", (w, h), (240, 235, 220)).save(b, "JPEG")
    return b.getvalue()


# Whatever words a card is given, it fits by itself. The same template is drawn with a short load and with a long one, in
# one render each, and the two pictures are compared where words may never be: the outer margin, the rows of the source
# line and under it, and the logo's corner. Everything else there (the logo, the source, the paper) is the same in both,
# so ink that differs is words that escaped. A card the renderer refuses raises, which fails the test by slide number.

FIT_TOKEN = "NPRA.600-1/9/13(13)Jld.2"
FIT_TITLE = {
    "short": "Semak label *dahulu*",
    "typical": "Notifikasi NPRA *bukan* kelulusan produk kosmetik",
    "long": f"Direktif {FIT_TOKEN} mewajibkan label *pembungkusan* kosmetik dikemas kini sebelum tarikh kuat kuasa",
}
FIT_LEAD = {
    "short": "",
    "typical": "Tiga perkara yang ramai pengeluar kosmetik salah faham tentang nombor notifikasi.",
    "long": "Pemegang notifikasi bertanggungjawab memastikan setiap pembungkusan, label dan risalah produk mematuhi garis "
    "panduan sebelum produk dipasarkan kepada pengguna di Malaysia.",
}
_S = [
    "Pemegang notifikasi mesti mengemas kini label pembungkusan dan menyimpan rekod pengilangan lengkap bagi setiap kelompok "
    "produk kosmetik yang dipasarkan di seluruh Malaysia tanpa pengecualian",
    "Pembungkusan luar dan dalam perlu memaparkan nama produk, senarai ramuan penuh, nombor kelompok, tarikh luput serta nama "
    "dan alamat pemegang notifikasi dengan jelas",
    "Setiap perubahan formula, pengilang atau pembungkusan mesti dimaklumkan kepada pihak berkuasa melalui sistem dalam talian "
    "sebelum produk yang diubah itu boleh dijual semula",
    "Fail maklumat produk hendaklah disimpan di alamat pemegang notifikasi dan diserahkan kepada pegawai penguat kuasa dalam "
    "tempoh yang ditetapkan apabila diminta secara rasmi",
    "Kegagalan mematuhi keperluan pelabelan dan pembungkusan boleh menyebabkan pembatalan notifikasi, penarikan balik produk "
    "daripada pasaran serta tindakan undang-undang terhadap pemegang notifikasi tersebut",
]
_H = ["Label pembungkusan", "Senarai ramuan penuh", "Perubahan formula", "Fail maklumat produk", "Pembatalan notifikasi"]


def _cut(text, n):
    return " ".join(text.split()[:n])


FIT_POINTS = {
    "plain": {
        "short": ["Label ada nombor NOT."],
        "typical": [
            "Nombor NOT bermaksud produk telah dinotifikasi.",
            "NPRA tidak menilai keselamatan sebelum nombor dikeluarkan.",
            "PIF mesti lengkap dan sedia diaudit.",
        ],
        "long": [x + "." for x in _S],
    },
    "pairs": {
        "short": ["Label | Ada nombor NOT."],
        "typical": [
            "Pengisytiharan | Pemegang notifikasi mengisytiharkan produk mematuhi garis panduan.",
            "Bukan penilaian | NPRA tidak menilai keselamatan sebelum nombor NOT dikeluarkan.",
            "Tanggungjawab | PIF mesti lengkap dan sedia diaudit pada bila-bila masa.",
        ],
        "long": [f"{h} | {_cut(x, 19)}." for h, x in zip(_H, _S, strict=True)],
    },
    "myth": {
        "short": ["Bernombor bermakna lulus | Nombor bukan kelulusan"],
        "typical": [
            "Ada nombor NOT, sudah lulus | Nombor NOT bukan kelulusan keselamatan",
            "NPRA uji semua produk | NPRA semak maklumat yang diisytiharkan",
        ],
        "long": [f"{_cut(_S[i], 11)} | {_cut(_S[i + 2], 11)}" for i in range(3)],
    },
    "bars": {
        "short": ["Malaysia | 0.5 | 0.5%"],
        "typical": ["Malaysia | 0.5 | 0.5%", "EU | 0.4 | 0.4%", "ASEAN | 0.5 | 0.5%"],
        "long": [
            "Had pembungkusan produk bilas Malaysia | 3.0 | 3.0% w/w",
            "Had produk tinggal Kesatuan Eropah | 0.5 | 0.5% w/w",
            "Had ASEAN Cosmetic Directive Annex III | 2.5 | 2.5% w/w",
            "Had cadangan jawatankuasa saintifik | 1.0 | 1.0% w/w",
            "Had sedia ada sebelum pindaan direktif | 2.0 | 2.0% w/w",
        ],
    },
    "triple": {
        "short": ["I | Surat | amaran"],
        "typical": [
            "I | Surat amaran | Notis bertulis kepada pemegang notifikasi.",
            "II | Penggantungan | Produk tidak boleh dijual sementara.",
            "III | Pembatalan | Notifikasi dibatalkan dan produk ditarik balik.",
        ],
        "long": [],
    },
    "yesno": {
        "short": ["Perkara | Kosmetik | Ubat", "Dinilai sebelum pasaran | tidak | ya", "Nombor rujukan | NOT | MAL"],
        "typical": [
            "Perkara | Kosmetik | Ubat",
            "Dinilai sebelum pasaran | tidak | ya",
            "Nombor rujukan | NOT | MAL",
            "Audit selepas pasaran | ya | ya",
            "Tuntutan rawatan | tidak | ya",
        ],
        "long": [
            "Perkara | Kosmetik | Ubat tradisional | Suplemen kesihatan",
            "Penilaian keselamatan pembungkusan sebelum pasaran | tidak | ya | ya",
            "Nombor rujukan pada label | NOT | MAL | MAL",
            "Audit pengilangan selepas pasaran | ya | ya | ya",
            "Tuntutan rawatan atau pencegahan penyakit | tidak | ya | tidak",
            "Pembaharuan setiap dua tahun | ya | tidak | tidak",
        ],
    },
    "headpairs": {
        "short": ["Wajib ke? | Ya", "Siapa semak | NPRA"],
        "typical": ["Wajib ke? | Ya", "Siapa semak | NPRA", "Tempoh sah | 2 tahun", "Boleh dibatalkan | Ya"],
        "long": ["Wajib ke? | Ya"] + [f"{h} | {_cut(x, 14)}" for h, x in zip(_H[:4], _S, strict=False)],
    },
}
# how each design takes its points, and how many of them it is given at most
FIT_SHAPE = {
    "g_bars": ("bars", 5),
    "g_rows": ("pairs", 4),
    "g_table": ("triple", 5),
    "g_check": ("pairs", 5),
    "g_myth": ("myth", 3),
    "e_explain": ("pairs", 3),
    "e_flow": ("pairs", 4),
    "e_myth": ("myth", 3),
    "e_check": ("pairs", 5),
    "p_fact": ("plain", 4),
    "p_list": ("pairs", 5),
    "p_split": ("plain", 5),
    "i_title": ("plain", 5),
    "i_hero": ("plain", 5),
    "i_step": ("plain", 5),
    "h_poster": ("headpairs", 5),
    "h_note": ("plain", 5),
}
FIT_SKIN = {"cover": ("plain", 5), "points": ("pairs", 5), "table": ("yesno", 6), "pick": ("plain", 5), "close": ("plain", 5)}
PICTURE_LOOKS = ("p", "i")


def _fit_slide(template, load):
    kind, most = FIT_SHAPE.get(template) or FIT_SKIN[template[2:]]
    slide = {
        "title": FIT_TITLE[load],
        "template": template,
        "points": FIT_POINTS[kind][load][:most],
        "footnote": "NPRA",
        "eyebrow": "Kosmetik",
    }
    if FIT_LEAD[load] and template != "g_bars":
        slide["lead"] = FIT_LEAD[load]
    if (template[0] not in PICTURE_LOOKS and not template.endswith("_cover")) or template == "i_title":
        slide["bg"] = "none"  # the set's picture is for the designs that are built on one
    return slide


def _fit_render(templates, load, size):
    """Every template in one render (one browser). A slide the renderer calls too full raises here, by number."""
    pics = studio_cards.render(
        [_fit_slide(t, load) for t in templates],
        look="grid",
        stream="regulab",
        eyebrow="Kosmetik",
        ground=_jpeg(900, 1100),
        size=size,
    )
    return [Image.open(io.BytesIO(p)).convert("RGB") for p in pics]


def _fit_escaped(card, calm):
    """Pixels that differ between the two cards in the outer margin, on or under the source line, and in the logo's corner."""
    from PIL import ImageChops

    w, h = card.size
    r, g, b = ImageChops.difference(card, calm).split()
    d = ImageChops.lighter(ImageChops.lighter(r, g), b).point(lambda v: 255 if v > 48 else 0)

    def n(box):
        return sum(1 for v in d.crop(box).tobytes() if v)

    return {
        "margin": n((0, 0, w, 30)) + n((0, h - 30, w, h)) + n((0, 0, 30, h)) + n((w - 30, 0, w, h)),
        "source": n((0, h - 100, w, h)),
        "logo": n((730, 0, w, 100)),
    }


def _fit_span(card):
    """The share of the free area (under the logo row, above the source line) between the first and the last row that
    carries something to look at: an edge, a letter, a box."""
    g = card.convert("L")
    w, h = g.size
    px = g.load()
    top, bottom = 130, h - 121
    rows = [y for y in range(top, bottom) if sum(1 for x in range(90, w - 93, 2) if abs(px[x, y] - px[x + 3, y]) > 30) >= 3]
    return (rows[-1] - rows[0]) / (bottom - top) if rows else 0.0


FIT_LONG_PORTRAIT = [
    "g_bars",
    "g_myth",
    "e_explain",
    "e_flow",
    "p_list",
    "h_poster",
    "h_note",
    "m_points",
    "b_pick",
    "k_table",
    "l_points",
    "s_table",
    "d_close",
]
FIT_TYPICAL_SQUARE = [
    "g_rows",
    "g_table",
    "g_check",
    "e_myth",
    "e_check",
    "p_fact",
    "p_split",
    "i_hero",
    "i_step",
    "k_cover",
    "t_points",
    "n_table",
]
FIT_SHORT = [
    "g_rows",
    "g_check",
    "e_explain",
    "e_check",
    "p_list",
    "i_title",
    "h_note",
    "m_points",
    "b_points",
    "d_close",
    "k_pick",
    "l_points",
]


@browser
@pytest.mark.parametrize(
    "templates,load,size", [(FIT_LONG_PORTRAIT, "long", (1080, 1350)), (FIT_TYPICAL_SQUARE, "typical", (1080, 1080))]
)
def test_a_full_card_fits_by_itself_with_no_word_in_the_margin_on_the_source_or_under_the_logo(templates, load, size):
    """The long load is a 110-character title with a reference no wrapper can break on a space, a 22-word lead and the
    most points the design takes, each as long as the writer may make it. On the square card, which is 270 px shorter,
    the typical load used to be refused by a dozen designs."""
    calm = _fit_render(templates, "short", size)
    full = _fit_render(templates, load, size)
    for t, a, b in zip(templates, full, calm, strict=True):
        assert a.size == size, t
        hit = _fit_escaped(a, b)
        assert hit["margin"] < 25 and hit["source"] < 40 and hit["logo"] < 25, f"{t} ({load}): words escaped {hit}"


@browser
def test_a_card_with_little_to_say_fills_at_least_half_of_its_room():
    """Three words and one short point: the content must span half of the free area. It used to sit in the upper third."""
    for t, card in zip(FIT_SHORT, _fit_render(FIT_SHORT, "short", (1080, 1350)), strict=True):
        assert _fit_span(card) >= 0.5, f"{t}: the words span only {_fit_span(card):.0%} of the free area"


@browser
@pytest.mark.parametrize("look", ["grid", "era", "image", "hand", "marker"])
def test_words_that_cannot_fit_at_a_readable_size_are_refused_in_every_family_never_drawn_off_the_card(look):
    """The most one slide can hold (compliance.normalise_slides: a 240-character title and five points of 400) does not
    fit a square card at any size a phone can read. The renderer says so by slide number, and the worker ships nothing."""
    most = compliance.normalise_slides([{"title": (FIT_TITLE["long"] + " ") * 3, "points": [(x + ". ") * 4 for x in _S]}])[0]
    assert len(most["title"]) == 240 and [len(p) for p in most["points"]] == [400] * 5
    with pytest.raises(SlideError, match="slide 2.*fuller than the card"):
        studio_cards.render(
            [SLIDES[0], most, SLIDES[2]], look=look, stream="regulab", eyebrow="Kosmetik", source="NPRA", size=(1080, 1080)
        )


@browser
def test_the_same_hand_drawn_card_is_the_same_picture_every_time():
    """Its wobbly border came from Math.random: no two renders of one slide matched, so nothing about it could be compared."""
    one = [{"title": "Semak *dahulu*", "template": "h_poster", "points": ["Wajib ke? | Ya", "Siapa semak | NPRA"]}]
    assert studio_cards.render(one, look="hand", stream="regulab") == studio_cards.render(one, look="hand", stream="regulab")
