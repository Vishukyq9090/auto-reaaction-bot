import asyncio
import os
import time
import threading
import json
import urllib.request
import random
from datetime import datetime

try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

from flask import Flask
from pyrogram import Client, filters, utils as pyro_utils
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant
from pyrogram.enums import ChatMemberStatus
from pymongo import MongoClient

# Fix Pyrogram Peer ID Invalid bug for newer -1002... / -1003... Telegram Channels
pyro_utils.MIN_CHANNEL_ID = -1009999999999

# --- 1. Web Server & External Pinger for 24/7 Keep-Alive ---
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Pro Reaction & FSub Bot is Running Perfectly 24/7!"

def run_server():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host="0.0.0.0", port=port)

def keep_alive_pinger():
    """Pings external Render URL & localhost every 4 minutes so it never sleeps."""
    time.sleep(15)
    port = int(os.environ.get("PORT", 8080))
    external_url = os.environ.get("RENDER_EXTERNAL_URL", "https://auto-reaaction-bot-24c9.onrender.com")
    local_url = f"http://127.0.0.1:{port}/"
    while True:
        for url in [external_url, local_url]:
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                urllib.request.urlopen(req, timeout=10)
            except Exception:
                pass
        time.sleep(240)

# --- 2. Configurations & DB Setup ---
API_ID = int(str(os.environ.get("API_ID", "12345")).strip() or 12345)
API_HASH = os.environ.get("API_HASH", "").strip()
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
MONGO_URI = os.environ.get("MONGO_URI", "").strip()
ADMIN_ID = int(str(os.environ.get("ADMIN_ID", "7412791600")).strip() or 7412791600)

app = Client(
    "ProReactionBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True
)

db_client = MongoClient(MONGO_URI)
db = db_client["ProReactionBot_DB"]
bot_users_col = db["bot_users"]
global_settings_col = db["global_settings"]

# --- 3. HYBRID REACTION SYSTEM (React or Reply) ---
async def safe_react_or_reply(message, emoji):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/setMessageReaction"
    data = {
        "chat_id": message.chat.id,
        "message_id": message.id,
        "reaction": [{"type": "emoji", "emoji": emoji}]
    }

    def make_request():
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(data).encode('utf-8'),
                headers={'Content-Type': 'application/json'}
            )
            with urllib.request.urlopen(req, timeout=5) as res:
                return res.getcode() == 200
        except Exception:
            return False

    success = await loop.run_in_executor(None, make_request)

    if not success:
        try:
            await message.reply_text(emoji)
        except Exception:
            pass

# --- 4. AI Mood Analyzer (50+ Emojis Supported) ---
def get_mood_emoji(text):
    text = str(text).lower()

    if any(word in text for word in ['love', 'pyar', 'pyaar', 'ishq', 'dil', 'heart', 'beautiful', 'cute', 'kiss', 'romantic']):
        return random.choice(["❤", "🥰", "😍", "❤️‍🔥", "💘", "😘", "💋"])
    elif any(word in text for word in ['funny', 'haha', 'lol', 'lmao', 'joke', 'मजाक', '😂', 'rofl', 'comedy', 'fun', 'hilarious']):
        return random.choice(["🤣", "😁", "🤪", "🤡"])
    elif any(word in text for word in ['sad', 'bad', 'crying', 'दुखी', 'खराब', 'sorry', 'rip', 'broken', 'cry', 'pain', 'hurt']):
        return random.choice(["😢", "😭", "💔", "🥀"])
    elif any(word in text for word in ['angry', 'mad', 'wtf', 'गुस्सा', 'hate', 'fuck', 'shit', 'idiot', 'stupid', 'annoy']):
        return random.choice(["🤬", "😡", "😈", "🖕"])
    elif any(word in text for word in ['wow', 'amazing', 'omg', 'shocking', 'surprise', 'crazy', 'insane', 'whoa', 'omfg']):
        return random.choice(["😱", "🤯", "😲", "👀"])
    elif any(word in text for word in ['gross', 'eww', 'sick', 'vomit', 'disgusting', 'dirty', 'kachra', 'ganda']):
        return random.choice(["🤮", "💩", "🥴"])
    elif any(word in text for word in ['win', 'won', 'party', 'congrats', 'celebrate', 'victory', 'champion', 'success']):
        return random.choice(["🎉", "🍾", "🏆", "👏", "💯"])
    elif any(word in text for word in ['fire', 'lit', 'hype', 'awesome', 'great', 'best', 'epic', 'mast', 'kadak', 'jhakaas']):
        return random.choice(["🔥", "⚡", "💯"])
    elif any(word in text for word in ['thanks', 'thank you', 'dhanyawad', 'shukriya', 'pray', 'bless', 'god', 'please']):
        return random.choice(["🙏", "😇", "🤝"])
    elif any(word in text for word in ['what', 'why', 'how', 'confused', 'think', 'soch', 'kya', 'kaise', 'hmm']):
        return random.choice(["🤔", "🤨", "😐"])
    elif any(word in text for word in ['bored', 'tired', 'sleepy', 'good night', 'boring', 'thak', 'neend']):
        return random.choice(["🥱", "😴"])
    else:
        return random.choice(["👍", "🔥", "❤", "⚡", "💯", "👌", "👏", "🥰", "😁", "👻", "🐳", "🌚", "🦄"])

