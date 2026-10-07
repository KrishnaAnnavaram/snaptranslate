# snaptranslate with Tesseract and its language packs. No installer runs inside the app.
FROM python:3.11-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      tesseract-ocr tesseract-ocr-eng tesseract-ocr-deu tesseract-ocr-fra tesseract-ocr-spa \
      tesseract-ocr-ita tesseract-ocr-por tesseract-ocr-nld tesseract-ocr-chi-sim tesseract-ocr-chi-tra \
      tesseract-ocr-jpn tesseract-ocr-kor tesseract-ocr-rus \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir ".[ocr,mt,ui]"

ENV SNAPTRANSLATE_BACKENDS=marian,nllb,llm,glossary
EXPOSE 8501
CMD ["streamlit", "run", "src/snaptranslate/app/streamlit_app.py", "--server.address=0.0.0.0"]
