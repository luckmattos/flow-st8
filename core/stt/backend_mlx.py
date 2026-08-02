"""MLX Whisper backend — runs on the Apple GPU via Metal.

Only reachable on Apple Silicon. It exists because openai-whisper on a Mac has
no GPU path: large-v3-turbo takes 20-45s per phrase on CPU, which reads as a
frozen app. The decoding parameters mirror backend_torch exactly so both
engines share the same anti-hallucination behaviour.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

import numpy as np

log = logging.getLogger(__name__)


def _dtype():
    import mlx.core as mx

    # Must match what mlx_whisper.transcribe requests, or ModelHolder loads a
    # second copy of the model.
    return mx.float16


# openai-whisper model name -> MLX community repo.
_REPOS = {
    "tiny": "mlx-community/whisper-tiny",
    "base": "mlx-community/whisper-base",
    "small": "mlx-community/whisper-small",
    "medium": "mlx-community/whisper-medium",
    "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
}


def repo_for(model_name: str) -> str:
    """Map a config model name onto an MLX repo, defaulting to the name itself."""
    return _REPOS.get(model_name, model_name)


class MlxWhisperBackend:
    """All MLX work is pinned to one thread.

    MLX streams are thread-local: a model loaded on one thread and used from
    another aborts the process with "There is no Stream(gpu, N) in current
    thread" — an uncatchable C++ abort, not a Python exception. The app calls
    transcribe from a ThreadPoolExecutor, so without this the first
    transcription after startup would kill the app. Serialising GPU work is
    wanted anyway; the model is not reentrant.
    """

    def __init__(self, model_name: str):
        self._model_name = model_name
        self._repo = repo_for(model_name)
        self._model = None
        self.name = "mlx (Apple GPU)"
        self._runner = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="mlx"
        )

    def close(self) -> None:
        self._runner.shutdown(wait=False)

    def load(self) -> None:
        self._runner.submit(self._load).result()

    def language_probs(self, audio: np.ndarray, allowed: tuple[str, ...]) -> dict[str, float]:
        return self._runner.submit(self._language_probs, audio, allowed).result()

    def transcribe(
        self, audio: np.ndarray, language: str, initial_prompt: str | None
    ) -> list[dict]:
        return self._runner.submit(
            self._transcribe, audio, language, initial_prompt
        ).result()

    # -- everything below runs on the mlx thread ------------------------

    def _load(self) -> None:
        import mlx.core as mx
        from mlx_whisper.transcribe import ModelHolder

        log.info("Loading MLX Whisper '%s'...", self._repo)
        # Go through mlx_whisper's own holder rather than load_model: transcribe()
        # fetches from it on every call, so loading separately would keep two
        # copies of the model resident and run language detection against a
        # different one than the transcription uses.
        self._model = ModelHolder.get_model(self._repo, _dtype())
        log.info("MLX Whisper model loaded (%s).", self.name)

    def _language_probs(self, audio: np.ndarray, allowed: tuple[str, ...]) -> dict[str, float]:
        import mlx.core as mx
        from mlx_whisper.audio import log_mel_spectrogram, pad_or_trim
        from mlx_whisper.decoding import detect_language

        n_mels = self._model.dims.n_mels
        # MLX's pad_or_trim only accepts mx.array — handing it a numpy array
        # fails deep inside mx.pad, which used to be swallowed by the caller's
        # except and silently pinned every recording to the first language.
        samples = mx.array(np.asarray(audio, dtype=np.float32))
        mel = log_mel_spectrogram(pad_or_trim(samples), n_mels=n_mels).astype(_dtype())
        _tokens, probs = detect_language(self._model, mel)
        dist = probs[0] if isinstance(probs, list) else probs
        return {lang: float(dist.get(lang, 0.0)) for lang in allowed}

    def _transcribe(
        self, audio: np.ndarray, language: str, initial_prompt: str | None
    ) -> list[dict]:
        import mlx_whisper

        result = mlx_whisper.transcribe(
            audio,
            path_or_hf_repo=self._repo,
            language=language,
            initial_prompt=initial_prompt,
            condition_on_previous_text=False,
            no_speech_threshold=0.6,
            logprob_threshold=-1.0,
            compression_ratio_threshold=2.4,
            temperature=(0.0,),
            verbose=None,
        )
        return result.get("segments", [])
