from __future__ import annotations

import json
import re
from pathlib import Path


WORD_RE = re.compile(r"\b[\w-]+\b", re.UNICODE)


class Accentor:
    def __init__(self, dictionary_path: Path) -> None:
        self.dictionary: dict[str, str] = {}
        if dictionary_path.exists():
            self.dictionary = json.loads(dictionary_path.read_text(encoding="utf-8"))

    def apply(self, text: str) -> str:
        if not self.dictionary:
            return text

        def _replace(match: re.Match[str]) -> str:
            original = match.group(0)
            replacement = self.dictionary.get(original.lower())
            return replacement or original

        return WORD_RE.sub(_replace, text)

