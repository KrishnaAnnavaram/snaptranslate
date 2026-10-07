import numpy as np
import pytest

from snaptranslate.langid import BuiltinDetector, NaiveBayesNgram, script_counts
from snaptranslate.languages import UnknownLanguage, get, is_known, normalize
from snaptranslate.preprocess import autocontrast, binarize, otsu_threshold, prepare_for_ocr, to_grayscale, upscale


@pytest.mark.parametrize(
    "raw, canon",
    [
        ("zh-cn", "zh"), ("zh-CN", "zh"), ("zh_TW", "zh-Hant"), ("zh-hk", "zh-Hant"), ("chi_sim", "zh"),
        ("chi_tra", "zh-Hant"), ("zho_Hans", "zh"), ("deu_Latn", "de"), ("pt-BR", "pt"), ("en-US", "en"),
        ("German", "de"), ("eng", "en"), ("FR", "fr"), ("jpn", "ja"),
    ],
)
def test_normalize(raw, canon):
    # Problem 5: langdetect gives zh-cn, Tesseract chi_sim, NLLB zho_Hans. All map to one code.
    assert normalize(raw) == canon


def test_unknown_codes():
    for bad in ("", "xx", "zh-xx", "klingon"):
        with pytest.raises(UnknownLanguage):
            normalize(bad)
    assert not is_known("xx") and is_known("de")


def test_registry_fields():
    assert get("zh-cn").tesseract == "chi_sim"
    assert get("zh-tw").nllb == "zho_Hant"
    assert get("de").marian == "de"


def test_script_detection():
    d = BuiltinDetector()
    assert d.detect("我们去火车站买票").code == "zh"
    assert d.detect("這是我們的國家").code == "zh-Hant"
    assert d.detect("駅はどこですか").code == "ja"
    assert d.detect("화장실이 어디예요").code == "ko"
    assert d.detect("Где находится вокзал").code == "ru"
    assert d.detect("أين المحطة").code == "ar"
    assert d.detect("स्टेशन कहाँ है").code == "hi"


@pytest.mark.parametrize(
    "text, code",
    [
        ("Die Straßenbahn fährt alle zehn Minuten vom Hauptplatz ab.", "de"),
        ("Le musée d'art moderne se trouve à côté de la cathédrale.", "fr"),
        ("La biblioteca municipal cierra los domingos por la tarde.", "es"),
        ("Il traghetto per l'isola parte ogni mattina alle otto.", "it"),
        ("The bus to the old town leaves from platform four.", "en"),
        ("De veerboot naar het eiland vertrekt elke ochtend om acht uur.", "nl"),
    ],
)
def test_latin_detection_on_unseen_sentences(text, code):
    assert BuiltinDetector().detect(text).code == code


def test_too_short_is_undetermined():
    assert BuiltinDetector().detect("ok").code == "und"
    assert BuiltinDetector().detect("12345 !!").method == "too-short"


def test_low_confidence_is_undetermined():
    det = BuiltinDetector(min_confidence=0.999999)
    assert det.detect("Taxi Hotel Bar").code == "und"


def test_naive_bayes_probabilities():
    nb = NaiveBayesNgram().fit({"a": ["aaaa aaa"], "b": ["bbbb bbb"]})
    code, conf = nb.predict("aaa")
    assert code == "a" and 0.5 < conf <= 1.0


def test_script_counts():
    c = script_counts("abc 漢字 カナ")
    assert c["Latn"] == 3 and c["Han"] == 2 and c["Kana"] == 2


def test_grayscale_and_errors():
    rgb = np.zeros((4, 5, 3), dtype=np.uint8)
    rgb[..., 0] = 255
    g = to_grayscale(rgb)
    assert g.shape == (4, 5) and np.allclose(g, 0.299 * 255)
    assert to_grayscale(np.ones((2, 2), dtype=np.uint8)).shape == (2, 2)
    with pytest.raises(ValueError):
        to_grayscale(np.zeros((2, 2, 2)))


def test_otsu_splits_bimodal_image():
    img = np.concatenate([np.full(500, 40.0), np.full(500, 210.0)])
    t = otsu_threshold(img)
    assert 40 < t < 210


def test_binarize_dark_text_on_light_and_inverted_sign():
    light = np.full((20, 20), 220.0)
    light[8:12, 2:18] = 30  # dark text
    out = binarize(light)
    assert out[10, 10] == 0 and out[0, 0] == 255
    dark_sign = 255 - light  # light text on a dark sign
    out2 = binarize(dark_sign)
    assert out2[10, 10] == 0 and out2[0, 0] == 255


def test_upscale_and_prepare():
    small = np.zeros((100, 50))
    assert upscale(small, 600).shape == (600, 300)
    assert upscale(np.zeros((700, 10)), 600).shape == (700, 10)
    rgb = np.random.default_rng(0).integers(0, 255, (50, 80, 3), dtype=np.uint8)
    out = prepare_for_ocr(rgb, min_height=100)
    assert out.dtype == np.uint8 and set(np.unique(out)) <= {0, 255} and out.shape[0] >= 100


def test_autocontrast_flat_image():
    flat = np.full((5, 5), 100.0)
    assert np.allclose(autocontrast(flat), 100.0)
