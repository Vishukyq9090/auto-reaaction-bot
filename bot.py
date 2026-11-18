import asyncio
import os
import time
import threading
import json
import urllib.request
import random
import certifi
from datetime import datetime

try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

from flask import Flask
from pyrogram import Client, filters, utils as pyro_utils
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant, FloodWait, ChatAdminRequired, RPCError
from pyrogram.enums import ChatMemberStatus, ChatType
from pymongo import MongoClient, ReturnDocument

# Fix Pyrogram Peer ID Invalid bug for newer -1002... / -1003... Telegram Channels
pyro_utils.MIN_CHANNEL_ID = -1009999999999

# --- 1. Web Server & External Pinger for 24/7 Keep-Alive ---
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Pro Reaction & FSub Bot is Running Perfectly 24/7!"

def run_server():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host="0.0.0.0", port=port, use_reloader=False)

def keep_alive_pinger():
    """Pings external Render URL & localhost every 4 minutes so it never sleeps."""
    time.sleep(15)
    port = int(os.environ.get("PORT", 8080))
    external_url = os.environ.get("RENDER_EXTERNAL_URL", "").strip()
    local_url = f"http://127.0.0.1:{port}/"
    urls = [u for u in [external_url, local_url] if u]
    while True:
        for url in urls:
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                urllib.request.urlopen(req, timeout=10)
            except Exception:
                pass
        time.sleep(240)

# --- 2. Configurations & Fast DB Setup ---
API_ID = int(str(os.environ.get("API_ID", "0")).strip() or 0)
API_HASH = os.environ.get("API_HASH", "").strip()
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
MONGO_URI = os.environ.get("MONGO_URI", "").strip()
ADMIN_ID = int(str(os.environ.get("ADMIN_ID", "7412791600")).strip() or 7412791600)

if not all([API_ID, API_HASH, BOT_TOKEN, MONGO_URI]):
    raise ValueError("Missing required environment variables: API_ID, API_HASH, BOT_TOKEN, or MONGO_URI")

app = Client(
    "ProReactionBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True,
    workers=16
)

db_client = MongoClient(MONGO_URI, tlsCAFile=certifi.where(), maxPoolSize=50)
db = db_client["ProReactionBot_DB"]
bot_users_col = db["bot_users"]
global_settings_col = db["global_settings"]

# Ensure fast O(1) lookup index on user_id
try:
    bot_users_col.create_index("user_id", unique=True)
except Exception:
    pass

# In-Memory Cache for High Speed
BOT_INFO = {"id": None, "username": None}
FSUB_CACHE = {"channels": None, "last_updated": 0}
ERROR_COOLDOWN = {}  # Prevents spamming admin with repeated channel errors

async def get_bot_info(client: Client):
    if not BOT_INFO["id"]:
        me = await client.get_me()
        BOT_INFO["id"] = me.id
        BOT_INFO["username"] = me.username
    return BOT_INFO

async def notify_admin_error(client: Client, key: str, text: str, cooldown: int = 600):
    """Sends error reports to Admin with cooldown protection."""
    if not ADMIN_ID:
        return
    now = time.time()
    if now - ERROR_COOLDOWN.get(key, 0) < cooldown:
        return
    ERROR_COOLDOWN[key] = now
    try:
        await client.send_message(ADMIN_ID, text)
    except Exception as e:
        print(f"Failed to notify admin: {e}")

def get_fsub_channels(force_refresh: bool = False):
    now = time.time()
    if force_refresh or FSUB_CACHE["channels"] is None or (now - FSUB_CACHE["last_updated"] > 300):
        fsub_data = global_settings_col.find_one({"id": "fsub"})
        FSUB_CACHE["channels"] = fsub_data.get("channels", []) if fsub_data else []
        FSUB_CACHE["last_updated"] = now
    return FSUB_CACHE["channels"]

def save_fsub_channels(channels: list):
    global_settings_col.update_one({"id": "fsub"}, {"$set": {"channels": channels}}, upsert=True)
    FSUB_CACHE["channels"] = channels
    FSUB_CACHE["last_updated"] = time.time()

