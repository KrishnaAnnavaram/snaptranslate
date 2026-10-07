"""The language registry and code normalisation.

Detectors, OCR engines and translation models use different codes for the same language:
``zh-cn`` (langdetect), ``chi_sim`` (Tesseract), ``zho_Hans`` (NLLB), ``zh`` (MarianMT). This module
maps all of them to one canonical code.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Language:
    code: str  # canonical code
    name: str
    tesseract: str  # Tesseract language pack
    nllb: str  # NLLB-200 / FLORES-200 code
    marian: str  # code in Helsinki-NLP opus-mt model names
    script: str  # ISO 15924


REGISTRY: dict[str, Language] = {
    lang.code: lang
    for lang in [
        Language("en", "English", "eng", "eng_Latn", "en", "Latn"),
        Language("de", "German", "deu", "deu_Latn", "de", "Latn"),
        Language("fr", "French", "fra", "fra_Latn", "fr", "Latn"),
        Language("es", "Spanish", "spa", "spa_Latn", "es", "Latn"),
        Language("it", "Italian", "ita", "ita_Latn", "it", "Latn"),
        Language("pt", "Portuguese", "por", "por_Latn", "pt", "Latn"),
        Language("nl", "Dutch", "nld", "nld_Latn", "nl", "Latn"),
        Language("tr", "Turkish", "tur", "tur_Latn", "tr", "Latn"),
        Language("pl", "Polish", "pol", "pol_Latn", "pl", "Latn"),
        Language("zh", "Chinese (Simplified)", "chi_sim", "zho_Hans", "zh", "Hans"),
        Language("zh-Hant", "Chinese (Traditional)", "chi_tra", "zho_Hant", "zh", "Hant"),
        Language("ja", "Japanese", "jpn", "jpn_Jpan", "ja", "Jpan"),
        Language("ko", "Korean", "kor", "kor_Hang", "ko", "Hang"),
        Language("ru", "Russian", "rus", "rus_Cyrl", "ru", "Cyrl"),
        Language("ar", "Arabic", "ara", "arb_Arab", "ar", "Arab"),
        Language("hi", "Hindi", "hin", "hin_Deva", "hi", "Deva"),
    ]
}

UNDETERMINED = "und"

_ALIASES: dict[str, str] = {
    "zh-cn": "zh", "zh-sg": "zh", "zh-hans": "zh", "zh-hans-cn": "zh", "zho": "zh", "chi": "zh", "cmn": "zh",
    "zh-tw": "zh-Hant", "zh-hk": "zh-Hant", "zh-mo": "zh-Hant", "zh-hant": "zh-Hant", "zh-hant-tw": "zh-Hant",
    "eng": "en", "ger": "de", "fre": "fr", "jap": "ja", "jp": "ja", "kr": "ko", "arb": "ar",
}


class UnknownLanguage(ValueError):
    pass


def _build_lookup() -> dict[str, str]:
    table: dict[str, str] = {}
    for lang in REGISTRY.values():
        for key in (lang.code, lang.tesseract, lang.nllb, lang.name):
            table[key.lower()] = lang.code
    table["chinese"] = "zh"
    table.update(_ALIASES)
    return table


_LOOKUP = _build_lookup()


def normalize(code: str) -> str:
    """Return the canonical code for any common spelling of a language code or name."""
    if not code or not code.strip():
        raise UnknownLanguage("empty language code")
    key = code.strip().lower().replace("_", "-")
    if key in _LOOKUP:
        return _LOOKUP[key]
    raw = code.strip().lower()
    if raw in _LOOKUP:  # NLLB codes keep the underscore
        return _LOOKUP[raw]
    base = key.split("-")[0]
    if base in _LOOKUP and base != "zh":
        return _LOOKUP[base]
    raise UnknownLanguage(f"unknown language code {code!r}")


def get(code: str) -> Language:
    return REGISTRY[normalize(code)]


def is_known(code: str) -> bool:
    try:
        normalize(code)
        return True
    except UnknownLanguage:
        return False
