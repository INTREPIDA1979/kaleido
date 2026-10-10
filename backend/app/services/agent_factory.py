import json
import uuid
import os
import random
from google import genai
from vertexai.generative_models import GenerativeModel, GenerationConfig
from google.cloud import storage
from app.services.embedding_service import EmbeddingService
from app.repositories.firestore_repo import FirestoreRepository

class AgentFactory:
    def __init__(self):
        self.embedder = EmbeddingService()
        self.repo = FirestoreRepository()
        
        # 💡 画像生成用クライアントの初期化 (us-central1 の gemini-2.5-flash-image を利用)
        self.image_client = genai.Client(
            vertexai=True,
            project="certain-song-509313-d8",
            location="us-central1"
        )
        
        system_instruction = """
あなたは、ユーザーの新しい課題を解決するための「専門家AIエージェント」を設計するクリエイターです。
ユーザーの入力内容を分析し、それに最も適した一般的な職業・専門分野を持つエージェントを1つ定義してください。
※細かすぎる単位ではなく、汎用的に使える単位（例：「アジア旅行プランナー」「グルメアドバイザー」）で生成してください。

以下のJSON形式で出力してください：
{
    "name": "エージェントの表示名",
    "gender": "male または female（指定された性別をそのまま設定してください）",
    "description": "何をしてくれる専門家かの短い説明（性別に沿った人物像を記述してください）",
    "system_prompt": "このエージェントとして振る舞うための具体的な指示・口調・ルールの設定。※必ず「音声での会話用に、回答は最大でも150〜200文字程度（3〜4文）で短く簡潔にし、自然なキャッチボールをすること」というルールを含めてください。",
    "theme_color": "このエージェントのテーマカラー（UI背景用パステルカラー16進数。例: #E0F7FA）",
    "voice_name": "指定されたgenderに合わせ、以下から1つ選択してください：
      - femaleの場合: ja-JP-Neural2-B
      - maleの場合: ja-JP-Neural2-C または ja-JP-Neural2-D"
}
"""
        config = GenerationConfig(response_mime_type="application/json")
        self.model = GenerativeModel(
            "gemini-3.5-flash",
            system_instruction=system_instruction,
            generation_config=config
        )

    def _generate_avatar_image(self, agent_name: str, description: str, gender: str) -> str:
        """指定された性別を明記してアバターを生成。失敗時はデフォルトアバターに切り替える。"""
        bucket_name = os.getenv("GCS_TEMP_BUCKET_NAME", "kaleido-demo-temp-assets")
        default_avatar_url = f"https://storage.googleapis.com/{bucket_name}/avatars/default_avatar.jpg"

        gender_desc = "female character" if gender == "female" else "male character"

        try:
            print(f"🎨 [{agent_name}] のアバター画像を生成中 ({gender_desc}, Gemini 2.5 Flash Image)...")
            
            # 💡 性別をプロンプトに明確に指定
            prompt = (
                f"A professional anime-style full-body {gender_desc} illustration: {description}. "
                f"Clean white background, masterpiece, highest quality, flat colors, clear line art. "
                f"Textless, pure character visual only, absolutely no text, no words, no letters, no signs, no typography, no watermarks."
            )
            
            response = self.image_client.models.generate_content(
                model='gemini-2.5-flash-image',
                contents=prompt
            )
            
            image_bytes = None
            if response.candidates and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if part.inline_data:
                        image_bytes = part.inline_data.data
                        break
                        
            # 💡 バイトデータが取得できなかった場合はデフォルトアバターへフォールバック
            if not image_bytes:
                print(f"⚠️ 画像バイトデータが取得できませんでした。デフォルトアバターを使用します: {default_avatar_url}")
                return default_avatar_url
            
            # GCSにアップロード
            file_name = f"avatars/{uuid.uuid4().hex}.jpg"
            client = storage.Client()
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(file_name)
            
            blob.upload_from_string(image_bytes, content_type="image/jpeg")
            
            image_url = f"https://storage.googleapis.com/{bucket_name}/{file_name}"
            print(f"✅ アバター画像生成完了: {image_url}")
            return image_url
            
        except Exception as e:
            # 💡 クォータ制限(429)などの例外発生時もデフォルトアバターへフォールバック
            print(f"⚠️ 画像生成エラー ({e})。デフォルトアバターを使用します: {default_avatar_url}")
            return default_avatar_url

    def generate_and_save_agent(self, user_message: str, user_id: str):
        """ユーザーのメッセージから新しいエージェントを生成し、保存する"""
        print(f"🌟 [AgentFactory] 新しい専門家を自動生成中... (入力: {user_message}, ユーザー: {user_id})")
        
        used_colors = []
        male_count = 0
        female_count = 0

        # 💡 既存エージェントの色と性別比率をカウント
        try:
            docs = self.repo.db.collection("agents").where("user_id", "in", ["system", user_id]).stream()
            for doc in docs:
                data = doc.to_dict()
                color = data.get("theme_color")
                if color:
                    used_colors.append(color)

                voice = data.get("voice_name", "")
                if voice == "ja-JP-Neural2-B":
                    female_count += 1
                elif voice in ["ja-JP-Neural2-C", "ja-JP-Neural2-D"]:
                    male_count += 1
        except Exception as e:
            print(f"⚠️ 既存エージェント情報の取得失敗: {e}")

        # 💡 性別比率のバランシング（少ない方を優先、同数ならランダム）
        if male_count < female_count:
            target_gender = "male"
        elif female_count < male_count:
            target_gender = "female"
        else:
            target_gender = random.choice(["male", "female"])

        used_colors_str = ", ".join(used_colors) if used_colors else "なし"

        prompt = f"""以下の入力に適した専門家エージェントを作成してください。
入力内容: {user_message}

【重要指示】
1. 性別は必ず「{target_gender}」に設定してください。
2. 使用済みの色: {used_colors_str}
   これらの色とは明確に異なる色相（ピンク系、ブルー系、イエロー系、パープル系、オレンジ系など）のパステルカラー（16進数）を必ず設定してください。"""

        # 1. Geminiにエージェントのプロファイルを作らせる
        response = self.model.generate_content(prompt)
        
        try:
            agent_data = json.loads(response.text)
        except Exception:
            agent_data = {
                "name": "汎用アシスタント",
                "gender": target_gender,
                "description": "あらゆる質問に答えるサポート担当",
                "system_prompt": "あなたは親切なアシスタントです。※音声での会話用に、回答は最大でも150〜200文字程度（3〜4文）で短く簡潔にし、自然なキャッチボールをしてください。",
                "theme_color": "#F3E5F5",
                "voice_name": "ja-JP-Neural2-B" if target_gender == "female" else "ja-JP-Neural2-C"
            }
            
        gender = agent_data.get("gender", target_gender)
        
        # 💡 声の性別不一致を確実に防ぐガード処理
        if gender == "female":
            voice_name = "ja-JP-Neural2-B"
        else:
            voice_name = agent_data.get("voice_name", "ja-JP-Neural2-C")
            if voice_name not in ["ja-JP-Neural2-C", "ja-JP-Neural2-D"]:
                voice_name = "ja-JP-Neural2-C"

        theme_color = agent_data.get("theme_color", "#F3E5F5")
            
        # 2. 生成されたエージェントの特徴（description）をベクトル化する
        embedding = self.embedder.generate_vector(
            text=agent_data["description"], 
            task_type="RETRIEVAL_DOCUMENT"
        )
        
        # 3. アバター画像を生成する（性別指定 ＆ 失敗時はデフォルトアバターURLが返る）
        avatar_url = self._generate_avatar_image(agent_data["name"], agent_data["description"], gender)
        
        # 4. Firestoreに保存
        agent_id = f"auto_gen_{uuid.uuid4().hex[:8]}"
        new_agent = self.repo.create_agent(
            agent_id=agent_id,
            name=agent_data["name"],
            description=agent_data["description"],
            system_prompt=agent_data["system_prompt"],
            embedding=embedding,
            theme_color=theme_color,
            voice_name=voice_name,
            user_id=user_id,
            avatar_url=avatar_url
        )
        
        new_agent["voice_name"] = voice_name
        new_agent["theme_color"] = theme_color
        new_agent["avatar_url"] = avatar_url

        print(f"✨ [AgentFactory] 新しい専門家「{new_agent['name']}」({gender}, 声: {voice_name}) が誕生し、チームに加わりました！")
        if avatar_url:
            print(f"🖼️ アバター画像: {avatar_url}")
            
        return new_agent