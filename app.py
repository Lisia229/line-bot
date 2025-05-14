from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import *
import os

app = Flask(__name__)

line_bot_api = LineBotApi(os.getenv("CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("CHANNEL_SECRET"))

# 管理員 LINE User ID（可加入多位）
admin_users = ["你的LINE_USER_ID"]

# 群組保護設定（存在記憶體）
group_settings = {}

# 初始化某個群組的預設設定
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

# 回傳當前狀態文字
def get_status_text(group_id):
    settings = group_settings[group_id]
    status_lines = []
    for key, value in settings.items():
        emoji = "✅" if value else "❌"
        name = {
            "kick_protect": "踢人保護",
            "invite_protect": "邀請保護",
            "name_image_protect": "群名/群圖保護",
            "invite_link_protect": "邀請網址保護",
            "note_protect": "記事本保護",
            "album_protect": "相簿保護",
            "mention_protect": "全體標記保護",
            "sticker_protect": "貼圖洗版保護",
        }[key]
        status_lines.append(f"{emoji} {name}")
    return "\n".join(status_lines)

# 接收 webhook
@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"

# 處理文字訊息
@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    text = event.message.text.strip()
    source = event.source
    user_id = source.user_id
    group_id = source.group_id if source.type == "group" else None

    if not group_id:
        return  # 只處理群組訊息

    init_group_settings(group_id)

    if user_id not in admin_users:
        return  # 非管理員無操作權

    # 保護項目對應表
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

    # 狀態查詢
    if text == "/狀態":
        status = get_status_text(group_id)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=status))
        return

    # 開/關 指令解析
    for name, key in toggle_map.items():
        if text == f"{name} 開":
            group_settings[group_id][key] = True
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"✅ {name} 已開啟"))
            return
        elif text == f"{name} 關":
            group_settings[group_id][key] = False
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"❌ {name} 已關閉"))
            return
          
@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    user_id = event.source.user_id
    print("User ID:", user_id)  # 部署後看 log 取得
    ...
