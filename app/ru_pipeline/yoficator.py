from __future__ import annotations

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_YO_DICT_PATH = Path(__file__).with_name("yo.dat")
WORD_RE = re.compile(r"\b[А-Яа-яЁёA-Za-z-]+\b", re.UNICODE)
COMMON_REPLACEMENTS = {
    "все": "всё",
    "еще": "ещё",
    "ее": "её",
    "осел": "осёл",
    "шел": "шёл",
    "вел": "вёл",
}
EL_EXCEPTIONS = {
    "умел",
    "смел",
    "удел",
    "предел",
    "хотел",
    "сидел",
    "летел",
    "смотрел",
    "дел",
}


class Yoficator:
    def __init__(self, dictionary_path: Path) -> None:
        self.dictionary: dict[str, str] = {}
        self._load_bundled_dictionary()
        if dictionary_path.resolve() != DEFAULT_YO_DICT_PATH.resolve():
            self._load_dictionary(dictionary_path)

    def apply(self, text: str) -> str:
        def _replace(match: re.Match[str]) -> str:
            original = match.group(0)
            lowered = original.lower()
            replacement = self.dictionary.get(lowered)
            if replacement:
                return self._apply_case(original, replacement)
            return self._apply_heuristics(original)

        return WORD_RE.sub(_replace, text)

    def _apply_heuristics(self, word: str) -> str:
        lowered = word.lower()
        if lowered in COMMON_REPLACEMENTS:
            return self._apply_case(word, COMMON_REPLACEMENTS[lowered])
        if lowered.endswith("ел") and len(lowered) > 3 and lowered not in EL_EXCEPTIONS:
            return self._apply_case(word, re.sub("е(?=л$)", "ё", lowered))
        return word

    def _load_bundled_dictionary(self) -> None:
        if DEFAULT_YO_DICT_PATH.exists():
            self._load_dictionary(DEFAULT_YO_DICT_PATH)

    def _load_dictionary(self, dictionary_path: Path) -> None:
        if not dictionary_path.exists():
            logger.warning("Yo dictionary file is missing: %s", dictionary_path)
            return
        try:
            if dictionary_path.suffix.lower() == ".json":
                payload = json.loads(dictionary_path.read_text(encoding="utf-8"))
                self.dictionary.update({str(key).lower(): str(value) for key, value in payload.items()})
                logger.info("Loaded yo dictionary overrides from %s entries=%s", dictionary_path, len(payload))
                return
            self.dictionary.update(self._load_dat_dictionary(dictionary_path))
            logger.info("Loaded yo dictionary from %s entries=%s", dictionary_path, len(self.dictionary))
        except Exception:
            logger.exception("Failed to load yo dictionary from %s", dictionary_path)

    @staticmethod
    def _load_dat_dictionary(dictionary_path: Path) -> dict[str, str]:
        output: dict[str, str] = {}
        for raw_line in dictionary_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "|" in line:
                source, target = line.split("|", 1)
            else:
                target = line
                source = line.replace("ё", "е")
            source = source.strip().lower()
            target = target.strip()
            if source and target:
                output[source] = target
        return output

    @staticmethod
    def _apply_case(original: str, replacement: str) -> str:
        if original.isupper():
            return replacement.upper()
        if original[:1].isupper():
            return replacement[:1].upper() + replacement[1:]
        return replacement

