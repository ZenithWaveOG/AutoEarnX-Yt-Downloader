import os, time, threading, random
import yt_dlp
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask, request
from supabase import create_client

BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
FORCE_CHANNEL = os.getenv("FORCE_CHANNEL")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
app = Flask(__name__)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

DAILY_LIMIT = 2

USER_AGENTS = [
    "Mozilla/5.0 (Linux; Android 11)",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X)",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
]

# ---------------- DATABASE ----------------
def get_user(uid):
    res = supabase.table("users").select("*").eq("user_id", uid).execute()
    return res.data[0] if res.data else None

def add_user(uid, ref=None):
    supabase.table("users").insert({
        "user_id": uid,
        "downloads": 0,
        "referrals": 0,
        "date": time.strftime("%Y-%m-%d")
    }).execute()

    if ref:
        ref_user = get_user(ref)
        if ref_user:
            supabase.table("users").update({
                "referrals": ref_user["referrals"] + 1,
                "downloads": ref_user["downloads"] + 1
            }).eq("user_id", ref).execute()

def reset_daily(uid):
    today = time.strftime("%Y-%m-%d")
    user = get_user(uid)
    if user["date"] != today:
        supabase.table("users").update({
            "downloads": 0,
            "date": today
        }).eq("user_id", uid).execute()

# ---------------- FORCE JOIN ----------------
def is_joined(uid):
    try:
        status = bot.get_chat_member(FORCE_CHANNEL, uid).status
        return status in ["member", "administrator", "creator"]
    except:
        return False

# ---------------- START ----------------
@bot.message_handler(commands=["start"])
def start(message):
    uid = message.from_user.id
    args = message.text.split()
    ref = int(args[1]) if len(args) > 1 else None

    if not get_user(uid):
        add_user(uid, ref)

    if not is_joined(uid):
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{FORCE_CHANNEL[1:]}"))
        kb.add(InlineKeyboardButton("✅ I Joined", callback_data="joined"))
        bot.send_message(
            uid,
            "⚠️ *Join our channel to use AutoEarnX Bot*",
            reply_markup=kb,
            parse_mode="Markdown"
        )
        return

    text = f"""
✨ *Welcome to AutoEarnX v3.0* ✨

🎬 Send any YouTube link  
⚡ I will download it for you  

📥 Formats:
🎵 MP3  
🎬 720p  
🎥 1080p  

📊 Daily Limit: *2 Downloads*  
👥 Refer & Earn +1 Download:

https://t.me/{bot.get_me().username}?start={uid}

🏆 /leaderboard – Top Referrers  
📢 /broadcast – Admin  
👑 /admin – Stats
"""
    bot.send_message(uid, text, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data == "joined")
def joined(call):
    if is_joined(call.from_user.id):
        bot.send_message(call.message.chat.id, "✅ Access granted! Send YouTube link.")
    else:
        bot.answer_callback_query(call.id, "Join channel first!")

# ---------------- LEADERBOARD ----------------
@bot.message_handler(commands=["leaderboard"])
def leaderboard(message):
    data = supabase.table("users").select("*").order("referrals", desc=True).limit(10).execute().data
    text = "🏆 *Referral Leaderboard*\n\n"
    for i, u in enumerate(data, 1):
        text += f"{i}. `{u['user_id']}` ➜ {u['referrals']} referrals\n"
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

# ---------------- LINK HANDLER ----------------
@bot.message_handler(func=lambda m: m.text and "youtu" in m.text)
def link_handler(message):
    uid = message.from_user.id
    reset_daily(uid)
    user = get_user(uid)

    if user["downloads"] >= DAILY_LIMIT:
        bot.send_message(uid, "❌ Daily limit reached.\nRefer 1 user to unlock more downloads.")
        return

    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🎵 MP3 Audio", callback_data=f"mp3|{message.text}"),
        InlineKeyboardButton("🎬 720p Video", callback_data=f"720|{message.text}"),
        InlineKeyboardButton("🎥 1080p Video", callback_data=f"1080|{message.text}")
    )
    bot.send_message(uid, "👇 *Select download format:*", reply_markup=kb, parse_mode="Markdown")

# ---------------- PROGRESS BAR ----------------
def progress_hook(d, chat_id, msg_id):
    if d["status"] == "downloading":
        percent = d.get("_percent_str", "")
        speed = d.get("_speed_str", "")
        eta = d.get("_eta_str", "")
        try:
            bot.edit_message_text(
                f"⬇ *Downloading...*\n\n📊 {percent}\n⚡ {speed}\n⏳ ETA: {eta}",
                chat_id,
                msg_id,
                parse_mode="Markdown"
            )
        except:
            pass

# ---------------- DOWNLOAD PROCESS ----------------
def download_process(call, quality, url):
    uid = call.from_user.id
    msg = bot.send_message(uid, "⏳ Starting download...")

    ydl_opts = {
        "outtmpl": f"{DOWNLOAD_FOLDER}/%(title)s.%(ext)s",
        "format": "bestaudio" if quality == "mp3" else f"bestvideo[height<={quality}]+bestaudio",
        "merge_output_format": "mp4",
        "progress_hooks": [lambda d: progress_hook(d, uid, msg.message_id)],
        "cookiefile": "cookies.txt",
        "noplaylist": True,
        "quiet": True,
        "headers": {
            "User-Agent": random.choice(USER_AGENTS)
        },
        "extractor_args": {
            "youtube": {
                "player_client": ["android"]
            }
        }
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url)
            file = ydl.prepare_filename(info)

        bot.edit_message_text("📤 Uploading...", uid, msg.message_id)

        with open(file, "rb") as f:
            if quality == "mp3":
                bot.send_audio(uid, f)
            else:
                bot.send_video(uid, f)

        os.remove(file)

        user = get_user(uid)
        supabase.table("users").update({
            "downloads": user["downloads"] + 1
        }).eq("user_id", uid).execute()

    except Exception as e:
        bot.send_message(uid, f"❌ Download failed:\n{e}")

@bot.callback_query_handler(func=lambda c: "|" in c.data)
def callback(call):
    quality, url = call.data.split("|")
    threading.Thread(target=download_process, args=(call, quality, url)).start()

# ---------------- BROADCAST ----------------
@bot.message_handler(commands=["broadcast"])
def broadcast(message):
    if message.from_user.id != ADMIN_ID:
        return
    bot.send_message(message.chat.id, "Send message to broadcast:")
    bot.register_next_step_handler(message, do_broadcast)

def do_broadcast(message):
    users = supabase.table("users").select("user_id").execute().data
    sent = 0
    for u in users:
        try:
            bot.send_message(u["user_id"], message.text)
            sent += 1
        except:
            pass
    bot.send_message(message.chat.id, f"✅ Broadcast sent to {sent} users")

# ---------------- ADMIN ----------------
@bot.message_handler(commands=["admin"])
def admin(message):
    if message.from_user.id != ADMIN_ID:
        return
    users = supabase.table("users").select("*").execute().data
    bot.send_message(message.chat.id, f"👑 Total users: {len(users)}")

# ---------------- WEBHOOK ----------------
@app.route("/", methods=["POST"])
def webhook():
    update = telebot.types.Update.de_json(request.stream.read().decode("utf-8"))
    bot.process_new_updates([update])
    return "OK"

@app.route("/")
def index():
    return "Bot Running"

if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
