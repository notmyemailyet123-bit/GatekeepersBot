import os
import logging
import asyncio
from io import BytesIO
from fpdf import FPDF
from flask import Flask, request
from telegram import Update, InputFile
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# -----------------------------
# CONFIG
# -----------------------------
TOKEN = os.getenv("BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
PORT = int(os.getenv("PORT", "10000"))
MAX_PHOTOS = 20  # Limit per album

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -----------------------------
# TELEGRAM APP
# -----------------------------
application = Application.builder().token(TOKEN).build()
_initialized = False

# -----------------------------
# USER SESSIONS
# -----------------------------
user_sessions = {}  # {user_id: {"photos": [(photo_bytes, caption)]}}


# -----------------------------
# HELPERS
# -----------------------------
async def initialize_app():
    global _initialized
    if not _initialized:
        await application.initialize()
        await application.start()
        logger.info("Telegram bot initialized and started.")
        _initialized = True


def ensure_event_loop():
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop


def create_pdf_album(photos_with_captions):
    pdf = FPDF()
    for img_bytes, caption in photos_with_captions:
        pdf.add_page()
        # Save image temporarily
        img_file = BytesIO(img_bytes)
        pdf.image(img_file, x=10, y=10, w=180)
        if caption:
            pdf.set_y(200)
            pdf.set_font("Arial", size=12)
            pdf.multi_cell(0, 10, caption)
    output = BytesIO()
    pdf.output(output)
    output.seek(0)
    return output


# -----------------------------
# HANDLERS
# -----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_sessions[update.effective_user.id] = {"photos": []}
    await update.message.reply_text(
        "Welcome to Gatekeepers Album Maker!\nSend me photos to add to your album. "
        "Send /create_album when ready."
    )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_sessions:
        user_sessions[user_id] = {"photos": []}

    if len(user_sessions[user_id]["photos"]) >= MAX_PHOTOS:
        await update.message.reply_text(
            f"You've reached the maximum of {MAX_PHOTOS} photos per album."
        )
        return

    photo_file = await update.message.photo[-1].get_file()
    photo_bytes = await photo_file.download_as_bytearray()
    caption = update.message.caption or ""
    user_sessions[user_id]["photos"].append((photo_bytes, caption))

    await update.message.reply_text(f"Photo added! Total: {len(user_sessions[user_id]['photos'])}")


async def create_album(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_sessions or not user_sessions[user_id]["photos"]:
        await update.message.reply_text("No photos found. Please send some first!")
        return

    album_pdf = create_pdf_album(user_sessions[user_id]["photos"])
    album_pdf_file = InputFile(album_pdf, filename="album.pdf")
    await update.message.reply_document(album_pdf_file)
    await update.message.reply_text("Album created and sent! ✅")

    # Reset session
    user_sessions[user_id]["photos"] = []


# -----------------------------
# REGISTER HANDLERS
# -----------------------------
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("create_album", create_album))
application.add_handler(MessageHandler(filters.PHOTO, handle_photo))


# -----------------------------
# FLASK INTEGRATION
# -----------------------------
@app.before_first_request
def setup_bot_once():
    loop = ensure_event_loop()
    loop.run_until_complete(initialize_app())


@app.route("/", methods=["GET"])
def home():
    return "Gatekeepers Bot is live and running!", 200


@app.route("/webhook", methods=["POST"])
def webhook():
    loop = ensure_event_loop()
    try:
        update_data = request.get_json(force=True)
        update = Update.de_json(update_data, application.bot)
        loop.create_task(application.process_update(update))
        return "OK", 200
    except Exception as e:
        logger.exception("Error processing webhook: %s", e)
        return "Internal Server Error", 500


# -----------------------------
# MAIN
# -----------------------------
if __name__ == "__main__":
    loop = ensure_event_loop()
    loop.run_until_complete(initialize_app())

    render_url = os.getenv("RENDER_EXTERNAL_URL")
    if render_url:
        webhook_url = f"{render_url}/webhook"
        loop.run_until_complete(application.bot.set_webhook(webhook_url))
        logger.info(f"Webhook set to {webhook_url}")

    app.run(host="0.0.0.0", port=PORT)
