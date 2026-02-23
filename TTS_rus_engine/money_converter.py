"""
Модуль для конвертации денежных сумм в слова для русского языка.
"""
import re
from typing import Optional, Tuple

def convert_money_in_text(text: str) -> str:
    """
    Конвертирует денежные суммы в тексте в слова.
    
    Args:
        text: Исходный текст
        
    Returns:
        Текст с конвертированными денежными суммами
    """
    if not text:
        return text
    money_patterns = [('\\b(\\d+(?:[.,]\\d+)?)\\s*(?:руб|рублей?|р\\.?)\\b', convert_rubles), ('\\b\\$?(\\d+(?:[.,]\\d+)?)\\s*(?:долларов?|долл\\.?|usd)\\b', convert_dollars), ('Text cleaned.', convert_euros), ('\\b(\\d+)\\s*(?:коп|копеек?|коп\\.?)\\b', convert_kopecks), ('\\b(\\d+)\\s*(?:цент|центов?|ц\\.?)\\b', convert_cents)]
    result = text
    for (pattern, converter) in money_patterns:
        result = re.sub(pattern, converter, result, flags=re.IGNORECASE)
    return result

def convert_rubles(match) -> str:
    """Конвертирует рубли в слова."""
    amount_str = match.group(1).replace(',', '.')
    amount = float(amount_str)
    return format_rubles(amount)

def convert_dollars(match) -> str:
    """Конвертирует доллары в слова."""
    amount_str = match.group(1).replace(',', '.')
    amount = float(amount_str)
    return format_dollars(amount)

def convert_euros(match) -> str:
    """Конвертирует евро в слова."""
    amount_str = match.group(1).replace(',', '.')
    amount = float(amount_str)
    return format_euros(amount)

def convert_kopecks(match) -> str:
    """Конвертирует копейки в слова."""
    amount = int(match.group(1))
    return format_kopecks(amount)

def convert_cents(match) -> str:
    """Конвертирует центы в слова."""
    amount = int(match.group(1))
    return format_cents(amount)

def format_rubles(amount: float) -> str:
    """Форматирует рубли словами."""
    if amount < 0:
        return f'минус {format_rubles(-amount)}'
    if amount == 0:
        return 'ноль рублей'
    rubles = int(amount)
    kopecks = int((amount - rubles) * 100)
    result_parts = []
    if rubles > 0:
        rubles_word = format_number_with_currency(rubles, 'рубль', 'рубля', 'рублей')
        result_parts.append(rubles_word)
    if kopecks > 0:
        kopecks_word = format_number_with_currency(kopecks, 'копейка', 'копейки', 'копеек')
        result_parts.append(kopecks_word)
    return ' '.join(result_parts)

def format_dollars(amount: float) -> str:
    """Форматирует доллары словами."""
    if amount < 0:
        return f'минус {format_dollars(-amount)}'
    if amount == 0:
        return 'ноль долларов'
    dollars = int(amount)
    cents = int((amount - dollars) * 100)
    result_parts = []
    if dollars > 0:
        dollars_word = format_number_with_currency(dollars, 'доллар', 'доллара', 'долларов')
        result_parts.append(dollars_word)
    if cents > 0:
        cents_word = format_number_with_currency(cents, 'цент', 'цента', 'центов')
        result_parts.append(cents_word)
    return ' '.join(result_parts)

def format_euros(amount: float) -> str:
    """Форматирует евро словами."""
    if amount < 0:
        return f'минус {format_euros(-amount)}'
    if amount == 0:
        return 'ноль евро'
    euros = int(amount)
    cents = int((amount - euros) * 100)
    result_parts = []
    if euros > 0:
        euros_word = format_number_with_currency(euros, 'евро', 'евро', 'евро')
        result_parts.append(euros_word)
    if cents > 0:
        cents_word = format_number_with_currency(cents, 'цент', 'цента', 'центов')
        result_parts.append(cents_word)
    return ' '.join(result_parts)

def format_kopecks(amount: int) -> str:
    """Форматирует копейки словами."""
    if amount < 0:
        return f'минус {format_kopecks(-amount)}'
    if amount == 0:
        return 'ноль копеек'
    return format_number_with_currency(amount, 'копейка', 'копейки', 'копеек')

def format_cents(amount: int) -> str:
    """Форматирует центы словами."""
    if amount < 0:
        return f'минус {format_cents(-amount)}'
    if amount == 0:
        return 'ноль центов'
    return format_number_with_currency(amount, 'цент', 'цента', 'центов')