async def resolve_valid_invite_link(client: Client, chat_id: int | str) -> tuple[int, str, str]:
    """Resolves chat peer, title, and generates a permanent/valid invite link without revoking existing links."""
    chat = await client.get_chat(chat_id)
    title = chat.title or str(chat.id)

    # 1. Prefer public username link if available
    if chat.username:
        return chat.id, title, f"https://t.me/{chat.username}"

    # 2. Use existing invite_link if available
    if chat.invite_link:
        return chat.id, title, chat.invite_link

    # 3. Create a dedicated permanent invite link (doesn't revoke existing ones)
    try:
        link_obj = await client.create_chat_invite_link(chat.id, name="FSub Auto Link")
        if link_obj and link_obj.invite_link:
            return chat.id, title, link_obj.invite_link
    except Exception:
        pass

    # 4. Fallback to export_chat_invite_link
    invite_link = await client.export_chat_invite_link(chat.id)
    return chat.id, title, invite_link

# --- 3. HYBRID REACTION SYSTEM (Fast & Safe) ---
async def safe_react_or_reply(message, emoji):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/setMessageReaction"
    payload = json.dumps({
        "chat_id": message.chat.id,
        "message_id": message.id,
        "reaction": [{"type": "emoji", "emoji": emoji}]
    }).encode("utf-8")

    def make_request():
        try:
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json", "Connection": "keep-alive"}
            )
            with urllib.request.urlopen(req, timeout=4) as res:
                return res.getcode() == 200
        except Exception:
            return False

    success = await loop.run_in_executor(None, make_request)

    # Fallback reply only in groups (avoids spamming standalone emoji posts in channels)
    if not success and message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        try:
            await message.reply_text(emoji)
        except Exception:
            pass

# --- 4. AI Mood Analyzer (50+ Emojis Supported) ---
MOOD_KEYWORDS = [
    ({'love', 'pyar', 'pyaar', 'ishq', 'dil', 'heart', 'beautiful', 'cute', 'kiss', 'romantic'}, ["❤", "🥰", "😍", "❤️‍🔥", "💘", "😘", "💋"]),
    ({'funny', 'haha', 'lol', 'lmao', 'joke', 'मजाक', '😂', 'rofl', 'comedy', 'fun', 'hilarious'}, ["🤣", "😁", "🤪", "🤡"]),
    ({'sad', 'bad', 'crying', 'दुखी', 'खराब', 'sorry', 'rip', 'broken', 'cry', 'pain', 'hurt'}, ["😢", "😭", "💔", "🥀"]),
    ({'angry', 'mad', 'wtf', 'गुस्सा', 'hate', 'fuck', 'shit', 'idiot', 'stupid', 'annoy'}, ["🤬", "😡", "😈", "🖕"]),
    ({'wow', 'amazing', 'omg', 'shocking', 'surprise', 'crazy', 'insane', 'whoa', 'omfg'}, ["😱", "🤯", "😲", "👀"]),
    ({'gross', 'eww', 'sick', 'vomit', 'disgusting', 'dirty', 'kachra', 'ganda'}, ["🤮", "💩", "🥴"]),
    ({'win', 'won', 'party', 'congrats', 'celebrate', 'victory', 'champion', 'success'}, ["🎉", "🍾", "🏆", "👏", "💯"]),
    ({'fire', 'lit', 'hype', 'awesome', 'great', 'best', 'epic', 'mast', 'kadak', 'jhakaas'}, ["🔥", "⚡", "💯"]),
    ({'thanks', 'thank you', 'dhanyawad', 'shukriya', 'pray', 'bless', 'god', 'please'}, ["🙏", "😇", "🤝"]),
    ({'what', 'why', 'how', 'confused', 'think', 'soch', 'kya', 'kaise', 'hmm'}, ["🤔", "🤨", "😐"]),
    ({'bored', 'tired', 'sleepy', 'good night', 'boring', 'thak', 'neend'}, ["🥱", "😴"]),
]
DEFAULT_EMOJIS = ["👍", "🔥", "❤", "⚡", "💯", "👌", "👏", "🥰", "😁", "👻", "🐳", "🌚", "🦄"]

def get_mood_emoji(text: str) -> str:
    text_lower = str(text).lower()
    for keywords, emojis in MOOD_KEYWORDS:
        if any(word in text_lower for word in keywords):
            return random.choice(emojis)
    return random.choice(DEFAULT_EMOJIS)

