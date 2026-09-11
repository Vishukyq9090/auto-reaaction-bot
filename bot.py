import asyncio
import os
import threading
from datetime import datetime, timedelta

try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

from flask import Flask
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait, UserNotParticipant
from pyrogram.enums import ChatMemberStatus
from pymongo import MongoClient

# --- 1. Web Server ---
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Auto-Accept Bot (Top 20 Languages + Refer Clickbait) is Running!"

def run_server():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host="0.0.0.0", port=port)

# --- 2. Configs & DB Setup ---
API_ID = int(os.environ.get("API_ID", 12345))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
MONGO_URI = os.environ.get("MONGO_URI", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))

app = Client("AutoAcceptBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

db_client = MongoClient(MONGO_URI)
db = db_client["AutoAcceptBot_DB"]
settings_col = db["settings"]
pending_users_col = db["pending_users"]
schedules_col = db["schedules"]
bot_users_col = db["bot_users"]
global_welcome_col = db["global_welcome"]
global_settings_col = db["global_settings"] # FSub Setting DB

# --- 🌐 3. Multi-Language Dictionary ---
TEXTS = {
    "en": {"start": "👋 **Hello! I am a Smart Auto-Accept Bot.**\n\n**🤖 What I do:**\nI automatically accept join requests.\n\n**📝 How to use:**\n1️⃣ Add me as Admin.\n2️⃣ Type `/admin` in your channel.", "admin_panel": "🎛 **Admin Panel**\n*(Deletes in 15s)*", "promo": "🎉 **Congratulations!**\nYou've been approved in **{chat}**.\n\n🚀 Join our official community 👇", "btn_add": "➕ Add Bot to Channel", "btn_refer": "🎁 Refer & Earn", "btn_lang": "🌐 Language", "not_admin": "❌ You are not an admin!", "accepting": "⏳ Accepting...", "done": "✅ **Completed!** ({count} accepted)", "lang_set": "✅ Language set to English!"},
    "hi": {"start": "👋 **नमस्ते! मैं एक Auto-Accept Bot हूँ।**\n\n**🤖 मैं क्या करता हूँ:**\nमैं जॉइन रिक्वेस्ट अपने आप एक्सेप्ट करता हूँ।\n\n**📝 इस्तेमाल:**\n1️⃣ मुझे चैनल में Admin बनाएं।\n2️⃣ `/admin` भेजें।", "admin_panel": "🎛 **एडमिन पैनल**\n*(15s में डिलीट)*", "promo": "🎉 **बधाई हो!**\nआपको **{chat}** में अप्रूव कर दिया गया है।\n\n🚀 हमारी कम्युनिटी जॉइन करें 👇", "btn_add": "➕ चैनल में जोड़ें", "btn_refer": "🎁 रेफर करें और कमाएं", "btn_lang": "🌐 भाषा (Language)", "not_admin": "❌ आप एडमिन नहीं हैं!", "accepting": "⏳ एक्सेप्ट कर रहा हूँ...", "done": "✅ **पूरा हुआ!** ({count} एक्सेप्ट किए)", "lang_set": "✅ भाषा हिंदी सेट हो गई!"}
}

def get_user_lang(user_id):
    user_data = bot_users_col.find_one({"user_id": user_id})
    return user_data.get("lang", "en") if user_data else "en"

def get_chat_lang(chat_id):
    chat_setting = settings_col.find_one({"chat_id": chat_id})
    return chat_setting.get("lang", "en") if chat_setting else "en"

async def delete_after(msg, delay):
    await asyncio.sleep(delay)
    try:
        await msg.delete()
    except:
        pass

async def is_user_admin(client, chat_id, user_id):
    try:
        member = await client.get_chat_member(chat_id, user_id)
        status_str = str(member.status).lower()
        return "owner" in status_str or "administrator" in status_str or "creator" in status_str
    except:
        return False

# --- ✨ Global One-Time Promo ---
async def send_one_time_promo(client, user_id, chat_id, chat_title):
    if not global_welcome_col.find_one({"user_id": user_id}):
        try:
            lang = get_chat_lang(chat_id)
            promo_text = TEXTS.get(lang, TEXTS["en"])["promo"].format(chat=chat_title)
            promo_keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔥 Join Community 🔥", url="https://t.me/openbook506")]
            ])
            await client.send_message(user_id, promo_text, reply_markup=promo_keyboard)
            global_welcome_col.insert_one({"user_id": user_id})
        except:
            pass

