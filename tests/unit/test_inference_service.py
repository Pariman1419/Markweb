import socket
import pytest
import grpc

from services.inference.server import build_server
from services.inference import mark_inference_pb2 as pb2
from services.inference import mark_inference_pb2_grpc as pb2_grpc

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
