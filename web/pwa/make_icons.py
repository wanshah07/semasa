"""Draws the Home Screen icons from Semasa's own mark (public/favicon.svg and the header's tile: an ink square, a sky-blue
ring, a pink dot), so the installed app wears the same mark as the tab. Run once after the mark changes:
    python3 web/pwa/make_icons.py
Drawn 4x larger and scaled down, which is how PIL gets smooth edges on a circle."""
from pathlib import Path
from PIL import Image, ImageDraw

INK, ACCENT, WARM = (16, 34, 47, 255), (63, 166, 238, 255), (255, 194, 206, 255)
OUT = Path(__file__).resolve().parent.parent / "public" / "icons"


def mark(size, *, rounded, scale=1.0):
    """The favicon's geometry on a 64 grid: ring radius 14, stroke 6, dot radius 4, tile corner 16.
    `rounded`: transparent corners like the favicon (the plain "any" icon). iOS and maskable icons must be full-bleed:
    iOS paints transparent corners black, and a maskable icon is cut to the launcher's own shape.
    `scale` shrinks the ring for the maskable icon, whose safe zone is the middle 80%."""
    s = size * 4
    u = s / 64
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if rounded:
        d.rounded_rectangle([0, 0, s - 1, s - 1], radius=16 * u, fill=INK)
    else:
        d.rectangle([0, 0, s, s], fill=INK)
    c = s / 2
    r_out, r_in, dot = (14 + 3) * u * scale, (14 - 3) * u * scale, 4 * u * scale
    d.ellipse([c - r_out, c - r_out, c + r_out, c + r_out], fill=ACCENT)
    d.ellipse([c - r_in, c - r_in, c + r_in, c + r_in], fill=INK)
    d.ellipse([c - dot, c - dot, c + dot, c + dot], fill=WARM)
    return img.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    mark(192, rounded=True).save(OUT / "icon-192.png", optimize=True)
    mark(512, rounded=True).save(OUT / "icon-512.png", optimize=True)
    mark(512, rounded=False).save(OUT / "icon-maskable-512.png", optimize=True)
    mark(180, rounded=False).convert("RGB").save(OUT / "apple-touch-icon.png", optimize=True)
    for p in sorted(OUT.iterdir()):
        print(p.name, Image.open(p).size, p.stat().st_size)
