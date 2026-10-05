"""Gemini によるレシピ抽出実装（2パス）。

パス1: 秒数つきフレーム + 文字起こし + 概要欄 → 暫定レシピ + 不明箇所(clarify)。
パス2: 不明箇所の短い動画クリップ → 該当工程の手法を具体化。
"""

from __future__ import annotations

import json
import logging
import time

from google import genai
from google.genai import types

from app import config
from app.llm.base import LLMClient, LLMError, RecipeResult
from app.models import Clarify, Frame, Ingredient, Recipe, Step, VideoClip


def _sec(v) -> float | None:
    """スキーマの seconds（-1や負は「根拠なし」）を float|None に正規化。"""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f >= 0 else None

# 一時的なサーバー側エラー（時間を置けば回復することが多い）
_RETRYABLE_CODES = {429, 500, 503}
_RETRYABLE_HINTS = ("503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED", "500", "overloaded")
_MAX_ATTEMPTS = 4  # 合計4回（待機 1s, 2s, 4s）

logger = logging.getLogger("recipe_kuma.gemini")

# media_resolution 文字列 → SDK enum
_MEDIA_RES_MAP = {
    "low": types.MediaResolution.MEDIA_RESOLUTION_LOW,
    "medium": types.MediaResolution.MEDIA_RESOLUTION_MEDIUM,
    "high": types.MediaResolution.MEDIA_RESOLUTION_HIGH,
}

_INGREDIENTS_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "amount": {"type": "string"},
        },
        "required": ["name", "amount"],
    },
}

_STEPS_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "seconds": {"type": "number"},  # その工程が写るフレーム秒。無ければ -1
        },
        "required": ["text", "seconds"],
    },
}

# パス1: レシピ + 不明箇所(clarify)
_SCHEMA_PASS1 = {
    "type": "object",
    "properties": {
        "found": {"type": "boolean"},
        "title": {"type": "string"},
        "ingredients": _INGREDIENTS_SCHEMA,
        "steps": _STEPS_SCHEMA,
        "clarify": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "seconds": {"type": "number"},
                    "reason": {"type": "string"},
                },
                "required": ["seconds", "reason"],
            },
        },
    },
    "required": ["found", "title", "ingredients", "steps", "clarify"],
}

# パス2: 具体化したレシピ本体
_SCHEMA_PASS2 = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "ingredients": _INGREDIENTS_SCHEMA,
        "steps": _STEPS_SCHEMA,
    },
    "required": ["title", "ingredients", "steps"],
}

_PROMPT_PASS1 = """\
あなたは料理動画からレシピを抽出するアシスタントです。
音声の文字起こし・動画の概要欄・各時刻のフレーム画像を総合して、レシピを構造化データで抽出してください。

重要な指示:
- 材料の分量は、画面のテロップ（焼き込み文字）に書かれていることが多いので、フレーム画像をよく見て読み取ること。
- テロップの書き方は動画ごとに様々。表記揺れは文脈から材料名と分量に正しく対応付けること。
- 音声とテロップで情報が食い違う場合、分量は基本的にテロップ（画面表示）を優先すること。
- 分量がどうしても読み取れない材料は、amount を "分量不明" にすること（材料自体は省略しない）。
- 手順は調理の順序どおりに並べること。
- 切り方・下処理・火の通し方などの調理手法は、フレーム画像から具体的に読み取って手順に書くこと
  （例: みじん切り / 薄切り / 十字の切れ目を入れる / 炒める・煮る・揚げる）。各手順は視聴者が再現できる具体性で書く。
- ただし、静止画では切り方などの動作がはっきり判断できない場合は、推測で曖昧に書かず、その工程の時刻を clarify に出すこと（下記）。
- 各手順には seconds（その工程が最もよく分かるフレームの時刻・秒）を入れること。渡された [t=..s] ラベルを参照する。
  該当フレームが無ければ seconds は -1 にする。（※材料には seconds は不要）
- これが料理のレシピ動画だと判断できない、またはレシピを抽出できない場合は found を false にすること。

clarify（重要）:
- 「切り方・折り方・こね方」など、静止画だけでは**動作が判断できない工程**があれば、その工程に対応するフレームの時刻(秒)を clarify に入れること。
- reason には「何が判断できないか」を書く（例: "じゃがいもの切り方が静止画では不明"）。
- 分からない工程を推測で書くくらいなら、clarify に出して動画で確認する方を優先すること。
- 最大3件まで。静止画で十分に判断できる場合は clarify を空配列にすること。
"""

_PROMPT_PASS2 = """\
以下に「現在のレシピ(JSON)」と、静止画では判断が難しかった工程の「短い動画クリップ」があります。
クリップの動き（切り方・手法）をよく見て、該当する手順を具体的で再現可能な表現に更新し、レシピ全体をJSONで返してください。

- 材料(ingredients)は基本的に変えないこと。手順(steps)の具体化に集中すること。
- 例: 「切れ目を入れる」→「十字に深さ1cmの切れ目を入れる」など、動画から分かる具体性を反映する。
- 各手順の seconds は、渡された元の値を維持すること（分からなければ -1）。
"""


