"""The ``snaptranslate`` command line."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict

from .benchmark import CopySource, langid_accuracy, load_testset, run, save
from .config import KNOWN_BACKENDS, Settings
from .langid import BuiltinDetector
from .languages import REGISTRY, UnknownLanguage, normalize
from .mt.router import build_router
from .pipeline import SnapTranslate


def _settings(args) -> Settings:
    s = Settings.from_env()
    if getattr(args, "backends", None):
        s = Settings(**{**s.model_dump(), "backends": tuple(b.strip() for b in args.backends.split(",") if b.strip())})
    return s


def _print_result(pr, as_json: bool) -> None:
    tr = pr.translation
    if as_json:
        d = {"input_kind": pr.input_kind, "translation": asdict(tr)}
        if pr.detection:
            d["detection"] = asdict(pr.detection)
        if pr.ocr:
            d["ocr"] = asdict(pr.ocr)
        print(json.dumps(d, ensure_ascii=False, indent=2))
        return
    if pr.ocr:
        print(f"OCR text ({'+'.join(pr.ocr.packs)}, {pr.ocr.passes} pass(es)): {pr.ocr.text}")
    if pr.detection:
        print(f"detected: {pr.detection.code} (confidence {pr.detection.confidence:.2f}, {pr.detection.method})")
    if tr.status == "translated":
        print(f"{tr.source_lang} -> {tr.target_lang} [{tr.backend}]: {tr.text}")
    elif tr.status == "approximate":
        print(f"{tr.source_lang} -> {tr.target_lang} [{tr.backend}, APPROXIMATE, coverage {tr.coverage:.0%}]: {tr.text}")
        print(f"note: {tr.message}")
    elif tr.status == "same_language":
        print(f"no translation needed: {tr.message}")
    else:
        print(f"NO TRANSLATION ({tr.status}): {tr.message}")


def cmd_translate(args) -> int:
    s = _settings(args)
    app = SnapTranslate(build_router(s))
    pr = app.translate_text(args.text, args.to or s.target, args.source)
    _print_result(pr, args.json)
    return 0 if pr.translation.ok else 2


def cmd_image(args) -> int:  # pragma: no cover - needs Tesseract and Pillow
    import numpy as np

    try:
        from PIL import Image
    except ImportError:
        print('reading an image needs: pip install -e ".[ocr]"', file=sys.stderr)
        return 1
    from .ocr import OCRUnavailable, TesseractOCR

    s = _settings(args)
    try:
        engine = TesseractOCR(s.tesseract_cmd)
    except OCRUnavailable as exc:
        print(f"OCR is not available: {exc}", file=sys.stderr)
        return 1
    image = np.asarray(Image.open(args.path).convert("RGB"))
    app = SnapTranslate(build_router(s), ocr=engine)
    try:
        pr = app.translate_image(image, args.to or s.target, args.source)
    except OCRUnavailable as exc:
        print(f"OCR is not available: {exc}", file=sys.stderr)
        return 1
    _print_result(pr, args.json)
    return 0 if pr.translation.ok else 2


def cmd_detect(args) -> int:
    d = BuiltinDetector().detect(args.text)
    print(json.dumps(asdict(d)))
    return 0


def cmd_languages(args) -> int:
    print(f"{'code':8s} {'name':24s} {'tesseract':10s} {'nllb':10s}")
    for lang in REGISTRY.values():
        print(f"{lang.code:8s} {lang.name:24s} {lang.tesseract:10s} {lang.nllb:10s}")
    return 0


def cmd_pairs(args) -> int:
    router = build_router(_settings(args))
    active = [b.name for b in router.active()]
    print("active backends:", ", ".join(active) or "none")
    codes = [normalize(c) for c in args.langs.split(",")]
    for (s, t), names in router.coverage_table(codes).items():
        print(f"{s:>7s} -> {t:7s} {', '.join(names) if names else 'NOT SUPPORTED'}")
    return 0


def cmd_benchmark(args) -> int:
    s = _settings(args)
    items = load_testset(args.testset)
    router = build_router(s)
    systems = router.active() + [CopySource()]
    conditions = ["clean", "ocr-native", "ocr-eng"] if args.condition == "all" else [args.condition]
    rows = run(systems, items, conditions, seed=args.seed, n_boot=args.n_boot)
    acc, wrong = langid_accuracy(BuiltinDetector(), items)
    if args.out:
        save(rows, args.out)
    if args.json:
        print(json.dumps({"langid_accuracy": acc, "rows": [asdict(r) for r in rows]}, indent=2))
        return 0
    print(f"{len(items)} test items, built-in language detector accuracy {acc:.3f}")
    for w in wrong:
        print(f"  detector miss: {w}")
    print(f"{'system':12s} {'condition':10s} {'pair':6s} {'n':>3s} {'answered':>8s} {'BLEU':>6s} {'95% CI':>14s} "
          f"{'chrF':>6s} {'95% CI':>14s} {'input CER':>9s}")
    for r in rows:
        print(f"{r.system:12s} {r.condition:10s} {r.pair:6s} {r.n:3d} {r.answered:8d} {r.bleu:6.1f} "
              f"[{r.bleu_ci[0]:5.1f},{r.bleu_ci[1]:5.1f}] {r.chrf:6.1f} [{r.chrf_ci[0]:5.1f},{r.chrf_ci[1]:5.1f}] "
              f"{r.mean_input_cer:9.3f}")
    return 0


def cmd_doctor(args) -> int:
    s = _settings(args)
    router = build_router(s)
    print("configured backends:", ", ".join(s.backends))
    for b in router.backends:
        print(f"  {b.name:9s} {'available' if b.available() else 'NOT available'}")
    print("LLM API:", "configured (key set)" if s.llm_configured else "not configured")
    try:
        from .ocr import TesseractOCR

        packs = sorted(TesseractOCR(s.tesseract_cmd).available_packs())
        print("Tesseract packs:", ", ".join(packs))
        missing = [lang.tesseract for lang in REGISTRY.values() if lang.tesseract not in packs]
        print("missing packs:", ", ".join(missing) or "none")
    except Exception as exc:  # OCRUnavailable or a missing extra
        print("Tesseract: not available:", exc)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="snaptranslate", description="OCR travel translator with honest fallbacks")
    sub = p.add_subparsers(dest="command", required=True)

    def backends(sp):
        sp.add_argument("--backends", help=f"comma list from {','.join(KNOWN_BACKENDS)} (default: SNAPTRANSLATE_BACKENDS)")

    sp = sub.add_parser("translate", help="translate a text")
    sp.add_argument("text")
    sp.add_argument("--to", help="target language (default: SNAPTRANSLATE_TARGET or en)")
    sp.add_argument("--from", dest="source", help="source language (default: detect)")
    sp.add_argument("--json", action="store_true")
    backends(sp)
    sp.set_defaults(func=cmd_translate)

    sp = sub.add_parser("image", help="read a photo with OCR and translate it")
    sp.add_argument("path")
    sp.add_argument("--to")
    sp.add_argument("--from", dest="source")
    sp.add_argument("--json", action="store_true")
    backends(sp)
    sp.set_defaults(func=cmd_image)

    sp = sub.add_parser("detect", help="detect the language of a text")
    sp.add_argument("text")
    sp.set_defaults(func=cmd_detect)

    sp = sub.add_parser("languages", help="list the supported languages and their codes")
    sp.set_defaults(func=cmd_languages)

    sp = sub.add_parser("pairs", help="show which backend translates each pair")
    sp.add_argument("--langs", default="en,de,fr,es,zh,ja")
    backends(sp)
    sp.set_defaults(func=cmd_pairs)

    sp = sub.add_parser("benchmark", help="score the active backends on a parallel test set")
    sp.add_argument("--testset", help="JSONL with id, src_lang, tgt_lang, src, ref (default: bundled synthetic set)")
    sp.add_argument("--condition", default="clean", choices=["clean", "ocr-native", "ocr-eng", "all"])
    sp.add_argument("--seed", type=int, default=0)
    sp.add_argument("--n-boot", type=int, default=500)
    sp.add_argument("--out", help="write the rows as JSON")
    sp.add_argument("--json", action="store_true")
    backends(sp)
    sp.set_defaults(func=cmd_benchmark)

    sp = sub.add_parser("doctor", help="check backends, Tesseract and language packs (installs nothing)")
    backends(sp)
    sp.set_defaults(func=cmd_doctor)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except UnknownLanguage as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
