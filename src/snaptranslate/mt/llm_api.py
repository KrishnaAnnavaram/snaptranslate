"""An instruction-tuned LLM behind an OpenAI-compatible chat API.

The API key comes only from ``SNAPTRANSLATE_LLM_API_KEY``. Temperature is 0, so the output is as
stable as the provider allows. The key never appears in an error message or a repr.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Callable, Sequence

from pydantic import SecretStr

from ..languages import get, normalize, REGISTRY
from .base import TranslationError

SYSTEM = (
    "You are a translation engine. Translate the user's text from {src} to {tgt}. "
    "Output only the translation, with no notes, no quotes and no transliteration."
)

Transport = Callable[[str, dict, dict], dict]


def _urllib_transport(url: str, headers: dict, body: dict) -> dict:  # pragma: no cover - network
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 - URL from settings
        return json.loads(resp.read().decode("utf-8"))


class LLMTranslator:
    name = "llm"

    def __init__(self, base_url: str, model: str, api_key: SecretStr, transport: Transport | None = None):
        self.base_url, self.model, self._key = base_url.rstrip("/"), model, api_key
        self._transport = transport or _urllib_transport

    def __repr__(self) -> str:
        return f"LLMTranslator(base_url={self.base_url!r}, model={self.model!r}, api_key=***)"

    def available(self) -> bool:
        return bool(self.base_url and self.model and self._key.get_secret_value())

    def supports(self, src: str, tgt: str) -> bool:
        return normalize(src) in REGISTRY and normalize(tgt) in REGISTRY

    def translate(self, texts: Sequence[str], src: str, tgt: str) -> list[str]:
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self._key.get_secret_value()}"}
        out = []
        for text in texts:
            body = {
                "model": self.model,
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": SYSTEM.format(src=get(src).name, tgt=get(tgt).name)},
                    {"role": "user", "content": text},
                ],
            }
            try:
                data = self._transport(self.base_url + "/chat/completions", headers, body)
                content = data["choices"][0]["message"]["content"].strip()
            except (urllib.error.URLError, KeyError, IndexError, TypeError, ValueError, TimeoutError) as exc:
                raise TranslationError(f"LLM request failed: {type(exc).__name__}") from exc
            if not content:
                raise TranslationError("LLM returned an empty translation")
            out.append(content)
        return out
