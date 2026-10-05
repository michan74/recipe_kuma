"""解析結果キャッシュの抽象インタフェース。

動画ID → 結果（markdown / html）をキャッシュする。
ローカルは SQLite 実装、Cloud Run では Firestore(or GCS) 実装に差し替える想定。
"""

from __future__ import annotations

from typing import Protocol, TypedDict


class CachedResult(TypedDict):
    markdown: str
    html: str


class RecipeCache(Protocol):
    """動画ID単位で解析結果を保存・取得する。"""

    def get(self, video_id: str) -> CachedResult | None:
        """キャッシュを引く。無ければ None。"""
        ...

    def set(self, video_id: str, markdown: str, html: str) -> None:
        """成功結果を保存する。"""
        ...
