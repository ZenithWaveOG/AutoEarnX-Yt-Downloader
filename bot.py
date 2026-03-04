import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
import yt_dlp
import os
import threading
import time
import random

BOT_TOKEN = "YOUR_BOT_TOKEN"
ADMIN_ID = 123456789
FORCE_CHANNEL = "@yourchannel"
DOWNLOAD_LIMIT = 2

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

users = {}
referrals = {}

USER_AGENTS = [
    "Mozilla/5.0 (Linux; Android 11)",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X)"
]

# ---------------- MENU ----------------
def main_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("🎬 Download Video"), KeyboardButton("🎵 Download MP3"))
    kb.add(KeyboardButton("👥 Refer & Earn"), KeyboardButton("🏆 Leaderboard"))
    kb.add(KeyboardButton("ℹ️ Help"), KeyboardButton("📊 My Stats"))
    return kb

# ---------------- FORCE JOIN ----------------
def is_joined(uid):
    try:
        status = bot.get_chat_member(FORCE_CHANNEL, uid).status
        return status in ["member", "administrator", "creator"]
    except:
        return False

# ---------------- FORMAT SAFE ----------------
def get_format(q):
    if q == "mp3":
        return "bestaudio/best"
    elif q == "720":
        return "bestvideo[height<=720]/best"
    elif q == "1080":
        return "bestvideo[height<=1080]/best"

# ---------------- START ----------------
@bot.message_handler(commands=["start"])
def start(message):
    uid = message.from_user.id
    args = message.text.split()
    ref = int(args[1]) if len(args) > 1 else None

    if uid not in users:
        users[uid] = DOWNLOAD_LIMIT
        if ref and ref != uid:
            referrals[ref] = referrals.get(ref, 0) + 1
            users[ref] += 1

    if not is_joined(uid):
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{FORCE_CHANNEL[1:]}"))
        kb.add(InlineKeyboardButton("✅ I Joined", callback_data="joined"))
        bot.send_message(uid, "⚠️ Join our channel to use bot", reply_markup=kb)
        return

    text = f"""
✨ *AutoEarnX v3.0* ✨

🎬 Send YouTube link  
⚡ Choose format  
📥 Download instantly  

Daily limit: *{users[uid]}*

👥 Refer & Earn +1:
https://t.me/{bot.get_me().username}?start={uid}
"""
    bot.send_message(uid, text, reply_markup=main_menu())

# ---------------- CALLBACK JOIN ----------------
@bot.callback_query_handler(func=lambda call: call.data == "joined")
def joined(call):
    if is_joined(call.from_user.id):
        bot.send_message(call.from_user.id, "✅ Verified!", reply_markup=main_menu())
    else:
        bot.answer_callback_query(call.id, "Join channel first!")

# ---------------- MENU BUTTONS ----------------
@bot.message_handler(func=lambda m: m.text == "🎬 Download Video")
def video_btn(m):
    bot.send_message(m.chat.id, "📥 Send YouTube link")

@bot.message_handler(func=lambda m: m.text == "🎵 Download MP3")
def mp3_btn(m):
    bot.send_message(m.chat.id, "📥 Send YouTube link")

@bot.message_handler(func=lambda m: m.text == "👥 Refer & Earn")
def refer_btn(m):
    uid = m.from_user.id
    bot.send_message(uid, f"👥 Your link:\nhttps://t.me/{bot.get_me().username}?start={uid}")

@bot.message_handler(func=lambda m: m.text == "🏆 Leaderboard")
def leaderboard_btn(m):
    text = "🏆 Leaderboard\n\n"
    for k, v in sorted(referrals.items(), key=lambda x: x[1], reverse=True):
        text += f"{k} → {v} refs\n"
    bot.send_message(m.chat.id, text or "No referrals yet.")

@bot.message_handler(func=lambda m: m.text == "ℹ️ Help")
def help_btn(m):
    bot.send_message(m.chat.id, "Send YouTube link and choose format.")

@bot.message_handler(func=lambda m: m.text == "📊 My Stats")
def stats_btn(m):
    uid = m.from_user.id
    bot.send_message(uid, f"📊 Remaining downloads: {users.get(uid,0)}")

# ---------------- LINK HANDLER ----------------
@bot.message_handler(func=lambda m: "youtu" in m.text)
def link_handler(m):
    uid = m.from_user.id
    if users.get(uid, 0) <= 0:
        bot.send_message(uid, "❌ Daily limit finished. Refer to get more.")
        return

    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🎵 MP3", callback_data=f"mp3|{m.text}"),
        InlineKeyboardButton("🎬 720p", callback_data=f"720|{m.text}"),
        InlineKeyboardButton("🎥 1080p", callback_data=f"1080|{m.text}")
    )
    bot.send_message(uid, "👇 Select format:", reply_markup=kb)

# ---------------- DOWNLOAD ----------------
@bot.callback_query_handler(func=lambda call: "|" in call.data)
def download(call):
    uid = call.from_user.id
    quality, url = call.data.split("|")

    msg = bot.send_message(uid, "⬇ Downloading...")

    def run():
        try:
            ydl_opts = {
                "outtmpl": "downloads/%(title)s.%(ext)s",
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

            users[uid] -= 1
            bot.send_document(uid, open(file, "rb"))
            os.remove(file)

        except Exception as e:
            bot.send_message(uid, f"❌ Download failed:\n{e}")

    threading.Thread(target=run).start()

print("Bot running...")
bot.infinity_polling()
