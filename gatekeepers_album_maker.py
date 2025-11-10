import os
import logging
import asyncio
from flask import Flask, request
from telegram import Update, InputMediaPhoto
from telegram.ext import Application, CommandHandler, ContextTypes

# ----------------- CONFIG -----------------
BOT_TOKEN = os.environ.get("BOT_TOKEN")  # Telegram bot token
BOT_URL = os.environ.get("BOT_URL")      # e.g., https://gatekeepersbot.onrender.com
PORT = int(os.environ.get("PORT", 10000))

# ----------------- LOGGING -----------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ----------------- FLASK APP -----------------
app = Flask(__name__)

# ----------------- TELEGRAM BOT -----------------
telegram_app = Application.builder().token(BOT_TOKEN).build()

# ----------------- ALBUMS -----------------
# Each album is a list of image URLs or local paths
albums = {
    "album1": [
        "https://example.com/face1.jpg",  # Only show for first album
        "https://example.com/pic1.jpg",
        "https://example.com/pic2.jpg"
    ],
    "album2": [
        "https://example.com/pic3.jpg",
        "https://example.com/pic4.jpg"
    ],
    "album3": [
        "https://example.com/pic5.jpg",
        "https://example.com/pic6.jpg"
    ]
}

# ----------------- TELEGRAM HANDLERS -----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    await update.message.reply_text(
        "Hello! Send /album <name> to get an album."
    )

async def album(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send an album by name. Only first face picture appears for first album."""
    if not context.args:
        await update.message.reply_text("Usage: /album <album_name>")
        return

    album_name = context.args[0].lower()
    if album_name not in albums:
        await update.message.reply_text("Album not found.")
        return

    pics = albums[album_name]
    media_group = []

    # Show first face pic only for the first album
    if album_name == "album1" and pics:
        media_group.append(InputMediaPhoto(pics[0]))

    # Add the rest of the album
    start_index = 1 if album_name == "album1" else 0
    for pic in pics[start_index:]:
        media_group.append(InputMediaPhoto(pic))

    if media_group:
        await update.message.reply_media_group(media_group)
    else:
        await update.message.reply_text("No images to show.")

# ----------------- REGISTER HANDLERS -----------------
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CommandHandler("album", album))

# ----------------- WEBHOOK ROUTE -----------------
@app.route("/webhook", methods=["POST"])
def webhook():
    """Receive updates from Telegram and push them to the bot's queue"""
    update = Update.de_json(request.get_json(force=True), telegram_app.bot)
    asyncio.run(telegram_app.update_queue.put(update))
    return "OK", 200

# ----------------- SET WEBHOOK -----------------
async def set_webhook():
    webhook_url = f"{BOT_URL}/webhook"
    await telegram_app.bot.set_webhook(webhook_url)
    logger.info(f"Webhook set to {webhook_url}")

# ----------------- START -----------------
if __name__ == "__main__":
    asyncio.run(set_webhook())
    app.run(host="0.0.0.0", port=PORT)