def format_number_with_currency(number: int, form1: str, form2: str, form5: str) -> str:
    """Форматирует число с валютой в правильной форме."""
    if number < 0:
        return f'минус {format_number_with_currency(-number, form1, form2, form5)}'
    if number == 0:
        return f'ноль {form5}'
    number_word = format_number(number)
    last_digit = number % 10
    last_two_digits = number % 100
    if last_two_digits in [11, 12, 13, 14]:
        currency_form = form5
    elif last_digit == 1:
        currency_form = form1
    elif last_digit in [2, 3, 4]:
        currency_form = form2
    else:
        currency_form = form5
    return f'{number_word} {currency_form}'

def format_small_number(number: int) -> str:
    """Форматирует небольшие числа (до 99) словами."""
    if number < 0:
        return f'минус {format_small_number(-number)}'
    if number == 0:
        return 'ноль'
    ones = {0: '', 1: 'один', 2: 'два', 3: 'три', 4: 'четыре', 5: 'пять', 6: 'шесть', 7: 'семь', 8: 'восемь', 9: 'девять'}
    tens = {0: '', 10: 'десять', 11: 'одиннадцать', 12: 'двенадцать', 13: 'тринадцать', 14: 'четырнадцать', 15: 'пятнадцать', 16: 'шестнадцать', 17: 'семнадцать', 18: 'восемнадцать', 19: 'девятнадцать', 20: 'двадцать', 30: 'тридцать', 40: 'сорок', 50: 'пятьдесят', 60: 'шестьдесят', 70: 'семьдесят', 80: 'восемьдесят', 90: 'девяносто'}
    if number in tens:
        return tens[number]
    tens_part = number // 10 * 10
    ones_part = number % 10
    result_parts = []
    if tens_part > 0:
        result_parts.append(tens[tens_part])
    if ones_part > 0:
        result_parts.append(ones[ones_part])
    return ' '.join(result_parts)

def format_number(number: int) -> str:
    """Форматирует число словами."""
    if number < 0:
        return f'минус {format_number(-number)}'
    if number == 0:
        return 'ноль'
    ones = {0: '', 1: 'один', 2: 'два', 3: 'три', 4: 'четыре', 5: 'пять', 6: 'шесть', 7: 'семь', 8: 'восемь', 9: 'девять'}
    tens = {0: '', 10: 'десять', 11: 'одиннадцать', 12: 'двенадцать', 13: 'тринадцать', 14: 'четырнадцать', 15: 'пятнадцать', 16: 'шестнадцать', 17: 'семнадцать', 18: 'восемнадцать', 19: 'девятнадцать', 20: 'двадцать', 30: 'тридцать', 40: 'сорок', 50: 'пятьдесят', 60: 'шестьдесят', 70: 'семьдесят', 80: 'восемьдесят', 90: 'девяносто'}
    hundreds = {0: '', 100: 'сто', 200: 'двести', 300: 'триста', 400: 'четыреста', 500: 'пятьсот', 600: 'шестьсот', 700: 'семьсот', 800: 'восемьсот', 900: 'девятьсот'}
    thousands = {0: '', 1000: 'одна тысяча', 2000: 'две тысячи', 3000: 'три тысячи', 4000: 'четыре тысячи', 5000: 'пять тысяч', 6000: 'шесть тысяч', 7000: 'семь тысяч', 8000: 'восемь тысяч', 9000: 'девять тысяч'}
    millions = {0: '', 1000000: 'один миллион', 2000000: 'два миллиона', 3000000: 'три миллиона', 4000000: 'четыре миллиона', 5000000: 'пять миллионов', 6000000: 'шесть миллионов', 7000000: 'семь миллионов', 8000000: 'восемь миллионов', 9000000: 'девять миллионов'}
    billions = {0: '', 1000000000: 'один миллиард', 2000000000: 'два миллиарда', 3000000000: 'три миллиарда', 4000000000: 'четыре миллиарда', 5000000000: 'пять миллиардов', 6000000000: 'шесть миллиардов', 7000000000: 'семь миллиардов', 8000000000: 'восемь миллиардов', 9000000000: 'девять миллиардов'}
    result_parts = []
    billions_part = number // 1000000000 * 1000000000
    if billions_part > 0:
        if billions_part in billions:
            result_parts.append(billions[billions_part])
        else:
            billions_count = billions_part // 1000000000
            if billions_count == 1:
                result_parts.append('один миллиард')
            elif billions_count in [2, 3, 4]:
                billions_word = format_small_number(billions_count)
                result_parts.append(f'{billions_word} миллиарда')
            else:
                billions_word = format_small_number(billions_count)
                result_parts.append(f'{billions_word} миллиардов')
    millions_part = number % 1000000000 // 1000000 * 1000000
    if millions_part > 0:
        if millions_part in millions:
            result_parts.append(millions[millions_part])
        else:
            millions_count = millions_part // 1000000
            if millions_count == 1:
                result_parts.append('один миллион')
            elif millions_count in [2, 3, 4]:
                millions_word = format_small_number(millions_count)
                result_parts.append(f'{millions_word} миллиона')
            else:
                millions_word = format_small_number(millions_count)
                result_parts.append(f'{millions_word} миллионов')
    thousands_part = number % 1000000 // 1000 * 1000
    if thousands_part > 0:
        if thousands_part in thousands:
            result_parts.append(thousands[thousands_part])
        else:
            thousands_count = thousands_part // 1000
            if thousands_count == 1:
                result_parts.append('одна тысяча')
            elif thousands_count in [2, 3, 4]:
                thousands_word = format_small_number(thousands_count)
                result_parts.append(f'{thousands_word} тысячи')
            else:
                thousands_word = format_small_number(thousands_count)
                result_parts.append(f'{thousands_word} тысяч')
    hundreds_part = number % 1000 // 100 * 100
    if hundreds_part > 0:
        if hundreds_part in hundreds:
            result_parts.append(hundreds[hundreds_part])
        else:
            hundreds_count = hundreds_part // 100
            hundreds_word = format_small_number(hundreds_count)
            result_parts.append(f'{hundreds_word}сот')
    remainder = number % 100
    if remainder > 0:
        if remainder in tens:
            result_parts.append(tens[remainder])
        else:
            tens_part = remainder // 10 * 10
            ones_part = remainder % 10
            if tens_part > 0:
                result_parts.append(tens[tens_part])
            if ones_part > 0:
                result_parts.append(ones[ones_part])
    return ' '.join(result_parts)

