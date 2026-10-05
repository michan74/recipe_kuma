"""yt-dlp による動画ダウンロードとメタ情報取得。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yt_dlp

from app import config


class DownloadError(Exception):
    """ダウンロード・メタ取得に失敗したときの例外（表示用メッセージを持つ）。"""


@dataclass
class DownloadResult:
    """ダウンロード結果とメタ情報。

    audio_path は video_path と同一で構わない（faster-whisper は動画コンテナから
    音声トラックをデコードできるため、別途音声抽出はしない）。
    """

    video_path: Path
    audio_path: Path
    description: str
    uploader: str
    duration: int


def download(url: str, work_dir: Path) -> DownloadResult:
    """動画をダウンロードし、メタ情報とともに返す。

    Args:
        url: YouTube動画のURL。
        work_dir: 一時ファイルの保存先ディレクトリ。

    Returns:
        DownloadResult。

    Raises:
        DownloadError: 長さ超過・非公開・年齢制限・取得失敗など。
    """
    ydl_opts = {
        # 多くの動画は音声のみ/映像のみの分離ストリーム（DASH）しか無いため、
        # 映像+音声を両方落として ffmpeg で1つのmp4にマージする。
        # 高さを MAX_DOWNLOAD_HEIGHT で上限キャップ（帯域・時間の節約。精度は別途の縮小で担保）。
        "format": (
            f"bestvideo[height<={config.MAX_DOWNLOAD_HEIGHT}]+bestaudio/"
            f"best[height<={config.MAX_DOWNLOAD_HEIGHT}]/best"
        ),
        "merge_output_format": "mp4",
        "outtmpl": str(work_dir / "video.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # まず情報だけ取得して長さをチェック（巨大動画のDLを避ける）
            info = ydl.extract_info(url, download=False)
            duration = int(info.get("duration") or 0)
            if duration > config.MAX_DURATION_SEC:
                raise DownloadError(
                    f"動画が長すぎます（{duration}秒）。"
                    f"{config.MAX_DURATION_SEC}秒以内の動画を指定してください。"
                )

            # 本ダウンロード
            info = ydl.extract_info(url, download=True)
            video_path = Path(ydl.prepare_filename(info))
    except DownloadError:
        raise
    except yt_dlp.utils.DownloadError as e:
        raise DownloadError(
            "動画を取得できませんでした。非公開・年齢制限・URLの誤りの可能性があります。"
        ) from e
    except Exception as e:  # noqa: BLE001 - 想定外の失敗もまとめて包む
        raise DownloadError(f"ダウンロード中にエラーが発生しました: {e}") from e

    # マージで拡張子が変わることがあるため、実ファイルを探し直す
    if not video_path.exists():
        media = [
            p
            for p in work_dir.glob("video.*")
            if p.suffix.lower() in {".mp4", ".mkv", ".webm"}
        ]
        if not media:
            raise DownloadError("ダウンロードしたファイルが見つかりませんでした。")
        video_path = max(media, key=lambda p: p.stat().st_size)

    return DownloadResult(
        video_path=video_path,
        audio_path=video_path,
        description=info.get("description") or "",
        uploader=info.get("uploader") or "",
        duration=duration,
    )
