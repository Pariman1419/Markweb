import pymupdf
from mark_engine.abs.brand_page import extract_brand_image


def test_brand_page_selects_last_matching_page_and_renders(tmp_path):
    path = tmp_path / 'abs.pdf'
    doc = pymupdf.open()
    for text in ('cover', 'Brand/Marking', 'other'):
        page = doc.new_page()
        page.insert_text((72, 72), text)
    doc.save(path)
    doc.close()
    image, method, page_number = extract_brand_image(path)
    assert image.startswith(b'\x89PNG\r\n\x1a\n')
    assert method == 'render200'
    assert page_number == 2
