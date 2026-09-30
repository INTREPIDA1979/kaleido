import os
import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from google.cloud import texttospeech

router = APIRouter()

# GCP TTSクライアントの初期化（ローカルADC認証を利用）
client = texttospeech.TextToSpeechClient()

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
        response = client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )
        
        # 4. 既存の uploads フォルダにMP3として保存
        filename = f"tts_{uuid.uuid4().hex[:8]}.mp3"
        filepath = os.path.join("uploads", filename)
        
        with open(filepath, "wb") as out:
            out.write(response.audio_content)
            
        # 5. フロントエンドがアクセスできるURLを返す
        file_url = f"http://127.0.0.1:8080/uploads/{filename}"
        print(f"✅ [TTS] 音声生成完了: {file_url} (Voice: {request.voice_name})")
        
        return {"audio_url": file_url}
        
    except Exception as e:
        print(f"🚨 [TTS Error] 音声合成に失敗しました: {e}")
        raise HTTPException(status_code=500, detail="音声の合成に失敗しました")