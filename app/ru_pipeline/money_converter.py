from __future__ import annotations

import re

from .number_converter import choose_plural, integer_to_words

RUB_RE = re.compile(r"\b(\d+(?:[.,]\d{1,2})?)\s*(?:₽|руб(?:\.|ль|ля|лей)?)\b", re.IGNORECASE)
USD_RE = re.compile(r"\$(\d+(?:[.,]\d{1,2})?)|\b(\d+(?:[.,]\d{1,2})?)\s*(?:usd|дол(?:\.|лар|лара|ларов)?)\b", re.IGNORECASE)
EUR_RE = re.compile(r"€(\d+(?:[.,]\d{1,2})?)|\b(\d+(?:[.,]\d{1,2})?)\s*(?:eur|евро)\b", re.IGNORECASE)


def convert_all_money_in_text(text: str) -> str:
    updated = RUB_RE.sub(lambda match: _render_amount(_parse_amount(match.group(1)), currency="rub"), text)
    updated = USD_RE.sub(lambda match: _render_amount(_parse_amount(match.group(1) or match.group(2)), currency="usd"), updated)
    updated = EUR_RE.sub(lambda match: _render_amount(_parse_amount(match.group(1) or match.group(2)), currency="eur"), updated)
    return updated


def _parse_amount(raw: str) -> tuple[int, int]:
    normalized = (raw or "0").replace(",", ".")
    integer_part, _, fractional_raw = normalized.partition(".")
    integer = int(integer_part)
    fractional = int(fractional_raw[:2].ljust(2, "0")) if fractional_raw else 0
    return integer, fractional


def _render_amount(amount: tuple[int, int], *, currency: str) -> str:
    integer, fractional = amount
    if currency == "rub":
        return _render_currency(
            integer,
            fractional,
            ("рубль", "рубля", "рублей"),
            ("копейка", "копейки", "копеек"),
        )
    if currency == "usd":
        return _render_currency(
            integer,
            fractional,
            ("доллар", "доллара", "долларов"),
            ("цент", "цента", "центов"),
        )
    return _render_currency(
        integer,
        fractional,
        ("евро", "евро", "евро"),
        ("цент", "цента", "центов"),
    )


def _render_currency(
    integer: int,
    fractional: int,
    main_forms: tuple[str, str, str],
    minor_forms: tuple[str, str, str],
) -> str:
    chunks = [
        integer_to_words(integer),
        choose_plural(integer, *main_forms),
    ]
    if fractional:
        chunks.extend(
            [
                integer_to_words(fractional, gender="feminine"),
                choose_plural(fractional, *minor_forms),
            ]
        )
    return " ".join(chunks)
