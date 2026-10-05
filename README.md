# レシピっクマ

YouTubeショート動画を解析し、レシピ（材料＋手順）を出力する。

## ローカル開発

```
cp .env.example .env   # GEMINI_API_KEY を記入
docker compose up --build
# → http://localhost:8000
```

## デプロイ（Cloud Run）

```
./scripts/deploy.sh
```

プロジェクト・リージョンは環境変数で上書きできる（既定: `PROJECT=recipe-kuma` / `REGION=asia-northeast1`）。

### 初回セットアップ（1回だけ）

個人アカウント用の gcloud 構成を作り、そこで作業する（会社用の構成と混ざらないように）。

```
gcloud config configurations create recipe-kuma
gcloud config set account <個人アカウント>
gcloud auth login <個人アカウント>
```

プロジェクト作成〜Secret 登録:

```
# 1. プロジェクト作成・課金紐付け
gcloud projects create recipe-kuma --name="Recipe Kuma"
gcloud config set project recipe-kuma
gcloud billing projects link recipe-kuma --billing-account=<課金アカウントID>

# 2. API 有効化
gcloud services enable --project recipe-kuma \
  run.googleapis.com cloudbuild.googleapis.com \
  secretmanager.googleapis.com artifactregistry.googleapis.com

# 3. GEMINI_API_KEY を Secret Manager に登録（名前は gemini-api-key 固定）
#    コンソールで作る場合は、上部のプロジェクトが recipe-kuma になっているか必ず確認する
grep '^GEMINI_API_KEY=' .env | cut -d= -f2- | tr -d '\n\r"' | \
  gcloud secrets create gemini-api-key --project recipe-kuma \
    --data-file=- --replication-policy=automatic

# 4. Cloud Run の実行SA（Compute既定SA）に Secret 読み取り権限を付与
PROJECT_NUMBER=$(gcloud projects describe recipe-kuma --format='value(projectNumber)')
gcloud secrets add-iam-policy-binding gemini-api-key --project recipe-kuma \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role=roles/secretmanager.secretAccessor
```

APIキーをローテーションしたら、新しいバージョンを追加するだけでよい（`:latest` を参照しているので次回デプロイで反映）:

```
grep '^GEMINI_API_KEY=' .env | cut -d= -f2- | tr -d '\n\r"' | \
  gcloud secrets versions add gemini-api-key --project recipe-kuma --data-file=-
```
