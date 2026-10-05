# CLAUDE.md

レシピっクマ（YouTubeショート動画 → レシピ化）プロジェクトの作業ルール。

## 作業記録（必須）

**作業したら必ず `docs/daily/YYYY-MM-DD.md` に記録する。**

- その日のファイルがあれば**追記**、無ければ**新規作成**。
- 区切り（セッション終了・機能完成・方針決定など）のタイミングで記録する。
- 記録する内容: やったこと（機能追加・不具合修正）、判断とその理由、停止点と次にやること。
- 日付は実際の当日（例: 2026-10-04）。相対表現は使わず絶対日付で書く。

## ドキュメント構成

| ファイル | 役割 |
|---|---|
| `spec.md` | 仕様（要件・技術選定・インフラ・調査結果） |
| `design.md` | 実装計画（クラス/ファイル構成） |
| `task.md` | タスク一覧と進捗 |
| `docs/backlog.md` | 後回し作業・改善候補（ハッカソン優先事項含む） |
| `docs/positioning.md` | プロダクト方針・差別化 |
| `docs/daily/` | 日々の作業記録 |

## プロジェクト概要

- YouTubeショート動画を解析し、レシピ（材料＋手順）を出力。手順には根拠（秒数・サムネ・動画シーク）を付ける。
- バックエンド: FastAPI / 文字起こし: ローカル faster-whisper / 解析: Gemini API（`gemini-3.8-flash`, Vision）。
- デプロイ先: GCP Cloud Run（Agentic AI Hackathon Vol.5 提出作品、締切 2026-10-15）。
- ローカル開発は Docker Compose（`docker compose up`、バインドマウント + `--reload`）。キャッシュ変更時は `docker restart recipe_kuma-app-1`。
