# Kaleido - AI Agent App 🤖✨

フルマネージドなGCP環境で動作する、マルチAIエージェント・チャットアプリケーションです。
FastAPIとFlutter Webを組み合わせ、複数のAIエージェント（経路検索、肌分析など）が文脈に応じて動的に切り替わり、ユーザーをサポートします。

## 🏛 Architecture

*   **Frontend**: Flutter Web (Dart)
*   **Backend**: FastAPI (Python)
*   **Database**: Cloud Firestore
*   **Storage**: Google Cloud Storage (GCS)
*   **AI / ML**: Vertex AI (Gemini, Embeddings)
*   **Deployment**: Cloud Run (予定)
*   **Secrets**: Secret Manager

## ✨ Features

*   **マルチエージェント・ルーティング**: ユーザーの質問内容に応じて、最適なAIエージェントが自動的にアサインされます。
*   **マルチモーダル対話**: テキストだけでなく、音声入力（Speech-to-Text）や画像アップロードに対応。
*   **音声読み上げ（TTS）**: 生成された回答をエージェントに応じた音声で読み上げます。
*   **エージェント相関図**: ユーザーと関わったエージェントの関係性をビジュアルで確認できる機能。
*   **デモ環境リセット**: ワンクリックでチャット履歴や生成エージェントを初期状態に戻す管理機能を実装。

## 🛠 Tech Stack

**Backend:**
*   Python 3.10+
*   FastAPI / Uvicorn
*   Google Cloud Client Libraries (Firestore, Storage, Secret Manager)
*   Vertex AI SDK

**Frontend:**
*   Flutter
*   Dart
*   http, image_picker, speech_to_text, audioplayers

---

## 🚀 Getting Started (ローカル開発環境)

### 1. GCP環境のセットアップ

本アプリを動作させるには、GCPプロジェクトと適切な権限を持ったサービスアカウントが必要です。
Cloud Shellを開き、以下のコマンドを実行してリソースと権限をセットアップしてください。

\`\`\`bash
# 1. 環境変数の設定 (BUCKET_NAMEはお好みの名前に変更してください)
PROJECT_ID=\$(gcloud config get-value project)
SA_NAME="kaleido-backend-sa"
SA_EMAIL="\${SA_NAME}@\${PROJECT_ID}.iam.gserviceaccount.com"
BUCKET_NAME="kaleido-demo-temp-assets"

# 2. サービスアカウントの作成
gcloud iam service-accounts create \$SA_NAME \
    --display-name="Kaleido Backend Service Account"

# 3. 必要なIAMロールの付与
# GCSへの画像/音声保存
gcloud projects add-iam-policy-binding \$PROJECT_ID \
    --member="serviceAccount:\${SA_EMAIL}" \
    --role="roles/storage.objectAdmin"
# 署名付きURLの発行
gcloud projects add-iam-policy-binding \$PROJECT_ID \
    --member="serviceAccount:\${SA_EMAIL}" \
    --role="roles/iam.serviceAccountTokenCreator"
# Firestoreへの履歴保存
gcloud projects add-iam-policy-binding \$PROJECT_ID \
    --member="serviceAccount:\${SA_EMAIL}" \
    --role="roles/datastore.user"
# Vertex AI (Gemini)の利用
gcloud projects add-iam-policy-binding \$PROJECT_ID \
    --member="serviceAccount:\${SA_EMAIL}" \
    --role="roles/aiplatform.user"

# 4. JSONキーの生成 (※絶対にGitにコミットしないでください)
gcloud iam service-accounts keys create service-account.json \
    --iam-account=\${SA_EMAIL}

# 5. GCSバケットのCORS設定 (Flutter Webでの音声再生用)
cat <<EOF> cors.json
[
  {
    "origin": ["*"],
    "method": ["GET", "HEAD", "OPTIONS"],
    "responseHeader": ["*"],
    "maxAgeSeconds": 3600
  }
]
EOF
gcloud storage buckets update gs://\$BUCKET_NAME --cors-file=cors.json
\`\`\`

### 2. バックエンドの起動

1. Cloud Shellで生成した `service-account.json` をダウンロードし、`backend/` ディレクトリ直下に配置します。
2. `backend/.env.example` をコピーして `.env` を作成し、必要な環境変数を設定します。
3. 依存関係をインストールし、サーバーを起動します。

\`\`\`bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
\`\`\`

### 3. フロントエンドの起動

\`\`\`bash
cd frontend
flutter pub get
flutter run -d chrome
\`\`\`

---

## 🔒 Security Notes

*   **APIキーの管理**: 本番環境では、APIキー等の機密情報はソースコードや`.env`に直接記述せず、必ず **Google Cloud Secret Manager** を経由して取得する設計としています。
*   **クレデンシャルの保護**: `service-account.json` および `.env` は `.gitignore` に登録されており、リポジトリには含まれません。