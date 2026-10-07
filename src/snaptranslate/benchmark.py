"""Offline benchmark: every system is scored against the REFERENCE TRANSLATION of each input.

The prototype scored each output against one fixed sentence from a drop-down list, so its BLEU had no
relation to translation quality. Here the test set gives a reference for each source sentence, the
score is corpus BLEU and chrF, and a failed or refused item counts as an empty output.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from importlib import resources
from pathlib import Path
from typing import Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .langid import LanguageDetector
from .languages import normalize
from .metrics import bootstrap_ci, corpus_bleu, corpus_chrf, cer
from .mt.base import Translator
from .mt.router import Router
from .synthetic import CONDITIONS


class BenchItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    src_lang: str
    tgt_lang: str
    src: str = Field(min_length=1)
    ref: str = Field(min_length=1)

    @field_validator("src_lang", "tgt_lang")
    @classmethod
    def _norm(cls, v: str) -> str:
        return normalize(v)


def load_testset(path: str | Path | None = None) -> list[BenchItem]:
    """Load JSONL with id, src_lang, tgt_lang, src, ref. Default: the bundled synthetic set."""
    if path:
        text = Path(path).read_text(encoding="utf-8")
    else:
        text = resources.files("snaptranslate.data").joinpath("testset.jsonl").read_text(encoding="utf-8")
    items = [BenchItem.model_validate_json(line) for line in text.splitlines() if line.strip()]
    ids = [i.id for i in items]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate ids in the test set")
    return items


class CopySource:
    """Baseline: output the source text. Any useful system must beat it."""

    name = "copy-source"

    def available(self) -> bool:
        return True

    def supports(self, src: str, tgt: str) -> bool:
        return True

    def translate(self, texts: Sequence[str], src: str, tgt: str) -> list[str]:
        return list(texts)


@dataclass
class SystemScore:
    system: str
    condition: str
    pair: str
    n: int
    answered: int  # items with an output (translated, approximate)
    bleu: float
    bleu_ci: tuple[float, float]
    chrf: float
    chrf_ci: tuple[float, float]
    mean_input_cer: float  # how much the condition changed the source text


def score_system(system: Translator, items: Sequence[BenchItem], condition: str = "clean", seed: int = 0,
                 n_boot: int = 500) -> list[SystemScore]:
    noise = CONDITIONS[condition]
    out: list[SystemScore] = []
    pairs = sorted({(i.src_lang, i.tgt_lang) for i in items})
    router = Router([system])
    for s, t in pairs:
        group = [i for i in items if (i.src_lang, i.tgt_lang) == (s, t)]
        hyps, refs, cers, answered = [], [], [], 0
        for k, it in enumerate(group):
            src_text = noise(it.src, seed + k)
            cers.append(cer(src_text, it.src))
            res = router.translate(src_text, s, t)
            if res.status in ("translated", "approximate"):
                answered += 1
                hyps.append(res.text)
            else:
                hyps.append("")
            refs.append(it.ref)
        out.append(
            SystemScore(
                system.name, condition, f"{s}-{t}", len(group), answered,
                corpus_bleu(hyps, refs), bootstrap_ci(hyps, refs, corpus_bleu, n_boot, seed),
                corpus_chrf(hyps, refs), bootstrap_ci(hyps, refs, corpus_chrf, n_boot, seed),
                sum(cers) / len(cers),
            )
        )
    return out


def langid_accuracy(detector: LanguageDetector, items: Sequence[BenchItem]) -> tuple[float, list[str]]:
    wrong = []
    for it in items:
        got = detector.detect(it.src).code
        if got != it.src_lang:
            wrong.append(f"{it.id}: expected {it.src_lang}, got {got}")
    return 1 - len(wrong) / len(items), wrong


def run(systems: Sequence[Translator], items: Sequence[BenchItem], conditions: Sequence[str] = ("clean",),
        seed: int = 0, n_boot: int = 500) -> list[SystemScore]:
    rows: list[SystemScore] = []
    for cond in conditions:
        if cond not in CONDITIONS:
            raise ValueError(f"unknown condition {cond!r}; known: {list(CONDITIONS)}")
        for system in systems:
            rows += score_system(system, items, cond, seed, n_boot)
    return rows


def save(rows: Sequence[SystemScore], path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps([asdict(r) for r in rows], indent=2), encoding="utf-8")
    return p
