"""gRPC inference service client and service-backed inference loader."""
from collections import OrderedDict
import hashlib
import json
import io
from pathlib import Path
import threading
import time
from typing import Any
import grpc
from PIL import Image

from services.inference import mark_inference_pb2 as pb2
from services.inference import mark_inference_pb2_grpc as pb2_grpc
from mark_engine.abs.auto_inference import build_auto_inference
from mark_engine.abs.layout import layout_lines
from mark_engine.abs.reocr import legend_candidates, trim_logo
from mark_engine.adapters.snapshot import _load_csv_cached, REOCR_MIN_SCORE
from mark_engine.domain.models import InferenceResult


class InferenceUnavailable(Exception):
    """Raised when the inference service is unreachable or encounters an error."""
    pass


class InferenceClient:
    """Client for communicating with the mark-inference gRPC service."""

    def __init__(self, addr: str, api_key: str, timeout_s: float = 60.0, backoff_s: float = 2.0):
        self.addr = addr
        self.api_key = api_key
        self.timeout_s = timeout_s
        self.backoff_s = backoff_s
        self._channel = grpc.insecure_channel(addr, options=[("grpc.max_receive_message_length", 32 * 1024 * 1024), ("grpc.max_send_message_length", 32 * 1024 * 1024)])
        self._stub = pb2_grpc.MarkInferenceStub(self._channel)

    def close(self):
        self._channel.close()

    def _metadata(self):
        return (("x-api-key", self.api_key),)

    def _call(self, fn: Any) -> Any:
        attempts = 0
        while True:
            try:
                return fn()
            except grpc.RpcError as rpc_err:
                if rpc_err.code() == grpc.StatusCode.UNAVAILABLE and attempts < 2:
                    attempts += 1
                    time.sleep(self.backoff_s)
                    continue
                raise InferenceUnavailable(f"RPC error {rpc_err.code()}: {rpc_err.details()}") from rpc_err
            except Exception as exc:
                raise InferenceUnavailable(f"Inference error: {exc}") from exc

    def health(self) -> dict:
        reply = self._call(lambda: self._stub.Health(pb2.HealthRequest(), timeout=self.timeout_s, metadata=self._metadata()))
        return {
            "status": reply.status,
            "ocr_device": reply.ocr_device,
            "symbol_device": reply.symbol_device,
            "free_vram_mb": reply.free_vram_mb,
            "model": {
                "service_version": reply.model.service_version,
                "device": reply.model.device,
                "ocr_rec_sha256": reply.model.ocr_rec_sha256,
                "detector_sha256": reply.model.detector_sha256,
                "symbol_sha256": reply.model.symbol_sha256,
            },
        }

    def page(self, name: str, png: bytes) -> list[list]:
        req = pb2.ImageRequest(name=name, png=png)
        reply = self._call(lambda: self._stub.Page(req, timeout=self.timeout_s, metadata=self._metadata()))
        return [
            [item.x0, item.y0, item.x1, item.y1, item.text, item.score]
            for item in reply.items
        ]

    def symbols(self, name: str, png: bytes) -> list[list]:
        req = pb2.ImageRequest(name=name, png=png)
        reply = self._call(lambda: self._stub.Symbols(req, timeout=self.timeout_s, metadata=self._metadata()))
        return [
            [sym.cls, sym.conf, sym.x0, sym.y0, sym.x1, sym.y1]
            for sym in reply.symbols
        ]

    def process_pdf(self, name: str, pdf_bytes: bytes):
        req = pb2.PdfRequest(name=name, pdf=pdf_bytes)
        return self._call(lambda: self._stub.ProcessPdf(req, timeout=self.timeout_s, metadata=self._metadata()))

    def rec(self, crops: list[bytes]) -> list[tuple[str, float]]:
        req = pb2.RecRequest(crops=crops)
        reply = self._call(lambda: self._stub.Rec(req, timeout=self.timeout_s, metadata=self._metadata()))
        return [(res.text, res.score) for res in reply.results]


