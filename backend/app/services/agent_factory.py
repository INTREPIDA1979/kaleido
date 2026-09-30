import json
import uuid
from vertexai.generative_models import GenerativeModel, GenerationConfig
from app.services.embedding_service import EmbeddingService
from app.repositories.firestore_repo import FirestoreRepository

class AgentFactory:
    def __init__(self):
        self.embedder = EmbeddingService()
        self.repo = FirestoreRepository()
        
        system_instruction = """
あなたは、ユーザーの新しい課題を解決するための「専門家AIエージェント」を設計するクリエイターです。
ユーザーの入力内容を分析し、それに最も適した一般的な職業・専門分野を持つエージェントを1つ定義してください。
※細かすぎる単位（例：「台湾の夜市専門家」）ではなく、汎用的に使える単位（例：「アジア旅行プランナー」「グルメアドバイザー」）で生成してください。

以下のJSON形式で出力してください：
{
    "name": "エージェントの表示名",
    "description": "何をしてくれる専門家かの短い説明",
    "system_prompt": "このエージェントとして振る舞うための具体的な指示・口調・ルールの設定。※必ず「音声での会話用に、回答は最大でも150〜200文字程度（3〜4文）で短く簡潔にし、自然なキャッチボールをすること」というルールを含めてください。",
    "theme_color": "このエージェントのテーマカラー（UI背景用パステルカラー16進数。例: #E0F7FA）",
    "voice_name": "エージェントの性別やキャラクターに最も合う声質を、以下の3つから1つだけ選んで文字列で指定してください。
      - ja-JP-Neural2-B (女性 / 明るく親しみやすい)
      - ja-JP-Neural2-C (男性 / 高めで爽やか)
      - ja-JP-Neural2-D (男性 / 低くて渋い)"
}
"""
        config = GenerationConfig(response_mime_type="application/json")
        self.model = GenerativeModel(
            "gemini-3.5-flash",
            system_instruction=system_instruction,
            generation_config=config
        )

    def generate_and_save_agent(self, user_message: str, user_id: str):
        """ユーザーのメッセージから新しいエージェントを生成し、保存する"""
        print(f"🌟 [AgentFactory] 新しい専門家を自動生成中... (入力: {user_message}, ユーザー: {user_id})")
        
        # 💡 【追加】ユーザーの既存エージェントの色を取得して被りを防ぐ
        used_colors = []
        try:
            docs = self.repo.db.collection("agents").where("user_id", "in", ["system", user_id]).stream()
            for doc in docs:
                color = doc.to_dict().get("theme_color")
                if color:
                    used_colors.append(color)
        except Exception as e:
            print(f"⚠️ 色の取得に失敗しました: {e}")

        used_colors_str = ", ".join(used_colors) if used_colors else "なし"

        # 💡 【追加】Geminiへのプロンプトに「既存の色を避ける」絶対ルールを注入
        prompt = f"""以下の入力に適した専門家エージェントを作成してください。
入力内容: {user_message}

【重要: テーマカラーの指定ルール】
現在、以下の色が既に他のエージェントで使用されています。
使用済みの色: {used_colors_str}
新しいエージェントには、これらの色とは明確に異なる色相（ピンク系、ブルー系、イエロー系、パープル系、オレンジ系など）のパステルカラー（16進数）を必ず設定してください。"""

        # 1. Geminiにエージェントのプロファイルを作らせる
        response = self.model.generate_content(prompt)
        
        try:
            agent_data = json.loads(response.text)
        except Exception:
            agent_data = {
                "name": "汎用アシスタント",
                "description": "あらゆる質問に答えるサポート担当",
                "system_prompt": "あなたは親切なアシスタントです。※音声での会話用に、回答は最大でも150〜200文字程度（3〜4文）で短く簡潔にし、自然なキャッチボールをしてください。",
                "theme_color": "#F3E5F5",
                "voice_name": "ja-JP-Neural2-B" 
            }
            
        theme_color = agent_data.get("theme_color", "#F3E5F5")
        voice_name = agent_data.get("voice_name", "ja-JP-Neural2-B") 
            
        # 2. 生成されたエージェントの特徴（description）をベクトル化する
        embedding = self.embedder.generate_vector(
            text=agent_data["description"], 
            task_type="RETRIEVAL_DOCUMENT"
        )
        
        # 3. Firestoreに保存
        agent_id = f"auto_gen_{uuid.uuid4().hex[:8]}"
        new_agent = self.repo.create_agent(
            agent_id=agent_id,
            name=agent_data["name"],
            description=agent_data["description"],
            system_prompt=agent_data["system_prompt"],
            embedding=embedding,
            theme_color=theme_color,
            voice_name=voice_name,
            user_id=user_id 
        )
        
        new_agent["voice_name"] = voice_name
        new_agent["theme_color"] = theme_color

        print(f"✨ [AgentFactory] 新しい専門家「{new_agent['name']}」が誕生し、チームに加わりました！ (色: {theme_color}, 声: {voice_name})")
        return new_agent