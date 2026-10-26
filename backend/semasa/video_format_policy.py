"""Versioned shared format contract. Normalize legacy rows on every retry, never hide choices."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

POLICY = json.loads((Path(__file__).resolve().parents[2] / 'rules/motion/video-format-policy.json').read_text())
FORMATS = {f['id']: f for f in POLICY['formats']}


def normalize(row: dict[str, Any]) -> dict[str, Any]:
    options = dict(row.get('options') or {})
    if row.get('voice') == 'clone' or options.get('voice_clone'):
        raise ValueError('Voice clone unconfigured: consent does not configure a provider; never default to cloning')
    if options.get('talking_avatar'):
        raise ValueError('Talking avatar unconfigured / experimental: actual SadTalker smoke must pass first')
    if options.get('source_footage'):
        raise ValueError('Source-footage editing unsupported here: preserve original audio/pacing; '
                         'do not replace with generated TTS')
    fmt = options.get('format')
    if fmt not in FORMATS:
        fmt = ('gimmick' if options.get('mode') == 'teaser' else 'silent-first' if row.get('voice') == 'off'
               else 'malay-voiced' if row.get('language') in {'bm', 'both'} else POLICY['default_format'])
    if row.get('stream') == 'linkedin' and fmt == 'malay-voiced':
        fmt = 'english-voiced'
    if row.get('voice') == 'off' and fmt != 'gimmick':
        fmt = 'silent-first'
    spec = FORMATS[fmt]
    language = spec.get('language', row.get('language') or 'en')
    if fmt == 'malay-voiced' and row.get('language') == 'both':
        language = 'both'
    if language not in {'en', 'bm', 'both'}:
        language = 'en'
    personal = row.get('stream') == 'linkedin'
    if personal:
        language = 'en'
    voice = row.get('voice')
    if voice not in {'male', 'female', 'kitten'} and not (isinstance(voice, str) and voice.endswith('Neural')):
        voice = spec.get('voice', 'male')
    if language != 'en' and voice == 'kitten':
        voice = 'male'
    if fmt == 'silent-first':
        voice = 'off'
    if fmt == 'gimmick' and row.get('voice') == 'off':
        voice = 'off'
    try:
        value = float(row.get('seconds') or 30)
        seconds = 60 if math.isfinite(value) and value > 30 else 30
    except (ValueError, TypeError):
        seconds = 30
    if fmt == 'gimmick':
        seconds = 10
    resolution = row.get('resolution') if row.get('resolution') in {'portrait', 'square', 'landscape'} else 'portrait'
    options.update(format=fmt, mode=spec['mode'], policy_version=POLICY['version'],
                   mute_all=options.get('mute_all') is True,
                   brand_profile='linkedin-personal' if personal else 'ws-regulab')
    return {**row, 'language':language, 'voice':voice, 'seconds':seconds,
            'resolution':'portrait' if personal else resolution, 'options':options}


def prepare_brand(store: Any, row: dict[str, Any], folder: Path) -> dict[str, str]:
    """Private uploaded still only. Missing personal asset blocks rather than substituting a corporate logo."""
    if row.get('stream') != 'linkedin':
        return {'profile':'ws-regulab'}
    avatar = (row.get('options') or {}).get('personal_avatar') or {}
    path = avatar.get('path') if isinstance(avatar, dict) else None
    if not path or not str(path).lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
        raise ValueError('LinkedIn personal avatar unconfigured: upload your own still avatar in Motion and save defaults')
    if '..' in str(path).split('/') or str(path).startswith('/'):
        raise ValueError('Invalid personal avatar storage path')
    from .motion_assets import BUCKET, MAX_BYTES, validate_ref
    validate_ref(avatar, str(row.get('created_by') or ''))
    data = store.storage.from_(BUCKET).download(path)
    if len(data) != int(avatar['size']) or len(data) > MAX_BYTES:
        raise ValueError('Personal avatar size differs from its private asset metadata')
    # Validate a real decodable image, not SVG/HTML disguised as a still.
    from io import BytesIO

    from PIL import Image
    image = Image.open(BytesIO(data))
    image.verify()
    target = folder / 'assets/personal-avatar.png'
    target.parent.mkdir(parents=True, exist_ok=True)
    Image.open(BytesIO(data)).convert('RGBA').save(target)
    return {'profile':'linkedin-personal', 'avatar':'assets/personal-avatar.png'}


def prompt(row: dict[str, Any]) -> str:
    r = normalize(row)
    spec = FORMATS[r['options']['format']]
    return (f"\nSELECTED FORMAT: {spec['id']} ({spec['name']}). Language {r['language']}; voice {r['voice']}; "
            f"{r['seconds']} seconds INCLUDING ending. Master {POLICY['master']}; preview {POLICY['preview']}. "
            "These resolved values override legacy mode, language and custom prompt conflicts. "
            "Frame one: strong truthful hook. No source-labels on screen unless legally required. "
            "Protect faces; torso overlays allowed. Never full-screen dark cutaways over uploaded footage. "
            "Source footage editing preserves original audio and pacing; no silent TTS replacement or cloning. "
            "No LabelLiteracy, recurring WS header or page counters. No invented credentials. "
            "Stock is illustrative, never imply that a stock product was tested. "
            "Voiced captions: transparent, clean 2–4 words only with actual word timings; otherwise phrase captions, "
            "honestly estimated timing, never fabricated word timestamps. "
            + ("Personal LinkedIn: avatar replaces WS logo; exact name Ts. ChM. Muhammad below it. "
               "English voice and text, portrait 9:16, visible/spoken Follow me for more. "
               if r.get('stream') == 'linkedin' else '')
            + ('Silent-first: write a complete connected casual reading narrative, NOT narration muted; '
               'no narration even on outro. '
               if r['voice'] == 'off' else ''))
