"""Device selection and fallback utilities for inference services."""
import logging
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def free_vram_mb() -> int | None:
    """Read available VRAM in megabytes using NVML (pynvml). Returns None on error."""
    try:
        import pynvml
        pynvml.nvmlInit()
        try:
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            return int(info.free // (1024 * 1024))
        finally:
            try:
                pynvml.nvmlShutdown()
            except Exception:
                pass
    except Exception:
        return None


def choose_device(
    free_vram_mb: int | None,
    min_free_mb: int,
    force: str | None = None,
    engine: str | None = None,
) -> str:
    """Choose 'gpu' or 'cpu' device.

    Rules:
    - force wins if specified ('gpu' or 'cpu').
    - If engine == 'ocr': if paddle.device.is_compiled_with_cuda() is False -> 'cpu'.
    - None (no GPU or no NVML) -> 'cpu'.
    - free < min_free_mb -> 'cpu'.
    - Otherwise -> 'gpu'.
    """
    if force:
        return force.lower().strip()
    if engine == "ocr":
        try:
            import paddle
            if hasattr(paddle, "device") and hasattr(paddle.device, "is_compiled_with_cuda"):
                if not paddle.device.is_compiled_with_cuda():
                    return "cpu"
        except Exception:
            pass
    if free_vram_mb is None:
        return "cpu"
    if free_vram_mb < min_free_mb:
        return "cpu"
    return "gpu"


def is_cuda_oom(exc: BaseException) -> bool:
    """Check if exception represents a CUDA Out of Memory error."""
    name = exc.__class__.__name__
    if name in ("OutOfMemoryError", "ResourceExhaustedError", "CUDAOutOfMemoryError"):
        return True
    msg = str(exc).lower()
    return "out of memory" in msg or "cuda oom" in msg


def with_cpu_fallback(run_gpu: Callable[[], T], run_cpu: Callable[[], T]) -> tuple[T, str]:
    """Execute run_gpu(); on CUDA out-of-memory error, log warning and fallback to run_cpu().

    Returns (result, device) where device is 'gpu' or 'cpu'.
    Other errors are raised.
    """
    try:
        res = run_gpu()
        return res, "gpu"
    except Exception as exc:
        if is_cuda_oom(exc):
            logger.warning("CUDA out of memory during inference (%s); falling back to CPU", exc)
            res = run_cpu()
            return res, "cpu"
        raise
