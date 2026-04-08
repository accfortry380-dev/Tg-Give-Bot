import os
import telebot
from telebot.types import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
import sqlite3
import time
import uuid
import re
import random
import threading
from datetime import datetime, timedelta
from flask import Flask, jsonify

# ================= CONFIG =================

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN environment variable missing")

ADMIN_ID = int(os.getenv("ADMIN_ID", "6321618547"))
DB_PATH = os.getenv("DB_PATH", "channels.db")
PORT = int(os.getenv("PORT", "10000"))

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
print("Bot Started ✅")

# ================= WEB SERVICE (Render health server) =================

app = Flask(__name__)

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "ok": True,
        "message": "Telegram bot web service is running"
    }), 200

@app.route("/healthz", methods=["GET"])
def healthz():
    return "ok", 200

# ================= DATABASE =================

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()

cursor.execute("CREATE TABLE IF NOT EXISTS channels (user_id INTEGER, channel_id TEXT, title TEXT)")

cursor.execute("""
CREATE TABLE IF NOT EXISTS giveaways (
    gw_id TEXT PRIMARY KEY,
    creator_id INTEGER,
    channels TEXT,
    title TEXT,
    description TEXT,
    image_file_id TEXT,
    duration_text TEXT,
    end_time TEXT,
    winners INTEGER,
    winner_type TEXT,
    prizes TEXT,
    must_join TEXT,
    ended INTEGER DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    first_name TEXT,
    username TEXT,
    join_date TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    name TEXT,
    title TEXT,
    description TEXT,
    image_file_id TEXT,
    winners INTEGER,
    winner_type TEXT,
    duration TEXT,
    prizes TEXT
)
""")
conn.commit()

try:
    cursor.execute("ALTER TABLE templates ADD COLUMN must_join TEXT")
    conn.commit()
except:
    pass

cursor.execute("""
CREATE TABLE IF NOT EXISTS participants (
    gw_id TEXT,
    user_id INTEGER,
    join_time TEXT,
    UNIQUE(gw_id, user_id)
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS giveaway_messages (
    gw_id TEXT,
    channel_id TEXT,
    message_id INTEGER
)
""")

conn.commit()

# ================= MENUS =================
user_selection = {}
giveaway_data = {}
template_data = {}

def main_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("➕ Add Channel", "🗂️ Manage Channels")
    kb.row("🎁 Create Giveaway", "📊 Dashboard")
    kb.row("📝 Templates", "❓ Help & Support")
    kb.row("ℹ️ About")
    return kb

def manage_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("🔎 View All Channels", "❌ Remove Channel")
    kb.row("↩️ Back to Main Menu")
    return kb

def cancel_inline():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("❌ Cancel", callback_data="cancel"))
    return kb

# ================= TEXT =================

WELCOME_TEXT = """This bot helps you create and manage
giveaways in your Telegram channels.

<b>Main Features:</b>
➕ Add and manage your channels
🎁 Create engaging giveaways
📊 Track analytics and results
🏆 Automatic winner selection

Choose an option from the menu
below to get started.
"""

ADD_CHANNEL_TEXT = """📢 <b>Add a New Channel</b>

Send the Channel ID or @username.

Make sure the bot is an admin in that
channel with proper permissions.

📋 <b>Format Example:</b>
• -1001234567890

💡 <b>How to find Chat ID:</b>
🤖 Use the @username_to_id_bot to
get chat ID
"""

HELP_TEXT = """🚀 <b>Quick Guide</b>
━━━━━━━━━━━━━━━━━━

1️⃣ <b>Add Channel</b>
• Click ➕ Add Channel
• Send channel ID or @username
• Bot must be admin (Post/Edit/Delete)

2️⃣ <b>Create Giveaway</b>
• Click 🎁 Create Giveaway
• Follow steps (title, time, winners, prize)

3️⃣ <b>Monitor</b>
• 📊 Dashboard → active & ended giveaways

📋 <b>Tips</b>
• Time: 5m | 1h | 2d
• Single prize = one line
• Multiple prizes = one per line
• Subscriptions are optional

🔧 <b>Common Issues</b>
• Channel not linked → bot/user not admin
• Missing permissions → allow Post/Edit/Delete
• Channel not found → check ID/username

📞 <b>Support:</b> @RASHIK_69
"""

ABOUT_TEXT = """ℹ️ <b>About</b>
━━━━━━━━━━━━━━━━━━

<b>Name:</b> Give Flow  
<b>Version:</b> v2.0 (Beta) 🛠️

👨‍💻 <b>Development Team:</b>
- Creator: <a href="https://t.me/RASHIK_69">RASHIK 69</a> 👨‍💻

⚙️ <b>Technical Stack:</b>
- Language: Python 🐍
- Library: PyTelegramBotAPI 📚
- Database: SQLite 🗄️

📌 <b>About:</b>
Automated giveaway management
for Telegram channels.
"""

# ================= HELPERS =================

def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def parse_end_time(end_time_str: str) -> datetime:
    return datetime.strptime(end_time_str, "%Y-%m-%d %H:%M:%S")

