"""Extract the Brand/Marking page using the R0 image selection rule."""
from pathlib import Path
import pymupdf


def extract_brand_image(pdf: Path) -> tuple[bytes, str, int]:
    with pymupdf.open(pdf) as doc:
        if not len(doc):
            raise ValueError(f'empty PDF: {pdf}')
        pages = [page.number for page in doc if 'Brand/Marking' in page.get_text()]
        page = doc[pages[-1] if pages else len(doc) - 1]
        best = None
        for image in page.get_images(full=True):
            try:
                record = doc.extract_image(image[0])
            except (RuntimeError, ValueError):
                continue
            width, height = record['width'], record['height']
            if width / max(height, 1) > 2.5 or height / max(width, 1) > 2.5 or width * height < 150 * 150:
                continue
            if best is None or width * height > best[1]['width'] * best[1]['height']:
                best = (image[0], record)
        if best is None:
            return page.get_pixmap(dpi=200).tobytes('png'), 'render200', page.number + 1
        xref, record = best
        if record['ext'] == 'png':
            return record['image'], 'raster', page.number + 1
        pixmap = pymupdf.Pixmap(doc, xref)
        if pixmap.n - pixmap.alpha >= 4:
            pixmap = pymupdf.Pixmap(pymupdf.csRGB, pixmap)
        return pixmap.tobytes('png'), 'raster', page.number + 1
