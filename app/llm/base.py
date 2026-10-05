"""LLM実装の差し替え点。

初版は Gemini 実装（`gemini.py`）。将来 Claude 実装などを追加する場合も
この `LLMClient` プロトコルに合わせれば差し替え可能。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.models import Clarify, Frame, Recipe, VideoClip


class LLMError(Exception):
    """LLM呼び出しに失敗したときの例外。"""


@dataclass
class RecipeResult:
    """LLMによるレシピ抽出結果（パス1）。

    found が False の場合、その動画からレシピは抽出できなかったことを示す。
    clarify は、静止画では判断できず動画クリップでの再確認が要る箇所のリスト。
    """

    found: bool
    recipe: Recipe | None = None
    clarify: list[Clarify] = field(default_factory=list)


class LLMClient(Protocol):
    """レシピ抽出を行うLLMクライアントの共通インタフェース。"""

    def extract_recipe(
        self,
        transcript: str,
        description: str,
        frames: list[Frame],
    ) -> RecipeResult:
        """パス1: 文字起こし・概要欄・秒数つきフレームからレシピを抽出する。

        静止画では判断できない工程があれば clarify に時刻を入れて返す。

        Raises:
            LLMError: API呼び出しや応答の解釈に失敗した場合。
        """
        ...

    def refine_recipe(self, recipe: Recipe, clips: list[VideoClip]) -> Recipe:
        """パス2: 短い動画クリップを見て、該当工程の手法を具体化したレシピを返す。

        Raises:
            LLMError: API呼び出しや応答の解釈に失敗した場合。
        """
        ...
