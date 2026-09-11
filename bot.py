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
from pyrogram.errors import FloodWait
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

# --- 🌐 3. Multi-Language Dictionary (Top 20 Worldwide) ---
TEXTS = {
    "en": {"start": "👋 **Hello! I am a Smart Auto-Accept Bot.**\n\n**🤖 What I do:**\nI automatically accept join requests.\n\n**📝 How to use:**\n1️⃣ Add me as Admin.\n2️⃣ Type `/admin` in your channel.", "admin_panel": "🎛 **Admin Panel**\n*(Deletes in 15s)*", "promo": "🎉 **Congratulations!**\nYou've been approved in **{chat}**.\n\n🚀 Join our official community 👇", "btn_add": "➕ Add Bot to Channel", "btn_refer": "🎁 Refer & Earn", "btn_lang": "🌐 Language", "not_admin": "❌ You are not an admin!", "accepting": "⏳ Accepting...", "done": "✅ **Completed!** ({count} accepted)", "lang_set": "✅ Language set to English!"},
    "hi": {"start": "👋 **नमस्ते! मैं एक Auto-Accept Bot हूँ।**\n\n**🤖 मैं क्या करता हूँ:**\nमैं जॉइन रिक्वेस्ट अपने आप एक्सेप्ट करता हूँ।\n\n**📝 इस्तेमाल:**\n1️⃣ मुझे चैनल में Admin बनाएं।\n2️⃣ `/admin` भेजें।", "admin_panel": "🎛 **एडमिन पैनल**\n*(15s में डिलीट)*", "promo": "🎉 **बधाई हो!**\nआपको **{chat}** में अप्रूव कर दिया गया है।\n\n🚀 हमारी कम्युनिटी जॉइन करें 👇", "btn_add": "➕ चैनल में जोड़ें", "btn_refer": "🎁 रेफर करें और कमाएं", "btn_lang": "🌐 भाषा (Language)", "not_admin": "❌ आप एडमिन नहीं हैं!", "accepting": "⏳ एक्सेप्ट कर रहा हूँ...", "done": "✅ **पूरा हुआ!** ({count} एक्सेप्ट किए)", "lang_set": "✅ भाषा हिंदी सेट हो गई!"},
    "es": {"start": "👋 **¡Hola! Soy un Bot de Auto-Aceptación.**\n\n**🤖 Qué hago:**\nAcepto solicitudes automáticamente.\n\n**📝 Cómo usar:**\n1️⃣ Añádeme como Admin.\n2️⃣ Escribe `/admin`.", "admin_panel": "🎛 **Panel de Administración**", "promo": "🎉 **¡Felicidades!**\nAprobado en **{chat}**.\n\n🚀 Únete a nuestra comunidad 👇", "btn_add": "➕ Añadir al Canal", "btn_refer": "🎁 Referir y Ganar", "btn_lang": "🌐 Idioma", "not_admin": "❌ ¡No eres administrador!", "accepting": "⏳ Aceptando...", "done": "✅ **¡Completado!** ({count} aceptados)", "lang_set": "✅ ¡Idioma Español configurado!"},
    "fr": {"start": "👋 **Bonjour! Je suis un Bot d'Auto-Acceptation.**\n\n**🤖 Ce que je fais:**\nJ'accepte automatiquement les demandes.\n\n**📝 Utilisation:**\n1️⃣ Ajoutez-moi comme Admin.\n2️⃣ Tapez `/admin`.", "admin_panel": "🎛 **Panneau d'administration**", "promo": "🎉 **Félicitations!**\nApprouvé dans **{chat}**.\n\n🚀 Rejoignez notre communauté 👇", "btn_add": "➕ Ajouter au Canal", "btn_refer": "🎁 Parrainer et Gagner", "btn_lang": "🌐 Langue", "not_admin": "❌ Vous n'êtes pas administrateur!", "accepting": "⏳ Acceptation...", "done": "✅ **Terminé!** ({count} acceptés)", "lang_set": "✅ Langue Française configurée!"},
    "ar": {"start": "👋 **مرحباً! أنا روبوت القبول التلقائي.**\n\n**🤖 ماذا أفعل:**\nأقبل الطلبات تلقائياً.\n\n**📝 الاستخدام:**\n1️⃣ أضفني كمسؤول.\n2️⃣ اكتب `/admin`.", "admin_panel": "🎛 **لوحة الإدارة**", "promo": "🎉 **تهانينا!**\nتمت الموافقة في **{chat}**.\n\n🚀 انضم لمجتمعنا 👇", "btn_add": "➕ إضافة للقناة", "btn_refer": "🎁 أشر واربح", "btn_lang": "🌐 اللغة", "not_admin": "❌ أنت لست مسؤولاً!", "accepting": "⏳ جاري القبول...", "done": "✅ **مكتمل!** ({count} مقبول)", "lang_set": "✅ تم تعيين اللغة العربية!"},
    "ru": {"start": "👋 **Привет! Я Бот Авто-Принятия.**\n\n**🤖 Что я делаю:**\nАвтоматически принимаю заявки.\n\n**📝 Использование:**\n1️⃣ Добавьте как Админа.\n2️⃣ Введите `/admin`.", "admin_panel": "🎛 **Панель Админа**", "promo": "🎉 **Поздравляем!**\nВы приняты в **{chat}**.\n\n🚀 Присоединяйтесь к нам 👇", "btn_add": "➕ Добавить в Канал", "btn_refer": "🎁 Пригласить", "btn_lang": "🌐 Язык", "not_admin": "❌ Вы не админ!", "accepting": "⏳ Принятие...", "done": "✅ **Готово!** ({count} принято)", "lang_set": "✅ Русский язык установлен!"},
    "pt": {"start": "👋 **Olá! Sou um Bot de Auto-Aceitação.**\n\n**🤖 O que eu faço:**\nAceito solicitações automaticamente.\n\n**📝 Como usar:**\n1️⃣ Me adicione como Admin.\n2️⃣ Digite `/admin`.", "admin_panel": "🎛 **Painel de Admin**", "promo": "🎉 **Parabéns!**\nAprovado em **{chat}**.\n\n🚀 Junte-se a nós 👇", "btn_add": "➕ Adicionar ao Canal", "btn_refer": "🎁 Indicar e Ganhar", "btn_lang": "🌐 Idioma", "not_admin": "❌ Você não é administrador!", "accepting": "⏳ Aceitando...", "done": "✅ **Concluído!** ({count} aceitos)", "lang_set": "✅ Idioma Português definido!"},
    "zh": {"start": "👋 **你好！我是自动通过机器人。**\n\n**🤖 我的功能:**\n自动通过加入请求。\n\n**📝 使用方法:**\n1️⃣ 将我设为管理员。\n2️⃣ 发送 `/admin`。", "admin_panel": "🎛 **管理面板**", "promo": "🎉 **恭喜！**\n您已加入 **{chat}**。\n\n🚀 加入我们的社区 👇", "btn_add": "➕ 添加到频道", "btn_refer": "🎁 推荐并赚取", "btn_lang": "🌐 语言", "not_admin": "❌ 您不是管理员！", "accepting": "⏳ 正在通过...", "done": "✅ **完成！** (已通过 {count})", "lang_set": "✅ 已设置为中文！"},
    "de": {"start": "👋 **Hallo! Ich bin ein Auto-Accept-Bot.**\n\n**🤖 Was ich tue:**\nAkzeptiert Anfragen automatisch.\n\n**📝 Nutzung:**\n1️⃣ Als Admin hinzufügen.\n2️⃣ `/admin` tippen.", "admin_panel": "🎛 **Admin-Panel**", "promo": "🎉 **Glückwunsch!**\nGenehmigt in **{chat}**.\n\n🚀 Tritt uns bei 👇", "btn_add": "➕ Zum Kanal hinzufügen", "btn_refer": "🎁 Empfehlen", "btn_lang": "🌐 Sprache", "not_admin": "❌ Du bist kein Admin!", "accepting": "⏳ Akzeptiere...", "done": "✅ **Fertig!** ({count} akzeptiert)", "lang_set": "✅ Deutsch als Sprache eingestellt!"},
    "ja": {"start": "👋 **こんにちは！自動承認ボットです。**\n\n**🤖 機能:**\nリクエストを自動承認します。\n\n**📝 使い方:**\n1️⃣ 管理者として追加。\n2️⃣ `/admin` と入力。", "admin_panel": "🎛 **管理パネル**", "promo": "🎉 **おめでとう！**\n**{chat}** に承認されました。\n\n🚀 コミュニティに参加 👇", "btn_add": "➕ チャンネルに追加", "btn_refer": "🎁 友達紹介", "btn_lang": "🌐 言語", "not_admin": "❌ 管理者ではありません！", "accepting": "⏳ 承認中...", "done": "✅ **完了！** ({count} 承認)", "lang_set": "✅ 日本語に設定しました！"},
    "bn": {"start": "👋 **হ্যালো! আমি অটো-অ্যাক্সেপ্ট বট।**\n\n**🤖 আমি যা করি:**\nস্বয়ংক্রিয়ভাবে রিকোয়েস্ট অ্যাক্সেপ্ট করি।\n\n**📝 ব্যবহার:**\n1️⃣ অ্যাডমিন হিসেবে যুক্ত করুন।\n2️⃣ `/admin` টাইপ করুন।", "admin_panel": "🎛 **অ্যাডমিন প্যানেল**", "promo": "🎉 **অভিনন্দন!**\n**{chat}** এ অনুমোদিত।\n\n🚀 আমাদের সাথে যুক্ত হন 👇", "btn_add": "➕ চ্যানেলে যুক্ত করুন", "btn_refer": "🎁 রেফার করুন", "btn_lang": "🌐 ভাষা", "not_admin": "❌ আপনি অ্যাডমিন নন!", "accepting": "⏳ অ্যাক্সেপ্ট করা হচ্ছে...", "done": "✅ **সম্পূর্ণ!** ({count} অ্যাক্সেপ্ট)", "lang_set": "✅ ভাষা বাংলা সেট করা হয়েছে!"},
    "ur": {"start": "👋 **ہیلو! میں آٹو ایکسیپٹ بوٹ ہوں۔**\n\n**🤖 میرا کام:**\nخودکار طور پر درخواستیں منظور کرنا۔\n\n**📝 استعمال:**\n1️⃣ مجھے ایڈمن بنائیں۔\n2️⃣ `/admin` لکھیں۔", "admin_panel": "🎛 **ایڈمن پینل**", "promo": "🎉 **مبارک ہو!**\n**{chat}** میں منظوری مل گئی۔\n\n🚀 ہماری کمیونٹی جوائن کریں 👇", "btn_add": "➕ چینل میں شامل کریں", "btn_refer": "🎁 ریفر کریں", "btn_lang": "🌐 زبان", "not_admin": "❌ آپ ایڈمن نہیں ہیں!", "accepting": "⏳ منظور ہو رہا ہے...", "done": "✅ **مکمل!** ({count} منظور)", "lang_set": "✅ زبان اردو سیٹ ہو گئی!"},
    "id": {"start": "👋 **Halo! Saya Bot Auto-Accept.**\n\n**🤖 Tugas saya:**\nMenerima permintaan secara otomatis.\n\n**📝 Cara pakai:**\n1️⃣ Jadikan Admin.\n2️⃣ Ketik `/admin`.", "admin_panel": "🎛 **Panel Admin**", "promo": "🎉 **Selamat!**\nDisetujui di **{chat}**.\n\n🚀 Bergabunglah bersama kami 👇", "btn_add": "➕ Tambah ke Channel", "btn_refer": "🎁 Referensikan", "btn_lang": "🌐 Bahasa", "not_admin": "❌ Anda bukan admin!", "accepting": "⏳ Menerima...", "done": "✅ **Selesai!** ({count} diterima)", "lang_set": "✅ Bahasa Indonesia diatur!"},
    "tr": {"start": "👋 **Merhaba! Otomatik Kabul Botuyum.**\n\n**🤖 Ne yaparım:**\nİstekleri otomatik kabul ederim.\n\n**📝 Kullanım:**\n1️⃣ Yönetici yapın.\n2️⃣ `/admin` yazın.", "admin_panel": "🎛 **Yönetici Paneli**", "promo": "🎉 **Tebrikler!**\n**{chat}** kanalında onaylandınız.\n\n🚀 Topluluğumuza katılın 👇", "btn_add": "➕ Kanala Ekle", "btn_refer": "🎁 Tavsiye Et", "btn_lang": "🌐 Dil", "not_admin": "❌ Yönetici değilsiniz!", "accepting": "⏳ Kabul ediliyor...", "done": "✅ **Tamamlandı!** ({count} kabul)", "lang_set": "✅ Dil Türkçe ayarlandı!"},
    "ko": {"start": "👋 **안녕하세요! 자동 승인 봇입니다.**\n\n**🤖 기능:**\n가입 요청 자동 승인.\n\n**📝 사용법:**\n1️⃣ 관리자로 추가.\n2️⃣ `/admin` 입력.", "admin_panel": "🎛 **관리자 패널**", "promo": "🎉 **축하합니다!**\n**{chat}** 에 승인되었습니다.\n\n🚀 커뮤니티 참여 👇", "btn_add": "➕ 채널에 추가", "btn_refer": "🎁 친구 초대", "btn_lang": "🌐 언어", "not_admin": "❌ 관리자가 아닙니다!", "accepting": "⏳ 승인 중...", "done": "✅ **완료!** ({count} 승인)", "lang_set": "✅ 한국어로 설정되었습니다!"},
    "vi": {"start": "👋 **Xin chào! Tôi là Bot Tự Động Duyệt.**\n\n**🤖 Chức năng:**\nTự động duyệt yêu cầu.\n\n**📝 Cách dùng:**\n1️⃣ Thêm làm Quản trị viên.\n2️⃣ Gõ `/admin`.", "admin_panel": "🎛 **Bảng điều khiển**", "promo": "🎉 **Chúc mừng!**\nĐược duyệt tại **{chat}**.\n\n🚀 Tham gia cộng đồng 👇", "btn_add": "➕ Thêm vào Kênh", "btn_refer": "🎁 Giới thiệu", "btn_lang": "🌐 Ngôn ngữ", "not_admin": "❌ Bạn không phải là admin!", "accepting": "⏳ Đang duyệt...", "done": "✅ **Hoàn tất!** ({count} đã duyệt)", "lang_set": "✅ Đã cài đặt Tiếng Việt!"},
    "it": {"start": "👋 **Ciao! Sono un Bot di Auto-Accettazione.**\n\n**🤖 Cosa faccio:**\nAccetto automaticamente le richieste.\n\n**📝 Uso:**\n1️⃣ Aggiungimi come Admin.\n2️⃣ Digita `/admin`.", "admin_panel": "🎛 **Pannello Admin**", "promo": "🎉 **Congratulazioni!**\nApprovato in **{chat}**.\n\n🚀 Unisciti alla community 👇", "btn_add": "➕ Aggiungi al Canale", "btn_refer": "🎁 Invita e Guadagna", "btn_lang": "🌐 Lingua", "not_admin": "❌ Non sei admin!", "accepting": "⏳ Accettazione...", "done": "✅ **Fatto!** ({count} accettati)", "lang_set": "✅ Lingua Italiana impostata!"},
    "th": {"start": "👋 **สวัสดี! ฉันคือบอทอนุมัติอัตโนมัติ**\n\n**🤖 หน้าที่:**\nอนุมัติคำขออัตโนมัติ\n\n**📝 วิธีใช้:**\n1️⃣ เพิ่มเป็นผู้ดูแล\n2️⃣ พิมพ์ `/admin`", "admin_panel": "🎛 **แผงควบคุม**", "promo": "🎉 **ยินดีด้วย!**\nอนุมัติใน **{chat}**\n\n🚀 เข้าร่วมกับเรา 👇", "btn_add": "➕ เพิ่มลงในช่อง", "btn_refer": "🎁 แนะนำเพื่อน", "btn_lang": "🌐 ภาษา", "not_admin": "❌ คุณไม่ใช่แอดมิน!", "accepting": "⏳ กำลังอนุมัติ...", "done": "✅ **เสร็จสิ้น!** (อนุมัติ {count})", "lang_set": "✅ ตั้งค่าภาษาไทยแล้ว!"},
    "fa": {"start": "👋 **سلام! من ربات تایید خودکار هستم.**\n\n**🤖 کار من:**\nتایید خودکار درخواست‌ها.\n\n**📝 نحوه استفاده:**\n1️⃣ ادمینم کنید.\n2️⃣ بنویسید `/admin`.", "admin_panel": "🎛 **پنل مدیریت**", "promo": "🎉 **تبریک!**\nدر **{chat}** تایید شدید.\n\n🚀 به ما بپیوندید 👇", "btn_add": "➕ افزودن به کانال", "btn_refer": "🎁 معرفی و کسب درآمد", "btn_lang": "🌐 زبان", "not_admin": "❌ شما ادمین نیستید!", "accepting": "⏳ در حال تایید...", "done": "✅ **انجام شد!** ({count} تایید)", "lang_set": "✅ زبان فارسی تنظیم شد!"},
    "sw": {"start": "👋 **Hujambo! Mimi ni Bot ya Kukubali Kiotomatiki.**\n\n**🤖 Kazi yangu:**\nKukubali maombi kiotomatiki.\n\n**📝 Matumizi:**\n1️⃣ Niweke kama Admin.\n2️⃣ Andika `/admin`.", "admin_panel": "🎛 **Jopo la Admin**", "promo": "🎉 **Hongera!**\nUmekubaliwa katika **{chat}**.\n\n🚀 Jiunge na jamii yetu 👇", "btn_add": "➕ Ongeza kwenye Kituo", "btn_refer": "🎁 Alika Marafiki", "btn_lang": "🌐 Lugha", "not_admin": "❌ Wewe sio admin!", "accepting": "⏳ Inakubali...", "done": "✅ **Imekamilika!** ({count} zimekubaliwa)", "lang_set": "✅ Lugha ya Swahili imewekwa!"}
}

