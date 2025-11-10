import asyncio
import logging
from flask import Flask, request
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
from fpdf import FPDF
from PIL import Image
import io
import os

# ----- Logging -----
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ----- Flask app -----
app = Flask(__name__)
app.bot_initialized = False  # ensure bot initializes only once

# ----- Telegram bot async setup -----
async def initialize_app():
    bot_token = os.environ.get('BOT_TOKEN')  # put your token in environment variables
    if not bot_token:
        raise ValueError("BOT_TOKEN environment variable not set")

    app.telegram_app = ApplicationBuilder().token(bot_token).build()

    # Command handler: /start
    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Welcome! Send me images and I'll make a PDF album.")

    # Message handler: receive images
    async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
        photos = update.message.photo
        if not photos:
            await update.message.reply_text("No photo found!")
            return

        # Take the highest quality image
        photo_file = await photos[-1].get_file()
        photo_bytes = io.BytesIO()
        await photo_file.download_to_memory(out=photo_bytes)
        photo_bytes.seek(0)

        # Store photo in user session
        user_id = update.message.from_user.id
        if 'images' not in context.user_data:
            context.user_data['images'] = []
        context.user_data['images'].append(photo_bytes)

        await update.message.reply_text(f"Image added! You have {len(context.user_data['images'])} images.")

    # Command handler: /generate
    async def generate_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
        images = context.user_data.get('images', [])
        if not images:
            await update.message.reply_text("No images to generate PDF!")
            return

        pdf = FPDF()
        for img_bytes in images:
            img_bytes.seek(0)
            img = Image.open(img_bytes)
            img_path = f"/tmp/{user_id}.png"
            img.save(img_path)
            pdf.add_page()
            pdf.image(img_path, x=10, y=10, w=180)
            os.remove(img_path)

        pdf_bytes = io.BytesIO()
        pdf.output(pdf_bytes)
        pdf_bytes.seek(0)

        await update.message.reply_document(pdf_bytes, filename="album.pdf")
        context.user_data['images'] = []  # reset after sending

    # Add handlers
    app.telegram_app.add_handler(CommandHandler('start', start))
    app.telegram_app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.telegram_app.add_handler(CommandHandler('generate', generate_pdf))

    # Start bot
    await app.telegram_app.initialize()
    await app.telegram_app.start()
    logger.info("Telegram bot initialized and started.")

# ----- Flask hooks -----
@app.before_request
def setup_bot_once():
    if not app.bot_initialized:
        asyncio.run(initialize_app())
        app.bot_initialized = True

# ----- Webhook endpoint -----
@app.route('/webhook', methods=['POST'])
def webhook():
    update = request.get_json(force=True)
    asyncio.run(app.telegram_app.update_queue.put(Update.de_json(update, app.telegram_app.bot)))
    return "OK", 200

# ----- Simple test route -----
@app.route('/', methods=['GET'])
def index():
    return "Gatekeepers Bot is running!", 200

# ----- Run Flask -----
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
