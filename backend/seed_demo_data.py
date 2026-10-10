import uuid
import os
import time
from google import genai
from google.cloud import storage
from fastapi import APIRouter

# 💡 必須モジュール
from app.repositories.firestore_repo import FirestoreRepository
from app.services.embedding_service import EmbeddingService

router = APIRouter()

# 💡 画像生成クライアントの初期化 (us-central1 の gemini-2.5-flash-image を利用)
image_client = genai.Client(
    vertexai=True,
    project="certain-song-509313-d8",
    location="us-central1"
)

# GCS クライアントの初期化
storage_client = storage.Client()


def _ensure_default_avatar() -> str:
    """
    デフォルトアバターが存在するか確認し、なければ生成してURLを返す。
    """
    bucket_name = os.getenv("GCS_TEMP_BUCKET_NAME", "kaleido-demo-temp-assets")
    bucket = storage_client.bucket(bucket_name)
    file_name = "avatars/default_avatar.jpg"
    blob = bucket.blob(file_name)
    default_url = f"https://storage.googleapis.com/{bucket_name}/{file_name}"

    if blob.exists():
        return default_url

    print("🎨 デフォルトアバター画像を新規生成中...")
    prompt = (
        "A friendly, neutral AI assistant character mascot. Modern anime style, "
        "minimalist, clean pure white background, flat color, high quality, "
        "friendly robot or futuristic companion mascot. "
        "Strictly textless, pure illustration without any letters, numbers, logos, words, or watermarks."
    )

    try:
        response = image_client.models.generate_content(
            model='gemini-2.5-flash-image',
            contents=prompt
        )
        image_bytes = None
        if response.candidates and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    image_bytes = part.inline_data.data
                    break

        if image_bytes:
            blob.upload_from_string(image_bytes, content_type="image/jpeg")
            print(f"✅ デフォルトアバター作成完了: {default_url}")
            time.sleep(10)
            return default_url
    except Exception as e:
        print(f"⚠️ デフォルトアバターの生成に失敗しました: {e}")

    return default_url


def _get_or_create_demo_avatar(
    agent_id: str, 
    agent_name: str, 
    description: str, 
    default_avatar_url: str = None, 
    max_retries: int = 3
) -> str:
    """
    固定ファイル名 (avatars/{agent_id}.jpg) で管理し、
    GCSに既に存在していればスキップしてURLを返す。
    失敗時は default_avatar_url にフォールバックする。
    """
    if not default_avatar_url:
        default_avatar_url = _ensure_default_avatar()

    bucket_name = os.getenv("GCS_TEMP_BUCKET_NAME", "kaleido-demo-temp-assets")
    bucket = storage_client.bucket(bucket_name)

    file_name = f"avatars/{agent_id}.jpg"
    blob = bucket.blob(file_name)
    image_url = f"https://storage.googleapis.com/{bucket_name}/{file_name}"

    # 1. 既に存在している場合はスキップ
    if blob.exists():
        print(f"⏩ [{agent_name}] は既存のアバターを使用します: {image_url}")
        return image_url

    # 2. 文字を描画させないプロンプト設定
    prompt = (
        f"A professional anime-style full-body character illustration: {description}. "
        f"Clean white background, masterpiece, highest quality, flat colors, clear line art. "
        f"Textless, pure character visual only, absolutely no text, no words, no letters, no signs, no typography, no watermarks."
    )

    backoff_delays = [30, 60, 90]

    for attempt in range(1, max_retries + 1):
        try:
            print(f"🎨 [{agent_name}] のアバター画像を新規生成中 (Gemini 2.5 Flash Image, 試行 {attempt}/{max_retries})...")
            
            response = image_client.models.generate_content(
                model='gemini-2.5-flash-image',
                contents=prompt
            )

            image_bytes = None
            if response.candidates and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if part.inline_data:
                        image_bytes = part.inline_data.data
                        break
            
            if not image_bytes:
                print(f"⚠️ [{agent_name}] 画像バイトデータが取得できませんでした")
                continue

            blob.upload_from_string(image_bytes, content_type="image/jpeg")
            print(f"✅ 生成・アップロード完了: {image_url}")

            # レート制限予防のための待機
            time.sleep(15)
            return image_url

        except Exception as e:
            print(f"⚠️ 画像生成エラー ({agent_name}, 試行 {attempt}): {e}")
            if attempt < max_retries:
                wait_sec = backoff_delays[attempt - 1]
                print(f"⏳ レート制限(429)対策のため {wait_sec} 秒待機して再試行します...")
                time.sleep(wait_sec)

    print(f"⚠️ [{agent_name}] はデフォルトアバターに切り替えます: {default_avatar_url}")
    return default_avatar_url


