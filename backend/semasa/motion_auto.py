"""Automatic style choice for every motion video (Wan, 25 Oct 2026: "make sure every video apply 99 styles based on
suitability").

The 99 effects in rules/motion/style-effects.json come from video-editing guides: most of them edit footage of a speaker, a
screen recording or a real screenshot. Semasa's films have none of those (and must never invent proof), so every effect is
judged here, per film and per scene, and one of three things happens:

  * it is ASSIGNED to the scene it suits, with a one-line recipe the writer builds in HTML/CSS/GSAP (text, shapes, photos);
  * it is NATIVE: the worker animates the scene's own heading itself (H01, H03, V01, V03: native_text.py), or the mix does it
    (S05, S08, S10);
  * it is UNAVAILABLE for this film, with the reason (needs footage, a capture, a sound file, or would break a rule).

Nothing is claimed that did not happen: the row's check_report lists what was assigned, what is native and why each of the
rest was not used. The choice is deterministic for a given row (same row, same styles) and varies between rows.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from . import motion_concepts
from .motion_styles import EFFECT_LIBRARY

NAMES = {e["id"]: e["name"] for e in EFFECT_LIBRARY["effects"]}
ROLES = ("hook", "fact", "why", "solution")
LABELS = {"bm": ("HOOK", "FAKTA", "KENAPA", "SOLUSI"), "both": ("HOOK", "FAKTA", "KENAPA", "SOLUSI"),
          "en": ("HOOK", "FACT", "WHY", "SOLUTION")}

FOOTAGE = "needs a filmed speaker or source footage; Semasa films have none"
CAPTURE = "needs a real screenshot, screen capture or verified data; it would have to be invented"
SOUND = "needs a licensed sound-effect file; the library has none"
POLICY = "breaks a house rule (transparent captions, nothing over the text, or a clean brand look)"
HEAVY = "layers that can hide text; not used while no-overlap is enforced"
UNAVAILABLE = {
    # the styles that need footage or a capture are drawn as Wan's own "original qualitative concept diagram" (motion_concepts),
    # so none of them is skipped for that reason any more
    **dict.fromkeys([], FOOTAGE),
    **dict.fromkeys([], CAPTURE),
    **dict.fromkeys(["S01", "S02", "S03", "S04", "S06", "S07", "S09", "M05"], SOUND),
    **dict.fromkeys(["C08", "F08", "F09", "L08"], POLICY),
    **dict.fromkeys([], HEAVY),
}
NATIVE_AUDIO = {"S05": "the music drops to near-silence for a breath before the Solusi scene (voiced films)",
                "S08": "the music ducks under every spoken line (always on in the mix)",
                "S10": "the music resolves with a fade as the logo page lands (always on in the mix)"}

# id: (roles, needs, recipe). roles: h f w s or * ; needs (all must hold): p photo on the scene, n digits in the scene's words,
# l two or more lines, c a comparison, m a myth, q a question heading, b both languages, d two years in the script,
# V voiced only, S silent only. One recipe sentence each: HTML/CSS/GSAP, inside the scene's own box, never over text.
RECIPES: dict[str, tuple[str, str, str]] = {
    "H01": ("h", "", "headline lands with a scale overshoot (the worker does this itself)"),
    "H02": ("h", "", "open on a 3-frame inverted-colour flash, then settle on the headline"),
    "H03": ("h", "q", "the question builds word by word (the worker does this itself)"),
    "H05": ("h", "V", "a 3-2-1 countdown in huge numerals zooms into the first line"),
    "H06": ("h", "", "two halves of the headline panel slide together, then lock"),
    "H08": ("h", "", "a 0.15 s high-contrast flash, then ONE oversized keyword hits"),
    "H09": ("h", "m", "the common belief is struck through, the correct claim takes its place"),
    "H10": ("h", "S", "a calm 0.8 s pause with a thin rule, then the title in elegant type"),
    "C02": ("*", "V", "lines pop in one to three words at a time with a small overshoot"),
    "C03": ("*", "L", "short lines type on character by character with a blinking caret"),
    "C04": ("*", "W", "an accent block sweeps behind one key word per line"),
    "C05": ("*", "", "lines stack in two or three short rows that rise one after another"),
    "C06": ("*", "SL", "calm sentence-case lines under a thin accent rule, crossfading softly"),
    "C07": ("*", "VW", "one key word per scene bursts to several times its size, then settles"),
    "C09": ("*", "tL", "lines print word by word in a monospace block with a blinking cursor"),
    "C10": ("*", "bL", "the Malay line big, the English line smaller and in the second accent colour"),
    "L05": ("fws", "pl", "the text panel slides in beside the photo, the photo stays in its own frame"),
    "L06": ("hw", "p", "the photo contracts into a sharp central frame with a thin accent ring"),
    "P03": ("fws", "N", "the figures in the words count up from zero to the number printed (never one that is not in the words)"),
    "P08": ("fws", "D", "a timeline draws across and the years pop on, each with its own label"),
    "P09": ("fw", "E", "the publication the film rests on (journal, title, reference), or the quoted words, sit on a card"),
    "V01": ("fws", "", "a short chapter title rises out of a mask line (the worker does this itself)"),
    "V02": ("fws", "n", "the numbers in the words burst on one after another with a staggered pop"),
    "V03": ("fws", "", "one short heading is framed by a highlight outline (the worker does this itself)"),
    "V04": ("fs", "l", "list items slide in one by one with numbered markers; earlier ones dim"),
    "V05": ("w", "c", "two option cards fly in from opposite edges and settle side by side"),
    "V06": ("wsf", "l", "a progress track with labelled steps fills from one to the next"),
    "V08": ("fwh", "", "a small bold shape morphs between a square, a triangle and a diamond above the text"),
    "V09": ("fws", "%", "a bar chart draws each percentage written in the words, the bar as long as the figure says"),
    "V10": ("ws", "SL", "the sentence appears phrase by phrase in muted type, the last key words in full colour"),
    "B04": ("fws", "l", "an icon pops in for each step with connectors drawn between them"),
    "B05": ("hws", "p", "the photo drifts slowly in two layers (a slow pan and a slower zoom) for depth"),
    "B08": ("fw", "", "circles, grids and lines drift calmly behind the text to picture the idea"),
    "X06": ("h", "p", "the photo breaks into a grid of tiles that snap together into the whole picture"),
    "X10": ("fw", "", "a blueprint grid spreads behind the text and outlines trace in"),
    "M02": ("*", "", "scenes hand over with a fast directional streak"),
    "M03": ("hws", "p", "the photo creeps in by about 6 percent over the whole scene"),
    "M04": ("s", "V", "everything holds for 0.4 s with a soft flash and a small punch, then the answer lands"),
    "M07": ("h", "", "the first frame jolts with four decaying micro-offsets (hook only, never the text block)"),
    "M08": ("*", "", "a shared shape stays in place while the scene changes around it"),
    "M09": ("*", "", "a hard-edged mask sweeps across and reveals the next scene"),
    "F02": ("*", "", "photos warmed a few hundred Kelvin with cream highlights"),
    "F03": ("*", "", "photos neutral-to-cool with deeper blues"),
    "F05": ("*", "", "photos in black and white with a firm readable contrast"),
    "F06": ("*", "", "photos with strong saturation and a punchy accent"),
    "F07": ("*", "", "photos lifted into a soft pastel floor with lower contrast"),
    "F10": ("*", "", "photos with clean neutral whites and crisp micro-contrast"),
}
RECIPES.update(motion_concepts.RECIPES)
NATIVE_TEXT = {"H01", "H03", "V01", "V03"}
# the styles that make the film stop and look (Wan, 26 Oct 2026: "use the wow styles"): they are placed first
WOW = {"H02", "H05", "H06", "H08", "H10", "X05", "X06", "X08", "X10", "M04", "M07", "L06", "V08", "V09", "P03", "P08", "C07",
       "B04", "P04", "P05", "L04", "X03"}
CONCEPT = motion_concepts.CONCEPT_CODES
# the styles the worker's own layout (motion_layout.compose) builds, so a film that falls back to it still shows them; the chooser
# prefers these (Wan, 26 Oct 2026: "make sure the styles are included, not using layman safe layout only")
BUILDABLE = {"H02", "H05", "H06", "H08", "H10", "C02", "C03", "C04", "C05", "C06", "C07", "C09", "C10", "L05", "L06", "P03",
             "P08", "P09", "V02", "V04", "V05", "V06", "V08", "V09", "V10", "B04", "B05", "B08", "X06", "X10", "M02", "M03",
             "M04", "M07", "M08", "M09", "F02", "F03", "F05", "F06", "F07", "F10", *motion_concepts.CONCEPT_CODES}
# styles that take over the scene's lines: a scene gets at most one of them
LINE_STYLES = {"L05", "V05", "B04", "V09", "P08", *motion_concepts.MULTI_CODES}
PHOTO_STYLES = {"L05", "L06", "X06"}                 # how a scene treats its photo: one way each
FAMILY_LIMIT = {"H": 1, "M": 2, "L": 1, "F": 1, "C": 1, "X": 1}      # per scene; other families may take two
PER_SCENE = 8
MIN_STYLES = 15                      # Wan, 26 Oct 2026: "at least 15 styles from 99 styles apply to the motion video"
# and then "push to use as many styles from 99 as you can": every eligible style is added, up to PER_SCENE in a scene
CAPTION = ("C01", "C02", "C03", "C04", "C05", "C06", "C07", "C09", "C10")
TRANSITION = ("M02", "M08", "M09")
FINISH = ("F01", "F02", "F03", "F04", "F05", "F06", "F07", "F10")
FINISH_SCENE_BOOST = {"F05": r"\b(recall|ban|banned|warning|danger|cancel|tarik|larang|amaran|bahaya|palsu|fake)\b",
                      "F06": r"\b(tips?|easy|quick|mudah|cepat|launch|baru|new|promo)\b",
                      "F03": r"\b(tech|digital|data|ai|system|sistem|software|lab|science|sains)\b",
                      "F02": r"\b(halal|food|makanan|beauty|kosmetik|cosmetic|skin|kulit|family|keluarga)\b"}
COMPARE = re.compile(r"\b(vs|versus|berbanding|atau|bukan|but|however|whereas|sebaliknya|tetapi|beza|difference|myth|mitos)\b",
                     re.I)
MYTH = re.compile(r"\b(myth|mitos|salah faham|misconception|wrong|silap|bukan|not)\b", re.I)
STEPS = re.compile(r"\b(step|langkah|first|then|next|pertama|kedua|kemudian|seterusnya|finally|akhir)\b", re.I)
TECH = re.compile(r"\b(code|api|system|sistem|data|software|digital|ai|algorithm|database|pangkalan)\b", re.I)


def role_of(index: int) -> str:
    return ROLES[min(index, len(ROLES) - 1)]


def words_of(sc: dict[str, Any]) -> str:
    return " ".join([sc.get("kicker", ""), sc.get("heading", ""), *(sc.get("lines") or []), sc.get("narration", "")])


def _tiebreak(seed: str, code: str) -> int:
    return int(hashlib.sha1(f"{seed}:{code}".encode()).hexdigest()[:6], 16)


def _holds(needs: str, sc: dict[str, Any], ctx: dict[str, Any]) -> bool:
    text = words_of(sc)
    on_screen = " ".join([sc.get("heading", ""), *(sc.get("lines") or [])])
    for n in needs:
        ok = {
            "p": bool(sc.get("photo")),
            "n": bool(re.search(r"\d", on_screen)),
            "l": len(sc.get("lines") or []) >= 2,
            "c": bool(COMPARE.search(text) or COMPARE.search(ctx["brief"])),
            "m": bool(MYTH.search(text) or MYTH.search(ctx["brief"])),
            "q": on_screen.strip().endswith("?"),
            "b": ctx["lang"] == "both",
            "d": len(set(re.findall(r"\b(?:19|20)\d{2}\b", ctx["all_text"]))) >= 2,
            "D": len({y for ln in (sc.get("lines") or []) for y in re.findall(r"\b(?:19|20)\d{2}\b", ln)}) >= 2,
            "%": any(re.search(r"\d\s?%", ln) for ln in (sc.get("lines") or [])),
            "N": any(not re.fullmatch(r"(?:19|20)\d{2}", n) for n in re.findall(r"(?<![\d.,])\d{2,7}(?![\d.,])", on_screen)),
            "L": bool(sc.get("lines")),
            "T": bool(sc.get("words")),
            "W": len((sc.get("heading") or "").split()) >= 3,
            "E": bool(re.search(r"[“”\"]", on_screen)) or ctx["study"],
            "V": ctx["voiced"],
            "S": not ctx["voiced"],
            "Q": bool(re.search(r"[“”\"]", on_screen)),
            "t": bool(TECH.search(text) or TECH.search(ctx["brief"])),
        }[n]
        if not ok:
            return False
    return True


def assign_photos(scenes: list[dict[str, Any]], photos: list[dict[str, Any]]) -> None:
    """Hook, Kenapa and Solusi carry a photo when there are three; Hook and Solusi with two; the Hook alone with one. The
    Fakta scene stays words and shapes: it is the one most likely to carry a number or a rule, and a picture is no proof."""
    slots = {3: (0, 2, 3), 2: (0, 3), 1: (0,)}.get(min(len(photos), 3), ())
    for i, sc in enumerate(s for s in scenes if s.get("id") != "brand-outro"):
        sc.pop("photo", None)
        sc.pop("photo_credit", None)
        if i in slots:
            p = photos[slots.index(i)]
            sc["photo"], sc["photo_credit"] = p["path"], p.get("credit", "")


WARN = re.compile(r"\b(recall|banned?|warning|danger(?:ous)?|fake|counterfeit|seiz(?:ed|ure)|cancell?ed|prohibited|illegal|"
                  r"toxic|tarik balik|ditarik|larang|dilarang|amaran|bahaya|palsu|haram|batal|dibatalkan|rampas|racun)\b", re.I)
NEWS = re.compile(r"\b(new|latest|announc\w*|circular|notice|guideline|effective|takes effect|from \d{1,2} \w+|2026|"
                  r"baharu|terkini|umum\w*|pekeliling|notis|garis panduan|berkuat kuasa|mulai|kini)\b", re.I)


OPENING = (("know", re.compile(r"^\W*(tahukah anda|did you know)", re.I)), ("warn", re.compile(r"^\W*(amaran|warning)", re.I)),
           ("news", re.compile(r"^\W*(berita terkini|breaking news)", re.I)))


def hook_of(text: str, opening: str = "") -> str:
    """Which attention hook opens the film (Wan, 26 Oct 2026): the one the film's own first words already are ('Tahukah anda...',
    'Amaran: ...', 'Berita terkini: ...'); failing that, by the topic: a danger or a recall is a Warning, a new rule or notice is
    Breaking News, anything else is Did you know."""
    for kind, rx in OPENING:
        if rx.search(opening or ""):
            return kind
    return "warn" if WARN.search(text) else "news" if NEWS.search(text) else "know"


def study_of(row: dict[str, Any]) -> dict[str, str] | None:
    """The publication a film rests on, from what the idea carries and nothing else: the journal, the paper's title and a
    reference taken from its address. None when the source is not a paper (a news item is not drawn as a study)."""
    ev = (row.get("options") or {}).get("evidence") or {}
    url = str(ev.get("source_url") or row.get("source_url") or "")
    name = str(ev.get("source_name") or "")
    paper = re.search(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)|doi\.org/(10\.\S+)|ncbi\.nlm\.nih\.gov/pmc/articles/(PMC\d+)", url)
    if not paper and not name.lower().startswith(("pubmed", "pmc")):
        return None
    ref = ("PMID " + paper.group(1)) if paper and paper.group(1) else ("DOI " + paper.group(2)) if paper and paper.group(2) \
        else paper.group(3) if paper and paper.group(3) else ""
    journal = name.split("·", 1)[1].strip() if "·" in name else ("" if name.lower().startswith("pubmed") else name)
    title = str(ev.get("source_title") or "").strip()
    if not (journal or title or ref):
        return None
    source = "PubMed" if "pubmed" in url + name.lower() else ""
    return {"journal": journal[:90], "title": title[:160], "ref": ref[:60], "source": source}


def choose(row: dict[str, Any], scenes: list[dict[str, Any]], *, voiced: bool, lang: str,
           stream: str = "regulab") -> dict[str, Any]:
    """Assign effects to a film's teaching scenes. Returns {scenes: {id: [codes]}, video: {...}, assigned, native,
    unavailable, notes}. Needs scenes with kicker/heading/lines/narration (and photo, set by assign_photos)."""
    seed = str(row.get("id") or row.get("brief") or "x")
    teaching = [s for s in scenes if s.get("id") != "brand-outro"]
    ctx = {"brief": str(row.get("brief") or ""), "lang": lang, "voiced": voiced, "study": bool(study_of(row)),
           "all_text": " ".join(words_of(s) for s in teaching) + " " + str(row.get("brief") or "")}
    out: dict[str, list[str]] = {}
    used: set[str] = set()

    def ranked(role_letter: str, sc: dict[str, Any], pool: list[str] | None = None) -> list[str]:
        cands = []
        for code, (roles, needs, _how) in RECIPES.items():
            if pool is not None and code not in pool:
                continue
            if pool is None and (code in CAPTION or code in TRANSITION or code in FINISH):
                continue
            if roles != "*" and role_letter not in roles:
                continue
            if not _holds(needs, sc, ctx):
                continue
            score = (10 + (6 if needs else 0) + (3 if code in NATIVE_TEXT else 0) + (4 if code in BUILDABLE else 0)
                     + (5 if code in WOW else 0) - (2 if code in CONCEPT else 0))
            if code == "V03" and len((sc.get("heading") or "").split()) > 3:
                continue
            if code == "V01" and len((sc.get("heading") or "").split()) > 4:
                continue
            if code == "H01" and len((sc.get("heading") or "").split()) > 5:
                continue
            cands.append((-(score), _tiebreak(seed + sc.get("id", ""), code), code))
        return [c[2] for c in sorted(cands)]

    # film-wide looks, one per scene so a film shows several of them: a caption style per scene, a finish per scene, and a
    # different transition at each hand-over
    cap_by: dict[str, str] = {}
    fin_by: dict[str, str] = {}
    trans_by: dict[str, str] = {}
    boost = [(0 if re.search(rx, ctx["all_text"], re.I) else 1, _tiebreak(seed, c), c) for c, rx in FINISH_SCENE_BOOST.items()]
    for i, sc in enumerate(teaching):
        letter = "hfws"[min(i, 3)]
        for pool, bag in ((CAPTION, cap_by), (FINISH, fin_by), (TRANSITION, trans_by)):
            if (pool is TRANSITION and i == len(teaching) - 1) or (pool is FINISH and not sc.get("photo")):
                continue
            order = [c for c in ranked(letter, sc, list(pool)) if c not in bag.values()] or ranked(letter, sc, list(pool))
            if pool is FINISH and i == 0 and not all(b[0] for b in boost):
                order = [min(boost)[2], *order]
            if order:
                bag[sc["id"]] = order[0]
    first = teaching[0]["id"] if teaching else ""
    finish = next(iter(fin_by.values()), "F07")
    if stream == "linkedin" and finish == "F07":
        finish = "F10"
        if fin_by:
            fin_by[next(iter(fin_by))] = finish
    video = {"captions": cap_by.get(first) or "C05", "transition": trans_by.get(first) or "M09", "finish": finish}
    audio = ["S08", "S10"] + (["S05"] if voiced else [])
    used.update(cap_by.values())
    used.update(fin_by.values())
    used.update(trans_by.values())

    def room(sid: str, code: str) -> bool:
        """May this scene take `code`: under its cap, its family not full, and only one style that takes over its lines."""
        have = out[sid]
        if len(have) >= PER_SCENE or code in used:
            return False
        if sum(1 for c in have if c[0] == code[0]) >= FAMILY_LIMIT.get(code[0], 2):
            return False
        if code in LINE_STYLES and any(c in LINE_STYLES for c in have):
            return False
        if code in PHOTO_STYLES and any(c in PHOTO_STYLES for c in have):
            return False
        if code in motion_concepts.KIND and any(c in motion_concepts.KIND for c in have):
            return False                                 # one concept diagram a scene: each takes a block of the column
        if code in {"M01", "M06"} and any(c in {"M01", "M06", "L06", "X06"} for c in have):
            return False                                 # one movement of the photo
        if code == "V06" and any(c in {"L05", "V05"} for c in have):
            return False
        if code in {"L05", "V05"} and "V06" in have:
            return False
        if code == "V10" and cap_by.get(sid) in {"C03", "C09"}:
            return False                                 # typed lines are drawn letter by letter; a quiet statement cannot be
        return True

    for i, sc in enumerate(teaching):
        letter = "hfws"[min(i, 3)]
        out[sc["id"]] = [cap_by[sc["id"]], *([fin_by[sc["id"]]] if sc["id"] in fin_by else []),
                         *([trans_by[sc["id"]]] if sc["id"] in trans_by else [])]
        for code in ranked(letter, sc):
            if len(out[sc["id"]]) >= 7:
                break
            if room(sc["id"], code):
                out[sc["id"]].append(code)
                used.add(code)

    def count() -> int:
        return len({*(c for codes in out.values() for c in codes), *video.values(), *audio})

    # the floor, and then everything else that is eligible: Wan, 26 Oct 2026: "push to use as many styles from 99 styles as
    # you can". The next most suitable style goes to the scene it suits until nothing eligible is left or the cap is reached
    for _ in range(PER_SCENE * 4):
        added = False
        for i, sc in enumerate(teaching):
            spare = [c for c in ranked("hfws"[min(i, 3)], sc) if room(sc["id"], c)]
            if spare:
                out[sc["id"]].append(spare[0])
                used.add(spare[0])
                added = True
        if not added:
            break
    study = study_of(row)
    native = sorted({c for codes in out.values() for c in codes if c in NATIVE_TEXT})
    assigned = sorted({*(c for codes in out.values() for c in codes), *video.values()} - NATIVE_TEXT)
    applied = set(assigned) | set(native) | set(audio)
    unavailable = dict(UNAVAILABLE)
    unavailable.update({c: "not needed by this film's words, or it suits a different scene" for c in NAMES
                        if c not in applied and c not in unavailable})
    ev = (row.get("options") or {}).get("evidence") or {}
    return {"scenes": out, "video": video, "assigned": assigned, "native": native, "audio": audio, "study": study,
            "evidence_url": str(ev.get("source_url") or row.get("source_url") or ""),
            "hook": hook_of((str(row.get("brief") or "") + " " + (words_of(teaching[0]) if teaching else "")),
                            str((teaching[0].get("narration") or teaching[0].get("heading") or "") if teaching else "")),
            "concept": sorted(set(assigned) & CONCEPT),
            "unavailable": unavailable, "considered": len(NAMES), "applied": len(applied)}


def prompt_block(plan: dict[str, Any], scenes: list[dict[str, Any]]) -> str:
    """What the writer is told: per scene and for the whole film, which styles to build, one recipe each."""
    def line(code: str) -> str:
        return f"{code} {NAMES.get(code, '')}: {RECIPES[code][2]}"
    rows = []
    for sc in scenes:
        codes = [c for c in plan["scenes"].get(sc["id"], []) if c not in NATIVE_TEXT]
        if codes:
            rows.append(f"- {sc['id']} ({sc.get('role', '')}): " + "; ".join(line(c) for c in codes))
    v = plan["video"]
    rows.append("- WHOLE FILM: " + "; ".join(line(v[k]) for k in ("captions", "transition", "finish")))
    native = [c for c in plan["native"]]
    tail = (f"\nThe worker applies {', '.join(native)} to the headings itself: do not animate those headings a second time."
            if native else "")
    return ("STYLES CHOSEN FOR THIS FILM (picked for what each scene says; build each in HTML/CSS/GSAP inside the scene's own "
            "box, from the scene's own words and photos; reading time and a clean layout outrank every effect, so drop an "
            "effect rather than let it touch the words):\n" + "\n".join(rows) + tail)


def effect_rows(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """The native text effects as the asset plan wants them, so native_text.inject can apply them."""
    return [{"id": c, "readiness": "ready", "adapter": "native-text", "asset": None,
             "reason": "Chosen automatically for this film's heading."} for c in plan["native"]]
