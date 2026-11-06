"""Extract the Brand/Marking page using the R0 image selection rule."""
import hashlib
from pathlib import Path
import pymupdf


def extract_brand_image(pdf: Path | bytes) -> tuple[bytes, str, int]:
    with (pymupdf.open(stream=pdf, filetype="pdf") if isinstance(pdf, bytes) else pymupdf.open(pdf)) as doc:
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


def extract_marking_image(
    abs_path: Path,
    dest_dir: Path,
    expected_source_sha256: str | None = None,
) -> tuple[Path, str]:
    """Extract marking page image from ABS document.

    Returns (image_file_path, sha256_digest).
    Image is saved as <dest_dir>/<sha256>.png.
    """
    if expected_source_sha256 is not None:
        source_digest = hashlib.sha256(abs_path.read_bytes()).hexdigest()
        if source_digest != expected_source_sha256:
            raise ValueError("ABS changed during image extraction")
    data, method, page = extract_brand_image(abs_path)
    digest = hashlib.sha256(data).hexdigest()
    dest_dir.mkdir(parents=True, exist_ok=True)
    image_path = dest_dir / f"{digest}.png"
    if not image_path.exists():
        image_path.write_bytes(data)
    elif hashlib.sha256(image_path.read_bytes()).hexdigest() != digest:
        raise RuntimeError(f"Image hash mismatch: {image_path}")
    return image_path, digest

