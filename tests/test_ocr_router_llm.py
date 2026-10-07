import numpy as np
import pytest
from pydantic import SecretStr

from snaptranslate.config import Settings
from snaptranslate.langid import BuiltinDetector
from snaptranslate.mt import (
    GlossaryTranslator,
    LLMTranslator,
    MarianTranslator,
    ModelCache,
    NLLBTranslator,
    Router,
    TranslationError,
    build_router,
    marian_model_name,
)
from snaptranslate.ocr import FIRST_PASS_PACKS, OCRUnavailable, ScriptedOCR, packs_for, read_image

IMG = np.zeros((10, 10), dtype=np.uint8)


class Fake:
    def __init__(self, name, pairs, out="OUT", fail=False, avail=True):
        self.name, self.pairs, self.out, self.fail, self.avail = name, pairs, out, fail, avail
        self.calls = 0

    def available(self):
        return self.avail

    def supports(self, s, t):
        return (s, t) in self.pairs

    def translate(self, texts, s, t):
        self.calls += 1
        if self.fail:
            raise TranslationError("model crashed")
        return [self.out for _ in texts]


# ---------------------------------------------------------------- OCR


def test_ocr_uses_the_source_language_pack():
    # Problem 4: German text is read with the German pack (plus English), not English only.
    assert packs_for("de", {"eng", "deu"}) == ("deu", "eng")
    assert packs_for("en", {"eng", "deu"}) == ("eng",)
    assert packs_for("zh-cn", {"chi_sim"}) == ("chi_sim",)


def test_missing_pack_raises_with_install_hint():
    with pytest.raises(OCRUnavailable, match="tesseract-ocr-chi-sim"):
        packs_for("zh", {"eng"})
    with pytest.raises(OCRUnavailable):
        packs_for(None, {"jpn"})


def test_two_pass_ocr_when_language_unknown():
    engine = ScriptedOCR({"*": "Der Ausgang ist links und der Bahnhof ist heute geschlossen."})
    res, detected = read_image(engine, IMG, None, BuiltinDetector())
    assert engine.calls[0] == FIRST_PASS_PACKS
    assert engine.calls[1] == ("deu", "eng")
    assert detected == "de" and res.passes == 2


def test_one_pass_when_language_given():
    engine = ScriptedOCR({"fra+eng": "La sortie est à gauche."})
    res, detected = read_image(engine, IMG, "fr", BuiltinDetector())
    assert engine.calls == [("fra", "eng")] and res.text == "La sortie est à gauche." and detected is None


def test_undetermined_after_first_pass():
    engine = ScriptedOCR({"*": "ok"})
    res, detected = read_image(engine, IMG, None, BuiltinDetector())
    assert detected is None and res.passes == 1 and "undetermined" in res.notes[0]


# ---------------------------------------------------------------- router


def test_same_language_is_not_a_translation():
    # Problem 6: en->en is reported as same_language, not as a translation.
    r = Router([Fake("a", {("en", "de")})]).translate("Hello", "en-US", "en")
    assert r.status == "same_language" and r.ok and r.backend == ""


def test_unsupported_pair_never_echoes_the_input():
    # Problem 6: the prototype showed the input as an "estimated meaning".
    r = Router([GlossaryTranslator()]).translate("Wo ist der Bahnhof?", "de", "ja")
    assert r.status == "unsupported_pair" and r.text == "" and not r.ok
    assert "German to Japanese" in r.message


def test_unknown_language_and_empty_text():
    router = Router([GlossaryTranslator()])
    assert router.translate("x", "xx", "en").status == "unsupported_pair"
    assert router.translate("   ", "de", "en").status == "empty"


def test_router_falls_back_to_next_backend():
    a = Fake("a", {("de", "en")}, fail=True)
    b = Fake("b", {("de", "en")}, out="Hello")
    r = Router([a, b]).translate("Hallo", "de", "en")
    assert r.status == "translated" and r.text == "Hello" and r.backend == "b" and r.tried == ("a", "b")


def test_all_backends_fail():
    r = Router([Fake("a", {("de", "en")}, fail=True)]).translate("Hallo", "de", "en")
    assert r.status == "failed" and r.text == "" and "crashed" in r.message


def test_unavailable_backends_are_skipped():
    a = Fake("a", {("de", "en")}, avail=False)
    r = Router([a, GlossaryTranslator()]).translate("Der Ausgang ist links.", "de", "en")
    assert a.calls == 0 and r.backend == "glossary"


