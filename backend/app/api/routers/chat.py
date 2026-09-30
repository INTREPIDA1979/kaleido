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
        # 【1次選考】ベクトル検索で候補を抽出
        # ==========================================
        print("👉 1. ベクトル検索で候補を抽出します...")
        top_agents = router_service.find_best_agents(request.message, limit=3)
        
        # 💡 【真の原因解決】ベクトル検索の閾値落ち（候補ゼロ）対策
        # 検索結果が空になってしまった場合、ユーザーが利用可能なエージェントを直接取得して候補に補充する
        # （LLMに「現在の手持ちカード」を見せるための純粋なフォールバック）
        if not top_agents:
            print("👉 [Debug] ベクトル検索で候補が絞れなかったため、全保有エージェントを展開します")
            try:
                docs = repo.db.collection("agents").where("user_id", "in", ["system", request.user_id]).stream()
                top_agents = []
                for doc in docs:
                    data = doc.to_dict()
                    # 💡 データベースの構造に合わせて、doc.id や agent_id を 'id' として統一する
                    data["id"] = data.get("id", data.get("agent_id", doc.id))
                    top_agents.append(data)
            except Exception as e:
                print(f"👉 [Debug] エージェント展開エラー: {e}")

        # 直近の会話履歴を取得し、文脈を把握する
        raw_history = repo.get_chat_history(request.user_id, limit=6)
        history_text = "\n".join([f"{h['role']}: {h['parts'][0]['text']}" for h in raw_history[-2:]]) if raw_history else "なし"
        
        candidates_str = "\n".join([f"- ID: {a['id']}, 名前: {a['name']}, 説明: {a.get('description', '')}" for a in top_agents])

        # ==========================================
        # 【2次選考】超軽量LLMルーターによる文脈判定 (ピュア版)
        # ==========================================
        routing_prompt = f"""
あなたはユーザーの発言の意図を汲み取り、既存のAIエージェントに割り当てるか、新規作成するかを判定するルーターです。

【直前の会話履歴】
{history_text}

【既存エージェント候補】
{candidates_str}

【ユーザーの最新の発言】
{request.message}

【判定ルール】
1. ユーザーの発言の「最も主要な要求（主目的）」を特定してください。
2. その主目的が、既存エージェントの「役割・説明」の範囲内で解決できる場合は、該当するエージェントIDを出力してください。
3. ⚠️重要: 「〜しつつ」「〜のついでに」など直前の文脈に触れる前置きがあっても、要求の主目的（例：本格的なダイエットや食事プランの設計など）が現在のエージェントの専門外である場合は、過去の文脈に引っ張られずに必ず「new」と出力してください。
4. 代名詞（「そのメニュー」「それ」など）で直前の話題をそのまま深掘りしている場合は、文脈継続として同じエージェントIDを出力してください。

出力ルール: 該当するエージェントID、または「new」という文字列のみを出力してください。
"""
        
        print(f"👉 2. Geminiによる文脈判定を実行中... 候補:\n{candidates_str}")
        router_model = GenerativeModel("gemini-3.5-flash", generation_config=GenerationConfig(temperature=0.0))
        router_response = router_model.generate_content(routing_prompt)
        routed_result = router_response.text.strip().replace("`", "").replace("\n", "")
        print(f"👉 [Debug] ルーターの判定結果: {routed_result}") 
        
        # 💡 ルーターの判定結果に従ってエージェントを決定
        if routed_result == "new" or not top_agents:
            print("👉 3. 【判定: 新規話題】全く新しい専門家を生成します...")
            active_agent = factory.generate_and_save_agent(request.message, request.user_id)
        else:
            active_agent = next((a for a in top_agents if a["id"] == routed_result), top_agents[0])
            print(f"👉 3. 【判定: 文脈継続】既存エージェント「{active_agent.get('name')}」が引き続き担当します。")

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
6. ⚠️重要: 音声読み上げを前提としているため、太字（**）や見出し（#）などのMarkdown装飾は一切使用せず、必ずプレーンテキストのみで出力してください。
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
        for _ in range(5):
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

@router.get("/history")
async def get_history(user_id: str, limit: int = 15):
    """フロントエンドの初期表示用にチャット履歴を返す"""
    raw_history = repo.get_chat_history(user_id, limit=limit)
    
    formatted_history = []
    # 💡 古い順に並べ直してフロントエンドに渡す
    for h in reversed(raw_history):
        text = h["parts"][0]["text"] if "parts" in h and h["parts"] else h.get("text", "")
        formatted_history.append({
            "role": h.get("role", "user"),
            "text": text,
            "agent_id": h.get("agent_id"),
            "agent_name": h.get("agent_name"),
            "theme_color": h.get("theme_color")
        })
        
    return {"history": formatted_history}