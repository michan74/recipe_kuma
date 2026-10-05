## deploy

### 0. プロジェクト確認・リージョン設定（東京）
gcloud config get-value project          # 対象プロジェクトを確認
export REGION=asia-northeast1

### 1. 必要なAPIを有効化
gcloud services enable \
  run.googleapis.com cloudbuild.googleapis.com \
  secretmanager.googleapis.com artifactregistry.googleapis.com

### 2. GEMINI_API_KEY を Secret Manager に登録（★ローテ後の新しいキーを貼る）
printf '%s' '新しいAPIキーをここに' | \
  gcloud secrets create gemini-api-key --data-file=- --replication-policy=automatic

### 3. Cloud Run の実行SAにシークレット読み取り権限を付与
PROJECT_NUMBER=$(gcloud projects describe "$(gcloud config get-value project)" --format='value(projectNumber)')
gcloud secrets add-iam-policy-binding gemini-api-key \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role=roles/secretmanager.secretAccessor

### 4. デプロイ（Dockerfileからビルド）
gcloud run deploy recipe-kuma \
  --source . \
  --region "$REGION" \
  --allow-unauthenticated \
  --memory 4Gi --cpu 2 \
  --timeout 900 \
  --max-instances 1 \
  --no-cpu-throttling \
  --set-secrets GEMINI_API_KEY=gemini-api-key:latest