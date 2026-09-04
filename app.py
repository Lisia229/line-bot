from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    MemberJoinedEvent, FlexSendMessage
)
import os
import sqlite3
import random
import re

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

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bot_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')

        default_settings = {
            "business_hours": "下午2:00~晚上8:00",
            "shop_address": "高雄市三民區信國路32號",
            "fb_link": "https://facebook.com/",
            "shopee_link": "https://shopee.tw/",
            "shop_announcement": "目前沒有公告"
        }

        for key, value in default_settings.items():
            cursor.execute('''
                INSERT OR IGNORE INTO bot_settings (key, value)
                VALUES (?, ?)
            ''', (key, value))

        conn.commit()

init_db()  # ← Heroku 啟動時也會執行這個

# 初始化 LINE Bot
line_bot_api = LineBotApi(os.getenv("CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("CHANNEL_SECRET"))

# 管理員清單（User ID）
ADMIN_USER_IDS = [
    "U149f4e039b2911dea1f3b6d6329af835", "U99c0c99890375b70599760c76eb958c9"
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
def get_setting(key):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT value FROM bot_settings WHERE key=?",
            (key,)
        )

        row = cursor.fetchone()

        if row:
            return row[0]

        return None


def set_setting(key, value):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()

        cursor.execute('''
            INSERT OR REPLACE INTO bot_settings (key, value)
            VALUES (?, ?)
        ''', (
            key,
            value
        ))

        conn.commit()
        
def set_business_hours(hours):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()

        cursor.execute('''
            INSERT OR REPLACE INTO bot_settings (key, value)
            VALUES (?, ?)
        ''', (
            "business_hours",
            hours
        ))

        conn.commit()
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
    lower_text = text.lower()
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
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=warning_msg))
        for admin_id in ADMIN_USER_IDS:
            line_bot_api.push_message(admin_id, TextSendMessage(text=admin_msg))

    if text == "/id":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"你的 User ID 是：{user_id}"))
        return

    if text == "/踢我":
        if not is_group_admin(group_id, user_id):
            try:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🥾 你請求被踢，我就踢！掰～"))
                line_bot_api.kickout_group_member(group_id, user_id)
            except Exception as e:
                for admin_id in ADMIN_USER_IDS:
                    line_bot_api.push_message(admin_id, TextSendMessage(text=f"❌ 踢出失敗，原因：{e}"))
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="你是管理員，不能自踢啦 😎"))
        return

    if "@all" in lower_text:
        if not is_group_admin(group_id, user_id):
            try:
                warn_and_notify(user_id, group_id, user_name, "未經授權使用 標記全體")
                line_bot_api.kickout_group_member(group_id, user_id)
            except Exception as e:
                for admin_id in ADMIN_USER_IDS:
                    line_bot_api.push_message(admin_id, TextSendMessage(text=f"❌ 無法踢出，原因：{e}"))
            return
        
    # ✅ 支援「幫我在1-80之間選5個數字」這種句子
    match = re.search(
        r"幫我在\s*(\d+)\s*[-~～至到－—]\s*(\d+)\s*之間選\s*(\d+)\s*個數字",
        text
    )
    if match:
        low, high, count = (int(match.group(i)) for i in range(1, 4))
        if low > high:
            low, high = high, low
        range_size = high - low + 1
        if count < 1 or count > range_size:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"❌ 數字個數要在 1~{range_size} 之間喔")
            )
            return
        numbers = random.sample(range(low, high + 1), count)
        result = "、".join(str(n) for n in numbers)
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=f"我幫你選的是：{result}")
        )
        return


    if "幫我選個數字" in text:
        number = random.randint(1, 80)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"我幫你選的是：{number}"))
        return

    if "要洗嗎" in text:
        if random.choice([True, False]):
            answer = "不洗直上"
        else:
            answer = f"洗 {random.randint(1, 10)} 下"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=answer))
        return

    if text.startswith("/設定地址 "):

        if not is_group_admin(group_id, user_id):
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="❌ 非管理員無法更改地址")
            )
            return

        value = text.replace("/設定地址 ", "").strip()

        set_setting("shop_address", value)

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(
                text=f"✅ 地址已更新\n\n{value}"
            )
        )
        return
    
    if text.startswith("/設定FB "):

        if not is_group_admin(group_id, user_id):
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="❌ 非管理員無法更改 FB")
            )
            return

        value = text.replace("/設定FB ", "").strip()

        set_setting("fb_link", value)

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(
                text="✅ FB 連結已更新"
            )
        )
        return
    
    if text.startswith("/設定蝦皮 "):

        if not is_group_admin(group_id, user_id):
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="❌ 非管理員無法更改蝦皮")
            )
            return

        value = text.replace("/設定蝦皮 ", "").strip()

        set_setting("shopee_link", value)

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(
                text="✅ 蝦皮連結已更新"
            )
        )
        return
    
    if text.startswith("/設定公告 "):

        if not is_group_admin(group_id, user_id):
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="❌ 非管理員無法更改公告")
            )
            return

        value = text.replace("/設定公告 ", "").strip()

        set_setting("shop_announcement", value)

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(
                text=f"📢 公告已更新\n\n{value}"
            )
        )
        return
        
    if text.startswith("/設定營業時間 "):

        if not is_group_admin(group_id, user_id):
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="❌ 非管理員無法更改營業時間")
            )
            return

        value = text.replace("/設定營業時間 ", "").strip()

        set_setting("business_hours", value)

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(
                text=f"✅ 營業時間已更新\n\n{value}"
            )
        )
        return
    
    # 📢 公告
    if any(kw in lower_text for kw in ["公告", "最新消息"]):

        reply_text = (
            f"📢 最新公告\n\n"
            f"{get_setting('shop_announcement')}"
        )

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )

        return
    

    if text == "/help":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=HELP_TEXT))
        return

    if text == "/狀態":
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

    # 📍 地址查詢
    if any(kw in lower_text for kw in ["地址", "熊賀勝地址", "在哪裡"]):
        reply_text = (
            "您好～熊賀勝的地址在：\n"
            f"📍 {get_setting('shop_address')}"
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
        return

    # 🕒 營業時間
    if any(kw in lower_text for kw in ["營業", "營業時間"]):
        reply_text = f"營業時間：{get_setting('business_hours')}"
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )
        return

    # 📣 追蹤卡片
    if any(kw in lower_text for kw in ["追蹤", "粉絲", "蝦皮", "fb"]):
        fb_bubble = {
            "type": "bubble",
            "hero": {
                "type": "image",
                "url": "https://scontent.ftpe8-2.fna.fbcdn.net/v/t39.30808-6/493687872_9649486425130129_4145194897754717464_n.jpg?_nc_cat=101&ccb=1-7&_nc_sid=cc71e4&_nc_ohc=AG6m_6XrNG8Q7kNvwFpiAF0&_nc_oc=Adk_Z2QXA5sO0zt8iZ6l5n261H8JDAoFyqCCG_uwL5nkmzXnQntqelWYs2J8Wm0TPfw&_nc_zt=23&_nc_ht=scontent.ftpe8-2.fna&_nc_gid=3e5vz6t8yyzOkO2sPrjnRg&oh=00_AfP2K4tWu6Scko4Ly0PZWA4wqQzfGnWKR-4yFSoHz6PQqA&oe=6861A47A",
                "size": "full",
                "aspectMode": "cover",
                "aspectRatio": "320:213"
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "paddingAll": "13px",
                "contents": [
                    {"type": "text", "text": "粉絲專頁", "size": "xs", "color": "#aaaaaa", "wrap": True},
                    {"type": "text", "text": "追蹤熊賀勝 Facebook", "weight": "bold", "size": "sm", "wrap": True},
                    {"type": "text", "text": "點我查看最新商品與活動公告", "size": "xs", "color": "#666666", "wrap": True}
                ]
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    {
                        "type": "button",
                        "style": "link",
                        "height": "sm",
                        "action": {
                            "type": "uri",
                            "label": "前往 Facebook",
                            "uri": get_setting("fb_link")
                        }
                    }
                ],
                "flex": 0
            }
        }

        shopee_bubble = {
            "type": "bubble",
            "hero": {
                "type": "image",
                "url": "https://down-aka-tw.img.susercontent.com/tw-11134233-7rasd-m4lencedlku8d0_tn.webp",
                "size": "full",
                "aspectMode": "cover",
                "aspectRatio": "320:213"
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "paddingAll": "13px",
                "contents": [
                    {"type": "text", "text": "蝦皮商城", "size": "xs", "color": "#aaaaaa", "wrap": True},
                    {"type": "text", "text": "在蝦皮上找到熊賀勝！", "weight": "bold", "size": "sm", "wrap": True},
                    {"type": "text", "text": "不定時更新商品到蝦皮喔！", "size": "xs", "color": "#666666", "wrap": True}
                ]
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    {
                        "type": "button",
                        "style": "link",
                        "height": "sm",
                        "action": {
                            "type": "uri",
                            "label": "前往蝦皮",
                            "uri": get_setting("shopee_link")
                        }
                    }
                ],
                "flex": 0
            }
        }

        carousel = {
            "type": "carousel",
            "contents": [fb_bubble, shopee_bubble]
        }

        line_bot_api.reply_message(
            event.reply_token,
            FlexSendMessage(alt_text="追蹤熊賀勝", contents=carousel)
        )
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
                f"{display_name} 歡迎加入熊賀勝群組，原籤一番賞&自制一番賞配率都在相簿呦🥳\n"
                "群組會有便宜的集單、盲盒的預購不定時免費抽獎🥳\n"
                "群組也會公告休息時間、新的一番賞&新的盲盒到貨通知呦🎊\n\n"
                "🐻新加入的朋友如果覺得老闆服務的不錯，價格也親民，歡迎幫我追蹤臉書粉絲專頁：\n"
                "https://www.facebook.com/profile.php?id=100095394499752&mibextid=LQQJ4d\n\n"
                "有空的話也歡迎到Google地圖幫「熊賀勝」評論5顆星星⭐️\n\n"
                "感謝大家的支持與愛待😊\n\n"
                "有任何問題歡迎找 @熊賀勝-小胡"
            )

            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=welcome_text)
            )
            



if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