@app.on_message((filters.channel | filters.group) & ~filters.service & ~filters.command(["pin"]))
async def mood_reaction_handler(client, message):
    if message.from_user and message.from_user.is_self:
        return
    text_content = message.text or message.caption or ""
    reaction_emoji = get_mood_emoji(text_content)
    await safe_react_or_reply(message, reaction_emoji)

# --- 5. MAGIC FSUB (Single Click Private/Public Channel Auto-Add + Error Report) ---
@app.on_chat_member_updated(filters.channel | filters.group)
async def magic_fsub_handler(client, update):
    try:
        bot_info = await get_bot_info(client)
        if not (update.new_chat_member and update.new_chat_member.user.id == bot_info["id"]):
            return

        new_status = update.new_chat_member.status
        old_status = update.old_chat_member.status if update.old_chat_member else None

        if new_status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER) and old_status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
            chat_id = update.chat.id
            try:
                await client.send_message(
                    chat_id,
                    "✅ **Pro Bot Successfully Added as Admin!**\nमैं हर पोस्ट पर रिएक्शन देने के लिए तैयार हूँ।"
                )
            except Exception:
                pass

            if update.from_user and update.from_user.id == ADMIN_ID:
                try:
                    resolved_id, title, invite_link = await resolve_valid_invite_link(client, chat_id)
                    channels = get_fsub_channels(force_refresh=True)

                    # Update existing or add new
                    updated = False
                    for c in channels:
                        if c["chat_id"] == resolved_id:
                            c["link"] = invite_link
                            c["title"] = title
                            updated = True
                            break
                    if not updated:
                        channels.append({"chat_id": resolved_id, "link": invite_link, "title": title})

                    save_fsub_channels(channels)

                    await client.send_message(
                        ADMIN_ID,
                        f"🎉 **Magic FSub Configured! (Single Click Add)**\n\n"
                        f"📢 **Channel:** `{title}`\n"
                        f"🆔 **ID:** `{resolved_id}`\n"
                        f"🔗 **Link:** {invite_link}\n\n"
                        f"✅ इस चैनल को Force Subscribe लिस्ट में ऑटोमैटिकली जोड़ दिया गया है!"
                    )
                except Exception as e:
                    await notify_admin_error(
                        client,
                        f"magic_fsub_{chat_id}",
                        f"⚠️ **Magic FSub Link Error!**\n\n"
                        f"📢 **Chat:** `{update.chat.title or chat_id}` (`{chat_id}`)\n"
                        f"❌ **Error:** `{e}`\n\n"
                        f"💡 **Solution:** कृपया बॉट को चैनल में **'Invite Users via Link'** परमिशन दें और `/addfsub {chat_id}` कमांड चलाएं।",
                        cooldown=10
                    )
    except Exception as e:
        print("Magic FSub Error:", e)

# --- 6. ADMIN PANEL & ANALYTICS (/panel) ---
@app.on_message(filters.command("panel") & filters.private)
async def owner_panel(client, message):
    if ADMIN_ID == 0 or message.from_user.id != ADMIN_ID:
        return

    users_count = bot_users_col.count_documents({})
    fsub_channels = get_fsub_channels(force_refresh=True)

    fsub_list_text = ""
    if fsub_channels:
        for idx, ch in enumerate(fsub_channels, 1):
            fsub_list_text += f"   {idx}. `{ch.get('chat_id')}` → [Link]({ch.get('link', 'https://t.me')})\n"
    else:
        fsub_list_text = "   • कोई चैनल सेट नहीं है।\n"

    text = (
        "👑 **PRO ADMIN DASHBOARD**\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"📊 **Analytics:**\n"
        f"👥 Total Registered Users: **{users_count}**\n"
        f"📢 Active FSub Channels: **{len(fsub_channels)}**\n"
        f"{fsub_list_text}\n"
        "🛠 **Commands Guide:**\n"
        "🔸 `बॉट को चैनल में एडमिन बनाएं` - FSub में अपने आप जुड़ जाएगा\n"
        "🔸 `/addfsub -1001234...` या `@username` - FSub मैन्युअल जोड़ें\n"
        "🔸 `/delfsub` या `/delfsub -1001234...` - FSub चैनल हटाएं\n"
        "🔸 `/broadcast` - किसी मैसेज का रिप्लाई करके ब्रॉडकास्ट करें\n"
        "🔸 `/pin` - ग्रुप/चैनल में किसी मैसेज का रिप्लाई करके पिन करें"
    )
    await message.reply(text, disable_web_page_preview=True)

