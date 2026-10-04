"""A reference design read as a LAYOUT, as the Design tab's reader (supabase/functions/semasa-chat/design.js) returns it: a pale
lilac poster with a topic panel, a bold headline, three supporting lines, a picture area and a source line. Written by hand for
the tests; nothing of any third party's artwork or words is in it (the words are blank: the roles carry the structure)."""


def _text(role, x, y, w, h, size, font="sans", weight=400, upper=False, color="#1b2a3a", lh=1.25, spacing=0):
    return {"type": "text", "role": role, "x": x, "y": y, "w": w, "h": h, "text": "", "chars": 40, "lines": 2, "font": font,
            "weight": weight, "italic": False, "size": size, "color": color, "behind": "#e6dfec", "align": "left",
            "uppercase": upper, "letter_spacing": spacing, "line_height": lh, "shadow": False}


POSTER = {
    "background": {"color": "#e6dfec",
                   "gradient": {"angle": 160, "stops": [{"at": 0, "color": "#d9d1e2"}, {"at": 1, "color": "#f7f3f8"}]}},
    "palette": ["#1b2a3a", "#e0d4e6", "#f7f3f8"],
    "elements": [
        {"type": "photo", "x": 0.5, "y": 0.52, "w": 0.7, "h": 0.55, "shape": "ellipse", "description": "a pink glass sphere"},
        {"type": "rect", "x": 0.06, "y": 0.1, "w": 0.6, "h": 0.07, "fill": "#e0d4e6", "opacity": 1, "radius": 0.15,
         "stroke": None, "stroke_w": 0},
        {"type": "line", "x": 0.06, "y": 0.34, "w": 0.3, "h": 0, "stroke": "#1b2a3a", "stroke_w": 0.004, "opacity": 1},
        _text("eyebrow", 0.06, 0.04, 0.4, 0.025, 0.022, weight=700, upper=True, lh=1.1, spacing=0.1),
        _text("headline", 0.06, 0.19, 0.86, 0.14, 0.062, weight=800, upper=True, lh=1.08),
        _text("point", 0.06, 0.38, 0.5, 0.07, 0.034),
        _text("point", 0.06, 0.5, 0.5, 0.07, 0.034),
        _text("point", 0.06, 0.62, 0.5, 0.07, 0.034),
        _text("source", 0.06, 0.93, 0.6, 0.02, 0.017, font="mono", color="#5b5668", lh=1.2),
    ],
    "covers": [{"kind": "logo", "x": 0.7, "y": 0.03, "w": 0.24, "h": 0.04}],
}
