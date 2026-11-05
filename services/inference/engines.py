"""Shared OCR and symbol detection engines with lazy model loading and fallback."""
import io
import os
from pathlib import Path
import tempfile
import threading
from typing import Any

# Ensure auto_growth and avoid unneeded model source check before Paddle is imported
os.environ.setdefault("FLAGS_allocator_strategy", "auto_growth")
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

from services.inference.devices import with_cpu_fallback


def _to_paddle_device(device: str) -> str:
    dev = device.lower().strip()
    if dev in ("gpu", "cuda") or dev.isdigit() or dev.startswith("gpu:"):
        return "gpu"
    return "cpu"


def _to_yolo_device(device: str) -> str:
    dev = device.lower().strip()
    if dev in ("gpu", "cuda"):
        return "0"
    return dev


def _setup_paddlex_cache():
    pdx_dir = Path(os.environ.get("PADDLE_PDX_CACHE_HOME", Path.home() / ".paddlex"))
    official_dir = pdx_dir / "official_models"
    try:
        pdx_dir.mkdir(parents=True, exist_ok=True)
        if not official_dir.exists():
            for source in [
                Path("/models/paddlex_cache/official_models"),
                Path("/models/official_models"),
            ]:
                if source.exists():
                    os.symlink(str(source), str(official_dir))
                    break
    except Exception:
        pass


class OcrEngine:
    """PaddleOCR text detector (PP-OCRv5_server_det) and recognizer (EXP09)."""

    def __init__(self, device: str = "cpu", recognizer_dir: str = "/models/exp09"):
        self.device = device
        if self.device == "gpu":
            try:
                import paddle
                if hasattr(paddle, "device") and hasattr(paddle.device, "is_compiled_with_cuda"):
                    if not paddle.device.is_compiled_with_cuda():
                        self.device = "cpu"
            except Exception:
                pass
        self.recognizer_dir = str(recognizer_dir)
        self._lock = threading.Lock()
        self._gpu_models: tuple[Any, Any] | None = None
        self._cpu_models: tuple[Any, Any] | None = None

    def _get_models(self, device: str):
        _setup_paddlex_cache()
        target = _to_paddle_device(device)
        if target == "gpu":
            if self._gpu_models is None:
                from paddleocr import TextDetection, TextRecognition

                det = TextDetection(model_name="PP-OCRv5_server_det", device="gpu", enable_mkldnn=False)
                rec = TextRecognition(model_name="PP-OCRv5_server_rec", model_dir=self.recognizer_dir, device="gpu")
                self._gpu_models = (det, rec)
            return self._gpu_models
        else:
            if self._cpu_models is None:
                from paddleocr import TextDetection, TextRecognition

                det = TextDetection(model_name="PP-OCRv5_server_det", device="cpu", enable_mkldnn=False)
                rec = TextRecognition(model_name="PP-OCRv5_server_rec", model_dir=self.recognizer_dir, device="cpu")
                self._cpu_models = (det, rec)
            return self._cpu_models

    def _predict_page(self, png: bytes, device: str) -> list[list]:
        from PIL import Image

        det_model, rec_model = self._get_models(device)
        with Image.open(io.BytesIO(png)) as source:
            image = source.convert("RGB")
        width, height = image.size

        img_temp_name = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                img_temp_name = tmp.name
                tmp.write(png)

            boxes = []
            for result in det_model.predict(input=img_temp_name, batch_size=1):
                for polygon in result["dt_polys"]:
                    xs = [float(point[0]) for point in polygon]
                    ys = [float(point[1]) for point in polygon]
                    pad = 0.15 * (max(ys) - min(ys))
                    boxes.append([
                        max(0, min(xs) - pad),
                        max(0, min(ys) - pad),
                        min(width, max(xs) + pad),
                        min(height, max(ys) + pad),
                    ])
        finally:
            if img_temp_name:
                Path(img_temp_name).unlink(missing_ok=True)

        items = []
        for box in boxes:
            crop_name = None
            try:
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp:
                    crop_name = temp.name
                image.crop(tuple(round(value) for value in box)).save(crop_name)
                result = next(iter(rec_model.predict(input=crop_name, batch_size=1)))
                items.append(
                    [round(value, 1) for value in box]
                    + [result["rec_text"], round(float(result["rec_score"]), 4)]
                )
            finally:
                if crop_name:
                    Path(crop_name).unlink(missing_ok=True)
        return items

    def _predict_rec(self, crops: list[bytes], device: str) -> list[tuple[str, float]]:
        _, rec_model = self._get_models(device)
        results = []
        for crop in crops:
            crop_name = None
            try:
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp:
                    crop_name = temp.name
                    temp.write(crop)
                res = next(iter(rec_model.predict(input=crop_name, batch_size=1)))
                results.append((res["rec_text"], round(float(res["rec_score"]), 4)))
            finally:
                if crop_name:
                    Path(crop_name).unlink(missing_ok=True)
        return results

    def page(self, png: bytes) -> list[list]:
        with self._lock:
            if _to_paddle_device(self.device) == "gpu":
                res, dev = with_cpu_fallback(
                    lambda: self._predict_page(png, "gpu"),
                    lambda: self._predict_page(png, "cpu"),
                )
                self.device = dev
                return res
            return self._predict_page(png, "cpu")

    def rec(self, crops: list[bytes]) -> list[tuple[str, float]]:
        with self._lock:
            if _to_paddle_device(self.device) == "gpu":
                res, dev = with_cpu_fallback(
                    lambda: self._predict_rec(crops, "gpu"),
                    lambda: self._predict_rec(crops, "cpu"),
                )
                self.device = dev
                return res
            return self._predict_rec(crops, "cpu")


class SymbolEngine:
    """YOLO symbol detector."""

    def __init__(self, device: str = "cpu", weights: str = "/models/symdet/v2/weights/best.pt"):
        self.device = device
        self.weights = str(weights)
        self._lock = threading.Lock()
        self._model = None

    def _get_model(self):
        if self._model is None:
            from ultralytics import YOLO

            self._model = YOLO(self.weights)
        return self._model

    def _predict_symbols(self, png: bytes, device: str) -> list[list]:
        model = self._get_model()
        img_temp_name = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                img_temp_name = tmp.name
                tmp.write(png)
            target_device = _to_yolo_device(device)
            result = model.predict(img_temp_name, imgsz=1024, conf=0.25, device=target_device, verbose=False)[0]
            return [
                [result.names[int(cls)], round(float(score), 3)] + [round(float(value), 1) for value in box]
                for cls, score, box in zip(result.boxes.cls, result.boxes.conf, result.boxes.xyxy)
            ]
        finally:
            if img_temp_name:
                Path(img_temp_name).unlink(missing_ok=True)

    def symbols(self, png: bytes) -> list[list]:
        with self._lock:
            if _to_paddle_device(self.device) == "gpu":
                res, dev = with_cpu_fallback(
                    lambda: self._predict_symbols(png, "gpu"),
                    lambda: self._predict_symbols(png, "cpu"),
                )
                self.device = dev
                return res
            return self._predict_symbols(png, "cpu")
