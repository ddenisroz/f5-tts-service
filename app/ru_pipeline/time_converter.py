from __future__ import annotations

import re

from .number_converter import choose_plural, integer_to_words

TIME_RE = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")


def convert_all_time_in_text(text: str) -> str:
    return TIME_RE.sub(_replace_time, text)


def _replace_time(match: re.Match[str]) -> str:
    hours = int(match.group(1))
    minutes = int(match.group(2))
    hours_words = integer_to_words(hours)
    minutes_words = integer_to_words(minutes, gender="feminine")
    hours_suffix = choose_plural(hours, "час", "часа", "часов")
    minutes_suffix = choose_plural(minutes, "минута", "минуты", "минут")
    return f"{hours_words} {hours_suffix} {minutes_words} {minutes_suffix}"
