# タスクリスト

## 進捗
- 完了: 16 / 16 タスク（タスク16は静的検証まで完了・実データE2Eは下記手順で各自実施）

---

## タスク

- [x] 1. プロジェクト雛形の作成
  - 対象: `pyproject.toml`, `.gitignore`, `.env.example`
  - 内容: uv管理の `pyproject.toml` に依存（`fastapi`, `uvicorn[standard]`, `yt-dlp`, `faster-whisper`, `google-genai`, `python-dotenv`）を定義。`.gitignore` に `.env` / `__pycache__/` / `*.pyc` / モデルキャッシュ・一時ディレクトリを追加。`.env.example` に `GEMINI_API_KEY=` を記載。

- [x] 2. 設定モジュール
  - 対象: `app/config.py`, `app/__init__.py`
  - 内容: 環境変数と調整値を集約。`GEMINI_API_KEY`（`.env`から）・`MAX_DURATION_SEC=180`・`SCENE_THRESHOLD=0.3`・`MAX_FRAMES=40`・`FRAME_LONG_EDGE=640`・`WHISPER_MODEL="medium"`・`GEMINI_MODEL="gemini-2.5-flash"` を定義。

- [x] 3. 型定義
  - 対象: `app/models.py`
  - 内容: `JobState`(Enum: QUEUED/DOWNLOADING/TRANSCRIBING/EXTRACTING_FRAMES/ANALYZING/DONE/ERROR)、`Job`(dataclass: id/url/state/result_markdown/error_message/created_at)、`Ingredient`(name/amount)、`Recipe`(title/ingredients/steps) を定義。

- [x] 4. LLM抽象インタフェース
  - 対象: `app/llm/base.py`, `app/llm/__init__.py`
  - 内容: `RecipeResult`(dataclass: found/recipe) と `LLMClient`(Protocol: `extract_recipe(transcript, description, frames) -> RecipeResult`) を定義。独自例外 `LLMError` も定義。

- [x] 5. Gemini実装
  - 対象: `app/llm/gemini.py`
  - 内容: `GeminiClient(LLMClient)` を実装。`google-genai` で `gemini-2.5-flash` を呼ぶ。フレームをinline画像パートで複数枚渡し、`response_schema`(JSON: found/title/ingredients[{name,amount}]/steps[])で受け取る。プロンプトで「分量不明は `amount="分量不明"`」「レシピでなければ `found=false`」を指示。失敗時は `LLMError`。

- [x] 6. ダウンロード処理
  - 対象: `app/pipeline/download.py`, `app/pipeline/__init__.py`
  - 内容: `download(url) -> DownloadResult`(video_path/audio_path/description/uploader/duration) を実装。yt-dlp のPython APIで動画+音声を一時ディレクトリに取得し、`info dict` からメタ情報取得。`duration > MAX_DURATION_SEC` は `DownloadError`。非公開/年齢制限等の例外をキャッチし日本語メッセージ化。

- [x] 7. 文字起こし処理
  - 対象: `app/pipeline/transcribe.py`
  - 内容: `transcribe(audio_path) -> str` を実装。`faster_whisper.WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")` を**モジュールレベルで1回だけロード**して使い回す。`language="ja"` 固定。セグメントを連結して返す。失敗時は `TranscribeError`。

- [x] 8. フレーム抽出処理
  - 対象: `app/pipeline/frames.py`
  - 内容: `extract_frames(video_path) -> list[bytes]` を実装。ffmpeg を subprocess で実行（`-vf "select='eq(n,0)+gt(scene,SCENE_THRESHOLD)',scale=-2:FRAME_LONG_EDGE" -vsync vfr -frames:v MAX_FRAMES` でJPEG一時出力）。出力JPEGを読み込み `list[bytes]` で返す。

