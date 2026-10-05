"""SQLite によるローカルキャッシュ実装（永続・単一ファイル）。

ローカル開発用。Cloud Run では永続FSが無いため Firestore/GCS 実装に差し替える。
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time

from app.cache.base import CachedResult


class SqliteCache:
    def __init__(self, path: str) -> None:
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        # ワーカースレッドとリクエストスレッドから触るため check_same_thread=False + ロック
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS recipe_cache (
                video_id   TEXT PRIMARY KEY,
                markdown   TEXT NOT NULL,
                html       TEXT NOT NULL,
                created_at REAL NOT NULL
            )
            """
        )
        self._conn.commit()

    def get(self, video_id: str) -> CachedResult | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT markdown, html FROM recipe_cache WHERE video_id = ?",
                (video_id,),
            ).fetchone()
        if row is None:
            return None
        return {"markdown": row[0], "html": row[1]}

    def set(self, video_id: str, markdown: str, html: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO recipe_cache "
                "(video_id, markdown, html, created_at) VALUES (?, ?, ?, ?)",
                (video_id, markdown, html, time.time()),
            )
            self._conn.commit()
