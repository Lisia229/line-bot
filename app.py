from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import *
import os
import sqlite3

app = Flask(__name__)
line_bot_api = LineBotApi(os.getenv("CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("CHANNEL_SECRET"))

# 初始化 SQLite 資料庫
def init_db():
    conn = sqlite3.connect("settings.db")
    c = conn.cursor()
    c.execute('''
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
    conn.close()

# 初始化該群設定
def init_group_settings(group_id):
    conn = sqlite3.connect("settings.db")
    c = conn.cursor()
    c.execute("SELECT group_id FROM group_settings WHERE group_id = ?", (group_id,))
    if not c.fetchone():
        c.execute('''
            INSERT INTO group_settings (group_id) VALUES (?)
        ''', (group_id,))
    conn.commit()
    conn.close()

# 更新設定
def update_setting(group_id, key, value):
    conn = sqlite3.connect("settings.db")
    c = conn.cursor()
    c.execute(f'''
        UPDATE group_settings SET {key} = ? WHERE group_id = ?
    ''', (1 if value else 0, group_id))
    conn.commit()
    conn.close()

# 取得設定
def get_group_status(group_id):
    conn = sqlite3.connect("settings.db")
    c = conn.cursor()
    c.execute("SELECT * FROM group_settings WHERE group_id = ?", (group_id,))
    row = c.fetchone()
    conn.close()
    return row

# 指令對應表
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
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"

# 確認是否為群組管理員
def is_group_admin(group_id, user_id):
    try:
        summary = line_bot_api.get_group_summary(group_id)
        profile = line_bot_api.get_group_member_profile(group_id, user_id)
        return hasattr(profile, "display_name")
    except:
        return False

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text.strip()
    source = event.source

    if source.type != "group":
        return

    user_id = source.user_id
    group_id = source.group_id

    init_group_settings(group_id)

    row = get_group_status(group_id)
    if row and row[7]:  # mention_protect index = 7
        try:
            if not is_group_admin(group_id, user_id):
                mentions = getattr(event.message.mention, "mentionees", [])
                if ("@所有人" in text or "@all" in text or len(mentions) >= 5):
                    line_bot_api.kickout_from_group(group_id, user_id)
                    return
        except:
            pass

    if not is_group_admin(group_id, user_id):
        return

    if text == "/help":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=HELP_TEXT))
        return

    if text == "/狀態":
        row = get_group_status(group_id)
        if not row:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="查無設定"))
            return
        keys = list(TOGGLE_MAP.values())
        status_lines = []
        for idx, key in enumerate(keys):
            name = [k for k, v in TOGGLE_MAP.items() if v == key][0]
            emoji = "✅" if row[idx + 1] else "❌"
            status_lines.append(f"{emoji} {name}")
        result = "\n".join(status_lines)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=result))
        return

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
    joined_users = event.joined.members
    group_id = event.source.group_id

    for user in joined_users:
        if user.type == "user":
            try:
                profile = line_bot_api.get_group_member_profile(group_id, user.user_id)
                display_name = profile.display_name
            except:
                display_name = "使用者"

            welcome_text = (
                f"{display_name} 歡迎加入熊賀勝群組，原籤一番賞&自制一番賞配率都在相簿呦🥳\n"
                "群組會有便宜的集單、盲盒的預購、不定時免費抽獎🥳\n"
                "群組也會公告休息時間、新的一番賞&新的盲盒到貨通知呦🎊\n\n"
                "🐻新加入的朋友如果覺得老闆服務的不錯，價格也親民，歡迎幫我追蹤臉書粉絲專頁：\n"
                "https://www.facebook.com/profile.php?id=100095394499752&mibextid=LQQJ4d\n\n"
                "有空的話也歡迎到 Google 地圖幫「熊賀勝」評論 5 顆星星⭐️\n\n"
                "感謝大家的支持與愛待😊\n\n"
                "有任何問題歡迎找 @熊賀勝-小胡 🫡"
            )

            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=welcome_text)
            )

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)