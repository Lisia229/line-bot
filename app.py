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
import json
from urllib.parse import parse_qs, quote, urlparse

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
FLY_USER_ID = "Ue49ea57203993d7f8bb644aa4303f8d7"
FLY_AUTO_REPLIES = (
    "你一開口，我就知道這群組今天又沒辦法安靜了。",
    "你先別急著說話，讓腦袋追上來。",
    "這句話你想了多久？怎麼看起來完全沒想過。",
    "本來想反駁你，後來發現你已經自己完成了。",
    "收到，已列入本日沒人問排行榜。",
    "你這個發言，很適合留在草稿裡。",
    "你是不是把群組當成自己的限時動態了？",
    "好消息：你有發言。壞消息：我們有看到。",
    "你的自信如果能分我一點，我早就去選總統了。",
    "你不是沒重點，你是很努力地避開重點。",
    "謝謝分享，我先假裝沒看到，給你一次機會。",
    "這麼多字，竟然沒有一句是我需要知道的。",
    "你先撤回，我們就當彼此還是朋友。",
    "你的通知比你本人還勤勞。",
    "你這個幽默，我可能要更新系統才接得到。",
    "你負責講，我們負責在其他群組討論。",
    "這句話值得截圖，等你清醒再給你看。",
    "你今天是不是又忘記把內心話設成靜音？",
    "你有考慮過打完字之後，不按送出嗎？",
    "看得出來你很努力，雖然不知道在努力什麼。",
)
FLY_AUTO_REPLY_QUEUE = []
FLY_LAST_AUTO_REPLY = None


def get_fly_auto_reply():
    global FLY_LAST_AUTO_REPLY

    if not FLY_AUTO_REPLY_QUEUE:
        FLY_AUTO_REPLY_QUEUE.extend(FLY_AUTO_REPLIES)
        random.shuffle(FLY_AUTO_REPLY_QUEUE)
        if FLY_AUTO_REPLY_QUEUE[-1] == FLY_LAST_AUTO_REPLY:
            FLY_AUTO_REPLY_QUEUE[0], FLY_AUTO_REPLY_QUEUE[-1] = (
                FLY_AUTO_REPLY_QUEUE[-1], FLY_AUTO_REPLY_QUEUE[0]
            )

    FLY_LAST_AUTO_REPLY = FLY_AUTO_REPLY_QUEUE.pop()
    return FLY_LAST_AUTO_REPLY

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

MAX_ICHIBAN_LISTINGS = 10


def get_ichiban_listings():
    value = get_setting("ichiban_listings")
    if not value:
        return []
    try:
        listings = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    return listings if isinstance(listings, list) else []


def save_ichiban_listings(listings):
    set_setting("ichiban_listings", json.dumps(listings, ensure_ascii=False))


def normalize_ichiban_image_url(image_url):
    parsed_url = urlparse(image_url)
    if parsed_url.hostname not in {
        "drive.google.com",
        "www.drive.google.com",
        "drive.usercontent.google.com",
    }:
        return image_url

    file_id = parse_qs(parsed_url.query).get("id", [None])[0]
    if not file_id:
        match = re.search(r"/file/d/([^/]+)", parsed_url.path)
        file_id = match.group(1) if match else None
    if not file_id:
        return image_url

    return f"https://drive.usercontent.google.com/download?id={quote(file_id)}&export=view"


def parse_ichiban_prize_fields(value):
    fields = [field.strip() for field in value.split("|")]
    if len(fields) != 6:
        return None

    title, image_url, aspect_ratio, play_one, play_two, remaining = fields
    image_url = normalize_ichiban_image_url(image_url)
    image_parsed = urlparse(image_url)
    ratio_match = re.fullmatch(r"([1-9]\d{0,3}):([1-9]\d{0,3})", aspect_ratio)
    if (
        not title or not play_one or not play_two or not remaining
        or not ratio_match
        or image_parsed.scheme != "https" or not image_parsed.netloc
    ):
        return None

    return {
        "title": title,
        "image_url": image_url,
        "aspect_ratio": aspect_ratio,
        "play_one": play_one,
        "play_two": play_two,
        "remaining": remaining,
    }


def build_ichiban_bubble(listing):
    return {
        "type": "bubble",
        "hero": {
            "type": "image",
            "url": normalize_ichiban_image_url(listing["image_url"]),
            "size": "full",
            "aspectMode": "cover",
            "aspectRatio": listing["aspect_ratio"],
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "sm",
            "contents": [
                {"type": "text", "text": listing["title"], "weight": "bold", "size": "md", "wrap": True},
                {"type": "text", "text": f"玩法一：{listing['play_one']}", "size": "sm", "wrap": True},
                {"type": "text", "text": f"玩法二：{listing['play_two']}", "size": "sm", "wrap": True},
                {"type": "text", "text": listing["remaining"], "weight": "bold", "size": "sm", "color": "#C7473A", "wrap": True},
            ],
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "contents": [{
                "type": "text",
                "text": "詳細配率請至群組相簿查看",
                "size": "sm",
                "color": "#666666",
                "align": "center",
                "wrap": True,
            }],
        },
    }

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