@app.on_message((filters.channel | filters.group) & ~filters.service)
async def mood_reaction_handler(client, message):
    if message.from_user and message.from_user.is_self:
        return

    text_content = message.text or message.caption or ""
    reaction_emoji = get_mood_emoji(text_content)
    await safe_react_or_reply(message, reaction_emoji)

# --- 5. MAGIC FSUB (Single Click Private/Public Channel Auto-Add) ---
@app.on_chat_member_updated(filters.channel | filters.group)
async def magic_fsub_handler(client, update):
    try:
        bot_info = await client.get_me()
        if update.new_chat_member and update.new_chat_member.user.id == bot_info.id:
            status = str(update.new_chat_member.status).lower()
            if "administrator" in status or "owner" in status:
                chat_id = update.chat.id

                await client.send_message(
                    chat_id,
                    "✅ **Pro Bot Successfully Added as Admin!**\nमैं हर पोस्ट पर रिएक्शन देने के लिए तैयार हूँ।"
                )

                if update.from_user and update.from_user.id == ADMIN_ID:
                    invite_link = update.chat.invite_link
                    if not invite_link:
                        try:
                            invite_link = await client.export_chat_invite_link(chat_id)
                        except Exception:
                            invite_link = ""

                    if invite_link:
                        fsub_data = global_settings_col.find_one({"id": "fsub"})
                        channels = fsub_data.get("channels", []) if fsub_data else []

                        if not any(c["chat_id"] == chat_id for c in channels):
                            channels.append({"chat_id": chat_id, "link": invite_link})
                            global_settings_col.update_one({"id": "fsub"}, {"$set": {"channels": channels}}, upsert=True)

                            await client.send_message(
                                ADMIN_ID,
                                f"🎉 **Magic FSub Configured! (Single Click Add)**\n\n"
                                f"📢 **Channel:** `{update.chat.title}`\n"
                                f"🆔 **ID:** `{chat_id}`\n\n"
                                f"✅ इस चैनल को Force Subscribe लिस्ट में ऑटोमैटिकली जोड़ दिया गया है!"
                            )
    except Exception as e:
        print("Magic FSub Error:", e)

# --- 6. ADMIN PANEL & ANALYTICS (/panel) ---
@app.on_message(filters.command("panel") & filters.private)
async def owner_panel(client, message):
    if ADMIN_ID == 0 or message.from_user.id != ADMIN_ID:
        return

    users_count = bot_users_col.count_documents({})
    fsub_data = global_settings_col.find_one({"id": "fsub"})
    fsub_channels = fsub_data.get("channels", []) if fsub_data else []

    text = (
        "👑 **PRO ADMIN DASHBOARD**\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"📊 **Analytics:**\n"
        f"👥 Total Registered Users: **{users_count}**\n"
        f"📢 Active FSub Channels: **{len(fsub_channels)}**\n\n"
        "🛠 **Commands Guide:**\n"
        "🔸 `बॉट को चैनल में एडमिन बनाएं` - FSub में अपने आप जुड़ जाएगा (Magic FSub)\n"
        "🔸 `/addfsub -1001234...` - Private/Public मैन्युअल जोड़ें\n"
        "🔸 `/delfsub` - सभी FSub चैनल्स हटा दें\n"
        "🔸 `/broadcast` - किसी मैसेज का रिप्लाई करके ब्रॉडकास्ट करें\n"
        "🔸 `/pin` - किसी मैसेज का रिप्लाई करके पिन करें\n"
    )
    await message.reply(text)

# --- 7. BROADCAST & PIN MESSAGES ---
@app.on_message(filters.command("broadcast") & filters.private)
async def broadcast_msg(client, message):
    if ADMIN_ID == 0 or message.from_user.id != ADMIN_ID:
        return

    if not message.reply_to_message:
        await message.reply("❌ **एरर:** किसी मैसेज, फोटो या वीडियो का रिप्लाई (Reply) करते हुए `/broadcast` लिखें।")
        return

    status = await message.reply("⏳ **ब्रॉडकास्ट शुरू हो रहा है...**")
    users = list(bot_users_col.find({}))
    success, failed = 0, 0

    for u in users:
        try:
            await message.reply_to_message.copy(u["user_id"])
            success += 1
            await asyncio.sleep(0.1)
        except Exception:
            failed += 1

    await status.edit_text(f"✅ **Broadcast Completed!**\n\n🟢 Success: {success}\n🔴 Failed: {failed}")

