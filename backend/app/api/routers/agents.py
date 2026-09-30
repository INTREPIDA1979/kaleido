from fastapi import APIRouter, HTTPException
from app.repositories.firestore_repo import FirestoreRepository

router = APIRouter()
repo = FirestoreRepository()

# 💡 クエリパラメータ user_id を受け取る
@router.get("/agents")
def get_all_agents(user_id: str = "user_a"):
    try:
        # 💡 user_id が一致するエージェントだけを取得
        docs = repo.db.collection("agents").where("user_id", "in", ["system", user_id]).stream()
        agents = []
        for doc in docs:
            data = doc.to_dict()
            agents.append({
                "id": doc.id,
                "name": data.get("name", "名称未設定"),
                "description": data.get("description", ""),
                "theme_color": data.get("theme_color", "#F3E5F5")
            })
        return {"agents": agents}
    except Exception as e:
        print(f"🚨 エージェント一覧取得エラー: {e}")
        raise HTTPException(status_code=500, detail="エージェント情報の取得に失敗しました。")