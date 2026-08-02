"""Contract for a speech-to-text engine.

Two implementations exist because no single one is good everywhere: PyTorch
Whisper is the fast path on CUDA and the only option on Windows, while MLX runs
on the Apple GPU and is the difference between 1s and 40s per phrase on a Mac.

Everything above this line — silence trimming, the energy gate, the
anti-hallucination cleanup — lives in core/transcriber.py and is shared.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import numpy as np


class Segment(Protocol):
    """What a backend must expose per transcribed segment."""

    text: str
    no_speech_prob: float


class SttBackend(Protocol):
    #: Human-readable engine + device, e.g. "mlx (Apple GPU)". Shown in logs.
    name: str

    def load(self) -> None:
        """Load the model. Called from a background thread."""
        ...

    def language_probs(self, audio: "np.ndarray", allowed: tuple[str, ...]) -> dict[str, float]:
        """Pick the most likely language, restricted to `allowed`.

        Whisper cannot natively limit its auto-detect to a subset, so backends read
        the full distribution and expose only the allowed slice. Choosing among
        them is policy and lives in core/transcriber.py, so both engines apply
        the same preference rule.
        """
        ...

    def transcribe(
        self,
        audio: "np.ndarray",
        language: str,
        initial_prompt: str | None,
    ) -> list[dict]:
        """Return raw segments, each with at least "text" and "no_speech_prob"."""
        ...