@app.on_message(filters.command("pin") & (filters.group | filters.channel))
async def pin_msg(client, message):
    if message.from_user and message.from_user.id == ADMIN_ID:
        if message.reply_to_message:
            try:
                await message.reply_to_message.pin(both_sides=True)
                await message.reply("📌 **मैसेज पिन कर दिया गया है!**")
            except Exception as e:
                await message.reply(f"❌ **पिन एरर:** {e}")

# --- 8. MANUAL FSUB COMMAND (Supports Private -100 IDs) ---
@app.on_message(filters.command("addfsub") & filters.private)
async def add_fsub(client, message):
    if ADMIN_ID == 0 or message.from_user.id != ADMIN_ID:
        return

    if len(message.command) < 2:
        await message.reply("❌ **सही तरीका:**\nPublic: `/addfsub @yourchannel`\nPrivate: `/addfsub -100123456789`")
        return

    channel_input = message.command[1]
    try:
        chat_id = int(channel_input) if channel_input.startswith("-100") else channel_input
        chat_info = await client.get_chat(chat_id)

        invite_link = chat_info.invite_link or await client.export_chat_invite_link(chat_info.id)

        fsub_data = global_settings_col.find_one({"id": "fsub"})
        channels = fsub_data.get("channels", []) if fsub_data else []

        if not any(c["chat_id"] == chat_info.id for c in channels):
            channels.append({"chat_id": chat_info.id, "link": invite_link})
            global_settings_col.update_one({"id": "fsub"}, {"$set": {"channels": channels}}, upsert=True)

        await message.reply(f"✅ **Force Subscribe सेट हो गया:** {chat_info.title}\n*(Total FSub Channels: {len(channels)})*")
    except Exception as e:
        await message.reply(f"❌ **एरर:** कृपया पहले बॉट को उस चैनल में Admin बनाएं या ID चेक करें।\nDetail: {e}")

@app.on_message(filters.command("delfsub") & filters.private)
async def del_fsub(client, message):
    if ADMIN_ID == 0 or message.from_user.id != ADMIN_ID:
        return
    global_settings_col.update_one({"id": "fsub"}, {"$set": {"channels": []}}, upsert=True)
    await message.reply("✅ **सभी Force Subscribe चैनल्स हटा दिए गए हैं!**")

# --- 9. START COMMAND (Multi-FSub, Registration, Refer & Earn, Socials) ---
@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    user_id = message.from_user.id
    bot_info = await client.get_me()

    fsub_data = global_settings_col.find_one({"id": "fsub"})
    fsub_channels = fsub_data.get("channels", []) if fsub_data else []
    not_joined = []

    for fsub in fsub_channels:
        try:
            member = await client.get_chat_member(fsub["chat_id"], user_id)
            if member.status in [ChatMemberStatus.BANNED, ChatMemberStatus.RESTRICTED]:
                return
        except UserNotParticipant:
            not_joined.append(fsub)
        except Exception:
            pass

    if not_joined:
        buttons = []
        for i, fsub in enumerate(not_joined):
            buttons.append([InlineKeyboardButton(f"🔔 Subscribe Channel {i+1}", url=fsub["link"])])

        buttons.append([InlineKeyboardButton("✅ I Have Subscribed", url=f"https://t.me/{bot_info.username}?start=start")])
        await message.reply(
            "🚨 **हमारी सर्विस इस्तेमाल करने के लिए कृपया हमारे सभी चैनल सब्सक्राइब करें!**",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    text = message.text.split()
    user_data = bot_users_col.find_one({"user_id": user_id})

    if not user_data:
        referrer_id = None
        if len(text) > 1 and text[1].startswith("ref_"):
            try:
                referrer_id = int(text[1].split("_")[1])
            except Exception:
                pass

        bot_users_col.insert_one({
            "user_id": user_id,
            "balance": 0,
            "referral_count": 0,
            "referred_by": referrer_id,
            "join_date": datetime.now()
        })

        if referrer_id and referrer_id != user_id:
            bot_users_col.update_one({"user_id": referrer_id}, {"$inc": {"balance": 5, "referral_count": 1}})
            try:
                await client.send_message(referrer_id, "🎉 **New Referral!**\n💰 + ₹5 added to your account!")
            except Exception:
                pass

    add_link = f"https://t.me/{bot_info.username}?startchannel=true&admin=post_messages+edit_messages+delete_messages+invite_users+manage_chat+pin_messages"

    welcome_msg = (
        "👋 **Welcome to the Smart Reaction Bot!**\n\n"
        "**मैं क्या कर सकता हूँ?**\n"
        "मैं आपके ग्रुप/चैनल के हर पोस्ट, फाइल या फोटो का मूड समझकर उस पर परफेक्ट इमोजी (Reaction) लगा सकता हूँ।\n\n"
        "**कैसे इस्तेमाल करें?**\n"
        "बस नीचे दिए गए ➕ बटन पर क्लिक करें और मुझे अपने चैनल/ग्रुप में **Admin** बना लें!"
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Bot to Channel / Group", url=add_link)],
        [InlineKeyboardButton("🎁 Refer & Earn (₹5/Refer)", callback_data="btn_refer")],
        [
            InlineKeyboardButton("📱 Telegram", url="https://t.me/openbook506"),
            InlineKeyboardButton("📸 Instagram", url="https://instagram.com/openbook606"),
            InlineKeyboardButton("▶️ YouTube", url="https://youtube.com/@openbook506")
        ]
    ])

    await message.reply_text(welcome_msg, reply_markup=keyboard)

