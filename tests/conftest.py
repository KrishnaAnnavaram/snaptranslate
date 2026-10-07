import os

import pytest


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch, tmp_path):
    for key in list(os.environ):
        if key.startswith("SNAPTRANSLATE_"):
            monkeypatch.delenv(key, raising=False)
    # Offline by default: tests never load a neural model or call an API.
    monkeypatch.setenv("SNAPTRANSLATE_BACKENDS", "glossary")
    monkeypatch.chdir(tmp_path)
