"""Language identification with normalised codes.

``BuiltinDetector`` works offline: Unicode script ranges decide non-Latin scripts, and a character
n-gram naive Bayes model decides between Latin-script languages. ``LangdetectDetector`` wraps the
optional ``langdetect`` package. Both return canonical codes from ``languages.py`` (for example
``zh``, never ``zh-cn``).
"""

from __future__ import annotations

import json
import math
import unicodedata
from collections import Counter
from dataclasses import dataclass
from importlib import resources
from typing import Protocol

from .languages import UNDETERMINED, UnknownLanguage, normalize


@dataclass(frozen=True)
class Detection:
    code: str  # canonical code or "und"
    confidence: float
    method: str


class LanguageDetector(Protocol):
    def detect(self, text: str) -> Detection: ...


# Characters that exist only in one of the two Chinese scripts (frequent ones).
_SIMPLIFIED = set("们这国说时个来会对发后学还经过见关长门问马车东书买卖乐电话请钱处飞场机图开点边头")
_TRADITIONAL = set("們這國說時個來會對發後學還經過見關長門問馬車東書買賣樂電話請錢處飛場機圖開點邊頭")


def script_counts(text: str) -> Counter:
    c: Counter = Counter()
    for ch in text:
        o = ord(ch)
        if 0x3040 <= o <= 0x30FF:
            c["Kana"] += 1
        elif 0xAC00 <= o <= 0xD7AF or 0x1100 <= o <= 0x11FF:
            c["Hang"] += 1
        elif 0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF:
            c["Han"] += 1
        elif 0x0400 <= o <= 0x04FF:
            c["Cyrl"] += 1
        elif 0x0600 <= o <= 0x06FF:
            c["Arab"] += 1
        elif 0x0900 <= o <= 0x097F:
            c["Deva"] += 1
        elif ch.isalpha() and unicodedata.name(ch, "").startswith("LATIN"):
            c["Latn"] += 1
    return c


def _ngrams(text: str, n_max: int = 3) -> list[str]:
    t = " " + " ".join("".join(ch.lower() if ch.isalpha() else " " for ch in text).split()) + " "
    out = []
    for n in range(1, n_max + 1):
        out += [t[i : i + n] for i in range(len(t) - n + 1)]
    return out


class NaiveBayesNgram:
    """Multinomial naive Bayes over character 1-3 grams with add-alpha smoothing."""

    def __init__(self, alpha: float = 0.5):
        self.alpha = alpha
        self.counts: dict[str, Counter] = {}
        self.totals: dict[str, int] = {}
        self.vocab: set[str] = set()

    def fit(self, samples: dict[str, list[str]]) -> "NaiveBayesNgram":
        for lang, sents in samples.items():
            c: Counter = Counter()
            for s in sents:
                c.update(_ngrams(s))
            self.counts[lang] = c
            self.totals[lang] = sum(c.values())
            self.vocab |= set(c)
        return self

    def log_scores(self, text: str) -> dict[str, float]:
        grams = _ngrams(text)
        v = len(self.vocab) + 1
        out = {}
        for lang, c in self.counts.items():
            denom = math.log(self.totals[lang] + self.alpha * v)
            out[lang] = sum(math.log(c.get(g, 0) + self.alpha) - denom for g in grams)
        return out

    def predict(self, text: str) -> tuple[str, float]:
        scores = self.log_scores(text)
        best = max(scores, key=scores.get)
        m = scores[best]
        z = sum(math.exp(s - m) for s in scores.values())
        return best, 1.0 / z


def load_samples() -> dict[str, list[str]]:
    data = json.loads(resources.files("snaptranslate.data").joinpath("langid_samples.json").read_text(encoding="utf-8"))
    return data["samples"]


class BuiltinDetector:
    def __init__(self, min_letters: int = 3, min_confidence: float = 0.5, samples: dict[str, list[str]] | None = None):
        self.min_letters, self.min_confidence = min_letters, min_confidence
        self.model = NaiveBayesNgram().fit(samples or load_samples())

    def detect(self, text: str) -> Detection:
        counts = script_counts(text)
        letters = sum(counts.values())
        if letters < self.min_letters:
            return Detection(UNDETERMINED, 0.0, "too-short")
        script, n = counts.most_common(1)[0]
        share = n / letters
        if counts["Kana"]:
            return Detection("ja", share, "script")
        if script == "Hang":
            return Detection("ko", share, "script")
        if script == "Han":
            simp = sum(ch in _SIMPLIFIED for ch in text)
            trad = sum(ch in _TRADITIONAL for ch in text)
            return Detection("zh-Hant" if trad > simp else "zh", share, "script")
        if script in ("Cyrl", "Arab", "Deva"):
            return Detection({"Cyrl": "ru", "Arab": "ar", "Deva": "hi"}[script], share, "script")
        code, conf = self.model.predict(text)
        if conf < self.min_confidence:
            return Detection(UNDETERMINED, conf, "ngram-low-confidence")
        return Detection(code, conf, "ngram")


class LangdetectDetector:  # pragma: no cover - optional extra
    """Wrapper for the ``langdetect`` package with code normalisation (``zh-cn`` -> ``zh``)."""

    def __init__(self, seed: int = 0):
        try:
            from langdetect import DetectorFactory, detect_langs
        except ImportError as exc:
            raise RuntimeError('langdetect needs: pip install -e ".[langdetect]"') from exc
        DetectorFactory.seed = seed
        self._detect_langs = detect_langs

    def detect(self, text: str) -> Detection:
        try:
            best = self._detect_langs(text)[0]
        except Exception as exc:  # langdetect raises LangDetectException on empty text
            return Detection(UNDETERMINED, 0.0, f"langdetect-error:{type(exc).__name__}")
        try:
            return Detection(normalize(best.lang), float(best.prob), "langdetect")
        except UnknownLanguage:
            return Detection(UNDETERMINED, float(best.prob), f"langdetect-unknown:{best.lang}")
