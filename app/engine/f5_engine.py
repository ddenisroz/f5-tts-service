from __future__ import annotations

import io
import logging
import math
import struct
import wave
from pathlib import Path
from time import perf_counter

from .base import BaseTtsEngine, SynthesisResult

logger = logging.getLogger(__name__)


class F5Engine(BaseTtsEngine):
    def __init__(self, *, mode: str, upstream_dir: Path, russian_weights_dir: Path) -> None:
        self.mode = mode.strip().lower()
        self.upstream_dir = upstream_dir
        self.russian_weights_dir = russian_weights_dir
        self._ready = False

    @property
    def ready(self) -> bool:
        return self._ready

    async def prewarm(self) -> None:
        if self.mode == "real":
            if not self.upstream_dir.exists():
                raise RuntimeError(f"F5 upstream directory not found: {self.upstream_dir}")
            if not self.russian_weights_dir.exists():
                raise RuntimeError(f"F5 russian weights not found: {self.russian_weights_dir}")
            # Real engine integration point:
            # here a dedicated wrapper can load model/tokenizer/vocoder from upstream.
            logger.info("Real mode prewarm completed (wrapper hook)")
        else:
            logger.info("Mock mode prewarm completed")
        self._ready = True

    async def synthesize(
        self,
        *,
        text: str,
        voice: str,
        volume_level: float = 50.0,
        metadata: dict | None = None,
    ) -> SynthesisResult:
        started = perf_counter()
        # Mock fallback is deterministic and fast for contract/perf pipeline tests.
        sample_rate = 24000
        duration = max(0.35, min(8.0, 0.035 * len(text)))
        frequency = 160.0 + (hash(voice) % 220)
        amplitude = max(0.05, min(1.0, volume_level / 100.0)) * 0.45
        audio_bytes = _generate_sine_wav(
            sample_rate=sample_rate,
            duration_sec=duration,
            frequency=frequency,
            amplitude=amplitude,
        )
        elapsed = perf_counter() - started
        return SynthesisResult(
            audio_bytes=audio_bytes,
            duration_sec=duration,
            sample_rate=sample_rate,
            voice=voice,
            meta={
                "engine_mode": self.mode,
                "inference_time_sec": round(elapsed, 4),
            },
        )


def _generate_sine_wav(
    *,
    sample_rate: int,
    duration_sec: float,
    frequency: float,
    amplitude: float,
) -> bytes:
    frames = int(sample_rate * duration_sec)
    pcm = bytearray()
    for i in range(frames):
        phase = 2.0 * math.pi * frequency * i / sample_rate
        value = int(32767.0 * amplitude * math.sin(phase))
        pcm.extend(struct.pack("<h", value))

    with io.BytesIO() as buff:
        with wave.open(buff, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(bytes(pcm))
        return buff.getvalue()

