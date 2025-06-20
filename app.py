from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from linebot.models import *
import os
import sqlite3

# 初始化 Flask 與資料庫
app = Flask(__name__)

@app.route('/')
# UptimeRobot 機器人呼叫
def index():
    return 'LINE Bot 正常運作中'

DB_PATH = "group_settings.db"
DEFAULT_SETTINGS = {
    "kick_protect": 0,
    "invite_protect": 0,
    "name_image_protect": 0,
    "invite_link_protect": 0,
    "note_protect": 0,
    "album_protect": 0,
    "mention_protect": 0,
    "sticker_protect": 0
}

GROUP_NAME_MAP = {
    "C4a0b94700721b72b0c2a32fd60ddccaa": "熊賀勝"
    }

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS group_settings (
                group_id TEXT PRIMARY KEY,
                kick_protect INTEGER DEFAULT 0,
                invite_protect INTEGER DEFAULT 0,
                name_image_protect INTEGER DEFAULT 0,
                invite_link_protect INTEGER DEFAULT 0,
                note_protect INTEGER DEFAULT 0,
                album_protect INTEGER DEFAULT 0,
                mention_protect INTEGER DEFAULT 0,
                sticker_protect INTEGER DEFAULT 0
            )
        ''')
        conn.commit()

init_db()  # ← Heroku 啟動時也會執行這個

# 初始化 LINE Bot
line_bot_api = LineBotApi(os.getenv("CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("CHANNEL_SECRET"))

# 管理員清單（User ID）
ADMIN_USER_IDS = [
    "U149f4e039b2911dea1f3b6d6329af835"
]

def init_group_settings(group_id):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM group_settings WHERE group_id = ?", (group_id,))
        if not cursor.fetchone():
            cursor.execute('''
                INSERT INTO group_settings (
                    group_id, kick_protect, invite_protect, name_image_protect,
                    invite_link_protect, note_protect, album_protect,
                    mention_protect, sticker_protect
                ) VALUES (?, 0, 0, 0, 0, 0, 0, 0, 0)
            ''', (group_id,))
            conn.commit()

def update_setting(group_id, key, value):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(f'''
            UPDATE group_settings SET {key} = ? WHERE group_id = ?
        ''', (1 if value else 0, group_id))
        conn.commit()

def get_group_status(group_id):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM group_settings WHERE group_id = ?", (group_id,))
        row = cursor.fetchone()
        if row:
            keys = [description[0] for description in cursor.description]
            return dict(zip(keys, row))
        else:
            init_group_settings(group_id)
            return DEFAULT_SETTINGS.copy()

def is_group_admin(group_id, user_id):
    return user_id in ADMIN_USER_IDS

TOGGLE_MAP = {
    "踢人保護": "kick_protect",
    "邀請保護": "invite_protect",
    "群名保護": "name_image_protect",
    "群圖保護": "name_image_protect",
    "邀請網址保護": "invite_link_protect",
    "記事本保護": "note_protect",
    "相簿保護": "album_protect",
    "全體標記保護": "mention_protect",
    "貼圖洗版保護": "sticker_protect",
}

HELP_TEXT = '''🔐 保護功能指令清單（限管理員）：
✅ 使用方式：
  群內輸入「功能名稱 開」或「功能名稱 關」
🧾 範例：
  踢人保護 開
  貼圖洗版保護 關
📊 查看目前狀態：
  /狀態

