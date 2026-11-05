"""gRPC server for mark-inference service on A100."""
import hmac
import io
import os
import sys
from concurrent import futures
from PIL import Image
import grpc

from services.inference import mark_inference_pb2 as pb2
from services.inference import mark_inference_pb2_grpc as pb2_grpc


def _validate_png(png: bytes, context: grpc.ServicerContext) -> None:
    if not png or not png.startswith(b"\x89PNG\r\n\x1a\n"):
        context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Input is not a valid PNG image")
    try:
        with Image.open(io.BytesIO(png)) as img:
            img.verify()
    except Exception as exc:
        context.abort(grpc.StatusCode.INVALID_ARGUMENT, f"Invalid PNG stream: {exc}")


class ApiKeyInterceptor(grpc.ServerInterceptor):
    def __init__(self, api_key: str):
        self._api_key = api_key

    def intercept_service(self, continuation, handler_call_details):
        metadata = dict(handler_call_details.invocation_metadata)
        client_key = metadata.get("x-api-key")
        if not client_key or not hmac.compare_digest(client_key, self._api_key):
            def abort(request, context):
                context.abort(grpc.StatusCode.UNAUTHENTICATED, "Missing or invalid x-api-key")
            return grpc.unary_unary_rpc_method_handler(abort)
        return continuation(handler_call_details)


class MarkInferenceServicer(pb2_grpc.MarkInferenceServicer):
    def __init__(self, ocr_engine, symbol_engine, model_info: dict | None = None):
        self.ocr_engine = ocr_engine
        self.symbol_engine = symbol_engine
        self._model_info = model_info or {}

    def _get_model_info(self, device: str | None = None) -> pb2.ModelInfo:
        return pb2.ModelInfo(
            service_version=self._model_info.get("service_version", "0.1.0"),
            device=device or getattr(self.ocr_engine, "device", "cpu"),
            ocr_rec_sha256=self._model_info.get("ocr_rec_sha256", ""),
            detector_sha256=self._model_info.get("detector_sha256", ""),
            symbol_sha256=self._model_info.get("symbol_sha256", ""),
        )

    def Health(self, request, context):
        ocr_dev = getattr(self.ocr_engine, "device", "cpu")
        sym_dev = getattr(self.symbol_engine, "device", "cpu")
        free_mb = getattr(self.ocr_engine, "free_vram_mb", None)
        if free_mb is None:
            try:
                from services.inference.devices import free_vram_mb
                val = free_vram_mb()
                free_mb = val if val is not None else 0
            except Exception:
                free_mb = 0
        return pb2.HealthReply(
            status="ok",
            ocr_device=ocr_dev,
            symbol_device=sym_dev,
            free_vram_mb=int(free_mb),
            model=self._get_model_info(device=ocr_dev),
        )

    def Page(self, request, context):
        _validate_png(request.png, context)
        raw_items = self.ocr_engine.page(request.png)
        items = [
            pb2.TextItem(
                x0=float(item[0]),
                y0=float(item[1]),
                x1=float(item[2]),
                y1=float(item[3]),
                text=str(item[4]),
                score=float(item[5]),
            )
            for item in raw_items
        ]
        ocr_dev = getattr(self.ocr_engine, "device", "cpu")
        return pb2.PageReply(
            items=items,
            model=self._get_model_info(device=ocr_dev),
        )

    def Symbols(self, request, context):
        _validate_png(request.png, context)
        raw_syms = self.symbol_engine.symbols(request.png)
        symbols = [
            pb2.Symbol(
                cls=str(sym[0]),
                conf=float(sym[1]),
                x0=float(sym[2]),
                y0=float(sym[3]),
                x1=float(sym[4]),
                y1=float(sym[5]),
            )
            for sym in raw_syms
        ]
        sym_dev = getattr(self.symbol_engine, "device", "cpu")
        return pb2.SymbolsReply(
            symbols=symbols,
            model=self._get_model_info(device=sym_dev),
        )

    def Rec(self, request, context):
        for crop in request.crops:
            _validate_png(crop, context)
        raw_results = self.ocr_engine.rec(list(request.crops))
        results = [
            pb2.RecResult(
                text=str(r[0]),
                score=float(r[1]),
            )
            for r in raw_results
        ]
        ocr_dev = getattr(self.ocr_engine, "device", "cpu")
        return pb2.RecReply(
            results=results,
            model=self._get_model_info(device=ocr_dev),
        )


def build_server(
    ocr,
    symbols,
    api_key: str,
    port: int,
    max_msg_mb: int = 32,
    model_info: dict | None = None,
) -> grpc.Server:
    options = [
        ("grpc.max_receive_message_length", max_msg_mb * 1024 * 1024),
        ("grpc.max_send_message_length", max_msg_mb * 1024 * 1024),
    ]
    interceptor = ApiKeyInterceptor(api_key)
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=10),
        interceptors=(interceptor,),
        options=options,
    )
    servicer = MarkInferenceServicer(ocr, symbols, model_info=model_info)
    pb2_grpc.add_MarkInferenceServicer_to_server(servicer, server)
    server.add_insecure_port(f"0.0.0.0:{port}")
    return server


def _file_sha256(path: str) -> str:
    import hashlib
    if not path or not os.path.isfile(path):
        return ""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def main():
    api_key = os.getenv("MARK_INF_API_KEY", "")
    if not api_key:
        print("ERROR: MARK_INF_API_KEY environment variable is required", file=sys.stderr)
        sys.exit(1)
    port = int(os.getenv("MARK_INF_PORT", "50051"))
    min_free_mb = int(os.getenv("MARK_INF_MIN_FREE_MB", "3000"))
    force_device = os.getenv("MARK_INF_FORCE_DEVICE")

    # Use choose_device and shared engines
    from services.inference.devices import choose_device, free_vram_mb
    from services.inference.engines import OcrEngine, SymbolEngine

    free_mb = free_vram_mb()
    device = choose_device(free_mb, min_free_mb=min_free_mb, force=force_device)
    recognizer_dir = os.getenv("MARK_INF_RECOGNIZER_DIR", "/models/exp09")
    weights = os.getenv("MARK_INF_SYMBOL_WEIGHTS", "/models/symdet/v2/weights/best.pt")

    # Find detector weights for model_info
    det_candidates = [
        "/models/paddlex_cache/official_models/PP-OCRv5_server_det/inference.pdiparams",
        "/models/PP-OCRv5_server_det/inference.pdiparams",
        os.path.expanduser("~/.paddlex/official_models/PP-OCRv5_server_det/inference.pdiparams"),
    ]
    det_path = next((p for p in det_candidates if os.path.isfile(p)), "")

    model_info = {
        "service_version": "0.1.0",
        "ocr_rec_sha256": _file_sha256(os.path.join(recognizer_dir, "inference.pdiparams")),
        "symbol_sha256": _file_sha256(weights),
        "detector_sha256": _file_sha256(det_path),
    }

    ocr = OcrEngine(device=device, recognizer_dir=recognizer_dir)
    symbols = SymbolEngine(device=device, weights=weights)

    server = build_server(ocr, symbols, api_key=api_key, port=port, model_info=model_info)
    server.start()
    print(f"mark-inference service running on port {port} (device={device})")
    server.wait_for_termination()


if __name__ == "__main__":
    main()
