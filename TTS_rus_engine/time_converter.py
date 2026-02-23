"""
Модуль для конвертации времени в слова для русского языка.
"""

import re
from typing import Optional

def convert_time_in_text(text: str) -> str:
    """
    Конвертирует время в тексте в слова.
    
    Args:
        text: Исходный текст
        
    Returns:
        Текст с конвертированным временем
    """
    if not text:
        return text
    
    # Паттерны для времени
    time_patterns = [
        # 24-часовой формат: 14:30, 09:15, 23:59
        (r'\b(\d{1,2}):(\d{2})\b', convert_24_hour_time),
        # 12-часовой формат: 2:30 PM, 9:15 AM
        (r'\b(\d{1,2}):(\d{2})\s*(AM|PM|am|pm)\b', convert_12_hour_time),
        # Словами: "два часа тридцать минут"
        (r'\b(\d{1,2})\s*час(?:а|ов)?\s*(\d{1,2})?\s*минут(?:а|ы|у)?\b', convert_time_words),
    ]
    
    result = text
    
    for pattern, converter in time_patterns:
        result = re.sub(pattern, converter, result, flags=re.IGNORECASE)
    
    return result

def convert_24_hour_time(match) -> str:
    """Конвертирует время в 24-часовом формате."""
    hours = int(match.group(1))
    minutes = int(match.group(2))
    
    return format_time_24h(hours, minutes)

def convert_12_hour_time(match) -> str:
    """Конвертирует время в 12-часовом формате."""
    hours = int(match.group(1))
    minutes = int(match.group(2))
    period = match.group(3).upper()
    
    # Конвертируем в 24-часовой формат
    if period == 'AM':
        if hours == 12:
            hours = 0
    elif period == 'PM':
        if hours != 12:
            hours += 12
    
    return format_time_24h(hours, minutes)

def convert_time_words(match) -> str:
    """Конвертирует время, записанное словами."""
    hours = int(match.group(1))
    minutes = int(match.group(2)) if match.group(2) else 0
    
    return format_time_24h(hours, minutes)

def format_time_24h(hours: int, minutes: int) -> str:
    """Форматирует время в 24-часовом формате словами."""
    if not (0 <= hours <= 23 and 0 <= minutes <= 59):
        return f"{hours}:{minutes:02d}"
    
    # Слова для часов
    hour_words = {
        0: "ноль", 1: "один", 2: "два", 3: "три", 4: "четыре", 5: "пять",
        6: "шесть", 7: "семь", 8: "восемь", 9: "девять", 10: "десять",
        11: "одиннадцать", 12: "двенадцать", 13: "тринадцать", 14: "четырнадцать",
        15: "пятнадцать", 16: "шестнадцать", 17: "семнадцать", 18: "восемнадцать",
        19: "девятнадцать", 20: "двадцать", 21: "двадцать один", 22: "двадцать два",
        23: "двадцать три"
    }
    
    # Слова для минут
    minute_words = {
        0: "ноль", 1: "одна", 2: "две", 3: "три", 4: "четыре", 5: "пять",
        6: "шесть", 7: "семь", 8: "восемь", 9: "девять", 10: "десять",
        11: "одиннадцать", 12: "двенадцать", 13: "тринадцать", 14: "четырнадцать",
        15: "пятнадцать", 16: "шестнадцать", 17: "семнадцать", 18: "восемнадцать",
        19: "девятнадцать", 20: "двадцать", 21: "двадцать одна", 22: "двадцать две",
        23: "двадцать три", 24: "двадцать четыре", 25: "двадцать пять",
        26: "двадцать шесть", 27: "двадцать семь", 28: "двадцать восемь",
        29: "двадцать девять", 30: "тридцать", 31: "тридцать одна", 32: "тридцать две",
        33: "тридцать три", 34: "тридцать четыре", 35: "тридцать пять",
        36: "тридцать шесть", 37: "тридцать семь", 38: "тридцать восемь",
        39: "тридцать девять", 40: "сорок", 41: "сорок одна", 42: "сорок две",
        43: "сорок три", 44: "сорок четыре", 45: "сорок пять", 46: "сорок шесть",
        47: "сорок семь", 48: "сорок восемь", 49: "сорок девять", 50: "пятьдесят",
        51: "пятьдесят одна", 52: "пятьдесят две", 53: "пятьдесят три",
        54: "пятьдесят четыре", 55: "пятьдесят пять", 56: "пятьдесят шесть",
        57: "пятьдесят семь", 58: "пятьдесят восемь", 59: "пятьдесят девять"
    }
    
    hour_word = hour_words[hours]
    minute_word = minute_words[minutes]
    
    # Формируем результат
    if minutes == 0:
        if hours == 1:
            return f"{hour_word} час"
        elif hours in [2, 3, 4]:
            return f"{hour_word} часа"
        else:
            return f"{hour_word} часов"
    else:
        if hours == 1:
            if minutes == 1:
                return f"{hour_word} час {minute_word} минута"
            elif minutes in [2, 3, 4]:
                return f"{hour_word} час {minute_word} минуты"
            else:
                return f"{hour_word} час {minute_word} минут"
        elif hours in [2, 3, 4]:
            if minutes == 1:
                return f"{hour_word} часа {minute_word} минута"
            elif minutes in [2, 3, 4]:
                return f"{hour_word} часа {minute_word} минуты"
            else:
                return f"{hour_word} часа {minute_word} минут"
        else:
            if minutes == 1:
                return f"{hour_word} часов {minute_word} минута"
            elif minutes in [2, 3, 4]:
                return f"{hour_word} часов {minute_word} минуты"
            else:
                return f"{hour_word} часов {minute_word} минут"

