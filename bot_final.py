import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, CallbackQueryHandler
)
from pymongo import MongoClient
import os

# ==================== CONFIG ====================
BOT_TOKEN = "8749017230:AAHlBCO7q4xirnkKxOCqDzBK2-y5sp2N96k"
OWNER_ID = 6778003842

# MongoDB Atlas URI — apna URI yahan daalo (env variable se lena best hai)
MONGO_URI = os.environ.get("MONGO_URI", "YOUR_MONGODB_URI_HERE")

FORCE_JOIN_CHANNELS = [
    {"name": "🟢 MAIN CHANNEL", "url": "https://t.me/UDDAN_JEE_NEET_BATCH_FREE", "username": "UDDAN_JEE_NEET_BATCH_FREE"},
    {"name": "🔵 BOOK PDF",      "url": "https://t.me/book_store_10_jee_neet",      "username": "book_store_10_jee_neet"},
    {"name": "🔴 GROUP",         "url": "https://t.me/public_group_2026",            "username": "public_group_2026"},
]

MAX_MESSAGE_LENGTH = 4096
# ================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== MONGODB SETUP ====================

mongo_client = MongoClient(MONGO_URI)
db = mongo_client["uddan_bot"]          # Database naam
users_col = db["users"]                 # Users collection


def db_add_user(user_id: int, full_name: str = "", username: str = ""):
    """User ko database mein save karo (already exist kare to skip)."""
    users_col.update_one(
        {"_id": user_id},
        {"$set": {"full_name": full_name, "username": username}, "$setOnInsert": {"_id": user_id}},
        upsert=True
    )


def db_get_all_user_ids() -> list:
    """Sare user IDs lao database se."""
    return [doc["_id"] for doc in users_col.find({}, {"_id": 1})]


def db_user_count() -> int:
    """Total users count."""
    return users_col.count_documents({})


# ==================== HELPER FUNCTIONS ====================

async def send_long_message(bot, chat_id, text, parse_mode="Markdown", reply_markup=None):
    """5000+ character messages ko automatically split karke bhejta hai."""
    if len(text) <= MAX_MESSAGE_LENGTH:
        await bot.send_message(chat_id, text, parse_mode=parse_mode, reply_markup=reply_markup)
        return

    parts = []
    while len(text) > MAX_MESSAGE_LENGTH:
        split_at = text.rfind('\n', 0, MAX_MESSAGE_LENGTH)
        if split_at == -1:
            split_at = MAX_MESSAGE_LENGTH
        parts.append(text[:split_at])
        text = text[split_at:].lstrip('\n')
    parts.append(text)

    for i, part in enumerate(parts):
        markup = reply_markup if i == len(parts) - 1 else None
        await bot.send_message(chat_id, part, parse_mode=parse_mode, reply_markup=markup)


async def is_member(bot, user_id: int, channel_username: str) -> bool:
    try:
        member = await bot.get_chat_member(f"@{channel_username}", user_id)
        return member.status in [
            ChatMember.MEMBER,
            ChatMember.ADMINISTRATOR,
            ChatMember.OWNER,
        ]
    except Exception:
        return False