def convert_money_range_in_text(text: str) -> str:
    """
    Конвертирует диапазоны денежных сумм в тексте.
    
    Args:
        text: Исходный текст
        
    Returns:
        Текст с конвертированными диапазонами денежных сумм
    """
    if not text:
        return text
    pattern = '\\b(\\d+(?:[.,]\\d+)?)-(\\d+(?:[.,]\\d+)?)\\s*(?:руб|рублей?|р\\.?)\\b'

    def convert_range(match):
        start_amount = float(match.group(1).replace(',', '.'))
        end_amount = float(match.group(2).replace(',', '.'))
        start_money = format_rubles(start_amount)
        end_money = format_rubles(end_amount)
        return f'от {start_money} до {end_money}'
    return re.sub(pattern, convert_range, text, flags=re.IGNORECASE)

def convert_money_expressions_in_text(text: str) -> str:
    """
    Конвертирует выражения с денежными суммами в тексте.
    
    Args:
        text: Исходный текст
        
    Returns:
        Текст с конвертированными выражениями с денежными суммами
    """
    if not text:
        return text
    patterns = [('\\bза\\s+(\\d+(?:[.,]\\d+)?)\\s*(?:руб|рублей?|р\\.?)\\b', lambda m: f"за {format_rubles(float(m.group(1).replace(',', '.')))}"), ('\\bдо\\s+(\\d+(?:[.,]\\d+)?)\\s*(?:руб|рублей?|р\\.?)\\b', lambda m: f"до {format_rubles(float(m.group(1).replace(',', '.')))}"), ('\\bболее\\s+(\\d+(?:[.,]\\d+)?)\\s*(?:руб|рублей?|р\\.?)\\b', lambda m: f"более {format_rubles(float(m.group(1).replace(',', '.')))}"), ('\\bменее\\s+(\\d+(?:[.,]\\d+)?)\\s*(?:руб|рублей?|р\\.?)\\b', lambda m: f"менее {format_rubles(float(m.group(1).replace(',', '.')))}")]
    result = text
    for (pattern, converter) in patterns:
        result = re.sub(pattern, converter, result, flags=re.IGNORECASE)
    return result

def convert_all_money_in_text(text: str) -> str:
    """
    Конвертирует все виды денежных сумм в тексте.
    
    Args:
        text: Исходный текст
        
    Returns:
        Текст с конвертированными денежными суммами
    """
    if not text:
        return text
    result = convert_money_in_text(text)
    result = convert_money_range_in_text(result)
    result = convert_money_expressions_in_text(result)
    return result
