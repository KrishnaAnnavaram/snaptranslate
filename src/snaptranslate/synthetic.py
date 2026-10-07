"""Synthetic OCR noise, to measure what a wrong OCR language pack does to a translation.

``ocr_english_pack`` imitates an English-only pack reading European text: accented letters lose
their accent or change into look-alike letters (``ü`` -> ``u`` or ``ti``), and inverted marks drop.
``ocr_native_pack`` imitates the correct pack: only rare random character errors.
"""

from __future__ import annotations

import random

ENGLISH_PACK_CONFUSIONS: dict[str, tuple[str, ...]] = {
    "ä": ("a",), "ö": ("o",), "ü": ("u", "ti"), "ß": ("B", "ss"), "Ä": ("A",), "Ö": ("O",), "Ü": ("U",),
    "é": ("e",), "è": ("e",), "ê": ("e",), "à": ("a",), "â": ("a",), "ç": ("c",), "î": ("i",), "ô": ("o",),
    "û": ("u",), "ù": ("u",), "É": ("E",), "ñ": ("n", "fi"), "á": ("a",), "í": ("i",), "ó": ("o",),
    "ú": ("u",), "¿": ("",), "¡": ("",), "ì": ("i",), "ò": ("o",),
}
_LOOKALIKE = {"l": "1", "O": "0", "rn": "m", "e": "c", "i": "l"}


def _random_errors(text: str, rate: float, rng: random.Random) -> str:
    out = []
    for ch in text:
        if ch.isalpha() and rng.random() < rate:
            out.append(_LOOKALIKE.get(ch, ch.swapcase()))
        else:
            out.append(ch)
    return "".join(out)


def ocr_english_pack(text: str, seed: int = 0, char_error_rate: float = 0.01) -> str:
    rng = random.Random(seed)
    mapped = "".join(rng.choice(ENGLISH_PACK_CONFUSIONS[ch]) if ch in ENGLISH_PACK_CONFUSIONS else ch for ch in text)
    return _random_errors(mapped, char_error_rate, rng)


def ocr_native_pack(text: str, seed: int = 0, char_error_rate: float = 0.01) -> str:
    return _random_errors(text, char_error_rate, random.Random(seed))


CONDITIONS = {
    "clean": lambda text, seed: text,
    "ocr-native": ocr_native_pack,
    "ocr-eng": ocr_english_pack,
}