🔧 支援的功能：
- 踢人保護
- 邀請保護
- 群名保護 / 群圖保護
- 邀請網址保護
- 記事本保護
- 相簿保護
- 全體標記保護
- 貼圖洗版保護
'''

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", None)
    body = request.get_data(as_text=True)
    print(f"signature: {signature}")
    print(f"body: {body}")
    print(f"CHANNEL_SECRET: {os.getenv('CHANNEL_SECRET')}")
    try:
        handler.handle(body, signature)
    except InvalidSignatureError as e:
        print("InvalidSignatureError:", e)
        abort(400)
    return "OK"


@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    print("收到訊息:", event)
    print("訊息文字:", event.message.text)
    print("來自:", event.source.type)

    text = event.message.text.strip()
    source = event.source

    if source.type != "group":
        return

    user_id = source.user_id
    group_id = source.group_id
    profile = line_bot_api.get_group_member_profile(group_id, user_id)
    user_name = profile.display_name

    init_group_settings(group_id)
    row = get_group_status(group_id)

    def warn_and_notify(user_id, group_id, user_name, reason):
        warning_msg = f"⚠️ {user_name} 觸犯了群組規則：{reason}，請注意行為。"
        admin_msg = f"👮 管理通知：使用者 {user_name} 在群組 {GROUP_NAME_MAP.get(group_id, group_id)} 觸犯了「{reason}」"
        # 一次用 reply_message 回覆警告訊息
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=warning_msg)
        )
        # 用 push_message 通知管理員
        for admin_id in ADMIN_USER_IDS:
            line_bot_api.push_message(admin_id, TextSendMessage(text=admin_msg))

    # 指令：/id
    if text == "/id":
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=f"你的 User ID 是：{user_id}")
        )
        return

    # 指令：/踢我（非管理員可踢自己）
    if text == "/踢我":
        if not is_group_admin(group_id, user_id):
            try:
                # 先回覆，再踢人（注意這樣會有 reply_token 用兩次的問題，可用 push_message 替代）
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🥾 你請求被踢，我就踢！掰～"))
                line_bot_api.kickout_group_member(group_id, user_id)
                print(f"使用者 {user_id} 已被踢出群組 {group_id}")
            except Exception as e:
                print(f"踢出失敗：{e}")
                # 踢出失敗改用 push_message 通知管理員
                for admin_id in ADMIN_USER_IDS:
                    line_bot_api.push_message(admin_id, TextSendMessage(text=f"❌ 踢出失敗，原因：{e}"))
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="你是管理員，不能自踢啦 😎"))
        return

    # 處理 @all 警告與踢出
    if "@all" in text.lower():
        if not is_group_admin(group_id, user_id):
            try:
                warn_and_notify(user_id, group_id, user_name, "未經授權使用 標記全體")
                print(f"非管理員使用 @all，準備踢出：{user_id}")
                line_bot_api.kickout_group_member(group_id, user_id)
            except Exception as e:
                print(f"踢出失敗：{e}")
                # 因 reply_token 只能用一次，改用 push_message 通知管理員
                for admin_id in ADMIN_USER_IDS:
                    line_bot_api.push_message(admin_id, TextSendMessage(text=f"❌ 無法踢出，原因：{e}"))
            return

    # 指令：/help
    if text == "/help":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=HELP_TEXT))
        return

    # 指令：/狀態
    if text == "/狀態":
        status_lines = []
        for display, key in TOGGLE_MAP.items():
            emoji = "✅" if row.get(key, 0) else "❌"
            status_lines.append(f"{emoji} {display}")
        result = "\n".join(status_lines)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=result))
        return

    # 指令：功能 開/關
    for display, key in TOGGLE_MAP.items():
        if text == f"{display} 開":
            update_setting(group_id, key, True)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"✅ {display} 已開啟"))
            return
        elif text == f"{display} 關":
            update_setting(group_id, key, False)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"❌ {display} 已關閉"))
            return

@handler.add(MemberJoinedEvent)
def handle_member_joined(event):
    group_id = event.source.group_id
    for user in event.joined.members:
        if user.type == "user":
            try:
                profile = line_bot_api.get_group_member_profile(group_id, user.user_id)
                display_name = profile.display_name
            except:
                display_name = "使用者"

            welcome_text = (
                f"{display_name} 歡迎加入熊赫勝群組，原籤一番購&自制一番購配率都在相簿器喔🥳\n"
                "群組會有便宜的集單、盲盒的預購、不定時免費抽獎🥳\n"
                "群組也會公告休息時間、新的一番購&新的盲盒到貨通知喔🎉\n\n"
                "🐻新加入的朋友如果覺得老闆服務的不錯，價格也觀測，歡迎幫我追蹤臉書粉絲專頁：\n"
                "https://www.facebook.com/profile.php?id=100095394499752&mibextid=LQQJ4d\n\n"
                "有空的話也歡迎到 Google 地圖幫「熊赫勝」評論 5 顆星星⭐️\n\n"
                "感謝大家的支持與愛待😊\n\n"
                "有任何問題歡迎找 @熊赫勝-小胡 🢪"
            )

            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=welcome_text)
            )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

