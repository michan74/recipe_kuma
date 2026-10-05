FROM python:3.11-slim

# ffmpeg（フレーム抽出・音声デコードに必要）
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 依存解決（ソースより先にコピーしてレイヤキャッシュを効かせる）
COPY pyproject.toml ./
COPY app ./app
COPY web ./web

# pip で直接インストール（ghcr.io 等の外部レジストリに依存しない）
RUN pip install --no-cache-dir .

# Whisper medium モデルをイメージに同梱（Cloud Run のコールドスタートでDLしない）
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('medium', device='cpu', compute_type='int8')"

EXPOSE 8000

# Cloud Run は $PORT を渡す（既定8080）。ローカルは8000にフォールバック。
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
