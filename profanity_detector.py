import re
import Levenshtein


CHAR_SUBSTITUTIONS = {
    '@': 'а',
    '0': 'о',
    'o': 'о',
    'O': 'О',
    '$': 'с',
    '3': 'е',
    '*': 'а',
    '#': 'х',
    '4': 'ч',
    '6': 'б',
    '9': 'д',
    '!': 'и',
    '1': 'и',
    '7': 'т',
    'x': 'х',
    'X': 'Х',
    'c': 'с',
    'C': 'С',
    'e': 'е',
    'a': 'а',
    'p': 'р',
    'y': 'у',
    'k': 'к',
}

ROOT_PATTERNS = [
    ('бля', {'блять', 'бля', 'блядь', 'бляд', 'блять'}),
    ('сука', {'сука', 'сук', 'суки', 'суке', 'суку'}),
    ('хуй', {'хуй', 'хуя', 'хуе', 'хую', 'хуем', 'хуёв', 'хуё', 'хуйн', 'хуйло', 'хуев'}),
    ('пизд', {'пизд', 'пизда', 'пизду', 'пизде', 'пиздой', 'пиздец', 'пиздат', 'пиздё'}),
    ('ебат', {'ебат', 'ебан', 'ебать', 'ебёт', 'ебё', 'ебал', 'ебла', 'ебл', 'ебнуть', 'ебаш', 'ебанам', 'ебаный', 'ебанут'}),
    ('ёбат', {'ёбат', 'ёбан', 'ёбать', 'ёбёт', 'ёбл', 'ёбнуть', 'ёбанам', 'ёбаный', 'ёбанут'}),
    ('нахуй', {'нахуй', 'на хуй', 'нах', 'наху'}),
    ('похуй', {'похуй', 'по хуй', 'поху', 'похер'}),
    ('заеб', {'заеб', 'заёб', 'заебал', 'заебала', 'заебать', 'заебись', 'заёб', 'заебан', 'заёб'}),
    ('уеб', {'уеб', 'уёб', 'уебал', 'уебать', 'уёб', 'уебан', 'уебищ'}),
    ('отъеб', {'отъеб', 'отъебись', 'отъебитесь', 'отьеб'}),
    ('долбо', {'долбоёб', 'долбоеб', 'долбо', 'долба'}),
    ('муд', {'мудак', 'мудила', 'мудил', 'муд'}),
    ('залуп', {'залуп', 'залупа', 'залупе', 'залупу'}),
    ('шлюх', {'шлюх', 'шлюха', 'шлюхе', 'шлюху', 'шлюхи'}),
    ('пидор', {'пидор', 'пидар', 'пидорас', 'пидарас', 'пидоры', 'пидорк'}),
    ('еблан', {'еблан', 'ёблан', 'ебланк'}),
    ('дебил', {'дебил', 'дебиль', 'дебило'}),
    ('даун', {'даун', 'дауни'}),
    ('чмо', {'чмо', 'чмош', 'чмек', 'чмыр'}),
    ('лох', {'лох', 'лохи', 'лошка', 'лошара'}),
    ('гандон', {'гандон', 'гондон', 'гандоны', 'гондоны'}),
    ('говн', {'говн', 'говно', 'говна', 'говне', 'говню', 'говнян'}),
    ('дерьм', {'дерьм', 'дерьмо', 'дерьма', 'дерьме'}),
    ('жопа', {'жопа', 'жоп', 'жопу', 'жопе', 'жопой', 'жопный'}),
    ('срать', {'срать', 'срач', 'срака', 'сраку', 'сраки', 'сран', 'срань'}),
    ('перд', {'перд', 'пердеть', 'пердун', 'пердан', 'перд'}),
    ('хер', {'хер', 'хера', 'херу', 'хером', 'херня', 'херов'}),
]


def normalize_text(text: str) -> str:
    normalized = []
    for char in text.lower():
        if char in CHAR_SUBSTITUTIONS:
            normalized.append(CHAR_SUBSTITUTIONS[char])
        else:
            normalized.append(char)
    return ''.join(normalized)


def _remove_duplicates(text: str) -> str:
    result = []
    prev = None
    for char in text:
        if char != prev:
            result.append(char)
            prev = char
    return ''.join(result)


def _is_profanity_word(word: str, threshold: float = 0.70) -> bool:
    normalized = normalize_text(word)
    deduped = _remove_duplicates(normalized)

    for root, variants in ROOT_PATTERNS:
        if root in normalized:
            return True
        if root in deduped:
            return True

        for variant in variants:
            ratio = Levenshtein.ratio(normalized, variant)
            if ratio >= threshold:
                return True

            if len(normalized) >= 3 and len(variant) >= 3:
                partial = Levenshtein.ratio(normalized[:len(variant)], variant)
                if partial >= threshold:
                    return True

            if len(normalized) >= 4:
                for i in range(len(normalized) - 3):
                    sub = normalized[i:i + len(variant)]
                    if len(sub) >= len(variant) - 1:
                        sub_ratio = Levenshtein.ratio(sub, variant)
                        if sub_ratio >= threshold + 0.1:
                            return True

    return False


def detect_profanity(text: str, threshold: float = 0.70) -> tuple[bool, str]:
    if not text or not text.strip():
        return False, ""

    cleaned = re.sub(r'[^\w\sа-яёА-ЯЁ@0$3*#!14679]', ' ', text)
    words = cleaned.split()

    found_words = []
    for word in words:
        if len(word) < 2:
            continue
        if _is_profanity_word(word, threshold):
            found_words.append(word)

    if found_words:
        return True, ', '.join(found_words)
    return False, ""