def get_user_lang(user_id):
    user_data = bot_users_col.find_one({"user_id": user_id})
    return user_data.get("lang", "en") if user_data else "en"

def get_chat_lang(chat_id):
    chat_setting = settings_col.find_one({"chat_id": chat_id})
    return chat_setting.get("lang", "en") if chat_setting else "en"

# --- Error Logger ---
async def send_admin_log(client, title, description):
    if ADMIN_ID != 0:
        try:
            await client.send_message(ADMIN_ID, f"⚠️ **{title}** ⚠️\n\n{description}")
        except:
            pass

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
            promo_text = TEXTS[lang]["promo"].format(chat=chat_title)
            promo_keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔥 Join @openbook506 🔥", url="https://t.me/openbook506")]
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

# --- ✨ Start Command ---
@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    user_id = message.from_user.id
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

        # 🎁 Refer Logic - Add ₹5 per refer
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
        [InlineKeyboardButton(TEXTS[lang]["btn_add"], url=add_link)],
        [InlineKeyboardButton(TEXTS[lang]["btn_refer"], callback_data="btn_refer"), 
         InlineKeyboardButton(TEXTS[lang]["btn_lang"], callback_data="btn_change_lang")],
        [InlineKeyboardButton("🔥 Join Our Channel 🔥", url="https://t.me/openbook506")]
    ])
    await message.reply_text(TEXTS[lang]["start"], reply_markup=keyboard)

