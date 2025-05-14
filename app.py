from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import *
import os
import firebase_admin
from firebase_admin import credentials, firestore
import json

# 初始化 Firebase（只執行一次）
if not firebase_admin._apps:
    cred_dict = json.loads(os.environ["FIREBASE_CREDENTIALS"])
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred)

db = firestore.client()

# 初始化 Flask 與 LINE Bot
app = Flask(__name__)
line_bot_api = LineBotApi(os.getenv("CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("CHANNEL_SECRET"))

# 預設群組設定
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

# 管理員清單（用戶 ID）
ADMIN_USER_IDS = [
    "U149f4e039b2911dea1f3b6d6329af835"
]

def is_group_admin(group_id, user_id):
    return user_id in ADMIN_USER_IDS

# 初始化群組設定
def init_group_settings(group_id):
    doc_ref = db.collection("group_settings").document(group_id)
    if not doc_ref.get().exists:
        doc_ref.set(DEFAULT_SETTINGS)

# 更新某個設定項目
def update_setting(group_id, key, value):
    db.collection("group_settings").document(group_id).update({key: 1 if value else 0})

# 取得群組狀態
def get_group_status(group_id):
    doc = db.collection("group_settings").document(group_id).get()
    return doc.to_dict() if doc.exists else None

# 指令對應
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

    if text == "/id":
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=f"你的 User ID 是：{user_id}")
        )
        return

    # 保護機制
    if row:
        def warn_and_notify(reason):
            warning_msg = f"⚠️ 你觸犯了群組規則：{reason}，請注意行為。"
            admin_msg = f"👮 管理通知：使用者 {user_id} 在群組 {group_id} 觸犯了「{reason}」"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=warning_msg))
            for admin_id in ADMIN_USER_IDS:
                try:
                    line_bot_api.push_message(admin_id, TextSendMessage(text=admin_msg))
                except:
                    pass

        if row.get("mention_protect", 0):
            if not is_group_admin(group_id, user_id):
                try:
                    mentions = getattr(event.message.mention, "mentionees", [])
                    if "@所有人" in text or "@all" in text or len(mentions) >= 5:
                        warn_and_notify("全體標記保護")
                        return
                except:
                    pass

        if row.get("invite_link_protect", 0) and "line.me/R/ti/g/" in text:
            if not is_group_admin(group_id, user_id):
                warn_and_notify("邀請網址保護")
                return

        if row.get("note_protect", 0) and "記事本" in text:
            if not is_group_admin(group_id, user_id):
                warn_and_notify("記事本保護")
                return

        if row.get("album_protect", 0) and "相簿" in text:
            if not is_group_admin(group_id, user_id):
                warn_and_notify("相簿保護")
                return

    # 僅限管理員操作
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
        status_lines = []
        for display, key in TOGGLE_MAP.items():
            emoji = "✅" if row.get(key, 0) else "❌"
            status_lines.append(f"{emoji} {display}")
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

# 處理貼圖事件（洗版保護）
@handler.add(StickerMessage)
def handle_sticker(event):
    source = event.source
    if source.type != "group":
        return
    group_id = source.group_id
    user_id = source.user_id

    row = get_group_status(group_id)
    if row and row.get("sticker_protect", 0):
        if not is_group_admin(group_id, user_id):
            warning_msg = "⚠️ 請勿洗貼圖，已通知管理員審查。"
            admin_msg = f"👮 貼圖洗版警告：使用者 {user_id} 在群組 {group_id} 洗貼圖"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=warning_msg))
            for admin_id in ADMIN_USER_IDS:
                try:
                    line_bot_api.push_message(admin_id, TextSendMessage(text=admin_msg))
                except:
                    pass

# 成員加入歡迎訊息
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

# 啟動伺服器
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