def start_broadcast(message, forward=False, text=None):
    status = bot.send_message(message.chat.id, "🚀 Broadcast started...\n\n0%")

    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()

    total = len(users)
    sent = 0
    failed = 0

    for i, row in enumerate(users, start=1):
        user_id = row[0]

        try:
            if forward:
                bot.forward_message(
                    user_id,
                    message.chat.id,
                    message.reply_to_message.message_id
                )
            else:
                bot.send_message(user_id, text)

            sent += 1
        except:
            failed += 1

        if i % 10 == 0 or i == total:
            percent = int((i / total) * 100) if total > 0 else 100
            progress_bar = "█" * (percent // 10) + "░" * (10 - (percent // 10))

            bot.edit_message_text(
                f"""🚀 <b>Broadcast Progress</b>

[{progress_bar}] {percent}%

👥 Total: {total}
✅ Sent: {sent}
❌ Failed: {failed}""",
                message.chat.id,
                status.message_id
            )

        time.sleep(0.05)

    bot.edit_message_text(
        f"""✅ <b>Broadcast Completed</b>

👥 Total Users: {total}
✅ Sent: {sent}
❌ Failed: {failed}""",
        message.chat.id,
        status.message_id
    )

def format_remaining_full(end_time: datetime) -> str:
    now = datetime.now().replace(microsecond=0)
    diff = end_time - now
    sec = int(diff.total_seconds())

    if sec <= 0:
        return "Ended"

    d = sec // 86400
    sec %= 86400
    h = sec // 3600
    sec %= 3600
    m = sec // 60
    s = sec % 60

    parts = []
    if d:
        parts.append(f"{d} days")
    if h:
        parts.append(f"{h} hours")
    if m:
        parts.append(f"{m} minutes")
    parts.append(f"{s} seconds")

    return ", ".join(parts)

def get_prize_type(prizes):
    if not prizes:
        return "Unknown"
    sample = prizes[0].strip()
    if sample.startswith("http://") or sample.startswith("https://"):
        return "Access Link"
    if ":" in sample and "@" in sample:
        return "Email:Password"
    if ":" in sample:
        return "User:Password"
    return "Code/Key"

def tg_link_from_channel(ch: str):
    ch = ch.strip()
    if ch.startswith("@"):
        return f"https://t.me/{ch[1:]}"
    return None

def is_member_of_required(user_id: int, must_join_list):
    for ch in must_join_list:
        ch = ch.strip()
        if not ch:
            continue
        try:
            member = bot.get_chat_member(ch, user_id)
            if member.status not in ("member", "administrator", "creator"):
                return False, ch
        except:
            return False, ch
    return True, None

def bot_is_admin_in_channel(channel):
    try:
        me = bot.get_me().id
        m = bot.get_chat_member(channel, me)
        return m.status in ("administrator", "creator")
    except:
        return False

def show_preview(chat_id, user_id):
    data = giveaway_data[user_id]

    required_list = data.get("must_join", [])
    required = len(required_list)

    prize_type = get_prize_type(data.get("prizes", []))

    preview_text = f"""📋 <b>Giveaway Preview</b>

🎁 <b>Title:</b> {data.get("title")}
📝 <b>Description:</b> {data.get("description")}
🏆 <b>Prize:</b> {prize_type}
⏳ <b>Duration:</b> Set
👥 <b>Winners:</b> {data.get("winners")}
🎯 <b>Winner Type:</b> {data.get("winner_type")}
📢 <b>Required Subs:</b> {required}
"""

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("✅ Confirm", callback_data="publish_gw"))
    markup.add(InlineKeyboardButton("❌ Cancel", callback_data="cancel_gw_final"))

    bot.send_message(chat_id, preview_text, reply_markup=markup)

def safe_edit_any(chat_id, message_id, text, reply_markup=None):
    try:
        bot.edit_message_caption(
            chat_id=chat_id,
            message_id=message_id,
            caption=text,
            parse_mode="HTML",
            reply_markup=reply_markup
        )
        return True
    except:
        pass

    try:
        bot.edit_message_text(
            text=text,
            chat_id=chat_id,
            message_id=message_id,
            parse_mode="HTML",
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )
        return True
    except Exception as e:
        print("Edit failed:", e)
        return False

# ================= START HANDLER =================

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name or "No Name"
    username = message.from_user.username or "NoUsername"

    cursor.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,))
    exists = cursor.fetchone()

    if not exists:
        cursor.execute(
            "INSERT INTO users VALUES (?,?,?,?)",
            (user_id, first_name, username, now_str())
        )
        conn.commit()

        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]

        try:
            bot.send_message(
                ADMIN_ID,
                f"""🚀 <b>New User Started Bot!</b>

👤 Name: {first_name}
🆔 ID: <code>{user_id}</code>
🔗 Username: @{username}

📊 Total Users: {total_users}"""
            )
        except:
            pass

    if message.text.startswith("/start join_"):
        gw_id = message.text.split("join_")[1].strip()

        cursor.execute("SELECT title, must_join, end_time, ended FROM giveaways WHERE gw_id=?", (gw_id,))
        row = cursor.fetchone()
        if not row:
            bot.send_message(message.chat.id, "❌ Giveaway not found or already ended.")
            return

        title, must_join_raw, end_time_str, ended = row

        if int(ended) == 1:
            bot.send_message(message.chat.id, "❌ This giveaway already ended.")
            return

        end_time = parse_end_time(end_time_str)
        if datetime.now() >= end_time:
            bot.send_message(message.chat.id, "❌ This giveaway already ended.")
            return

        must_join_list = [x.strip() for x in (must_join_raw or "").split(",") if x.strip()]
        if must_join_list:
            ok, missing = is_member_of_required(user_id, must_join_list)
            if not ok:
                bot.send_message(message.chat.id, "❌ You must join required channels first.")
                return

        cursor.execute("SELECT 1 FROM participants WHERE gw_id=? AND user_id=?", (gw_id, user_id))
        if cursor.fetchone():
            bot.send_message(
                message.chat.id,
                f"✅ Already Joined!\n\nYou're already participating in: {title}."
            )
            return

        cursor.execute("INSERT INTO participants VALUES (?, ?, ?)", (gw_id, user_id, now_str()))
        conn.commit()

        bot.send_message(
            message.chat.id,
            f"""🎉 <b>Successfully Joined!</b>

You're now participating in: <b>{title}</b>

Good luck! Winners will be announced automatically when the giveaway ends."""
        )
        return

    bot.send_message(message.chat.id, WELCOME_TEXT, reply_markup=main_menu())

@bot.message_handler(func=lambda m: m.text == "🗂️ Manage Channels")
def manage(message):
    bot.send_message(
        message.chat.id,
        "🗂️ <b>Manage Channels</b>\n\nChoose an action:",
        reply_markup=manage_menu()
    )

# ================= DASHBOARD =================

@bot.message_handler(func=lambda m: m.text == "📊 Dashboard")
def dashboard(message):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("🟢 Active Giveaways")
    kb.row("⚫ Expired Giveaways")
    kb.row("📈 Analytics")
    kb.row("↩️ Back to Main Menu")

    bot.send_message(
        message.chat.id,
        "📊 <b>Dashboard</b>\n\nChoose an option:",
        reply_markup=kb
    )

# ================= ACTIVE GIVEAWAYS =================

@bot.message_handler(func=lambda m: m.text == "🟢 Active Giveaways")
def active_giveaways(message):
    cursor.execute("""
        SELECT gw_id, title, end_time
        FROM giveaways
        WHERE ended=0
        ORDER BY end_time ASC
    """)
    rows = cursor.fetchall()

    if not rows:
        bot.send_message(message.chat.id, "❌ No active giveaways.")
        return

    text = "🟢 <b>Active Giveaways:</b>\n\n"

    for gw_id, title, end_time_str in rows:
        end_time = parse_end_time(end_time_str)
        remaining = format_remaining_full(end_time)

        text += f"🎁 <b>{title}</b>\n"
        text += f"🆔 <code>{gw_id}</code>\n"
        text += f"⏳ {remaining}\n\n"

    bot.send_message(message.chat.id, text)

# ================= EXPIRED GIVEAWAYS =================

@bot.message_handler(func=lambda m: m.text == "⚫ Expired Giveaways")
def expired_giveaways(message):
    cursor.execute("""
        SELECT gw_id, title, end_time
        FROM giveaways
        WHERE ended=1
        ORDER BY end_time DESC
    """)
    rows = cursor.fetchall()

    if not rows:
        bot.send_message(message.chat.id, "❌ No expired giveaways.")
        return

    text = "⚫ <b>Expired Giveaways:</b>\n\n"

    for gw_id, title, end_time_str in rows:
        text += f"🎁 <b>{title}</b>\n"
        text += f"🆔 <code>{gw_id}</code>\n"
        text += f"📅 Ended At: {end_time_str}\n\n"

    bot.send_message(message.chat.id, text)

