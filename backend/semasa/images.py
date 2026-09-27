"""Opening an uploaded picture the right way up.

A phone photo is usually stored sideways with an EXIF Orientation tag that says how to turn it; a browser obeys the tag,
Pillow does not. So a bottle photographed upright on a phone was cut out lying on its side (a 601x101 cut-out from a
portrait photo, measured). Every picture a person uploads is opened through here."""

from __future__ import annotations

import io

from PIL import Image, ImageOps


def open_upright(data: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(data))
    img.load()
    try:
        return ImageOps.exif_transpose(img) or img
    except Exception:  # noqa: BLE001 - a broken EXIF block must not lose the picture: use it as stored
        return img
