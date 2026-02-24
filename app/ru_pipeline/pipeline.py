from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .accentor import Accentor
from .normalizer import normalize_text
from .yoficator import Yoficator


@dataclass(slots=True)
class RuPipeline:
    yoficator: Yoficator
    accentor: Accentor

    @classmethod
    def create(cls, yo_dict_path: Path, accents_dict_path: Path) -> "RuPipeline":
        return cls(
            yoficator=Yoficator(yo_dict_path),
            accentor=Accentor(accents_dict_path),
        )

    def process(self, text: str) -> str:
        text = self.yoficator.apply(text)
        text = normalize_text(text)
        text = self.accentor.apply(text)
        return text