# ================= ANALYTICS =================

@bot.message_handler(func=lambda m: m.text == "📈 Analytics")
def analytics(message):
    cursor.execute("SELECT COUNT(*) FROM giveaways")
    total_gw = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM giveaways WHERE ended=0")
    active = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM giveaways WHERE ended=1")
    expired = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM participants")
    total_participants = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]

    bot.send_message(
        message.chat.id,
        f"""📊 <b>Analytics Report</b>

👥 Total Users: {total_users}
🎁 Total Giveaways: {total_gw}
🟢 Active: {active}
⚫ Expired: {expired}
👥 Current Participants: {total_participants}
"""
    )

# ================= TEMPLATES MENU =================

@bot.message_handler(func=lambda m: m.text == "📝 Templates" or m.text == "Templates")
def template_menu(message):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("📋 View Templates")
    kb.row("➕ Create Template")
    kb.row("↩️ Back to Main Menu")

    bot.send_message(
        message.chat.id,
        """📝 <b>Template Manager</b>

Templates help you quickly create giveaways
with pre-configured settings.

Choose an option:""",
        reply_markup=kb
    )

@bot.message_handler(func=lambda m: m.text == "➕ Create Template")
def create_template(message):
    template_data[message.from_user.id] = {"step": "name"}
    bot.send_message(message.chat.id, "📝 Enter Template Name:\n\nSend /cancel to abort.")

@bot.message_handler(commands=['resetdb'])
def reset_db(message):
    if message.from_user.id != ADMIN_ID:
        return

    cursor.execute("DELETE FROM giveaways")
    cursor.execute("DELETE FROM participants")
    cursor.execute("DELETE FROM giveaway_messages")
    cursor.execute("DELETE FROM templates")
    cursor.execute("DELETE FROM channels")
    cursor.execute("DELETE FROM users")
    conn.commit()

    bot.send_message(message.chat.id, "✅ Database Cleared.")

