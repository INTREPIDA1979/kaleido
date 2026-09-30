from google.cloud import firestore
import uuid
from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
from google.cloud.firestore_v1.vector import Vector

class FirestoreRepository:
    def __init__(self):
        # ローカルADCを利用して認証キーなしで自動接続
        self.db = firestore.Client()

    def save_message(self, user_id: str, role: str, text: str, agent_id: str = None):
        """メッセージをFirestoreに保存する"""
        message_id = str(uuid.uuid4())
        doc_ref = self.db.collection("users").document(user_id).collection("messages").document(message_id)
        
        data = {
            "role": role,
            "text": text,
            "created_at": firestore.SERVER_TIMESTAMP
        }
        if agent_id:
            data["agent_id"] = agent_id
            
        doc_ref.set(data)

    def get_chat_history(self, user_id: str, limit: int = 10):
        """直近の会話履歴を取得し、時系列（古い順）に並べ替えて返す"""
        messages_ref = self.db.collection("users").document(user_id).collection("messages")
        
        # 最新のlimit件を取得
        docs = messages_ref.order_by(
            "created_at", direction=firestore.Query.DESCENDING
        ).limit(limit).stream()
        
        # Geminiに渡す形式に変換
        history = []
        for doc in docs:
            data = doc.to_dict()
            history.append({
                "role": "user" if data.get("role") == "user" else "model",
                "parts": [{"text": data.get("text")}]
            })
            
        # 降順で取得したものを時系列（昇順）に戻す
        return history[::-1]

    def search_agents(self, query_vector: list[float], limit: int = 3):
        """ベクトル検索でクエリに最も近いエージェントを上位抽出する"""
        collection_ref = self.db.collection("agents")
        
        vector_query = collection_ref.find_nearest(
            vector_field="embedding",
            query_vector=Vector(query_vector),
            distance_measure=DistanceMeasure.COSINE,
            limit=limit,
            distance_result_field="distance"
        )
        
        docs = vector_query.stream()
        agents = []
        for doc in docs:
            data = doc.to_dict()
            agents.append({
                "id": doc.id,
                "name": data.get("name"),
                "description": data.get("description"),
                "system_prompt": data.get("system_prompt"),
                "distance": data.get("distance"),
                "theme_color": data.get("theme_color") # 💡 DBからテーマカラーも取得するよう追加
            })
        return agents
    
    def get_memory(self, user_id: str, agent_id: str = "global"):
        """グローバルまたはエージェント固有の記憶を取得する。存在しなければ初期化する。"""
        if agent_id == "global":
            doc_ref = self.db.collection("users").document(user_id).collection("global_memory").document("orchestrator")
        else:
            doc_ref = self.db.collection("users").document(user_id).collection("agent_memories").document(agent_id)

        doc = doc_ref.get()
        if doc.exists:
            return doc.to_dict()
        
        # 存在しない場合のデフォルト構造
        default_memory = {
            "preferences": "",
            "long_term_summary": "",
            "working_memory": ""
        }
        doc_ref.set(default_memory)
        return default_memory

    # 💡 引数に theme_color を追加し、デフォルト値を設定
    def create_agent(self, agent_id: str, name: str, description: str, system_prompt: str, embedding: list[float], theme_color: str = "#F3E5F5", voice_name: str = "ja-JP-Neural2-B", user_id: str = "user_a"):
        doc_ref = self.db.collection("agents").document(agent_id)
        doc_ref.set({
            "user_id": user_id, # 👈 追加
            "name": name,
            "description": description,
            "system_prompt": system_prompt,
            "embedding": embedding,
            "theme_color": theme_color,
            "voice_name": voice_name
        })
        return {
            "id": agent_id,
            "name": name,
            "description": description,
            "system_prompt": system_prompt,
            "theme_color": theme_color # 💡 戻り値にも追加
        }