🎟 一番賞 Bubble（限管理員，欄位以 | 分隔）：
/一番賞新增 標題|圖片網址|比例|玩法一|玩法二|剩餘抽數
/一番賞修改 編號|標題|圖片網址|比例|玩法一|玩法二|剩餘抽數
/一番賞刪除 編號
/一番賞列表
/今日一番賞推薦
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

    if user_id == "U99c0c99890375b70599760c76eb958c9" and "開店" in text:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="老闆終於起床上班了")
        )
        return

    if user_id == FLY_USER_ID:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=get_fly_auto_reply())
        )
        return

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

    if text.startswith(("/一番賞新增 ", "/一番賞修改 ", "/一番賞刪除 ", "/一番賞列表", "/今日一番賞推薦")):
        if not is_group_admin(group_id, user_id):
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="❌ 只有管理員可以管理或發送一番賞")
            )
            return

    if text.startswith("/一番賞新增 "):
        listings = get_ichiban_listings()
        if len(listings) >= MAX_ICHIBAN_LISTINGS:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="❌ 最多只能設定 10 款一番賞")
            )
            return

        listing = parse_ichiban_prize_fields(text[len("/一番賞新增 "):])
        if listing is None:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="❌ 格式錯誤。請依序提供：標題|圖片網址|比例|玩法一|玩法二|剩餘抽數；圖片網址需為 HTTPS 且開放連結檢視。")
            )
            return

        listings.append(listing)
        save_ichiban_listings(listings)
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=f"✅ 已新增第 {len(listings)} 款：{listing['title']}")
        )
        return

    if text.startswith("/一番賞修改 "):
        try:
            index_text, listing_text = text[len("/一番賞修改 "):].split("|", 1)
            listing_index = int(index_text.strip()) - 1
        except ValueError:
            listing_index = -1
            listing_text = ""

        listings = get_ichiban_listings()
        if not 0 <= listing_index < len(listings):
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="❌ 編號無效，請先用 /一番賞列表 查看編號")
            )
            return

        listing = parse_ichiban_prize_fields(listing_text)
        if listing is None:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="❌ 格式錯誤。請提供：編號|標題|圖片網址|比例|玩法一|玩法二|剩餘抽數；圖片網址需為 HTTPS 且開放連結檢視。")
            )
            return

        listings[listing_index] = listing
        save_ichiban_listings(listings)
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=f"✅ 第 {listing_index + 1} 款已更新：{listing['title']}")
        )
        return

    if text.startswith("/一番賞刪除 "):
        listings = get_ichiban_listings()
        try:
            listing_index = int(text[len("/一番賞刪除 "):].strip()) - 1
        except ValueError:
            listing_index = -1

        if not 0 <= listing_index < len(listings):
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="❌ 編號無效，請先用 /一番賞列表 查看編號")
            )
            return

        removed = listings.pop(listing_index)
        save_ichiban_listings(listings)
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=f"✅ 已刪除：{removed['title']}")
        )
        return

    if text == "/一番賞列表":
        listings = get_ichiban_listings()
        listing_text = "\n".join(
            f"{index}. {listing['title']}（{listing['remaining']}）"
            for index, listing in enumerate(listings, start=1)
        ) or "目前沒有設定一番賞"
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=listing_text)
        )
        return

    if text == "/今日一番賞推薦":
        listings = get_ichiban_listings()
        if not listings:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="目前沒有設定一番賞，請先使用 /一番賞新增")
            )
            return

        carousel = {
            "type": "carousel",
            "contents": [build_ichiban_bubble(listing) for listing in listings[:MAX_ICHIBAN_LISTINGS]],
        }
        line_bot_api.reply_message(
            event.reply_token,
            FlexSendMessage(alt_text="今日一番賞資訊", contents=carousel)
        )
        return

    if text == "/id":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"你的 User ID 是：{user_id}"))
        return

    if text == "幫我踢掉fly":
        if not is_group_admin(group_id, user_id):
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="❌ 只有管理員可以使用這個指令")
            )
            return

        try:
            line_bot_api.kickout_group_member(group_id, FLY_USER_ID)
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="✅ fly 已踢出群組")
            )
        except Exception as e:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"❌ 踢出 fly 失敗，原因：{e}")
            )
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
        
    # ✅ 支援「幫我在1-80之間選5個數字／號碼」這種句子
    match = re.search(
        r"幫我在\s*(\d+)\s*[-~～至到－—]\s*(\d+)\s*(?:之間\s*)?選\s*(\d+)\s*個(?:數字|號碼)",
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

