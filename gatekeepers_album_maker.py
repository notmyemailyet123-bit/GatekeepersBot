import os
import re
import logging
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

# ----- Logging -----
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ----- Environment variables -----
BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", 10000))
WEBHOOK_URL = f"https://gatekeepersbot.onrender.com/{BOT_TOKEN}"

# ----- States for ConversationHandler -----
NORMAL_FACE, CONTENT_PHOTOS, SOCIAL_LINKS = range(3)

# Temporary storage
user_data_store = {}

# Ensure photos directory exists
os.makedirs("photos", exist_ok=True)

# ----- Handlers -----

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_data_store[user_id] = {"normal_face": None, "content_photos": [], "social_links": {}}
    logger.info(f"User {user_id} started a conversation")
    await update.message.reply_text("Welcome! Send the celebrity's normal face photo to start.")
    return NORMAL_FACE


async def receive_normal_face(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not update.message.photo:
        await update.message.reply_text("Please send a photo to continue.")
        return NORMAL_FACE

    photo = await update.message.photo[-1].get_file()
    path = f"photos/{photo.file_id}.jpg"
    await photo.download_to_drive(path)

    user_data_store[user_id]["normal_face"] = path
    logger.info(f"User {user_id} sent normal face photo: {path}")
    await update.message.reply_text(
        "Normal face received! Now send the celebrity's content photos one at a time. Send 'Done' when finished."
    )
    return CONTENT_PHOTOS


async def receive_content_photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text

    if text and text.lower() == "done":
        await update.message.reply_text(
            "Great! Now send the celebrity's social media links (YouTube, Instagram, TikTok, or any other) one at a time. Send 'Done' when finished."
        )
        logger.info(f"User {user_id} finished sending content photos")
        return SOCIAL_LINKS

    if update.message.photo:
        photo = await update.message.photo[-1].get_file()
        path = f"photos/{photo.file_id}.jpg"
        await photo.download_to_drive(path)
        user_data_store[user_id]["content_photos"].append(path)
        logger.info(f"User {user_id} sent content photo: {path}")
        await update.message.reply_text("Photo saved. Send another or 'Done' if finished.")
        return CONTENT_PHOTOS

    await update.message.reply_text("Please send a photo or 'Done'.")
    return CONTENT_PHOTOS


async def receive_social_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text

    if text.lower() == "done":
        data = user_data_store[user_id]
        social_text = "\n".join(f"{platform}: {link}" for platform, link in data["social_links"].items())
        await update.message.reply_text(
            f"All done! Here is a summary:\n"
            f"Normal face: {data['normal_face']}\n"
            f"Content photos: {len(data['content_photos'])}\n"
            f"Social media links:\n{social_text or 'None'}"
        )
        logger.info(f"User {user_id} finished sending social links")
        return ConversationHandler.END

    platform = detect_social_platform(text)
    if platform:
        user_data_store[user_id]["social_links"][platform] = text
        logger.info(f"User {user_id} added social link: {platform} -> {text}")
        await update.message.reply_text(f"{platform} link saved. Send another or 'Done'.")
    else:
        await update.message.reply_text("Link not recognized. Send a valid URL or 'Done'.")
        logger.warning(f"User {user_id} sent unrecognized link: {text}")

    return SOCIAL_LINKS

# ----- Utility -----
def detect_social_platform(url: str) -> str:
    url = url.lower()
    if "instagram.com" in url:
        return "Instagram"
    elif "youtube.com" in url or "youtu.be" in url:
        return "YouTube"
    elif "tiktok.com" in url:
        return "TikTok"
    else:
        match = re.search(r"https?://(?:www\.)?([^/]+)", url)
        if match:
            return match.group(1)
    return None

# ----- ConversationHandler -----
conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        NORMAL_FACE: [MessageHandler(filters.PHOTO, receive_normal_face)],
        CONTENT_PHOTOS: [
            MessageHandler(filters.PHOTO | (filters.TEXT & (~filters.COMMAND)), receive_content_photos)
        ],
        SOCIAL_LINKS: [
            MessageHandler(filters.TEXT & (~filters.COMMAND), receive_social_links)
        ],
    },
    fallbacks=[],
)

# ----- Application -----
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(conv_handler)

# ----- Run Webhook -----
logger.info(f"Starting bot with webhook: {WEBHOOK_URL}")
app.run_webhook(
    listen="0.0.0.0",
    port=PORT,
    webhook_url=WEBHOOK_URL,
)
