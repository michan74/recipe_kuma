"""FastAPI エントリ・ルーティング。"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.jobs import store
from app.models import JobState

_WEB_DIR = Path(__file__).resolve().parent.parent / "web"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 起動時にワーカースレッドを開始
    store.start()
    yield


app = FastAPI(title="レシピっクマ", lifespan=lifespan)


class CreateJobRequest(BaseModel):
    url: str


@app.post("/api/jobs")
def create_job(req: CreateJobRequest) -> dict:
    url = req.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="URLを入力してください。")
    job = store.create_job(url)
    return {"job_id": job.id}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="ジョブが見つかりません。")
    return {"state": job.state.value, "error_message": job.error_message}


@app.get("/api/jobs/{job_id}/result")
def get_result(job_id: str) -> dict:
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="ジョブが見つかりません。")
    if job.state != JobState.DONE:
        raise HTTPException(status_code=409, detail="まだ完了していません。")
    return {
        "markdown": job.result_markdown,
        "html": job.result_html,
        "video_id": job.video_id,
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(_WEB_DIR / "index.html")
