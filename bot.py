import asyncio
import os
import threading
import json
import urllib.request
from datetime import datetime

try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

from flask import Flask
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant
from pyrogram.enums import ChatMemberStatus
from pymongo import MongoClient

# --- 1. Web Server for Render Keep-Alive ---
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Pro Reaction & FSub Bot is Running!"

def run_server():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host="0.0.0.0", port=port)

# --- 2. Configurations & DB Setup ---
API_ID = int(os.environ.get("API_ID", 12345))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
MONGO_URI = os.environ.get("MONGO_URI", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))

app = Client("ProReactionBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

db_client = MongoClient(MONGO_URI)
db = db_client["ProReactionBot_DB"]
bot_users_col = db["bot_users"]
global_settings_col = db["global_settings"]

# --- 🚀 3. PRO FEATURE: Error-Free Direct Telegram API Reaction ---
# Pyrogram के एरर (BOT_METHOD_INVALID) से बचने के लिए डायरेक्ट API कॉल
def safe_react(chat_id, message_id, emoji):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/setMessageReaction"
    data = {
        "chat_id": chat_id,
        "message_id": message_id,
        "reaction": [{"type": "emoji", "emoji": emoji}]
    }
    try:
        req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'), headers={'Content-Type': 'application/json'})
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        print(f"Reaction API Error: {e}")

# --- 🤖 4. AI Caption Mood Analyzer ---
def get_mood_emoji(text):
    text = str(text).lower()
    
    if any(word in text for word in ['sad', 'bad', 'crying', 'दुखी', 'खराब', 'sorry', 'rip']):
        return "😢"
    elif any(word in text for word in ['funny', 'haha', 'lol', 'joke', 'मजाक', '😂', 'rofl']):
        return "😂"
    elif any(word in text for word in ['angry', 'mad', 'wtf', 'गुस्सा', 'hate']):
        return "😡"
    elif any(word in text for word in ['love', 'romantic', 'pyar', 'pyaar', '❤️', 'beautiful', 'cute']):
        return "❤️"
    elif any(word in text for word in ['wow', 'amazing', 'omg', 'shocking', 'surprise']):
        return "😱"
    else:
        return "👍" # Default Positive Reaction (अगर बॉट को कुछ समझ न आए)

@app.on_message((filters.channel | filters.group) & ~filters.service)
async def mood_reaction_handler(client, message):
    if message.from_user and message.from_user.is_self:
        return
        
    # मैसेज, कैप्शन, लिंक, डॉक्यूमेंट - किसी भी फॉर्मैट का टेक्स्ट पकड़ेगा
    text_content = message.text or message.caption or ""
    reaction_emoji = get_mood_emoji(text_content)
    
    # 100% Error-Free Reaction Call
    safe_react(message.chat.id, message.id, reaction_emoji)

# --- ⚙️ 5. ADMIN PANEL & ANALYTICS (/panel) ---
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
        "🔸 `/addfsub @username` - FSub चैनल जोड़ें\n"
        "🔸 `/delfsub` - सभी FSub चैनल्स हटा दें\n"
        "🔸 `/broadcast` - किसी मैसेज का रिप्लाई करके ब्रॉडकास्ट करें\n"
        "🔸 `/pin` - किसी मैसेज का रिप्लाई करके पिन करें\n"
    )
    await message.reply(text)

# --- 📢 6. BROADCAST & PIN MESSAGES ---
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
            await asyncio.sleep(0.1)  # Anti-Spam
        except:
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

# --- 🔗 7. SINGLE CLICK FSUB MANAGEMENT ---
@app.on_message(filters.command("addfsub") & filters.private)
async def add_fsub(client, message):
    if ADMIN_ID == 0 or message.from_user.id != ADMIN_ID:
        return
        
    if len(message.command) < 2:
        await message.reply("❌ **सही तरीका:** `/addfsub @yourchannel`")
        return
        
    channel_username = message.command[1]
    try:
        chat_info = await client.get_chat(channel_username)
        invite_link = chat_info.invite_link or await client.export_chat_invite_link(chat_info.id)
        
        fsub_data = global_settings_col.find_one({"id": "fsub"})
        channels = fsub_data.get("channels", []) if fsub_data else []
        
        if not any(c["chat_id"] == chat_info.id for c in channels):
            channels.append({"chat_id": chat_info.id, "link": invite_link})
            global_settings_col.update_one({"id": "fsub"}, {"$set": {"channels": channels}}, upsert=True)
            
        await message.reply(f"✅ **Force Subscribe सेट हो गया:** {chat_info.title}\n*(Total FSub Channels: {len(channels)})*")
    except Exception as e:
        await message.reply(f"❌ **एरर:** कृपया पहले बॉट को उस चैनल में Admin बनाएं।\nDetail: {e}")

