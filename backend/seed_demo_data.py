import uuid
import time
from fastapi import APIRouter, BackgroundTasks
from app.repositories.firestore_repo import FirestoreRepository
from app.services.embedding_service import EmbeddingService

router = APIRouter()

# サブコレクションも含めて再帰的に完全削除するヘルパー関数
def delete_collection_recursively(collection_ref):
    deleted_count = 0
    for doc in collection_ref.stream():
        # 1. ドキュメントに紐づくサブコレクション（messages, global_memory等）を全て取得して削除
        for sub_collection in doc.reference.collections():
            delete_collection_recursively(sub_collection)
        # 2. サブコレクションを消し終わったら、親ドキュメント自身を削除
        doc.reference.delete()
        deleted_count += 1
    return deleted_count

# リセット処理の本体
def run_seed_process():
    repo = FirestoreRepository()
    embedder = EmbeddingService()
    db = repo.db

    print("🚀 デモ用初期データの投入（リセット）を開始します...")

    # 1. 既存の `agents` コレクションを完全に初期化
    print("🗑️ 既存のエージェントデータを削除しています...")
    agents_deleted = delete_collection_recursively(db.collection("agents"))
    print(f"✨ {agents_deleted}件のエージェント親ドキュメントを削除しました。")

    # 2. 既存の `users` コレクションを完全に初期化（ゴーストドキュメント対策）
    print("🗑️ 既存のユーザーデータ（チャット履歴・記憶含む）を削除しています...")
    target_user_ids = ["user_a", "user_b", "system", "test_user_01"]
    for uid in target_user_ids:
        user_doc_ref = db.collection("users").document(uid)
        for sub_collection in user_doc_ref.collections():
            delete_collection_recursively(sub_collection)
        user_doc_ref.delete()
    
    # 念のため、通常のstream()で取得できるユーザーも削除
    users_deleted = delete_collection_recursively(db.collection("users"))
    print(f"✨ ユーザーデータを完全に削除し、まっさらな状態にしました。")

    # 3. 共通エージェント (system) の登録
    system_agents = [
        {
            "id": "travel_planner_01",
            "name": "駅すぱあと経路検索エージェント",
            "description": "駅すぱあとAPIと連携し、国内外の旅行計画、おすすめスポット、交通機関の案内を行う専門家。",
            "system_prompt": "あなたは駅すぱあとの経路検索ロジックを活用するプロの旅行プランナーです。最適な旅程を提案してください。※音声での会話用に、回答は最大でも150〜200文字程度（3〜4文）で短く簡潔にし、ユーザーと自然なキャッチボールをしてください。",
            "theme_color": "#E0F7FA",
            "voice_name": "ja-JP-Neural2-C",
            "user_id": "system"
        },
        {
            "id": "beauty_analyst_01",
            "name": "YouCam肌分析エージェント",
            "description": "YouCamのAI解析技術をベースに、肌質や骨格に合わせたメイクアップ、スキンケアの提案を行う専門家。",
            "system_prompt": "あなたはYouCamの肌診断技術を活用するビューティーアナリストです。美と健康に関する専門的なアドバイスを提供してください。※音声での会話用に、回答は最大でも150〜200文字程度（3〜4文）で短く簡潔にし、ユーザーと自然なキャッチボールをしてください。",
            "theme_color": "#FCE4EC",
            "voice_name": "ja-JP-Neural2-B",
            "user_id": "system"
        }
    ]

    for a in system_agents:
        embedding = embedder.generate_vector(a["description"], "RETRIEVAL_DOCUMENT")
        repo.create_agent(
            agent_id=a["id"], name=a["name"], description=a["description"],
            system_prompt=a["system_prompt"], embedding=embedding,
            theme_color=a["theme_color"], voice_name=a["voice_name"], user_id=a["user_id"]
        )
        print(f"✅ 共通エージェント登録完了: {a['name']}")

    # 4. User B専用エージェントの登録
    user_b_agents = [
        {"name": "ITサポートエンジニア", "desc": "PCトラブルやネットワーク設定を支援する技術者", "color": "#E8EAF6", "voice": "ja-JP-Neural2-C"},
        {"name": "熱血フィットネストレーナー", "desc": "自宅でできる自重トレーニングや食事管理を指導", "color": "#FFEBEE", "voice": "ja-JP-Neural2-D"},
        {"name": "セルフケアアドバイザー", "desc": "勉強や仕事の疲れを癒やすリフレッシュ方法を提案", "color": "#E8F5E9", "voice": "ja-JP-Neural2-A"},
        {"name": "アクアリウム専門家", "desc": "熱帯魚の飼育や水槽のレイアウトをアドバイス", "color": "#E3F2FD", "voice": "ja-JP-Neural2-C"},
        {"name": "子育てコミュニケーション", "desc": "反抗期の子どもとの接し方や教育の悩みに寄り添う", "color": "#FFF3E0", "voice": "ja-JP-Neural2-B"},
        {"name": "資産運用コンサルタント", "desc": "NISAやiDeCoなど、初心者のための投資アドバイス", "color": "#FFF8E1", "voice": "ja-JP-Neural2-D"},
        {"name": "時短レシピクリエイター", "desc": "忙しい日でも10分で作れる栄養満点の料理を提案", "color": "#FBE9E7", "voice": "ja-JP-Neural2-B"},
        {"name": "台湾グルメガイド", "desc": "台湾の夜市やローカルフードの美味しい楽しみ方を解説", "color": "#F3E5F5", "voice": "ja-JP-Neural2-B"},
        {"name": "睡眠改善インストラクター", "desc": "良質な睡眠をとるための環境づくりや習慣を指導", "color": "#EDE7F6", "voice": "ja-JP-Neural2-A"},
        {"name": "弓道フォームアナリスト", "desc": "射法八節や手首の角度など、弓道の技術的指導", "color": "#F5F5F5", "voice": "ja-JP-Neural2-D"}
    ]

    # 生成したエージェントのIDを保持して履歴追加時に利用する
    created_user_b_agents = {}

    for a in user_b_agents:
        agent_id = f"user_b_agent_{uuid.uuid4().hex[:8]}"
        created_user_b_agents[a["name"]] = {
            "id": agent_id,
            "theme_color": a["color"],
            "voice_name": a["voice"]
        }
        
        embedding = embedder.generate_vector(a["desc"], "RETRIEVAL_DOCUMENT")
        repo.create_agent(
            agent_id=agent_id, name=a["name"], description=a["desc"],
            system_prompt=f"あなたは{a['name']}です。専門知識を活かして答えてください。",
            embedding=embedding, theme_color=a["color"], voice_name=a["voice"], user_id="user_b"
        )
        print(f"✅ User Bエージェント登録完了: {a['name']}")
