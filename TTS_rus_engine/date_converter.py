"""
Модуль для конвертации дат в слова для русского языка.
"""

import re
from typing import Optional, Tuple
from datetime import datetime

def convert_date_in_text(text: str) -> str:
    """
    Конвертирует даты в тексте в слова.
    
    Args:
        text: Исходный текст
        
    Returns:
        Текст с конвертированными датами
    """
    if not text:
        return text
    
    # Паттерны для дат
    date_patterns = [
        # DD.MM.YYYY: 25.12.2024, 01.01.2025
        (r'\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b', convert_dd_mm_yyyy),
        # DD.MM.YY: 25.12.24, 01.01.25
        (r'\b(\d{1,2})\.(\d{1,2})\.(\d{2})\b', convert_dd_mm_yy),
        # YYYY-MM-DD: 2024-12-25, 2025-01-01
        (r'\b(\d{4})-(\d{1,2})-(\d{1,2})\b', convert_yyyy_mm_dd),
        # DD/MM/YYYY: 25/12/2024, 01/01/2025
        (r'\b(\d{1,2})/(\d{1,2})/(\d{4})\b', convert_dd_mm_yyyy),
        # DD/MM/YY: 25/12/24, 01/01/25
        (r'\b(\d{1,2})/(\d{1,2})/(\d{2})\b', convert_dd_mm_yy),
    ]
    
    result = text
    
    for pattern, converter in date_patterns:
        result = re.sub(pattern, converter, result)
    
    return result

def convert_dd_mm_yyyy(match) -> str:
    """Конвертирует дату в формате DD.MM.YYYY."""
    day = int(match.group(1))
    month = int(match.group(2))
    year = int(match.group(3))
    
    return format_date(day, month, year)

def convert_dd_mm_yy(match) -> str:
    """Конвертирует дату в формате DD.MM.YY."""
    day = int(match.group(1))
    month = int(match.group(2))
    year = int(match.group(3))
    
    # Конвертируем двузначный год в четырехзначный
    if year < 50:
        year += 2000
    else:
        year += 1900
    
    return format_date(day, month, year)

def convert_yyyy_mm_dd(match) -> str:
    """Конвертирует дату в формате YYYY-MM-DD."""
    year = int(match.group(1))
    month = int(match.group(2))
    day = int(match.group(3))
    
    return format_date(day, month, year)

def format_date(day: int, month: int, year: int) -> str:
    """Форматирует дату словами."""
    if not (1 <= day <= 31 and 1 <= month <= 12 and 1000 <= year <= 9999):
        return f"{day:02d}.{month:02d}.{year}"
    
    # Слова для дней
    day_words = {
        1: "первое", 2: "второе", 3: "третье", 4: "четвертое", 5: "пятое",
        6: "шестое", 7: "седьмое", 8: "восьмое", 9: "девятое", 10: "десятое",
        11: "одиннадцатое", 12: "двенадцатое", 13: "тринадцатое", 14: "четырнадцатое",
        15: "пятнадцатое", 16: "шестнадцатое", 17: "семнадцатое", 18: "восемнадцатое",
        19: "девятнадцатое", 20: "двадцатое", 21: "двадцать первое", 22: "двадцать второе",
        23: "двадцать третье", 24: "двадцать четвертое", 25: "двадцать пятое",
        26: "двадцать шестое", 27: "двадцать седьмое", 28: "двадцать восьмое",
        29: "двадцать девятое", 30: "тридцатое", 31: "тридцать первое"
    }
    
    # Слова для месяцев
    month_words = {
        1: "января", 2: "февраля", 3: "марта", 4: "апреля", 5: "мая", 6: "июня",
        7: "июля", 8: "августа", 9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"
    }
    
    # Слова для годов
    year_word = format_year(year)
    
    day_word = day_words[day]
    month_word = month_words[month]
    
    return f"{day_word} {month_word} {year_word} года"

