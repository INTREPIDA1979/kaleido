import os
import uuid
import shutil
from fastapi import APIRouter, UploadFile, File

router = APIRouter()

# 画像の保存先ディレクトリを作成
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/upload")
async def upload_image(file: UploadFile = File(...)):
    # 拡張子を取得し、一意のファイル名を生成
    ext = file.filename.split(".")[-1]
    filename = f"{uuid.uuid4()}.{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    
    # ファイルを保存
    with open(filepath, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # ローカル検証用のURLを返す（バックエンド自身がダウンロード可能なURL）
    file_url = f"http://127.0.0.1:8080/uploads/{filename}"
    print(f"✅ 画像アップロード成功: {file_url}")
    return {"url": file_url}