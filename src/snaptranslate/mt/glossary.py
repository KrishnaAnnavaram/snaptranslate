"""Offline glossary backend: longest-phrase, then word-by-word lookup into English.

This backend gives an APPROXIMATION. The router labels its output ``approximate`` and reports the
coverage (the share of source words that the glossary knows). If the coverage is below the minimum,
the backend refuses, and the user sees "no translation" instead of the untranslated input.
"""

from __future__ import annotations

import json
import re
import unicodedata
from importlib import resources
from typing import Sequence

from ..languages import normalize
from .base import TranslationError

_TOKEN = re.compile(r"[^\W\d_]+'|[^\W\d_]+(?:'[^\W\d_]+)?|\d+", re.UNICODE)


def raw_tokens(text: str) -> list[str]:
    """Word tokens in their original case. French elisions keep their apostrophe (``l'``)."""
    return _TOKEN.findall(unicodedata.normalize("NFC", text).replace("’", "'"))


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in raw_tokens(text)]


class GlossaryTranslator:
    name = "glossary"

    def __init__(self, data: dict | None = None, min_coverage: float = 0.6):
        if data is None:
            data = json.loads(resources.files("snaptranslate.data").joinpath("glossary.json").read_text(encoding="utf-8"))
        self.target = data["target"]
        self.min_coverage = min_coverage
        self.tables: dict[str, tuple[dict[tuple[str, ...], str], dict[str, str]]] = {}
        for lang, entry in data["languages"].items():
            phrases = {tuple(tokenize(k)): v for k, v in entry.get("phrases", {}).items()}
            self.tables[lang] = (phrases, entry.get("words", {}))
        self.last_coverage: list[float] = []

    def available(self) -> bool:
        return True

    def supports(self, src: str, tgt: str) -> bool:
        return normalize(src) in self.tables and normalize(tgt) == self.target

    def gloss(self, text: str, src: str) -> tuple[str, float]:
        phrases, words = self.tables[normalize(src)]
        raw = raw_tokens(text)
        toks = [t.lower() for t in raw]
        max_len = max((len(k) for k in phrases), default=1)
        out: list[str] = []
        known = 0
        i = 0
        while i < len(toks):
            for n in range(min(max_len, len(toks) - i), 0, -1):
                key = tuple(toks[i : i + n])
                if n > 1 and key in phrases:
                    out.append(phrases[key])
                    known += n
                    i += n
                    break
            else:
                tok = toks[i]
                if tok in words:
                    out.append(words[tok])
                    known += 1
                elif tok.isdigit():
                    out.append(tok)
                    known += 1
                elif raw[i][0].isupper() and i > 0:
                    # Possibly a name (Berlin): copy it, but do not count it as known.
                    # German capitalises every noun, so this word can also be an unknown noun.
                    out.append(raw[i])
                else:
                    out.append(f"[{raw[i]}]")  # unknown word stays visible and marked
                i += 1
        coverage = known / len(toks) if toks else 0.0
        sentence = " ".join(out)
        if sentence:
            sentence = sentence[0].upper() + sentence[1:]
        end = text.strip()[-1:] if text.strip() else ""
        if end in ".?!":
            sentence += end
        return sentence, coverage

    def translate(self, texts: Sequence[str], src: str, tgt: str) -> list[str]:
        if not self.supports(src, tgt):
            raise TranslationError(f"glossary has no {src}->{tgt} table")
        out, self.last_coverage = [], []
        for t in texts:
            sentence, cov = self.gloss(t, src)
            if cov < self.min_coverage:
                raise TranslationError(f"glossary knows only {cov:.0%} of the words (minimum {self.min_coverage:.0%})")
            out.append(sentence)
            self.last_coverage.append(cov)
        return out
