import hashlib
import pymupdf
from services.inference import mark_inference_pb2 as pb
from services.inference.server import MarkInferenceServicer

class OCR:
    device = 'cpu'
    def page(self, png): return [[1, 2, 100, 20, 'LINE 1: OLD', .99]]
    def rec(self, crops): return [('NEW', .99)] * len(crops)

class Symbols:
    device = 'cpu'
    def symbols(self, png): return [['logo', .9, 1, 2, 3, 4]]

def test_process_pdf_returns_image_and_inference():
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), 'Brand/Marking')
    data = doc.tobytes()
    doc.close()
    reply = MarkInferenceServicer(OCR(), Symbols()).ProcessPdf(pb.PdfRequest(name='abs.pdf', pdf=data), None)
    assert reply.png.startswith(b'\x89PNG\r\n\x1a\n')
    assert reply.png_sha256 == hashlib.sha256(reply.png).hexdigest()
    assert reply.page_number == 1
    assert reply.items[0].text == 'LINE 1: OLD'
    assert reply.symbols[0].cls == 'logo'
    assert 'NEW' in list(reply.reocr.values())[0]

def test_pdf_loader_saves_image_and_uses_response(tmp_path, monkeypatch):
    from mark_engine.adapters import inference_service as service
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), 'Brand/Marking')
    data = doc.tobytes()
    doc.close()
    source = tmp_path / 'abs.pdf'
    source.write_bytes(data)
    reply = MarkInferenceServicer(OCR(), Symbols()).ProcessPdf(pb.PdfRequest(pdf=data), None)
    class Client:
        def process_pdf(self, name, pdf):
            assert pdf == data
            return reply
    captured = {}
    def build(elr, stem, items, symbols, reocr):
        captured.update(stem=stem, items=items, symbols=symbols, reocr=reocr)
        return 'result'
    monkeypatch.setattr(service, 'build_auto_inference', build)
    result = service.load_service_inference_for_pdf(Client(), source, tmp_path / 'images', hashlib.sha256(data).hexdigest(), 'ELR', 'abs')
    assert result == 'result'
    assert (tmp_path / 'images' / (reply.png_sha256 + '.png')).read_bytes() == reply.png
    assert captured['stem'] == reply.png_sha256
    assert captured['items'][0][4] == 'LINE 1: OLD'
    assert list(captured['reocr'].values()) == [('OLD', 'NEW')]
