import socket
import pytest
import grpc

from services.inference.server import build_server
from services.inference import mark_inference_pb2 as pb2
from services.inference import mark_inference_pb2_grpc as pb2_grpc
from services.inference.devices import choose_device, with_cpu_fallback
from mark_engine.adapters.inference_service import (
    InferenceClient,
    InferenceUnavailable,
    load_service_inference,
)
from mark_engine.adapters.inference_cache import load_cached_inference
from mark_engine.domain.models import ProcessingStatus

TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\n\x00\x00\x00\n\x08\x02\x00\x00\x00\x02PX\xea"
    b"\x00\x00\x00\rIDATx\x9cc`\x18\x05\xa4\x03\x00\x016\x00\x01V\xd1\x7f\xc8\x00\x00\x00\x00IEND\xaeB`\x82"
)


class FakeOcrEngine:
    def __init__(self, device="gpu"):
        self.device = device

    def page(self, png: bytes):
        return [
            [10.0, 20.0, 30.0, 40.0, "LINE1", 0.9950],
            [10.0, 50.0, 30.0, 70.0, "LINE2", 0.9850],
        ]

    def rec(self, crops: list[bytes]):
        return [("LINE1", 0.9950) for _ in crops]


class FakeSymbolEngine:
    def __init__(self, device="gpu"):
        self.device = device

    def symbols(self, png: bytes):
        return [
            ["ADI_LOGO", 0.95, 5.0, 5.0, 15.0, 15.0],
        ]


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def running_server():
    port = find_free_port()
    api_key = "test-secret-key-12345"
    ocr = FakeOcrEngine()
    symbols = FakeSymbolEngine()
    server = build_server(ocr, symbols, api_key=api_key, port=port)
    server.start()
    channel = grpc.insecure_channel(f"127.0.0.1:{port}")
    stub = pb2_grpc.MarkInferenceStub(channel)
    try:
        yield stub, api_key
    finally:
        channel.close()
        server.stop(grace=None)


def test_health_reports_devices_and_model(running_server):
    stub, api_key = running_server
    reply = stub.Health(pb2.HealthRequest(), metadata=(("x-api-key", api_key),))
    assert reply.status == "ok"
    assert reply.ocr_device in ("gpu", "cpu")
    assert reply.symbol_device in ("gpu", "cpu")
    assert reply.model.service_version != ""


@pytest.mark.parametrize(
    "metadata",
    [
        (),
        (("x-api-key", "wrong-key"),),
    ],
)
def test_missing_or_wrong_api_key_is_unauthenticated(running_server, metadata):
    stub, _ = running_server
    with pytest.raises(grpc.RpcError) as exc_info:
        stub.Health(pb2.HealthRequest(), metadata=metadata)
    assert exc_info.value.code() == grpc.StatusCode.UNAUTHENTICATED


def test_page_round_trips_items_in_order(running_server):
    stub, api_key = running_server
    req = pb2.ImageRequest(name="test.png", png=TINY_PNG)
    reply = stub.Page(req, metadata=(("x-api-key", api_key),))
    assert len(reply.items) == 2
    assert reply.items[0].text == "LINE1"
    assert reply.items[0].score == pytest.approx(0.9950, rel=1e-3)
    assert reply.items[1].text == "LINE2"
    assert reply.model.device in ("gpu", "cpu")


def test_bad_png_is_invalid_argument_and_server_survives(running_server):
    stub, api_key = running_server
    req_bad = pb2.ImageRequest(name="bad.png", png=b"not-a-valid-png-stream")
    with pytest.raises(grpc.RpcError) as exc_info:
        stub.Page(req_bad, metadata=(("x-api-key", api_key),))
    assert exc_info.value.code() == grpc.StatusCode.INVALID_ARGUMENT

    # Verify server survives and can handle subsequent valid call
    req_good = pb2.ImageRequest(name="good.png", png=TINY_PNG)
    reply = stub.Page(req_good, metadata=(("x-api-key", api_key),))
    assert len(reply.items) == 2


