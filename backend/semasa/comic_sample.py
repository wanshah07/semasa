"""Wan's comic comparison, run by hand (16 Nov 2026: "Try both and compare"): the same four-panel comic drawn four times,
by ChatGPT and by Gemini, each once with the picture maker writing the words and once with Semasa printing them.

  python -m semasa.comic_sample [out_dir]

Every picture is tried on its own, so one maker being off does not hide the other. Each finished poster is saved in out_dir
and in the `semasa-generated` bucket under samples/comic/, and its address is printed on a RESULT line. Nothing else is
written: no idea, no post, no media row. The sample's words are for looking at the lettering only and are not a post.
"""

from __future__ import annotations

import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import chatgpt_login, comic, db, gemini_images

log = logging.getLogger("semasa.comic_sample")

# One topic for all four pictures. It carries a manual's name, a year and a clause number on purpose: those are what an image
# model is most likely to get wrong, and what a regulatory comic can least afford to. The rule quoted is MPPHM (Domestik) 2020,
# Klausa 40(2): "Pemegang SPHM hendaklah dibenarkan mencetak warna logo Halal Malaysia mengikut kesesuaian selagi mana tidak
# mengubah spesifikasi logo Halal Malaysia."
SCRIPT: dict[str, Any] = {
    "title": "Logo halal bukan hijau. Palsu ke?",
    "source": "Sumber: MPPHM (Domestik) 2020, Klausa 40(2)",
    "setting": "a small Malaysian grocery shop, a low shelf of packaged food behind the two people, a plain wall above it",
    "cast": {
        "A": "a young Malaysian woman shopper wearing a pastel pink tudung and a cream blouse, holding a snack packet that has "
             "a small plain black round emblem on it (the emblem has no lettering)",
        "B": "a Malaysian man in his thirties, a halal consultant, short black hair, glasses, navy polo shirt, holding a "
             "clipboard",
    },
    "panels": [
        {"scene": "A looks closely at the snack packet in her hand, puzzled. B stands beside her, listening.",
         "lines": [{"who": "A", "text": "Eh, logo halal kat paket ni warna hitam. Bukan sepatutnya hijau ke?"}]},
        {"scene": "A holds the packet up to B, worried. B smiles calmly and raises one hand.",
         "lines": [{"who": "A", "text": "Jangan-jangan logo palsu?"},
                   {"who": "B", "text": "Tak semestinya. Warna bukan penentu."}]},
        {"scene": "B points at the logo on the packet and explains. A listens with interest.",
         "lines": [{"who": "B", "text": "Pemegang sijil boleh cetak logo ikut warna pembungkusan, asalkan spesifikasi "
                                        "logo tak diubah."}]},
        {"scene": "A looks relieved and curious. B shows her the clipboard.",
         "lines": [{"who": "A", "text": "Mana tulis tu?"},
                   {"who": "B", "text": "MPPHM (Domestik) 2020, Klausa 40(2)."}]},
    ],
}

MODES = ("full", "art")


def make(draw: Any, mode: str, script: dict[str, Any]) -> bytes:
    """One finished poster. `draw(prompt) -> bytes` is the picture maker."""
    if mode == "full":
        return comic.frame(draw(comic.prompt_full(script)), script)
    return comic.frame(comic.letter(draw(comic.prompt_art(script)), script), script)


def run(makers: dict[str, Any], script: dict[str, Any], save: Any) -> list[dict[str, Any]]:
    """[{maker, mode, ok, detail}] for every maker and mode. `makers` maps a name to its draw function, or to a string saying
    why that maker cannot be used; `save(name, data) -> address`."""
    out = []
    for maker, draw in makers.items():
        for mode in MODES:
            if isinstance(draw, str):
                out.append({"maker": maker, "mode": mode, "ok": False, "detail": draw})
                continue
            try:
                detail = save(f"{maker}-{mode}", make(draw, mode, script))
                ok = True
            except Exception as exc:  # noqa: BLE001 - report this picture, then carry on to the next
                ok, detail = False, f"{type(exc).__name__}: {str(exc)[:300]}"
            out.append({"maker": maker, "mode": mode, "ok": ok, "detail": detail})
            log.info("%s %s: %s %s", maker, mode, "OK" if ok else "FAILED", detail)
    return out


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    store = db.client()
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M")
    login, gemini = chatgpt_login.Login(store), gemini_images.Drawer(store)
    makers: dict[str, Any] = {
        "chatgpt": (lambda p: login.draw(p, size="1024x1024")) if login.connected() else "ChatGPT is not connected",
        "gemini": (lambda p: gemini.draw(p, resolution="square")) if gemini.ready()
        else "Gemini pictures are off or no key is usable",
    }

    def save(name: str, data: bytes) -> str:
        if out_dir:
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / f"{name}.jpg").write_bytes(data)
        return db.upload_generated(store, f"samples/comic/{stamp}-{name}.jpg", data, "image/jpeg")

    results = run(makers, comic.check(SCRIPT), save)
    for r in results:
        print(f"RESULT {r['maker']} {r['mode']}={'OK' if r['ok'] else 'FAILED'} · {r['detail']}")
    return 0 if any(r["ok"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
