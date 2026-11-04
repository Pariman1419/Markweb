from pathlib import Path
from typing import Sequence
import pymupdf


def make_pdf(path: Path | str, pages_text: Sequence[str] | str) -> Path:
    """Create a minimal PDF file with the specified text per page."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(pages_text, str):
        pages_text = [pages_text]

    doc = pymupdf.open()
    for text in pages_text:
        page = doc.new_page()
        page.insert_text((72, 72), text)
    doc.save(str(path))
    doc.close()
    return path


create_pdf = make_pdf
