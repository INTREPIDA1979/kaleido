from app.services.embedding_service import EmbeddingService
from app.repositories.firestore_repo import FirestoreRepository

class RouterService:
    def __init__(self):
        self.embedder = EmbeddingService()
        self.repo = FirestoreRepository()
        # 💡 AgentFactory の依存と閾値設定を削除（chat.py側に移譲）

    def find_best_agents(self, user_message: str, limit: int = 3):
        """
        ユーザーの入力をベクトル化し、Firestoreから最適なエージェントを検索して返す。
        （※生成ロジックは chat.py 側に移譲したため、ここでは純粋な検索のみを行う）
        """
        # 1. クエリをベクトル化
        query_vector = self.embedder.generate_vector(
            text=user_message, 
            task_type="RETRIEVAL_QUERY"
        )
        
        # 2. Firestoreで類似度検索
        top_agents = self.repo.search_agents(query_vector=query_vector, limit=limit)
        
        # 💡 生成ロジックを取り除き、そのまま結果を返す
        return top_agents