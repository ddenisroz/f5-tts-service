from __future__ import annotations

import re

from .number_converter import integer_to_words

DATE_PATTERNS = (
    re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b"),
    re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b"),
    re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b"),
    re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{2})\b"),
    re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{2})\b"),
)

MONTHS = {
    1: "января",
    2: "февраля",
    3: "марта",
    4: "апреля",
    5: "мая",
    6: "июня",
    7: "июля",
    8: "августа",
    9: "сентября",
    10: "октября",
    11: "ноября",
    12: "декабря",
}

DAY_ORDINALS = {
    1: "первое",
    2: "второе",
    3: "третье",
    4: "четвертое",
    5: "пятое",
    6: "шестое",
    7: "седьмое",
    8: "восьмое",
    9: "девятое",
    10: "десятое",
    11: "одиннадцатое",
    12: "двенадцатое",
    13: "тринадцатое",
    14: "четырнадцатое",
    15: "пятнадцатое",
    16: "шестнадцатое",
    17: "семнадцатое",
    18: "восемнадцатое",
    19: "девятнадцатое",
    20: "двадцатое",
    21: "двадцать первое",
    22: "двадцать второе",
    23: "двадцать третье",
    24: "двадцать четвертое",
    25: "двадцать пятое",
    26: "двадцать шестое",
    27: "двадцать седьмое",
    28: "двадцать восьмое",
    29: "двадцать девятое",
    30: "тридцатое",
    31: "тридцать первое",
}


def convert_all_dates_in_text(text: str) -> str:
    updated = text
    updated = DATE_PATTERNS[0].sub(lambda m: _render_date(int(m.group(1)), int(m.group(2)), int(m.group(3))), updated)
    updated = DATE_PATTERNS[1].sub(lambda m: _render_date(int(m.group(1)), int(m.group(2)), int(m.group(3))), updated)
    updated = DATE_PATTERNS[2].sub(lambda m: _render_date(int(m.group(3)), int(m.group(2)), int(m.group(1))), updated)
    updated = DATE_PATTERNS[3].sub(lambda m: _render_date(int(m.group(1)), int(m.group(2)), _expand_year(int(m.group(3)))), updated)
    updated = DATE_PATTERNS[4].sub(lambda m: _render_date(int(m.group(1)), int(m.group(2)), _expand_year(int(m.group(3)))), updated)
    return updated


def _expand_year(year: int) -> int:
    if year < 50:
        return 2000 + year
    return 1900 + year


def _render_date(day: int, month: int, year: int) -> str:
    if day not in DAY_ORDINALS or month not in MONTHS:
        return f"{day:02d}.{month:02d}.{year}"
    return f"{DAY_ORDINALS[day]} {MONTHS[month]} {integer_to_words(year)} года"
