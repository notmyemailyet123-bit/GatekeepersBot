import os
import logging
import asyncio
from flask import Flask, request
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

# ----------------------
# Logging setup
# ----------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ----------------------
# Flask app
# ----------------------
app = Flask(__name__)

# ----------------------
# Telegram bot setup
# ----------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable not set")

telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()

# Keep track of albums per user
user_albums = {}  # user_id -> list of albums
first_face_sent = set()  # user_ids who have sent the first face picture

# ----------------------
# Bot commands
# ----------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hello! Send me images and I'll make albums for you. The first face picture will appear only in your first album."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Send photos to add to your albums. Albums are collections of images sent together."
    )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    photos = update.message.photo

    if not photos:
        return

    # Get highest resolution photo
    photo_file = photos[-1].file_id

    # Initialize album for user
    if user_id not in user_albums:
        user_albums[user_id] = []

    album_index = len(user_albums[user_id])

    # For first album only, include the "first face" if not sent yet
    if album_index == 0 and user_id not in first_face_sent:
        # Here you can attach your first face image, e.g., a URL or file_id
        first_face_image = "first_face_file_id_or_url"
        user_albums[user_id].append([first_face_image])

        first_face_sent.add(user_id)

    # Append current photo to the current album
    if album_index < len(user_albums[user_id]):
        user_albums[user_id][album_index].append(photo_file)
    else:
        user_albums[user_id].append([photo_file])

    await update.message.reply_text(f"Added photo to album #{album_index + 1}!")

# ----------------------
# Flask webhook route
# ----------------------
@app.route("/webhook", methods=["POST"])
async def webhook():
    data = await request.get_json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.update_queue.put(update)
    return "ok"

# ----------------------
# Set webhook for Telegram
# ----------------------
async def set_webhook():
    BOT_URL = os.getenv("BOT_URL")
    if not BOT_URL:
        raise RuntimeError("BOT_URL environment variable not set")

    webhook_url = f"{BOT_URL}/webhook"
    await telegram_app.bot.set_webhook(webhook_url)
    logger.info(f"Webhook set to {webhook_url}")

# ----------------------
# Add handlers
# ----------------------
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CommandHandler("help", help_command))
telegram_app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

# ----------------------
# Main
# ----------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))

    # Start webhook setup before running Flask
    asyncio.run(set_webhook())

    # Run Flask
    app.run(host="0.0.0.0", port=port)
