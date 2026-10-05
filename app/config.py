"""設定値・調整パラメータの集約。

環境変数（`.env`）とチューニング用の定数をここにまとめる。
実装中に調整したい値（上限・しきい値・モデル名など）は全てここを参照する。
"""

import os

from dotenv import load_dotenv

load_dotenv()

# --- 認証 ---
# Gemini API キー（https://aistudio.google.com で発行）
GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "")

# --- 動画・フレーム ---
# 動画長の上限（秒）。超過は弾く。YouTubeショート想定で3分。
MAX_DURATION_SEC: int = 180
# ダウンロード動画の高さ上限(px)。フレーム/クリップは別途縮小するので過剰な高画質は不要。
# 帯域・時間・ディスクの節約が目的（Geminiトークンには影響しない）。
MAX_DOWNLOAD_HEIGHT: int = 720
# ffmpeg シーン変化検出のしきい値（0.0〜1.0）。低いほどフレームを多く拾う。
SCENE_THRESHOLD: float = 0.3
# Visionに渡すフレームの最大枚数（保険のキャップ）。
MAX_FRAMES: int = 40
# フレーム画像の長辺ピクセル（ダウンスケール先）。テロップ判読とトークンのバランス。
FRAME_LONG_EDGE: int = 640

# --- 文字起こし ---
# faster-whisper のモデルサイズ。
WHISPER_MODEL: str = "medium"
# 文字起こし対象の言語（日本語固定）。
WHISPER_LANGUAGE: str = "ja"

# --- LLM ---
# レシピ整形・Vision解析に使う Gemini モデル。
GEMINI_MODEL: str = "gemini-3.8-flash"

# 画像/動画のトークン解像度（Gemini 3系）。1枚あたり low=280 / medium=560 / high=1120 トークン。
# テロップ可読性 ↔ トークンのトレードオフ。環境変数 MEDIA_RESOLUTION で変更可。
MEDIA_RESOLUTION: str = os.environ.get("MEDIA_RESOLUTION", "medium").lower()

# --- キャッシュ ---
# ローカルSQLiteキャッシュの保存先。Cloud Run では Firestore/GCS に差し替える。
CACHE_PATH: str = os.environ.get("CACHE_PATH", "data/cache.sqlite3")

# --- 2パス精度向上（不明箇所だけ短クリップ動画で再判定）---
# 無効化したいときは ENABLE_CLARIFY_PASS=0。
ENABLE_CLARIFY_PASS: bool = os.environ.get("ENABLE_CLARIFY_PASS", "1") not in ("0", "false", "False")
# クリップは [秒数-窓, 秒数+窓] の範囲を切り出す。
CLIP_WINDOW_SEC: float = 2.0
# パス2に渡すクリップの最大本数。
MAX_CLARIFY_CLIPS: int = 3
# クリップのダウンスケール長辺（トークン節約）。
CLIP_LONG_EDGE: int = 480

# --- デバッグ ---
# True にすると、AIに送るフレーム画像と入力テキストを DEBUG_DIR に保存する（精度確認用）。
DEBUG_SAVE_FRAMES: bool = os.environ.get("DEBUG_SAVE_FRAMES", "") not in ("", "0", "false", "False")
DEBUG_DIR: str = os.environ.get("DEBUG_DIR", "data/debug")
