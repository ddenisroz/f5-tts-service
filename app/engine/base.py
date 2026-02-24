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
        volume_level: float = 50.0,
        metadata: dict[str, Any] | None = None,
    ) -> SynthesisResult:  # pragma: no cover - interface
        raise NotImplementedError

