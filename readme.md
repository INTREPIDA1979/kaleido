# Kaleido - AI Agent App 🤖✨

フルマネージドなGCP環境で動作する、マルチAIエージェント・チャットアプリケーションです。
FastAPIとFlutter Webを組み合わせ、複数のAIエージェント（経路検索、肌分析など）が文脈に応じて動的に切り替わり、ユーザーをサポートします。

## 🏛 Architecture & Deployment Strategy

本プロジェクトは、開発端末（Windows等）の環境構築負荷を最小限にするため、バックエンドとフロントエンドでデプロイ元を分けるハイブリッドな構成をとっています。

*   **Backend**: FastAPI (Python) / Cloud Run
    *   👉 **Cloud Shellからデプロイ**: ローカルPCへのDocker環境（Docker Desktop等）の導入を避けるため、GCP上のCloud Buildを利用してコンテナを構築・デプロイします。
*   **Frontend**: Flutter Web (Dart) / Firebase Hosting
    *   👉 **ローカルPCからデプロイ**: Flutter SDKは容量が大きくCloud Shell上での環境構築が困難なため、ローカルPC上でWebビルドを行い、Firebase CLI経由でデプロイします。
*   **Database**: Cloud Firestore
*   **Storage**: Google Cloud Storage (GCS)
*   **AI / ML**: Vertex AI (Gemini, Embeddings)
*   **Secrets**: Secret Manager

## ✨ Features

*   **マルチエージェント・ルーティング**: ユーザーの質問内容に応じて、最適なAIエージェントが自動的にアサインされます。
*   **マルチモーダル対話**: テキストだけでなく、音声入力（Speech-to-Text）や画像アップロードに対応。
*   **音声読み上げ（TTS）**: 生成された回答をエージェントに応じた音声で読み上げます。
*   **エージェント相関図**: ユーザーと関わったエージェントの関係性をビジュアルで確認できる機能。
*   **デモ環境リセット**: ワンクリックでチャット履歴や生成エージェントを初期状態に戻す管理機能を実装。

---

## 📋 Prerequisites (事前準備)

このプロジェクトを構築・実行するには、事前に以下の準備が必要です。

1. **GCPプロジェクトの作成**: Google Cloud Consoleから新規プロジェクトを作成しておくこと。
2. **VS Codeのインストール**: ローカルPCでコード編集・フロントエンドの実行を行うため。
3. **リポジトリのクローン**: 
   バックエンド用（Cloud Shell）とフロントエンド用（ローカルPC（VSCode））の**双方で**、本リポジトリをクローンしておいてください。

   ```bash
   git clone https://github.com/INTREPIDA1979/kaleido.git
   ```

### ローカルPCの必須ツール:

- Google Cloud SDK (gcloud CLI)
- Flutter SDK (Webサポート有効化済み)
- Firebase CLI (npm install -g firebase-tools)
- Python 3.1x

---

## Environment Setup (共通のクラウド環境構築)

以下の作業は、GCPのCloud Shellにて実行してください。

### 1. GCP APIの有効化

```
gcloud services enable \
  run.googleapis.com \
  firestore.googleapis.com \
  storage.googleapis.com \
  aiplatform.googleapis.com \
  secretmanager.googleapis.com \
  cloudbuild.googleapis.com
```

### 2. サービスアカウントとGCSリソースの作成

BUCKET_NAMEを修正して、以下のコマンドを実行してください。

```
# 環境変数の設定 (BUCKET_NAMEは世界で一意の名前に変更してください)
PROJECT_ID=$(gcloud config get-value project)
SA_NAME="kaleido-backend-sa"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
BUCKET_NAME="your_bucket_name"

# サービスアカウントの作成
gcloud iam service-accounts create $SA_NAME --display-name="Kaleido Backend Service Account"

# GCSバケットの作成とCORS設定 (Flutter Webでの音声再生に必須)
gcloud storage buckets create gs://$BUCKET_NAME --location=asia-northeast1
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
gcloud storage buckets update gs://$BUCKET_NAME --cors-file=cors.json

# 必要なIAMロールの付与
gcloud projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:${SA_EMAIL}" --role="roles/storage.objectAdmin"
gcloud projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:${SA_EMAIL}" --role="roles/iam.serviceAccountTokenCreator"
gcloud projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:${SA_EMAIL}" --role="roles/datastore.user"
gcloud projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:${SA_EMAIL}" --role="roles/aiplatform.user"

# JSONキーの生成 (※絶対にGitにコミットしないでください。ローカル開発用に使います)
gcloud iam service-accounts keys create service-account.json --iam-account=${SA_EMAIL}

# Cloud ShellからローカルPCへキーをダウンロード
cloudshell download service-account.json
```

✅ 重要: バケット名は、重複を避けるために、適宜、変更してください。
✅ 重要: ダウンロードした service-account.json は、ローカルPC側（VS Code等）の backend/ ディレクトリ直下に移動・配置してください。

### 3. Firestore と Firebase の初期設定

1. **Firestoreの作成**: GCPコンソールから「Firestore」を開き、**Nativeモード**でデータベース(`(default)`)を作成します。
   * ※**ロケーション**は、Cloud Runと同じ `asia-northeast1` (東京) を選択してください。
2. **初期データの投入**: アプリ稼働に必要な初期エージェントデータ等があれば、作成したFirestoreに登録してください。
3. **Firebaseの追加**: ブラウザでFirebaseコンソールを開き、「プロジェクトを追加」から**既存のGCPプロジェクト**を選択してFirebaseを有効化します。

