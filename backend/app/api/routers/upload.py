import os
import uuid
from datetime import timedelta
from fastapi import APIRouter, UploadFile, File
from google.cloud import storage

router = APIRouter()

@router.post("/upload")
async def upload_image(file: UploadFile = File(...)):
    # .envからバケット名を取得
    bucket_name = os.getenv("GCS_TEMP_BUCKET_NAME")
    if not bucket_name:
        raise Exception("GCS_TEMP_BUCKET_NAME is not set in environment variables.")

    # ファイル名をユニークにする
    ext = file.filename.split('.')[-1] if '.' in file.filename else 'jpg'
    new_filename = f"{uuid.uuid4().hex}.{ext}"

    # GCSへアップロード
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(f"images/{new_filename}")
    
    # メモリ上のファイルを直接GCSへストリームアップロード
    blob.upload_from_file(file.file, content_type=file.content_type)

    # フロントエンドがアクセスできる「署名付きURL（24時間有効）」を生成
    signed_url = blob.generate_signed_url(
        version="v4",
        expiration=timedelta(hours=24),
        method="GET"
    )

    return {"url": signed_url}