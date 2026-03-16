from __future__ import annotations

import re

ONES = {
    "masculine": ("ноль", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять"),
    "feminine": ("ноль", "одна", "две", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять"),
    "neuter": ("ноль", "одно", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять"),
}
TEENS = (
    "десять",
    "одиннадцать",
    "двенадцать",
    "тринадцать",
    "четырнадцать",
    "пятнадцать",
    "шестнадцать",
    "семнадцать",
    "восемнадцать",
    "девятнадцать",
)
TENS = ("", "", "двадцать", "тридцать", "сорок", "пятьдесят", "шестьдесят", "семьдесят", "восемьдесят", "девяносто")
HUNDREDS = ("", "сто", "двести", "триста", "четыреста", "пятьсот", "шестьсот", "семьсот", "восемьсот", "девятьсот")
TRIPLE_ORDERS = (
    ("", "", "", "masculine"),
    ("тысяча", "тысячи", "тысяч", "feminine"),
    ("миллион", "миллиона", "миллионов", "masculine"),
    ("миллиард", "миллиарда", "миллиардов", "masculine"),
)
NUMBER_RE = re.compile(r"\b\d+\b")


def choose_plural(number: int, one: str, few: str, many: str) -> str:
    value = abs(int(number))
    tail = value % 100
    if 11 <= tail <= 14:
        return many
    tail = value % 10
    if tail == 1:
        return one
    if 2 <= tail <= 4:
        return few
    return many


def integer_to_words(number: int, gender: str = "masculine") -> str:
    value = int(number)
    if value == 0:
        return ONES["masculine"][0]
    if value < 0:
        return f"минус {integer_to_words(-value, gender=gender)}"

    chunks: list[str] = []
    order_index = 0
    while value > 0:
        triplet = value % 1000
        if triplet:
            one, few, many, order_gender = TRIPLE_ORDERS[order_index]
            current_gender = order_gender if order_index > 0 else gender
            words = triplet_to_words(triplet, current_gender)
            if order_index > 0:
                words.append(choose_plural(triplet, one, few, many))
            chunks.append(" ".join(words))
        value //= 1000
        order_index += 1

    return " ".join(reversed(chunks)).strip()


def triplet_to_words(number: int, gender: str = "masculine") -> list[str]:
    words: list[str] = []
    hundreds = number // 100
    tens_units = number % 100
    if hundreds:
        words.append(HUNDREDS[hundreds])
    if 10 <= tens_units <= 19:
        words.append(TEENS[tens_units - 10])
        return words

    tens = tens_units // 10
    units = tens_units % 10
    if tens:
        words.append(TENS[tens])
    if units:
        words.append(ONES[gender][units])
    return words


def convert_numbers_in_text(text: str) -> str:
    return NUMBER_RE.sub(lambda match: integer_to_words(int(match.group(0))), text)