@pytest.mark.parametrize(
    "free_mb,min_free,force,expected",
    [
        (80000, 3000, "cpu", "cpu"),
        (0, 3000, "gpu", "gpu"),
        (None, 3000, "gpu", "gpu"),
        (None, 3000, None, "cpu"),
        (2000, 3000, None, "cpu"),
        (3000, 3000, None, "gpu"),
        (5000, 3000, None, "gpu"),
    ],
)
def test_choose_device(free_mb, min_free, force, expected):
    assert choose_device(free_mb, min_free_mb=min_free, force=force) == expected


def test_oom_falls_back_to_cpu_once():
    cpu_built_count = 0
    cpu_engine = None

    def get_cpu_engine():
        nonlocal cpu_built_count, cpu_engine
        if cpu_engine is None:
            cpu_built_count += 1
            cpu_engine = "built_cpu_engine"
        return cpu_engine

    def fake_gpu():
        raise RuntimeError("CUDA out of memory. Tried to allocate 2.00 GiB")

    def fake_cpu():
        engine = get_cpu_engine()
        return f"result_from_{engine}"

    # First call: fake GPU raises OOM -> falls back to CPU, engine built once
    res1, dev1 = with_cpu_fallback(fake_gpu, fake_cpu)
    assert res1 == "result_from_built_cpu_engine"
    assert dev1 == "cpu"
    assert cpu_built_count == 1

    # Second call: fake GPU raises OOM -> falls back to CPU, engine reused (still built once)
    res2, dev2 = with_cpu_fallback(fake_gpu, fake_cpu)
    assert res2 == "result_from_built_cpu_engine"
    assert dev2 == "cpu"
    assert cpu_built_count == 1


def test_other_errors_are_not_swallowed():
    def fake_gpu_value_error():
        raise ValueError("Invalid dimension")

    def fake_cpu():
        return "cpu_result"

    with pytest.raises(ValueError, match="Invalid dimension"):
        with_cpu_fallback(fake_gpu_value_error, fake_cpu)


class FallbackFakeOcrEngine:
    def __init__(self):
        self.device = "gpu"
        self._cpu_engine = None
        self._cpu_build_count = 0

    def _get_cpu(self):
        if self._cpu_engine is None:
            self._cpu_build_count += 1
            self._cpu_engine = "cpu_ready"
        return self._cpu_engine

    def page(self, png: bytes):
        def run_gpu():
            if self.device == "gpu":
                raise RuntimeError("CUDA out of memory. Tried to allocate...")
            return []

        def run_cpu():
            self._get_cpu()
            return [[0.0, 0.0, 10.0, 10.0, "CPU_FALLBACK_TEXT", 0.99]]

        res, dev = with_cpu_fallback(run_gpu, run_cpu)
        self.device = dev
        return res


def test_server_reports_cpu_after_fallback():
    port = find_free_port()
    api_key = "test-fallback-key"
    ocr = FallbackFakeOcrEngine()
    symbols = FakeSymbolEngine()
    server = build_server(ocr, symbols, api_key=api_key, port=port)
    server.start()
    channel = grpc.insecure_channel(f"127.0.0.1:{port}")
    stub = pb2_grpc.MarkInferenceStub(channel)
    try:
        req = pb2.ImageRequest(name="test.png", png=TINY_PNG)
        reply = stub.Page(req, metadata=(("x-api-key", api_key),))
        assert reply.model.device == "cpu"
        assert len(reply.items) == 1
        assert reply.items[0].text == "CPU_FALLBACK_TEXT"

        # Subsequent health check should also reflect cpu
        health = stub.Health(pb2.HealthRequest(), metadata=(("x-api-key", api_key),))
        assert health.ocr_device == "cpu"
    finally:
        channel.close()
        server.stop(grace=None)


