import os
import asyncio
import httpx
from vertexai.generative_models import FunctionDeclaration, Tool
from dotenv import load_dotenv

load_dotenv()

class YouCamService:
    def __init__(self):
        self.api_key = os.getenv("YOUCAM_API_KEY")
        self.base_url = "https://yce-api-01.makeupar.com/s2s/v2.0"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        self._cached_tools = None

    async def get_gemini_tools(self) -> Tool:
        if self._cached_tools is not None:
            return self._cached_tools
            
        analyze_skin_func = FunctionDeclaration(
            name="youcam_api_analyze_skin",
            description="ユーザーの顔画像の公開URLから、肌の水分量、シミ、シワ、毛穴などの状態をAIで分析・スコアリングします。",
            parameters={
                "type": "object",
                "properties": {
                    "image_url": {"type": "string", "description": "分析対象の顔画像の公開URL"}
                },
                "required": ["image_url"]
            }
        )
        self._cached_tools = Tool(function_declarations=[analyze_skin_func])
        return self._cached_tools

    async def execute_tool(self, tool_name: str, arguments: dict):
        if tool_name == "youcam_api_analyze_skin":
            image_url = arguments.get("image_url")
            print(f"💄 [YouCam] 肌分析開始: {image_url}")
            return await self.analyze_skin(image_url)
        return "Unknown tool"

    async def analyze_skin(self, image_url: str) -> str:
        if not self.api_key:
            print("🚨 [YouCam Fatal] .envファイルに YOUCAM_API_KEY が設定されていません！")
            return "YouCam APIキーが設定されていません。"
            
        try:
            print(f"⏳ [YouCam] 1. ユーザー画像のダウンロード開始: {image_url}")
            async with httpx.AsyncClient(timeout=45.0) as client:
                # 1. ユーザーの画像をダウンロード
                img_resp = await client.get(image_url)
                img_resp.raise_for_status() # HTTPエラー（403 Forbidden等）があればここで例外を発生させる
                img_bytes = img_resp.content
                img_size = len(img_bytes)
                print(f"✅ [YouCam] 画像取得成功 (サイズ: {img_size} bytes)")

                # 2. File API を叩いてアップロード用URLを取得
                print("⏳ [YouCam] 2. YouCamサーバーへアップロード枠を要求中...")
                file_payload = {
                    "files": [{
                        "content_type": "image/jpeg",
                        "file_name": "user_face.jpg",
                        "file_size": img_size
                    }]
                }
                file_resp = await client.post(f"{self.base_url}/file", headers=self.headers, json=file_payload)
                if file_resp.status_code != 200:
                    print(f"🚨 [YouCam API Error] File API 失敗: {file_resp.text}")
                    return f"YouCam APIとの通信に失敗しました: {file_resp.text}"
                    
                file_data = file_resp.json()["data"]["files"][0]
                file_id = file_data["file_id"]
                upload_req = file_data["requests"][0]

                # 3. 指定されたAWS S3 URLへ画像をバイナリでアップロード
                print("⏳ [YouCam] 3. S3へ画像バイナリをアップロード中...")
                upload_headers = upload_req["headers"]
                upload_resp = await client.put(upload_req["url"], headers=upload_headers, content=img_bytes)
                upload_resp.raise_for_status()

                # 4. Skin Analysis タスクの作成
                print("⏳ [YouCam] 4. 肌分析タスク (Skin Analysis) を作成中...")
                task_payload = {
                    "src_file_id": file_id,
                    "dst_actions": ["wrinkle", "texture", "acne", "moisture", "pore", "age_spot", "radiance", "eye_bag"],
                    "format": "json"
                }
                task_resp = await client.post(f"{self.base_url}/task/skin-analysis", headers=self.headers, json=task_payload)
                if task_resp.status_code != 200:
                    print(f"🚨 [YouCam API Error] Task API 失敗: {task_resp.text}")
                    return f"分析タスクの作成に失敗しました: {task_resp.text}"
                    
                task_id = task_resp.json()["data"]["task_id"]
                print(f"✅ [YouCam] タスク作成成功 (Task ID: {task_id})。分析完了を待ちます...")

                # 5. 分析完了までポーリング (最大30秒)
                for i in range(15):
                    await asyncio.sleep(2)
                    poll_resp = await client.get(f"{self.base_url}/task/skin-analysis/{task_id}", headers=self.headers)
                    poll_data = poll_resp.json().get("data", {})
                    status = poll_data.get("task_status")
                    
                    print(f"   ... ポーリング {i+1}/15: ステータス '{status}'")
                    
                    if status == "success":
                        results = poll_data.get("results", {})
                        
                        # 💡 堅牢なパース：返却形式がリストでも辞書でも対応できるようにする
                        report = "【YouCam 肌分析スコア (100点満点)】\n"
                        
                        try:
                            # パターン1: results["output"] がリストで返ってくる場合
                            if "output" in results and isinstance(results["output"], list):
                                for item in results["output"]:
                                    label = item.get("type", "Unknown").replace('_', ' ').capitalize()
                                    score = item.get("ui_score", item.get("raw_score", "N/A"))
                                    report += f"- {label}: {score}点\n"
                            
                            # パターン2: 直接 score_info.json のような辞書形式で返ってくる場合
                            elif isinstance(results, dict):
                                for key, val in results.items():
                                    if isinstance(val, dict):
                                        label = key.replace('hd_', '').replace('_', ' ').capitalize()
                                        score = val.get("ui_score", val.get("raw_score", "N/A"))
                                        if score != "N/A":
                                            report += f"- {label}: {score}点\n"
                                            
                        except Exception as parse_e:
                            print(f"⚠️ [YouCam Parse Error] JSON構造が想定外です。生データを送ります: {parse_e}")
                            report = f"【YouCam 肌分析 生データ】\n{results}\n"
                        
                        report += "\n※システムプロンプト：このスコアを分析し、ユーザーに専門的で優しい美容アドバイスを提供してください。"
                        print(f"✅ [YouCam] 分析完了！\n{report}")
                        return report
                        
                    elif status == "error":
                        error_detail = poll_resp.text
                        print(f"🚨 [YouCam API Error] 分析エンジン側でエラーが発生しました。\n詳細データ: {error_detail}")
                        return "画像の解析基準（顔のサイズや明るさなど）を満たさず、肌分析がエラーになりました。"
                        
                print("🚨 [YouCam Timeout] 分析が時間内に終わりませんでした。")
                return "肌分析がタイムアウトしました。"
        except Exception as e:
            print(f"🚨 [YouCam Exception] システム例外: {str(e)}")
            return f"画像処理中にシステム例外が発生しました: {str(e)}"