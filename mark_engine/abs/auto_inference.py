"""Build inference lines from the shared OCR and symbol-detector outputs."""
from mark_engine.abs.layout import layout_lines
from mark_engine.abs.symbols_to_lines import assign_graphics
from mark_engine.domain.models import InferenceResult, LayoutLine, Side


def build_auto_inference(elr_no, img_stem, items, detections, reocr):
    lines = layout_lines(items)
    graphics = assign_graphics(lines, detections)
    by_key = {}
    for side, number, text, score, _ in lines:
        reread = reocr.get(f'{img_stem}|{side.value}|{number}')
        if reread and text.strip() == reread[0]:
            text = reread[1]
        by_key[(side, number)] = (text, score)
    keys = sorted(set(by_key) | set(graphics), key=lambda k: (0 if k[0] == Side.TOP else 1, k[1]))
    result = tuple(LayoutLine(side=side, line_no=number,
                              text=by_key.get((side, number), ('', None))[0],
                              graphics=graphics.get((side, number), ''),
                              score=by_key.get((side, number), ('', None))[1])
                   for side, number in keys)
    return InferenceResult(elr_no=elr_no, lines=result, layout_source='auto')
