"""ffmpeg によるシーン変化フレーム抽出と、短い動画クリップの切り出し。"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from app import config
from app.models import Frame

_PTS_RE = re.compile(r"pts_time:([0-9.]+)")


class FrameError(Exception):
    """フレーム抽出・クリップ切り出しに失敗したときの例外。"""


def extract_frames(video_path: Path) -> list[Frame]:
    """シーン変化フレームを抽出し、各フレームの秒数つきで返す。

    - 先頭フレーム + シーン変化（scene > しきい値）を採用。
    - 長辺を FRAME_LONG_EDGE にダウンスケール。最大 MAX_FRAMES 枚。
    - `showinfo` の `pts_time` を解析して各フレームの秒数を得る。

    Raises:
        FrameError: ffmpeg の実行に失敗した場合。
    """
    out_dir = video_path.parent / "frames"
    out_dir.mkdir(parents=True, exist_ok=True)

    vf = (
        f"select='eq(n\\,0)+gt(scene\\,{config.SCENE_THRESHOLD})',"
        f"scale=-2:{config.FRAME_LONG_EDGE},showinfo"
    )
    cmd = [
        "ffmpeg",
        "-i",
        str(video_path),
        "-vf",
        vf,
        "-vsync",
        "vfr",
        "-frames:v",
        str(config.MAX_FRAMES),
        "-q:v",
        "2",
        str(out_dir / "frame_%03d.jpg"),
    ]

    try:
        proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    except FileNotFoundError as e:
        raise FrameError("ffmpeg が見つかりません。") from e

    stderr = proc.stderr.decode("utf-8", errors="ignore") if proc.stderr else ""
    if proc.returncode != 0:
        raise FrameError(f"フレーム抽出に失敗しました: {stderr[-500:]}")

    # showinfo の pts_time を出力順に取得（= 出力JPEGの順序に対応）
    pts = [float(x) for x in _PTS_RE.findall(stderr)]
    files = sorted(out_dir.glob("frame_*.jpg"))

    frames: list[Frame] = []
    for i, path in enumerate(files):
        seconds = pts[i] if i < len(pts) else 0.0
        frames.append(Frame(seconds=seconds, data=path.read_bytes()))
    return frames


def extract_clip(video_path: Path, start: float, end: float) -> bytes:
    """[start, end] 秒の短い動画クリップを mp4 バイト列で返す（映像のみ・縮小）。

    Raises:
        FrameError: ffmpeg の実行に失敗した場合。
    """
    out_path = video_path.parent / f"clip_{start:.1f}_{end:.1f}.mp4"
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-ss",
        str(start),
        "-to",
        str(end),
        "-an",  # 切り方判定に音声は不要
        "-vf",
        f"scale=-2:{config.CLIP_LONG_EDGE}",
        "-c:v",
        "libx264",
        "-movflags",
        "+faststart",
        "-loglevel",
        "error",
        str(out_path),
    ]
    try:
        proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    except FileNotFoundError as e:
        raise FrameError("ffmpeg が見つかりません。") from e
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="ignore") if proc.stderr else ""
        raise FrameError(f"クリップ切り出しに失敗しました: {stderr[-300:]}")
    return out_path.read_bytes()
