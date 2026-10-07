"""The translation router: pick the first available backend that supports the pair.

Rules:
- The same source and target language gives ``same_language``. It is not called a translation.
- A pair that no backend supports gives ``unsupported_pair`` with an empty text and a clear message.
- If a backend fails, the router tries the next one and records each attempt in ``tried``.
- The glossary backend gives ``approximate``, never ``translated``.
"""

from __future__ import annotations

from typing import Sequence

from ..config import Settings
from ..languages import UnknownLanguage, get, normalize
from .base import ModelCache, TranslationError, TranslationResult, Translator
from .glossary import GlossaryTranslator
from .llm_api import LLMTranslator
from .neural import MarianTranslator, NLLBTranslator


class Router:
    def __init__(self, backends: Sequence[Translator]):
        if not backends:
            raise ValueError("the router needs at least one backend")
        self.backends = list(backends)

    def active(self) -> list[Translator]:
        return [b for b in self.backends if b.available()]

    def candidates(self, src: str, tgt: str) -> list[Translator]:
        return [b for b in self.active() if b.supports(src, tgt)]

    def translate(self, text: str, src: str, tgt: str) -> TranslationResult:
        text = text.strip()
        try:
            s, t = normalize(src), normalize(tgt)
        except UnknownLanguage as exc:
            return TranslationResult(text, "", src, tgt, "unsupported_pair", message=str(exc))
        if not text:
            return TranslationResult(text, "", s, t, "empty", message="no text to translate")
        if s == t:
            return TranslationResult(text, text, s, t, "same_language", message=f"the text is already in {get(s).name}")
        cands = self.candidates(s, t)
        if not cands:
            names = ", ".join(b.name for b in self.active()) or "none"
            return TranslationResult(
                text, "", s, t, "unsupported_pair",
                message=f"no installed backend translates {get(s).name} to {get(t).name} (active backends: {names})",
            )
        tried: list[str] = []
        errors: list[str] = []
        for backend in cands:
            tried.append(backend.name)
            try:
                out = backend.translate([text], s, t)[0]
            except (TranslationError, RuntimeError, OSError) as exc:
                errors.append(f"{backend.name}: {exc}")
                continue
            if isinstance(backend, GlossaryTranslator):
                cov = backend.last_coverage[0] if backend.last_coverage else 0.0
                return TranslationResult(text, out, s, t, "approximate", backend.name,
                                         "word-by-word glossary output, not a full translation", cov, tuple(tried))
            return TranslationResult(text, out, s, t, "translated", backend.name, "", 1.0, tuple(tried))
        return TranslationResult(text, "", s, t, "failed", message="; ".join(errors), tried=tuple(tried))

    def coverage_table(self, codes: Sequence[str]) -> dict[tuple[str, str], list[str]]:
        table = {}
        for s in codes:
            for t in codes:
                if s != t:
                    table[(s, t)] = [b.name for b in self.candidates(s, t)]
        return table


def build_router(settings: Settings) -> Router:
    cache = ModelCache(settings.model_cache_size)
    factories = {
        "marian": lambda: MarianTranslator(cache=cache),
        "nllb": lambda: NLLBTranslator(settings.nllb_model, cache=cache),
        "llm": lambda: LLMTranslator(settings.llm_base_url, settings.llm_model, settings.llm_api_key),
        "glossary": lambda: GlossaryTranslator(),
    }
    return Router([factories[name]() for name in settings.backends])