※ 基本的にデフォルト設定なので、設定が分からない時は、Gemini等に聞いて、設定してください。

---

## 💻 Local Development (ローカル開発環境での起動)

### バックエンドの起動 (ローカルPC)

1. **GCPへのログイン**: ローカルPCからGCPのリソースにアクセスするための認証を行います。（初回のみ）

   ```bash
   gcloud auth login
   gcloud config set project YOUR_PROJECT_ID
   ```
2. 前段でダウンロードした `service-account.json` が `backend/` 直下にあることを確認します。
3. `backend/.env.example` をコピーして `backend/.env` を作成し、各種APIキー（駅すぱあと、YouCAMなど）を設定します。

   ```
   # backend/.env の設定内容（例）
   EKISPERT_API_ACCESS_KEY=your_key_here
   YOUCAM_API_KEY=your_key_here
   GOOGLE_APPLICATION_CREDENTIALS=service-account.json
   GCS_TEMP_BUCKET_NAME=your_bucket_name
   ```

4. 仮想環境を構築し、サーバーを起動します。

   ```bash
   cd backend
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
   ```

### フロントエンドの起動 (ローカルPC)

ビルド時引数でローカルのAPIエンドポイントを渡して起動します。

```
cd frontend
flutter pub get
flutter run -d chrome --dart-define=API_URL=http://localhost:8080/api/v1
```

### 動作確認 (ローカルでのテスト手順)

フロントエンドとバックエンドが起動したら、以下の手順でシステム全体が正常に稼働しているかテストします。
起動したFlutterのチャット画面から以下のプロンプトを送信し、文脈に合わせて担当エージェントが自動で切り替わるか確認してください。

‐ シナリオA: 通常会話（デフォルトエージェント）
  - 「こんにちは！開発お疲れ様です。モチベーションが上がる一言をください！」
- シナリオB: 経路検索（駅すぱあとエージェント）
  - 「明日の朝9時に新宿駅から東京駅に行くルートを教えて」
- シナリオC: 肌診断（YouCAMエージェント）
  - （人物の顔写真をアップロードした上で）「この写真から肌年齢と状態を診断して」
  - ※ 顔写真は証明写真のようにアップの画像だときちんと認識してくれます。

## GCP上でのデプロイ

### 1. バックエンドのデプロイ（Cloud Shellで実行）

1．シークレットの登録（初回のみ）

APIキーとサービスアカウントのJSONキーをSecret Managerに預けます。
まずは、事前準備で作成した `service-account.json` が配置されているディレクトリ（通常はホームディレクトリ）で、シークレットの登録を行います。

```bash
# APIキーと秘密鍵をSecret Managerに登録 (初回のみ)
# ※YOUR_EKISPERT_KEY, YOUR_YOUCAM_KEY の部分は実際のキーに置き換えてください
printf "YOUR_EKISPERT_KEY" | gcloud secrets create ekispert-api-key --data-file=-
printf "YOUR_YOUCAM_KEY" | gcloud secrets create youcam-api-key --data-file=-
gcloud secrets create backend-sa-key --data-file=service-account.json
```

シークレットの登録が完了したら、クローンしたリポジトリのバックエンドディレクトリへ移動し、デプロイを実行します。

```
# バックエンドのソースコードがあるディレクトリへ移動
cd kaleido/backend

# デプロイ用変数のセット
PROJECT_ID=$(gcloud config get-value project)
SA_EMAIL="kaleido-backend-sa@${PROJECT_ID}.iam.gserviceaccount.com"
BUCKET_NAME="your_bucket_name"  # ※実際に作成したバケット名に変更してください

# デプロイの実行
gcloud run deploy kaleido-backend \
  --source . \
  --region asia-northeast1 \
  --service-account ${SA_EMAIL} \
  --set-env-vars "GCS_TEMP_BUCKET_NAME=${BUCKET_NAME},GOOGLE_APPLICATION_CREDENTIALS=/secrets/sa-key.json" \
  --set-secrets "EKISPERT_API_ACCESS_KEY=ekispert-api-key:latest,YOUCAM_API_KEY=youcam-api-key:latest,/secrets/sa-key.json=backend-sa-key:latest" \
  --allow-unauthenticated
```

✅ 重要: デプロイされたURLが表示されるので、コピーして残しておいてください。次のフロントエンドのデプロイ時に使用します。

### 2. フロントエンドのビルドとデプロイ (ローカルPCから実行)

フロントエンドがCloud Run上のバックエンドと通信できるよう、ビルド時に --dart-define を使ってAPIのURLを動的に渡します。この作業はローカルPC（VS Code）のターミナルで行います。

```
cd frontend

# Firebase CLIへログイン
firebase login

# プロジェクトの初期化
firebase init hosting
# 1. "Add Firebase to an existing Google Cloud Platform project" を選択
# 2. 対象のGCPプロジェクトを選択
# 3. Public directory: build/web
# 4. Single-page app: y
# 5. GitHub actions: N
# 6. Overwrite index.html: N (※絶対にN)

# Cloud RunのURLを指定してWeb用ビルドを作成
# (※ 先ほどデプロイしたバックエンドのURLに置き換えてください)
flutter build web --release --dart-define=API_URL={https://kaleido-backend-xxx.run.app/api/v1}

# Firebaseへデプロイ
firebase deploy --only hosting
```

デプロイ成功後、表示される Hosting URL にアクセスすれば本番環境のアプリが利用可能です！

動作確認は、ローカル環境構築時に記載したのと同様に確認してみてください。

