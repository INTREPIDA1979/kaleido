import os
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from vertexai.generative_models import FunctionDeclaration, Tool
from dotenv import load_dotenv

load_dotenv()

class EkispertMCPClient:
    def __init__(self):
        self.url = "https://api-mcp.ekispert.jp/mcp"
        self.access_key = os.getenv("EKISPERT_API_ACCESS_KEY") 
        
        if not self.access_key:
            print("🚨 [FATAL] APIキーが読み込めていません！.envファイルの配置か変数名を確認してください。")

        self.headers = {
            "ekispert-api-access-key": self.access_key,
            "Accept": "text/event-stream"
        }

        self._cached_tools = None  # 💡 キャッシュ用の変数を追加
        
        print("\n=== 🚆 MCPクライアント起動 (本番APIフル稼働モード) ===")
        print("====================================================\n")

    async def get_gemini_tools(self) -> Tool:
        # 💡 すでに取得済みなら、即座にキャッシュを返す
        if self._cached_tools is not None:
            return self._cached_tools
        
        print("⏳ [MCP] 本番サーバーからツール一覧を取得中...")
        declarations = []
        
        # 💡 Geminiが拒絶する不要なキーを根こそぎ削除する最強のサニタイズ関数
        def sanitize_schema(d):
            if isinstance(d, dict):
                d.pop("$schema", None)
                d.pop("exclusiveMinimum", None)
                d.pop("exclusiveMaximum", None)
                for key, value in list(d.items()):
                    sanitize_schema(value)
            elif isinstance(d, list):
                for item in d:
                    sanitize_schema(item)
            return d

        try:
            async with streamablehttp_client(self.url, headers=self.headers) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    response = await session.list_tools()
                    
                    for tool in response.tools:
                        raw_schema = tool.inputSchema or {}
                        schema = sanitize_schema(raw_schema)
                        
                        if "type" not in schema:
                            schema["type"] = "object"
                        if "properties" not in schema:
                            schema["properties"] = {}

                        try:
                            declarations.append(
                                FunctionDeclaration(
                                    name=tool.name,
                                    description=tool.description,
                                    parameters=schema
                                )
                            )
                        except Exception as schema_e:
                            print(f"⚠️ [Skip] ツール '{tool.name}' のスキーマ変換エラー: {schema_e}")
                            
                    print(f"✅ [MCP] {len(declarations)}個の本番ツールを読み込みました！")
        except Exception as e:
            print(f"⚠️ [MCP] ツール取得中に例外発生: {e}")

        # モックは削除し、純粋に取得できたツールのみを返す
        if not declarations:
            print("⚠️ [MCP] 利用可能なツールがありません。APIの応答を確認してください。")

        return Tool(function_declarations=declarations)

    async def execute_tool(self, tool_name: str, arguments: dict):
        # ==========================================
        # 🛡️ ガードレール層
        # ==========================================
        safe_args = arguments.copy()
        # prohibited_keys = ["date", "time", "departureTime", "arrivalTime", "searchType"]
        prohibited_keys = []
        for key in prohibited_keys:
            if key in safe_args:
                print(f"🛡️ [Guardrail] 規約違反防止のため、パラメータ '{key}' を強制削除しました。")
                del safe_args[key]

        print(f"🚆 [MCP Call] 実行ツール: {tool_name}, 引数: {safe_args}")
        
        content = ""
        try:
            async with streamablehttp_client(self.url, headers=self.headers) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments=safe_args)
                    for item in result.content:
                        if item.type == "text":
                            content += item.text
        except Exception as e:
            print(f"⚠️ [MCP] ツール実行中に例外発生: {e}")

        # モックは削除し、APIエラー時はエラーメッセージのみを返す
        if not content:
            content = "経路情報の取得に失敗しました。時間をおいて再度お試しください。"
            
        return content