# --- Smart Join Request Handler ---
@app.on_chat_join_request()
async def handle_join_request(client, message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    chat_title = message.chat.title

    chat_setting = settings_col.find_one({"chat_id": chat_id})
    auto_accept = chat_setting.get("auto_accept", True) if chat_setting else True

    if auto_accept:
        try:
            await client.approve_chat_join_request(chat_id, user_id)
            asyncio.create_task(send_one_time_promo(client, user_id, chat_id, chat_title))
        except:
            pass
    else:
        pending_users_col.update_one(
            {"chat_id": chat_id, "user_id": user_id},
            {"$set": {"status": "pending", "chat_title": chat_title}},
            upsert=True
        )

# --- ✨ Force Subscribe Admin Command ---
@app.on_message(filters.command("setfsub") & filters.private)
async def set_fsub(client, message):
    if ADMIN_ID == 0 or message.from_user.id != ADMIN_ID:
        return
    if len(message.command) < 2:
        await message.reply("❌ **सही तरीका:** `/setfsub @yourchannel`\n(हटाने के लिए लिखें: `/setfsub off`)")
        return
    
    channel_username = message.command[1]
    if channel_username.lower() == "off":
        global_settings_col.update_one({"id": "fsub"}, {"$set": {"channel": None}}, upsert=True)
        await message.reply("✅ **Force Subscribe हटा दिया गया है!**")
    else:
        global_settings_col.update_one({"id": "fsub"}, {"$set": {"channel": channel_username}}, upsert=True)
        await message.reply(f"✅ **Force Subscribe सेट हो गया:** {channel_username}")

# --- ✨ Start Command (With FSub Logic) ---
@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    user_id = message.from_user.id
    
    # 🔒 Force Subscribe Check
    fsub_data = global_settings_col.find_one({"id": "fsub"})
    if fsub_data and fsub_data.get("channel"):
        fsub_channel = fsub_data["channel"]
        try:
            member = await client.get_chat_member(fsub_channel, user_id)
            if member.status in [ChatMemberStatus.BANNED, ChatMemberStatus.RESTRICTED]:
                return
        except UserNotParticipant:
            bot_info = await client.get_me()
            fsub_kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔔 Subscribe Now 🔔", url=f"https://t.me/{fsub_channel.replace('@', '')}")],
                [InlineKeyboardButton("✅ I Have Subscribed", url=f"https://t.me/{bot_info.username}?start=start")]
            ])
            await message.reply("🚨 **कृपया बॉट का उपयोग करने से पहले हमारे मुख्य चैनल से जुड़ें!**\n\nसब्सक्राइब करने के बाद 'I Have Subscribed' पर क्लिक करें।", reply_markup=fsub_kb)
            return
        except Exception:
            pass # Ignore if bot is not admin in FSub channel

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
            "lang": "en"
        })

        if referrer_id and referrer_id != user_id:
            bot_users_col.update_one({"user_id": referrer_id}, {"$inc": {"balance": 5, "referral_count": 1}})
            try:
                await client.send_message(referrer_id, "🎉 **New Referral!**\n💰 + ₹5 added to your account!")
            except:
                pass

    lang = get_user_lang(user_id)
    bot_info = await client.get_me()
    add_link = f"https://t.me/{bot_info.username}?startchannel=true&admin=invite_users+delete_messages"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(TEXTS.get(lang, TEXTS["en"])["btn_add"], url=add_link)],
        [InlineKeyboardButton(TEXTS.get(lang, TEXTS["en"])["btn_refer"], callback_data="btn_refer"), 
         InlineKeyboardButton(TEXTS.get(lang, TEXTS["en"])["btn_lang"], callback_data="btn_change_lang")]
    ])
    await message.reply_text(TEXTS.get(lang, TEXTS["en"])["start"], reply_markup=keyboard)

