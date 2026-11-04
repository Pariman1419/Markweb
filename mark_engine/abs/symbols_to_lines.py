from collections import defaultdict
from collections.abc import Sequence
from typing import Any

from mark_engine.domain.models import Side

TOKEN_MAP: dict[str, str] = {
    "pin1_dot": "@",
    "adi_partial_logo": "%",
    "adi_full_logo": "{",
}


def line_model(rows: Sequence[tuple[int, float, float, float, float]]) -> tuple[float, float]:
    """Least-squares y = a + b*idx over the crops of one side (b from spacing if 1 crop)."""
    idx = [r[0] for r in rows]
    yc = [(r[2] + r[4]) / 2 for r in rows]
    if len(rows) >= 2 and len(set(idx)) >= 2:
        n = len(idx)
        mx = sum(idx) / n
        my = sum(yc) / n
        denom = sum((i - mx) ** 2 for i in idx)
        if denom > 0:
            b = sum((i - mx) * (y - my) for i, y in zip(idx, yc)) / denom
            return my - b * mx, b
    h = rows[0][4] - rows[0][2]
    return yc[0] - 2.2 * h * idx[0], 2.2 * h


def assign_graphics(
    lines: Sequence[Any],
    detections: Sequence[tuple[str, float, float, float, float, float]],
    conf_min: float = 0.5,
) -> dict[tuple[Side, int], str]:
    """Assigns detected marking graphics to brand lines and encodes as DB symbol tokens.

    Non-legacy behavior: line 0 = side-level graphic, not returned in result.
    """
    crops: dict[Side, list[tuple[int, float, float, float, float]]] = {}
    for item in lines:
        if isinstance(item, tuple):
            s, n = item[0], item[1]
            bb = item[4] if len(item) > 4 else getattr(item, "bbox", None)
        else:
            s, n = item.side, item.line_no
            bb = getattr(item, "bbox", None)

        if bb is not None:
            crops.setdefault(s, []).append((n, float(bb[0]), float(bb[1]), float(bb[2]), float(bb[3])))

    if not crops:
        return {}

    valid_dets = [
        (d[0], d[2], d[3], d[4], d[5])
        for d in detections
        if d[1] >= conf_min and d[0] in TOKEN_MAP
    ]
    if not valid_dets:
        return {}

    models = {
        s: (line_model(r), min(x[1] for x in r), max(x[3] for x in r), max(x[0] for x in r))
        for s, r in crops.items()
    }

    per: dict[tuple[Side, int], list[tuple[float, str]]] = defaultdict(list)
    for cls, x0, y0, x1, y1 in valid_dets:
        cx = (x0 + x1) / 2
        cy = y0 + 0.25 * (y1 - y0)

        def gap(c: tuple[int, float, float, float, float]) -> float:
            dx = max(c[1] - cx, 0.0, cx - c[3])
            dy = max(c[2] - cy, 0.0, cy - c[4])
            return (dx * dx + dy * dy) ** 0.5

        s = min(crops, key=lambda k: min(gap(c) for c in crops[k]))
        (a, b), lx0, lx1, nmax = models[s]
        k = round((cy - a) / b) if b > 0 else 1

        if k < -1 or not (lx0 - max(0.6 * (lx1 - lx0), 4 * b) <= cx <= lx1 + max(0.3 * (lx1 - lx0), 2 * b)):
            continue
        elif k < 1:
            k = 1
        elif k > nmax:
            k = 0

        if k >= 1:
            per[(s, k)].append((cx, TOKEN_MAP[cls]))

    out: dict[tuple[Side, int], str] = {}
    for (s, k), toks in sorted(per.items()):
        out[(s, k)] = "".join(t for _, t in sorted(toks))
    return out
