from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ReferenceTranscriber:
    def __init__(
        self,
        *,
        enabled: bool,
        model_name: str,
        device: str,
        compute_type: str,
        language: str,
    ) -> None:
        self.enabled = bool(enabled)
        self.model_name = (model_name or "turbo").strip()
        self.device = (device or "auto").strip()
        self.compute_type = (compute_type or "auto").strip()
        self.language = (language or "ru").strip()
        self._model: Any = None
        self._load_lock = asyncio.Lock()

    async def prewarm(self) -> None:
        if not self.enabled:
            return
        await self._ensure_loaded()

    async def transcribe(self, audio_path: Path) -> str:
        if not self.enabled:
            return ""
        if not audio_path.exists():
            raise RuntimeError(f"Transcription input file not found: {audio_path}")
        await self._ensure_loaded()
        return await asyncio.to_thread(self._transcribe_sync, str(audio_path))

    async def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        async with self._load_lock:
            if self._model is not None:
                return
            self._model = await asyncio.to_thread(self._load_model_sync)
            logger.info("Reference transcriber is ready model=%s", self.model_name)

    def _load_model_sync(self) -> Any:
        try:
            from faster_whisper import WhisperModel
        except Exception as error:
            raise RuntimeError(
                "faster-whisper is required for voice transcription. "
                "Install dependency and model runtime."
            ) from error

        return WhisperModel(
            self.model_name,
            device=self.device,
            compute_type=self.compute_type,
        )

    def _transcribe_sync(self, audio_path: str) -> str:
        assert self._model is not None
        segments, _ = self._model.transcribe(
            audio_path,
            language=self.language or None,
            beam_size=5,
            vad_filter=True,
        )
        text = " ".join((segment.text or "").strip() for segment in segments).strip()
        return " ".join(text.split())
