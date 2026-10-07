"""Machine translation backends and the router."""

from .base import ModelCache, TranslationError, TranslationResult, Translator
from .glossary import GlossaryTranslator
from .llm_api import LLMTranslator
from .neural import MARIAN_PAIRS, MarianTranslator, NLLBTranslator, marian_model_name
from .router import Router, build_router

__all__ = [
    "ModelCache",
    "TranslationError",
    "TranslationResult",
    "Translator",
    "GlossaryTranslator",
    "LLMTranslator",
    "MarianTranslator",
    "NLLBTranslator",
    "MARIAN_PAIRS",
    "marian_model_name",
    "Router",
    "build_router",
]
