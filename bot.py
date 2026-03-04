import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
import yt_dlp
import os
import threading
import random
from supabase import create_client

# ================== ENV VARIABLES ==================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
FORCE_CHANNEL = os.getenv("FORCE_CHANNEL")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN missing")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

USER_AGENTS = [
    "Mozilla/5.0 (Linux; Android 11)",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X)"
]

# ================== KEYBOARD ==================
def main_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("🎬 Download Video"), KeyboardButton("🎵 Download MP3"))
    kb.add(KeyboardButton("👥 Refer & Earn"), KeyboardButton("🏆 Leaderboard"))
    kb.add(KeyboardButton("📊 My Stats"), KeyboardButton("ℹ️ Help"))
    return kb

# ================== FORCE JOIN ==================
def is_joined(uid):
    try:
        status = bot.get_chat_member(FORCE_CHANNEL, uid).status
        return status in ["member", "administrator", "creator"]
    except:
        return False

# ================== SUPABASE FUNCTIONS ==================
def get_user(uid):
    data = supabase.table("users").select("*").eq("user_id", uid).execute().data
    return data[0] if data else None

def add_user(uid, ref=None):
    if not get_user(uid):
        supabase.table("users").insert({
            "user_id": uid,
            "downloads_left": 2,
            "referred_by": ref
        }).execute()

        if ref:
            supabase.table("users").update({
                "downloads_left": supabase.rpc("increment", {"x": 1})
            }).eq("user_id", ref).execute()

            supabase.table("referrals").insert({
                "referrer": ref,
                "referred": uid
            }).execute()

def reduce_download(uid):
    user = get_user(uid)
    if user:
        supabase.table("users").update({
            "downloads_left": user["downloads_left"] - 1
        }).eq("user_id", uid).execute()

def get_ref_count(uid):
    data = supabase.table("referrals").select("*").eq("referrer", uid).execute().data
    return len(data)

def get_leaderboard():
    data = supabase.table("referrals") \
        .select("referrer", count="exact") \
        .group("referrer") \
        .execute().data
    return data

# ================== FORMAT SAFE ==================
def get_format(q):
    if q == "mp3":
        return "bestaudio/best"
    elif q == "720":
        return "bestvideo[height<=720]/best"
    elif q == "1080":
        return "bestvideo[height<=1080]/best"

# ================== START ==================
@bot.message_handler(commands=["start"])
def start(message):
    uid = message.from_user.id
    args = message.text.split()
    ref = int(args[1]) if len(args) > 1 else None

    add_user(uid, ref)

    if not is_joined(uid):
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{FORCE_CHANNEL[1:]}"))
        kb.add(InlineKeyboardButton("✅ I Joined", callback_data="joined"))
        bot.send_message(uid, "⚠️ Join our channel to use the bot", reply_markup=kb)
        return

    user = get_user(uid)

    text = f"""
✨ *AutoEarnX v3.0* ✨

🎬 Send YouTube link  
⚡ Choose format  
📥 Download instantly  

📊 Daily downloads left: *{user['downloads_left']}*

👥 Refer & Earn +1 download:
https://t.me/{bot.get_me().username}?start={uid}
"""
    bot.send_message(uid, text, reply_markup=main_menu())

# ================== JOIN CALLBACK ==================
@bot.callback_query_handler(func=lambda call: call.data == "joined")
def joined(call):
    if is_joined(call.from_user.id):
        bot.send_message(call.from_user.id, "✅ Verified!", reply_markup=main_menu())
    else:
        bot.answer_callback_query(call.id, "Join channel first!")

# ================== MENU BUTTONS ==================
@bot.message_handler(func=lambda m: m.text == "🎬 Download Video")
def video_btn(m):
    bot.send_message(m.chat.id, "📥 Send YouTube link")

@bot.message_handler(func=lambda m: m.text == "🎵 Download MP3")
def mp3_btn(m):
    bot.send_message(m.chat.id, "📥 Send YouTube link")

@bot.message_handler(func=lambda m: m.text == "👥 Refer & Earn")
def refer_btn(m):
    uid = m.from_user.id
    bot.send_message(uid, f"👥 Your referral link:\nhttps://t.me/{bot.get_me().username}?start={uid}")

@bot.message_handler(func=lambda m: m.text == "🏆 Leaderboard")
def leaderboard_btn(m):
    data = get_leaderboard()
    text = "🏆 *Referral Leaderboard*\n\n"
    for d in data:
        text += f"{d['referrer']} → {d['count']} referrals\n"
    bot.send_message(m.chat.id, text or "No data yet.")

@bot.message_handler(func=lambda m: m.text == "📊 My Stats")
def stats_btn(m):
    uid = m.from_user.id
    user = get_user(uid)
    refs = get_ref_count(uid)
    bot.send_message(uid, f"""
📊 *Your Stats*

Downloads left: {user['downloads_left']}
Referrals: {refs}
""")

@bot.message_handler(func=lambda m: m.text == "ℹ️ Help")
def help_btn(m):
    bot.send_message(m.chat.id, "Send any YouTube link and choose MP3 / 720p / 1080p.")

# ================== LINK HANDLER ==================
@bot.message_handler(func=lambda m: "youtu" in m.text)
def link_handler(m):
    uid = m.from_user.id
    user = get_user(uid)

    if user["downloads_left"] <= 0:
        bot.send_message(uid, "❌ Daily limit finished. Refer to get more.")
        return

    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🎵 MP3", callback_data=f"mp3|{m.text}"),
        InlineKeyboardButton("🎬 720p", callback_data=f"720|{m.text}"),
        InlineKeyboardButton("🎥 1080p", callback_data=f"1080|{m.text}")
    )
    bot.send_message(uid, "👇 Select format:", reply_markup=kb)

# ================== DOWNLOAD ==================
@bot.callback_query_handler(func=lambda call: "|" in call.data)
def download(call):
    uid = call.from_user.id
    quality, url = call.data.split("|")

    msg = bot.send_message(uid, "⬇ Downloading...")

    def run():
        try:
            ydl_opts = {
                "outtmpl": f"{DOWNLOAD_FOLDER}/%(title)s.%(ext)s",
                "format": get_format(quality),
                "merge_output_format": "mp4",
                "cookiefile": "cookies.txt",
                "noplaylist": True,
                "quiet": True,
                "headers": {"User-Agent": random.choice(USER_AGENTS)}
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                file = ydl.prepare_filename(info)

            reduce_download(uid)
            bot.send_document(uid, open(file, "rb"))
            os.remove(file)

        except Exception as e:
            bot.send_message(uid, f"❌ Download failed:\n{e}")

    threading.Thread(target=run).start()

print("Bot running...")
bot.infinity_polling()
