"""OCR with the correct language packs.

The prototype always read with the English pack, so ``über`` became ``tiber``. This module reads with
the pack of the source language. If the source language is not known, it reads once with a set of
Latin packs, detects the language, and reads again with the detected pack.

The module never installs software. If Tesseract or a pack is missing, it raises ``OCRUnavailable``
with the install command.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, Sequence

import numpy as np

from .languages import REGISTRY, get
from .preprocess import prepare_for_ocr

FIRST_PASS_PACKS = ("eng", "deu", "fra", "spa", "ita")


class OCRUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class OCRResult:
    text: str
    confidence: float  # mean word confidence 0..1, or -1 when the engine gives none
    packs: tuple[str, ...]
    passes: int = 1
    notes: tuple[str, ...] = field(default=())


class OCREngine(Protocol):
    def available_packs(self) -> set[str]: ...

    def read(self, image: np.ndarray, packs: Sequence[str]) -> OCRResult: ...


def packs_for(lang_code: str | None, available: set[str]) -> tuple[str, ...]:
    """The packs to use for a known source language. English is added for mixed signs."""
    if lang_code is None:
        chosen = tuple(p for p in FIRST_PASS_PACKS if p in available)
        if not chosen:
            raise OCRUnavailable(f"none of the first-pass packs {FIRST_PASS_PACKS} is installed")
        return chosen
    pack = get(lang_code).tesseract
    if pack not in available:
        raise OCRUnavailable(
            f"the Tesseract pack '{pack}' for {get(lang_code).name} is not installed. "
            f"Install it, for example: apt-get install tesseract-ocr-{pack.replace('_', '-')}"
        )
    return (pack,) if pack == "eng" or "eng" not in available else (pack, "eng")


class TesseractOCR:  # pragma: no cover - needs the Tesseract binary
    def __init__(self, tesseract_cmd: str = "", preprocess: bool = True):
        try:
            import pytesseract
        except ImportError as exc:
            raise OCRUnavailable('pytesseract needs: pip install -e ".[ocr]"') from exc
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        self._tess = pytesseract
        self.preprocess = preprocess
        try:
            self._packs = set(pytesseract.get_languages(config=""))
        except Exception as exc:  # TesseractNotFoundError or an OS error
            raise OCRUnavailable(
                "the Tesseract binary is not found. Install it (apt-get install tesseract-ocr, "
                "brew install tesseract, or the Windows installer) or set SNAPTRANSLATE_TESSERACT_CMD"
            ) from exc

    def available_packs(self) -> set[str]:
        return set(self._packs)

    def read(self, image: np.ndarray, packs: Sequence[str]) -> OCRResult:
        img = prepare_for_ocr(image) if self.preprocess else np.asarray(image)
        data = self._tess.image_to_data(img, lang="+".join(packs), output_type=self._tess.Output.DICT)
        words, confs = [], []
        for w, c in zip(data["text"], data["conf"]):
            if w.strip():
                words.append(w)
                if float(c) >= 0:
                    confs.append(float(c) / 100.0)
        text = self._tess.image_to_string(img, lang="+".join(packs)).strip()
        return OCRResult(text, sum(confs) / len(confs) if confs else -1.0, tuple(packs))


class ScriptedOCR:
    """Test double: returns a fixed text for each pack set and records the calls."""

    def __init__(self, texts: dict[str, str], packs: set[str] | None = None, confidence: float = 0.9):
        self.texts = texts
        self.packs = packs if packs is not None else {lang.tesseract for lang in REGISTRY.values()}
        self.confidence = confidence
        self.calls: list[tuple[str, ...]] = []

    def available_packs(self) -> set[str]:
        return set(self.packs)

    def read(self, image: np.ndarray, packs: Sequence[str]) -> OCRResult:
        self.calls.append(tuple(packs))
        key = "+".join(packs)
        text = self.texts.get(key, self.texts.get("*", ""))
        return OCRResult(text, self.confidence, tuple(packs))


def read_image(engine: OCREngine, image: np.ndarray, source_lang: str | None, detector) -> tuple[OCRResult, str | None]:
    """Read an image. Returns the OCR result and the detected source language (or None).

    1. If the source language is known, read once with its pack.
    2. If not, read with the first-pass packs, detect the language and, if a different pack is
       needed, read again with that pack.
    """
    available = engine.available_packs()
    if source_lang:
        return engine.read(image, packs_for(source_lang, available)), None
    first = engine.read(image, packs_for(None, available))
    det = detector.detect(first.text)
    if det.code == "und":
        return OCRResult(first.text, first.confidence, first.packs, 1, ("language undetermined after pass 1",)), None
    try:
        packs = packs_for(det.code, available)
    except OCRUnavailable as exc:
        return OCRResult(first.text, first.confidence, first.packs, 1, (str(exc),)), det.code
    second = engine.read(image, packs)
    return OCRResult(second.text, second.confidence, second.packs, 2, (f"pass 1 detected {det.code}",)), det.code