@bot.message_handler(func=lambda m: m.from_user.id in template_data)
def handle_template_steps(message):
    if message.text == "/cancel":
        template_data.pop(message.from_user.id, None)
        bot.send_message(message.chat.id, "❌ Template creation cancelled.", reply_markup=main_menu())
        return

    if message.text in ["↩️ Back to Main Menu", "Back to Main Menu"]:
        template_data.pop(message.from_user.id, None)
        bot.send_message(message.chat.id, "🏠 <b>Main Menu</b>", reply_markup=main_menu())
        return

    user_id = message.from_user.id
    step = template_data[user_id]["step"]

    if step == "name":
        template_data[user_id]["name"] = message.text
        template_data[user_id]["step"] = "title"
        bot.send_message(message.chat.id, "🎁 Enter Giveaway Title:\n\nSend /cancel to abort.")
        return

    if step == "title":
        template_data[user_id]["title"] = message.text
        template_data[user_id]["step"] = "description"
        bot.send_message(message.chat.id, "📝 Enter Description:\n\nSend /cancel to abort.")
        return

    if step == "description":
        template_data[user_id]["description"] = message.text
        template_data[user_id]["step"] = "duration"
        bot.send_message(message.chat.id, "⏳ Enter Duration (5m / 1h / 2d):")
        return

    if step == "duration":
        template_data[user_id]["duration"] = message.text
        template_data[user_id]["step"] = "winners"
        bot.send_message(message.chat.id, "🏆 Enter Number of Winners:")
        return

    if step == "edit_required":
        text = message.text.strip()

        if text == "0":
            cursor.execute(
                "UPDATE templates SET must_join=NULL WHERE id=?",
                (template_data[user_id]["tid"],)
            )
            conn.commit()
            template_data.pop(user_id)
            bot.send_message(
                message.chat.id,
                "✅ Required subs cleared.",
                reply_markup=main_menu()
            )
            return

        channels = text.replace("\n", " ").split()
        valid = []

        for ch in channels:
            try:
                chat = bot.get_chat(ch)
                if not bot_is_admin_in_channel(chat.id):
                    bot.send_message(message.chat.id, f"❌ Bot not admin in {ch}")
                    return
                valid.append(ch)
            except:
                bot.send_message(message.chat.id, f"❌ Invalid channel: {ch}")
                return

        cursor.execute(
            "UPDATE templates SET must_join=? WHERE id=?",
            (",".join(valid), template_data[user_id]["tid"])
        )
        conn.commit()

        template_data.pop(user_id)

        bot.send_message(
            message.chat.id,
            f"✅ Required subscriptions updated ({len(valid)} channels).",
            reply_markup=main_menu()
        )
        return

    if step == "winners":
        if not message.text.isdigit():
            bot.send_message(message.chat.id, "❌ Enter valid number.")
            return

        template_data[user_id]["winners"] = int(message.text)
        template_data[user_id]["step"] = "winner_type"

        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.row("🎲 Random", "🏃 First X")
        bot.send_message(message.chat.id, "Select Winner Type:", reply_markup=kb)
        return

    if step == "winner_type":
        template_data[user_id]["winner_type"] = message.text
        template_data[user_id]["step"] = "prizes"
        bot.send_message(message.chat.id, "🎁 Enter Prizes (one per line):")
        return

    if step == "prizes":
        prizes = message.text.strip()
        data = template_data[user_id]

        cursor.execute("""
            INSERT INTO templates
            (user_id, name, title, description, image_file_id, winners, winner_type, duration, prizes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            data["name"],
            data["title"],
            data["description"],
            data.get("image"),
            data["winners"],
            data["winner_type"],
            data["duration"],
            prizes
        ))
        conn.commit()

        template_data.pop(user_id)
        bot.send_message(message.chat.id, "✅ Template Saved Successfully!", reply_markup=main_menu())
        return

    if step == "edit_duration":
        cursor.execute(
            "UPDATE templates SET duration=? WHERE id=?",
            (message.text, template_data[user_id]["tid"])
        )
        conn.commit()
        template_data.pop(user_id)
        bot.send_message(message.chat.id, "✅ Duration updated.", reply_markup=main_menu())
        return

    if step == "edit_prizes":
        cursor.execute(
            "UPDATE templates SET prizes=? WHERE id=?",
            (message.text, template_data[user_id]["tid"])
        )
        conn.commit()
        template_data.pop(user_id)
        bot.send_message(message.chat.id, "✅ Prizes updated.", reply_markup=main_menu())
        return

@bot.message_handler(func=lambda m: m.text == "📋 View Templates")
def view_templates(message):
    cursor.execute("SELECT id, name FROM templates WHERE user_id=?", (message.from_user.id,))
    rows = cursor.fetchall()

    if not rows:
        bot.send_message(message.chat.id, "❌ No templates found.")
        return

    kb = InlineKeyboardMarkup()
    for tid, name in rows:
        kb.add(InlineKeyboardButton(f"📄 {name}", callback_data=f"view_tpl_{tid}"))

    bot.send_message(message.chat.id, "📋 Your Templates:", reply_markup=kb)

@bot.callback_query_handler(func=lambda call: call.data.startswith("view_tpl_"))
def view_template_details(call):
    tid = call.data.split("_")[-1]

    cursor.execute("""
        SELECT name, title, description, image_file_id,
               winners, winner_type, duration, prizes, must_join
        FROM templates WHERE id=?
    """, (tid,))
    row = cursor.fetchone()

    if not row:
        bot.answer_callback_query(call.id, "Template not found.")
        return

    name, title, desc, image, winners, wtype, duration, prizes, must_join = row

    required_list = [x.strip() for x in (must_join or "").split(",") if x.strip()]
    required_count = len(required_list)

    img_status = "✅ Added" if image else "❌ None"

    text = f"""📄 <b>{name}</b>

🎁 Title: {title}
📝 Description: {desc}
🖼 Image: {img_status}
🏆 Winners: {winners}
🎲 Type: {wtype}
⏳ Duration: {duration}
📢 Required Subs: {required_count}

🎁 Prizes:
{prizes}
"""

    kb = InlineKeyboardMarkup()
    kb.row(
        InlineKeyboardButton("🚀 Use Template", callback_data=f"use_tpl_{tid}"),
        InlineKeyboardButton("✏ Edit Template", callback_data=f"edit_tpl_{tid}")
    )
    kb.row(
        InlineKeyboardButton("🗑 Delete", callback_data=f"del_tpl_{tid}")
    )

    bot.edit_message_text(
        text,
        call.message.chat.id,
        call.message.message_id,
        reply_markup=kb
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("edit_tpl_"))
def edit_template_menu(call):
    tid = call.data.split("_")[-1]

    kb = InlineKeyboardMarkup()
    kb.row(
        InlineKeyboardButton("🖼 Edit Image", callback_data=f"tpl_edit_img_{tid}"),
        InlineKeyboardButton("❌ Delete Image", callback_data=f"tpl_del_img_{tid}")
    )
    kb.row(
        InlineKeyboardButton("⏳ Edit Duration", callback_data=f"tpl_edit_dur_{tid}"),
        InlineKeyboardButton("🎁 Edit Prizes", callback_data=f"tpl_edit_prize_{tid}")
    )
    kb.row(
        InlineKeyboardButton("🏆 Edit Winners", callback_data=f"tpl_edit_win_{tid}"),
        InlineKeyboardButton("🎲 Edit Winner Type", callback_data=f"tpl_edit_type_{tid}")
    )
    kb.row(
        InlineKeyboardButton("📢 Edit Required Subs", callback_data=f"tpl_edit_req_{tid}")
    )
    kb.row(
        InlineKeyboardButton("↩ Back", callback_data=f"view_tpl_{tid}")
    )

    bot.edit_message_text(
        "✏ <b>Edit Template</b>\n\nSelect what you want to modify:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=kb
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("tpl_edit_dur_"))
def tpl_edit_duration(call):
    tid = call.data.split("_")[-1]

    template_data[call.from_user.id] = {
        "step": "edit_duration",
        "tid": tid
    }

    bot.send_message(call.from_user.id, "⏳ Enter new duration (5m / 1h / 2d):")

@bot.callback_query_handler(func=lambda call: call.data.startswith("tpl_edit_prize_"))
def tpl_edit_prize(call):
    tid = call.data.split("_")[-1]

    template_data[call.from_user.id] = {
        "step": "edit_prizes",
        "tid": tid
    }

    bot.send_message(call.from_user.id, "🎁 Send new prizes (one per line):")

@bot.callback_query_handler(func=lambda call: call.data.startswith("tpl_edit_img_"))
def tpl_edit_image(call):
    tid = call.data.split("_")[-1]

    template_data[call.from_user.id] = {
        "step": "edit_image",
        "tid": tid
    }

    bot.send_message(call.from_user.id, "🖼 Send new image:")

@bot.callback_query_handler(func=lambda call: call.data.startswith("tpl_del_img_"))
def tpl_delete_image(call):
    tid = call.data.split("_")[-1]

    cursor.execute("UPDATE templates SET image_file_id=NULL WHERE id=?", (tid,))
    conn.commit()

    bot.answer_callback_query(call.id, "Image deleted ✅")

@bot.callback_query_handler(func=lambda call: call.data.startswith("tpl_edit_req_"))
def tpl_edit_required(call):
    tid = call.data.split("_")[-1]

    template_data[call.from_user.id] = {
        "step": "edit_required",
        "tid": tid
    }

    bot.send_message(
        call.from_user.id,
        """📢 Send required channels (optional)

Send:
-1001234567890
@channelusername

Separate multiple with space or newline.
Send 0 to clear."""
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("use_tpl_"))
def use_template(call):
    user_id = call.from_user.id
    tid = call.data.split("_")[-1]

    cursor.execute("""
        SELECT title, description, image_file_id, winners,
               winner_type, duration, prizes, must_join
        FROM templates WHERE id=? AND user_id=?
    """, (tid, user_id))
    row = cursor.fetchone()

    if not row:
        bot.answer_callback_query(call.id, "Template not found.")
        return

    title, desc, image, winners, wtype, duration, prizes, must_join = row

    cursor.execute("SELECT channel_id, title FROM channels WHERE user_id=?", (user_id,))
    rows = cursor.fetchall()

    if not rows:
        bot.answer_callback_query(call.id, "No channels added.")
        return

    user_selection[user_id] = []
    giveaway_data[user_id] = {
        "title": title,
        "description": desc,
        "winners": winners,
        "winner_type": wtype,
        "duration": duration,
        "prizes": prizes.split("\n"),
        "image": image,
        "must_join": [x.strip() for x in (must_join or "").split(",") if x.strip()],
        "step": "template_channel_select"
    }

    markup = InlineKeyboardMarkup()
    for cid, cname in rows:
        markup.add(InlineKeyboardButton(f"☑ {cname}", callback_data=f"tpl_toggle_{cid}"))

    markup.add(InlineKeyboardButton("✅ Confirm Channels", callback_data="tpl_confirm_channels"))
    markup.add(InlineKeyboardButton("❌ Cancel", callback_data="cancel_gw"))

    bot.edit_message_text(
        """🚀 <b>Create Giveaway from Template</b>

Select one or more channels to publish:""",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("tpl_toggle_"))
def tpl_toggle_channel(call):
    user_id = call.from_user.id
    cid = call.data.replace("tpl_toggle_", "")

    if cid in user_selection[user_id]:
        user_selection[user_id].remove(cid)
    else:
        user_selection[user_id].append(cid)

    cursor.execute("SELECT channel_id, title FROM channels WHERE user_id=?", (user_id,))
    rows = cursor.fetchall()

    markup = InlineKeyboardMarkup()
    for channel_id, title in rows:
        text = f"✅ {title}" if channel_id in user_selection[user_id] else f"☑ {title}"
        markup.add(InlineKeyboardButton(text, callback_data=f"tpl_toggle_{channel_id}"))

    markup.add(InlineKeyboardButton("✅ Confirm Channels", callback_data="tpl_confirm_channels"))
    markup.add(InlineKeyboardButton("❌ Cancel", callback_data="cancel_gw"))

    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "tpl_confirm_channels")
def tpl_confirm_channels(call):
    user_id = call.from_user.id

    if not user_selection.get(user_id):
        bot.answer_callback_query(call.id, "Select at least one channel!")
        return

    giveaway_data[user_id]["channels"] = user_selection[user_id]

    call.data = "publish_gw"
    publish_gw(call)

@bot.message_handler(func=lambda m: m.text in ["↩️ Back to Main Menu", "Back to Main Menu"])
def back_to_main(message):
    user_id = message.from_user.id

    template_data.pop(user_id, None)
    giveaway_data.pop(user_id, None)
    user_selection.pop(user_id, None)

    bot.send_message(
        message.chat.id,
        "🏠 <b>Main Menu</b>",
        reply_markup=main_menu()
    )

@bot.message_handler(commands=['broadcast'])
def broadcast_command(message):
    if message.from_user.id != ADMIN_ID:
        return

    if message.reply_to_message:
        start_broadcast(message, forward=True)
        return

    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        bot.send_message(
            message.chat.id,
            "❌ Use:\n\nReply to a message and type /broadcast\nOR\n/broadcast your text here"
        )
        return

    start_broadcast(message, forward=False, text=parts[1])

@bot.message_handler(func=lambda m: m.text == "➕ Add Channel")
def add_channel(message):
    bot.send_message(message.chat.id, ADD_CHANNEL_TEXT, reply_markup=cancel_inline())

@bot.message_handler(func=lambda m: m.text == "❓ Help & Support")
def help_support(message):
    bot.send_message(message.chat.id, HELP_TEXT, reply_markup=main_menu())

@bot.message_handler(func=lambda m: m.text == "ℹ️ About")
def about(message):
    bot.send_message(message.chat.id, ABOUT_TEXT, reply_markup=main_menu())

@bot.callback_query_handler(func=lambda call: call.data == "cancel")
def cancel(call):
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id)
    bot.send_message(call.message.chat.id, "🏠 <b>Main Menu</b>", reply_markup=main_menu())

@bot.message_handler(commands=['cancel'])
def cancel_all(message):
    user_id = message.from_user.id

    giveaway_data.pop(user_id, None)
    user_selection.pop(user_id, None)
    template_data.pop(user_id, None)

    bot.send_message(
        message.chat.id,
        "❌ Process cancelled.",
        reply_markup=main_menu()
    )

@bot.callback_query_handler(func=lambda call: call.data == "cancel_gw_final")
def cancel_final(call):
    user_id = call.from_user.id
    giveaway_data.pop(user_id, None)
    user_selection.pop(user_id, None)
    bot.edit_message_text("❌ Giveaway cancelled.", call.message.chat.id, call.message.message_id)

@bot.message_handler(func=lambda m: m.text and m.text.startswith("-100"))
def link_channel(message):
    channel_id = message.text.strip()
    try:
        chat = bot.get_chat(channel_id)

        cursor.execute("SELECT 1 FROM channels WHERE channel_id=? AND user_id=?", (channel_id, message.from_user.id))
        if cursor.fetchone():
            bot.send_message(message.chat.id, "⚠️ Channel already added.")
            return

        cursor.execute("INSERT INTO channels VALUES (?, ?, ?)", (message.from_user.id, channel_id, chat.title))
        conn.commit()

        username = f"(@{chat.username})" if chat.username else ""

        bot.send_message(
            message.chat.id,
            f"""✅ <b>Channel Linked Successfully!</b>

📢 <b>{chat.title}</b> {username}
🆔 Channel ID: <code>{channel_id}</code>

You can now create giveaways in this channel.
""",
            reply_markup=main_menu()
        )
    except:
        bot.send_message(message.chat.id, "❌ Failed to link channel.\nMake sure bot is admin & ID is correct.")

@bot.message_handler(func=lambda m: m.text == "🔎 View All Channels")
def view_channels(message):
    cursor.execute("SELECT title, channel_id FROM channels WHERE user_id=?", (message.from_user.id,))
    rows = cursor.fetchall()

    if not rows:
        bot.send_message(message.chat.id, "⚠️ No channels added yet.")
        return

    text = "📋 <b>Your Channels:</b>\n\n"
    for i, (title, cid) in enumerate(rows, start=1):
        try:
            chat = bot.get_chat(cid)
            username = f"(@{chat.username})" if chat.username else ""
        except:
            username = ""

        default_tag = " 🏷 (Default)" if i == 1 else ""
        text += f"{i}. ✅ <b>{title}</b> {username}{default_tag}\n"
        text += f"🆔 ID: <code>{cid}</code>\n\n"

    bot.send_message(message.chat.id, text)

@bot.message_handler(func=lambda m: m.text == "❌ Remove Channel")
def remove_channel_list(message):
    cursor.execute("SELECT title, channel_id FROM channels WHERE user_id=?", (message.from_user.id,))
    rows = cursor.fetchall()

    if not rows:
        bot.send_message(message.chat.id, "⚠️ No channels to remove.")
        return

    kb = InlineKeyboardMarkup()
    for title, cid in rows:
        kb.add(InlineKeyboardButton(f"❌ {title}", callback_data=f"del_channel_{cid}"))

    bot.send_message(message.chat.id, "Select channel to remove:", reply_markup=kb)

@bot.callback_query_handler(func=lambda call: call.data.startswith("del_channel_"))
def delete_channel(call):
    cid = call.data.replace("del_channel_", "")
    cursor.execute("DELETE FROM channels WHERE channel_id=? AND user_id=?", (cid, call.from_user.id))
    conn.commit()
    bot.edit_message_text("✅ Channel removed successfully.", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("del_tpl_"))
def delete_template(call):
    tid = call.data.replace("del_tpl_", "")

    cursor.execute("DELETE FROM templates WHERE id=? AND user_id=?", 
                   (tid, call.from_user.id))
    conn.commit()

    bot.edit_message_text(
        "🗑 Template deleted successfully.",
        call.message.chat.id,
        call.message.message_id
    )

@bot.message_handler(func=lambda m: m.text == "🎁 Create Giveaway")
def create_giveaway(message):
    cursor.execute("SELECT channel_id, title FROM channels WHERE user_id=?", (message.from_user.id,))
    rows = cursor.fetchall()

    if not rows:
        bot.send_message(message.chat.id, "⚠️ No channels added.")
        return

    user_selection[message.from_user.id] = []

    markup = InlineKeyboardMarkup()
    for cid, title in rows:
        markup.add(InlineKeyboardButton(f"☑ {title}", callback_data=f"toggle_{cid}"))

    markup.add(InlineKeyboardButton("✅ Confirm Selection", callback_data="confirm_channels"))
    markup.add(InlineKeyboardButton("❌ Cancel", callback_data="cancel_gw"))

    bot.send_message(
        message.chat.id,
        """🎁 <b>Create Giveaway</b>

Step 1/8: Select one or more channels for this giveaway.

Tap to toggle selection, then confirm.""",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "cancel_gw")
def cancel_gw(call):
    user_id = call.from_user.id
    giveaway_data.pop(user_id, None)
    user_selection.pop(user_id, None)
    bot.edit_message_text("❌ Cancelled.", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("toggle_"))
def toggle_channel(call):
    user_id = call.from_user.id
    cid = call.data.replace("toggle_", "")

    if user_id not in user_selection:
        user_selection[user_id] = []

    if cid in user_selection[user_id]:
        user_selection[user_id].remove(cid)
    else:
        user_selection[user_id].append(cid)

    cursor.execute("SELECT channel_id, title FROM channels WHERE user_id=?", (user_id,))
    rows = cursor.fetchall()

    markup = InlineKeyboardMarkup()
    for channel_id, title in rows:
        text = f"✅ {title}" if channel_id in user_selection[user_id] else f"☑ {title}"
        markup.add(InlineKeyboardButton(text, callback_data=f"toggle_{channel_id}"))

    markup.add(InlineKeyboardButton("✅ Confirm Selection", callback_data="confirm_channels"))
    markup.add(InlineKeyboardButton("❌ Cancel", callback_data="cancel_gw"))

    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "confirm_channels")
def confirm_channels(call):
    user_id = call.from_user.id

    if not user_selection.get(user_id):
        bot.answer_callback_query(call.id, "Select at least one channel!")
        return

    giveaway_data[user_id] = {
        "channels": user_selection[user_id],
        "image": None,
        "step": "image"
    }

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("⏭ Skip", callback_data="skip_image"))

    bot.edit_message_text(
        """🖼 <b>Step 2/8:</b> Send a giveaway image (Optional)

📸 Upload an image for your giveaway post.

Send /cancel to abort.""",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "skip_image")
def skip_image(call):
    user_id = call.from_user.id
    if user_id not in giveaway_data:
        return

    giveaway_data[user_id]["image"] = None
    giveaway_data[user_id]["step"] = "title"

    bot.edit_message_text(
        """⏭ Image skipped.

<b>Step 3/8:</b> Enter the giveaway title.

Send /cancel to abort.""",
        call.message.chat.id,
        call.message.message_id
    )

@bot.message_handler(content_types=['photo'])
def handle_all_photos(message):
    user_id = message.from_user.id

    if user_id in template_data:
        if template_data[user_id].get("step") == "edit_image":
            file_id = message.photo[-1].file_id

            cursor.execute(
                "UPDATE templates SET image_file_id=? WHERE id=?",
                (file_id, template_data[user_id]["tid"])
            )
            conn.commit()

            template_data.pop(user_id)

            bot.send_message(
                message.chat.id,
                "✅ Template image updated.",
                reply_markup=main_menu()
            )
            return

    if user_id in giveaway_data:
        if giveaway_data[user_id].get("step") == "image":
            giveaway_data[user_id]["image"] = message.photo[-1].file_id
            giveaway_data[user_id]["step"] = "title"

            bot.send_message(
                message.chat.id,
                """✅ Image uploaded!

<b>Step 3/8:</b> Enter the giveaway title.

Send /cancel to abort."""
            )
            return

@bot.message_handler(func=lambda m: m.from_user.id in giveaway_data)
def handle_steps(message):
    user_id = message.from_user.id

    if user_id not in giveaway_data:
        return

    step = giveaway_data[user_id].get("step")

    if step == "title":
        giveaway_data[user_id]["title"] = message.text
        giveaway_data[user_id]["step"] = "description"
        bot.send_message(message.chat.id, "📝 <b>Step 4/8:</b> Enter a short description.")
        return

    if step == "description":
        giveaway_data[user_id]["description"] = message.text
        giveaway_data[user_id]["step"] = "duration"
        bot.send_message(
            message.chat.id,
            """⏳ <b>Step 5/8:</b> Enter giveaway duration.

Format: <code>5m</code>, <code>1h</code>, <code>2d</code> (m=minutes, h=hours, d=days)"""
        )
        return

    if step == "duration":
        duration_text = message.text.lower().strip()
        match = re.match(r"^(\d+)([mhd])$", duration_text)
        if not match:
            bot.send_message(
                message.chat.id,
                "❌ Invalid format.\n\nUse: <code>5m</code>, <code>1h</code>, <code>2d</code>"
            )
            return

        value = int(match.group(1))
        unit = match.group(2)

        if unit == "m":
            delta = timedelta(minutes=value)
        elif unit == "h":
            delta = timedelta(hours=value)
        else:
            delta = timedelta(days=value)

        end_time = datetime.now() + delta

        giveaway_data[user_id]["duration"] = duration_text
        giveaway_data[user_id]["end_time"] = end_time
        giveaway_data[user_id]["step"] = "winners"

        bot.send_message(message.chat.id, "🏆 <b>Step 6/8:</b> Enter number of winners.")
        return

    if step == "winners":
        if not message.text.isdigit():
            bot.send_message(message.chat.id, "❌ Enter a valid number.")
            return

        winners = int(message.text)
        if winners < 1 or winners > 50:
            bot.send_message(message.chat.id, "❌ Winners must be between 1-50.")
            return

        giveaway_data[user_id]["winners"] = winners
        giveaway_data[user_id]["step"] = "waiting_winner_type"

        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🎲 Random", callback_data="winner_random"))
        markup.add(InlineKeyboardButton("🏃 First X Participants", callback_data="winner_first"))

        bot.send_message(
            message.chat.id,
            "🏆 <b>Step 7/8:</b> Choose winner selection type:",
            reply_markup=markup
        )
        return

    if step == "prize":
        prizes = message.text.strip().splitlines()
        prizes = [p.strip() for p in prizes if p.strip()]

        if not prizes:
            bot.send_message(message.chat.id, "❌ Please send at least one prize.")
            return

        giveaway_data[user_id]["prizes"] = prizes
        giveaway_data[user_id]["step"] = "join_channels"

        prize_type = get_prize_type(prizes)

        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("⏭ Skip", callback_data="skip_join"))

        bot.send_message(
            message.chat.id,
            f"""✅ <b>Prize Received!</b>

🎁 <b>Detected Prize Type:</b> {prize_type}
📦 <b>Total Items:</b> {len(prizes)}

<b>Step 7/8:</b> Send one or more channel IDs or @usernames that participants must join (optional).

You can separate multiple channels with spaces or newlines.""",
            reply_markup=markup
        )
        return

    if step == "join_channels":
        raw = message.text.strip()
        if not raw:
            giveaway_data[user_id]["must_join"] = []
            giveaway_data[user_id]["step"] = "preview"
            show_preview(message.chat.id, user_id)
            return

        channels = raw.replace("\n", " ").split()
        valid_channels = []

        for ch in channels:
            try:
                chat = bot.get_chat(ch)
                if not bot_is_admin_in_channel(chat.id):
                    bot.send_message(message.chat.id, f"❌ Bot is not admin in {ch}")
                    return
                valid_channels.append(ch)
            except:
                bot.send_message(message.chat.id, f"❌ Invalid channel: {ch}")
                return

        giveaway_data[user_id]["must_join"] = valid_channels
        giveaway_data[user_id]["step"] = "preview"
        show_preview(message.chat.id, user_id)
        return

@bot.callback_query_handler(func=lambda call: call.data in ["winner_random", "winner_first"])
def winner_type_handler(call):
    user_id = call.from_user.id
    if user_id not in giveaway_data:
        return

    if giveaway_data[user_id].get("step") != "waiting_winner_type":
        return

    giveaway_data[user_id]["winner_type"] = "Random Selection" if call.data == "winner_random" else "First X Participants"
    giveaway_data[user_id]["step"] = "prize"

    bot.edit_message_text(
        """🎁 <b>Step 8/8:</b> Send the giveaway prize details
━━━━━━━━━━━━━━━━━━

<b>Prize Formats:</b>
• user:pass → johndoe:12345
• email:pass → test@gmail.com:1234
• code/key → ABC1-DEF2-GHI3

📌 Note: One prize per line. Auto-detected.""",
        call.message.chat.id,
        call.message.message_id
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("delete_gw_"))
def delete_gw_confirm(call):
    gw_id = call.data.replace("delete_gw_", "")

    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("✅ Yes, Delete", callback_data=f"confirm_delete_{gw_id}")
    )
    kb.add(
        InlineKeyboardButton("❌ No", callback_data="cancel_delete")
    )

    bot.edit_message_reply_markup(
        call.message.chat.id,
        call.message.message_id,
        reply_markup=kb
    )

    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "cancel_delete")
def cancel_delete(call):
    bot.answer_callback_query(call.id, "Cancelled ❌")

@bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_delete_"))
def confirm_delete(call):
    gw_id = call.data.replace("confirm_delete_", "")

    cursor.execute(
        "SELECT channel_id, message_id FROM giveaway_messages WHERE gw_id=?",
        (gw_id,)
    )
    rows = cursor.fetchall()

    for ch_id, msg_id in rows:
        try:
            bot.delete_message(ch_id, msg_id)
        except:
            pass

    cursor.execute("DELETE FROM giveaways WHERE gw_id=?", (gw_id,))
    cursor.execute("DELETE FROM participants WHERE gw_id=?", (gw_id,))
    cursor.execute("DELETE FROM giveaway_messages WHERE gw_id=?", (gw_id,))
    conn.commit()

    bot.edit_message_text(
        "❌ <b>Giveaway Cancelled Successfully.</b>\n\nAll giveaway data removed.",
        call.message.chat.id,
        call.message.message_id
    )

    bot.answer_callback_query(call.id, "Giveaway Deleted ❌")

@bot.callback_query_handler(func=lambda call: call.data == "skip_join")
def skip_join(call):
    user_id = call.from_user.id
    if user_id not in giveaway_data:
        return

    giveaway_data[user_id]["must_join"] = []
    giveaway_data[user_id]["step"] = "preview"

    show_preview(call.message.chat.id, user_id)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "publish_gw")
def publish_gw(call):
    user_id = call.from_user.id

    if user_id not in giveaway_data:
        return

    data = giveaway_data[user_id]
    gw_id = str(uuid.uuid4())[:8]

    duration_text = data.get("duration", "5m")
    match = re.search(r"(\d+)([mhd])", duration_text)

    if not match:
        bot.answer_callback_query(call.id, "❌ Invalid duration format! Use 5m / 1h / 2d")
        return

    value = int(match.group(1))
    unit = match.group(2)

    if unit == "m":
        delta = timedelta(minutes=value)
    elif unit == "h":
        delta = timedelta(hours=value)
    else:
        delta = timedelta(days=value)

    publish_time = datetime.now().replace(microsecond=0)
    end_time = publish_time + delta

    required_list = data.get("must_join", [])

    if isinstance(required_list, str):
        required_list = [x.strip() for x in required_list.split(",") if x.strip()]

    required_text = ""
    if required_list:
        required_text = "\n\n📢 Required Channels:\n"
        for ch in required_list:
            required_text += f"• {ch}\n"

    prize_type = get_prize_type(data.get("prizes", []))

    caption = f"""✅ <b>GIVEAWAY STARTED</b>

🎁 <b>{data['title']}</b>

📝 <b>Description:</b>
{data['description']}{required_text}

🏆 <b>Prize:</b> {prize_type}
⏳ <b>Deadline:</b> {format_remaining_full(end_time)} remaining
🎲 <b>Selection Type:</b> {data['winner_type']}
👥 <b>Total Participants:</b> 0
👑 <b>Total Winners:</b> {data['winners']}

🎯 Tap below to participate!
"""

    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton(
            "🎉 Join Giveaway",
            url=f"https://t.me/{bot.get_me().username}?start=join_{gw_id}"
        )
    )
    kb.add(
        InlineKeyboardButton(
            "🔄 Reload Status",
            callback_data=f"reload_{gw_id}"
        )
    )

    posted_names = []
    message_ids = {}

    for channel in data["channels"]:
        try:
            if data["image"]:
                msg = bot.send_photo(channel, data["image"], caption=caption, reply_markup=kb)
            else:
                msg = bot.send_message(channel, caption, reply_markup=kb, disable_web_page_preview=True)

            message_ids[str(channel)] = int(msg.message_id)

            try:
                ch = bot.get_chat(channel)
                posted_names.append(ch.title)
            except:
                posted_names.append(str(channel))
        except Exception as e:
            print("Post failed:", e)

    cursor.execute(
        "INSERT INTO giveaways VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            gw_id,
            user_id,
            ",".join([str(x) for x in data["channels"]]),
            data.get("title", ""),
            data.get("description", ""),
            data["image"] if data["image"] else "",
            data.get("duration", ""),
            end_time.strftime("%Y-%m-%d %H:%M:%S"),
            int(data.get("winners", 1)),
            data.get("winner_type", "Random Selection"),
            "\n".join(data.get("prizes", [])),
            ",".join(required_list),
            0
        )
    )

    for ch_id, msg_id in message_ids.items():
        cursor.execute("INSERT INTO giveaway_messages VALUES (?,?,?)", (gw_id, ch_id, msg_id))

    conn.commit()

    giveaway_data.pop(user_id, None)
    user_selection.pop(user_id, None)

    posted_lines = "\n".join([f"• {n}" for n in posted_names]) if posted_names else "• (none)"

    success_kb = InlineKeyboardMarkup()
    success_kb.add(
        InlineKeyboardButton("🗑 Delete Giveaway", callback_data=f"delete_gw_{gw_id}")
    )

    bot.edit_message_text(
        f"""✅ <b>Giveaway Created Successfully!</b>

🎉 Your giveaway has been posted to:
{posted_lines}

📊 Winners will be selected automatically when the deadline is reached.""",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=success_kb
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("reload_"))
def reload_status(call):
    gw_id = call.data.replace("reload_", "").strip()

    cursor.execute("SELECT title, description, end_time, winners, winner_type, must_join, ended FROM giveaways WHERE gw_id=?", (gw_id,))
    row = cursor.fetchone()
    if not row:
        bot.answer_callback_query(call.id, "Not found / ended.")
        return

    title, description, end_time_str, winners, winner_type, must_join_raw, ended = row
    end_time = parse_end_time(end_time_str)

    cursor.execute("SELECT COUNT(*) FROM participants WHERE gw_id=?", (gw_id,))
    total = cursor.fetchone()[0]

    must_list = [x.strip() for x in (must_join_raw or "").split(",") if x.strip()]
    required_text = ""
    if must_list:
        required_text = "\n\n📢 <b>Required Subscriptions:</b>\n" + "\n".join([f"- {x}" for x in must_list])

    if int(ended) == 1 or datetime.now() >= end_time:
        bot.answer_callback_query(call.id, "Giveaway ended.")
        return

    caption = f"""✅ <b>GIVEAWAY STARTED</b>

🎁 <b>{title}</b>

📝 <b>Description:</b>
{description}{required_text}

⏳ <b>Deadline:</b> {format_remaining_full(end_time)} remaining
🎲 <b>Selection Type:</b> {winner_type}
👥 <b>Total Participants:</b> {total}
👑 <b>Total Winners:</b> {winners}

🎯 Tap below to participate!
"""

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🎉 Join Giveaway", url=f"https://t.me/{bot.get_me().username}?start=join_{gw_id}"))
    kb.add(InlineKeyboardButton("🔄 Reload Status", callback_data=f"reload_{gw_id}"))

    safe_edit_any(
        call.message.chat.id,
        call.message.message_id,
        caption,
        reply_markup=kb
    )

    bot.answer_callback_query(call.id, "Updated ✅")

# ================= AUTO WINNER SELECTOR =================

def check_giveaways_loop():
    while True:
        try:
            cursor.execute("""
                SELECT gw_id, channels, title, description, end_time,
                       winners, winner_type, prizes, ended
                FROM giveaways
            """)
            rows = cursor.fetchall()

            for row in rows:
                gw_id, channels_raw, title, description, end_time_str, winners, winner_type, prizes_raw, ended = row

                if int(ended) == 1:
                    continue

                end_time = parse_end_time(end_time_str)
                remaining_seconds = (end_time - datetime.now()).total_seconds()

                if remaining_seconds > 0:
                    continue

                cursor.execute("UPDATE giveaways SET ended=1 WHERE gw_id=?", (gw_id,))
                conn.commit()

                cursor.execute(
                    "SELECT user_id FROM participants WHERE gw_id=? ORDER BY join_time ASC",
                    (gw_id,)
                )
                users = [u[0] for u in cursor.fetchall()]

                prizes = [p.strip() for p in (prizes_raw or "").split("\n") if p.strip()]
                total_participants = len(users)

                winners = int(winners)
                selected = []

                if users:
                    if winner_type == "First X Participants":
                        selected = users[:min(winners, len(users))]
                    else:
                        selected = random.sample(users, k=min(winners, len(users)))

                if total_participants == 0:
                    ended_text = f"""🏁 <b>GIVEAWAY ENDED</b>

🎁 {title}

📝 {description}

👥 Total Participants: 0
🎲 Selection Type: {winner_type}

❌ No participants joined this giveaway."""
                else:
                    winner_lines = []
                    for i, uid in enumerate(selected, start=1):
                        winner_lines.append(
                            f"{i}. <a href='tg://user?id={uid}'>Winner</a>"
                        )

                    ended_text = f"""🏁 <b>GIVEAWAY ENDED</b>

🎁 {title}

📝 {description}

👥 Total Participants: {total_participants}
🎲 Selection Type: {winner_type}
🏆 Total Winners: {len(selected)}

🏅 <b>Winners:</b>
{chr(10).join(winner_lines)}

🎉 Congratulations to all winners!"""

                cursor.execute(
                    "SELECT channel_id, message_id FROM giveaway_messages WHERE gw_id=?",
                    (gw_id,)
                )
                msg_rows = cursor.fetchall()

                for ch_id, msg_id in msg_rows:
                    try:
                        safe_edit_any(ch_id, int(msg_id), ended_text, reply_markup=None)
                    except:
                        pass

                if selected and prizes:
                    for i, uid in enumerate(selected):
                        prize = prizes[i] if i < len(prizes) else prizes[-1]
                        try:
                            bot.send_message(
                                uid,
                                f"""🎉🎉🎉 <b>CONGRATULATIONS!</b> 🎉🎉🎉

🏆 You are a WINNER of the giveaway:
<b>{title}</b>

🎁 <b>Your Prize:</b>

<code>{prize}</code>

✨ Please share a screenshot in the giveaway chat!

💝 Enjoy your reward!"""
                            )
                        except:
                            pass

                cursor.execute("DELETE FROM participants WHERE gw_id=?", (gw_id,))
                cursor.execute("DELETE FROM giveaway_messages WHERE gw_id=?", (gw_id,))
                conn.commit()
        except Exception as e:
            print("Winner loop error:", e)

        time.sleep(10)

# ================= BOT POLLING LOOP =================

def run_bot():
    while True:
        try:
            print("Polling started...")
            bot.infinity_polling(timeout=60, long_polling_timeout=60, skip_pending=False)
        except Exception as e:
            print("Polling error:", e)
            time.sleep(5)

# ================= MAIN =================

if __name__ == "__main__":
    threading.Thread(target=check_giveaways_loop, daemon=True).start()
    threading.Thread(target=run_bot, daemon=True).start()

    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)