# --- 7. BROADCAST & PIN MESSAGES ---
@app.on_message(filters.command("broadcast") & filters.private)
async def broadcast_msg(client, message):
    if ADMIN_ID == 0 or message.from_user.id != ADMIN_ID:
        return

    if not message.reply_to_message:
        await message.reply("❌ **एरर:** किसी मैसेज, फोटो या वीडियो का रिप्लाई (Reply) करते हुए `/broadcast` लिखें।")
        return

    status = await message.reply("⏳ **ब्रॉडकास्ट शुरू हो रहा है...**")
    cursor = bot_users_col.find({}, {"user_id": 1})
    success, failed = 0, 0

    for u in cursor:
        try:
            await message.reply_to_message.copy(u["user_id"])
            success += 1
            await asyncio.sleep(0.05)
        except FloodWait as e:
            await asyncio.sleep(e.value)
            try:
                await message.reply_to_message.copy(u["user_id"])
                success += 1
            except Exception:
                failed += 1
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

# --- 8. MANUAL FSUB COMMANDS (Supports Private -100 IDs & Specific Delete) ---
@app.on_message(filters.command("addfsub") & filters.private)
async def add_fsub(client, message):
    if ADMIN_ID == 0 or message.from_user.id != ADMIN_ID:
        return

    if len(message.command) < 2:
        await message.reply("❌ **सही तरीका:**\nPublic: `/addfsub @yourchannel`\nPrivate: `/addfsub -100123456789`")
        return

    channel_input = message.command[1].strip()
    try:
        chat_id = int(channel_input) if channel_input.startswith("-") else channel_input
        resolved_id, title, invite_link = await resolve_valid_invite_link(client, chat_id)

        channels = get_fsub_channels(force_refresh=True)
        updated = False
        for c in channels:
            if c["chat_id"] == resolved_id:
                c["link"] = invite_link
                c["title"] = title
                updated = True
                break
        if not updated:
            channels.append({"chat_id": resolved_id, "link": invite_link, "title": title})

        save_fsub_channels(channels)
        await message.reply(
            f"✅ **Force Subscribe सेट हो गया:** {title}\n"
            f"🆔 **ID:** `{resolved_id}`\n"
            f"🔗 **Link:** {invite_link}\n"
            f"*(Total FSub Channels: {len(channels)})*",
            disable_web_page_preview=True
        )
    except Exception as e:
        await message.reply(
            f"❌ **एरर:** कृपया पहले बॉट को उस चैनल में **Admin (Invite Users परमिशन के साथ)** बनाएं या ID चेक करें।\n"
            f"**Detail:** `{e}`"
        )

@app.on_message(filters.command("delfsub") & filters.private)
async def del_fsub(client, message):
    if ADMIN_ID == 0 or message.from_user.id != ADMIN_ID:
        return

    if len(message.command) > 1:
        target = message.command[1].strip()
        channels = get_fsub_channels(force_refresh=True)
        new_channels = [c for c in channels if str(c.get("chat_id")) != target]
        save_fsub_channels(new_channels)
        await message.reply(f"✅ चैनल `{target}` को FSub लिस्ट से हटा दिया गया है! (Remaining: {len(new_channels)})")
    else:
        save_fsub_channels([])
        await message.reply("✅ **सभी Force Subscribe चैनल्स हटा दिए गए हैं!**")