# --- Admin Panel Command ---
@app.on_message(filters.command("admin") & (filters.group | filters.channel))
async def admin_panel(client, message):
    try:
        try:
            await message.delete()
        except:
            pass

        chat_type = str(message.chat.type).lower()
        chat_id = message.chat.id
        user_id = message.from_user.id

        if "channel" not in chat_type:
            if message.from_user and not await is_user_admin(client, chat_id, user_id):
                return

        admin_lang = get_user_lang(user_id)
        settings_col.update_one({"chat_id": chat_id}, {"$set": {"lang": admin_lang}}, upsert=True)
        
        chat_setting = settings_col.find_one({"chat_id": chat_id})
        is_auto_on = chat_setting.get("auto_accept", True) if chat_setting else True
        auto_btn_text = "🟢 Auto-Accept : ON" if is_auto_on else "🔴 Auto-Accept : OFF"

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(auto_btn_text, callback_data="toggle_auto")],
            [InlineKeyboardButton("✅ Accept", callback_data="btn_acceptall"), 
             InlineKeyboardButton("⏳ Schedule", callback_data="btn_show_schedule")],
            [InlineKeyboardButton("🔗 Link", callback_data="btn_link")]
        ])

        msg = await message.reply_text(TEXTS.get(admin_lang, TEXTS["en"])["admin_panel"], reply_markup=keyboard)
        asyncio.create_task(delete_after(msg, 15))
    except Exception as e:
        pass