def load_service_inference_for_pdf(client, pdf_path: Path, images_dir: Path,
                                   expected_sha256: str, elr_no: str, abs_stem: str, *, image_saved=None) -> InferenceResult:
    data = pdf_path.read_bytes()
    if expected_sha256 and hashlib.sha256(data).hexdigest() != expected_sha256:
        raise ValueError("ABS changed before inference")
    reply = client.process_pdf(pdf_path.name, data)
    digest = hashlib.sha256(reply.png).hexdigest()
    if not reply.png.startswith(b"\x89PNG\r\n\x1a\n") or digest != reply.png_sha256:
        raise InferenceUnavailable("Invalid image or hash returned by inference service")
    images_dir.mkdir(parents=True, exist_ok=True)
    image_path = images_dir / f"{digest}.png"
    if image_path.exists() and hashlib.sha256(image_path.read_bytes()).hexdigest() != digest:
        raise RuntimeError(f"Image hash mismatch: {image_path}")
    if not image_path.exists():
        image_path.write_bytes(reply.png)
    if image_saved is not None:
        image_saved(image_path)
    items = [[i.x0, i.y0, i.x1, i.y1, i.text, i.score] for i in reply.items]
    symbols = [[s.cls, s.conf, s.x0, s.y0, s.x1, s.y1] for s in reply.symbols]
    reread = {key: tuple(json.loads(value)) for key, value in reply.reocr.items()}
    return build_auto_inference(elr_no, digest, items, symbols, reread)


_SERVICE_INFERENCE_CACHE: OrderedDict[str, tuple[list, list, dict]] = OrderedDict()
_CACHE_MAX_SIZE = 512
_CACHE_LOCK = threading.Lock()


def load_service_inference_for_image(
    client: InferenceClient,
    image_path: Path,
    elr_no: str,
    abs_stem: str,
) -> InferenceResult:
    """Run inference against a marking page image via the gRPC service."""
    if not image_path.is_file():
        raise FileNotFoundError(f"Inference image missing: {image_path}")

    name = image_path.name
    stem = image_path.stem

    with _CACHE_LOCK:
        cached = _SERVICE_INFERENCE_CACHE.get(name)
        if cached is not None:
            _SERVICE_INFERENCE_CACHE.move_to_end(name)

    if cached is not None:
        page_items, symbol_items, reocr_map = cached
        return build_auto_inference(elr_no, stem, page_items, symbol_items, reocr_map)

    png_bytes = image_path.read_bytes()
    page_items = client.page(name, png_bytes)
    symbol_items = client.symbols(name, png_bytes)

    # Re-OCR with trim-logo on
    with Image.open(io.BytesIO(png_bytes)) as source:
        image = source.convert("RGB")

    candidates = legend_candidates(name, page_items)
    for side, number, text, _, box in layout_lines(page_items):
        key = f"{stem}|{side.value}|{number}"
        if box and not any(row["key"] == key for row in candidates):
            cropped = trim_logo(image.crop(tuple(int(x) for x in box)))
            if cropped:
                candidates.append({"key": key, "old": text.strip(), "image": cropped, "method": "trim_logo"})

    reocr_map = {}
    if candidates:
        crops = []
        for candidate in candidates:
            crop = candidate.get("image") or image.crop(candidate["box"])
            buf = io.BytesIO()
            crop.convert("RGB").save(buf, "PNG")
            crops.append(buf.getvalue())
        rec_results = client.rec(crops)
        for candidate, (new_text, score) in zip(candidates, rec_results):
            old = candidate["old"].strip()
            new = (new_text or "").strip()
            if new and new != old and score >= REOCR_MIN_SCORE:
                reocr_map[candidate["key"]] = (old, new)

    with _CACHE_LOCK:
        _SERVICE_INFERENCE_CACHE[name] = (page_items, symbol_items, reocr_map)
        _SERVICE_INFERENCE_CACHE.move_to_end(name)
        if len(_SERVICE_INFERENCE_CACHE) > _CACHE_MAX_SIZE:
            _SERVICE_INFERENCE_CACHE.popitem(last=False)

    return build_auto_inference(elr_no, stem, page_items, symbol_items, reocr_map)


def load_service_inference(
    client: InferenceClient,
    images_dir: Path,
    index_csv: Path,
    elr_no: str,
    abs_stem: str,
) -> InferenceResult:
    """Load inference results via live gRPC service using an index CSV (blind batch compatibility)."""
    matching = [
        row for row in _load_csv_cached(str(index_csv))
        if row.get("elr", "").upper() == elr_no.upper()
        and row.get("abs_file", "").upper() == abs_stem.upper()
    ]
    if len(matching) > 1:
        raise ValueError(f"{elr_no}: duplicate inference index entries")
    if not matching:
        raise ValueError(f"{elr_no}: no inference index for resolved ABS {abs_stem}")

    name = matching[0]["image"]
    image_path = images_dir / name
    return load_service_inference_for_image(client, image_path, elr_no, abs_stem)