@app.on_message(filters.command("delfsub") & filters.private)
async def del_fsub(client, message):
    if ADMIN_ID == 0 or message.from_user.id != ADMIN_ID:
        return
    global_settings_col.update_one({"id": "fsub"}, {"$set": {"channels": []}}, upsert=True)
    await message.reply("✅ **सभी Force Subscribe चैनल्स हटा दिए गए हैं!**")

# --- ✨ 8. START COMMAND (Multi-FSub, Registration, Refer & Earn, Socials) ---
@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    user_id = message.from_user.id
    bot_info = await client.get_me()
    
    # 🔒 Multi-Channel Force Subscribe Check
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
        await message.reply("🚨 **हमारी सर्विस इस्तेमाल करने के लिए कृपया हमारे सभी चैनल सब्सक्राइब करें!**", reply_markup=InlineKeyboardMarkup(buttons))
        return

    # User Registration & Refer System
    text = message.text.split()
    user_data = bot_users_col.find_one({"user_id": user_id})

    if not user_data:
        referrer_id = None
        if len(text) > 1 and text[1].startswith("ref_"):
            try:
                referrer_id = int(text[1].split("_")[1])
            except:
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
            except:
                pass

    # 🔗 PRO Single Click Add Admin Link (All Permissions)
    add_link = f"https://t.me/{bot_info.username}?startchannel=true&admin=post_messages+edit_messages+delete_messages+invite_users+manage_chat+pin_messages"
    
    welcome_msg = (
        "👋 **Welcome to the Smart Reaction Bot!**\n\n"
        "**मैं क्या कर सकता हूँ?**\n"
        "मैं आपके ग्रुप/चैनल के हर पोस्ट, फाइल या फोटो का मूड समझकर उस पर परफेक्ट इमोजी (Reaction) लगा सकता हूँ।\n\n"
        "**कैसे इस्तेमाल करें?**\n"
        "बस नीचे दिए गए ➕ बटन पर क्लिक करें और मुझे अपने चैनल/ग्रुप में **Admin** बना लें!"
    )

    # 📱 Clean Social Media Integration (@openboo506) & Core Buttons
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Bot to Channel / Group", url=add_link)],
        [InlineKeyboardButton("🎁 Refer & Earn (₹5/Refer)", callback_data="btn_refer")],
        [
            InlineKeyboardButton("📱 Telegram", url="https://t.me/openboo506"),
            InlineKeyboardButton("📸 Instagram", url="https://instagram.com/openboo506"),
            InlineKeyboardButton("▶️ YouTube", url="https://youtube.com/@openboo506")
        ]
    ])
    
    await message.reply_text(welcome_msg, reply_markup=keyboard)


# --- 🎁 9. REFER & EARN BUTTON LOGIC ---
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
                InlineKeyboardButton("📱 Telegram", url="https://t.me/openboo506"),
                InlineKeyboardButton("📸 Instagram", url="https://instagram.com/openboo506"),
                InlineKeyboardButton("▶️ YouTube", url="https://youtube.com/@openboo506")
            ]
        ])
        await msg.edit_text(welcome_msg, reply_markup=keyboard)

# --- 🟢 10. BOT START/UP NOTIFICATION ---
async def startup_notification():
    await app.start()
    if ADMIN_ID != 0:
        try:
            bot_info = await app.get_me()
            await app.send_message(
                ADMIN_ID,
                f"✅ **BOT IS ONLINE AND WORKING!**\n\n"
                f"🤖 **Bot Name:** {bot_info.first_name}\n"
                f"⏰ **Started At:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"👉 **एडमिन पैनल देखने के लिए क्लिक करें:** /panel"
            )
        except Exception as e:
            print("Admin Notification Failed:", e)
    await app.stop()

if __name__ == "__main__":
    # Send start notification asynchronously
    loop.run_until_complete(startup_notification())
    
    # Run Web Server
    threading.Thread(target=run_server, daemon=True).start()
    
    # Run Bot
    print("Pro Bot Started Worldwide!")
    app.run()
