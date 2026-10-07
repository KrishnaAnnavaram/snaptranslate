import ast
import json
import re
from pathlib import Path

import numpy as np
import pytest

from snaptranslate.cli import main
from snaptranslate.history import SessionHistory
from snaptranslate.mt import GlossaryTranslator, Router
from snaptranslate.ocr import OCRUnavailable, ScriptedOCR
from snaptranslate.pipeline import SnapTranslate

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "snaptranslate"


def make(history=None, ocr=None):
    return SnapTranslate(Router([GlossaryTranslator()]), ocr=ocr, history=history)


def test_text_pipeline_detects_and_translates():
    res = make().translate_text("La sortie est à gauche.", "en")
    assert res.detection.code == "fr" and res.translation.text == "The exit is on the left."


def test_undetermined_language_asks_the_user():
    res = make().translate_text("ok", "en")
    assert res.translation.status == "undetermined_language" and "Choose the source language" in res.translation.message
    assert make().translate_text("x", "en", source="klingon").translation.status == "undetermined_language"


def test_image_pipeline_with_scripted_ocr():
    ocr = ScriptedOCR({"*": "Der Ausgang ist links und der Bahnhof ist heute geschlossen.", "deu+eng": "Der Ausgang ist links."})
    res = make(ocr=ocr).translate_image(np.zeros((5, 5)), "en")
    assert res.input_kind == "image" and res.ocr.passes == 2 and res.translation.text == "The exit is on the left."
    empty = make(ocr=ScriptedOCR({"*": ""})).translate_image(np.zeros((5, 5)), "en", "de")
    assert empty.translation.status == "empty"
    with pytest.raises(OCRUnavailable):
        make().translate_image(np.zeros((5, 5)), "en")


def test_history_is_per_session_and_bounded(tmp_path):
    # Problem 10: each session owns its history. Nothing is written to a shared file.
    a, b = make(SessionHistory(2)), make(SessionHistory(2))
    for text in ["Der Ausgang ist links.", "Wo ist die Apotheke?", "Der Bahnhof ist heute geschlossen."]:
        a.translate_text(text, "en", "de")
    assert len(a.history) == 2 and len(b.history) == 0
    assert a.history.entries()[0].source_text == "Wo ist die Apotheke?"
    assert list(tmp_path.iterdir()) == []
    out = a.history.export_json(tmp_path / "mine.json")
    assert len(json.loads(out.read_text(encoding="utf-8"))) == 2
    off = make(SessionHistory(0))
    off.translate_text("Der Ausgang ist links.", "en", "de")
    assert len(off.history) == 0
    a.history.clear()
    assert len(a.history) == 0
    with pytest.raises(ValueError):
        SessionHistory(-1)


def test_failed_translation_not_in_history():
    app = make()
    app.translate_text("Wo ist der Bahnhof?", "ja", "de")
    assert len(app.history) == 0


# ---------------------------------------------------------------- CLI


def test_cli_translate(capsys):
    assert main(["translate", "Où est la pharmacie ?", "--to", "en"]) == 0
    assert "Where is the pharmacy?" in capsys.readouterr().out
    assert main(["translate", "Wo ist der Bahnhof?", "--to", "ja"]) == 2
    assert "NO TRANSLATION" in capsys.readouterr().out
    assert main(["translate", "Hello friends", "--from", "en", "--to", "en"]) == 0
    assert "no translation needed" in capsys.readouterr().out


def test_cli_json_and_errors(capsys):
    assert main(["translate", "Prohibido fumar.", "--from", "es", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["translation"]["status"] == "approximate" and data["translation"]["text"] == "No smoking."
    assert main(["translate", "x", "--to", "klingon", "--from", "de"]) == 2


def test_cli_other_commands(capsys, tmp_path):
    assert main(["detect", "Wo ist der Bahnhof bitte?"]) == 0
    assert json.loads(capsys.readouterr().out)["code"] == "de"
    assert main(["languages"]) == 0
    assert "chi_sim" in capsys.readouterr().out
    assert main(["pairs", "--langs", "de,en,ja"]) == 0
    out = capsys.readouterr().out
    assert "de ->" in out and "NOT SUPPORTED" in out
    assert main(["benchmark", "--n-boot", "20", "--out", str(tmp_path / "b.json")]) == 0
    assert "copy-source" in capsys.readouterr().out
    assert main(["benchmark", "--n-boot", "10", "--condition", "ocr-eng", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["rows"][0]["condition"] == "ocr-eng"
    assert main(["doctor"]) == 0
    assert "glossary" in capsys.readouterr().out


# ---------------------------------------------------------------- hygiene (problems 1, 7, 8, 11)


def _sources():
    return [p for p in SRC.rglob("*.py")]


def test_no_bare_except_in_source():
    for path in _sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        bare = [n.lineno for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler) and n.type is None]
        assert not bare, f"bare except in {path.name} at {bare}"


def test_no_subprocess_installer_or_server_camera():
    for path in _sources():
        text = path.read_text(encoding="utf-8")
        for forbidden in ("os.system", "subprocess", "VideoCapture", "import cv2", ".exe"):
            assert forbidden not in text, f"{forbidden} in {path.name}"


def test_no_key_like_strings_in_repository():
    pattern = re.compile(r"sk-[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{30,}|hf_[A-Za-z0-9]{25,}|ghp_[A-Za-z0-9]{30,}")
    for path in ROOT.rglob("*"):
        if path.is_file() and path.suffix in {".py", ".md", ".toml", ".json", ".jsonl", ".yml", ".example"} \
                and ".venv" not in path.parts and ".git" not in path.parts:
            assert not pattern.search(path.read_text(encoding="utf-8", errors="ignore")), path
