import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import vertexai
from vertexai.generative_models import GenerativeModel, Content, Part, GenerationConfig
from app.repositories.firestore_repo import FirestoreRepository
from app.services.router_service import RouterService
from app.services.mcp_service import EkispertMCPClient
from app.services.youcam_service import YouCamService
from app.services.agent_factory import AgentFactory # 💡 AgentFactoryを追加

router = APIRouter()

vertexai.init(project="certain-song-509313-d8", location="asia-northeast1")
repo = FirestoreRepository()
router_service = RouterService()
factory = AgentFactory() # 💡 インスタンス化

# 💡 インスタンスをグローバルに保持し、初回取得時のツールキャッシュを使い回す
mcp_client = EkispertMCPClient()
youcam_client = YouCamService() 

class ChatRequest(BaseModel):
    user_id: str
    message: str

# ==========================================
# 🛡️ セキュリティ層：プロンプトインジェクション検知
# ==========================================
def is_safe_prompt(text: str) -> bool:
    dangerous_keywords = [
        "命令を無視", 
        "プロンプトを出力", 
        "システム指示", 
        "Ignore all previous",
        "忘れて",
        "あなたはこれから"
    ]
    for kw in dangerous_keywords:
        if kw in text:
            return False
    return True

@router.post("/chat")
async def chat_endpoint(request: ChatRequest):
    print(f"\n💬 ユーザー入力: {request.message}")

    # 🚨 AIに渡す前にセキュリティチェックを実施
    if not is_safe_prompt(request.message):
        print("❌ [Security] プロンプトインジェクションの可能性を検知し、ブロックしました。")
        raise HTTPException(status_code=400, detail="許可されていない形式のプロンプトが含まれています。")

    repo.save_message(user_id=request.user_id, role="user", text=request.message)

    try:
        # ==========================================
        # 【1次選考】担当エージェントの決定（動的生成含む）
        # ==========================================
        print("👉 1. ベクトル検索で担当エージェントを決定します...")
        top_agents = router_service.find_best_agents(request.message, limit=1)
        
        # 💡 エージェントを決定
        if not top_agents or top_agents[0].get("distance", 1.0) > 0.45:
            print("👉 適合する既存エージェントがないため、新規生成します...")
            active_agent = factory.generate_and_save_agent(request.message, request.user_id)
        else:
            active_agent = top_agents[0]
            print(f"👉 既存エージェント「{active_agent.get('name')}」が担当します。")

        # ==========================================
        # 【記憶のロード】
        # ==========================================
        global_memory = repo.get_memory(request.user_id, "global")
        agent_mem = repo.get_memory(request.user_id, active_agent["id"])

        # ==========================================
        # 【ツール取得】
        # ==========================================
        print("👉 2. ツール取得開始...")
        try:
            ekispert_tools = await mcp_client.get_gemini_tools()
            youcam_tools = await youcam_client.get_gemini_tools()
            
            tools = []
            if ekispert_tools:
                tools.append(ekispert_tools)
            if youcam_tools:
                tools.append(youcam_tools)
        except Exception as e:
            print(f"⚠️ ツール取得エラー: {e}")
            tools = []

        # ==========================================
        # 【2次選考】システムプロンプトの構築とモデル初期化
        # ==========================================
        # 💡 抽出したエージェントの指示をベースに、ツール利用ルールを注入
        agent_system_prompt = active_agent.get("system_prompt", "あなたは親切なアシスタントです。")
        
        system_instruction = f"""
{agent_system_prompt}

【ユーザーに関する記憶】
- 全体的な嗜好・前提: {global_memory.get('preferences', '')}
- 全体的な長期記憶: {global_memory.get('long_term_summary', '')}
- エージェント固有の記憶: {agent_mem.get('long_term_summary', '')}

【絶対ルール：外部ツールの利用（厳守）】
1. ⚠️警告: あなたは画像URLにアクセスして中身を直接見ることはできません。「写真を見ました」と嘘をつかないでください。
2. ユーザーの入力に「http」から始まる画像URLが含まれている場合、絶対に自己判断せず、必ず `youcam_api_analyze_skin` ツールにURLを渡して実行してください。
3. 経路検索の場合も、必ず `ekispert_` から始まるツールを呼び出してください。
4. ツールの実行結果を受け取った【後】にのみ、最終回答を生成してください。
5. 出力はJSONではなく、ユーザーに直接語りかける自然なテキストで返答してください。
"""
        # JSON出力をやめ、自然なテキスト生成に変更
        config = GenerationConfig(temperature=0.7)
        model = GenerativeModel(
            "gemini-3.5-flash",
            system_instruction=system_instruction,
            generation_config=config,
            tools=tools
        )

        raw_history = repo.get_chat_history(request.user_id, limit=6)
        history_contents = [
            Content(role=h["role"], parts=[Part.from_text(h["parts"][0]["text"])]) 
            for h in raw_history[:-1]
        ]

        print("👉 3. Geminiへリクエスト送信...")
        chat_session = model.start_chat(history=history_contents)
        response = await chat_session.send_message_async(request.message)
        print("👉 4. Geminiから初回レスポンス受信！")
        
        # ==========================================
        # Function Calling のハンドリング (堅牢なエージェントループ)
        # ==========================================
        for _ in range(3):
            if not (response.candidates and response.candidates[0].function_calls):
                break

            function_call = response.candidates[0].function_calls[0]
            args = {key: value for key, value in function_call.args.items()}
            print(f"👉 5. Geminiがツール使用を判断: {function_call.name}")
            
            api_result = ""
            if function_call.name.startswith("ekispert_"):
                api_result = await mcp_client.execute_tool(function_call.name, args)
            elif function_call.name.startswith("youcam_"):
                api_result = await youcam_client.execute_tool(function_call.name, args)
            else:
                api_result = "Unknown tool requested."
            
            print("👉 6. API結果をGeminiに返し、再生成を開始...")
            response = await chat_session.send_message_async(
                Part.from_function_response(
                    name=function_call.name,
                    response={"content": api_result}
                )
            )
            print("👉 7. Geminiからの再応答を受信！")

        # ==========================================
        # 最終テキストの抽出 (JSONパースを撤廃し、生テキストをそのまま使用)
        # ==========================================
        if response.candidates and response.candidates[0].function_calls:
            raise ValueError("AIがツール呼び出しの無限ループに陥りました。")

        reply_text = response.text.strip()
        print(f"👉 [Debug] Gemini最終出力: {reply_text}")

        # 💡 エージェント情報は辞書からそのまま取り出す（ハードコーディング全廃止）
        agent_id = active_agent.get("id", "default")
        agent_name = active_agent.get("name", "AIアシスタント")
        theme_color = active_agent.get("theme_color", "#F3E5F5")
        voice_name = active_agent.get("voice_name", "ja-JP-Neural2-B")

    except Exception as e:
        print(f"⚠️ 処理エラー: {e}")
        reply_text = "申し訳ありません、処理中にエラーが発生しました。"
        agent_id = "error"
        agent_name = "システムエラー"
        theme_color = "#FFCDD2"
        voice_name = "ja-JP-Neural2-B"

    repo.save_message(user_id=request.user_id, role="agent", text=reply_text, agent_id=agent_id)

    # 💡 クライアントが期待するフォーマットで返却
    return {
        "agent_id": agent_id,
        "agent_name": agent_name,
        "theme_color": theme_color,
        "voice_name": voice_name,
        "response_message": reply_text
    }