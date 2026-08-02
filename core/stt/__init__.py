"""Picks the speech-to-text engine for this machine.

Order is cuda -> mlx -> cpu. Nothing heavy is imported while deciding: the
probe uses importlib and a cheap torch call, so a Mac never pays to load CUDA
machinery and a Windows box never looks for MLX.
"""

from __future__ import annotations

import importlib.util
import logging
import platform
import sys

log = logging.getLogger(__name__)

#: Models that are painful without a GPU, used to warn (never to silently swap).
_HEAVY_MODELS = {"medium", "large-v3-turbo"}
_CPU_FRIENDLY_MODEL = "small"


def _has_cuda() -> bool:
    if importlib.util.find_spec("torch") is None:
        return False
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        log.debug("CUDA probe failed.", exc_info=True)
        return False


def _has_mlx() -> bool:
    if sys.platform != "darwin" or platform.machine() != "arm64":
        return False
    return importlib.util.find_spec("mlx_whisper") is not None


def describe_device() -> str:
    if _has_cuda():
        return "cuda"
    if _has_mlx():
        return "mlx"
    return "cpu"


def recommended_model(current: str) -> str:
    """What to suggest on this hardware. Only advisory — never applied silently."""
    if describe_device() == "cpu" and current in _HEAVY_MODELS:
        return _CPU_FRIENDLY_MODEL
    return current


def create_backend(model_name: str):
    """Build the best available backend for `model_name`."""
    device = describe_device()

    if device == "mlx":
        from core.stt.backend_mlx import MlxWhisperBackend

        return MlxWhisperBackend(model_name)

    from core.stt.backend_torch import TorchWhisperBackend

    if device == "cpu" and model_name in _HEAVY_MODELS:
        log.warning(
            "Model '%s' has no GPU to run on here; expect 20-45s per phrase. "
            "Consider '%s'.",
            model_name,
            _CPU_FRIENDLY_MODEL,
        )
    return TorchWhisperBackend(model_name, device)
