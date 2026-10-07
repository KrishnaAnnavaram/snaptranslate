"""Per-session translation history: in memory, bounded, private to one session.

The prototype wrote every user's text to one shared ``chat_history.json`` file. Here each session
owns its own ``SessionHistory``. Nothing is written to disk unless the user calls ``export_json``.
"""

from __future__ import annotations

import json
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class HistoryEntry:
    time: str
    source_lang: str
    target_lang: str
    source_text: str
    text: str
    status: str
    backend: str


class SessionHistory:
    def __init__(self, limit: int = 20):
        if limit < 0:
            raise ValueError("limit must be 0 or more")
        self.limit = limit
        self._items: deque[HistoryEntry] = deque(maxlen=limit or None)

    def add(self, result) -> None:
        if self.limit == 0:
            return
        self._items.append(
            HistoryEntry(
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
                result.source_lang,
                result.target_lang,
                result.source_text,
                result.text,
                result.status,
                result.backend,
            )
        )

    def entries(self) -> list[HistoryEntry]:
        return list(self._items)

    def clear(self) -> None:
        self._items.clear()

    def export_json(self, path: str | Path) -> Path:
        p = Path(path)
        p.write_text(json.dumps([asdict(e) for e in self._items], ensure_ascii=False, indent=2), encoding="utf-8")
        return p

    def __len__(self) -> int:
        return len(self._items)
