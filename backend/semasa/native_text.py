"""Deterministic heading-only adaptations. Never infer copy or edit source footage.

Operate on an existing authored heading, preserving its placement, palette and language.
This deliberately does not implement the catalog's subject/footage/background edits.
"""

import re

from bs4 import BeautifulSoup
from bs4.element import NavigableString

NATIVE_IDS = {"H01", "H03", "V01", "V03"}
DURATIONS = {"H01": 1.8, "H03": 2.4, "V01": 1.6, "V03": 1.5}


def inject(document: str, report: dict, scenes: list[dict], total: float) -> str:
    if not any(e["id"] in NATIVE_IDS for e in report["effects"]):
        return document
    soup = BeautifulSoup(document, "html.parser")
    if soup.body is None:
        raise ValueError("No body for native text effects")
    commands = []
    occupied = []
    for effect in report["effects"]:
        code = effect["id"]
        if code not in NATIVE_IDS:
            continue
        effect.pop("cue", None)
        effect.update(readiness="fallback", reason="No eligible non-overlapping authored heading; native text effect skipped.")
        for index, scene in enumerate(scenes):
            if scene.get("id") == "brand-outro" or (code.startswith("H") and index != 0):
                continue
            heading = str(scene.get("heading") or "").strip()
            limit = {"H01": 5, "H03": 12, "V01": 4, "V03": 3}[code]
            if not heading or len(heading.split()) > limit or (code == "H03" and not heading.endswith("?")):
                continue
            start = float(scene.get("start", 0))
            duration = min(DURATIONS[code], float(scene["duration"]), total - start)
            if duration < 0.7 or any(start < b and start + duration > a for a, b in occupied):
                continue
            scope = soup.find(id=scene.get("id")) if scene.get("id") else None
            candidates = [t for t in (scope or soup).select("h1,h2,h3")
                          if t.get_text(" ", strip=True) == heading and not t.select("[data-native-effect]")]
            if len(candidates) != 1:
                continue
            target = candidates[0]
            ident = f"native-{code}"
            span = soup.new_tag(
                "span",
                id=ident,
                attrs={"data-native-effect": code, "style": "display:inline-block;max-width:100%;transform-origin:center;"},
            )
            for child in list(target.contents):
                span.append(child.extract())
            target.append(span)
            selector = f'"#{ident}"'
            enter = min(0.43, duration * 0.3)
            if code == "H01":
                commands.append(
                    f'tl.fromTo({selector},{{scale:2.2,opacity:0}},{{scale:1,opacity:1,duration:{enter:g},ease:"back.out(1.3)"}},{start:g});'
                )
            elif code == "H03":
                # Visual word stagger only: NOT spoken word alignment or karaoke timing.
                for node in list(span.descendants):
                    if not isinstance(node, NavigableString):
                        continue
                    for token in re.findall(r"\s+|\S+", str(node)):
                        if token.isspace():
                            node.insert_before(token)
                        else:
                            part = soup.new_tag("span", attrs={"class": "native-word", "style": "display:inline-block;"})
                            part.string = token
                            node.insert_before(part)
                    node.extract()
                stagger = min(0.09, duration * 0.25 / max(1, len(heading.split()) - 1))
                commands.append(
                    f'tl.fromTo("#{ident} .native-word",{{yPercent:40,opacity:0}},'
                    f'{{yPercent:0,opacity:1,stagger:{stagger:g},duration:{enter:g},ease:"expo.out"}},{start:g});'
                )
            elif code == "V01":
                # Mask only this heading; never move the surrounding composition.
                mask = soup.new_tag("span", attrs={"style": "display:block;overflow:hidden;"})
                span.wrap(mask)
                commands.append(
                    f'tl.fromTo({selector},{{yPercent:110}},{{yPercent:0,duration:{enter:g},ease:"expo.out"}},{start:g});'
                )
            else:
                span["style"] += "box-sizing:border-box;border:.04em solid currentColor;border-radius:.08em;padding:.12em;"
                commands.append(
                    f'tl.fromTo({selector},{{scale:.9,opacity:0}},{{scale:1,opacity:1,duration:{enter:g},ease:"expo.out"}},{start:g});'
                )
            # the heading STAYS after its entrance: it used to fade out at the end of the cue, and a silent film lost its
            # heading two seconds into a scene that was meant to be read (run 40, 26 Oct 2026)
            effect.update(
                readiness="ready",
                adapter="native-text",
                asset=None,
                reason=("Native heading-only adaptation; preserves authored copy/design. "
                        "No source-footage, matte, blur or word-sync editing."),
                cue={"start": start, "duration": duration, "scene_id": scene.get("id")},
            )
            occupied.append((start, start + duration))
            break
    if commands:
        script = soup.new_tag("script")
        script.string = '{const tl=window.__timelines["main"];' + "".join(commands) + "tl.seek(0);}"
        soup.body.append(script)
    return str(soup)