class GeminiClient(LLMClient):
    """Gemini を使ったレシピ抽出クライアント（2パス）。"""

    def __init__(self) -> None:
        if not config.GEMINI_API_KEY:
            raise LLMError("GEMINI_API_KEY が設定されていません（.env を確認してください）")
        self._client = genai.Client(api_key=config.GEMINI_API_KEY)

    def _generate_with_retry(self, contents: list, schema: dict):
        """generate_content を一時エラー時に指数バックオフでリトライする。"""
        cfg_kwargs = dict(
            response_mime_type="application/json",
            response_schema=schema,
        )
        media_res = _MEDIA_RES_MAP.get(config.MEDIA_RESOLUTION)
        if media_res is not None:
            cfg_kwargs["media_resolution"] = media_res
        cfg = types.GenerateContentConfig(**cfg_kwargs)
        last_exc: Exception | None = None
        for attempt in range(_MAX_ATTEMPTS):
            try:
                return self._client.models.generate_content(
                    model=config.GEMINI_MODEL,
                    contents=contents,
                    config=cfg,
                )
            except Exception as e:  # noqa: BLE001 - 一時エラーか判定してリトライ
                last_exc = e
                code = getattr(e, "code", None)
                transient = code in _RETRYABLE_CODES or any(h in str(e) for h in _RETRYABLE_HINTS)
                if transient and attempt < _MAX_ATTEMPTS - 1:
                    time.sleep(2**attempt)  # 1s, 2s, 4s
                    continue
                if transient:
                    raise LLMError(
                        "Geminiが一時的に混雑しています（しばらく待って再実行してください）"
                    ) from e
                raise LLMError(f"Gemini 呼び出しに失敗しました: {e}") from e
        raise LLMError(f"Gemini 呼び出しに失敗しました: {last_exc}")

    @staticmethod
    def _parse_ingredients(items) -> list[Ingredient]:
        return [
            Ingredient(name=i.get("name", ""), amount=i.get("amount", "分量不明"))
            for i in (items or [])
        ]

    @staticmethod
    def _parse_steps(items) -> list[Step]:
        steps: list[Step] = []
        for s in items or []:
            if isinstance(s, dict):
                steps.append(Step(text=s.get("text", ""), seconds=_sec(s.get("seconds"))))
            else:
                steps.append(Step(text=str(s)))
        return steps

    def extract_recipe(
        self,
        transcript: str,
        description: str,
        frames: list[Frame],
    ) -> RecipeResult:
        contents: list = [
            _PROMPT_PASS1,
            f"【概要欄】\n{description or '（なし）'}",
            f"【音声の文字起こし】\n{transcript or '（なし）'}",
            "【以下は各時刻のフレーム画像です】",
        ]
        for fr in frames:
            contents.append(f"[t={fr.seconds:.1f}s]")
            contents.append(types.Part.from_bytes(data=fr.data, mime_type="image/jpeg"))

        logger.info(
            "Gemini送信(パス1): model=%s / frames=%d枚 / transcript=%d文字 / description=%d文字",
            config.GEMINI_MODEL,
            len(frames),
            len(transcript),
            len(description or ""),
        )
        logger.info("  [transcript] %s", (transcript or "（なし）")[:2000])
        logger.info("  [description] %s", (description or "（なし）")[:1000])

        response = self._generate_with_retry(contents, _SCHEMA_PASS1)
        try:
            data = json.loads(response.text)
        except Exception as e:  # noqa: BLE001 - 応答(JSON)の解釈失敗
            raise LLMError(f"Gemini 応答の解釈に失敗しました: {e}") from e

        if not data.get("found"):
            return RecipeResult(found=False)

        recipe = Recipe(
            title=data.get("title", ""),
            ingredients=self._parse_ingredients(data.get("ingredients")),
            steps=self._parse_steps(data.get("steps")),
        )
        clarify = [
            Clarify(seconds=float(c.get("seconds", 0)), reason=c.get("reason", ""))
            for c in data.get("clarify", [])
        ]
        logger.info("  パス1結果: clarify=%d件", len(clarify))
        return RecipeResult(found=True, recipe=recipe, clarify=clarify)

    def refine_recipe(self, recipe: Recipe, clips: list[VideoClip]) -> Recipe:
        recipe_json = json.dumps(
            {
                "title": recipe.title,
                "ingredients": [
                    {"name": i.name, "amount": i.amount} for i in recipe.ingredients
                ],
                "steps": [
                    {"text": s.text, "seconds": s.seconds if s.seconds is not None else -1}
                    for s in recipe.steps
                ],
            },
            ensure_ascii=False,
        )
        contents: list = [
            _PROMPT_PASS2,
            f"【現在のレシピ(JSON)】\n{recipe_json}",
            "【以下は、判断が難しかった工程の短い動画クリップです】",
        ]
        for clip in clips:
            contents.append(f"[t={clip.seconds:.1f}s / 確認理由: {clip.reason}]")
            contents.append(types.Part.from_bytes(data=clip.data, mime_type="video/mp4"))

        logger.info("Gemini送信(パス2): clips=%d本", len(clips))

        response = self._generate_with_retry(contents, _SCHEMA_PASS2)
        try:
            data = json.loads(response.text)
        except Exception as e:  # noqa: BLE001 - 応答(JSON)の解釈失敗
            raise LLMError(f"Gemini 応答の解釈に失敗しました: {e}") from e

        ing_data = data.get("ingredients")
        steps_data = data.get("steps")
        return Recipe(
            title=data.get("title", recipe.title),
            ingredients=self._parse_ingredients(ing_data) if ing_data else recipe.ingredients,
            steps=self._parse_steps(steps_data) if steps_data is not None else recipe.steps,
        )
