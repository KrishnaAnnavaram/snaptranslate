"""Translation and OCR metrics in pure Python.

``corpus_bleu`` follows the sacreBLEU defaults (13a tokenisation, 4-gram, exponential smoothing,
one reference). ``corpus_chrf`` follows sacreBLEU chrF2 (character 6-grams, beta 2, no spaces).
A test compares both with the ``sacrebleu`` package when it is installed.
"""

from __future__ import annotations

import math
import random
import re
from collections import Counter
from typing import Callable, Sequence


def tokenize_13a(line: str) -> str:
    line = line.replace("<skipped>", "").replace("-\n", "").replace("\n", " ")
    if "&" in line:
        line = line.replace("&quot;", '"').replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    line = f" {line} "
    line = re.sub(r"([\{-\~\[-\` -\&\(-\+\:-\@\/])", r" \1 ", line)
    line = re.sub(r"([^0-9])([\.,])", r"\1 \2 ", line)
    line = re.sub(r"([\.,])([^0-9])", r" \1 \2", line)
    line = re.sub(r"([0-9])(-)", r"\1 \2 ", line)
    return " ".join(line.split())


def _ngrams(tokens: Sequence[str], n: int) -> Counter:
    return Counter(tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1))


def bleu_stats(hyp: str, ref: str, order: int = 4) -> list[int]:
    """[hyp_len, ref_len, correct_1..order, total_1..order]"""
    h, r = tokenize_13a(hyp).split(), tokenize_13a(ref).split()
    correct, total = [], []
    for n in range(1, order + 1):
        hc, rc = _ngrams(h, n), _ngrams(r, n)
        correct.append(sum(min(c, rc[g]) for g, c in hc.items()))
        total.append(max(0, len(h) - n + 1))
    return [len(h), len(r)] + correct + total


def bleu_from_stats(stats: Sequence[int], order: int = 4) -> float:
    sys_len, ref_len = stats[0], stats[1]
    correct, total = stats[2 : 2 + order], stats[2 + order : 2 + 2 * order]
    precisions = [0.0] * order
    smooth = 1.0
    for n in range(order):
        if total[n] == 0:
            break
        if correct[n] == 0:
            smooth *= 2
            precisions[n] = 100.0 / (smooth * total[n])
        else:
            precisions[n] = 100.0 * correct[n] / total[n]
    if sys_len < ref_len:
        bp = math.exp(1 - ref_len / sys_len) if sys_len > 0 else 0.0
    else:
        bp = 1.0
    logs = [math.log(p) if p > 0 else -9999999999 for p in precisions]
    return bp * math.exp(sum(logs) / order)


def corpus_bleu(hyps: Sequence[str], refs: Sequence[str]) -> float:
    if len(hyps) != len(refs):
        raise ValueError("hyps and refs differ in length")
    stats = [0] * 10
    for h, r in zip(hyps, refs):
        stats = [a + b for a, b in zip(stats, bleu_stats(h, r))]
    return bleu_from_stats(stats)


def chrf_stats(hyp: str, ref: str, order: int = 6) -> list[int]:
    """[n_hyp, n_ref, n_match] for each character order 1..order."""
    h, r = "".join(hyp.split()), "".join(ref.split())
    out: list[int] = []
    for n in range(1, order + 1):
        hc = Counter(h[i : i + n] for i in range(len(h) - n + 1))
        rc = Counter(r[i : i + n] for i in range(len(r) - n + 1))
        out += [sum(hc.values()), sum(rc.values()), sum(min(c, rc[g]) for g, c in hc.items())]
    return out


def chrf_from_stats(stats: Sequence[int], order: int = 6, beta: float = 2.0) -> float:
    eps = 1e-16
    factor = beta**2
    avg_prec = avg_rec = 0.0
    effective = 0
    for i in range(order):
        n_hyp, n_ref, n_match = stats[3 * i : 3 * i + 3]
        prec = n_match / n_hyp if n_hyp > 0 else eps
        rec = n_match / n_ref if n_ref > 0 else eps
        if n_hyp > 0 and n_ref > 0:
            avg_prec += prec
            avg_rec += rec
            effective += 1
    if effective == 0:
        return 0.0
    avg_prec /= effective
    avg_rec /= effective
    if avg_prec + avg_rec == 0:
        return 0.0
    return 100 * (1 + factor) * avg_prec * avg_rec / (factor * avg_prec + avg_rec)


def corpus_chrf(hyps: Sequence[str], refs: Sequence[str]) -> float:
    if len(hyps) != len(refs):
        raise ValueError("hyps and refs differ in length")
    stats = [0] * 18
    for h, r in zip(hyps, refs):
        stats = [a + b for a, b in zip(stats, chrf_stats(h, r))]
    return chrf_from_stats(stats)


def levenshtein(a: Sequence, b: Sequence) -> int:
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, start=1):
        cur = [i]
        for j, y in enumerate(b, start=1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def cer(hyp: str, ref: str) -> float:
    """Character error rate of OCR output against the true text."""
    return levenshtein(hyp, ref) / max(1, len(ref))


def wer(hyp: str, ref: str) -> float:
    return levenshtein(hyp.split(), ref.split()) / max(1, len(ref.split()))


def bootstrap_ci(
    hyps: Sequence[str], refs: Sequence[str], metric: Callable[[Sequence[str], Sequence[str]], float],
    n_boot: int = 1000, seed: int = 0, alpha: float = 0.05,
) -> tuple[float, float]:
    """Percentile bootstrap interval of a corpus metric (resampling sentences)."""
    rng = random.Random(seed)
    n = len(hyps)
    vals = []
    for _ in range(n_boot):
        idx = [rng.randrange(n) for _ in range(n)]
        vals.append(metric([hyps[i] for i in idx], [refs[i] for i in idx]))
    vals.sort()
    return vals[int(alpha / 2 * n_boot)], vals[int((1 - alpha / 2) * n_boot) - 1]


def paired_bootstrap(
    hyps_a: Sequence[str], hyps_b: Sequence[str], refs: Sequence[str],
    metric: Callable[[Sequence[str], Sequence[str]], float], n_boot: int = 1000, seed: int = 0,
) -> float:
    """Share of bootstrap samples in which system A scores higher than system B."""
    rng = random.Random(seed)
    n = len(refs)
    wins = 0
    for _ in range(n_boot):
        idx = [rng.randrange(n) for _ in range(n)]
        r = [refs[i] for i in idx]
        if metric([hyps_a[i] for i in idx], r) > metric([hyps_b[i] for i in idx], r):
            wins += 1
    return wins / n_boot
