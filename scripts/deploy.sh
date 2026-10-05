#!/usr/bin/env bash
# Cloud Run へデプロイする。初回セットアップ（プロジェクト・Secret 等）は README 参照。
set -euo pipefail

PROJECT="${PROJECT:-recipe-kuma}"
REGION="${REGION:-asia-northeast1}"
SERVICE="${SERVICE:-recipe-kuma}"

cd "$(dirname "$0")/.."

echo "project=${PROJECT} region=${REGION} service=${SERVICE} account=$(gcloud config get-value account 2>/dev/null)"

# NOTE: --max-instances 1 + --no-cpu-throttling は、ジョブをメモリ内で管理し
# バックグラウンドスレッドで処理している現状の前提。複数インスタンスにすると
# ジョブ状態が共有されず、CPU スロットリングありだとレスポンス後に処理が止まる。
gcloud run deploy "$SERVICE" \
  --source . \
  --project "$PROJECT" \
  --region "$REGION" \
  --allow-unauthenticated \
  --memory 4Gi --cpu 2 \
  --timeout 900 \
  --max-instances 1 \
  --no-cpu-throttling \
  --set-secrets GEMINI_API_KEY=gemini-api-key:latest \
  --quiet
