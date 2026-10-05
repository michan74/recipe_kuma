"""インメモリのキャッシュ実装（プロセス再起動で消える）。"""

from __future__ import annotations

import threading

from app.cache.base import CachedResult


class InMemoryCache:
    def __init__(self) -> None:
        self._data: dict[str, CachedResult] = {}
        self._lock = threading.Lock()

    def get(self, video_id: str) -> CachedResult | None:
        with self._lock:
            return self._data.get(video_id)

    def set(self, video_id: str, markdown: str, html: str) -> None:
        with self._lock:
            self._data[video_id] = {"markdown": markdown, "html": html}