# --- 10. REFER & EARN BUTTON LOGIC ---
@app.on_callback_query()
async def callback_handler(client, callback_query):
    user_id = callback_query.from_user.id
    msg = callback_query.message
    data = callback_query.data
    bot_info = await client.get_me()

    if data == "btn_refer":
        user_data = bot_users_col.find_one({"user_id": user_id})
        balance = user_data.get("balance", 0) if user_data else 0
        ref_count = user_data.get("referral_count", 0) if user_data else 0
        ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"

        refer_text = (
            f"🎁 **Refer & Earn Program**\n\n"
            f"Share your link and earn **₹5** per refer!\n\n"
            f"👥 Total Refers: {ref_count}\n"
            f"💰 Balance: ₹{balance}\n\n"
            f"📌 **Your Link:**\n`{ref_link}`\n\n"
            f"⚠️ *Minimum Withdrawal is ₹500.*"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💸 Withdraw (₹500)", callback_data="btn_withdraw")],
            [InlineKeyboardButton("🔙 Back", callback_data="btn_back")]
        ])
        await msg.edit_text(refer_text, reply_markup=keyboard)

    elif data == "btn_withdraw":
        user_data = bot_users_col.find_one({"user_id": user_id})
        balance = user_data.get("balance", 0) if user_data else 0
        if balance < 500:
            await callback_query.answer(f"❌ Minimum Withdrawal is ₹500!\nYour Current Balance: ₹{balance}", show_alert=True)
        else:
            await callback_query.answer("✅ Withdrawal Request Submitted!\nYour account is under review.", show_alert=True)

    elif data == "btn_back":
        add_link = f"https://t.me/{bot_info.username}?startchannel=true&admin=post_messages+edit_messages+delete_messages+invite_users+manage_chat+pin_messages"
        welcome_msg = "👋 **Welcome to the Smart Reaction Bot!**\n\nबस नीचे दिए गए ➕ बटन पर क्लिक करें और मुझे अपने चैनल/ग्रुप में **Admin** बना लें!"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Add Bot to Channel / Group", url=add_link)],
            [InlineKeyboardButton("🎁 Refer & Earn (₹5/Refer)", callback_data="btn_refer")],
            [
                InlineKeyboardButton("📱 Telegram", url="https://t.me/openbook506"),
                InlineKeyboardButton("📸 Instagram", url="https://instagram.com/openbook606"),
                InlineKeyboardButton("▶️ YouTube", url="https://youtube.com/@openbook506")
            ]
        ])
        await msg.edit_text(welcome_msg, reply_markup=keyboard)

# --- 11. DIRECT STARTUP NOTIFICATION ---
def send_startup_notification():
    if ADMIN_ID != 0 and BOT_TOKEN:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        text = f"✅ **REACTION BOT IS ONLINE 24/7!**\n\n⏰ **Started At:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n👉 **एडमिन पैनल:** /panel"
        data = {"chat_id": ADMIN_ID, "text": text, "parse_mode": "Markdown"}
        try:
            req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'), headers={'Content-Type': 'application/json'})
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            pass

if __name__ == "__main__":
    threading.Thread(target=run_server, daemon=True).start()
    threading.Thread(target=keep_alive_pinger, daemon=True).start()
    threading.Thread(target=send_startup_notification, daemon=True).start()

    print("Pro Reaction Bot Started 24/7 Worldwide!")
    app.run()
