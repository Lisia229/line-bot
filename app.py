from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import *
import os

app = Flask(__name__)

line_bot_api = LineBotApi(os.getenv("CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("CHANNEL_SECRET"))

# ✅ 管理員 LINE User ID（你的 ID）
admin_users = ["U149f4e039b2911dea1f3b6d6329af835"]

# ✅ 群組保護設定（存在記憶體）
group_settings = {}

# 初始化群組預設設定
def init_group_settings(group_id):
    if group_id not in group_settings:
        group_settings[group_id] = {
            "kick_protect": False,
            "invite_protect": False,
            "name_image_protect": False,
            "invite_link_protect": False,
            "note_protect": False,
            "album_protect": False,
            "mention_protect": False,
            "sticker_protect": False,
        }

# 狀態查詢
def get_status_text(group_id):
    settings = group_settings[group_id]
    display_names = {
        "kick_protect": "踢人保護",
        "invite_protect": "邀請保護",
        "name_image_protect": "群名/群圖保護",
        "invite_link_protect": "邀請網址保護",
        "note_protect": "記事本保護",
        "album_protect": "相簿保護",
        "mention_protect": "全體標記保護",
        "sticker_protect": "貼圖洗版保護",
    }
    status_lines = []
    for key, val in settings.items():
        emoji = "✅" if val else "❌"
        status_lines.append(f"{emoji} {display_names[key]}")
    return "\n".join(status_lines)

# Webhook 路由
@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"

# 處理訊息事件
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text.strip()
    source = event.source
    user_id = source.user_id
    group_id = source.group_id if source.type == "group" else None

    print("User ID:", user_id)  # 印出使用者 ID（第一次抓取時用）

    if not group_id:
        return  # 只處理群組訊息

    init_group_settings(group_id)

    if user_id not in admin_users:
        return  # 不是管理員

    # 指令映射
    toggle_map = {
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

    # 查詢狀態
    if text == "/狀態":
        status = get_status_text(group_id)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=status))
        return

    # 開 / 關 指令處理
    for name, key in toggle_map.items():
        if text == f"{name} 開":
            group_settings[group_id][key] = True
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"✅ {name} 已開啟"))
            return
        elif text == f"{name} 關":
            group_settings[group_id][key] = False
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"❌ {name} 已關閉"))
            return

# 本地端測試用
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
