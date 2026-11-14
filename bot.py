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
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant
from pyrogram.enums import ChatMemberStatus
from pymongo import MongoClient

# --- 1. Web Server & Auto Self-Pinger for 24/7 Keep-Alive ---
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Pro Reaction & FSub Bot is Running Perfectly 24/7!"

def run_server():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host="0.0.0.0", port=port)

def keep_alive_pinger():
    """Pings the server every 4 minutes so it never sleeps on Render or Cloud hosts."""
    time.sleep(15)
    port = int(os.environ.get("PORT", 8080))
    ping_url = os.environ.get("RENDER_EXTERNAL_URL") or f"http://127.0.0.1:{port}/"
    while True:
        try:
            urllib.request.urlopen(ping_url, timeout=10)
        except Exception:
            pass
        time.sleep(240)

# --- 2. Configurations & DB Setup ---
API_ID = int(str(os.environ.get("API_ID", "12345")).strip() or 12345)
API_HASH = os.environ.get("API_HASH", "").strip()
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
MONGO_URI = os.environ.get("MONGO_URI", "").strip()
ADMIN_ID = int(str(os.environ.get("ADMIN_ID", "7412791600")).strip() or 7412791600)

# in_memory=True prevents SQLite session file lock errors on 24/7 restarts
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

# --- 🚀 3. HYBRID REACTION SYSTEM (React or Reply) ---
async def safe_react_or_reply(message, emoji):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/setMessageReaction"
    data = {
        "chat_id": message.chat.id,
        "message_id": message.id,
        "reaction": [{"type": "emoji", "emoji": emoji}]
    }
    
    def make_request():
        try:
            req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'), headers={'Content-Type': 'application/json'})
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

# --- 🤖 4. AI Mood Analyzer (50+ Emojis Supported) ---
def get_mood_emoji(text):
    text = str(text).lower
