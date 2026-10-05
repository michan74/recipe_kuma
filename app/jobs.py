"""ジョブストアと直列ワーカー。

ジョブはメモリ内 dict に保持し、単一ワーカースレッド + キューで直列処理する
（＝同時1ジョブ）。重い処理はこのワーカースレッド上で走るため、FastAPI の
イベントループを塞がない。
"""

from __future__ import annotations

import queue
import threading

from app import config
from app.cache.base import RecipeCache
from app.cache.sqlite import SqliteCache
from app.llm.base import LLMClient, LLMError
from app.llm.gemini import GeminiClient
from app.models import Job, JobState
from app.pipeline import runner
from app.videoid import extract_video_id


class JobStore:
    """ジョブの登録・取得と、直列ワーカーの駆動を担う。"""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._queue: queue.Queue[str] = queue.Queue()
        self._lock = threading.Lock()
        self._llm: LLMClient | None = None
        self._cache: RecipeCache = SqliteCache(config.CACHE_PATH)
        self._worker = threading.Thread(target=self._run_worker, daemon=True)
        self._started = False

    def start(self) -> None:
        """ワーカースレッドを開始する（多重起動しない）。"""
        if not self._started:
            self._started = True
            self._worker.start()

    def create_job(self, url: str) -> Job:
        """ジョブを生成する。キャッシュヒット時は即完了、ミス時はキューに積む。"""
        job = Job(url=url)
        job.video_id = extract_video_id(url)

        # キャッシュ照会（動画IDが取れた場合のみ）
        if job.video_id:
            cached = self._cache.get(job.video_id)
            if cached is not None:
                job.result_markdown = cached["markdown"]
                job.result_html = cached["html"]
                job.state = JobState.DONE
                with self._lock:
                    self._jobs[job.id] = job
                return job

        with self._lock:
            self._jobs[job.id] = job
        self._queue.put(job.id)
        return job

    def get_job(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def _get_llm(self) -> LLMClient:
        """LLMクライアントを遅延生成して使い回す。"""
        if self._llm is None:
            self._llm = GeminiClient()
        return self._llm

    def _run_worker(self) -> None:
        while True:
            job_id = self._queue.get()
            job = self.get_job(job_id)
            if job is None:
                continue
            try:
                llm = self._get_llm()
            except LLMError as e:
                job.error_message = str(e)
                job.state = JobState.ERROR
                continue
            runner.run(job, llm, self._cache)


# アプリ全体で共有するシングルトン（main.py の起動時に start() する）。
store = JobStore()
