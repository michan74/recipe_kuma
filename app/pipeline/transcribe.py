"""faster-whisper による音声の文字起こし。"""

from __future__ import annotations

from pathlib import Path

from faster_whisper import WhisperModel

from app import config


class TranscribeError(Exception):
    """文字起こしに失敗したときの例外。"""


# モデルは重いので、プロセス内で一度だけロードして使い回す（遅延初期化）。
_model: WhisperModel | None = None


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        _model = WhisperModel(
            config.WHISPER_MODEL,
            device="cpu",
            compute_type="int8",
        )
    return _model


def transcribe(audio_path: Path) -> str:
    """音声（または動画コンテナ）から日本語テキストを書き起こす。

    Args:
        audio_path: 音声を含むメディアファイルのパス。

    Returns:
        連結した文字起こしテキスト。

    Raises:
        TranscribeError: 文字起こしに失敗した場合。
    """
    try:
        model = _get_model()
        segments, _info = model.transcribe(
            str(audio_path),
            language=config.WHISPER_LANGUAGE,
        )
        text = "".join(segment.text for segment in segments)
    except Exception as e:  # noqa: BLE001 - デコード/推論の失敗をまとめて包む
        raise TranscribeError(f"文字起こしに失敗しました: {e}") from e

    return text.strip()