def test_glossary_is_approximate_with_coverage():
    r = Router([GlossaryTranslator()]).translate("Die Küche ist bis Mitternacht geöffnet.", "de", "en")
    assert r.status == "approximate" and 0.6 <= r.coverage < 1.0
    assert "[Mitternacht]" in r.text or "Mitternacht" in r.text


def test_glossary_refuses_low_coverage():
    with pytest.raises(TranslationError, match="knows only"):
        GlossaryTranslator().translate(["Völlig unbekannte Wörterkette hier drin"], "de", "en")
    with pytest.raises(TranslationError):
        GlossaryTranslator().translate(["x"], "de", "fr")


def test_glossary_phrases_and_elision():
    g = GlossaryTranslator()
    assert g.gloss("Défense de fumer.", "fr")[0] == "No smoking."
    out, cov = g.gloss("La cuisine est ouverte jusqu'à minuit.", "fr")
    assert out == "The kitchen is open until midnight." and cov == 1.0


def test_marian_pairs_and_chinese_model_name():
    # Problem 5: Chinese maps to the existing opus-mt-zh-en model.
    m = MarianTranslator()
    assert m.supports("zh-cn", "en") and m.supports("zh-TW", "en")
    assert marian_model_name("zh-cn", "en") == "Helsinki-NLP/opus-mt-zh-en"
    assert not m.supports("de", "ja")
    assert NLLBTranslator().supports("de", "ja")


def test_model_cache_loads_once_and_evicts():
    # Problem 9: a model loads once, not on every click.
    cache = ModelCache(2)
    loads = []
    for key in ["a", "a", "b", "a", "c", "b"]:
        cache.get(key, lambda k=key: loads.append(k) or k)
    assert loads == ["a", "b", "c", "b"] and len(cache) == 2 and cache.loads == 4
    with pytest.raises(ValueError):
        ModelCache(0)


def test_build_router_order(monkeypatch):
    s = Settings(backends=("llm", "glossary"))
    router = build_router(s)
    assert [b.name for b in router.backends] == ["llm", "glossary"]
    assert [b.name for b in router.active()] == ["glossary"]  # no LLM key configured


# ---------------------------------------------------------------- LLM API and secrets


def test_llm_translator_request_is_deterministic():
    # Problem 3: an instruction model at temperature 0, not a sampled code model.
    seen = {}

    def transport(url, headers, body):
        seen.update(url=url, headers=headers, body=body)
        return {"choices": [{"message": {"content": " The exit is on the left. "}}]}

    t = LLMTranslator("https://api.example.test/v1/", "some-model", SecretStr("secret-value-123"), transport)
    assert t.available() and t.supports("de", "en")
    assert t.translate(["Der Ausgang ist links."], "de", "en") == ["The exit is on the left."]
    assert seen["url"] == "https://api.example.test/v1/chat/completions"
    assert seen["body"]["temperature"] == 0
    assert "German" in seen["body"]["messages"][0]["content"]


def test_llm_errors_and_repr_hide_the_key():
    # Problem 1: the key never appears in a repr or an error message.
    def broken(url, headers, body):
        return {"unexpected": True}

    t = LLMTranslator("https://x.test", "m", SecretStr("secret-value-123"), broken)
    assert "secret-value-123" not in repr(t)
    with pytest.raises(TranslationError) as exc:
        t.translate(["Hallo"], "de", "en")
    assert "secret-value-123" not in str(exc.value)

    def empty(url, headers, body):
        return {"choices": [{"message": {"content": "  "}}]}

    with pytest.raises(TranslationError, match="empty"):
        LLMTranslator("https://x.test", "m", SecretStr("k"), empty).translate(["Hallo"], "de", "en")


def test_settings_from_env_hides_key(monkeypatch):
    monkeypatch.setenv("SNAPTRANSLATE_LLM_API_KEY", "secret-value-123")
    monkeypatch.setenv("SNAPTRANSLATE_LLM_BASE_URL", "https://x.test")
    monkeypatch.setenv("SNAPTRANSLATE_LLM_MODEL", "m")
    monkeypatch.setenv("SNAPTRANSLATE_BACKENDS", "llm, glossary")
    monkeypatch.setenv("SNAPTRANSLATE_MODEL_CACHE_SIZE", "2")
    s = Settings.from_env(dotenv=False)
    assert s.llm_configured and s.backends == ("llm", "glossary") and s.model_cache_size == 2
    assert "secret-value-123" not in repr(s) and "secret-value-123" not in str(s.model_dump())
    monkeypatch.setenv("SNAPTRANSLATE_BACKENDS", "argos")
    with pytest.raises(ValueError):
        Settings.from_env(dotenv=False)
