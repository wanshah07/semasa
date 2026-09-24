"""Category and language, two ways.

`rules_category()` is a keyword rulebook in BM and EN. It is the FALLBACK, and rows
it decides carry `summary_source = "rules"` so nobody mistakes them for reviewed.
`llm_annotate()` asks the model for a summary, category and language for a batch
of headlines in one call and returns only the rows it could parse.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .llm import LLM

CATEGORIES: tuple[str, ...] = (
    "kosmetik", "halal", "makanan", "farmaseutikal", "kesihatan", "ekonomi", "politik",
    "jenayah", "sosial", "teknologi", "hiburan", "sukan", "pendidikan", "alam_sekitar", "lain",
)

# Order matters: the first family with a hit wins, so the regulated categories
# Wan works in come before the general ones.
_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("kosmetik", ("kosmetik", "cosmetic", "skincare", "penjagaan kulit", "pemutih", "whitening", "merkuri",
                  "mercury", "hidrokuinon", "hydroquinone", "npra", "notifikasi", "produk kecantikan",
                  "beauty product", "sunscreen", "pelindung matahari", "serum", "krim muka")),
    ("halal", ("halal", "jakim", "haram", "sijil halal", "logo halal", "sembelih", "babi", "pork",
               "syubhah", "fatwa", "bpjph")),
    ("farmaseutikal", ("ubat", "farmasi", "pharmac", "vaksin", "vaccine", "produk tidak berdaftar",
                       "unregistered product", "racun berjadual", "scheduled poison", "antibiotik", "dadah",
                       "drug", "suplemen", "supplement", "mal2", "mal1")),
    ("makanan", ("keracunan makanan", "food poisoning", "bkkm", "fsqd", "label makanan", "food label",
                 "makanan", "food", "minuman", "beverage", "restoran", "gerai", "kantin")),
    ("kesihatan", ("kkm", "moh", "hospital", "klinik", "clinic", "doktor", "doctor", "pesakit", "patient",
                   "wabak", "outbreak", "denggi", "dengue", "covid", "influenza", "mental", "kanser", "cancer",
                   "kesihatan", "health")),
    ("jenayah", ("polis", "police", "ditahan", "arrested", "dakwa", "charged", "mahkamah", "court",
                 "scam", "penipuan", "rasuah", "sprm", "macc", "bunuh", "murder", "rompak", "robbery",
                 "tikam", "maut", "kemalangan", "accident", "buli")),
    ("politik", ("menteri", "minister", "perdana menteri", "prime minister", "parlimen", "parliament",
                 "dun", "pilihan raya", "election", "prn", "pru", "umno", "pas", "dap", "pkr", "bersatu",
                 "perikatan", "pakatan", "kerajaan", "government", "exco", "menteri besar", "sultan", "agong",
                 "ros", "letak jawatan")),
    ("ekonomi", ("ekonomi", "economy", "ringgit", "bursa", "saham", "stock", "inflasi", "inflation", "cukai",
                 "tax", "sst", "gst", "subsidi", "subsidy", "harga", "price", "bank negara", "bnm", "gaji",
                 "salary", "pelaburan", "investment", "epf", "kwsp", "petrol", "ron95")),
    ("teknologi", ("teknologi", "technology", "ai ", "kecerdasan buatan", "data", "siber", "cyber",
                   "aplikasi", "app", "digital", "internet", "tiktok", "telco", "5g")),
    ("pendidikan", ("sekolah", "school", "pelajar", "student", "universiti", "university", "spm", "stpm",
                    "upu", "guru", "teacher", "kpm", "pendidikan", "education")),
    ("alam_sekitar", ("banjir", "flood", "jerebu", "haze", "gempa", "earthquake", "ribut", "storm", "cuaca",
                      "weather", "alam sekitar", "environment", "pencemaran", "pollution", "hutan", "forest")),
    ("sukan", ("sukan", "sport", "bola", "football", "badminton", "harimau malaya", "olimpik", "olympic",
               "sukan asia", "sea games", "perlawanan", "match", "atlet", "athlete")),
    ("hiburan", ("artis", "pelakon", "actor", "actress", "filem", "movie", "drama", "penyanyi", "singer",
                 "konsert", "concert", "hiburan", "entertainment", "selebriti", "celebrity", "viral")),
    ("sosial", ("masyarakat", "community", "netizen", "keluarga", "family", "agama", "religion", "masjid",
                "kebajikan", "welfare", "oku", "warga emas", "b40")),
)

_BM_STOP = {"yang", "dan", "untuk", "dengan", "kepada", "tidak", "dalam", "akan", "ini", "itu", "di", "ke",
            "daripada", "adalah", "kerana", "selepas", "berkata", "mahu", "jawatan"}
_EN_STOP = {"the", "and", "of", "to", "for", "with", "in", "on", "is", "are", "will", "after", "says", "over"}


def detect_lang(text: str, default: str = "ms") -> str:
    words = re.findall(r"[a-zA-Z']+", text.lower())
    if not words:
        return default
    bm = sum(w in _BM_STOP for w in words)
    en = sum(w in _EN_STOP for w in words)
    if bm == en:
        return default
    return "ms" if bm > en else "en"


def rules_category(text: str) -> str:
    hay = f" {text.lower()} "
    for category, needles in _RULES:
        for n in needles:
            if n in hay:
                return category
    return "lain"


_SYSTEM = (
    "You classify Malaysian news headlines for a regulatory-affairs team (cosmetics, halal, food, "
    "pharmaceuticals). For each item return a one- or two-sentence summary IN THE SAME LANGUAGE as the "
    "headline (Bahasa Malaysia — never Bahasa Indonesia — or English), a category from the list, and the "
    "language code. Do not invent facts that are not in the headline or snippet. "
    "Answer with JSON only: {\"items\": [{\"i\": <index>, \"summary\": \"…\", \"category\": \"…\", \"lang\": \"ms|en\"}]}.\n"
    f"Categories: {', '.join(CATEGORIES)}."
)


def llm_annotate(llm: LLM, batch: list[dict[str, Any]]) -> dict[int, dict[str, str]]:
    """batch: [{"i": idx, "title": …, "snippet": …, "source": …}]. Returns {idx: {summary, category, lang}}
    for the rows the model answered validly; anything malformed is simply absent."""
    if not batch:
        return {}
    user = "Items:\n" + "\n".join(
        json.dumps({"i": b["i"], "title": b["title"], "snippet": (b.get("snippet") or "")[:300],
                    "source": b.get("source") or ""}, ensure_ascii=False)
        for b in batch
    )
    out = llm.chat_json(_SYSTEM, user, max_tokens=220 * len(batch) + 100)
    if not out:
        return {}
    wanted = {b["i"] for b in batch}
    result: dict[int, dict[str, str]] = {}
    for row in out.get("items") or []:
        if not isinstance(row, dict):
            continue
        try:
            i = int(row.get("i"))
        except (TypeError, ValueError):
            continue
        cat = str(row.get("category") or "").strip().lower().replace(" ", "_")
        summary = str(row.get("summary") or "").strip()
        lang = str(row.get("lang") or "").strip().lower()
        if i not in wanted or cat not in CATEGORIES or not summary:
            continue
        result[i] = {"summary": summary[:600], "category": cat, "lang": lang if lang in ("ms", "en") else ""}
    return result