# --- 9. FSUB CHECK HELPER (Fixes Peer ID Invalid, Broken Links & Alerts Admin) ---
async def check_user_fsub(client: Client, user_id: int) -> list:
    if user_id == ADMIN_ID:
        return []

    fsub_channels = get_fsub_channels()
    if not fsub_channels:
        return []

    not_joined = []
    channels_updated = False

    for fsub in fsub_channels:
        chat_id = fsub["chat_id"]
        link = fsub.get("link", "")

        # Ensure link exists and peer is cached
        if not link or not link.startswith("http"):
            try:
                _, title, new_link = await resolve_valid_invite_link(client, chat_id)
                fsub["link"] = new_link
                fsub["title"] = title
                link = new_link
                channels_updated = True
            except Exception as e:
                await notify_admin_error(
                    client,
                    f"fsub_link_{chat_id}",
                    f"⚠️ **FSub Link Fix Error!**\nचैनल `{chat_id}` का इनवाइट लिंक नहीं मिल पा रहा है।\n**Error:** `{e}`\nकृपया `/delfsub {chat_id}` करें या बॉट को Admin परमिशन दें।"
                )
                continue

        try:
            member = await client.get_chat_member(chat_id, user_id)
            if member.status in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED):
                not_joined.append(fsub)
        except UserNotParticipant:
            not_joined.append(fsub)
        except (ValueError, KeyError, RPCError) as e:
            err_str = str(e)
            # If Peer ID Invalid due to cold in-memory session, warm up peer cache and retry once
            if "PEER_ID_INVALID" in err_str or "Peer id invalid" in err_str:
                try:
                    await client.get_chat(chat_id)
                    member = await client.get_chat_member(chat_id, user_id)
                    if member.status in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED):
                        not_joined.append(fsub)
                    continue
                except UserNotParticipant:
                    not_joined.append(fsub)
                    continue
                except Exception as retry_err:
                    err_str = str(retry_err)

            await notify_admin_error(
                client,
                f"fsub_check_{chat_id}",
                f"🚨 **FSub Join Check Error (Admin Alert)**\n\n"
                f"📢 **Channel ID:** `{chat_id}`\n"
                f"👤 **User ID:** `{user_id}`\n"
                f"❌ **Error:** `{err_str}`\n\n"
                f"💡 **Solution:** बॉट इस चैनल में Admin नहीं है या हटाया जा चुका है। इसे हटाने के लिए `/delfsub {chat_id}` भेजें।"
            )

    if channels_updated:
        save_fsub_channels(fsub_channels)

    return not_joined

