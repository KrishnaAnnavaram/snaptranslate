"""Settings from environment variables. Secrets are SecretStr values and never appear in a repr."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

PREFIX = "SNAPTRANSLATE_"
KNOWN_BACKENDS = ("marian", "nllb", "llm", "glossary")


def load_dotenv(path: str | os.PathLike = ".env") -> None:
    p = Path(path)
    if not p.is_file():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and v and k not in os.environ:
            os.environ[k] = v


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)

    backends: tuple[str, ...] = ("marian", "nllb", "llm", "glossary")
    target: str = "en"
    tesseract_cmd: str = ""
    model_cache_size: int = Field(default=4, ge=1, le=32)
    nllb_model: str = "facebook/nllb-200-distilled-600M"
    llm_base_url: str = ""
    llm_model: str = ""
    llm_api_key: SecretStr = SecretStr("")
    history_limit: int = Field(default=20, ge=0, le=500)

    @field_validator("backends")
    @classmethod
    def _known(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        bad = [b for b in v if b not in KNOWN_BACKENDS]
        if bad:
            raise ValueError(f"unknown backends {bad}; known: {list(KNOWN_BACKENDS)}")
        if not v:
            raise ValueError("at least one backend is required")
        return v

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_base_url and self.llm_model and self.llm_api_key.get_secret_value())

    @classmethod
    def from_env(cls, dotenv: bool = True) -> "Settings":
        if dotenv:
            load_dotenv()
        env = {k[len(PREFIX):].lower(): v for k, v in os.environ.items() if k.startswith(PREFIX) and v.strip()}
        data: dict = {}
        if "backends" in env:
            data["backends"] = tuple(b.strip().lower() for b in env["backends"].split(",") if b.strip())
        for key in ("target", "tesseract_cmd", "nllb_model", "llm_base_url", "llm_model"):
            if key in env:
                data[key] = env[key].strip()
        for key in ("model_cache_size", "history_limit"):
            if key in env:
                data[key] = int(env[key])
        if "llm_api_key" in env:
            data["llm_api_key"] = SecretStr(env["llm_api_key"])
        return cls(**data)
