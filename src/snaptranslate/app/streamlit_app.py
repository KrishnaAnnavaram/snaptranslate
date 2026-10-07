"""One Streamlit page (extra ``ui``): browser camera or upload, cached models, per-session history.

Run: streamlit run src/snaptranslate/app/streamlit_app.py
"""

from __future__ import annotations

import io

import numpy as np
import streamlit as st

from snaptranslate.config import Settings
from snaptranslate.history import SessionHistory
from snaptranslate.languages import REGISTRY
from snaptranslate.mt.router import build_router
from snaptranslate.pipeline import SnapTranslate


@st.cache_resource
def _shared():
    """Loaded once for the server process: settings, router (with its model cache) and the OCR engine."""
    settings = Settings.from_env()
    router = build_router(settings)
    try:
        from snaptranslate.ocr import TesseractOCR

        ocr = TesseractOCR(settings.tesseract_cmd)
    except Exception as exc:  # OCRUnavailable or a missing extra
        ocr = None
        st.session_state["ocr_problem"] = str(exc)
    return settings, router, ocr


settings, router, ocr = _shared()
if "history" not in st.session_state:  # one history for each browser session, never shared
    st.session_state.history = SessionHistory(settings.history_limit)
app = SnapTranslate(router, ocr=ocr, history=st.session_state.history)

st.set_page_config(page_title="snaptranslate", page_icon=":camera:")
st.title("snaptranslate")
codes = list(REGISTRY)
col1, col2 = st.columns(2)
source = col1.selectbox("From", ["auto"] + codes, format_func=lambda c: "Detect" if c == "auto" else REGISTRY[c].name)
target = col2.selectbox("To", codes, index=codes.index(settings.target) if settings.target in codes else 0,
                        format_func=lambda c: REGISTRY[c].name)
src = None if source == "auto" else source

tab_text, tab_photo, tab_history = st.tabs(["Text", "Photo", "History"])
result = None
with tab_text:
    text = st.text_area("Text")
    if st.button("Translate", key="t") and text.strip():
        result = app.translate_text(text, target, src)
with tab_photo:
    if ocr is None:
        st.warning("OCR is not available: " + st.session_state.get("ocr_problem", "unknown problem"))
    else:
        shot = st.camera_input("Take a photo") or st.file_uploader("or upload a photo", type=["png", "jpg", "jpeg"])
        if shot is not None and st.button("Read and translate", key="p"):
            from PIL import Image

            image = np.asarray(Image.open(io.BytesIO(shot.getvalue())).convert("RGB"))
            result = app.translate_image(image, target, src)
with tab_history:
    for e in reversed(st.session_state.history.entries()):
        st.caption(f"{e.time} {e.source_lang} -> {e.target_lang} ({e.status}, {e.backend})")
        st.write(f"{e.source_text} → {e.text}")
    if st.button("Clear history"):
        st.session_state.history.clear()

if result is not None:
    tr = result.translation
    if result.ocr:
        st.text(f"OCR ({'+'.join(result.ocr.packs)}): {result.ocr.text}")
    if tr.status == "translated":
        st.success(tr.text)
        st.caption(f"{tr.source_lang} -> {tr.target_lang} with {tr.backend}")
    elif tr.status == "approximate":
        st.warning(f"Approximate (word-by-word, coverage {tr.coverage:.0%}): {tr.text}")
    elif tr.status == "same_language":
        st.info(tr.message)
    else:
        st.error(f"No translation: {tr.message}")