def format_year(year: int) -> str:
    """Форматирует год словами."""
    if year < 1000 or year > 9999:
        return str(year)
    
    # Слова для тысяч
    thousands = year // 1000
    hundreds = (year % 1000) // 100
    tens = (year % 100) // 10
    ones = year % 10
    
    # Слова для тысяч
    thousand_words = {
        1: "одна тысяча", 2: "две тысячи", 3: "три тысячи", 4: "четыре тысячи",
        5: "пять тысяч", 6: "шесть тысяч", 7: "семь тысяч", 8: "восемь тысяч",
        9: "девять тысяч"
    }
    
    # Слова для сотен
    hundred_words = {
        1: "сто", 2: "двести", 3: "триста", 4: "четыреста", 5: "пятьсот",
        6: "шестьсот", 7: "семьсот", 8: "восемьсот", 9: "девятьсот"
    }
    
    # Слова для десятков и единиц
    tens_words = {
        10: "десять", 11: "одиннадцать", 12: "двенадцать", 13: "тринадцать",
        14: "четырнадцать", 15: "пятнадцать", 16: "шестнадцать", 17: "семнадцать",
        18: "восемнадцать", 19: "девятнадцать", 20: "двадцать", 21: "двадцать один",
        22: "двадцать два", 23: "двадцать три", 24: "двадцать четыре", 25: "двадцать пять",
        26: "двадцать шесть", 27: "двадцать семь", 28: "двадцать восемь", 29: "двадцать девять",
        30: "тридцать", 31: "тридцать один", 32: "тридцать два", 33: "тридцать три",
        34: "тридцать четыре", 35: "тридцать пять", 36: "тридцать шесть", 37: "тридцать семь",
        38: "тридцать восемь", 39: "тридцать девять", 40: "сорок", 41: "сорок один",
        42: "сорок два", 43: "сорок три", 44: "сорок четыре", 45: "сорок пять",
        46: "сорок шесть", 47: "сорок семь", 48: "сорок восемь", 49: "сорок девять",
        50: "пятьдесят", 51: "пятьдесят один", 52: "пятьдесят два", 53: "пятьдесят три",
        54: "пятьдесят четыре", 55: "пятьдесят пять", 56: "пятьдесят шесть", 57: "пятьдесят семь",
        58: "пятьдесят восемь", 59: "пятьдесят девять", 60: "шестьдесят", 61: "шестьдесят один",
        62: "шестьдесят два", 63: "шестьдесят три", 64: "шестьдесят четыре", 65: "шестьдесят пять",
        66: "шестьдесят шесть", 67: "шестьдесят семь", 68: "шестьдесят восемь", 69: "шестьдесят девять",
        70: "семьдесят", 71: "семьдесят один", 72: "семьдесят два", 73: "семьдесят три",
        74: "семьдесят четыре", 75: "семьдесят пять", 76: "семьдесят шесть", 77: "семьдесят семь",
        78: "семьдесят восемь", 79: "семьдесят девять", 80: "восемьдесят", 81: "восемьдесят один",
        82: "восемьдесят два", 83: "восемьдесят три", 84: "восемьдесят четыре", 85: "восемьдесят пять",
        86: "восемьдесят шесть", 87: "восемьдесят семь", 88: "восемьдесят восемь", 89: "восемьдесят девять",
        90: "девяносто", 91: "девяносто один", 92: "девяносто два", 93: "девяносто три",
        94: "девяносто четыре", 95: "девяносто пять", 96: "девяносто шесть", 97: "девяносто семь",
        98: "девяносто восемь", 99: "девяносто девять"
    }
    
    # Формируем результат
    result_parts = []
    
    # Тысячи
    if thousands > 0:
        result_parts.append(thousand_words[thousands])
    
    # Сотни
    if hundreds > 0:
        result_parts.append(hundred_words[hundreds])
    
    # Десятки и единицы
    remainder = year % 100
    if remainder > 0:
        if remainder in tens_words:
            result_parts.append(tens_words[remainder])
        else:
            # Для чисел больше 99, которые не в словаре
            if tens > 0:
                tens_word = tens_words[tens * 10]
                result_parts.append(tens_word)
            if ones > 0:
                ones_word = tens_words[ones]
                result_parts.append(ones_word)
    
    return " ".join(result_parts)

def convert_date_range_in_text(text: str) -> str:
    """
    Конвертирует диапазоны дат в тексте.
    
    Args:
        text: Исходный текст
        
    Returns:
        Текст с конвертированными диапазонами дат
    """
    if not text:
        return text
    
    # Паттерн для диапазонов дат: 01.01.2024-31.12.2024
    pattern = r'\b(\d{1,2})\.(\d{1,2})\.(\d{4})-(\d{1,2})\.(\d{1,2})\.(\d{4})\b'
    
    def convert_range(match):
        start_day = int(match.group(1))
        start_month = int(match.group(2))
        start_year = int(match.group(3))
        end_day = int(match.group(4))
        end_month = int(match.group(5))
        end_year = int(match.group(6))
        
        start_date = format_date(start_day, start_month, start_year)
        end_date = format_date(end_day, end_month, end_year)
        
        return f"с {start_date} по {end_date}"
    
    return re.sub(pattern, convert_range, text)

def convert_date_expressions_in_text(text: str) -> str:
    """
    Конвертирует временные выражения с датами в тексте.
    
    Args:
        text: Исходный текст
        
    Returns:
        Текст с конвертированными временными выражениями
    """
    if not text:
        return text
    
    # Паттерны для временных выражений с датами
    patterns = [
        # "на 25.12.2024" -> "на двадцать пятое декабря две тысячи двадцать четвертого года"
        (r'\bна\s+(\d{1,2})\.(\d{1,2})\.(\d{4})\b', lambda m: f"на {format_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))}"),
        # "до 01.01.2025" -> "до первого января две тысячи двадцать пятого года"
        (r'\bдо\s+(\d{1,2})\.(\d{1,2})\.(\d{4})\b', lambda m: f"до {format_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))}"),
        # "после 15.06.2024" -> "после пятнадцатого июня две тысячи двадцать четвертого года"
        (r'\bпосле\s+(\d{1,2})\.(\d{1,2})\.(\d{4})\b', lambda m: f"после {format_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))}"),
        # "около 10.03.2024" -> "около десятого марта две тысячи двадцать четвертого года"
        (r'\bоколо\s+(\d{1,2})\.(\d{1,2})\.(\d{4})\b', lambda m: f"около {format_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))}"),
    ]
    
    result = text
    
    for pattern, converter in patterns:
        result = re.sub(pattern, converter, result, flags=re.IGNORECASE)
    
    return result

def convert_all_dates_in_text(text: str) -> str:
    """
    Конвертирует все виды дат в тексте.
    
    Args:
        text: Исходный текст
        
    Returns:
        Текст с конвертированными датами
    """
    if not text:
        return text
    
    # Применяем все конвертеры по порядку
    result = convert_date_in_text(text)
    result = convert_date_range_in_text(result)
    result = convert_date_expressions_in_text(result)
    
    return result
