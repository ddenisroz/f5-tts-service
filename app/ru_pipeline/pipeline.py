from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .accentor import Accentor
from .date_converter import convert_all_dates_in_text
from .money_converter import convert_all_money_in_text
from .number_converter import convert_numbers_in_text
from .time_converter import convert_all_time_in_text
from .yoficator import Yoficator

LONG_SEQ_RE = re.compile(r"(.)\1{3,}", flags=re.UNICODE)
SPACE_RE = re.compile(r"\s+", flags=re.UNICODE)
CYRILLIC_RE = re.compile(r"[а-яё]", flags=re.IGNORECASE)
LATIN_RE = re.compile(r"[a-z]", flags=re.IGNORECASE)

logger = logging.getLogger(__name__)


class StageLogger(Protocol):
    def info(self, msg: str, *args, **kwargs) -> None: ...


@dataclass(slots=True)
class RuPipeline:
    yoficator: Yoficator
    accentor: Accentor

    @classmethod
    def create(
        cls,
        yo_dict_path: Path,
        accents_dict_path: Path,
        *,
        ruaccent_enabled: bool = True,
    ) -> "RuPipeline":
        return cls(
            yoficator=Yoficator(yo_dict_path),
            accentor=Accentor(accents_dict_path, enabled=ruaccent_enabled),
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

    @staticmethod
    def detect_language(text: str) -> str:
        cyrillic_count = len(CYRILLIC_RE.findall(text or ""))
        latin_count = len(LATIN_RE.findall(text or ""))
        if cyrillic_count > latin_count:
            return "russian"
        if latin_count > cyrillic_count:
            return "english"
        if cyrillic_count > 0:
            return "russian"
        return "russian"

    def process(self, text: str, logger: StageLogger | None = None) -> str:
        text = self._preclean(text)
        if not text:
            if logger is not None:
                logger.info("RU preprocessing produced empty text after preclean")
            return ""
        pipeline_logger = logger or globals()["logger"]
        language = self.detect_language(text)
        pipeline_logger.info("RU preprocessing language=%s", language)
        if language == "russian":
            text = self._apply_stage("yo", text, self.yoficator.apply, pipeline_logger)
            text = self._apply_stage("date_normalization", text, convert_all_dates_in_text, pipeline_logger)
            text = self._apply_stage("time_normalization", text, convert_all_time_in_text, pipeline_logger)
            text = self._apply_stage("money_normalization", text, convert_all_money_in_text, pipeline_logger)
            text = self._apply_stage("number_normalization", text, convert_numbers_in_text, pipeline_logger)
            text = self._apply_stage("accenting", text, self.accentor.apply, pipeline_logger)
        else:
            pipeline_logger.info("Skipping RU-only preprocessing for language=%s", language)
        text = SPACE_RE.sub(" ", text).strip()
        if text and text[-1] not in ".!?":
            text = f"{text}."
        pipeline_logger.info("RU preprocessing output=%r", text)
        return text

    @staticmethod
    def _apply_stage(stage_name: str, text: str, transform, pipeline_logger: StageLogger) -> str:
        updated = transform(text)
        if updated != text:
            pipeline_logger.info("RU preprocessing stage=%s before=%r after=%r", stage_name, text, updated)
        else:
            pipeline_logger.info("RU preprocessing stage=%s no_change=true", stage_name)
        return updated
