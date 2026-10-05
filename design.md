# 実装計画 — レシピっクマ 🐻

`spec.md` の確定仕様（YouTubeショート想定・音声Whisper + フレームVision + 概要欄 → 構造化レシピ）をもとにした詳細設計。

---

## 方針・アーキテクチャ

- **バックエンド**: FastAPI。同時1ジョブを**単一ワーカースレッド + キュー**で直列処理する。
- **ジョブ管理**: メモリ内 `dict`（`job_id → Job`）。進捗を `state` で持ち、フロントがポーリングで取得。
- **重い処理（Whisper・ffmpeg・LLM）はワーカースレッドで実行**し、FastAPIのイベントループを塞がない。POST/GETエンドポイントは `dict` を読み書きするだけで即応答。
- **パイプラインは純粋関数の連なり**: `download → transcribe → extract_frames → extract_recipe`。各ステップは入出力が明確で単体テストしやすい形にする。
- **LLMは抽象インタフェース `LLMClient` 経由**で呼ぶ。初版は `GeminiClient`。将来 `ClaudeClient` を追加して環境変数で切替可能にする。
- **LLM出力は構造化（JSON）で受け取り、サーバ側でMarkdownを組み立てる**（Markdown直接生成より安定）。
- 全てDockerで実行（`python:3.11-slim` + ffmpeg）。Whisperモデルはvolumeにキャッシュ。

---

## ファイル構成

```
recipe_kuma/
├─ spec.md
├─ design.md
├─ Dockerfile                 # 新規: python:3.11-slim + ffmpeg + 依存
├─ compose.yaml               # 新規: ポート・env・モデルキャッシュvolume
├─ pyproject.toml             # 新規: uv管理の依存定義
├─ .env.example               # 新規: GEMINI_API_KEY のテンプレ
├─ .gitignore                 # 新規: .env / __pycache__ / モデルキャッシュ 等
├─ app/
│  ├─ __init__.py
│  ├─ main.py                 # 新規: FastAPI エントリ・ルーティング・静的配信
│  ├─ config.py               # 新規: 設定値（上限・しきい値・モデル名・APIキー）
│  ├─ models.py               # 新規: Job / JobState / Recipe 等の型定義
│  ├─ jobs.py                 # 新規: ジョブストア + ワーカースレッド + キュー
│  ├─ pipeline/
│  │  ├─ __init__.py
│  │  ├─ runner.py            # 新規: 1ジョブ分のパイプライン実行（各ステップ呼び出し）
│  │  ├─ download.py          # 新規: yt-dlp で動画DL + メタ情報取得
│  │  ├─ transcribe.py        # 新規: faster-whisper で文字起こし
│  │  ├─ frames.py            # 新規: ffmpeg でシーン変化フレーム抽出
│  │  └─ recipe.py            # 新規: LLMClient を呼びレシピ抽出 → Markdown組み立て
│  └─ llm/
│     ├─ __init__.py
│     ├─ base.py              # 新規: LLMClient プロトコル + RecipeResult
│     └─ gemini.py            # 新規: Gemini 実装（google-genai）
└─ web/
   └─ index.html             # 新規: URL入力・進捗ポーリング・コピーUI（素のHTML/JS）
```

---

## クラス・型定義

### JobState（Enum）
- **場所**: `app/models.py`
- **役割**: ジョブの進捗状態。
- **値**: `QUEUED` / `DOWNLOADING` / `TRANSCRIBING` / `EXTRACTING_FRAMES` / `ANALYZING` / `DONE` / `ERROR`
- フロント表示マッピング: `DOWNLOADING`→「ダウンロード中」、`TRANSCRIBING`→「文字起こし中」、`EXTRACTING_FRAMES`/`ANALYZING`→「解析中」。

### Job（dataclass）
- **場所**: `app/models.py`
- **役割**: 1件の処理ジョブの状態保持。
- **フィールド**:
  - `id: str` — UUID
  - `url: str` — 入力URL
  - `state: JobState`
  - `result_markdown: str | None` — 完成レシピ
  - `error_message: str | None` — エラー時の表示文言
  - `created_at: float`

