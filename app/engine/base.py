from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SynthesisResult:
    audio_bytes: bytes
    duration_sec: float
    sample_rate: int
    voice: str
    meta: dict[str, Any] = field(default_factory=dict)


class BaseTtsEngine:
    async def prewarm(self) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    async def synthesize(
        self,
        *,
        text: str,
        voice: str,
        ref_audio_path: str,
        ref_text: str,
        volume_level: float = 50.0,
        cfg_strength: float | None = None,
        speed_preset: str | None = None,
        remove_silence: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> SynthesisResult:  # pragma: no cover - interface
        raise NotImplementedError
