import os
from google import genai
from google.genai import types

# 💡 プロジェクトIDを指定し、Vertex AI モードで初期化
# ※ ドキュメントにある通り global または us-central1 で呼び出します
client = genai.Client(
    vertexai=True,
    project="certain-song-509313-d8",
    location="us-central1"
)

prompt = "A cute cat wearing a red bowtie, anime style, clean white background, high quality, character illustration"

print("🎨 Gemini 2.5 Flash Image で画像を生成中...")

try:
    # 💡 response_mime_type を指定せず、テキストプロンプトのみを渡す
    response = client.models.generate_content(
        model='gemini-2.5-flash-image',
        contents=prompt
    )

    image_saved = False
    if response.candidates and response.candidates[0].content.parts:
        for part in response.candidates[0].content.parts:
            # 返却されたマルチモーダルパーツの中から画像データを抽出
            if part.inline_data:
                output_filename = "test_output.jpg"
                with open(output_filename, "wb") as f:
                    f.write(part.inline_data.data)
                print(f"🎉 生成・保存に成功しました！: {os.path.abspath(output_filename)}")
                image_saved = True
                break

    if not image_saved:
        print("⚠️ 画像データが含まれていませんでした。レスポンス:", response.text)

except Exception as e:
    print(f"❌ エラーが発生しました: {e}")