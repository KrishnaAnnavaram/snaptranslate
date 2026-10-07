"""Neural translators: MarianMT (one model for each pair) and NLLB-200 (many-to-many).

Both import ``transformers`` lazily, so the core package works without the ``mt`` extra. Both use
greedy or beam decoding with no sampling, so the same input gives the same output.
"""

from __future__ import annotations

import importlib.util
from typing import Sequence

from ..languages import REGISTRY, get, normalize
from .base import ModelCache

# Helsinki-NLP opus-mt pairs (canonical codes) that this project uses. Extend the set to add pairs.
MARIAN_PAIRS: frozenset[tuple[str, str]] = frozenset(
    [(x, "en") for x in ("de", "fr", "es", "it", "nl", "ru", "zh", "ja", "ko", "ar", "hi", "tr", "pl")]
    + [("en", x) for x in ("de", "fr", "es", "it", "nl", "ru", "zh", "ar", "hi")]
    + [("de", "fr"), ("fr", "de"), ("fr", "es"), ("es", "fr"), ("de", "es"), ("es", "de")]
)


def _has(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def marian_model_name(src: str, tgt: str) -> str:
    return f"Helsinki-NLP/opus-mt-{get(src).marian}-{get(tgt).marian}"


class MarianTranslator:
    name = "marian"

    def __init__(self, cache: ModelCache | None = None, num_beams: int = 4, max_new_tokens: int = 256):
        self.cache = cache or ModelCache(4)
        self.num_beams, self.max_new_tokens = num_beams, max_new_tokens

    def available(self) -> bool:
        return _has("transformers") and _has("torch") and _has("sentencepiece")

    def supports(self, src: str, tgt: str) -> bool:
        s, t = normalize(src), normalize(tgt)
        s = "zh" if s == "zh-Hant" else s
        return (s, t) in MARIAN_PAIRS

    def _load(self, model_name: str):  # pragma: no cover - downloads a model
        from transformers import MarianMTModel, MarianTokenizer

        tok = MarianTokenizer.from_pretrained(model_name)
        model = MarianMTModel.from_pretrained(model_name)
        model.eval()
        return tok, model

    def translate(self, texts: Sequence[str], src: str, tgt: str) -> list[str]:  # pragma: no cover
        import torch

        name = marian_model_name("zh" if normalize(src) == "zh-Hant" else src, tgt)
        tok, model = self.cache.get(name, lambda: self._load(name))
        batch = tok(list(texts), return_tensors="pt", padding=True, truncation=True)
        with torch.no_grad():
            out = model.generate(**batch, num_beams=self.num_beams, do_sample=False, max_new_tokens=self.max_new_tokens)
        return [tok.decode(o, skip_special_tokens=True) for o in out]


class NLLBTranslator:
    name = "nllb"

    def __init__(self, model_name: str = "facebook/nllb-200-distilled-600M", cache: ModelCache | None = None,
                 num_beams: int = 4, max_new_tokens: int = 256):
        self.model_name = model_name
        self.cache = cache or ModelCache(1)
        self.num_beams, self.max_new_tokens = num_beams, max_new_tokens

    def available(self) -> bool:
        return _has("transformers") and _has("torch") and _has("sentencepiece")

    def supports(self, src: str, tgt: str) -> bool:
        return normalize(src) in REGISTRY and normalize(tgt) in REGISTRY

    def _load(self):  # pragma: no cover - downloads a model
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

        tok = AutoTokenizer.from_pretrained(self.model_name)
        model = AutoModelForSeq2SeqLM.from_pretrained(self.model_name)
        model.eval()
        return tok, model

    def translate(self, texts: Sequence[str], src: str, tgt: str) -> list[str]:  # pragma: no cover
        import torch

        tok, model = self.cache.get(self.model_name, self._load)
        tok.src_lang = get(src).nllb
        batch = tok(list(texts), return_tensors="pt", padding=True, truncation=True)
        bos = tok.convert_tokens_to_ids(get(tgt).nllb)
        with torch.no_grad():
            out = model.generate(**batch, forced_bos_token_id=bos, num_beams=self.num_beams, do_sample=False,
                                 max_new_tokens=self.max_new_tokens)
        return tok.batch_decode(out, skip_special_tokens=True)
