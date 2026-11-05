"""Candidate generation and logo trimming for re-OCR on mark legends."""
from pathlib import Path
import re

LEGEND = re.compile(r"^\s*(?:L|LINE)\s*([1-9])\s*:\s*(\S.*)$", re.I)


def legend_candidates(name: str, items: list) -> list[dict]:
    """Identify legend line candidates (e.g., 'LINE 1: ...') from OCR boxes.

    Returns dicts with 'key', 'old', 'box' (int tuple), and 'method'.
    """
    rows = []
    for x0, y0, x1, y1, text, _ in items:
        match = LEGEND.match(text)
        if match:
            cut = x0 + (x1 - x0) * (text.index(":") + 1) / len(text)
            rows.append({
                "key": f"{Path(name).stem}|TOP|{match.group(1)}",
                "old": match.group(2).strip(),
                "box": (int(cut) + 2, int(y0) - 2, int(x1) + 6, int(y1) + 2),
                "method": "legend_value",
            })
    return rows


def trim_logo(image):
    """Detect and trim a dark logo prefix on the left of an image strip.

    Returns the cropped PIL Image or None if no valid logo was detected.
    """
    import numpy as np

    darkness = (np.asarray(image.convert("L")) < 100).mean(axis=0)
    width, height = image.size
    xs = np.where(darkness > 0.5)[0]
    if not len(xs) or xs[0] > 0.25 * width:
        return None
    x = int(xs[0])
    while x < width and not (darkness[x:x + 4] < 0.02).all():
        x += 1
    if x - xs[0] < 0.5 * height or x > 0.6 * width or darkness[xs[0]:x].max() < 0.9:
        return None
    return image.crop((min(width - 1, x + max(3, height // 8)), 0, width, height))
