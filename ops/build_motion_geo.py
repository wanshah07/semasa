"""Builds rules/motion/geo.json, the outlines the Motion map style draws (Wan, 27 Oct 2026: "add map ... to make the motion video
interesting").

Source: Natural Earth 1:50m admin-0 countries, public domain (https://www.naturalearthdata.com/about/terms-of-use/). The file
is simplified so the whole world is a few hundred kilobytes: a country in South-East Asia keeps more detail than the rest,
because the map is most often drawn there. Only outer rings are kept, and islands under a minimum size are dropped.

    python ops/build_motion_geo.py path/to/ne_50m_admin_0_countries.geojson

Output shape: {"_about", "countries": {ISO3: {"name", "label": [lon, lat], "rings": [[[lon, lat], ...], ...]}}}.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "rules" / "motion" / "geo.json"
SEA = {"MYS", "IDN", "SGP", "THA", "VNM", "PHL", "BRN", "KHM", "LAO", "MMR", "TLS"}
FINE, COARSE = 0.02, 0.18          # degrees of simplification: South-East Asia, everywhere else
MIN_AREA_FINE, MIN_AREA_COARSE = 0.002, 0.6   # square degrees under which a ring is dropped


def area(ring: list[list[float]]) -> float:
    return abs(sum(ring[i][0] * ring[(i + 1) % len(ring)][1] - ring[(i + 1) % len(ring)][0] * ring[i][1]
                   for i in range(len(ring)))) / 2


def dp(points: list[list[float]], eps: float) -> list[list[float]]:
    """Douglas-Peucker, iterative. A closed ring is cut at the point farthest from its start first, since a chord from a point to
    itself measures nothing."""
    if len(points) < 3:
        return points
    if points[0] == points[-1]:
        far = max(range(1, len(points) - 1), key=lambda i: math.hypot(points[i][0] - points[0][0], points[i][1] - points[0][1]))
        return dp(points[:far + 1], eps)[:-1] + dp(points[far:], eps)
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        a, b = stack.pop()
        ax, ay, bx, by = *points[a], *points[b]
        dx, dy = bx - ax, by - ay
        norm = math.hypot(dx, dy) or 1e-12
        far, far_d = -1, 0.0
        for i in range(a + 1, b):
            d = abs(dy * points[i][0] - dx * points[i][1] + bx * ay - by * ax) / norm
            if d > far_d:
                far, far_d = i, d
        if far_d > eps:
            keep[far] = True
            stack += [(a, far), (far, b)]
    return [p for p, k in zip(points, keep, strict=True) if k]


def main(src: str) -> None:
    data = json.loads(Path(src).read_text(encoding="utf-8"))
    out = {}
    for f in data["features"]:
        p = f["properties"]
        iso = p.get("ADM0_A3") or p.get("ISO_A3")
        if not iso or iso in {"ATA", "-99"}:
            continue
        geom = f["geometry"]
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        eps, floor = (FINE, MIN_AREA_FINE) if iso in SEA else (COARSE, MIN_AREA_COARSE)
        rings = []
        for poly in polys:
            ring = poly[0]
            if area(ring) < floor:
                continue
            simple = dp(ring, eps)
            if len(simple) >= 4:
                rings.append([[round(x, 2), round(y, 2)] for x, y in simple])
        if not rings:                                    # a tiny state (Singapore, Brunei's islands) keeps its biggest ring
            ring = max((poly[0] for poly in polys), key=area)
            rings = [[[round(x, 3), round(y, 3)] for x, y in dp(ring, 0.004)]]
        out[iso] = {"name": p.get("NAME") or p.get("ADMIN"), "label": [round(p.get("LABEL_X", 0), 2), round(p.get("LABEL_Y", 0), 2)],
                    "rings": rings}
    doc = {"_about": "Natural Earth 1:50m admin-0 countries (public domain), simplified by ops/build_motion_geo.py. "
                     "Drawn by backend/semasa/motion_visuals.py.", "countries": out}
    OUT.write_text(json.dumps(doc, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    print(len(out), "countries,", OUT.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main(sys.argv[1])
