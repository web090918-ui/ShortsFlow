"""Text-to-speech boundary for the product Short (Task 10).

Sentences are synthesized one at a time so each clip's measured duration drives
the caption timing exactly; the pipeline concatenates the clips with FFmpeg.
"""

import logging
from pathlib import Path
from typing import Any, Protocol


logger = logging.getLogger(__name__)


class SpeechSynthesisError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


class SpeechSynthesizer(Protocol):
    name: str

    def synthesize(self, text: str, destination: Path) -> None:
        """Write spoken audio for ``text`` to ``destination`` (MP3)."""
        ...


class OpenAISpeechSynthesizer:
    name = "openai_tts"

    def __init__(
        self,
        client: Any,
        *,
        model: str = "gpt-4o-mini-tts",
        voice: str = "nova",
        instructions: str | None = None,
    ) -> None:
        self._client = client
        self._model = model
        self._voice = voice
        self._instructions = instructions

    def synthesize(self, text: str, destination: Path) -> None:
        request: dict[str, Any] = {
            "model": self._model,
            "voice": self._voice,
            "input": text,
            "response_format": "mp3",
        }
        if self._instructions:
            request["instructions"] = self._instructions
        try:
            with self._client.audio.speech.with_streaming_response.create(**request) as response:
                response.stream_to_file(str(destination))
        except Exception as exc:
            logger.warning("TTS request failed", exc_info=exc)
            status_code = getattr(exc, "status_code", None)
            detail = " ".join(str(exc).split())[:160]
            retryable = status_code not in {400, 401, 403, 404}
            raise SpeechSynthesisError(
                f"음성 합성에 실패했습니다"
                + (f" (HTTP {status_code}, {exc.__class__.__name__})" if status_code else f" ({exc.__class__.__name__})")
                + f": {detail}",
                retryable=retryable,
            ) from exc
        if not destination.exists() or destination.stat().st_size == 0:
            raise SpeechSynthesisError("합성된 음성이 비어 있습니다.")