# --- 10. START COMMAND (Multi-FSub, Atomic Registration, Refer & Earn) ---
@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    user_id = message.from_user.id
    bot_info = await get_bot_info(client)

    args = message.text.split()
    start_param = args[1] if len(args) > 1 else "start"

    not_joined = await check_user_fsub(client, user_id)
    if not_joined:
        buttons = []
        for i, fsub in enumerate(not_joined, 1):
            ch_title = fsub.get("title") or f"Channel {i}"
            buttons.append([InlineKeyboardButton(f"🔔 Join {ch_title}", url=fsub["link"])])

        buttons.append([
            InlineKeyboardButton(
                "✅ I Have Subscribed",
                url=f"https://t.me/{bot_info['username']}?start={start_param}"
            )
        ])
        await message.reply(
            "🚨 **हमारी सर्विस इस्तेमाल करने के लिए कृपया नीचे दिए गए सभी चैनल जॉइन करें!**\n\n"
            "जॉइन करने के बाद **'✅ I Have Subscribed'** पर क्लिक करें।",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    referrer_id = None
    if start_param.startswith("ref_"):
        try:
            cand_id = int(start_param.split("_")[1])
            if cand_id != user_id:
                referrer_id = cand_id
        except Exception:
            pass

    # Atomic registration prevents duplicate referral exploits
    res = bot_users_col.update_one(
        {"user_id": user_id},
        {
            "$setOnInsert": {
                "user_id": user_id,
                "balance": 0,
                "referral_count": 0,
                "referred_by": referrer_id,
                "join_date": datetime.now()
            }
        },
        upsert=True
    )

    if res.upserted_id and referrer_id:
        ref_update = bot_users_col.update_one(
            {"user_id": referrer_id},
            {"$inc": {"balance": 5, "referral_count": 1}}
        )
        if ref_update.modified_count > 0:
            try:
                await client.send_message(referrer_id, "🎉 **New Referral Joined!**\n💰 **+₹5** आपके अकाउंट में जोड़ दिए गए हैं!")
            except Exception:
                pass

    add_link = f"https://t.me/{bot_info['username']}?startchannel=true&admin=post_messages+edit_messages+delete_messages+invite_users+manage_chat+pin_messages"

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

# --- 11. REFER & EARN CALLBACK LOGIC (Secure Withdrawal + Admin Alert) ---
@app.on_callback_query()
async def callback_handler(client, callback_query):
    user_id = callback_query.from_user.id
    msg = callback_query.message
    data = callback_query.data
    bot_info = await get_bot_info(client)

    if data == "btn_refer":
        user_data = bot_users_col.find_one({"user_id": user_id}) or {}
        balance = user_data.get("balance", 0)
        ref_count = user_data.get("referral_count", 0)
        ref_link = f"https://t.me/{bot_info['username']}?start=ref_{user_id}"

        refer_text = (
            f"🎁 **Refer & Earn Program**\n\n"
            f"Share your link and earn **₹5** per refer!\n\n"
            f"👥 Total Refers: **{ref_count}**\n"
            f"💰 Balance: **₹{balance}**\n\n"
            f"📌 **Your Link:**\n`{ref_link}`\n\n"
            f"⚠️ *Minimum Withdrawal is ₹500.*"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💸 Withdraw (₹500)", callback_data="btn_withdraw")],
            [InlineKeyboardButton("🔙 Back", callback_data="btn_back")]
        ])
        await msg.edit_text(refer_text, reply_markup=keyboard)

    elif data == "btn_withdraw":
        # Atomic balance deduction so user cannot double-withdraw
        updated_user = bot_users_col.find_one_and_update(
            {"user_id": user_id, "balance": {"$gte": 500}},
            {"$inc": {"balance": -500}},
            return_document=ReturnDocument.AFTER
        )
        if not updated_user:
            user_data = bot_users_col.find_one({"user_id": user_id}) or {}
            balance = user_data.get("balance", 0)
            await callback_query.answer(f"❌ Minimum Withdrawal is ₹500!\nYour Current Balance: ₹{balance}", show_alert=True)
        else:
            await callback_query.answer("✅ Withdrawal Request Submitted!\nAdmin को रिक्वेस्ट भेज दी गई है।", show_alert=True)
            if ADMIN_ID:
                user_mention = callback_query.from_user.mention
                await notify_admin_error(
                    client,
                    f"withdraw_{user_id}_{ int(time.time()) }",
                    f"💸 **New Withdrawal Request!**\n\n"
                    f"👤 **User:** {user_mention} (`{user_id}`)\n"
                    f"💰 **Amount:** ₹500\n"
                    f"👥 **Total Referrals:** {updated_user.get('referral_count', 0)}\n"
                    f"💵 **Remaining Balance:** ₹{updated_user.get('balance', 0)}",
                    cooldown=1
                )

    elif data == "btn_back":
        add_link = f"https://t.me/{bot_info['username']}?startchannel=true&admin=post_messages+edit_messages+delete_messages+invite_users+manage_chat+pin_messages"
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

# --- 12. STARTUP WARMUP & NOTIFICATION ---
async def warmup_and_notify():
    await asyncio.sleep(2)
    try:
        await get_bot_info(app)
        # Warm up FSub peer cache so in_memory session never throws PEER_ID_INVALID
        fsub_channels = get_fsub_channels(force_refresh=True)
        updated = False
        for fsub in fsub_channels:
            try:
                _, title, link = await resolve_valid_invite_link(app, fsub["chat_id"])
                if fsub.get("link") != link or fsub.get("title") != title:
                    fsub["link"] = link
                    fsub["title"] = title
                    updated = True
            except Exception as e:
                await notify_admin_error(
                    app,
                    f"startup_fsub_{fsub['chat_id']}",
                    f"⚠️ **Startup FSub Check Failed!**\nChannel ID: `{fsub['chat_id']}`\nError: `{e}`"
                )
        if updated:
            save_fsub_channels(fsub_channels)

        if ADMIN_ID:
            await app.send_message(
                ADMIN_ID,
                f"✅ **REACTION BOT IS ONLINE 24/7!**\n\n"
                f"⏰ **Started At:** `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`\n"
                f"📢 **Loaded FSub Channels:** `{len(fsub_channels)}`\n"
                f"👉 **एडमिन पैनल:** /panel"
            )
    except Exception as e:
        print(f"Startup Warmup Error: {e}")

if __name__ == "__main__":
    threading.Thread(target=run_server, daemon=True).start()
    threading.Thread(target=keep_alive_pinger, daemon=True).start()

    print("Pro Reaction Bot Starting 24/7 Worldwide...")
    app.start()
    loop.create_task(warmup_and_notify())
    from pyrogram import idle
    idle()
    app.stop()
