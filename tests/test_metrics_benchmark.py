import json

import pytest

from snaptranslate.benchmark import CopySource, langid_accuracy, load_testset, run, save, score_system
from snaptranslate.langid import BuiltinDetector
from snaptranslate.metrics import (
    bootstrap_ci,
    cer,
    corpus_bleu,
    corpus_chrf,
    levenshtein,
    paired_bootstrap,
    tokenize_13a,
    wer,
)
from snaptranslate.mt import GlossaryTranslator
from snaptranslate.synthetic import ocr_english_pack, ocr_native_pack

H = ["The train station is closed today.", "No smoking please", "Where is pharmacy?",
     "The kitchen open until 12, now.", "x"]
R = ["The train station is closed today.", "Please do not smoke.", "Where is the pharmacy?",
     "The kitchen is open until midnight.", "The exit is on the left."]


def test_bleu_and_chrf_reference_values():
    # Values match sacrebleu 2.x on the same input (checked when the package was installed).
    assert corpus_bleu(H, R) == pytest.approx(34.2331174535977, abs=1e-6)
    assert corpus_chrf(H, R) == pytest.approx(57.87110034009684, abs=1e-6)


def test_metrics_match_sacrebleu_when_installed():
    sacrebleu = pytest.importorskip("sacrebleu")
    assert corpus_bleu(H, R) == pytest.approx(sacrebleu.corpus_bleu(H, [R]).score, abs=1e-6)
    assert corpus_chrf(H, R) == pytest.approx(sacrebleu.corpus_chrf(H, [R]).score, abs=1e-6)


def test_metric_edges():
    assert corpus_bleu(R, R) == pytest.approx(100.0)
    assert corpus_bleu([""] * 5, R) == 0.0
    assert corpus_chrf(R, R) == pytest.approx(100.0)
    assert corpus_chrf([""], ["abc"]) == 0.0
    with pytest.raises(ValueError):
        corpus_bleu(["a"], [])
    assert tokenize_13a("Hello, world.") == "Hello , world ."


def test_cer_wer():
    assert levenshtein("kitten", "sitting") == 3
    assert cer("tiber", "über") == pytest.approx(0.5)
    assert wer("the exit left", "the exit is left") == pytest.approx(0.25)


def test_bootstrap_intervals():
    lo, hi = bootstrap_ci(H, R, corpus_chrf, n_boot=200)
    assert lo <= corpus_chrf(H, R) <= hi
    assert paired_bootstrap(R, H, R, corpus_bleu, n_boot=100) == 1.0


def test_each_output_is_scored_against_its_own_reference():
    # Problem 2: shuffling the references (the prototype used one fixed sentence) destroys the score.
    items = [i for i in load_testset() if i.src_lang == "de"]
    hyps = [GlossaryTranslator().gloss(i.src, "de")[0] for i in items]
    refs = [i.ref for i in items]
    assert corpus_bleu(hyps, refs) > 40
    assert corpus_bleu(hyps, [refs[0]] * len(refs)) < 15


def test_copy_source_baseline_is_low_and_glossary_beats_it():
    items = load_testset()
    gl = {r.pair: r for r in score_system(GlossaryTranslator(), items, n_boot=50)}
    cp = {r.pair: r for r in score_system(CopySource(), items, n_boot=50)}
    for pair in ("de-en", "fr-en", "es-en"):
        assert gl[pair].bleu > cp[pair].bleu + 30
        assert cp[pair].bleu < 5


def test_wrong_ocr_pack_hurts_the_translation():
    # Problem 4 on synthetic noise: losing accents lowers the score for each language.
    items = load_testset()
    rows = run([GlossaryTranslator()], items, ["clean", "ocr-eng"], n_boot=50)
    clean = {r.pair: r.chrf for r in rows if r.condition == "clean"}
    noisy = {r.pair: r.chrf for r in rows if r.condition == "ocr-eng"}
    assert all(noisy[p] < clean[p] for p in clean)
    with pytest.raises(ValueError):
        run([GlossaryTranslator()], items, ["fog"])


def test_ocr_noise_functions():
    assert ocr_english_pack("über", seed=1, char_error_rate=0) in ("uber", "tiber")
    assert ocr_english_pack("¿Dónde?", char_error_rate=0) == "Donde?"
    assert ocr_native_pack("über", char_error_rate=0) == "über"


def test_failed_items_count_as_empty_output():
    items = load_testset()
    rows = score_system(GlossaryTranslator(min_coverage=1.01), items, n_boot=20)
    assert all(r.answered == 0 and r.bleu == 0.0 for r in rows)


def test_testset_loader(tmp_path):
    items = load_testset()
    assert len(items) == 36 and {i.src_lang for i in items} == {"de", "fr", "es"}
    p = tmp_path / "t.jsonl"
    line = json.dumps({"id": "a", "src_lang": "German", "tgt_lang": "en-GB", "src": "Hallo", "ref": "Hello"})
    p.write_text(line + "\n" + line + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        load_testset(p)
    p.write_text(line + "\n", encoding="utf-8")
    assert load_testset(p)[0].src_lang == "de"


def test_langid_accuracy_on_testset():
    acc, wrong = langid_accuracy(BuiltinDetector(), load_testset())
    assert acc >= 0.85 and len(wrong) == round((1 - acc) * 36)


def test_save_rows(tmp_path):
    rows = score_system(CopySource(), load_testset()[:3], n_boot=10)
    data = json.loads(save(rows, tmp_path / "o" / "r.json").read_text())
    assert data[0]["system"] == "copy-source"
