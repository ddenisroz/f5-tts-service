from __future__ import annotations

import re

CYRILLIC_RE = re.compile(r"[\u0400-\u04FF]")
LATIN_RE = re.compile(r"[a-z]", re.IGNORECASE)
PROTECTED_RE = re.compile(
    r"https?://\S+|www\.\S+|\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b|\b(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}\S*|"
    r"(?<!\w)@[A-Za-z0-9_][A-Za-z0-9_.-]*|(?<!\w)#[A-Za-z0-9_][A-Za-z0-9_.-]*|"
    r"(?<!\w):[A-Za-z0-9_]{2,32}:(?!\w)|(?<!\w)[A-Z][A-Z0-9_]{1,31}(?!\w)",
    re.UNICODE,
)
LATIN_WORD_RE = re.compile(r"(?<![@#:/.\w-])([A-Za-z][A-Za-z'-]{1,31})(?![\w@#:/-])")

COMMON_PRONUNCIATIONS = {
    "ai": "эй ай",
    "api": "апи",
    "bot": "бот",
    "chat": "чат",
    "discord": "дискорд",
    "donate": "донат",
    "donation": "донейшен",
    "google": "гугл",
    "lol": "лол",
    "misha": "миша",
    "obs": "о би эс",
    "ok": "окей",
    "paid": "пейд",
    "player": "плеер",
    "prime": "прайм",
    "react": "реакт",
    "stream": "стрим",
    "streamer": "стример",
    "sub": "саб",
    "tts": "ти ти эс",
    "twitch": "твич",
    "youtube": "ютуб",
}

PHONEME_REPLACEMENTS = (
    ("sch", "щ"),
    ("shch", "щ"),
    ("yo", "ё"),
    ("yu", "ю"),
    ("ya", "я"),
    ("ye", "е"),
    ("zh", "ж"),
    ("ch", "ч"),
    ("sh", "ш"),
    ("kh", "х"),
    ("ts", "ц"),
    ("ph", "ф"),
    ("th", "т"),
    ("ck", "к"),
    ("qu", "кв"),
    ("oo", "у"),
    ("ee", "и"),
)

CHAR_REPLACEMENTS = str.maketrans(
    {
        "a": "а",
        "b": "б",
        "c": "к",
        "d": "д",
        "e": "е",
        "f": "ф",
        "g": "г",
        "h": "х",
        "i": "и",
        "j": "дж",
        "k": "к",
        "l": "л",
        "m": "м",
        "n": "н",
        "o": "о",
        "p": "п",
        "q": "к",
        "r": "р",
        "s": "с",
        "t": "т",
        "u": "у",
        "v": "в",
        "w": "в",
        "x": "кс",
        "y": "й",
        "z": "з",
    }
)


def normalize_latin_words_for_ru(text: str) -> str:
    if not text or not CYRILLIC_RE.search(text) or not LATIN_RE.search(text):
        return text

    protected: list[str] = []

    def protect(match: re.Match[str]) -> str:
        protected.append(match.group(0))
        return f"⟦pv{len(protected) - 1}⟧"

    masked = PROTECTED_RE.sub(protect, text)
    normalized = LATIN_WORD_RE.sub(lambda match: _normalize_word(match.group(1)), masked)

    for index, value in enumerate(protected):
        normalized = normalized.replace(f"⟦pv{index}⟧", value)
    return normalized


def _normalize_word(word: str) -> str:
    cleaned = word.strip("'-").lower()
    if len(cleaned) < 2 or not LATIN_RE.search(cleaned):
        return word
    if cleaned in COMMON_PRONUNCIATIONS:
        return COMMON_PRONUNCIATIONS[cleaned]

    normalized = cleaned
    for source, target in PHONEME_REPLACEMENTS:
        normalized = normalized.replace(source, target)
    return normalized.translate(CHAR_REPLACEMENTS)
