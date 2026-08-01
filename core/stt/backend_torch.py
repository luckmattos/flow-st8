"""PyTorch Whisper backend — the original engine, unchanged in behaviour.

This is the only option on Windows and the fast path wherever CUDA exists.
Every decoding parameter here is load-bearing: they are the anti-hallucination
settings tuned in earlier releases, not defaults.
"""

from __future__ import annotations

import logging

import numpy as np

log = logging.getLogger(__name__)


class TorchWhisperBackend:
    def __init__(self, model_name: str, device: str):
        self._model_name = model_name
        self._device = device
        self._use_fp16 = device == "cuda"
        self._model = None
        self.name = f"openai-whisper ({device})"

    def load(self) -> None:
        import whisper

        log.info("Loading Whisper model '%s' on %s...", self._model_name, self._device.upper())
        self._model = whisper.load_model(self._model_name, device=self._device)
        log.info("Whisper model loaded (%s).", self.name)

    def detect_language(self, audio: np.ndarray, allowed: tuple[str, ...]) -> str:
        import whisper

        mel = whisper.log_mel_spectrogram(
            whisper.pad_or_trim(audio), n_mels=self._model.dims.n_mels
        ).to(self._model.device)
        if self._use_fp16:
            mel = mel.half()
        _, probs = self._model.detect_language(mel)
        best = max(allowed, key=lambda lang: probs.get(lang, 0.0))
        log.info(
            "Restricted lang detect: %s -> %s",
            " ".join(f"{lang}={probs.get(lang, 0.0):.2f}" for lang in allowed),
            best,
        )
        return best

    def transcribe(
        self, audio: np.ndarray, language: str, initial_prompt: str | None
    ) -> list[dict]:
        import whisper

        result = whisper.transcribe(
            self._model,
            audio,
            language=language,
            fp16=self._use_fp16,
            task="transcribe",
            initial_prompt=initial_prompt,
            # condition_on_previous_text=False prevents the decoder feedback
            # loop that causes repetitive hallucinations on trailing silence.
            condition_on_previous_text=False,
            no_speech_threshold=0.6,
            logprob_threshold=-1.0,
            compression_ratio_threshold=2.4,
            temperature=(0.0,),
        )
        return result.get("segments", [])