def convert_time_range_in_text(text: str) -> str:
    """
    Конвертирует временные диапазоны в тексте.
    
    Args:
        text: Исходный текст
        
    Returns:
        Текст с конвертированными временными диапазонами
    """
    if not text:
        return text
    
    # Паттерн для временных диапазонов: 9:00-17:00, 14:30-15:45
    pattern = r'\b(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})\b'
    
    def convert_range(match):
        start_hours = int(match.group(1))
        start_minutes = int(match.group(2))
        end_hours = int(match.group(3))
        end_minutes = int(match.group(4))
        
        start_time = format_time_24h(start_hours, start_minutes)
        end_time = format_time_24h(end_hours, end_minutes)
        
        return f"с {start_time} до {end_time}"
    
    return re.sub(pattern, convert_range, text)

def convert_time_expressions_in_text(text: str) -> str:
    """
    Конвертирует временные выражения в тексте.
    
    Args:
        text: Исходный текст
        
    Returns:
        Текст с конвертированными временными выражениями
    """
    if not text:
        return text
    
    # Паттерны для временных выражений
    patterns = [
        # "в 14:30" -> "в четырнадцать тридцать"
        (r'\bв\s+(\d{1,2}):(\d{2})\b', lambda m: f"в {format_time_24h(int(m.group(1)), int(m.group(2)))}"),
        # "до 18:00" -> "до восемнадцати часов"
        (r'\bдо\s+(\d{1,2}):(\d{2})\b', lambda m: f"до {format_time_24h(int(m.group(1)), int(m.group(2)))}"),
        # "после 12:00" -> "после двенадцати часов"
        (r'\bпосле\s+(\d{1,2}):(\d{2})\b', lambda m: f"после {format_time_24h(int(m.group(1)), int(m.group(2)))}"),
        # "около 15:30" -> "около пятнадцати тридцати"
        (r'\bоколо\s+(\d{1,2}):(\d{2})\b', lambda m: f"около {format_time_24h(int(m.group(1)), int(m.group(2)))}"),
    ]
    
    result = text
    
    for pattern, converter in patterns:
        result = re.sub(pattern, converter, result, flags=re.IGNORECASE)
    
    return result

def convert_all_time_in_text(text: str) -> str:
    """
    Конвертирует все виды времени в тексте.
    
    Args:
        text: Исходный текст
        
    Returns:
        Текст с конвертированным временем
    """
    if not text:
        return text
    
    # Применяем все конвертеры по порядку
    result = convert_time_in_text(text)
    result = convert_time_range_in_text(result)
    result = convert_time_expressions_in_text(result)
    
    return result
