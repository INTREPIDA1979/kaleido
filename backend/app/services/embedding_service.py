from vertexai.language_models import TextEmbeddingInput, TextEmbeddingModel

class EmbeddingService:
    def __init__(self):
        # 最新のテキスト埋め込みモデルを指定
        self.model = TextEmbeddingModel.from_pretrained("text-multilingual-embedding-002")

    def generate_vector(self, text: str, task_type: str = "RETRIEVAL_DOCUMENT") -> list[float]:
        """
        テキストをベクトル（数値の配列）に変換する
        task_type:
            - RETRIEVAL_DOCUMENT: データベースに保存する側（エージェントの説明文）
            - RETRIEVAL_QUERY: 検索する側（ユーザーの入力）
        """
        inputs = [TextEmbeddingInput(text, task_type)]
        embeddings = self.model.get_embeddings(inputs)
        return embeddings[0].values