# --- Button Click Handler ---
@app.on_callback_query()
async def callback_handler(client, callback_query):
    try:
        user_id = callback_query.from_user.id
        chat_id = callback_query.message.chat.id
        msg = callback_query.message
        data = callback_query.data
        lang = get_user_lang(user_id)

        if data == "btn_change_lang":
            lang_kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🇬🇧 English", callback_data="setlang_en"), InlineKeyboardButton("🇮🇳 हिन्दी", callback_data="setlang_hi")],
                [InlineKeyboardButton("🔙 Back", callback_data="btn_start_menu")]
            ])
            await msg.edit_text("**Please select your language:**", reply_markup=lang_kb)
            return

        elif data.startswith("setlang_"):
            new_lang = data.split("_")[1]
            bot_users_col.update_one({"user_id": user_id}, {"$set": {"lang": new_lang}}, upsert=True)
            await callback_query.answer(TEXTS.get(new_lang, TEXTS["en"])["lang_set"], show_alert=True)
            bot_info = await client.get_me()
            add_link = f"https://t.me/{bot_info.username}?startchannel=true&admin=invite_users+delete_messages"
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(TEXTS.get(new_lang, TEXTS["en"])["btn_add"], url=add_link)],
                [InlineKeyboardButton(TEXTS.get(new_lang, TEXTS["en"])["btn_refer"], callback_data="btn_refer"), 
                 InlineKeyboardButton(TEXTS.get(new_lang, TEXTS["en"])["btn_lang"], callback_data="btn_change_lang")]
            ])
            await msg.edit_text(TEXTS.get(new_lang, TEXTS["en"])["start"], reply_markup=keyboard)
            return

        if data == "btn_refer":
            bot_info = await client.get_me()
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
                [InlineKeyboardButton("🔙 Back", callback_data="btn_start_menu")]
            ])
            await msg.edit_text(refer_text, reply_markup=keyboard)
            return

        elif data == "btn_withdraw":
            user_data = bot_users_col.find_one({"user_id": user_id})
            balance = user_data.get("balance", 0) if user_data else 0
            if balance < 500:
                await callback_query.answer(f"❌ Minimum Withdrawal is ₹500!\nYour Current Balance: ₹{balance}", show_alert=True)
            else:
                await callback_query.answer("✅ Withdrawal Request Submitted!\n\nYour account is under review for fake/bot referrals.", show_alert=True)
            return

        elif data == "btn_start_menu":
            bot_info = await client.get_me()
            add_link = f"https://t.me/{bot_info.username}?startchannel=true&admin=invite_users+delete_messages"
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(TEXTS.get(lang, TEXTS["en"])["btn_add"], url=add_link)],
                [InlineKeyboardButton(TEXTS.get(lang, TEXTS["en"])["btn_refer"], callback_data="btn_refer"), 
                 InlineKeyboardButton(TEXTS.get(lang, TEXTS["en"])["btn_lang"], callback_data="btn_change_lang")]
            ])
            await msg.edit_text(TEXTS.get(lang, TEXTS["en"])["start"], reply_markup=keyboard)
            return

        if not await is_user_admin(client, chat_id, user_id):
            await callback_query.answer(TEXTS.get(lang, TEXTS["en"])["not_admin"], show_alert=True)
            return

        admin_lang = get_chat_lang(chat_id)

        if data == "toggle_auto":
            chat_setting = settings_col.find_one({"chat_id": chat_id})
            current_status = chat_setting.get("auto_accept", True) if chat_setting else True
            new_status = not current_status
            settings_col.update_one({"chat_id": chat_id}, {"$set": {"auto_accept": new_status}}, upsert=True)
            auto_btn_text = "🟢 Auto-Accept : ON" if new_status else "🔴 Auto-Accept : OFF"
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(auto_btn_text, callback_data="toggle_auto")],
                [InlineKeyboardButton("✅ Accept", callback_data="btn_acceptall"), InlineKeyboardButton("⏳ Schedule", callback_data="btn_show_schedule")],
                [InlineKeyboardButton("🔗 Link", callback_data="btn_link")]
            ])
            await msg.edit_reply_markup(reply_markup=keyboard)
            await callback_query.answer(f"Auto-Accept is {'ON' if new_status else 'OFF'}", show_alert=False)

        elif data == "btn_show_schedule":
            sch_keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("5 Min", callback_data="sch_5"), InlineKeyboardButton("15 Min", callback_data="sch_15")],
                [InlineKeyboardButton("30 Min", callback_data="sch_30"), InlineKeyboardButton("60 Min", callback_data="sch_60")],
                [InlineKeyboardButton("🔙 Back", callback_data="btn_back")]
            ])
            await msg.edit_text("⏳ **Schedule Time:**", reply_markup=sch_keyboard)

        elif data.startswith("sch_"):
            minutes = int(data.split("_")[1])
            target_time = datetime.now() + timedelta(minutes=minutes)
            schedules_col.insert_one({"chat_id": chat_id, "run_at": target_time})
            await msg.edit_text(f"✅ Schedule set for {minutes} Mins!\n*(Deletes in 5s)*")
            asyncio.create_task(delete_after(msg, 5))

        elif data == "btn_back":
            chat_setting = settings_col.find_one({"chat_id": chat_id})
            is_auto_on = chat_setting.get("auto_accept", True) if chat_setting else True
            auto_btn_text = "🟢 Auto-Accept : ON" if is_auto_on else "🔴 Auto-Accept : OFF"
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(auto_btn_text, callback_data="toggle_auto")],
                [InlineKeyboardButton("✅ Accept", callback_data="btn_acceptall"), InlineKeyboardButton("⏳ Schedule", callback_data="btn_show_schedule")],
                [InlineKeyboardButton("🔗 Link", callback_data="btn_link")]
            ])
            await msg.edit_text(TEXTS.get(admin_lang, TEXTS["en"])["admin_panel"], reply_markup=keyboard)

        elif data == "btn_acceptall":
            await callback_query.answer(TEXTS.get(admin_lang, TEXTS["en"])["accepting"], show_alert=False)
            await msg.edit_text(TEXTS.get(admin_lang, TEXTS["en"])["accepting"])
            pending = list(pending_users_col.find({"chat_id": chat_id}))
            success_count = 0
            for p in pending:
                chat_title = p.get("chat_title", "Channel")
                try:
                    await client.approve_chat_join_request(chat_id, p["user_id"])
                    success_count += 1
                    asyncio.create_task(send_one_time_promo(client, p["user_id"], chat_id, chat_title))
                except:
                    pass
                finally:
                    pending_users_col.delete_one({"_id": p["_id"]})
                await asyncio.sleep(1)
            final_text = TEXTS.get(admin_lang, TEXTS["en"])["done"].format(count=success_count)
            await msg.edit_text(final_text)
            asyncio.create_task(delete_after(msg, 5))

        elif data == "btn_link":
            invite_link = await client.create_chat_invite_link(chat_id=chat_id, creates_join_request=True)
            await msg.edit_text(f"✅ **Link:**\n{invite_link.invite_link}\n*(Deletes in 15s)*")
            asyncio.create_task(delete_after(msg, 15))

    except Exception as e:
        pass

