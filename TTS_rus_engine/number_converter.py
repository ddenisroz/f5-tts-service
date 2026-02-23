#!/usr/bin/env python3
"""
Модуль для конвертации чисел в слова на русском языке
"""
import re
import logging
from typing import Union, List
logger = logging.getLogger(__name__)

class NumberToWordsConverter:
    """Конвертер чисел в слова на русском языке"""

    def __init__(self):
        self.units = ['ноль', 'один', 'два', 'три', 'четыре', 'пять', 'шесть', 'семь', 'восемь', 'девять', 'десять', 'одиннадцать', 'двенадцать', 'тринадцать', 'четырнадцать', 'пятнадцать', 'шестнадцать', 'семнадцать', 'восемнадцать', 'девятнадцать']
        self.tens = ['', '', 'двадцать', 'тридцать', 'сорок', 'пятьдесят', 'шестьдесят', 'семьдесят', 'восемьдесят', 'девяносто']
        self.hundreds = ['', 'сто', 'двести', 'триста', 'четыреста', 'пятьсот', 'шестьсот', 'семьсот', 'восемьсот', 'девятьсот']
        self.orders = [('', '', ''), ('тысяча', 'тысячи', 'тысяч'), ('миллион', 'миллиона', 'миллионов'), ('миллиард', 'миллиарда', 'миллиардов'), ('триллион', 'триллиона', 'триллионов')]
        self.one_forms = ['один', 'одна', 'одно']
        self.two_forms = ['два', 'две', 'два']
        self.three_forms = ['три', 'три', 'три']
        self.four_forms = ['четыре', 'четыре', 'четыре']

    def _get_plural_form(self, number: int, forms: tuple) -> str:
        """Получает правильную форму множественного числа"""
        if number % 10 == 1 and number % 100 != 11:
            return forms[0]
        elif 2 <= number % 10 <= 4 and (number % 100 < 10 or number % 100 >= 20):
            return forms[1]
        else:
            return forms[2]

    def _convert_triplet(self, triplet: int, gender: str='m') -> str:
        """Конвертирует тройку цифр (0-999) в слова"""
        if triplet == 0:
            return ''
        result = []
        if triplet >= 100:
            result.append(self.hundreds[triplet // 100])
        remainder = triplet % 100
        if remainder < 20:
            if remainder > 0:
                if remainder == 1:
                    result.append(self.one_forms[0 if gender == 'm' else 1])
                elif remainder == 2:
                    result.append(self.two_forms[0 if gender == 'm' else 1])
                elif remainder == 3:
                    result.append(self.three_forms[0 if gender == 'm' else 1])
                elif remainder == 4:
                    result.append(self.four_forms[0 if gender == 'm' else 1])
                else:
                    result.append(self.units[remainder])
        else:
            tens = remainder // 10
            units = remainder % 10
            result.append(self.tens[tens])
            if units > 0:
                if units == 1:
                    result.append(self.one_forms[0 if gender == 'm' else 1])
                elif units == 2:
                    result.append(self.two_forms[0 if gender == 'm' else 1])
                elif units == 3:
                    result.append(self.three_forms[0 if gender == 'm' else 1])
                elif units == 4:
                    result.append(self.four_forms[0 if gender == 'm' else 1])
                else:
                    result.append(self.units[units])
        return ' '.join(result)

    def convert_number(self, number: Union[int, str], gender: str='m') -> str:
        """
        Конвертирует число в слова
        
        Args:
            number: Число для конвертации
            gender: Род ("m" - мужской, "f" - женский, "n" - средний)
            
        Returns:
            Число словами
        """
        try:
            if isinstance(number, str):
                number = int(number.replace(' ', '').replace(',', ''))
            if number == 0:
                return 'ноль'
            if number < 0:
                return 'минус ' + self.convert_number(-number, gender)
            groups = []
            temp = number
            while temp > 0:
                groups.append(temp % 1000)
                temp //= 1000
            result = []
            for (i, group) in enumerate(groups):
                if group == 0:
                    continue
                current_gender = gender
                if i == 1:
                    current_gender = 'f'
                elif i >= 2:
                    current_gender = 'm'
                group_words = self._convert_triplet(group, current_gender)
                if group_words:
                    result.append(group_words)
                    if i < len(self.orders):
                        order_forms = self.orders[i]
                        order_word = self._get_plural_form(group, order_forms)
                        if order_word:
                            result.append(order_word)
            return ' '.join(reversed(result))
        except (ValueError, TypeError) as e:
            logger.exception('Ошибка конвертации числа {number}')
            return str(number)

    def convert_time(self, time_str: str) -> str:
        """
        Конвертирует время в слова
        
        Args:
            time_str: Время в формате "HH:MM" или "HH.MM"
            
        Returns:
            Время словами
        """
        try:
            time_str = re.sub('[^\\d:]', '', time_str)
            if ':' in time_str:
                (hours, minutes) = time_str.split(':')
            elif len(time_str) == 4:
                hours = time_str[:2]
                minutes = time_str[2:]
            else:
                return time_str
            hours = int(hours)
            minutes = int(minutes)
            result = []
            if hours == 0:
                result.append('ноль часов')
            elif hours == 1:
                result.append('один час')
            elif 2 <= hours <= 4:
                result.append(f'{self.convert_number(hours)} часа')
            else:
                result.append(f'{self.convert_number(hours)} часов')
            if minutes == 0:
                result.append('ноль минут')
            elif minutes == 1:
                result.append('одна минута')
            elif 2 <= minutes <= 4:
                result.append(f'{self.convert_number(minutes)} минуты')
            else:
                result.append(f'{self.convert_number(minutes)} минут')
            return ' '.join(result)
        except (ValueError, IndexError) as e:
            logger.exception('Ошибка конвертации времени {time_str}')
            return time_str

    def convert_date(self, date_str: str) -> str:
        """
        Конвертирует дату в слова
        
        Args:
            date_str: Дата в формате "DD.MM.YYYY" или "DD/MM/YYYY"
            
        Returns:
            Дата словами
        """
        try:
            date_str = re.sub('[^\\d./]', '', date_str)
            if '.' in date_str:
                (day, month, year) = date_str.split('.')
            elif '/' in date_str:
                (day, month, year) = date_str.split('/')
            else:
                return date_str
            day = int(day)
            month = int(month)
            year = int(year)
            months = ['', 'января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']
            result = []
            if day == 1:
                result.append('первое')
            elif day == 2:
                result.append('второе')
            elif day == 3:
                result.append('третье')
            elif day == 4:
                result.append('четвертое')
            elif day == 5:
                result.append('пятое')
            elif day == 6:
                result.append('шестое')
            elif day == 7:
                result.append('седьмое')
            elif day == 8:
                result.append('восьмое')
            elif day == 9:
                result.append('девятое')
            elif day == 10:
                result.append('десятое')
            elif day == 11:
                result.append('одиннадцатое')
            elif day == 12:
                result.append('двенадцатое')
            elif day == 13:
                result.append('тринадцатое')
            elif day == 14:
                result.append('четырнадцатое')
            elif day == 15:
                result.append('пятнадцатое')
            elif day == 16:
                result.append('шестнадцатое')
            elif day == 17:
                result.append('семнадцатое')
            elif day == 18:
                result.append('восемнадцатое')
            elif day == 19:
                result.append('девятнадцатое')
            elif day == 20:
                result.append('двадцатое')
            elif day == 21:
                result.append('двадцать первое')
            elif day == 22:
                result.append('двадцать второе')
            elif day == 23:
                result.append('двадцать третье')
            elif day == 24:
                result.append('двадцать четвертое')
            elif day == 25:
                result.append('двадцать пятое')
            elif day == 26:
                result.append('двадцать шестое')
            elif day == 27:
                result.append('двадцать седьмое')
            elif day == 28:
                result.append('двадцать восьмое')
            elif day == 29:
                result.append('двадцать девятое')
            elif day == 30:
                result.append('тридцатое')
            elif day == 31:
                result.append('тридцать первое')
            else:
                result.append(self.convert_number(day))
            if 1 <= month <= 12:
                result.append(months[month])
            else:
                result.append(self.convert_number(month))
            result.append(self.convert_number(year))
            result.append('года')
            return ' '.join(result)
        except (ValueError, IndexError) as e:
            logger.exception('Ошибка конвертации даты {date_str}')
            return date_str

    def convert_money(self, amount_str: str) -> str:
        """
        Конвертирует денежную сумму в слова
        
        Args:
            amount_str: Сумма в формате "1234 руб" или "1234.56 руб"
            
        Returns:
            Сумма словами
        """
        try:
            amount_match = re.search('(\\d+(?:\\.\\d+)?)', amount_str)
            currency_match = re.search('Text cleaned.', amount_str, re.IGNORECASE)
            if not amount_match:
                return amount_str
            amount = float(amount_match.group(1))
            currency = currency_match.group(1).lower() if currency_match else 'руб'
            if currency in ['руб', 'рубл']:
                currency_name = 'рубль'
                currency_forms = ('рубль', 'рубля', 'рублей')
            elif currency in ['долл', '$']:
                currency_name = 'доллар'
                currency_forms = ('доллар', 'доллара', 'долларов')
            elif currency in ['евро', 'Text cleaned.']:
                currency_name = 'евро'
                currency_forms = ('евро', 'евро', 'евро')
            else:
                currency_name = currency
                currency_forms = (currency, currency, currency)
            integer_part = int(amount)
            fractional_part = int((amount - integer_part) * 100) if amount != integer_part else 0
            result = []
            if integer_part > 0:
                amount_words = self.convert_number(integer_part, 'm')
                result.append(amount_words)
                currency_word = self._get_plural_form(integer_part, currency_forms)
                result.append(currency_word)
            if fractional_part > 0 and currency in ['руб', 'рубл']:
                if integer_part > 0:
                    result.append('и')
                kopecks_word = self.convert_number(fractional_part, 'f')
                result.append(kopecks_word)
                if fractional_part == 1:
                    result.append('копейка')
                elif 2 <= fractional_part <= 4:
                    result.append('копейки')
                else:
                    result.append('копеек')
            return ' '.join(result)
        except (ValueError, AttributeError) as e:
            logger.exception('Ошибка конвертации денежной суммы {amount_str}')
            return amount_str
number_converter = NumberToWordsConverter()

def convert_numbers_in_text(text: str) -> str:
    """
    Конвертирует все числа в тексте в слова
    
    Args:
        text: Исходный текст
        
    Returns:
        Текст с числами, замененными на слова
    """
    try:
        patterns = [('\\b(\\d{1,2}[:.]\\d{2})\\b', lambda m: number_converter.convert_time(m.group(1))), ('\\b(\\d{1,2}[./]\\d{1,2}[./]\\d{4})\\b', lambda m: number_converter.convert_date(m.group(1))), ('Text cleaned.', lambda m: number_converter.convert_money(m.group(0))), ('\\b(\\d+)\\b', lambda m: number_converter.convert_number(m.group(1)))]
        result = text
        for (pattern, converter) in patterns:
            result = re.sub(pattern, converter, result)
        return result
    except Exception:
        logger.exception('Ошибка конвертации чисел в тексте')
        return text
if __name__ == '__main__':
    converter = NumberToWordsConverter()
    test_cases = ['123', '2024', '14:30', '25.12.2024', '1000 руб', '1234.56 руб', '50 долл', 'Сегодня 15 числа, время 14:30, сумма 1000 рублей']
    for test in test_cases:
        result = convert_numbers_in_text(test)
        logger.info(f"Number conversion: '{test}' -> '{result}'")
