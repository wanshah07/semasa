# ruff: noqa: E501   (the in-page measuring script is one readable block of JavaScript)
"""Wan, 17 Nov 2026: "Make sure comic or person not cut off". The film's frames are MEASURED in a real browser: at many moments of
every scene, with the GSAP timeline sought exactly as the renderer does, the whole panel (its frame, its four edges) lies inside
the safe margins of the 1080x1920 canvas, the ink frame is really on screen on all four sides (read from a screenshot), and no
text or bubble runs past its box or the margins. Needs a browser: SEMASA_CHROME=/path/to/chrome."""

from __future__ import annotations

import io
import os
import shutil
from pathlib import Path

import pytest
from PIL import Image

from semasa import comic, comic_film, comic_library, comic_writer, motion_templates

browser = pytest.mark.skipif(
    not os.environ.get("SEMASA_CHROME"), reason="set SEMASA_CHROME to measure the frames in a real browser"
)
ROOT = Path(__file__).resolve().parents[2]
GSAP = ROOT / ".claude" / "skills" / "ws-regulab-motion" / "assets" / "gsap.min.js"
W, H = comic_film.W, comic_film.H
TOL = 1.5

PANELS = [
    {"scene": "s", "lines": [{"who": "A", "text": "Hana, ada berita dua orang ditahan guna sijil halal palsu. Betul ke?"}]},
    {
        "scene": "s",
        "lines": [
            {"who": "A", "text": "Sijil tu macam mana nak tahu palsu?"},
            {"who": "B", "text": "Buletin TV3 melaporkan dua individu ditahan kerana guna sijil itu."},
        ],
    },
    {"scene": "s", "lines": [{"who": "B", "text": "Pewarna rambut, Pak Mat."}]},
    {"scene": "s", "lines": [{"who": "A", "text": "Oh, begitu."}, {"who": "B", "text": "Itu yang dilaporkan."}]},
]
SB = {
    "title": "Sijil halal palsu: apa yang dilaporkan oleh penguat kuasa minggu ini?",
    "panels": PANELS,
    "episode": 12,
    "source": "Buletin TV3, 16 Nov 2026: dua individu ditahan kerana menggunakan sijil halal palsu",
    "names": {"A": "Pak Mat", "B": "Hana"},
}