# --- Background Schedule Tracker ---
async def schedule_tracker():
    while True:
        try:
            now = datetime.now()
            ready_schedules = list(schedules_col.find({"run_at": {"$lte": now}}))
            for sch in ready_schedules:
                chat_id = sch["chat_id"]
                pending = list(pending_users_col.find({"chat_id": chat_id}))
                success_count = 0
                if pending:
                    for p in pending:
                        chat_title = p.get("chat_title", "Channel")
                        try:
                            await app.approve_chat_join_request(chat_id, p["user_id"])
                            success_count += 1
                            asyncio.create_task(send_one_time_promo(app, p["user_id"], chat_id, chat_title))
                        except:
                            pass
                        finally:
                            pending_users_col.delete_one({"_id": p["_id"]})
                        await asyncio.sleep(1)
                schedules_col.delete_one({"_id": sch["_id"]})
                if success_count > 0:
                    admin_lang = get_chat_lang(chat_id)
                    done_text = TEXTS.get(admin_lang, TEXTS["en"])["done"].format(count=success_count)
                    done_msg = await app.send_message(chat_id, done_text)
                    asyncio.create_task(delete_after(done_msg, 5))
        except Exception:
            pass
        await asyncio.sleep(30)


# --- ✨ NEW: Channel Me Admin Bante Hi Message Bhejna ---
@app.on_chat_member_updated(filters.channel | filters.group)
async def bot_added_as_admin(client, update):
    try:
        bot_info = await client.get_me()
        # Check if the updated member is the bot itself
        if update.new_chat_member and update.new_chat_member.user.id == bot_info.id:
            status = str(update.new_chat_member.status).lower()
            if "administrator" in status or "owner" in status:
                await client.send_message(
                    update.chat.id,
                    "✅ **Bot Successfully Added as Admin!**\n\n"
                    "🟢 **Auto-Accept:** ON\n"
                    "🟢 **Auto-Reactions:** ON\n\n"
                    "👉 Settings बदलने के लिए यहाँ `/admin` भेजें।"
                )
    except Exception:
        pass

# --- ✨ Auto-Reaction with Caption Mood (Fixed) ---
def get_mood_emoji(text):
    text = str(text).lower()
    
    if any(word in text for word in ['sad', 'bad', 'crying', 'दुखी', 'खराब', 'sorry']):
        return "😢"
    elif any(word in text for word in ['funny', 'haha', 'lol', 'joke', 'मजाक', '😂']):
        return "😂"
    elif any(word in text for word in ['angry', 'mad', 'wtf', 'गुस्सा', 'hate']):
        return "😡"
    else:
        # Default Positive Reaction 
        return "👍"

# Filter update kiya gaya (Taaki Photo/Media bina text wale pe bhi kaam kare)
@app.on_message(filters.channel | filters.group)
async def auto_reaction_handler(client, message):
    # Text ya Caption nikaalein (Agar nahi hai toh blank manega)
    text_content = message.text or message.caption or ""
    
    reaction_emoji = get_mood_emoji(text_content)
    
    try:
        await client.send_reaction(
            chat_id=message.chat.id,
            message_id=message.id,
            emoji=reaction_emoji
        )
    except Exception as e:
        print(f"Reaction Error: {e}")

if __name__ == "__main__":
    threading.Thread(target=run_server, daemon=True).start()
    print("Bot is ready Worldwide! (With Reactions & Fsub Mode)")
    loop.create_task(schedule_tracker())
    app.run()
