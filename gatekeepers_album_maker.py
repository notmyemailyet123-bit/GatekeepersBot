import os
import re
import logging
import tempfile
from flask import Flask, request
from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)
import requests

# Logging setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")

# Conversation states
(
    STATE_FACE,
    STATE_PHOTOS,
    STATE_VIDEOS,
    STATE_NAME,
    STATE_ALIAS,
    STATE_COUNTRY,
    STATE_FAME,
    STATE_SOCIALS,
    STATE_FINAL_CONFIRM,
) = range(9)

BTN_NEXT = "Next"
BTN_DONE = "Done"

user_data = {}

app = Flask(__name__)

def get_user_key(update: Update) -> str:
    return str(update.effective_user.id)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome to the Gatekeepers Album Maker! Please send your normal face photo to begin."
    )
    return STATE_FACE

async def face_photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_key = get_user_key(update)
    user_data[user_key] = {"face": None, "photos": [], "videos": [], "socials": []}

    photo = update.message.photo[-1]
    file = await photo.get_file()
    file_path = os.path.join(tempfile.gettempdir(), f"{user_key}_face.jpg")
    await file.download_to_drive(file_path)
    user_data[user_key]["face"] = file_path

    await update.message.reply_text(
        "Got it! Now send all the photos you want to include. When you’re done, tap Next.",
        reply_markup=ReplyKeyboardMarkup([[KeyboardButton(BTN_NEXT)]], resize_keyboard=True),
    )
    return STATE_PHOTOS

async def photos_collector(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_key = get_user_key(update)
    photo = update.message.photo[-1]
    file = await photo.get_file()
    file_path = os.path.join(tempfile.gettempdir(), f"{user_key}_photo_{len(user_data[user_key]['photos'])}.jpg")
    await file.download_to_drive(file_path)
    user_data[user_key]["photos"].append(file_path)
    await update.message.reply_text("Photo saved! You can send more or tap Next.")
    return STATE_PHOTOS

async def photos_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Now send all videos or GIFs you want to include. When you’re done, tap Next.",
        reply_markup=ReplyKeyboardMarkup([[KeyboardButton(BTN_NEXT)]], resize_keyboard=True),
    )
    return STATE_VIDEOS

async def videos_collector(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_key = get_user_key(update)
    file_id = None

    if update.message.video:
        file_id = update.message.video.file_id
    elif update.message.animation:
        file_id = update.message.animation.file_id
    elif update.message.document and "video" in (update.message.document.mime_type or ""):
        file_id = update.message.document.file_id

    if file_id:
        file = await context.bot.get_file(file_id)
        file_path = os.path.join(tempfile.gettempdir(), f"{user_key}_video_{len(user_data[user_key]['videos'])}.mp4")
        await file.download_to_drive(file_path)
        user_data[user_key]["videos"].append(file_path)
        await update.message.reply_text("Video saved! Send more or tap Next.")
    else:
        await update.message.reply_text("That doesn’t look like a video. Try again.")
    return STATE_VIDEOS

async def videos_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("What’s the celebrity’s full name?")
    return STATE_NAME

async def receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data[get_user_key(update)]["name"] = update.message.text
    await update.message.reply_text("Got it. What’s their alias or social handle?")
    return STATE_ALIAS

async def receive_alias(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data[get_user_key(update)]["alias"] = update.message.text
    await update.message.reply_text("Cool. What country are they from?")
    return STATE_COUNTRY

async def receive_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data[get_user_key(update)]["country"] = update.message.text
    await update.message.reply_text("Why are they famous?")
    return STATE_FAME

async def receive_fame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data[get_user_key(update)]["fame"] = update.message.text
    await update.message.reply_text(
        "Now send all their social media links. When finished, tap Done.",
        reply_markup=ReplyKeyboardMarkup([[KeyboardButton(BTN_DONE)]], resize_keyboard=True),
    )
    return STATE_SOCIALS

async def socials_collector(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_key = get_user_key(update)
    user_data[user_key]["socials"].append(update.message.text)
    await update.message.reply_text("Link added! You can send more or tap Done.")
    return STATE_SOCIALS

async def finalize_and_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_key = get_user_key(update)
    data = user_data[user_key]
    await update.message.reply_text("Building your album... please wait ⏳")

    # Create final text summary
    summary = (
        f"Name: {data['name']}\n"
        f"Alias: {data['alias']}\n"
        f"Country: {data['country']}\n"
        f"Fame: {data['fame']}\n"
        f"Top socials:\n" + "\n".join(data["socials"])
    )
    await update.message.reply_text("✅ Album created!\n\n" + summary)
    return ConversationHandler.END

async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data[get_user_key(update)] = {"face": None, "photos": [], "videos": [], "socials": []}
    await update.message.reply_text("Restarted! Please send your face photo again.")
    return STATE_FACE

def create_app():
    app_telegram = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            STATE_FACE: [
                MessageHandler(filters.PHOTO & ~filters.COMMAND, face_photo_handler),
                CommandHandler("restart", restart),
            ],
            STATE_PHOTOS: [
                MessageHandler(filters.TEXT & filters.Regex(re.compile(f"^{re.escape(BTN_NEXT)}$", re.I)), photos_next),
                MessageHandler(filters.PHOTO & ~filters.COMMAND, photos_collector),
                CommandHandler("restart", restart),
            ],
            STATE_VIDEOS: [
                MessageHandler(filters.TEXT & filters.Regex(re.compile(f"^{re.escape(BTN_NEXT)}$", re.I)), videos_next),
                MessageHandler(
                    filters.VIDEO
                    | filters.ANIMATION
                    | filters.Document.MimeType("video/")
                    | filters.Create(lambda m: m.document and "video" in (m.document.mime_type or "")),
                    videos_collector,
                ),
                CommandHandler("restart", restart),
            ],
            STATE_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_name),
                CommandHandler("restart", restart),
            ],
            STATE_ALIAS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_alias),
                CommandHandler("restart", restart),
            ],
            STATE_COUNTRY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_country),
                CommandHandler("restart", restart),
            ],
            STATE_FAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_fame),
                CommandHandler("restart", restart),
            ],
            STATE_SOCIALS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, socials_collector),
                MessageHandler(filters.Regex(re.compile(f"^{re.escape(BTN_DONE)}$", re.I)), finalize_and_send),
                CommandHandler("restart", restart),
            ],
        },
        fallbacks=[CommandHandler("restart", restart)],
        allow_reentry=True,
    )

    app_telegram.add_handler(conv_handler)

    @app.route("/webhook", methods=["POST"])
    def webhook():
        update = Update.de_json(request.get_json(force=True), app_telegram.bot)
        app_telegram.update_queue.put_nowait(update)
        return "ok", 200

    async def set_webhook():
        await app_telegram.bot.set_webhook(f"{WEBHOOK_URL}/webhook")
        logger.info("Webhook set successfully.")

    app_telegram.run_webhook = set_webhook
    return app_telegram

if __name__ == "__main__":
    app_obj = create_app()
    import asyncio
    asyncio.run(app_obj.run_webhook())
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