# --- Broadcast Command (Only YOU) ---
@app.on_message(filters.command("broadcast") & filters.private)
async def broadcast_message(client, message):
    if ADMIN_ID == 0 or message.from_user.id != ADMIN_ID:
        return
    try:
        await message.delete()
    except:
        pass
    if not message.reply_to_message:
        return

    status_msg = await message.reply_text("⏳ **Broadcasting...**")
    users = list(bot_users_col.find({}))
    success, failed = 0, 0
    
    for u in users:
        try:
            await message.reply_to_message.copy(u["user_id"])
            success += 1
            await asyncio.sleep(0.1)
        except FloodWait as e:
            await asyncio.sleep(e.value + 2)
            try:
                await message.reply_to_message.copy(u["user_id"])
                success += 1
            except:
                failed += 1
        except:
            failed += 1

    await status_msg.edit_text(f"✅ **Broadcast Done!**\nSuccess: {success}\nFailed: {failed}")
    asyncio.create_task(delete_after(status_msg, 15))

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

        msg = await message.reply_text(TEXTS[admin_lang]["admin_panel"], reply_markup=keyboard)
        asyncio.create_task(delete_after(msg, 15))
    except Exception as e:
        await send_admin_log(client, "/admin Error", f"Chat: {message.chat.id}\nError: `{e}`")

