from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .accentor import Accentor
from .normalizer import normalize_text
from .yoficator import Yoficator

LONG_SEQ_RE = re.compile(r"(.)\1{3,}", flags=re.UNICODE)
SPACE_RE = re.compile(r"\s+", flags=re.UNICODE)


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

    @staticmethod
    def _preclean(text: str) -> str:
        text = SPACE_RE.sub(" ", (text or "").strip())
        if not text:
            return ""
        if not any(ch.isalnum() for ch in text):
            return ""
        text = LONG_SEQ_RE.sub(r"\1\1\1", text)
        return SPACE_RE.sub(" ", text).strip()

    def process(self, text: str) -> str:
        text = self._preclean(text)
        if not text:
            return ""
        text = self.yoficator.apply(text)
        text = normalize_text(text)
        text = self.accentor.apply(text)
        text = SPACE_RE.sub(" ", text).strip()
        if text and text[-1] not in ".!?":
            text = f"{text}."
        return text