import uuid
import time
from fastapi import APIRouter, BackgroundTasks
from app.repositories.firestore_repo import FirestoreRepository
from app.services.embedding_service import EmbeddingService

router = APIRouter()

# サブコレクションも含めて再帰的に完全削除するヘルパー関数
def delete_collection_recursively(collection_ref):
    deleted_count = 0
    for doc in collection_ref.stream():
        # 1. ドキュメントに紐づくサブコレクション（messages, global_memory等）を全て取得して削除
        for sub_collection in doc.reference.collections():
            delete_collection_recursively(sub_collection)
        # 2. サブコレクションを消し終わったら、親ドキュメント自身を削除
        doc.reference.delete()
        deleted_count += 1
    return deleted_count

# リセット処理の本体
def run_seed_process():
    repo = FirestoreRepository()
    embedder = EmbeddingService()
    db = repo.db

    print("🚀 デモ用初期データの投入（リセット）を開始します...")

    # 1. 既存の `agents` コレクションを完全に初期化
    print("🗑️ 既存のエージェントデータを削除しています...")
    agents_deleted = delete_collection_recursively(db.collection("agents"))
    print(f"✨ {agents_deleted}件のエージェント親ドキュメントを削除しました。")

    # 2. 既存の `users` コレクションを完全に初期化（ゴーストドキュメント対策）
    print("🗑️ 既存のユーザーデータ（チャット履歴・記憶含む）を削除しています...")
    target_user_ids = ["user_a", "user_b", "system", "test_user_01"]
    for uid in target_user_ids:
        user_doc_ref = db.collection("users").document(uid)
        for sub_collection in user_doc_ref.collections():
            delete_collection_recursively(sub_collection)
        user_doc_ref.delete()
    
    # 念のため、通常のstream()で取得できるユーザーも削除
    users_deleted = delete_collection_recursively(db.collection("users"))
    print(f"✨ ユーザーデータを完全に削除し、まっさらな状態にしました。")

    # 3. 共通エージェント (system) の登録
    system_agents = [
        {
            "id": "travel_planner_01",
            "name": "駅すぱあと経路検索エージェント",
            "description": "駅すぱあとAPIと連携し、国内外の旅行計画、おすすめスポット、交通機関の案内を行う専門家。",
            "system_prompt": "あなたは駅すぱあとの経路検索ロジックを活用するプロの旅行プランナーです。最適な旅程を提案してください。※音声での会話用に、回答は最大でも150〜200文字程度（3〜4文）で短く簡潔にし、ユーザーと自然なキャッチボールをしてください。",
            "theme_color": "#E0F7FA",
            "voice_name": "ja-JP-Neural2-C",
            "user_id": "system"
        },
        {
            "id": "beauty_analyst_01",
            "name": "YouCam肌分析エージェント",
            "description": "YouCamのAI解析技術をベースに、肌質や骨格に合わせたメイクアップ、スキンケアの提案を行う専門家。",
            "system_prompt": "あなたはYouCamの肌診断技術を活用するビューティーアナリストです。美と健康に関する専門的なアドバイスを提供してください。※音声での会話用に、回答は最大でも150〜200文字程度（3〜4文）で短く簡潔にし、ユーザーと自然なキャッチボールをしてください。",
            "theme_color": "#FCE4EC",
            "voice_name": "ja-JP-Neural2-B",
            "user_id": "system"
        }
    ]

    for a in system_agents:
        embedding = embedder.generate_vector(a["description"], "RETRIEVAL_DOCUMENT")
        repo.create_agent(
            agent_id=a["id"], name=a["name"], description=a["description"],
            system_prompt=a["system_prompt"], embedding=embedding,
            theme_color=a["theme_color"], voice_name=a["voice_name"], user_id=a["user_id"]
        )
        print(f"✅ 共通エージェント登録完了: {a['name']}")

    # 4. User B専用エージェントの登録
    user_b_agents = [
        {"name": "ITサポートエンジニア", "desc": "PCトラブルやネットワーク設定を支援する技術者", "color": "#E8EAF6", "voice": "ja-JP-Neural2-C"},
        {"name": "熱血フィットネストレーナー", "desc": "自宅でできる自重トレーニングや食事管理を指導", "color": "#FFEBEE", "voice": "ja-JP-Neural2-D"},
        {"name": "セルフケアアドバイザー", "desc": "勉強や仕事の疲れを癒やすリフレッシュ方法を提案", "color": "#E8F5E9", "voice": "ja-JP-Neural2-A"},
        {"name": "アクアリウム専門家", "desc": "熱帯魚の飼育や水槽のレイアウトをアドバイス", "color": "#E3F2FD", "voice": "ja-JP-Neural2-C"},
        {"name": "子育てコミュニケーション", "desc": "反抗期の子どもとの接し方や教育の悩みに寄り添う", "color": "#FFF3E0", "voice": "ja-JP-Neural2-B"},
        {"name": "資産運用コンサルタント", "desc": "NISAやiDeCoなど、初心者のための投資アドバイス", "color": "#FFF8E1", "voice": "ja-JP-Neural2-D"},
        {"name": "時短レシピクリエイター", "desc": "忙しい日でも10分で作れる栄養満点の料理を提案", "color": "#FBE9E7", "voice": "ja-JP-Neural2-B"},
        {"name": "台湾グルメガイド", "desc": "台湾の夜市やローカルフードの美味しい楽しみ方を解説", "color": "#F3E5F5", "voice": "ja-JP-Neural2-B"},
        {"name": "睡眠改善インストラクター", "desc": "良質な睡眠をとるための環境づくりや習慣を指導", "color": "#EDE7F6", "voice": "ja-JP-Neural2-A"},
        {"name": "弓道フォームアナリスト", "desc": "射法八節や手首の角度など、弓道の技術的指導", "color": "#F5F5F5", "voice": "ja-JP-Neural2-D"}
    ]

    # 生成したエージェントのIDを保持して履歴追加時に利用する
    created_user_b_agents = {}

    for a in user_b_agents:
        agent_id = f"user_b_agent_{uuid.uuid4().hex[:8]}"
        created_user_b_agents[a["name"]] = {
            "id": agent_id,
            "theme_color": a["color"],
            "voice_name": a["voice"]
        }
        
        embedding = embedder.generate_vector(a["desc"], "RETRIEVAL_DOCUMENT")
        repo.create_agent(
            agent_id=agent_id, name=a["name"], description=a["desc"],
            system_prompt=f"あなたは{a['name']}です。専門知識を活かして答えてください。",
            embedding=embedding, theme_color=a["color"], voice_name=a["voice"], user_id="user_b"
        )
        print(f"✅ User Bエージェント登録完了: {a['name']}")

    # 5. User B のダミーチャット履歴を追加
    print("💬 User Bのチャット履歴を生成しています...")
    
    # 会話1: 台湾旅行 (台湾グルメガイド)
    tw_agent = created_user_b_agents["台湾グルメガイド"]
    repo.save_message(user_id="user_b", role="user", text="今度台湾に行く予定なんですが、おすすめの夜市と絶対食べるべきローカルフードを教えてください！")
    time.sleep(0.5)
    repo.save_message(
        user_id="user_b", role="agent", 
        text="台湾旅行ですね！初めてなら「士林夜市（シーリンイエシー）」や「饒河街夜市（ラオホージエ）」がおすすめです。名物の大きなフライドチキン（大鶏排）や、胡椒餅は絶対に外せませんよ！", 
        agent_id=tw_agent["id"], agent_name="台湾グルメガイド", theme_color=tw_agent["theme_color"]
    )
    time.sleep(0.5)

    # 会話2: 弓道 (弓道フォームアナリスト)
    kyudo_agent = created_user_b_agents["弓道フォームアナリスト"]
    repo.save_message(user_id="user_b", role="user", text="離れの時に弓手が下がってしまう癖があるのですが、どうすれば改善できますか？")
    time.sleep(0.5)
    repo.save_message(
        user_id="user_b", role="agent", 
        text="弓手が下がるのは、押し開く力が途切れていることが原因の一つです。会で的の中心に向かって真っ直ぐに伸び合いを続け、矢筋に沿って自然に離れる感覚を意識してみてください。手首の角度も要確認ですね。", 
        agent_id=kyudo_agent["id"], agent_name="弓道フォームアナリスト", theme_color=kyudo_agent["theme_color"]
    )
    time.sleep(0.5)

    # 会話3: 宅建試験の勉強と睡眠 (睡眠改善インストラクター)
    sleep_agent = created_user_b_agents["睡眠改善インストラクター"]
    repo.save_message(user_id="user_b", role="user", text="10月の宅建試験に向けて夜遅くまで勉強しているのですが、翌日に疲れが残ってしまいます。短い時間でもスッキリ起きられるコツはありますか？")
    time.sleep(0.5)
    repo.save_message(
        user_id="user_b", role="agent", 
        text="資格試験の勉強、お疲れ様です！就寝の90分前に入浴して深部体温を上げることと、寝る直前のスマホを控えるだけで睡眠の質は劇的に変わります。まずは今夜、湯船にしっかり浸かってみませんか？", 
        agent_id=sleep_agent["id"], agent_name="睡眠改善インストラクター", theme_color=sleep_agent["theme_color"]
    )
    time.sleep(0.5)

    # 会話4: サッカーと筋トレ (熱血フィットネストレーナー)
    fitness_agent = created_user_b_agents["熱血フィットネストレーナー"]
    repo.save_message(user_id="user_b", role="user", text="週末のサッカーの試合に向けて、下半身のウェイトトレーニングのメニューを少し軽めにした方がいいでしょうか？")
    time.sleep(0.5)
    repo.save_message(
        user_id="user_b", role="agent", 
        text="試合前のコンディショニングだな！素晴らしい心がけだ！試合の2〜3日前からは、高重量のスクワットは控えて、自重でのランジやストレッチ中心の疲労を抜くメニューに切り替えよう。当日に最高のパフォーマンスを出せるぞ！", 
        agent_id=fitness_agent["id"], agent_name="熱血フィットネストレーナー", theme_color=fitness_agent["theme_color"]
    )
    time.sleep(0.5)

    # 会話5: 子育て (子育てコミュニケーション)
    parenting_agent = created_user_b_agents["子育てコミュニケーション"]
    repo.save_message(user_id="user_b", role="user", text="中学生になった娘が、最近あまり学校の出来事を話してくれなくなりました。どう接するのが正解なんでしょうか。")
    time.sleep(0.5)
    repo.save_message(
        user_id="user_b", role="agent", 
        text="中学生という多感な時期にはよくある変化ですので、ご安心くださいね。無理に聞き出そうとせず、「いつでも話を聞くよ」という姿勢で見守ることが大切です。一緒に美味しいものを食べている時など、リラックスした場面でふと話してくれることが多いですよ。", 
        agent_id=parenting_agent["id"], agent_name="子育てコミュニケーション", theme_color=parenting_agent["theme_color"]
    )
    time.sleep(0.5)

    # 会話6: ICTコンサルティング (ITサポートエンジニア)
    it_agent = created_user_b_agents["ITサポートエンジニア"]
    repo.save_message(user_id="user_b", role="user", text="ICTコンサルティングの案件で、クライアントにAWS LambdaとDockerを使った構成のメリットを分かりやすく説明したいです。")
    time.sleep(0.5)
    repo.save_message(
        user_id="user_b", role="agent", 
        text="承知いたしました。非エンジニアの方へは「使った分だけ課金されるため無駄な維持費がかからない」「アクセス集中時に自動で対応できるのでシステムが止まりにくい」の2点を強調すると伝わりやすいです。インフラ管理の手間が省ける点も大きなアピールポイントですね。", 
        agent_id=it_agent["id"], agent_name="ITサポートエンジニア", theme_color=it_agent["theme_color"]
    )
    time.sleep(0.5)

    # 会話7: 作り置き (時短レシピクリエイター)
    recipe_agent = created_user_b_agents["時短レシピクリエイター"]
    repo.save_message(user_id="user_b", role="user", text="妻と共働きで忙しいので、休日のうちに平日の副菜を作り置きしたいです。日持ちして栄養がある簡単なレシピを教えてください。")
    time.sleep(0.5)
    repo.save_message(
        user_id="user_b", role="agent", 
        text="それなら「切り干し大根とツナの塩昆布和え」や「ピーマンの塩昆布ナムル」がおすすめです！どちらも火を使わずレンジや和えるだけで完成し、冷蔵庫で4〜5日持ちますよ。ミネラルも豊富で忙しい平日の強い味方です！", 
        agent_id=recipe_agent["id"], agent_name="時短レシピクリエイター", theme_color=recipe_agent["theme_color"]
    )

    print("🎉 デモ用データの完全初期化および再投入が完了しました！")

if __name__ == "__main__":
    run_seed_process()