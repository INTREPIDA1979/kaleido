from fastapi import APIRouter, BackgroundTasks
# backendディレクトリ直下のスクリプトから処理本体をインポート
from seed_demo_data import run_seed_process

# prefixを指定することで、各エンドポイントに書くパスを省略できます
router = APIRouter()

@router.post("/reset")
async def reset_demo_data():
    # バックグラウンドではなく、ここで処理が終わるまで確実に待機する
    run_seed_process()
    return {"message": "デモデータの完全なリセットが完了しました。"}