async def check_force_join(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.effective_user.id
    not_joined = []

    for ch in FORCE_JOIN_CHANNELS:
        joined = await is_member(context.bot, user_id, ch["username"])
        if not joined:
            not_joined.append(ch)

    if not not_joined:
        return True

    buttons = []
    for ch in not_joined:
        buttons.append([InlineKeyboardButton(ch["name"], url=ch["url"])])
    buttons.append([InlineKeyboardButton("✅ Maine Join Kar Liya", callback_data="check_join")])

    keyboard = InlineKeyboardMarkup(buttons)
    text = (
        "⚠️ *Bot Use Karne Ke Liye Pehle In Channels Ko Join Karo!*\n\n"
        "Neeche diye channels join karo, phir *'Maine Join Kar Liya'* button dabao 👇"
    )
    if update.message:
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")
    elif update.callback_query:
        await update.callback_query.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    return False


def get_admin_buttons(user_id: int) -> InlineKeyboardMarkup:
    """Owner ke liye quick action buttons."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📤 Reply", callback_data=f"admin_reply_{user_id}"),
            InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast"),
        ],
        [
            InlineKeyboardButton("📊 Stats", callback_data="admin_stats"),
            InlineKeyboardButton("👤 User Info", callback_data=f"admin_info_{user_id}"),
        ]
    ])


# ==================== FORWARD ALL FILE TYPES TO OWNER ====================

async def forward_media_to_owner(context, user, message):
    """Har type ki file/media owner ko forward karta hai."""
    user_info = (
        f"📩 *Naya Message Aaya!*\n\n"
        f"👤 Name: [{user.full_name}](tg://user?id={user.id})\n"
        f"🆔 User ID: `{user.id}`\n"
        f"🔖 Username: @{user.username if user.username else 'N/A'}\n\n"
    )
    admin_buttons = get_admin_buttons(user.id)

    try:
        if message.text:
            await send_long_message(
                context.bot, OWNER_ID,
                user_info + f"💬 Message:\n{message.text}",
                reply_markup=admin_buttons
            )
        elif message.photo:
            caption = message.caption or ""
            await context.bot.send_photo(
                OWNER_ID, message.photo[-1].file_id,
                caption=user_info + f"🖼️ Photo\n{caption}",
                parse_mode="Markdown", reply_markup=admin_buttons
            )
        elif message.video:
            caption = message.caption or ""
            await context.bot.send_video(
                OWNER_ID, message.video.file_id,
                caption=user_info + f"🎥 Video\n{caption}",
                parse_mode="Markdown", reply_markup=admin_buttons
            )
        elif message.document:
            caption = message.caption or ""
            await context.bot.send_document(
                OWNER_ID, message.document.file_id,
                caption=user_info + f"📄 Document: {message.document.file_name}\n{caption}",
                parse_mode="Markdown", reply_markup=admin_buttons
            )
        elif message.audio:
            caption = message.caption or ""
            await context.bot.send_audio(
                OWNER_ID, message.audio.file_id,
                caption=user_info + f"🎵 Audio\n{caption}",
                parse_mode="Markdown", reply_markup=admin_buttons
            )
        elif message.voice:
            await context.bot.send_voice(
                OWNER_ID, message.voice.file_id,
                caption=user_info + "🎤 Voice Message",
                parse_mode="Markdown", reply_markup=admin_buttons
            )
        elif message.video_note:
            await context.bot.send_message(OWNER_ID, user_info + "📹 Video Note:", parse_mode="Markdown")
            await context.bot.send_video_note(OWNER_ID, message.video_note.file_id, reply_markup=admin_buttons)
        elif message.sticker:
            await context.bot.send_message(OWNER_ID, user_info + "🎭 Sticker:", parse_mode="Markdown")
            await context.bot.send_sticker(OWNER_ID, message.sticker.file_id, reply_markup=admin_buttons)
        elif message.animation:
            caption = message.caption or ""
            await context.bot.send_animation(
                OWNER_ID, message.animation.file_id,
                caption=user_info + f"🎞️ GIF\n{caption}",
                parse_mode="Markdown", reply_markup=admin_buttons
            )
        elif message.location:
            await context.bot.send_message(OWNER_ID, user_info + "📍 Location:", parse_mode="Markdown")
            await context.bot.send_location(
                OWNER_ID, message.location.latitude, message.location.longitude,
                reply_markup=admin_buttons
            )
        elif message.contact:
            await context.bot.send_message(OWNER_ID, user_info + "📞 Contact:", parse_mode="Markdown")
            await context.bot.send_contact(
                OWNER_ID, message.contact.phone_number, message.contact.first_name,
                last_name=message.contact.last_name, reply_markup=admin_buttons
            )
        else:
            await send_long_message(
                context.bot, OWNER_ID,
                user_info + "📨 Unknown type ka message aaya.",
                reply_markup=admin_buttons
            )
    except Exception as e:
        logger.warning(f"Media forward failed: {e}")


# ==================== COMMANDS ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    joined = await check_force_join(update, context)
    if not joined:
        return

    # MongoDB mein save karo
    db_add_user(user.id, user.full_name, user.username or "")

    try:
        await context.bot.send_message(
            OWNER_ID,
            f"🔔 *New User Started Bot!*\n\n"
            f"👤 Name: [{user.full_name}](tg://user?id={user.id})\n"
            f"🆔 User ID: `{user.id}`\n"
            f"🔖 Username: @{user.username if user.username else 'N/A'}\n"
            f"👥 Total Users: `{db_user_count()}`",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.warning(f"Owner notify failed: {e}")

    await update.message.reply_text(
        f"👋 *Namaste {user.first_name}!*\n\n"
        f"🎓 *UDDAN JEE/NEET Bot* mein aapka swagat hai!\n\n"
        f"📚 Yahan aapko best study material milega.\n"
        f"Koi bhi sawaal poochho, hum help karenge! ✅\n\n"
        f"📎 Aap Text, Photo, Video, PDF — kuch bhi bhej sakte ho!",
        parse_mode="Markdown"
    )


async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner-only: /broadcast ya /bc <message>"""
    user = update.effective_user
    if user.id != OWNER_ID:
        await update.message.reply_text("❌ Sirf Owner is command ka use kar sakta hai!")
        return

    if not context.args:
        await update.message.reply_text(
            "📢 *Broadcast Usage:*\n\n"
            "`/broadcast Aapka message yahan likho`\n"
            "`/bc Shortcut bhi use kar sakte ho`",
            parse_mode="Markdown"
        )
        return

    broadcast_text = " ".join(context.args)
    user_ids = db_get_all_user_ids()   # ✅ MongoDB se lao
    sent = 0
    failed = 0

    await update.message.reply_text(f"📢 Broadcast shuru ho raha hai... {len(user_ids)} users ko bhejenge.")

    for uid in user_ids:
        try:
            await send_long_message(
                context.bot, uid,
                f"📢 *Broadcast Message:*\n\n{broadcast_text}"
            )
            sent += 1
        except Exception:
            failed += 1

    await update.message.reply_text(
        f"✅ *Broadcast Complete!*\n\n"
        f"📤 Sent: {sent}\n"
        f"❌ Failed: {failed}",
        parse_mode="Markdown"
    )


async def reply_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner only: /reply <user_id> <message> ya /r <user_id> <message>"""
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Sirf Owner is command ka use kar sakta hai!")
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "📤 *Reply Usage:*\n\n"
            "`/reply 123456789 Aapka jawab`\n"
            "`/r 123456789 Shortcut`\n\n"
            "💡 Tip: DM notification ke buttons se directly reply karo!",
            parse_mode="Markdown"
        )
        return

    try:
        target_id = int(context.args[0])
        msg = " ".join(context.args[1:])
        await send_long_message(
            context.bot, target_id,
            f"📬 *Owner ka Reply:*\n\n{msg}"
        )
        await update.message.reply_text(
            f"✅ Message bhej diya!\n"
            f"👤 To: [User](tg://user?id={target_id}) (`{target_id}`)",
            parse_mode="Markdown"
        )
    except ValueError:
        await update.message.reply_text("❌ User ID galat hai! Sirf numbers likhein.")
    except Exception as e:
        await update.message.reply_text(f"❌ Message nahi gaya: {e}")


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show bot stats — /stats ya /s"""
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Sirf Owner dekh sakta hai!")
        return
    total = db_user_count()   # ✅ MongoDB se lao
    await update.message.reply_text(
        f"📊 *Bot Stats:*\n\n👥 Total Users: `{total}`",
        parse_mode="Markdown"
    )


# ==================== CALLBACK HANDLERS ====================

async def check_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    joined = await check_force_join(update, context)
    if not joined:
        return

    db_add_user(user.id, user.full_name, user.username or "")

    try:
        await context.bot.send_message(
            OWNER_ID,
            f"✅ *User Ne Channels Join Kar Liye!*\n\n"
            f"👤 Name: [{user.full_name}](tg://user?id={user.id})\n"
            f"🆔 User ID: `{user.id}`\n"
            f"🔖 Username: @{user.username if user.username else 'N/A'}",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.warning(f"Owner notify failed: {e}")

    await query.message.edit_text(
        f"✅ *Shukriya {user.first_name}! Aap join ho gaye.*\n\n"
        f"Ab aap bot ka pura use kar sakte ho! 🎉\n\n"
        f"📎 Text, Photo, Video, PDF — kuch bhi bhej sakte ho!",
        parse_mode="Markdown"
    )


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin buttons ke callbacks handle karta hai."""
    query = update.callback_query
    await query.answer()

    if query.from_user.id != OWNER_ID:
        await query.answer("❌ Sirf Owner use kar sakta hai!", show_alert=True)
        return

    data = query.data

    if data.startswith("admin_reply_"):
        target_id = data.replace("admin_reply_", "")
        await query.message.reply_text(
            f"📤 *Reply Karo:*\n\n"
            f"`/r {target_id} Aapka jawab yahan`\n\n"
            f"User Tag: [Click Here](tg://user?id={target_id})",
            parse_mode="Markdown"
        )

    elif data == "admin_broadcast":
        await query.message.reply_text(
            "📢 *Broadcast Karo:*\n\n"
            "`/bc Aapka broadcast message`",
            parse_mode="Markdown"
        )

    elif data == "admin_stats":
        total = db_user_count()
        await query.message.reply_text(
            f"📊 *Bot Stats:*\n\n👥 Total Users: `{total}`",
            parse_mode="Markdown"
        )

    elif data.startswith("admin_info_"):
        target_id = data.replace("admin_info_", "")
        await query.message.reply_text(
            f"👤 *User Info:*\n\n"
            f"🆔 User ID: `{target_id}`\n"
            f"🔗 Profile: [Click Here](tg://user?id={target_id})\n\n"
            f"Quick Reply:\n`/r {target_id} Aapka jawab`",
            parse_mode="Markdown"
        )


# ==================== DM HANDLER ====================

async def dm_notify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.message

    if user.id == OWNER_ID:
        return

    joined = await check_force_join(update, context)
    if not joined:
        return

    # MongoDB mein save karo
    db_add_user(user.id, user.full_name, user.username or "")

    await forward_media_to_owner(context, user, message)
    await message.reply_text("✅ Aapka message mil gaya! Jald hi reply milega. 🙏")


# ==================== SAVE USER ====================

async def save_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Har interacting user ko MongoDB mein save karo."""
    user = update.effective_user
    if user:
        db_add_user(user.id, user.full_name or "", user.username or "")


# ==================== MAIN ====================

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Group -1: Sabse pehle har user save ho
    app.add_handler(MessageHandler(filters.ALL, save_user), group=-1)

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("bc", broadcast))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("s", stats))
    app.add_handler(CommandHandler("reply", reply_user))
    app.add_handler(CommandHandler("r", reply_user))

    # Callbacks
    app.add_handler(CallbackQueryHandler(check_join_callback, pattern="^check_join$"))
    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin_"))

    # DM handler
    dm_filter = filters.ChatType.PRIVATE & ~filters.COMMAND
    app.add_handler(MessageHandler(dm_filter, dm_notify))

    print("🤖 Bot chal raha hai... (MongoDB connected)")
    print("📌 Shortcuts: /r = reply | /bc = broadcast | /s = stats")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
