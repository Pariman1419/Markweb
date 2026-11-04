import re
import statistics
from collections import defaultdict
from collections.abc import Sequence

from mark_engine.domain.models import Side

LABEL = re.compile(r"^\s*(?:L|LINE)\s*([1-9])\s*$", re.I)
HEAD = re.compile(r"^\s*(TOP|BOTTOM|BACK)\s*(?:SIDE|MARK(?:ING)?)?\s*:?\s*$", re.I)
SKIP = re.compile(
    r"PIN\s*1|LEAD\s*\d|LEAD\s*N\b|NOTES?:|^\d\.\s|JEDEC|DESIGN GUIDE|SQUARE OR|RECTANG|RETANG|"
    r"JUSTIFIED|BODY MAY|REFERENCE|MARK PIN",
    re.I,
)
LEGEND = re.compile(r"^\s*(?:L|LINE)\s*([1-9])\s*:\s*(.*)$", re.I)


def layout_lines(
    items: Sequence[tuple[float, float, float, float, str, float]],
) -> list[tuple[Side, int, str, float | None, tuple[float, float, float, float] | None]]:
    """Port of legacy build_h1.py line layout (without REOCR overrides or LEGACY branches).

    Items are (x0, y0, x1, y1, text, score).
    Returns list of (Side, line_no, text, score, bbox).
    """
    out: list[tuple[Side, int, str, float | None, tuple[float, float, float, float] | None]] = []

    # 1. Legend layout: when image has >= 2 legend rows matching LEGEND
    leg = [
        (int(m.group(1)), m.group(2).strip(), x0, y0, x1, y1)
        for x0, y0, x1, y1, t, s in items
        for m in [LEGEND.match(t)]
        if m
    ]
    if len({l[0] for l in leg}) >= 2:
        seen_lines: set[int] = set()
        for n, inline, x0, y0, x1, y1 in sorted(leg, key=lambda l: l[3]):
            if n in seen_lines:
                continue
            seen_lines.add(n)
            h, yc = y1 - y0, (y0 + y1) / 2
            right = sorted(
                (bx0, t, sc, (bx0, by0, bx1, by1))
                for bx0, by0, bx1, by1, t, sc in items
                if bx0 >= (x0 + x1) / 2
                and abs((by0 + by1) / 2 - yc) < 0.5 * h
                and bx0 - x1 < 4 * h
                and not LEGEND.match(t)
            )
            parts = ([inline] if inline else []) + [c[1] for c in right]
            boxes = [(x0, y0, x1, y1)] + [c[3] for c in right]
            text = " ".join(parts).strip()
            bb = (
                float(round(min(b[0] for b in boxes))),
                float(round(min(b[1] for b in boxes))),
                float(round(max(b[2] for b in boxes))),
                float(round(max(b[3] for b in boxes))),
            )
            score = round(min([c[2] for c in right] or [1.0]), 4)
            out.append((Side.TOP, n, text, score, bb))
        return sorted(out, key=lambda r: (0 if r[0] == Side.TOP else 1, r[1]))

    # 2. Standard label layout
    labels = [
        (int(LABEL.match(t).group(1)), x0, y0, x1, y1)
        for x0, y0, x1, y1, t, s in items
        if LABEL.match(t)
    ]
    heads = [
        (Side.TOP if t.strip().upper().startswith("TOP") else Side.BOTTOM, (x0 + x1) / 2, (y0 + y1) / 2)
        for x0, y0, x1, y1, t, s in items
        if HEAD.match(t)
    ]
    side_by_head = len({h[0] for h in heads}) == 2
    labels.sort(key=lambda l: ((l[2] + l[4]) / 2, l[1]))

    side: Side = Side.TOP
    prev = 0
    rows: list[tuple[Side, int, float, float, float, float]] = []

    for n, x0, y0, x1, y1 in labels:
        yc = (y0 + y1) / 2
        if side_by_head:
            above = [h for h in heads if h[2] < yc] or heads
            ymax = max(h[2] for h in above)
            near = [h for h in above if ymax - h[2] < 3 * (y1 - y0)]
            side = min(near, key=lambda h: abs(h[1] - (x0 + x1) / 2))[0]
        elif n <= prev and n == 1:
            side = Side.BOTTOM
        if any(r[0] == side and r[1] == n for r in rows):
            continue
        rows.append((side, n, x1, yc, y1 - y0, x0))
        prev = n

    by_side: dict[Side, list[tuple[Side, int, float, float, float, float]]] = defaultdict(list)
    for r in rows:
        by_side[r[0]].append(r)

    used: set[int] = set()
    for s, rs in by_side.items():
        ys = sorted(r[3] for r in rs)
        gap = statistics.median([b - a for a, b in zip(ys, ys[1:])]) if len(ys) > 1 else 2.5 * rs[0][4]

        def row_cands(lx1: float, yc: float, left: bool = False, lx0: float = 0.0):
            cand = []
            for i, (x0, y0, x1, y1, t, sc) in enumerate(items):
                if i in used or LABEL.match(t) or HEAD.match(t) or SKIP.search(t):
                    continue
                cy = (y0 + y1) / 2
                if not -0.6 * gap <= cy - yc <= 0.35 * gap:
                    continue
                if not left and x0 > lx1 - 2 and x0 - lx1 < 14 * gap:
                    cand.append((x0, i, t, sc, (x0, y0, x1, y1)))
                elif left and x1 < lx0 + 2 and lx0 - x1 < 14 * gap:
                    cand.append((x0, i, t, sc, (x0, y0, x1, y1)))
            return sorted(cand)

        left_mode = not any(row_cands(r[2], r[3]) for r in rs)
        for _, n, lx1, yc, h, lx0 in rs:
            cand = row_cands(lx1, yc, left_mode, lx0)
            if left_mode and cand:
                cand = [c for c in cand if c[0] - cand[0][0] < 3 * gap]

            chain = []
            for c in cand:
                if not chain:
                    if c[0] - lx1 > 6 * gap:
                        break
                    chain.append(c)
                elif c[4][0] - chain[-1][4][2] < 3 * (c[4][3] - c[4][1]):
                    chain.append(c)

            if chain:
                top = min(c[4][1] for c in chain)
                hmin = min(c[4][3] - c[4][1] for c in chain)
                chain.sort(key=lambda c: (c[4][1] > top + 0.6 * hmin, c[0]))

            cand = chain
            for c in cand:
                used.add(c[1])

            text = " ".join(c[2] for c in cand).strip()
            bb = (
                (
                    float(round(min(c[4][0] for c in cand))),
                    float(round(min(c[4][1] for c in cand))),
                    float(round(max(c[4][2] for c in cand))),
                    float(round(max(c[4][3] for c in cand))),
                )
                if cand
                else None
            )
            score = round(min(c[3] for c in cand), 4) if cand else None
            out.append((s, n, text, score, bb))

    return sorted(out, key=lambda r: (0 if r[0] == Side.TOP else 1, r[1]))