def test_service_loader_equals_cache_loader(tmp_path):
    import json
    from mark_engine.domain.models import Side

    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    images_dir = cache_dir / "images"
    images_dir.mkdir()
    (images_dir / "test_img.png").write_bytes(TINY_PNG)

    # images_index.csv
    (cache_dir / "images_index.csv").write_text(
        "elr,abs_file,image,source_sha256,sha256\n"
        "ADI2607001,ABS000001,test_img.png,dummy_src,dummy_sha\n",
        encoding="utf-8",
    )
    # det_rec.json
    det_rec = {
        "test_img.png": [
            [10.0, 20.0, 100.0, 40.0, "LINE 1: ABC", 0.9950],
            [10.0, 50.0, 100.0, 70.0, "LINE 2: XYZ", 0.9850],
        ]
    }
    (cache_dir / "det_rec.json").write_text(json.dumps(det_rec), encoding="utf-8")
    # detections.json
    detections = {
        "test_img": [
            ["ADI_LOGO", 0.950, 5.0, 5.0, 15.0, 15.0],
        ]
    }
    (cache_dir / "detections.json").write_text(json.dumps(detections), encoding="utf-8")
    # reocr.csv
    (cache_dir / "reocr.csv").write_text(
        "key,old,new,score,method\n"
        "test_img|TOP|1,ABC,ABC_NEW,0.9900,legend_value\n",
        encoding="utf-8",
    )

    cache_res = load_cached_inference(cache_dir, "ADI2607001", "ABS000001")

    class ReplayOcrEngine:
        def __init__(self):
            self.device = "gpu"

        def page(self, png: bytes):
            return det_rec["test_img.png"]

        def rec(self, crops: list[bytes]):
            return [("ABC_NEW", 0.9900)]

    class ReplaySymbolEngine:
        def __init__(self):
            self.device = "gpu"

        def symbols(self, png: bytes):
            return detections["test_img"]

    port = find_free_port()
    api_key = "test-replay-key"
    server = build_server(ReplayOcrEngine(), ReplaySymbolEngine(), api_key=api_key, port=port)
    server.start()
    try:
        client = InferenceClient(addr=f"127.0.0.1:{port}", api_key=api_key)
        service_res = load_service_inference(
            client=client,
            images_dir=images_dir,
            index_csv=cache_dir / "images_index.csv",
            elr_no="ADI2607001",
            abs_stem="ABS000001",
        )
        assert service_res == cache_res
    finally:
        server.stop(grace=None)


def test_server_down_raises_inference_unavailable():
    # Non-listening port with short timeout and 0 retries or fast backoff
    client = InferenceClient(addr="127.0.0.1:59999", api_key="dummy", timeout_s=0.2, backoff_s=0.01)
    with pytest.raises(InferenceUnavailable):
        client.health()


def test_run_blind_service_failure_is_inference_failed(monkeypatch):
    from scripts.run_blind import execute_job_with_fallback
    from mark_engine.domain.models import ElrMeta, OracleMark

    meta = ElrMeta(elr_no="ADI2607999", top_type_code="E", top_layout_code="A", top_mark_id=1)
    oracle = OracleMark(elr_no="ADI2607999")

    def mock_process_elr(meta, oracle, root, months, work_dir, rules, loader, **kwargs):
        # Trigger the failing loader as pipeline would during inference loading stage
        loader(root, meta.elr_no, "dummy_abs")

    def failing_loader(root, elr_no, abs_stem):
        raise InferenceUnavailable("Connection refused")

    monkeypatch.setattr("scripts.run_blind.process_elr", mock_process_elr)
    job = execute_job_with_fallback(meta, oracle, failing_loader)
    assert job.processing_status == ProcessingStatus.FAILED
    assert job.hold_reason == "INFERENCE_FAILED"
    assert job.verification_status.name == "NOT_VERIFIABLE"


