import os
import uuid
from datetime import timedelta
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from google.cloud import texttospeech
from google.cloud import storage

router = APIRouter()

# GCP クライアントの初期化（再利用してパフォーマンスを上げるためグローバルに配置）
tts_client = texttospeech.TextToSpeechClient()
storage_client = storage.Client()

class TTSRequest(BaseModel):
    text: str
    voice_name: str

@router.post("/tts")
async def generate_speech(request: TTSRequest):
    try:
        # 1. テキストと音声（声質）の設定
        synthesis_input = texttospeech.SynthesisInput(text=request.text)
        voice = texttospeech.VoiceSelectionParams(
            language_code="ja-JP",
            name=request.voice_name,
        )
        
        # 2. 出力形式をMP3に設定
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3
        )
        
        # 3. GCP APIを呼び出して音声合成
        response = tts_client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )
        
        # 4. GCSへ直接アップロード
        bucket_name = os.getenv("GCS_TEMP_BUCKET_NAME")
        if not bucket_name:
            raise Exception("環境変数 GCS_TEMP_BUCKET_NAME が設定されていません。")

        # 音声ファイルは audio/ フォルダ以下に保存して整理する
        filename = f"audio/tts_{uuid.uuid4().hex[:8]}.mp3"
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(filename)
        
        # メモリ上の音声バイトデータを直接GCSへストリームアップロード
        blob.upload_from_string(response.audio_content, content_type="audio/mpeg")
        
        # 5. フロントエンドがアクセスできる「署名付きURL（24時間有効）」を生成
        signed_url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(hours=24),
            method="GET"
        )
        
        print(f"✅ [TTS] 音声生成＆GCS保存完了: (Voice: {request.voice_name})")
        
        return {"audio_url": signed_url}
        
    except Exception as e:
        print(f"🚨 [TTS Error] 音声合成・GCS保存に失敗しました: {e}")
        raise HTTPException(status_code=500, detail="音声の合成に失敗しました")