"""The end-to-end service: (OCR) -> language identification -> routing -> history."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

from .history import SessionHistory
from .langid import BuiltinDetector, Detection, LanguageDetector
from .languages import UNDETERMINED, UnknownLanguage, normalize
from .mt.base import TranslationResult
from .mt.router import Router
from .ocr import OCREngine, OCRResult, OCRUnavailable, read_image


@dataclass(frozen=True)
class PipelineResult:
    input_kind: Literal["text", "image"]
    translation: TranslationResult
    detection: Detection | None = None
    ocr: OCRResult | None = None


class SnapTranslate:
    def __init__(self, router: Router, detector: LanguageDetector | None = None, ocr: OCREngine | None = None,
                 history: SessionHistory | None = None):
        self.router = router
        self.detector = detector or BuiltinDetector()
        self.ocr = ocr
        self.history = history if history is not None else SessionHistory()

    def _resolve_source(self, text: str, source: str | None) -> tuple[str | None, Detection | None, str]:
        if source:
            try:
                return normalize(source), None, ""
            except UnknownLanguage as exc:
                return None, None, str(exc)
        det = self.detector.detect(text)
        if det.code == UNDETERMINED:
            return None, det, "the language is not clear. Choose the source language and try again"
        return det.code, det, ""

    def translate_text(self, text: str, target: str, source: str | None = None, kind: str = "text",
                       ocr: OCRResult | None = None, detection: Detection | None = None) -> PipelineResult:
        src, det, problem = self._resolve_source(text, source)
        det = det or detection
        if src is None:
            res = TranslationResult(text.strip(), "", source or UNDETERMINED, target, "undetermined_language", message=problem)
        else:
            res = self.router.translate(text, src, target)
        if res.ok:
            self.history.add(res)
        return PipelineResult(kind, res, det, ocr)  # type: ignore[arg-type]

    def translate_image(self, image: np.ndarray, target: str, source: str | None = None) -> PipelineResult:
        if self.ocr is None:
            raise OCRUnavailable('no OCR engine is configured; install the extra: pip install -e ".[ocr]"')
        ocr_result, detected = read_image(self.ocr, image, source, self.detector)
        if not ocr_result.text.strip():
            res = TranslationResult("", "", source or UNDETERMINED, target, "empty", message="OCR found no text in the image")
            return PipelineResult("image", res, None, ocr_result)
        return self.translate_text(ocr_result.text, target, source or detected, "image", ocr_result)