# --- Button Click Handler ---
@app.on_callback_query()
async def callback_handler(client, callback_query):
    try:
        user_id = callback_query.from_user.id
        chat_id = callback_query.message.chat.id
        msg = callback_query.message
        data = callback_query.data
        lang = get_user_lang(user_id)

        # --- 🌐 Language Selector (Top 20 Worldwide) ---
        if data == "btn_change_lang":
            lang_kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🇬🇧 English", callback_data="setlang_en"), InlineKeyboardButton("🇮🇳 हिन्दी", callback_data="setlang_hi")],
                [InlineKeyboardButton("🇪🇸 Español", callback_data="setlang_es"), InlineKeyboardButton("🇫🇷 Français", callback_data="setlang_fr")],
                [InlineKeyboardButton("🇸🇦 العربية", callback_data="setlang_ar"), InlineKeyboardButton("🇷🇺 Русский", callback_data="setlang_ru")],
                [InlineKeyboardButton("🇵🇹 Português", callback_data="setlang_pt"), InlineKeyboardButton("🇨🇳 中文", callback_data="setlang_zh")],
                [InlineKeyboardButton("🇩🇪 Deutsch", callback_data="setlang_de"), InlineKeyboardButton("🇯🇵 日本語", callback_data="setlang_ja")],
                [InlineKeyboardButton("🇧🇩 বাংলা", callback_data="setlang_bn"), InlineKeyboardButton("🇵🇰 اردو", callback_data="setlang_ur")],
                [InlineKeyboardButton("🇮🇩 Bahasa", callback_data="setlang_id"), InlineKeyboardButton("🇹🇷 Türkçe", callback_data="setlang_tr")],
                [InlineKeyboardButton("🇰🇷 한국어", callback_data="setlang_ko"), InlineKeyboardButton("🇻🇳 Tiếng Việt", callback_data="setlang_vi")],
                [InlineKeyboardButton("🇮🇹 Italiano", callback_data="setlang_it"), InlineKeyboardButton("🇹🇭 ไทย", callback_data="setlang_th")],
                [InlineKeyboardButton("🇮🇷 فارسی", callback_data="setlang_fa"), InlineKeyboardButton("🇰🇪 Swahili", callback_data="setlang_sw")],
                [InlineKeyboardButton("🔙 Back", callback_data="btn_start_menu")]
            ])
            await msg.edit_text("**Please select your language:**", reply_markup=lang_kb)
            return

        elif data.startswith("setlang_"):
            new_lang = data.split("_")[1]
            bot_users_col.update_one({"user_id": user_id}, {"$set": {"lang": new_lang}}, upsert=True)
            await callback_query.answer(TEXTS[new_lang]["lang_set"], show_alert=True)
            
            bot_info = await client.get_me()
            add_link = f"https://t.me/{bot_info.username}?startchannel=true&admin=invite_users+delete_messages"
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(TEXTS[new_lang]["btn_add"], url=add_link)],
                [InlineKeyboardButton(TEXTS[new_lang]["btn_refer"], callback_data="btn_refer"), 
                 InlineKeyboardButton(TEXTS[new_lang]["btn_lang"], callback_data="btn_change_lang")],
                [InlineKeyboardButton("🔥 Join Our Channel 🔥", url="https://t.me/openbook506")]
            ])
            await msg.edit_text(TEXTS[new_lang]["start"], reply_markup=keyboard)
            return

        # --- 💸 Refer System (Clickbait + 5 Rupee) ---
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
                # 🚫 CLICKBAIT ALERT: Will not deduct money, just show fake verification message
                await callback_query.answer("✅ Withdrawal Request Submitted!\n\nYour account is under review for fake/bot referrals. Verification process takes 7-14 working days.", show_alert=True)
            return

        elif data == "btn_start_menu":
            bot_info = await client.get_me()
            add_link = f"https://t.me/{bot_info.username}?startchannel=true&admin=invite_users+delete_messages"
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(TEXTS[lang]["btn_add"], url=add_link)],
                [InlineKeyboardButton(TEXTS[lang]["btn_refer"], callback_data="btn_refer"), 
                 InlineKeyboardButton(TEXTS[lang]["btn_lang"], callback_data="btn_change_lang")],
                [InlineKeyboardButton("🔥 Join Our Channel 🔥", url="https://t.me/openbook506")]
            ])
            await msg.edit_text(TEXTS[lang]["start"], reply_markup=keyboard)
            return

        # --- Channel Admin Panel Logic ---
        if not await is_user_admin(client, chat_id, user_id):
            await callback_query.answer(TEXTS[lang]["not_admin"], show_alert=True)
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
            await msg.edit_text(TEXTS[admin_lang]["admin_panel"], reply_markup=keyboard)

        elif data == "btn_acceptall":
            await callback_query.answer(TEXTS[admin_lang]["accepting"], show_alert=False)
            await msg.edit_text(TEXTS[admin_lang]["accepting"])
            
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
                
            final_text = TEXTS[admin_lang]["done"].format(count=success_count)
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
                    done_text = TEXTS[admin_lang]["done"].format(count=success_count)
                    done_msg = await app.send_message(chat_id, done_text)
                    asyncio.create_task(delete_after(done_msg, 5))
        except Exception as e:
        # यह लाइन Render के Logs में असली कारण बता देगी
        print(f"Reaction Error: {e}")

if __name__ == "__main__":
    threading.Thread(target=run_server, daemon=True).start()
    print("Bot is ready Worldwide! (Top 20 Multi-Language + Refer & Earn Mode)")
    loop.create_task(schedule_tracker())
    app.run()