### Ingredient / Recipe（dataclass or pydantic）
- **場所**: `app/models.py`
- **役割**: 構造化レシピ。LLMの構造化出力に対応。
  - `Ingredient`: `name: str`, `amount: str`（読めない場合は `"分量不明"`）
  - `Recipe`: `title: str`, `ingredients: list[Ingredient]`, `steps: list[str]`

### RecipeResult（dataclass）
- **場所**: `app/llm/base.py`
- **役割**: LLM抽出結果のラッパ。レシピ抽出可否を含む。
  - `found: bool` — レシピが抽出できたか（falseなら「レシピが見つかりませんでした」）
  - `recipe: Recipe | None`

### LLMClient（Protocol）
- **場所**: `app/llm/base.py`
- **役割**: LLM実装の差し替え点。
- **メソッド**:
  - `extract_recipe(transcript: str, description: str, frames: list[bytes]) -> RecipeResult`
    - 文字起こし・概要欄・フレーム画像(JPEGバイト列)を受け取り、構造化レシピを返す。

### GeminiClient（LLMClient実装）
- **場所**: `app/llm/gemini.py`
- **役割**: `google-genai` 経由で `gemini-2.5-flash` を呼ぶ。
- **実装ポイント**:
  - フレームを inline の画像パートとして複数枚渡す。
  - `response_schema`（JSONモード）で `{found, title, ingredients[{name, amount}], steps[]}` を受け取る。
  - プロンプトで「分量が読めない材料は `amount` を `"分量不明"` にする」「レシピと判断できなければ `found=false`」を指示。
  - APIキーは `config.GEMINI_API_KEY`。

### JobStore + Worker
- **場所**: `app/jobs.py`
- **役割**: ジョブの登録・取得と、直列ワーカーの駆動。
- **主な要素**:
  - `jobs: dict[str, Job]` — メモリ内ストア
  - `queue: queue.Queue[str]` — 処理待ちjob_id
  - `create_job(url) -> Job` — ジョブ生成・enqueue
  - `get_job(job_id) -> Job | None`
  - `_worker()` — キューから1件ずつ取り出し `pipeline.runner.run(job)` を呼ぶ常駐スレッド（`app起動時にstart`）

---

## 主要な処理フロー

### API

| メソッド | パス | 役割 |
|---|---|---|
| `POST` | `/api/jobs` | `{url}` を受けジョブ生成・enqueue → `{job_id}` を返す。URL長の事前バリデーションはダウンロード段で実施 |
| `GET` | `/api/jobs/{id}` | `{state, error_message}` を返す（ポーリング） |
| `GET` | `/api/jobs/{id}/result` | 完了時に `{markdown}` を返す |
| `GET` | `/` | `web/index.html` を配信 |

### パイプライン（`pipeline/runner.py`）

```
run(job):
  try:
    job.state = DOWNLOADING
    meta = download(job.url)          # video_path, audio_path, description, uploader, duration
      └─ duration > 180s ならここで弾いて ERROR

    job.state = TRANSCRIBING
    transcript = transcribe(meta.audio_path)   # faster-whisper medium / ja / int8

    job.state = EXTRACTING_FRAMES
    frames = extract_frames(meta.video_path)    # ffmpeg scene>0.3, 最大40枚, JPEGバイト列

    job.state = ANALYZING
    result = llm.extract_recipe(transcript, meta.description, frames)
    if not result.found:
        job.error_message = "この動画からレシピは見つかりませんでした"
        job.state = ERROR; return
    job.result_markdown = build_markdown(result.recipe, job.url, meta.uploader)
    job.state = DONE
  except DownloadError/TranscribeError/LLMError as e:
    job.error_message = <各段階の分かりやすい文言>
    job.state = ERROR
  finally:
    一時ファイル（動画・音声）を削除
```

### 各ステップの要点

