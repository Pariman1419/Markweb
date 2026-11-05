import socket
import pytest
import grpc

from services.inference.server import build_server
from services.inference import mark_inference_pb2 as pb2
from services.inference import mark_inference_pb2_grpc as pb2_grpc
from services.inference.devices import choose_device, with_cpu_fallback

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

