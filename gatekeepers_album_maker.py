import os
import math
import re
from dotenv import load_dotenv
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    InputMediaVideo,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
    ConversationHandler,
)
from flask import Flask, request
import asyncio
from telegram.error import BadRequest

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.environ.get("PORT", "10000"))

(
    FACE_PHOTO,
    CONTENT_PHOTOS,
    CONTENT_VIDEOS,
    NAME,
    ALIAS,
    COUNTRY,
    FAME,
    SOCIALS,
    CONFIRM,
) = range(9)

app = Flask(__name__)


# === START ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("Send the celebrity’s normal face photo.")
    return FACE_PHOTO


# === STEP 1 ===
async def face_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    photo = update.message.photo[-1]
    context.user_data["face_photo"] = photo.file_id
    context.user_data["photos"] = []
    context.user_data["videos"] = []
    await update.message.reply_text(
        "Now send all photos you want to include. When done, press Next.",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("Next ➡️", callback_data="next_videos")]]
        ),
    )
    return CONTENT_PHOTOS


# === STEP 2 ===
async def content_photos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["photos"].append(update.message.photo[-1].file_id)
    return CONTENT_PHOTOS


async def next_to_videos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "Now send all videos and GIFs you want to include. When done, press Next.",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("Next ➡️", callback_data="next_name")]]
        ),
    )
    return CONTENT_VIDEOS


# === STEP 3 ===
async def content_videos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    media = update.message
    if media.video:
        context.user_data["videos"].append(media.video.file_id)
    elif media.animation:
        context.user_data["videos"].append(media.animation.file_id)
    return CONTENT_VIDEOS


async def next_to_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("What’s the celebrity’s full name?")
    return NAME


# === STEP 4–8 ===
async def name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["name"] = update.message.text.strip()
    await update.message.reply_text("Send their alias or social handles.")
    return ALIAS


async def alias(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["alias"] = update.message.text.strip()
    await update.message.reply_text("Send their country of origin.")
    return COUNTRY


async def country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["country"] = update.message.text.strip()
    await update.message.reply_text("Why is this person famous?")
    return FAME


async def fame(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["fame"] = update.message.text.strip()
    await update.message.reply_text("Send all social links with follower counts.\nExample:\nhttps://www.instagram.com/username 5.7M")
    return SOCIALS


# === STEP 8: SOCIALS ===
def extract_socials(text: str):
    platforms = ["instagram", "youtube", "tiktok", "twitter", "x.com", "facebook", "threads"]
    lines = re.split(r"[,;\n]+", text)
    socials = {}
    for line in lines:
        match = re.search(r"(https?://\S+)\s+([\d\.]+[KkMm]?)", line.strip())
        if match:
            url = match.group(1)
            followers = match.group(2)
            for p in platforms:
                if p in url.lower():
                    socials[p.capitalize()] = (url, followers)
                    break
    return socials


async def socials(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    socials_text = update.message.text.strip()
    context.user_data["socials"] = extract_socials(socials_text)

    text = (
        f"^^^^^^^^^^^^^^^\n\n"
        f"Name: {context.user_data['name']}\n"
        f"Alias: {context.user_data['alias']}\n"
        f"Country: {context.user_data['country']}\n"
        f"Fame: {context.user_data['fame']}\n"
        f"Top socials:\n"
    )

    for name, (url, followers) in context.user_data["socials"].items():
        text += f"{name} ({followers}) - {url}\n"

    text += "\n===============\n"

    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("✅ Confirm", callback_data="confirm")],
                [InlineKeyboardButton("🔁 Restart", callback_data="restart")],
                [InlineKeyboardButton("❌ Exit", callback_data="exit")],
            ]
        ),
    )
    return CONFIRM


# === FINAL: OUTPUT ALBUMS ===
async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    media_files = [context.user_data["face_photo"]] + context.user_data["photos"] + context.user_data["videos"]
    total = len(media_files)
    if total == 0:
        await query.message.reply_text("No media found to create album.")
        return CONFIRM

    chunk_size = math.ceil(total / math.ceil(total / 10))
    albums = [media_files[i:i + chunk_size] for i in range(0, total, chunk_size)]

    for album in albums:
        group = []
        for file_id in album:
            if file_id in context.user_data["videos"]:
                group.append(InputMediaVideo(file_id))
            else:
                group.append(InputMediaPhoto(file_id))
        await query.message.reply_media_group(group)

    await query.message.reply_text("All albums have been sent! Would you like to restart?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔁 Restart", callback_data="restart"),
             InlineKeyboardButton("❌ Exit", callback_data="exit")]
        ])
    )
    return CONFIRM


# === RESTART & EXIT FIX ===
async def restart_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    try:
        await query.answer()
    except BadRequest:
        pass
    context.user_data.clear()
    await query.message.reply_text("✅ Restart successful! Send the celebrity’s normal face photo.")
    return FACE_PHOTO


async def exit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    try:
        await query.answer()
    except BadRequest:
        pass
    await query.message.reply_text("Goodbye! You can type /start anytime to begin again.")
    context.user_data.clear()
    return ConversationHandler.END


# === CONVERSATION HANDLER ===
conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        FACE_PHOTO: [MessageHandler(filters.PHOTO, face_photo)],
        CONTENT_PHOTOS: [
            MessageHandler(filters.PHOTO, content_photos),
            CallbackQueryHandler(next_to_videos, pattern="^next_videos$")
        ],
        CONTENT_VIDEOS: [
            MessageHandler(filters.VIDEO | filters.ANIMATION, content_videos),
            CallbackQueryHandler(next_to_name, pattern="^next_name$")
        ],
        NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name)],
        ALIAS: [MessageHandler(filters.TEXT & ~filters.COMMAND, alias)],
        COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, country)],
        FAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, fame)],
        SOCIALS: [MessageHandler(filters.TEXT & ~filters.COMMAND, socials)],
        CONFIRM: [
            CallbackQueryHandler(confirm, pattern="^confirm$"),
            CallbackQueryHandler(restart_callback, pattern="^restart$"),
            CallbackQueryHandler(exit_callback, pattern="^exit$")
        ],
    },
    fallbacks=[CommandHandler("restart", restart_callback)],
    per_chat=True,
    per_user=True,
)

# === TELEGRAM APP SETUP ===
telegram_app = ApplicationBuilder().token(TOKEN).build()
telegram_app.add_handler(conv_handler)


# === FLASK WEBHOOK ===
@app.route(f"/{TOKEN}", methods=["POST"])
async def webhook() -> str:
    update = Update.de_json(await request.get_json(), telegram_app.bot)
    await telegram_app.process_update(update)
    return "ok"


async def main():
    await telegram_app.bot.set_webhook(f"https://gatekeepersbot.onrender.com/{TOKEN}")
    print("Webhook set successfully!")


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
    app.run(host="0.0.0.0", port=PORT)