**download.py** — `download(url) -> DownloadResult`
- yt-dlp を Python API で呼ぶ。`info dict` から `duration` / `description` / `uploader` を取得。
- `duration > 180` は `DownloadError`（上限超過）として弾く。
- 動画(mp4)と音声(m4a/wav)を一時ディレクトリに保存。非公開/年齢制限等は例外→キャッチして日本語メッセージ化。

**transcribe.py** — `transcribe(audio_path) -> str`
- `faster_whisper.WhisperModel("medium", device="cpu", compute_type="int8")`
- `language="ja"` 固定。セグメントを連結して1本のテキストに。
- モデルはプロセス内で**1回だけロードして使い回す**（毎回ロードしない）。

**frames.py** — `extract_frames(video_path) -> list[bytes]`
- ffmpeg: `-vf "select='gt(scene,0.3)',scale=-2:640" -vsync vfr -frames:v 40` で JPEG を一時出力。
- 先頭フレームも確実に含めるため `select='eq(n,0)+gt(scene,0.3)'` とする。
- 出力JPEGを読み込み `list[bytes]` で返す（縦型ショート想定、長辺640px目安でトークン節約・テロップは判読可能なサイズ）。

**recipe.py**
- `extract_recipe(...)` を `LLMClient` 経由で呼ぶ。
- `build_markdown(recipe, url, uploader) -> str` で spec の固定スキーマに整形（材料は `- {name} {amount}`、手順は番号付き、末尾に `出典: {url}（{uploader}）`）。

---

## 考慮事項・決定事項

- **同時1ジョブ**: 単一ワーカースレッド + `queue.Queue` で自然に直列化。2件目以降は `QUEUED` で待つ。Whisperのメモリ競合も防げる。
- **Whisperのブロッキング**: ワーカーは独立スレッドなのでFastAPIのイベントループを塞がない。モデルはシングルトンで常駐。
- **フレーム枚数**: ショート想定で通常10〜30枚。40枚キャップは保険。全枚数をそのままVisionへ（spec🐻回答どおり）。
- **画像サイズ**: 長辺640px目安にダウンスケール。テロップ判読と無料枠トークンのバランス。読み取り精度が低ければ上げる（調整パラメータ）。
- **LLM構造化出力**: `response_schema` でJSON受け → サーバでMarkdown組み立て。Markdown直生成より崩れにくく、`分量不明`・`found=false` の制御も確実。
- **分量不明**（🐻回答）: `amount="分量不明"` としてMarkdownにも明記。材料自体は省略しない。
- **レシピ抽出不可**（spec）: `found=false` を受けたら専用エラーメッセージで `ERROR`。
- **一時ファイル**: ジョブ完了・失敗どちらでも `finally` で削除。
- **エラー文言**: 段階別に日本語化（DL失敗/長すぎ/文字起こし失敗/LLM失敗/レシピ無し）。リトライは手動。
- **設定の外出し**: `config.py` に上限(180s)・しきい値(0.3)・最大枚数(40)・モデル名・画像長辺・APIキーを集約し調整しやすく。
- **メモリ内ジョブ**: プロセス再起動で消える。初版はこれで可（spec スコープ外に永続化）。

---

## 依存パッケージ（pyproject.toml 想定）

- `fastapi`, `uvicorn[standard]` — Web
- `yt-dlp` — ダウンロード・メタ取得
- `faster-whisper` — 文字起こし
- `google-genai` — Gemini
- `python-dotenv` — `.env` 読み込み（任意）
- ffmpeg はOSパッケージ（Dockerの `apt install ffmpeg`）

---

## 次のステップ

`/tasks` で、この設計を小さな実装単位に分解して `task.md` を作成する。
想定される大きな単位: ①プロジェクト雛形(Docker/pyproject/config) → ②型定義 → ③各パイプライン関数 → ④LLM抽象+Gemini → ⑤ジョブ管理+ワーカー → ⑥FastAPIルーティング → ⑦フロントHTML → ⑧結合・動作確認。
