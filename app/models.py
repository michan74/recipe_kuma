"""アプリ全体で使う型定義。"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum


class JobState(str, Enum):
    """ジョブの進捗状態。

    フロント表示マッピング:
      DOWNLOADING       → ダウンロード中
      TRANSCRIBING      → 文字起こし中
      EXTRACTING_FRAMES → 解析中
      ANALYZING         → 解析中
    """

    QUEUED = "queued"
    DOWNLOADING = "downloading"
    TRANSCRIBING = "transcribing"
    EXTRACTING_FRAMES = "extracting_frames"
    ANALYZING = "analyzing"
    DONE = "done"
    ERROR = "error"


@dataclass
class Job:
    """1件の解析ジョブ。メモリ内で状態を保持する。"""

    url: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    video_id: str | None = None
    state: JobState = JobState.QUEUED
    result_markdown: str | None = None
    result_html: str | None = None
    error_message: str | None = None
    created_at: float = field(default_factory=time.time)


@dataclass
class Ingredient:
    """材料1つ。分量が読めない場合は amount に "分量不明" を入れる。"""

    name: str
    amount: str


@dataclass
class Step:
    """手順1つ。

    seconds: その工程が最もよく分かるフレームの秒数（根拠表示・動画シーク用、無ければ None）。
    """

    text: str
    seconds: float | None = None


@dataclass
class Recipe:
    """構造化レシピ。LLMの構造化出力に対応する。"""

    title: str
    ingredients: list[Ingredient]
    steps: list[Step]


@dataclass
class Frame:
    """抽出したフレーム1枚（秒数つき）。"""

    seconds: float
    data: bytes  # JPEG


@dataclass
class Clarify:
    """静止画では判断できず、動画クリップでの再確認が要る箇所。"""

    seconds: float
    reason: str


@dataclass
class VideoClip:
    """パス2でLLMに渡す短い動画クリップ。"""

    seconds: float
    reason: str
    data: bytes  # mp4