def test_compare_counts_box_and_text_diffs(tmp_path):
    import json
    from scripts.compare_inference import run_comparison

    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    images_dir = cache_dir / "images"
    images_dir.mkdir()
    img_name = "test_img.png"
    (images_dir / img_name).write_bytes(TINY_PNG)

    (cache_dir / "images_index.csv").write_text(
        "elr,abs_file,image,source_sha256,sha256\n"
        f"ADI2607001,ABS000001,{img_name},dummy_src,dummy_sha\n",
        encoding="utf-8",
    )

    # Cached data has 1 page item and 1 symbol
    det_rec = {
        img_name: [
            [10.0, 20.0, 100.0, 40.0, "CACHED_TEXT", 0.99],
        ]
    }
    (cache_dir / "det_rec.json").write_text(json.dumps(det_rec), encoding="utf-8")

    detections = {
        "test_img": [
            ["pin1_dot", 0.95, 10.0, 10.0, 20.0, 20.0],
        ]
    }
    (cache_dir / "detections.json").write_text(json.dumps(detections), encoding="utf-8")

    # Mock client with mismatched page text and mismatched symbol
    class FakeClient:
        def health(self):
            return {"ocr_device": "cpu", "model": {"service_version": "0.1.0"}}

        def page(self, name, png):
            # Same box, different text -> should flag text diff
            return [[10.0, 20.0, 100.0, 40.0, "DIFFERENT_TEXT", 0.99]]

        def symbols(self, name, png):
            # Different symbol class
            return [["adi_logo", 0.95, 10.0, 10.0, 20.0, 20.0]]

        def rec(self, crops):
            return []

    out_dir = tmp_path / "out"
    summary = run_comparison(cache_dir=cache_dir, client=FakeClient(), out_dir=out_dir)

    assert summary["images_total"] == 1
    assert summary["images_passed"] == 0
    assert summary["page_diffs"] == 1
    assert summary["symbol_diffs"] == 1

    diffs_csv = (out_dir / "diffs.csv").read_text(encoding="utf-8")
    assert "image_sha256,kind,field" in diffs_csv
    assert "test_img,page,text" in diffs_csv
    assert "test_img,symbol,class_multiset" in diffs_csv
    # Verify no raw OCR text leaked in output
    assert "CACHED_TEXT" not in diffs_csv
    assert "DIFFERENT_TEXT" not in diffs_csv


def test_choose_device_ocr_cpu_when_paddle_not_cuda(monkeypatch):
    import sys
    from unittest.mock import MagicMock
    from services.inference.devices import choose_device

    fake_paddle = MagicMock()
    fake_paddle.device.is_compiled_with_cuda.return_value = False
    monkeypatch.setitem(sys.modules, "paddle", fake_paddle)

    # When VRAM is abundant (> 3000 MB):
    # OCR should choose CPU because paddle is not CUDA-compiled
    ocr_dev = choose_device(free_vram_mb=8000, min_free_mb=3000, engine="ocr")
    assert ocr_dev == "cpu"

    # YOLO / Symbol should still choose GPU
    sym_dev = choose_device(free_vram_mb=8000, min_free_mb=3000, engine="symbol")
    assert sym_dev == "gpu"


def test_health_reports_ocr_cpu_and_symbol_gpu():
    from services.inference.server import build_server
    from services.inference import mark_inference_pb2 as pb2
    from services.inference import mark_inference_pb2_grpc as pb2_grpc

    port = find_free_port()
    api_key = "test-split-device-key"
    ocr = FakeOcrEngine()
    ocr.device = "cpu"
    symbols = FakeSymbolEngine()
    symbols.device = "gpu"

    server = build_server(ocr, symbols, api_key=api_key, port=port)
    server.start()
    channel = grpc.insecure_channel(f"127.0.0.1:{port}")
    stub = pb2_grpc.MarkInferenceStub(channel)
    try:
        reply = stub.Health(pb2.HealthRequest(), metadata=(("x-api-key", api_key),))
        assert reply.status == "ok"
        assert reply.ocr_device == "cpu"
        assert reply.symbol_device == "gpu"
    finally:
        channel.close()
        server.stop(grace=None)