def delete_collection_recursively(collection_ref):
    deleted_count = 0
    for doc in collection_ref.stream():
        for sub_collection in doc.reference.collections():
            delete_collection_recursively(sub_collection)
        doc.reference.delete()
        deleted_count += 1
    return deleted_count


def run_seed_process():
    repo = FirestoreRepository()
    embedder = EmbeddingService()
    db = repo.db

    print("🚀 デモ用初期データの投入（リセット）を開始します...")
    
    print("🗑️ 既存データを削除しています...")
    delete_collection_recursively(db.collection("agents"))
    target_user_ids = ["user_a", "user_b", "system", "test_user_01"]
    for uid in target_user_ids:
        user_doc_ref = db.collection("users").document(uid)
        for sub_collection in user_doc_ref.collections():
            delete_collection_recursively(sub_collection)
        user_doc_ref.delete()
    delete_collection_recursively(db.collection("users"))
    print("✨ データ削除完了。")

    # デモ共通のフォールバック用デフォルトアバターを準備
    default_avatar_url = _ensure_default_avatar()

    # 3. 共通エージェント
    system_agents = [
        {
            "id": "travel_planner_01",
            "name": "駅すぱあと経路検索エージェント",
            "description": "【重要：国内専用】日本の国内鉄道・バスなどの経路検索・乗り換え案内のみを担当する駅員風の専門家。台湾などの海外旅行の話題、一般的な旅行プランの相談、おすすめスポットの提案には絶対に対応しません。",
            "system_prompt": "あなたは駅すぱあとの経路検索ロジックを活用する交通案内の専門家です。日本の国内の駅や交通機関の経路検索のみを行ってください。海外旅行や一般的な観光プランの提案を求められた場合は「私は国内の経路検索専門ですので、新しいエージェントにご相談ください」と返答してください。※音声での会話用に、回答は最大でも150〜200文字程度（3〜4文）で短く簡潔にし、ユーザーと自然なキャッチボールをしてください。",
            "theme_color": "#E0F7FA",
            "voice_name": "ja-JP-Neural2-C",
            "user_id": "system"
        },
        {
            "id": "beauty_analyst_01",
            "name": "YouCam肌分析エージェント",
            "description": "YouCamのAI解析技術をベースに、肌質や骨格に合わせたメイクアップ、スキンケアの提案を行う白衣を着た専門家。",
            "system_prompt": "あなたはYouCamの肌診断技術を活用するビューティーアナリストです。美と健康に関する専門的なアドバイスを提供してください。※音声での会話用に、回答は最大でも150〜200文字程度（3〜4文）で短く簡潔にし、ユーザーと自然なキャッチボールをしてください。",
            "theme_color": "#FCE4EC",
            "voice_name": "ja-JP-Neural2-B",
            "user_id": "system"
        }
    ]

    for a in system_agents:
        embedding = embedder.generate_vector(a["description"], "RETRIEVAL_DOCUMENT")
        avatar_url = _get_or_create_demo_avatar(
            a["id"], a["name"], a["description"], default_avatar_url
        ) 
        repo.create_agent(
            agent_id=a["id"], name=a["name"], description=a["description"],
            system_prompt=a["system_prompt"], embedding=embedding,
            theme_color=a["theme_color"], voice_name=a["voice_name"], user_id=a["user_id"],
            avatar_url=avatar_url 
        )
        print(f"✅ 共通エージェント登録完了: {a['name']}")

    # 4. User B専用エージェント（💡 voice の Neural2-A を Neural2-B に修正）
    user_b_agents = [
        {"id": "user_b_it_support", "name": "ITサポートエンジニア", "desc": "PCトラブルやネットワーク設定を支援する技術者", "color": "#E8EAF6", "voice": "ja-JP-Neural2-C"},
        {"id": "user_b_fitness_trainer", "name": "熱血フィットネストレーナー", "desc": "サッカーのユニフォームを着て、自宅でできる自重トレーニングや食事管理を指導するコーチ", "color": "#FFEBEE", "voice": "ja-JP-Neural2-D"},
        {"id": "user_b_selfcare", "name": "セルフケアアドバイザー", "desc": "勉強や仕事の疲れを癒やすリフレッシュ方法を提案", "color": "#E8F5E9", "voice": "ja-JP-Neural2-B"}, # 💡 修正
        {"id": "user_b_aquarium", "name": "アクアリウム専門家", "desc": "熱帯魚の飼育や水槽のレイアウトをアドバイス", "color": "#E3F2FD", "voice": "ja-JP-Neural2-C"},
        {"id": "user_b_parenting", "name": "子育てコミュニケーション", "desc": "反抗期の子どもとの接し方や教育の悩みに寄り添う", "color": "#FFF3E0", "voice": "ja-JP-Neural2-B"},
        {"id": "user_b_asset_mgmt", "name": "資産運用コンサルタント", "desc": "NISAやiDeCoなど、初心者のための投資アドバイス", "color": "#FFF8E1", "voice": "ja-JP-Neural2-D"},
        {"id": "user_b_short_recipe", "name": "時短レシピクリエイター", "desc": "エプロン姿で忙しい日でも10分で作れる栄養満点の料理を提案", "color": "#FBE9E7", "voice": "ja-JP-Neural2-B"},
        {"id": "user_b_taiwan_gourmet", "name": "台湾グルメガイド", "desc": "台湾の夜市やローカルフードの美味しい楽しみ方を解説", "color": "#F3E5F5", "voice": "ja-JP-Neural2-B"},
        {"id": "user_b_sleep_improvement", "name": "睡眠改善インストラクター", "desc": "良質な睡眠をとるための環境づくりや習慣を指導", "color": "#EDE7F6", "voice": "ja-JP-Neural2-B"}, # 💡 修正
        {"id": "user_b_kyudo_analyst", "name": "弓道フォームアナリスト", "desc": "弓道着を着て、射法八節や手首の角度など、弓道の技術的指導を行う専門家", "color": "#F5F5F5", "voice": "ja-JP-Neural2-D"}
    ]

    created_user_b_agents = {}
    for a in user_b_agents:
        agent_id = a["id"]
        embedding = embedder.generate_vector(a["desc"], "RETRIEVAL_DOCUMENT")
        avatar_url = _get_or_create_demo_avatar(
            agent_id, a["name"], a["desc"], default_avatar_url
        ) 
        created_user_b_agents[a["name"]] = {
            "id": agent_id,
            "theme_color": a["color"],
            "voice_name": a["voice"],
            "avatar_url": avatar_url # 💡 チャット履歴用にも保持
        }
        
        repo.create_agent(
            agent_id=agent_id, name=a["name"], description=a["desc"],
            system_prompt=f"あなたは{a['name']}です。専門知識を活かして答えてください。※音声での会話用に、回答は最大でも150〜200文字程度（3〜4文）で短く簡潔にし、自然なキャッチボールをしてください。",
            embedding=embedding, theme_color=a["color"], voice_name=a["voice"], user_id="user_b",
            avatar_url=avatar_url 
        )
        print(f"✅ User Bエージェント登録完了: {a['name']}")

    # 5. User B の各エージェントとの一往復会話履歴を登録
    print("💬 User Bのチャット履歴（各専門家との1往復）を生成しています...")
    
    dialogues = [
        {
            "agent_name": "ITサポートエンジニア",
            "user_text": "Wi-Fiルーターを買い替えたんですが、奥の部屋だけ電波が届きにくいです。改善方法はありますか？",
            "agent_text": "ルーターの設置場所を床から1〜2mほど離し、壁や家電から離してみてください。それでも届きにくい場合は、メッシュWi-Fiの導入や中継機の追加が最も効果的ですよ！"
        },
        {
            "agent_name": "熱血フィットネストレーナー",
            "user_text": "平日の夜、家で短時間でできるおすすめのトレーニングはありますか？",
            "agent_text": "ナイスモチベーション！自重スクワットとプランクを組み合わせたサーキットが最高です。1回4分でも心拍数が上がって基礎代謝がしっかり向上しますよ。今日からすぐやってみましょう！"
        },
        {
            "agent_name": "セルフケアアドバイザー",
            "user_text": "デスクワークが続くと夕方に目が疲れて肩も重くなります。",
            "agent_text": "長時間の作業、お疲れ様です！ホットアイマスクや蒸しタオルで目元を温めつつ、肩甲骨を大きく回すストレッチを取り入れてみてください。1時間に一度深呼吸するだけでもリフレッシュできますよ。"
        },
        {
            "agent_name": "アクアリウム専門家",
            "user_text": "小型の水槽で初心者でも飼いやすい熱帯魚を教えてください。",
            "agent_text": "それならアカヒレやネオンテトラ、グッピーが水質変化に強く育てやすくておすすめです！まずは水草を少し入れて、バクテリアが定着するまでエサを与えすぎないのがコツですよ。"
        },
        {
            "agent_name": "子育てコミュニケーション",
            "user_text": "中学に入ってから子どもの口数が減って、どう接していいか悩みます。",
            "agent_text": "自立への大切な第一歩ですね。無理に聞き出そうとせず、「あなたの味方だよ」というサインだけ伝えて見守るのがベストです。話しかけてきた時は作業の手を止めて共感してあげてくださいね。"
        },
        {
            "agent_name": "資産運用コンサルタント",
            "user_text": "新NISAを始めたいのですが、初心者は何から選ぶのが無難ですか？",
            "agent_text": "まずは「つみたて投資枠」を使って、全世界株式（オール・カントリー）やS&P500に連動するインデックス投信を毎月定額で積み立てるのが王道で安心です。少額から無理なく始めましょう！"
        },
        {
            "agent_name": "時短レシピクリエイター",
            "user_text": "冷蔵庫に豚肉とキャベツしかありません。10分で作れるおかずはありますか？",
            "agent_text": "豚肉とキャベツの味噌バター炒めが絶品ですよ！フライパンで強火でザッと炒め、味噌・みりん・バターを絡めるだけでご飯が止まらないメインおかずの完成です！"
        },
        {
            "agent_name": "台湾グルメガイド",
            "user_text": "今度台湾に行く予定なんですが、おすすめの夜市と絶対食べるべきローカルフードを教えてください！",
            "agent_text": "台湾旅行ですね！初めてなら「士林夜市」や「饒河街夜市」がおすすめです。名物の大きなフライドチキン（大鶏排）や、胡椒餅は絶対に外せませんよ！"
        },
        {
            "agent_name": "睡眠改善インストラクター",
            "user_text": "夜中に何度も目が覚めてしまい、朝スッキリ起きられません。",
            "agent_text": "就寝90分前にお風呂で湯船に浸かり、深部体温を一度上げるのが効果的です。また、寝室の温度を20度前後に保ち、スマホの画面はベッドに入る30分前から控えてみてくださいね。"
        },
        {
            "agent_name": "弓道フォームアナリスト",
            "user_text": "離れのときに弓手が下がってしまう癖を直すにはどう意識すればいいですか？",
            "agent_text": "会（かい）の段階で肩甲骨をしっかり下ろし、左肩が詰まらないように伸び合うことが大切です。手先で押し出そうとせず、胸の中央から左右均等に割り開く意識を持つと弓手が安定しますよ。"
        }
    ]

    for d in dialogues:
        ag = created_user_b_agents[d["agent_name"]]
        repo.save_message(
            user_id="user_b", role="user", text=d["user_text"]
        )
        time.sleep(0.1)
        repo.save_message(
            user_id="user_b", role="agent", 
            text=d["agent_text"], 
            agent_id=ag["id"], 
            agent_name=d["agent_name"], 
            theme_color=ag["theme_color"],
            avatar_url=ag["avatar_url"] # 💡 アバターURLも履歴に含めて保存
        )
        time.sleep(0.1)

    print("🎉 デモ用データの完全初期化および投入が完了しました！")


if __name__ == "__main__":
    run_seed_process()