def art(side: int = 1080) -> Image.Image:
    img = Image.new("RGB", (side, side), (240, 232, 214))
    for n, c in enumerate(((220, 120, 120), (120, 200, 130), (120, 140, 220), (230, 200, 90))):
        x, y = (n % 2) * side // 2, (n // 2) * side // 2
        img.paste(Image.new("RGB", (side // 2 - 6, side // 2 - 6), c), (x + 3, y + 3))
    return img


def build(tmp: Path, *, wordless: bool) -> Path:
    series = comic_library.series_of(comic_library.library(None), "isu-semasa-harian")
    script = comic_writer.assemble({"title": SB["title"], "setting": "", "panels": PANELS}, series, "regulab", SB["source"])
    folder = tmp / ("w" if wordless else "b")
    folder.mkdir(parents=True)
    buf = io.BytesIO()
    art().save(buf, "PNG")
    panels = comic_film.write_panels(buf.getvalue(), folder, wordless=wordless)
    html, _ = comic_film.compose(
        SB,
        script,
        panels,
        wordless=wordless,
        website="www.kkmhalalconsultant.com",
        episode_line=comic_library.episode_line(series["name"], 12, "bm"),
    )
    motion_templates.copy_fonts(folder)
    shutil.copy(GSAP, folder / "gsap.min.js")
    shutil.copy(ROOT / "rules" / "motion" / "official-logo-transparent.png", folder / "assets" / "official-logo-transparent.png")
    (folder / "index.html").write_text(html.replace(motion_templates.GSAP_URL, "gsap.min.js"), encoding="utf-8")
    return folder


MEASURE = """() => { const out = []; const win = {w: innerWidth, h: innerHeight};
  const shown = (el) => { for (let e = el; e && e !== document.body; e = e.parentElement) { if (+getComputedStyle(e).opacity < 0.05) return false; } return true; };
  const clips = [...document.querySelectorAll('.clip')].filter(c => c.style.visibility === 'visible');
  for (const c of clips) {
    for (const el of c.querySelectorAll('.box, .ey, .cnt, .ttl, .say, .dots, .os, #ol')) {
      if (!shown(el)) continue;
      const r = el.getBoundingClientRect(); let tr = r;
      if (el.matches('.ey, .cnt, .ttl, .say, .os')) { const g = document.createRange(); g.selectNodeContents(el); tr = g.getBoundingClientRect(); }
      out.push({cls: el.className || el.id, id: el.id, l: tr.left, r: tr.right, t: tr.top, b: tr.bottom, box: el.matches('.box') ? {l: r.left, r: r.right, t: r.top, b: r.bottom} : null});
    }
    for (const el of c.querySelectorAll('.art')) {
      const r = el.getBoundingClientRect(), p = el.closest('.box').getBoundingClientRect();
      out.push({cls: 'art', id: '', l: r.left, r: r.right, t: r.top, b: r.bottom, inside: p, over: false});
    }
    for (const el of c.querySelectorAll('.bt')) {
      if (!shown(el)) continue;
      const r = el.getBoundingClientRect(), p = el.closest('.box').getBoundingClientRect();
      out.push({cls: 'bt', id: el.parentElement.id, l: r.left, r: r.right, t: r.top, b: r.bottom, inside: p, over: el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 1});
    }
  } return {win, out}; }"""


def seek(page, t):
    page.evaluate(
        "(t) => { window.__timelines.main.seek(t); document.querySelectorAll('.clip').forEach(c => { const s = +c.dataset.start, d = +c.dataset.duration; "
        "c.style.visibility = (t >= s && t < s + d) ? 'visible' : 'hidden'; }); }",
        t,
    )


@browser
@pytest.mark.parametrize("wordless", [True, False])
def test_no_camera_move_ever_crops_the_panel_or_pushes_a_word_past_the_margins(tmp_path, wordless):
    from playwright.sync_api import sync_playwright

    from semasa.studio_cards import _launch

    folder = build(tmp_path, wordless=wordless)
    tl = comic_film.timeline(SB)
    times = []
    for p in tl["panels"]:  # every scene from its first frame to its last, and across the cut
        times += [p["start"] + i * 0.25 for i in range(int(p["duration"] / 0.25) + 1)] + [p["start"] + p["duration"] - 0.01]
    times += [0.0, 1.0, comic_film.TITLE_SECONDS - 0.05, tl["outro_start"] + 0.2, tl["outro_start"] + 1.2, tl["total"] - 0.05]
    shots = {}
    for p in tl["panels"]:
        shots[round(p["start"] + 0.5, 2)] = "start"
        shots[round(p["start"] + p["duration"] / 2, 2)] = "middle"
        shots[round(p["start"] + p["duration"] - 0.4, 2)] = "end"
    with sync_playwright() as pw:
        b = _launch(pw)
        try:
            page = b.new_page(viewport={"width": W, "height": H})
            page.goto((folder / "index.html").as_uri())
            page.wait_for_function("() => !!(window.__timelines && window.__timelines.main)", polling=100)
            page.wait_for_timeout(500)
            seen_box = 0
            for t in sorted(set(times) | set(shots)):
                seek(page, t)
                got = page.evaluate(MEASURE)
                for m in got["out"]:
                    where = f"t={t:g} {m['cls']} {m['id']}"
                    if m["cls"] in ("bt", "art"):
                        assert not m["over"], f"{where}: the words run past their bubble"
                        i = m["inside"]
                        assert (
                            m["l"] >= i["left"] - TOL
                            and m["r"] <= i["right"] + TOL
                            and m["t"] >= i["top"] - TOL
                            and m["b"] <= i["bottom"] + TOL
                        ), f"{where}: a bubble (or the picture itself, when it is scaled past its box) leaves its panel"
                        continue
                    if m["r"] - m["l"] == 0 and m["b"] - m["t"] == 0:
                        continue  # the decorative rule has no text to measure
                    assert m["l"] >= comic_film.SAFE_X - TOL and m["r"] <= W - comic_film.SAFE_X + TOL, (
                        f"{where}: outside the side margins {m}"
                    )
                    assert m["t"] >= comic_film.SAFE_Y - TOL and m["b"] <= H - comic_film.SAFE_Y + TOL, (
                        f"{where}: outside the top and bottom margins {m}"
                    )
                    if m["box"]:
                        seen_box += 1
                if t in shots:
                    box = next((m["box"] for m in got["out"] if m["box"]), None)
                    png = Image.open(io.BytesIO(page.screenshot())).convert("RGB")
                    assert box, f"t={t:g}: no panel on screen"
                    mid_x, mid_y = round((box["l"] + box["r"]) / 2), round((box["t"] + box["b"]) / 2)
                    # the ink frame (7 px just outside the panel) is on screen on all four sides: the whole panel is in the frame
                    for name, xy in (
                        ("left", (round(box["l"]) - 4, mid_y)),
                        ("right", (round(box["r"]) + 3, mid_y)),
                        ("top", (mid_x, round(box["t"]) - 4)),
                        ("bottom", (mid_x, round(box["b"]) + 3)),
                    ):
                        assert sum(png.getpixel(xy)) < 150, (
                            f"t={t:g} ({shots[t]}): the panel's {name} edge is not on screen at {xy}"
                        )
            assert seen_box > 20
        finally:
            b.close()


def test_the_camera_never_scales_a_panel_above_its_own_box():
    sb = {"title": "T", "panels": PANELS, "source": "S", "names": {"A": "a", "B": "b"}}
    series = comic_library.series_of(comic_library.library(None), "isu-semasa-harian")
    script = comic_writer.assemble({"title": "T", "setting": "", "panels": PANELS}, series, "regulab", "S")
    for wordless in (True, False):
        html, _ = comic_film.compose(
            sb, script, [f"assets/panel{i}.jpg" for i in (1, 2, 3, 4)], wordless=wordless, website="w", episode_line="E"
        )
        import re

        scales = [float(x) for x in re.findall(r"scale:([\d.]+)", html)]
        assert scales and max(scales) <= 1.0, "a push-in past the box would crop the panel"
    assert comic_film.BOX == W - 2 * comic_film.SAFE_X and comic_film.BOX_X >= comic_film.SAFE_X
    assert comic_film.BOX_Y >= comic_film.SAFE_Y and comic_film.BOX_Y + comic_film.BOX <= H - comic_film.SAFE_Y


def test_the_comic_constants_the_film_relies_on_are_the_real_ones():
    assert comic.SIDE == 1080 and comic.PANELS == 4
