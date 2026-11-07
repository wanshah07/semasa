"""Motion's scene pictures from Gemini (Wan, 6 Nov 2026: "add gemini api key I can add multiple and its auto select same like
chatgpt"). One picture per call to Gemini's native `generateContent` with an image model, using whichever of Wan's keys
gemini_keys.py picks; a key that is rate-limited or refused is marked and the next one is tried, up to three in one picture.

Used by motion_gpt_images.py after ChatGPT (or alone when ChatGPT is not connected): a scene whose picture cannot be
drawn keeps its Unsplash photo, so nothing here may stop a film. Every failure is a GeminiError the caller turns into a
note, and `limit` says the keys are all spent or all refused, so the rest of that film stops asking.

The request shape follows Google's published API (`x-goog-api-key`, `generationConfig.responseModalities`,
`imageConfig.aspectRatio`) and was written without a key to try it on: the first real film is the proof. It steps down on a
400 (without the aspect ratio, then text-and-image), and on a 404 it looks for an image model in the key's own model list and
uses that for the rest of the run.
"""

from __future__ import annotations

import base64
import time
from datetime import UTC, datetime
from typing import Any

import requests

from . import gemini_keys
from .log import get_logger

log = get_logger("semasa.gemini_images")

ASPECT = {"portrait": "9:16", "landscape": "16:9", "square": "1:1"}
MIN_BYTES = 2000


class GeminiError(RuntimeError):
    """A picture Gemini did not give. `limit`: every usable key is spent or refused (stop asking for this film)."""

    def __init__(self, message: str, *, limit: bool = False):
        super().__init__(message)
        self.limit = limit


class _KeyFail(Exception):
    """This key could not do it (the text says why); the next key may."""

    def __init__(self, text: str):
        super().__init__(text)
        self.text = text


def _clip(text: Any, n: int = 240) -> str:
    return " ".join(str(text or "").split())[:n]


def _body(prompt: str, aspect: str, variant: int) -> dict[str, Any]:
    gen: dict[str, Any] = {"responseModalities": ["IMAGE"] if variant == 0 else ["TEXT", "IMAGE"]}
    if variant == 0:
        gen["imageConfig"] = {"aspectRatio": aspect}
    return {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": gen}


def picture_of(data: Any) -> bytes:
    """The first inline picture in a generateContent answer. Raises GeminiError (no key is blamed) when the model answered with
    words only or declined: a blocked prompt is the prompt's fault, not the key's."""
    if not isinstance(data, dict):
        raise GeminiError("Gemini's answer was not readable")
    for cand in data.get("candidates") or []:
        for part in ((cand.get("content") or {}).get("parts") or []):
            blob = part.get("inlineData") or part.get("inline_data") or {}
            if blob.get("data"):
                try:
                    raw = base64.b64decode(blob["data"], validate=False)
                except ValueError as exc:
                    raise GeminiError("the picture Gemini sent could not be decoded") from exc
                if len(raw) < MIN_BYTES:
                    raise GeminiError("the picture Gemini sent was empty")
                return raw
    why = (data.get("promptFeedback") or {}).get("blockReason") or next(
        (c.get("finishReason") for c in data.get("candidates") or [] if c.get("finishReason") not in (None, "STOP")), "")
    said = " ".join(str(p.get("text") or "") for c in data.get("candidates") or []
                    for p in ((c.get("content") or {}).get("parts") or []))
    raise GeminiError("Gemini gave no picture" + (f" ({why})" if why else "") + (f": {_clip(said, 120)}" if said.strip() else ""))


class Drawer:
    """Draws pictures with Wan's Gemini keys. `http` is `requests` (a test passes its own); `sleep` is `time.sleep`."""

    def __init__(self, store: Any, *, http: Any = None, sleep: Any = None, now: Any = None):
        self.store = store
        self.http = http or requests
        self.sleep = sleep or time.sleep
        self.now = now or (lambda: datetime.now(UTC))
        self.settings = gemini_keys.load_settings(store)
        self.model = self.settings["image_model"]
        self.discovered = False

    def ready(self) -> bool:
        """Gemini may draw: switched on for pictures and at least one key that can be tried now."""
        return bool(self.settings["enabled"] and self.settings["images"]
                    and gemini_keys.usable(gemini_keys.keys(self.store), self.now()))

    def max_images(self) -> int:
        return int(self.settings["max_images"])

    def _find_model(self, key: str) -> str:
        """An image model in this key's own list, other than the one that was not found; "" when there is none."""
        try:
            r = self.http.get(f"{gemini_keys.NATIVE}/models", headers={"x-goog-api-key": key}, params={"pageSize": 200},
                              timeout=30)
            if r.status_code != 200:
                return ""
            for m in r.json().get("models") or []:
                name = str(m.get("name") or "").removeprefix("models/")
                if "image" in name and "generateContent" in (m.get("supportedGenerationMethods") or []) and name != self.model:
                    return name
        except (requests.RequestException, ValueError, AttributeError):
            return ""
        return ""

    def _call(self, key: str, prompt: str, aspect: str) -> bytes:
        variant, retried, looked = 0, False, False
        while True:
            try:
                r = self.http.post(f"{gemini_keys.NATIVE}/models/{self.model}:generateContent",
                                   headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                                   json=_body(prompt, aspect, variant), timeout=(20, 180))
            except requests.RequestException as exc:
                raise _KeyFail(f"could not reach Gemini: {_clip(exc, 120)}") from exc
            code, text = r.status_code, _clip(getattr(r, "text", ""))
            if code == 200:
                try:
                    return picture_of(r.json())
                except ValueError as exc:
                    raise GeminiError("Gemini's answer was not JSON") from exc
            if code == 404 and not looked:
                looked = True
                found = self._find_model(key)
                if found:
                    log.info("Gemini image model %s not found; using %s", self.model, found)
                    self.model, self.discovered = found, True
                    continue
            if code == 400 and gemini_keys.classify(f"{code} {text}") == "bad":
                raise _KeyFail(f"{code} {text}")
            if code == 400 and variant < 1:
                variant += 1
                continue
            if code in (500, 502, 503, 504) and not retried:
                retried = True
                self.sleep(3)
                continue
            if code in (401, 403, 429) or code >= 500:
                raise _KeyFail(f"{code} {text}")
            raise GeminiError(f"Gemini answered {code}: {text}")

    def draw(self, prompt: str, *, resolution: str = "portrait") -> bytes:
        """One picture's bytes. Tries the usable keys in turn (least recently used first); GeminiError when none gives one."""
        aspect = ASPECT.get(resolution, "1:1")
        if not (self.settings["enabled"] and self.settings["images"]):
            raise GeminiError("Gemini pictures are switched off", limit=True)
        rows = gemini_keys.usable(gemini_keys.keys(self.store), self.now())[:gemini_keys.TRIES]
        if not rows:
            raise GeminiError("no Gemini key can be used right now", limit=True)
        failures: list[str] = []
        for row in rows:
            try:
                data = self._call(row["api_key"], prompt, aspect)
            except _KeyFail as exc:
                gemini_keys.note(self.store, row, False, exc.text, self.now())
                failures.append(f"{row.get('label') or row.get('hint') or 'a key'}: {_clip(exc.text, 90)}")
                continue
            gemini_keys.note(self.store, row, True, now=self.now())
            return data
        raise GeminiError("every Gemini key failed (" + "; ".join(failures)[:260] + ")", limit=True)
