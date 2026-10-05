"""1ジョブ分のパイプライン実行。

download → transcribe → extract_frames → extract_recipe の順に実行し、
各段で job.state を更新する。失敗は段階別の日本語メッセージで ERROR にする。
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path

from app import config
from app.cache.base import RecipeCache
from app.llm.base import LLMClient, LLMError
from app.models import Frame, Job, JobState, VideoClip
from app.pipeline.download import DownloadError, download
from app.pipeline.frames import FrameError, extract_clip, extract_frames
from app.pipeline.recipe import build_html, build_markdown
from app.pipeline.transcribe import TranscribeError, transcribe

logger = logging.getLogger("recipe_kuma.pipeline")


def _dump_debug(job: Job, transcript: str, description: str, frames: list[Frame]) -> None:
    """AIに送るフレーム画像と入力テキストをファイルに保存する（精度確認用）。"""
    out = Path(config.DEBUG_DIR) / (job.video_id or job.id)
    out.mkdir(parents=True, exist_ok=True)
    (out / "input.txt").write_text(
        f"url: {job.url}\n"
        f"video_id: {job.video_id}\n"
        f"frames: {len(frames)}\n\n"
        f"=== description（概要欄）===\n{description}\n\n"
        f"=== transcript（文字起こし）===\n{transcript}\n",
        encoding="utf-8",
    )
    for i, frame in enumerate(frames):
        (out / f"frame_{i:03d}_t{frame.seconds:.1f}s.jpg").write_bytes(frame.data)
    logger.info("[%s] debug dump: %s", job.video_id or job.id, out)


def _clarify_pass(job: Job, llm: LLMClient, video_path, recipe, clarify):
    """不明箇所の短クリップを切り出し、パス2で手順を具体化する。失敗時は元recipeを返す。"""
    clips: list[VideoClip] = []
    for c in clarify[: config.MAX_CLARIFY_CLIPS]:
        start = max(0.0, c.seconds - config.CLIP_WINDOW_SEC)
        end = c.seconds + config.CLIP_WINDOW_SEC
        try:
            data = extract_clip(video_path, start, end)
        except FrameError as e:
            logger.warning("[%s] クリップ切り出し失敗(t=%.1f): %s", job.video_id or job.id, c.seconds, e)
            continue
        clips.append(VideoClip(seconds=c.seconds, reason=c.reason, data=data))

    if not clips:
        return recipe

    logger.info("[%s] パス2実行: clips=%d本", job.video_id or job.id, len(clips))
    try:
        return llm.refine_recipe(recipe, clips)
    except LLMError as e:
        logger.warning("[%s] パス2失敗、パス1の結果を使用: %s", job.video_id or job.id, e)
        return recipe


def run(job: Job, llm: LLMClient, cache: RecipeCache | None = None) -> None:
    """ジョブを実行し、結果を job に書き込む（例外は投げず job.state で表現）。

    成功時、video_id があれば結果をキャッシュに保存する。
    """
    work_dir = Path(tempfile.mkdtemp(prefix="recipe_kuma_"))
    try:
        job.state = JobState.DOWNLOADING
        meta = download(job.url, work_dir)

        job.state = JobState.TRANSCRIBING
        transcript = transcribe(meta.audio_path)
        logger.info(
            "[%s] transcript: %d文字 / preview: %s",
            job.video_id or job.id,
            len(transcript),
            transcript[:120].replace("\n", " "),
        )

        job.state = JobState.EXTRACTING_FRAMES
        frames = extract_frames(meta.video_path)
        logger.info(
            "[%s] frames: %d枚 (しきい値=%s, 長辺=%spx)",
            job.video_id or job.id,
            len(frames),
            config.SCENE_THRESHOLD,
            config.FRAME_LONG_EDGE,
        )

        if config.DEBUG_SAVE_FRAMES:
            _dump_debug(job, transcript, meta.description, frames)

        job.state = JobState.ANALYZING
        result = llm.extract_recipe(transcript, meta.description, frames)
        if not result.found or result.recipe is None:
            job.error_message = "この動画からレシピは見つかりませんでした"
            job.state = JobState.ERROR
            return

        recipe = result.recipe
        # パス2: 静止画で判断できなかった工程だけ、短クリップ動画で具体化
        if config.ENABLE_CLARIFY_PASS and result.clarify:
            recipe = _clarify_pass(job, llm, meta.video_path, recipe, result.clarify)

        job.result_markdown = build_markdown(recipe, job.url, meta.uploader, job.video_id)
        job.result_html = build_html(recipe, job.url, meta.uploader, job.video_id, frames)
        job.state = JobState.DONE

        if cache is not None and job.video_id:
            cache.set(job.video_id, job.result_markdown, job.result_html)

    except DownloadError as e:
        job.error_message = str(e)
        job.state = JobState.ERROR
    except TranscribeError as e:
        job.error_message = str(e)
        job.state = JobState.ERROR
    except FrameError as e:
        job.error_message = str(e)
        job.state = JobState.ERROR
    except LLMError as e:
        job.error_message = f"レシピ解析に失敗しました: {e}"
        job.state = JobState.ERROR
    except Exception as e:  # noqa: BLE001 - 想定外も必ずジョブ側に反映
        job.error_message = f"予期しないエラーが発生しました: {e}"
        job.state = JobState.ERROR
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
