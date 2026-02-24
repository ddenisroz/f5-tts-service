from __future__ import annotations

import re
from typing import Callable

from num2words import num2words


DATE_RE = re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})\b")
TIME_RE = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")
MONEY_USD_RE = re.compile(r"\$(\d+(?:[.,]\d{1,2})?)")
MONEY_RUB_RE = re.compile(r"\b(\d+(?:[.,]\d{1,2})?)\s?(?:₽|руб(?:\.|лей|ля|ль)?)\b", re.IGNORECASE)
NUMBER_RE = re.compile(r"\b\d+\b")

MONTHS_RU = [
    "",
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
]


def _safe_num2words(number: int, lang: str = "ru") -> str:
    try:
        return num2words(number, lang=lang)
    except Exception:
        return str(number)


def _apply_regex(text: str, pattern: re.Pattern[str], fn: Callable[[re.Match[str]], str]) -> str:
    return pattern.sub(fn, text)


def normalize_text(text: str) -> str:
    def repl_date(match: re.Match[str]) -> str:
        day = int(match.group(1))
        month = int(match.group(2))
        year_raw = match.group(3)
        year = int(year_raw) if len(year_raw) == 4 else 2000 + int(year_raw)
        if month < 1 or month > 12:
            return match.group(0)
        day_text = _safe_num2words(day)
        year_text = _safe_num2words(year)
        return f"{day_text} {MONTHS_RU[month]} {year_text} года"

    def repl_time(match: re.Match[str]) -> str:
        hh = int(match.group(1))
        mm = int(match.group(2))
        hh_text = _safe_num2words(hh)
        mm_text = _safe_num2words(mm)
        return f"{hh_text} часов {mm_text} минут"

    def repl_usd(match: re.Match[str]) -> str:
        raw = match.group(1).replace(",", ".")
        amount = float(raw)
        integer = int(amount)
        cents = int(round((amount - integer) * 100))
        text = f"{_safe_num2words(integer)} долларов"
        if cents:
            text += f" {_safe_num2words(cents)} центов"
        return text

    def repl_rub(match: re.Match[str]) -> str:
        raw = match.group(1).replace(",", ".")
        amount = float(raw)
        integer = int(amount)
        kopecks = int(round((amount - integer) * 100))
        text = f"{_safe_num2words(integer)} рублей"
        if kopecks:
            text += f" {_safe_num2words(kopecks)} копеек"
        return text

    def repl_number(match: re.Match[str]) -> str:
        return _safe_num2words(int(match.group(0)))

    text = _apply_regex(text, DATE_RE, repl_date)
    text = _apply_regex(text, TIME_RE, repl_time)
    text = _apply_regex(text, MONEY_USD_RE, repl_usd)
    text = _apply_regex(text, MONEY_RUB_RE, repl_rub)
    text = _apply_regex(text, NUMBER_RE, repl_number)
    return text