- [x] 9. レシピ整形・Markdown組み立て
  - 対象: `app/pipeline/recipe.py`
  - 内容: `LLMClient` を使う薄いラッパ。`build_markdown(recipe, url, uploader) -> str` を実装（specの固定スキーマ: `# 料理名` / `## 材料` を `- {name} {amount}` / `## 手順` を番号付き / 末尾 `出典: {url}（{uploader}）`）。

- [x] 10. パイプライン実行
  - 対象: `app/pipeline/runner.py`
  - 内容: `run(job, llm)` を実装。download→transcribe→extract_frames→extract_recipe を順に呼び、各段で `job.state` を更新。`found=false` は「レシピが見つかりませんでした」で ERROR。各例外を段階別の日本語メッセージにして ERROR。`finally` で一時ファイル削除。

- [x] 11. ジョブ管理・ワーカー
  - 対象: `app/jobs.py`
  - 内容: `jobs: dict[str, Job]` と `queue.Queue` を持つ `JobStore`。`create_job(url)`(UUID発行・enqueue)、`get_job(id)`。常駐ワーカースレッド `_worker()` がキューから1件ずつ取り `runner.run` を呼ぶ（直列＝同時1ジョブ）。アプリ起動時にワーカーを start。

- [x] 12. FastAPI ルーティング
  - 対象: `app/main.py`
  - 内容: `POST /api/jobs`(→job_id)、`GET /api/jobs/{id}`(→state/error_message)、`GET /api/jobs/{id}/result`(→markdown)、`GET /`(web/index.html配信) を実装。起動時に `JobStore` のワーカーを開始。

- [x] 13. フロントエンド
  - 対象: `web/index.html`
  - 内容: 素のHTML/JS。URL入力→`POST /api/jobs`→job_idを保持→一定間隔で `GET /api/jobs/{id}` をポーリングし進捗(ダウンロード中/文字起こし中/解析中)を表示→DONEで result 取得しMarkdown表示＋**コピーボタン**。ERRORは error_message を表示。

- [x] 14. Dockerfile
  - 対象: `Dockerfile`
  - 内容: `python:3.11-slim` ベース。`apt-get install ffmpeg`、uvで依存インストール、アプリをコピー、`uvicorn app.main:app --host 0.0.0.0 --port 8000` で起動。

- [x] 15. Docker Compose
  - 対象: `compose.yaml`
  - 内容: サービス定義。ポート `8000:8000`、`.env` から `GEMINI_API_KEY` を渡す、**Whisperモデルキャッシュ用volume**（`~/.cache/huggingface` 相当）をマウントして初回DLを永続化。

- [x] 16. 結合・動作確認
  - 対象: （全体）
  - 内容: `docker compose up` で起動し、実際のYouTubeショートURLで1本解析。進捗遷移・レシピMarkdown・コピー・エラー系（長すぎ/不正URL/レシピ無し）を確認。テロップ読み取り精度を見て、必要なら `SCENE_THRESHOLD` / `FRAME_LONG_EDGE` を調整。
  - 実施状況: 全モジュールの構文コンパイル（`py_compile`）とインポート整合を確認済み。**実データE2Eは要APIキー・ネットワークのため未実施** → 下記「手動動作確認手順」で各自実行。

---

## 手動動作確認手順

1. `cp .env.example .env` して `GEMINI_API_KEY` を記入（https://aistudio.google.com で発行）
2. `docker compose up --build`（初回はWhisperモデル ~1.5GB のDLで時間がかかる）
3. ブラウザで `http://localhost:8000` を開く
4. YouTubeショートURLを入力して「解析」→ 進捗（ダウンロード中→文字起こし中→解析中）→ レシピMarkdown表示 → コピー
5. エラー系の確認: 3分超の動画 / 不正URL / 料理以外の動画（「レシピが見つかりませんでした」）
6. テロップ読み取り精度を見て、必要なら `app/config.py` の `SCENE_THRESHOLD`・`FRAME_LONG_EDGE` を調整
