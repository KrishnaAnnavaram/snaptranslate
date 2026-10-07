"""The translator interface and the result type."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Callable, Literal, Protocol, Sequence

Status = Literal[
    "translated", "approximate", "same_language", "unsupported_pair", "undetermined_language", "failed", "empty"
]


@dataclass(frozen=True)
class TranslationResult:
    source_text: str
    text: str  # empty unless status is "translated", "approximate" or "same_language"
    source_lang: str
    target_lang: str
    status: Status
    backend: str = ""
    message: str = ""
    coverage: float = 1.0  # share of source words that the backend could translate
    tried: tuple[str, ...] = field(default=())

    @property
    def ok(self) -> bool:
        return self.status in ("translated", "approximate", "same_language")


class Translator(Protocol):
    name: str

    def available(self) -> bool: ...

    def supports(self, src: str, tgt: str) -> bool: ...

    def translate(self, texts: Sequence[str], src: str, tgt: str) -> list[str]: ...


class TranslationError(RuntimeError):
    pass


class ModelCache:
    """A small LRU cache for loaded models. A model loads once and stays until evicted."""

    def __init__(self, max_size: int = 4):
        if max_size < 1:
            raise ValueError("max_size must be 1 or more")
        self.max_size = max_size
        self._items: OrderedDict[str, object] = OrderedDict()
        self.loads = 0

    def get(self, key: str, loader: Callable[[], object]) -> object:
        if key in self._items:
            self._items.move_to_end(key)
            return self._items[key]
        value = loader()
        self.loads += 1
        self._items[key] = value
        if len(self._items) > self.max_size:
            self._items.popitem(last=False)
        return value

    def __contains__(self, key: str) -> bool:
        return key in self._items

    def __len__(self) -> int:
        return len(self._items)
